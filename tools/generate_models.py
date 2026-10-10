#!/usr/bin/env python3
"""Generate the 3D map models for the King in Yellow (Hastur) units.

Builds three detailed static models procedurally - human figures on real
anatomical proportions dressed in hanging cloth, and a Byakhee with plausible
flying-creature anatomy - and writes them in the
Clausewitz binary .mesh format, together with a 1024px texture set and the
mesh/entity definitions HoI4 needs:

    gfx/models/units/eldritch/*.mesh            the models
    gfx/models/units/eldritch/*.dds             shared texture atlas (diffuse, normal, specular)
    gfx/entities/eldritch_hastur_meshes.gfx     pdxmesh definitions (with the in-game scale)
    gfx/entities/eldritch_hastur_units.asset    <sprite>_entity definitions used by the battalions

Clausewitz conventions (from the community io_pdx_mesh exporter/importer):
  * Y is up, models face -Z, UV v=0 is the top of the texture, and triangles
    are wound so that (B - A) x (C - A) points out of the surface.
  * Tangents are (x, y, z, w) with w = sign(dot(cross(N, T), dP/dv)).
  * Normal maps: X in green, Y (up) in alpha; blue is an emissive mask.
  * Specular maps: R = mask, G = specular level, B = metalness, A = roughness.

Usage:
    python3 tools/generate_models.py                  write everything
    python3 tools/generate_models.py --preview DIR    also render preview PNGs into DIR

Requires numpy and Pillow. Output is deterministic.
"""

import functools
import math
import os
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = "gfx/models/units/eldritch"
TEXTURE = "eldritch_hastur"
ATLAS = 1024
SPEC_SIZE = 512

# In-game size multiplier written into the pdxmesh definitions. The models are
# authored at roughly human scale (a zealot is ~1.9 units tall); raise or lower
# this if units look too small or too large on the map.
MESH_SCALE = 2.0

# Atlas regions in pixels: x0, y0, x1, y1 (y grows downwards, like UV v).
REGIONS = {
    "cloth": (0, 0, 512, 512),
    "lining": (512, 0, 768, 256),
    "bandage": (768, 0, 1024, 256),
    "tentacle": (512, 256, 1024, 512),
    "leather": (0, 512, 512, 768),
    "membrane": (0, 768, 512, 1024),
    "bone": (512, 512, 768, 640),
    "metal": (768, 512, 1024, 640),
    "wood": (512, 640, 768, 768),
    "glow": (768, 640, 896, 768),
    "sucker": (896, 640, 1024, 768),
    "banner": (512, 768, 1024, 1024),
}


def region_uv(name, s, t, margin=0.012):
    """Map (s, t) in [0, 1] (t = 0 is the top of the region) into atlas UVs."""
    x0, y0, x1, y1 = REGIONS[name]
    s = margin + (1 - 2 * margin) * min(max(s, 0.0), 1.0)
    t = margin + (1 - 2 * margin) * min(max(t, 0.0), 1.0)
    return ((x0 + s * (x1 - x0)) / ATLAS, (y0 + t * (y1 - y0)) / ATLAS)


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def normalize(v):
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def smoothstep(a, b, x):
    t = min(max((x - a) / (b - a), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def align_y_to(d):
    """Rotation matrix taking +Y onto direction d."""
    d = normalize(d)
    y = np.array([0.0, 1.0, 0.0])
    v = np.cross(y, d)
    c = float(np.dot(y, d))
    if np.linalg.norm(v) < 1e-9:
        return np.eye(3) if c > 0 else rot_x(math.pi)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * (1 / (1 + c))


@functools.lru_cache(maxsize=None)
def _noise_coeffs(seed):
    rng = np.random.default_rng(seed)
    k = np.arange(1, 9)
    amp = rng.uniform(0.3, 1.0, 8) / k
    return k, amp, rng.uniform(0, 2 * math.pi, 8), float(np.sum(amp))


def hash_noise(x, seed=0):
    """Smooth 1D noise in [-1, 1], periodic with period 1 when x spans [0, 1)."""
    k, amp, ph, total = _noise_coeffs(seed)
    return float(np.sum(amp * np.sin(2 * math.pi * k * x + ph))) / total


# ---------------------------------------------------------------------------
# Mesh building
# ---------------------------------------------------------------------------

class MeshBuilder:
    def __init__(self):
        self.p, self.n, self.uv, self.tris = [], [], [], []

    def vert(self, p, n, uv):
        self.p.append(np.asarray(p, dtype=float))
        self.n.append(normalize(n))
        self.uv.append((float(uv[0]), float(uv[1])))
        return len(self.p) - 1

    def tri(self, a, b, c, outward=None):
        pa, pb, pc = self.p[a], self.p[b], self.p[c]
        cross = np.cross(pb - pa, pc - pa)
        if np.linalg.norm(cross) < 1e-14:
            return
        if outward is None:
            outward = self.n[a] + self.n[b] + self.n[c]
        if np.dot(cross, outward) < 0:
            b, c = c, b
        self.tris.append((a, b, c))

    def surface(self, fn, nu, nv, region, closed_u=False, outward=None, inner_region=None, skip=None,
                uv_fn=None):
        """Parametric surface fn(s, t) -> point, s, t in [0, 1].

        Normals come from finite differences and are oriented by outward(p, s, t).
        inner_region adds a back side (double-sided cloth). skip(s, t) removes a
        quad (holes, tatters). uv_fn(s, t) overrides the (s, t) -> region mapping.
        """
        eps = 1e-3
        grid_p = [[np.asarray(fn(i / nu, j / nv), float) for i in range(nu + 1)] for j in range(nv + 1)]

        def normal_at(i, j):
            s, t = i / nu, j / nv
            if closed_u:
                sa, sb = (s - eps) % 1.0, (s + eps) % 1.0
            else:
                sa, sb = max(s - eps, 0.0), min(s + eps, 1.0)
            ta, tb = max(t - eps, 0.0), min(t + eps, 1.0)
            du = np.asarray(fn(sb, t), float) - np.asarray(fn(sa, t), float)
            dv = np.asarray(fn(s, tb), float) - np.asarray(fn(s, ta), float)
            n = np.cross(du, dv)
            p = grid_p[j][i]
            hint = outward(p, s, t) if outward else n
            if np.linalg.norm(n) < 1e-10:
                return normalize(hint)
            n = normalize(n)
            return n if np.dot(n, hint) >= 0 else -n

        normals = [[normal_at(i, j) for i in range(nu + 1)] for j in range(nv + 1)]
        sides = [(1, region)] + ([(-1, inner_region)] if inner_region else [])
        for sign, reg in sides:
            idx = []
            for j in range(nv + 1):
                row = []
                for i in range(nu + 1):
                    s, t = i / nu, j / nv
                    uv = uv_fn(s, t) if uv_fn else region_uv(reg, s, t)
                    if uv_fn and sign < 0:
                        uv = region_uv(reg, s, t)
                    row.append(self.vert(grid_p[j][i], normals[j][i] * sign, uv))
                idx.append(row)
            for j in range(nv):
                for i in range(nu):
                    if skip and skip((i + 0.5) / nu, (j + 0.5) / nv):
                        continue
                    a, b, c, d = idx[j][i], idx[j][i + 1], idx[j + 1][i + 1], idx[j + 1][i]
                    self.tri(a, b, c)
                    self.tri(a, c, d)

    def lathe(self, profile, region, segs=16, center=(0, 0, 0), rot=None, scale=(1, 1, 1)):
        """Surface of revolution around local +Y. profile: [(r, y), ...] bottom to top."""
        rot = np.eye(3) if rot is None else rot
        scale = np.asarray(scale, float)
        center = np.asarray(center, float)
        pts = np.asarray(profile, float)
        prof_n = []
        for i in range(len(pts)):
            a, b = pts[max(i - 1, 0)], pts[min(i + 1, len(pts) - 1)]
            prof_n.append(normalize((b[1] - a[1], -(b[0] - a[0]))))
        rings = []
        for i, (r, y) in enumerate(pts):
            ring = []
            for j in range(segs + 1):
                t = 2 * math.pi * j / segs
                local = np.array([r * math.cos(t), y, r * math.sin(t)])
                nr, ny = prof_n[i]
                ln = np.array([nr * math.cos(t), ny, nr * math.sin(t)])
                uv = region_uv(region, j / segs, 1 - i / max(len(pts) - 1, 1))
                ring.append(self.vert(rot @ (local * scale) + center, rot @ (ln / scale), uv))
            rings.append(ring)
        for i in range(len(rings) - 1):
            for j in range(segs):
                a, b, c, d = rings[i][j], rings[i][j + 1], rings[i + 1][j + 1], rings[i + 1][j]
                self.tri(a, b, c)
                self.tri(a, c, d)

    def ellipsoid(self, center, radii, region, segs=16, rings=10, rot=None):
        profile = [(math.sin(math.pi * k / rings), -math.cos(math.pi * k / rings)) for k in range(rings + 1)]
        self.lathe(profile, region, segs=segs, center=center, rot=rot, scale=radii)

    def cone(self, base, apex, radius, region, segs=8, flat=1.0):
        base, apex = np.asarray(base, float), np.asarray(apex, float)
        h = np.linalg.norm(apex - base)
        self.lathe([(0.0, 0.0), (radius, 0.0), (radius * 0.6, h * 0.5), (0.0, h)], region, segs=segs,
                   center=base, rot=align_y_to(apex - base), scale=(1, 1, flat))

    def tube(self, path, radii, region, segs=10, inner=None, cap=True, ring_mod=None):
        """Tube along a polyline. inner: per-point 'inner side' direction; that side
        maps to u = 0.5 of the region. ring_mod(i, a) scales the radius around each
        ring (cloth folds). Returns the ring frames for placing details."""
        path = [np.asarray(p, float) for p in path]
        n_pts = len(path)
        tangents = [normalize(path[min(i + 1, n_pts - 1)] - path[max(i - 1, 0)]) for i in range(n_pts)]
        frames = []
        ref = None
        for i in range(n_pts):
            T = tangents[i]
            if inner is not None:
                ref = np.asarray(inner[i], float)
            elif ref is None:
                ref = np.array([0.0, 1.0, 0.0]) if abs(T[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
            I = normalize(ref - T * np.dot(ref, T))
            if np.linalg.norm(I) < 1e-6:
                I = normalize(np.cross(T, [1.0, 0.0, 0.0]))
            if inner is None:
                ref = I  # parallel transport
            frames.append((T, I, np.cross(T, I)))
        length = [0.0]
        for i in range(1, n_pts):
            length.append(length[-1] + np.linalg.norm(path[i] - path[i - 1]))
        total = max(length[-1], 1e-9)
        pos = np.zeros((n_pts, segs + 1, 3))
        dirs = np.zeros((n_pts, segs + 1, 3))
        for i in range(n_pts):
            T, I, S = frames[i]
            for j in range(segs + 1):
                a = 2 * math.pi * j / segs
                d = -math.cos(a) * I + math.sin(a) * S  # a = pi -> inner side
                r = radii[i] * (ring_mod(i, a) if ring_mod else 1.0)
                pos[i, j] = path[i] + d * r
                dirs[i, j] = d
        rings = []
        for i in range(n_pts):
            ring = []
            for j in range(segs + 1):
                n = dirs[i, j]
                if ring_mod:
                    da = pos[i, (j + 1) % segs] - pos[i, (j - 1) % segs]
                    dl = pos[min(i + 1, n_pts - 1), j] - pos[max(i - 1, 0), j]
                    c = np.cross(dl, da)
                    if np.linalg.norm(c) > 1e-12:
                        c = normalize(c)
                        n = c if np.dot(c, dirs[i, j]) > 0 else -c
                ring.append(self.vert(pos[i, j], n, region_uv(region, j / segs, length[i] / total)))
            rings.append(ring)
        for i in range(n_pts - 1):
            for j in range(segs):
                a, b, c, d = rings[i][j], rings[i][j + 1], rings[i + 1][j + 1], rings[i + 1][j]
                self.tri(a, b, c)
                self.tri(a, c, d)
        if cap and radii[-1] > 1e-4:
            T = frames[-1][0]
            tip = self.vert(path[-1] + T * radii[-1], T, region_uv(region, 0.5, 1.0))
            for j in range(segs):
                self.tri(rings[-1][j], rings[-1][j + 1], tip, outward=T)
        return frames

    def sucker(self, p, n, rs, segs=8):
        self.lathe([(0.85 * rs, -0.25 * rs), (rs, 0.22 * rs), (0.88 * rs, 0.40 * rs), (0.55 * rs, 0.32 * rs),
                    (0.0, 0.06 * rs)], "sucker", segs=segs, center=p, rot=align_y_to(n))

    def merge(self, other, rot=None, offset=(0, 0, 0), scale=1.0):
        rot = np.eye(3) if rot is None else rot
        base = len(self.p)
        for p, n, uv in zip(other.p, other.n, other.uv):
            self.p.append(rot @ (p * scale) + np.asarray(offset, float))
            self.n.append(rot @ n)
            self.uv.append(uv)
        self.tris += [(a + base, b + base, c + base) for a, b, c in other.tris]


# ---------------------------------------------------------------------------
# Models (Y up, facing -Z; the back of every model is +Z)
#
# Every figure is built on real human proportions - 1.80 m tall, a 0.23 m
# head, 0.42 m shoulders, 0.30 m upper arms and 0.27 m forearms - and dressed
# in cloth that hangs from that body.
# ---------------------------------------------------------------------------

def radial(theta):
    """Unit direction around the Y axis; theta = 0 is the back (+Z), pi the front (-Z)."""
    return np.array([math.sin(theta), 0.0, math.cos(theta)])


def catmull(keys, x):
    """Catmull-Rom interpolation of value tuples over keys [(x, values), ...] sorted by x."""
    xs = [k[0] for k in keys]
    vals = [np.asarray(k[1], float) for k in keys]
    if x <= xs[0]:
        return vals[0]
    if x >= xs[-1]:
        return vals[-1]
    i = max(j for j in range(len(xs) - 1) if xs[j] <= x)
    x0, x1 = xs[i], xs[i + 1]
    u = (x - x0) / (x1 - x0)
    p0, p1, p2, p3 = vals[max(i - 1, 0)], vals[i], vals[i + 1], vals[min(i + 2, len(vals) - 1)]
    m1 = (p2 - p0) / max(xs[i + 1] - xs[max(i - 1, 0)], 1e-9) * (x1 - x0)
    m2 = (p3 - p1) / max(xs[min(i + 2, len(xs) - 1)] - xs[i], 1e-9) * (x1 - x0)
    u2, u3 = u * u, u * u * u
    return (2 * u3 - 3 * u2 + 1) * p1 + (u3 - 2 * u2 + u) * m1 + (-2 * u3 + 3 * u2) * p2 + (u3 - u2) * m2


def polyline_point(pts, s):
    """Point at fraction s along a polyline (by length)."""
    pts = [np.asarray(p, float) for p in pts]
    seg = [np.linalg.norm(pts[i + 1] - pts[i]) for i in range(len(pts) - 1)]
    target = s * sum(seg)
    for i, L in enumerate(seg):
        if target <= L or i == len(seg) - 1:
            f = min(target / max(L, 1e-9), 1.0)
            return pts[i] + (pts[i + 1] - pts[i]) * f
        target -= L
    return pts[-1]


def smooth_path(pts, n):
    """Catmull-Rom resampling of control points into n points."""
    keys = [(i / (len(pts) - 1), p) for i, p in enumerate(pts)]
    return [catmull(keys, k / (n - 1)) for k in range(n)]


def superellipse(theta, W, D, n=2.4):
    s, c = math.sin(theta), math.cos(theta)
    return W * math.copysign(abs(s) ** (2 / n), s), D * math.copysign(abs(c) ** (2 / n), c)


def drape(theta, y, seed, ks=(9, 14, 23), weights=(0.55, 0.30, 0.15)):
    """Hanging cloth folds in [-1, 1]."""
    k, amp, ph, _ = _noise_coeffs(seed)
    v = 0.0
    for i, (kk, w) in enumerate(zip(ks, weights)):
        v += w * math.sin(kk * theta + ph[i] + y * (1.2 + 0.9 * i) * (amp[i] * 4 - 1))
    return v


def cloth_sweep(m, keys, y_top, y_bot, fold_amp, seed, nu, nv, region="cloth", inner="lining", n_exp=2.4,
                skip=None, ks=(9, 14, 23)):
    """A garment hanging from y_top down to y_bot(s) (number or function of s).

    keys: [(y, (W, D, zc)), ...] sorted by y - half-width, half-depth and centre z
    of the body/garment cross-section at that height. fold_amp(y): fold depth (m).
    """
    def hem(s):
        return y_bot(s) if callable(y_bot) else y_bot

    def fn(s, t):
        th = 2 * math.pi * s
        y = y_top + (hem(s) - y_top) * t
        W, D, zc = catmull(keys, y)
        x, z = superellipse(th, W, D, n_exp)
        g = normalize((x / max(W, 1e-6) ** 2, z / max(D, 1e-6) ** 2))
        a = fold_amp(y) * drape(th, y, seed, ks)
        return np.array([x + g[0] * a, y, z + g[1] * a + zc])

    def outward(p, s, t):
        zc = catmull(keys, p[1])[2]
        return np.array([p[0], 0.0, p[2] - zc])

    m.surface(fn, nu, nv, region, closed_u=True, inner_region=inner, skip=skip, outward=outward)


def bandaged_head(m, c, scale, res):
    """A head with brow, eye sockets, nose, cheekbones and chin, wrapped in bandages."""
    c = np.asarray(c, float)
    hx, hy, hz = 0.074, 0.115, 0.096

    def fn(s, t):
        th = 2 * math.pi * s
        e = -math.pi / 2 + math.pi * t
        ce, se = math.cos(e), math.sin(e)
        x, y, z = hx * ce * math.sin(th), hy * se, hz * ce * math.cos(th)
        if se < 0:  # jaw narrows
            x *= 1 - 0.22 * -se
            z *= 1 - 0.06 * -se
        front = max(0.0, -math.cos(th))
        lat = math.sin(th)
        bump = (0.024 * math.exp(-(lat / 0.11) ** 2) * math.exp(-((se + 0.08) / 0.20) ** 2)      # nose
                + 0.010 * math.exp(-((se - 0.30) / 0.08) ** 2) * (1 - 0.5 * abs(lat))             # brow
                - 0.012 * math.exp(-((abs(lat) - 0.33) / 0.12) ** 2) * math.exp(-((se - 0.14) / 0.10) ** 2)
                + 0.010 * math.exp(-(lat / 0.25) ** 2) * math.exp(-((se + 0.78) / 0.14) ** 2)      # chin
                + 0.006 * math.exp(-((abs(lat) - 0.55) / 0.2) ** 2) * math.exp(-((se + 0.05) / 0.2) ** 2))
        z -= bump * front
        return c + scale * np.array([x, y, z])

    m.surface(fn, res(22), res(18), "bandage", closed_u=True, outward=lambda p, s, t: p - c)


def hood(m, hc, scale, res, seed):
    """Cloth hood sitting ~4 cm off the head, its opening framing the face."""
    hc = np.asarray(hc, float)

    def fn(s, t):
        e = -0.46 * math.pi + t * 0.96 * math.pi
        ec, er = -0.05 * math.pi, 0.34 * math.pi
        w = 1.02 * math.sqrt(max(0.0, 1 - ((e - ec) / er) ** 2)) if e > ec else 1.02
        w += 0.01
        a = w + s * (2 * math.pi - 2 * w)  # a = 0 is the front (-Z)
        ce, se = math.cos(e), math.sin(e)
        back = 0.5 - 0.5 * math.cos(a)
        front = 1 - back
        peak = max(0.0, se) ** 4 * back
        flare = 1 + 0.55 * smoothstep(-0.28 * math.pi, -0.46 * math.pi, e)
        wob = 1 + 0.035 * math.sin(6 * a + 2.5 * t + seed)
        x = 0.112 * ce * math.sin(a) * flare * wob
        y = 0.152 * se + 0.05 * peak
        z = -0.135 * ce * math.cos(a) * flare * wob + 0.018 - 0.03 * front * max(0.0, se) + 0.12 * peak
        return hc + scale * np.array([x, y, z])

    m.surface(fn, res(30), res(18), "cloth", inner_region="lining", outward=lambda p, s, t: p - hc)


def cowl(m, neck, scale, res, seed):
    """Capelet draped from the neck over the shoulders, hanging lower at the front."""
    nx, ny, nz = neck
    keys = [(-0.43, (0.285, 0.205, -0.005)), (-0.28, (0.275, 0.188, -0.005)), (-0.15, (0.262, 0.168, 0.0)),
            (-0.08, (0.228, 0.148, 0.004)), (-0.03, (0.160, 0.118, 0.008)), (0.015, (0.100, 0.092, 0.010)),
            (0.035, (0.086, 0.084, 0.010))]
    keys = [(ny + k * scale, (W * scale, D * scale, nz + zc * scale)) for k, (W, D, zc) in keys]

    def hem(s):
        front = 0.5 - 0.5 * math.cos(2 * math.pi * s)
        return ny + scale * (-0.40 - 0.11 * front + 0.03 * hash_noise(s, seed + 3))

    cloth_sweep(m, keys, ny + 0.035 * scale, hem, lambda y: scale * (0.002 + 0.018 * smoothstep(ny, ny - 0.4 * scale, y)),
                seed + 1, res(56), res(14), ks=(8, 13, 21),
                skip=lambda s, t: t > 0.88 and hash_noise((s * 5) % 1.0, seed + 5) > 0.55)


def sleeve(m, shoulder, elbow, wrist, scale, res, seed):
    """Bell sleeve over a real-length arm, with a bandaged hand."""
    shoulder, elbow, wrist = (np.asarray(v, float) for v in (shoulder, elbow, wrist))
    fore = normalize(wrist - elbow)
    pts = smooth_path([shoulder, (shoulder + elbow) / 2, elbow, (elbow + wrist) / 2, wrist + fore * 0.03 * scale],
                      res(10))
    n = len(pts)
    radii = [scale * (0.066 + 0.006 * math.sin(math.pi * min(i / (n - 1) * 1.6, 1)) + 0.034 * (i / (n - 1)) ** 3)
             for i in range(n)]
    m.tube(pts, radii, "cloth", segs=res(14), cap=False,
           ring_mod=lambda i, a: 1 + 0.07 * math.sin(5 * a + i * 0.6 + seed) + 0.04 * math.sin(9 * a - i * 0.4))
    # hand: palm and fingers curled into a fist, thumb along the side
    hand_c = wrist + fore * 0.055 * scale
    m.ellipsoid(hand_c, (0.044 * scale, 0.058 * scale, 0.030 * scale), "bandage", segs=res(10), rings=res(7),
                rot=align_y_to(fore))
    side = normalize(np.cross(fore, [0.0, 1.0, 0.0]))
    m.ellipsoid(hand_c + side * 0.03 * scale - fore * 0.01 * scale, (0.014 * scale, 0.032 * scale, 0.014 * scale),
                "bandage", segs=res(6), rings=res(4), rot=align_y_to(fore))


def robed_cultist(scale=1.0, detail=1.0, seed=0, arms="spear", arms_inside=False):
    """A standing cultist, 1.80 m tall at scale 1. Returns the mesh and the spear hand position."""
    m = MeshBuilder()

    def res(n):
        return max(5, int(n * detail))

    K = scale
    wide = 0.05 if arms_inside else 0.0
    keys = [(0.00, (0.305, 0.250, 0.000)), (0.25, (0.262, 0.200, 0.000)), (0.55, (0.228, 0.168, 0.000)),
            (0.90, (0.200, 0.142, 0.004)), (1.08, (0.170 + wide * 0.6, 0.122, 0.000)),
            (1.28, (0.186 + wide, 0.132, -0.010)), (1.40, (0.205 + wide * 0.6, 0.126, -0.004)),
            (1.47, (0.150, 0.100, 0.006)), (1.53, (0.080, 0.070, 0.010))]
    keys = [(y * K, (W * K, D * K, zc * K)) for y, (W, D, zc) in keys]

    def fold_amp(y):
        y = y / K
        belt = 1 - 0.85 * math.exp(-((y - 1.08) / 0.04) ** 2)
        return K * (0.003 + 0.042 * smoothstep(1.25, 0.0, y)) * belt

    def tatters(s, t):
        if t < 0.88:
            return False
        holes = hash_noise(s * 3 % 1.0, seed + 7) * 0.6 + hash_noise((s * 7 + t * 0.5) % 1.0, seed + 9) * 0.4
        return holes > 0.66 - (t - 0.88) * 2.0

    cloth_sweep(m, keys, 1.53 * K, lambda s: K * (0.012 + 0.03 * (0.5 + 0.5 * hash_noise(s, seed + 1))),
                fold_amp, seed, res(64), res(40), skip=tatters)

    # rope belt with hanging, knotted ends
    W, D, zc = catmull(keys, 1.08 * K)
    belt = []
    for k in range(res(40) + 1):
        th = 2 * math.pi * k / res(40)
        x, z = superellipse(th, W + 0.012 * K, D + 0.012 * K)
        belt.append((x, 1.08 * K, z + zc))
    m.tube(belt, [0.011 * K] * len(belt), "leather", segs=6, cap=False)
    for dx, L in ((-0.05, 0.30), (-0.02, 0.24)):
        x0 = dx * K
        z0 = -(D + 0.015 * K)
        m.tube([(x0, 1.07 * K, z0), (x0 - 0.01 * K, (1.07 - L / 2) * K, z0 - 0.01 * K), (x0, (1.07 - L) * K, z0)],
               [0.009 * K] * 3, "leather", segs=6)
        m.ellipsoid((x0, (1.07 - L) * K, z0), (0.015 * K,) * 3, "leather", segs=6, rings=4)

    # boots peeking out from under the hem
    for sx in (-1, 1):
        m.ellipsoid((sx * 0.085 * K, 0.04 * K, -0.20 * K), (0.048 * K, 0.04 * K, 0.08 * K), "leather",
                    segs=res(10), rings=res(6))

    neck = np.array([0.0, 1.53 * K, 0.010 * K])
    head_c = np.array([0.0, 1.665 * K, 0.0])
    m.tube([neck, head_c - np.array([0, 0.09 * K, 0])], [0.052 * K, 0.050 * K], "bandage", segs=res(10), cap=False)
    bandaged_head(m, head_c, K, res)
    hood(m, head_c, K, res, seed)
    cowl(m, neck, K, res, seed)

    hand = None
    if arms == "spear":
        sleeve(m, (0.19 * K, 1.43 * K, 0.0), (0.27 * K, 1.17 * K, 0.04 * K), (0.28 * K, 1.06 * K, -0.17 * K), K, res,
               seed)
        sleeve(m, (-0.19 * K, 1.43 * K, 0.0), (-0.24 * K, 1.16 * K, 0.03 * K), (-0.21 * K, 0.93 * K, -0.07 * K), K,
               res, seed + 2)
        hand = np.array([0.28 * K, 1.06 * K, -0.215 * K])
    return m, hand


def spear_with_banner(m, x, z, top=2.30, seed=11):
    m.tube([(x, 0.02, z), (x, top, z)], [0.016, 0.014], "wood", segs=8)
    m.lathe([(0.0, 0.0), (0.021, 0.0), (0.021, 0.07), (0.0, 0.08)], "metal", segs=8, center=(x, top - 0.03, z))
    m.lathe([(0.0, 0.0), (0.016, 0.02), (0.040, 0.10), (0.028, 0.20), (0.0, 0.30)], "metal", segs=8,
            center=(x, top + 0.04, z), scale=(1, 1, 0.28))
    bw, bh = 0.42, 0.62
    y0 = top - 0.14
    m.tube([(x - 0.02, y0, z), (x + bw + 0.03, y0, z)], [0.011, 0.011], "wood", segs=6)
    for cx in (x + bw * 0.25, x + bw * 0.75):  # cords
        m.tube([(cx, y0, z), (cx, y0 - 0.03, z)], [0.004, 0.004], "leather", segs=4)

    def banner(s, t):
        return np.array([x + 0.02 + s * bw,
                         y0 - 0.03 - t * bh - 0.025 * math.sin(s * math.pi),
                         z + 0.030 * math.sin(s * 5.0 + t * 2.5) + 0.02 * t * math.sin(s * 11)])

    def rag(s, t):
        cut = 0.80 + 0.18 * hash_noise(s, seed)
        hole = t > 0.35 and hash_noise((s * 2 + t) % 1.0, seed + 2) * hash_noise((t * 3) % 1.0, seed + 4) > 0.45
        return t > cut or hole

    m.surface(banner, 14, 18, "banner", inner_region="banner", skip=rag,
              outward=lambda p, s, t: np.array([0.0, 0.0, -1.0]))


def zealot():
    m, hand = robed_cultist(detail=0.7, seed=0)
    spear_with_banner(m, hand[0], hand[2])
    return m


# ----- tentacles ---------------------------------------------------------------

def tentacle_path(L, lift, curl, twist, start_r, theta, steps=56):
    """Integrate a tentacle that slides out along the ground, rises and hooks over."""
    pts, inner = [], []
    p = np.array([math.sin(theta) * start_r, 0.14, math.cos(theta) * start_r])
    d0 = radial(theta)
    up = np.array([0.0, 1.0, 0.0])
    for i in range(steps):
        s = i / (steps - 1)
        phi = (lift * smoothstep(0.12, 0.55, s) + curl * smoothstep(0.55, 1.0, s)) * math.pi / 2
        side = np.cross(up, d0)
        d = normalize(d0 * math.cos(twist * s) + side * math.sin(twist * s))
        tangent = d * math.cos(phi) + up * math.sin(phi)
        pts.append(p.copy())
        inner.append(-d * math.sin(phi) + up * math.cos(phi))
        p = p + tangent * (L / (steps - 1))
        p[1] = max(p[1], 0.06)
    return pts, inner


def add_tentacle(m, L, r0, lift, curl, twist, start_r, theta):
    pts, inner = tentacle_path(L, lift, curl, twist, start_r, theta)
    n = len(pts)
    # octopus-arm taper: thick, muscular base narrowing to a fine tip
    radii = [r0 * (1 - i / (n - 1)) ** 1.25 + 0.008 for i in range(n)]
    radii = [r * (1 + 0.04 * math.sin(i * 0.8 + theta * 3)) for i, r in enumerate(radii)]
    frames = m.tube(pts, radii, "tentacle", segs=16, inner=inner)
    # two alternating rows of suckers, sized to the arm, spaced along its length
    seglen = [np.linalg.norm(pts[i + 1] - pts[i]) for i in range(n - 1)]
    pos, i, row = 0.0, 2, 0
    while i < n - 3:
        T, I, S = frames[i]
        rs = radii[i] * 0.40
        a = math.pi + (0.42 if row % 2 else -0.42)
        d = -math.cos(a) * I + math.sin(a) * S
        m.sucker(pts[i] + d * radii[i] * 0.93, d, rs, segs=8 if rs > 0.03 else 6)
        row += 1
        step = rs * 1.15
        acc = 0.0
        while i < n - 3 and acc < step:
            acc += seglen[i]
            i += 1


def king_in_yellow():
    K = 2.5
    m, _ = robed_cultist(scale=K, detail=1.0, seed=3, arms="none", arms_inside=True)
    rng = np.random.default_rng(21)
    for k in range(8):
        theta = 2 * math.pi * (k + 0.5) / 8 + rng.uniform(-0.25, 0.25)
        L = rng.uniform(3.6, 5.0)
        lift = rng.uniform(0.9, 1.1)
        curl = rng.choice([-1, 1]) * rng.uniform(0.5, 1.3)
        twist = rng.uniform(-0.5, 0.5)
        add_tentacle(m, L, 0.27, lift, curl, twist, 0.50, theta)
    return m


# ----- the Byakhee and its rider -------------------------------------------------

# torso cross-sections along the spine: z -> (half width, height above spine,
# depth below spine, spine height)
BYAKHEE_TORSO = [(-0.60, (0.14, 0.11, 0.15, 1.40)), (-0.42, (0.28, 0.15, 0.32, 1.33)),
                 (-0.18, (0.30, 0.13, 0.35, 1.27)), (0.08, (0.24, 0.12, 0.23, 1.21)),
                 (0.32, (0.22, 0.13, 0.17, 1.17)), (0.55, (0.10, 0.09, 0.09, 1.13))]


def byakhee_top(z):
    W, top, bot, ys = catmull(BYAKHEE_TORSO, z)
    return ys + top


def byakhee_rider():
    m = MeshBuilder()

    def torso(s, t):
        th = 2 * math.pi * s  # 0 = top of the back, pi = keel
        z = -0.60 + t * 1.15
        W, top, bot, ys = catmull(BYAKHEE_TORSO, z)
        c = math.cos(th)
        x = W * math.sin(th) * (1 - 0.38 * max(0.0, -c) ** 1.5)  # narrows into a keel
        y = ys + (top if c > 0 else bot) * c
        ribs = (0.016 * max(0.0, math.sin((z + 0.45) * math.pi / 0.065)) * smoothstep(-0.48, -0.40, z)
                * (1 - smoothstep(0.0, 0.08, z)) * abs(math.sin(th)) ** 2)
        x += math.copysign(ribs, x)
        if 0.02 < z < 0.30:  # emaciated, sunken belly
            y += 0.05 * max(0.0, -c) * math.sin((z - 0.02) / 0.28 * math.pi)
        return np.array([x, y, z])

    m.surface(torso, 30, 34, "leather", closed_u=True,
              outward=lambda p, s, t: np.array([p[0], p[1] - catmull(BYAKHEE_TORSO, p[2])[3], 0.0]))
    for k in range(10):  # bony spine
        z = 0.48 - k * 0.105
        y = byakhee_top(z)
        m.cone((0.0, y - 0.01, z), (0.0, y + 0.07 - abs(k - 5) * 0.006, z + 0.05), 0.022, "bone", segs=6)

    # long S-curved neck and a skull with a hooked beak, toothed jaw and burning eyes
    neck = smooth_path([(0, 1.40, -0.56), (0, 1.62, -0.80), (0, 1.88, -0.94), (0, 2.03, -1.10), (0, 2.08, -1.20)], 14)
    m.tube(neck, [0.13 - 0.045 * i / 13 for i in range(14)], "leather", segs=12, cap=False,
           ring_mod=lambda i, a: 1 + 0.08 * max(0.0, math.cos(a)) * abs(math.sin(i * 1.6)))
    m.ellipsoid((0, 2.11, -1.25), (0.085, 0.092, 0.13), "bone", segs=14, rings=10)
    beak = smooth_path([(0, 2.10, -1.34), (0, 2.07, -1.50), (0, 2.01, -1.64), (0, 1.94, -1.71)], 10)
    m.tube(beak, [0.052 - 0.046 * (i / 9) ** 1.2 for i in range(10)], "bone", segs=10,
           ring_mod=lambda i, a: 1 - 0.25 * abs(math.sin(a)))
    jaw = smooth_path([(0, 2.03, -1.30), (0, 1.98, -1.44), (0, 1.95, -1.56)], 8)
    m.tube(jaw, [0.040 - 0.034 * i / 7 for i in range(8)], "bone", segs=8,
           ring_mod=lambda i, a: 1 - 0.3 * abs(math.sin(a)))
    for k in range(6):
        b = polyline_point(beak, 0.15 + k * 0.12)
        j = polyline_point(jaw, 0.10 + k * 0.13)
        for sx in (-1, 1):
            m.cone(b + np.array([sx * 0.02, -0.02, 0]), b + np.array([sx * 0.018, -0.055, -0.005]), 0.007, "bone", segs=4)
            m.cone(j + np.array([sx * 0.016, 0.015, 0]), j + np.array([sx * 0.015, 0.045, -0.005]), 0.006, "bone", segs=4)
    for sx in (-1, 1):
        m.ellipsoid((sx * 0.058, 2.135, -1.30), (0.03, 0.026, 0.03), "lining", segs=8, rings=6)
        m.ellipsoid((sx * 0.062, 2.135, -1.31), (0.018, 0.016, 0.018), "glow", segs=8, rings=6)
        for k, (dy, dz) in enumerate(((0.07, 0.10), (0.05, 0.16), (0.02, 0.19))):
            base = np.array([sx * 0.04, 2.15 + dy * 0.3, -1.20 + dz * 0.2])
            m.cone(base, base + np.array([sx * 0.05, dy, dz]), 0.018 - k * 0.003, "bone", segs=5)

    # bird-like digitigrade legs with talons, under the centre of mass
    for sx in (-1, 1):
        hip = (sx * 0.17, 1.12, 0.26)
        knee = (sx * 0.25, 0.80, 0.00)
        ankle = (sx * 0.22, 0.38, 0.20)
        foot = np.array([sx * 0.20, 0.07, 0.04])
        thigh = smooth_path([hip, knee], 6)
        m.tube(thigh, [0.115, 0.11, 0.10, 0.09, 0.08, 0.07], "leather", segs=12)
        m.tube(smooth_path([knee, ankle], 6), [0.065, 0.058, 0.05, 0.045, 0.042, 0.04], "leather", segs=10)
        m.tube(smooth_path([ankle, foot], 5), [0.038, 0.034, 0.032, 0.03, 0.03], "leather", segs=8)
        for k, ang in enumerate((-0.45, 0.0, 0.45)):
            d = np.array([math.sin(ang) * sx, 0.0, -math.cos(ang)])
            toe = foot + d * 0.16 + np.array([0, -0.05, 0])
            m.tube([foot, foot + d * 0.08 + np.array([0, -0.03, 0]), toe], [0.022, 0.018, 0.014], "leather", segs=6)
            m.cone(toe, toe + d * 0.07 + np.array([0, -0.025, 0]), 0.013, "bone", segs=5)
        back_toe = foot + np.array([0, -0.04, 0.10])
        m.tube([foot, back_toe], [0.018, 0.013], "leather", segs=6)
        m.cone(back_toe, back_toe + np.array([0, -0.02, 0.06]), 0.011, "bone", segs=5)

    # tail
    tail = smooth_path([(0, 1.13, 0.55), (0, 1.03, 0.90), (0, 0.90, 1.25), (0.06, 0.80, 1.55), (0.12, 0.76, 1.82)], 16)
    m.tube(tail, [0.085 * (1 - i / 15) ** 1.1 + 0.006 for i in range(16)], "leather", segs=8)

    # bat wings: the forelimb is the wing, with finger bones carrying a torn membrane
    for sx in (-1, 1):
        S = np.array([sx * 0.20, 1.44, -0.40])
        E = np.array([sx * 0.72, 1.96, -0.30])
        W = np.array([sx * 1.28, 2.36, -0.10])
        F = [np.array([sx * 2.32, 2.52, 0.25]), np.array([sx * 2.20, 1.88, 0.66]),
             np.array([sx * 1.74, 1.33, 0.86]), np.array([sx * 1.14, 1.06, 0.80])]
        B = np.array([sx * 0.22, 1.17, 0.32])
        m.tube(smooth_path([S, E], 5), [0.06, 0.055, 0.05, 0.045, 0.04], "leather", segs=10)
        m.tube(smooth_path([E, W], 5), [0.04, 0.034, 0.03, 0.028, 0.026], "leather", segs=8)
        m.ellipsoid(E, (0.045,) * 3, "leather", segs=8, rings=6)
        m.ellipsoid(W, (0.035,) * 3, "leather", segs=8, rings=6)
        m.cone(W, W + np.array([sx * 0.03, 0.12, -0.10]), 0.018, "bone", segs=5)  # thumb claw
        for tip in F:
            mid = W + (tip - W) * 0.45 + np.array([0, 0.03, 0])
            m.tube(smooth_path([W, mid, tip], 6), [0.02, 0.017, 0.014, 0.011, 0.008, 0.004], "bone", segs=6)
            m.ellipsoid(mid, (0.018,) * 3, "bone", segs=6, rings=4)

        def torn(s, t, sx=sx, k=0):
            # ragged trailing edge
            depth = 0.10 + 0.10 * (0.5 + 0.5 * hash_noise(s, 30 + sx + k))
            if t > 1 - depth:
                return True
            # one long rip running in from the edge
            centre = 0.3 + 0.4 * (0.5 + 0.5 * hash_noise(0.37, 50 + sx + k))
            width = 0.035 * (0.5 + 0.5 * hash_noise((t * 2) % 1.0, 60 + sx + k))
            return t > 0.45 + 0.2 * (0.5 + 0.5 * hash_noise(0.11, 70 + sx + k)) and abs(s - centre) < width

        def panel(fa, fb, k):
            def fn(s, t):
                edge = fa + (fb - fa) * s
                p = W + (edge - W) * t
                p += normalize(W - edge) * 0.20 * np.linalg.norm(fb - fa) * math.sin(math.pi * s) * t ** 2
                return p + np.array([0, -0.05, 0.03]) * math.sin(math.pi * s) * math.sin(math.pi * t)
            m.surface(fn, 14, 18, "membrane", inner_region="membrane",
                      skip=lambda s, t: torn(s, t, k=k), outward=lambda p, s, t: np.array([0.0, 1.0, 0.0]))

        for k in range(3):
            panel(F[k], F[k + 1], k + 1)

        def inner_panel(s, t):
            arm = polyline_point([S, E, W], s)
            trail = B + (F[3] - B) * s
            trail = trail + normalize(arm - trail) * 0.25 * math.sin(math.pi * s)
            return arm + (trail - arm) * t + np.array([0, -0.06, 0.02]) * math.sin(math.pi * s) * math.sin(math.pi * t)

        m.surface(inner_panel, 20, 14, "membrane", inner_region="membrane", skip=lambda s, t: torn(s, t, k=7),
                  outward=lambda p, s, t: np.array([0.0, 1.0, 0.0]))

    # saddle cloth bearing the Yellow Sign, draped over the back
    def saddle(s, t):
        x = (s - 0.5) * 0.95
        z = -0.32 + t * 0.62
        W = catmull(BYAKHEE_TORSO, z)[0]
        y = byakhee_top(z) + 0.012 - max(0.0, abs(x) - 0.55 * W) * 1.7 - 0.6 * max(0.0, abs(x) - 0.9 * W)
        x *= 1 - 0.1 * max(0.0, abs(x) - W)
        return np.array([x, y, z])

    m.surface(saddle, 16, 10, "banner", inner_region="lining",
              skip=lambda s, t: (s < 0.06 or s > 0.94) and hash_noise((t * 2) % 1.0, 55) > 0.3,
              outward=lambda p, s, t: np.array([p[0] * 0.5, 1.0, 0.0]))
    rider(m)
    return m


def rider(m):
    """A cultist sitting astride the Byakhee: thighs over its flanks, boots in the
    air, a couched lance in the right hand and the reins in the left."""
    def res(n):
        return max(5, int(n * 0.6))

    seat_y = byakhee_top(0.02) + 0.10
    pelvis = np.array([0.0, seat_y, 0.02])
    neck = np.array([0.0, seat_y + 0.52, -0.04])
    head_c = np.array([0.0, seat_y + 0.665, -0.05])

    # upper body garment, leaning slightly forward
    keys = [(seat_y + 0.02, (0.175, 0.125, 0.02)), (seat_y + 0.15, (0.165, 0.118, 0.01)),
            (seat_y + 0.33, (0.182, 0.128, -0.012)), (seat_y + 0.44, (0.205, 0.124, -0.028)),
            (seat_y + 0.49, (0.150, 0.100, -0.034)), (seat_y + 0.535, (0.080, 0.070, -0.040))]
    cloth_sweep(m, keys, seat_y + 0.535, seat_y + 0.05, lambda y: 0.004 + 0.01 * smoothstep(seat_y + 0.4, seat_y, y),
                21, res(48), res(16))

    # robe skirts spreading over the saddle and hanging down the creature's flanks
    def skirt(s, t):
        th = 2 * math.pi * s
        d = radial(th)
        front = 0.5 - 0.5 * math.cos(th)
        side = abs(math.sin(th))
        r = 0.17 + (0.16 + 0.10 * side) * t ** 0.7
        y = seat_y + 0.06 - (0.16 + 0.42 * side ** 1.2) * t ** 1.15
        z = 0.02 + d[2] * r * 0.80 - 0.06 * front * t
        x = d[0] * r * (1 + 0.25 * side)
        a = (0.004 + 0.03 * t) * drape(th, t, 23, (7, 12, 19))
        return np.array([x + d[0] * a, y, z + d[2] * a])

    m.surface(skirt, res(48), res(12), "cloth", closed_u=True, inner_region="lining",
              skip=lambda s, t: t > 0.85 and hash_noise((s * 4) % 1.0, 24) > 0.5,
              outward=lambda p, s, t: np.array([p[0], 0.3, p[2] - 0.02]))

    # legs: trousered thighs over the flanks, booted shins hanging free
    for sx in (-1, 1):
        hip = np.array([sx * 0.10, seat_y, 0.02])
        knee = np.array([sx * 0.31, seat_y - 0.17, -0.30])
        ankle = np.array([sx * 0.34, seat_y - 0.55, -0.24])
        toe = np.array([sx * 0.34, seat_y - 0.58, -0.38])
        m.tube(smooth_path([hip, knee], 6), [0.085, 0.08, 0.075, 0.068, 0.062, 0.058], "cloth", segs=10,
               ring_mod=lambda i, a: 1 + 0.06 * math.sin(4 * a + i))
        m.tube(smooth_path([knee, ankle], 6), [0.058, 0.055, 0.052, 0.05, 0.048, 0.046], "leather", segs=10)
        m.ellipsoid(knee, (0.062,) * 3, "leather", segs=8, rings=6)
        m.ellipsoid((ankle + toe) / 2 + np.array([0, 0.0, 0.01]), (0.05, 0.045, 0.11), "leather", segs=10, rings=6,
                    rot=align_y_to(np.array([0, 0.25, 1.0])))

    m.tube([neck, head_c - np.array([0, 0.09, 0])], [0.052, 0.050], "bandage", segs=8, cap=False)
    bandaged_head(m, head_c, 1.0, res)
    hood(m, head_c, 1.0, res, 25)
    cowl(m, neck, 1.0, res, 26)

    # right arm couches the lance, left arm holds the reins
    sh_r = np.array([0.19, seat_y + 0.44, -0.03])
    sh_l = np.array([-0.19, seat_y + 0.44, -0.03])
    hand_r = np.array([0.24, seat_y + 0.12, -0.20])
    hand_l = np.array([-0.17, seat_y + 0.16, -0.28])
    sleeve(m, sh_r, sh_r + np.array([0.06, -0.25, 0.07]), hand_r, 1.0, res, 27)
    sleeve(m, sh_l, sh_l + np.array([-0.06, -0.23, 0.0]), hand_l, 1.0, res, 28)
    butt = np.array([0.26, seat_y - 0.10, 0.42])
    d = normalize(hand_r + np.array([0.0, 0.0, -0.05]) - butt)
    tip = butt + d * 2.9
    m.tube([butt, tip], [0.016, 0.013], "wood", segs=6)
    m.lathe([(0.0, 0.0), (0.028, 0.03), (0.02, 0.18), (0.0, 0.28)], "metal", segs=8, center=tip, rot=align_y_to(d),
            scale=(1, 1, 0.35))

    def pennant(s, t):
        base = butt + d * (2.25 + 0.5 * s)
        return base + np.array([0.0, -0.22 * t * (1 - 0.6 * s), 0.10 * t]) + \
            np.array([0.03, 0, 0]) * math.sin(s * 6 + t * 3)

    m.surface(pennant, 8, 6, "banner", inner_region="banner",
              skip=lambda s, t: t > 0.7 + 0.25 * hash_noise(s, 77),
              outward=lambda p, s, t: np.array([1.0, 0.0, 0.0]))
    # reins to the creature's jaw
    for sx in (-1, 1):
        m.tube([hand_l + np.array([0, 0, -0.04]), np.array([sx * 0.07, 1.78, -0.92]), np.array([sx * 0.05, 2.02, -1.32])],
               [0.006, 0.006, 0.006], "leather", segs=4)


MODELS = {
    "eldritch_yellow_zealot": zealot,
    "eldritch_byakhee_rider": byakhee_rider,
    "eldritch_king_in_yellow": king_in_yellow,
}

# battalion sprite -> mesh
ENTITIES = {
    "eldritch_yellow_zealots": "eldritch_yellow_zealot",
    "eldritch_byakhee_riders": "eldritch_byakhee_rider",
    "eldritch_hastur_incarnate": "eldritch_king_in_yellow",
}


# ---------------------------------------------------------------------------
# .mesh writer / reader (Clausewitz binary asset format)
# ---------------------------------------------------------------------------

def _obj(name, depth):
    return b"[" * depth + name.encode("latin-1") + b"\x00"


def _prop(name, values):
    out = b"!" + struct.pack("<b", len(name)) + name.encode("latin-1")
    if isinstance(values, str):
        s = values.encode("latin-1")
        return out + b"s" + struct.pack("<i", 1) + struct.pack("<i", len(s) + 1) + s + b"\x00"
    if all(isinstance(v, (int, np.integer)) for v in values):
        vals = [int(v) for v in values]
        return out + b"i" + struct.pack("<i", len(vals)) + struct.pack(f"<{len(vals)}i", *vals)
    vals = [float(v) for v in values]
    return out + b"f" + struct.pack("<i", len(vals)) + struct.pack(f"<{len(vals)}f", *vals)


def tangents(p, n, uv, tris):
    """Per-vertex tangents (x, y, z, w) from UV gradients."""
    tan = np.zeros_like(p)
    bit = np.zeros_like(p)
    t = np.asarray(tris)
    p0, p1, p2 = p[t[:, 0]], p[t[:, 1]], p[t[:, 2]]
    w0, w1, w2 = uv[t[:, 0]], uv[t[:, 1]], uv[t[:, 2]]
    e1, e2 = p1 - p0, p2 - p0
    d1, d2 = w1 - w0, w2 - w0
    det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    det = np.where(np.abs(det) < 1e-12, 1e-12, det)
    T = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) / det[:, None]
    B = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) / det[:, None]
    for k in range(3):
        np.add.at(tan, t[:, k], T)
        np.add.at(bit, t[:, k], B)
    out = []
    for i in range(len(p)):
        tv = tan[i] - n[i] * np.dot(n[i], tan[i])
        if np.linalg.norm(tv) < 1e-9:
            ref = np.array([0.0, 1.0, 0.0]) if abs(n[i][1]) < 0.9 else np.array([1.0, 0.0, 0.0])
            tv = np.cross(ref, n[i])
        tv = normalize(tv)
        w = 1.0 if np.dot(np.cross(n[i], tv), bit[i]) >= 0 else -1.0
        out.append((tv[0], tv[1], tv[2], w))
    return np.array(out)


def mesh_arrays(m):
    p = np.array(m.p)
    n = np.array(m.n)
    uv = np.array(m.uv)
    ta = tangents(p, n, uv, m.tris)
    lo, hi = p.min(axis=0), p.max(axis=0)
    centre = (lo + hi) / 2
    radius = float(np.max(np.linalg.norm(p - centre, axis=1)))
    return {
        "p": p.flatten().tolist(),
        "n": n.flatten().tolist(),
        "ta": ta.flatten().tolist(),
        "u0": uv.flatten().tolist(),
        "tri": [i for t in m.tris for i in t],
        "boundingsphere": [*centre.tolist(), radius],
        "min": lo.tolist(),
        "max": hi.tolist(),
    }


def write_mesh(path, shape_name, a):
    data = b"@@b@" + _prop("pdxasset", [1, 0]) + _obj("object", 1) + _obj(shape_name, 2) + _obj("mesh", 3)
    for key in ("p", "n", "ta", "u0", "tri", "boundingsphere"):
        data += _prop(key, a[key])
    data += _obj("aabb", 4) + _prop("min", a["min"]) + _prop("max", a["max"])
    data += _obj("material", 4)
    data += _prop("shader", "PdxMeshStandard")
    data += _prop("diff", f"{TEXTURE}_diffuse.dds")
    data += _prop("n", f"{TEXTURE}_normal.dds")
    data += _prop("spec", f"{TEXTURE}_spec.dds")
    data += _obj("locator", 1)
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as f:
        f.write(data)


def read_mesh(path):
    """Minimal reader for the same format, used to verify what was written."""
    data = open(path, "rb").read()
    assert data[:4] == b"@@b@", "bad header"
    pos, tree = 4, {"props": {}, "children": []}
    stack = [tree]
    while pos < len(data):
        ch = data[pos:pos + 1]
        if ch == b"[":
            depth = 0
            while data[pos:pos + 1] == b"[":
                depth += 1
                pos += 1
            end = data.index(b"\x00", pos)
            node = {"name": data[pos:end].decode("latin-1"), "props": {}, "children": []}
            pos = end + 1
            stack = stack[:depth]
            stack[-1]["children"].append(node)
            stack.append(node)
        elif ch == b"!":
            ln = data[pos + 1]
            name = data[pos + 2:pos + 2 + ln].decode("latin-1")
            pos += 2 + ln
            kind = data[pos:pos + 1]
            count = struct.unpack_from("<i", data, pos + 1)[0]
            pos += 5
            if kind == b"i":
                val = list(struct.unpack_from(f"<{count}i", data, pos))
                pos += 4 * count
            elif kind == b"f":
                val = list(struct.unpack_from(f"<{count}f", data, pos))
                pos += 4 * count
            elif kind == b"s":
                slen = struct.unpack_from("<i", data, pos)[0]
                pos += 4
                val = data[pos:pos + slen - 1].decode("latin-1")
                assert data[pos + slen - 1] == 0, "string not null terminated"
                pos += slen
            else:
                raise ValueError(f"unknown data type {kind!r} at {pos}")
            stack[-1]["props"][name] = val
        else:
            raise ValueError(f"unexpected byte {ch!r} at {pos}")
    return tree


def verify_mesh(path):
    tree = read_mesh(path)
    assert tree["props"]["pdxasset"] == [1, 0]
    assert [c["name"] for c in tree["children"]] == ["object", "locator"]
    mesh = tree["children"][0]["children"][0]["children"][0]
    pr = mesh["props"]
    nv = len(pr["p"]) // 3
    assert len(pr["n"]) == nv * 3 and len(pr["ta"]) == nv * 4 and len(pr["u0"]) == nv * 2
    assert len(pr["tri"]) % 3 == 0 and max(pr["tri"]) < nv and min(pr["tri"]) >= 0
    assert nv < 65536, "too many vertices for 16-bit indices"
    uv = np.array(pr["u0"])
    assert uv.min() >= 0 and uv.max() <= 1
    kids = {c["name"]: c["props"] for c in mesh["children"]}
    assert set(kids) == {"aabb", "material"}
    assert kids["material"]["shader"] == "PdxMeshStandard"
    for slot in ("diff", "n", "spec"):
        assert os.path.exists(os.path.join(os.path.dirname(path), kids["material"][slot])), slot
    p = np.array(pr["p"]).reshape(-1, 3)
    n = np.array(pr["n"]).reshape(-1, 3)
    t = np.array(pr["tri"]).reshape(-1, 3)
    geo = np.cross(p[t[:, 1]] - p[t[:, 0]], p[t[:, 2]] - p[t[:, 0]])
    agree = np.einsum("ij,ij->i", geo, n[t].sum(axis=1)) > 0
    assert agree.mean() > 0.99, f"winding disagrees with normals on {1 - agree.mean():.1%} of triangles"
    return nv, len(t), kids["aabb"]["min"], kids["aabb"]["max"]


# ---------------------------------------------------------------------------
# Textures
# ---------------------------------------------------------------------------

def save_dds_mips(img, rel_path):
    """Uncompressed A8R8G8B8 DDS with a full mip chain."""
    img = img.convert("RGBA")
    w, h = img.size
    levels = [img]
    while levels[-1].width > 1 or levels[-1].height > 1:
        cur = levels[-1]
        levels.append(cur.resize((max(1, cur.width // 2), max(1, cur.height // 2)), Image.BOX))
    header = struct.pack("<4sIIIIIII11I", b"DDS ", 124, 0x1 | 0x2 | 0x4 | 0x8 | 0x1000 | 0x20000,
                         h, w, w * 4, 0, len(levels), *([0] * 11))
    pixel_format = struct.pack("<II4sIIIII", 32, 0x41, b"\0\0\0\0", 32,
                               0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    caps = struct.pack("<IIIII", 0x1000 | 0x8 | 0x400000, 0, 0, 0, 0)
    body = b"".join(np.array(lv)[:, :, [2, 1, 0, 3]].tobytes() for lv in levels)
    full = os.path.join(ROOT, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as f:
        f.write(header + pixel_format + caps + body)


def value_noise(h, w, cy, cx, rng):
    """Tileable value noise in [0, 1]."""
    grid = rng.random((cy, cx))
    ys = np.arange(h) * cy / h
    xs = np.arange(w) * cx / w
    y0, x0 = np.floor(ys).astype(int), np.floor(xs).astype(int)
    fy, fx = ys - y0, xs - x0
    fy, fx = fy * fy * (3 - 2 * fy), fx * fx * (3 - 2 * fx)
    y1, x1 = (y0 + 1) % cy, (x0 + 1) % cx
    g00, g01 = grid[np.ix_(y0, x0)], grid[np.ix_(y0, x1)]
    g10, g11 = grid[np.ix_(y1, x0)], grid[np.ix_(y1, x1)]
    top = g00 * (1 - fx) + g01 * fx
    bot = g10 * (1 - fx) + g11 * fx
    return top * (1 - fy[:, None]) + bot * fy[:, None]


def fbm(h, w, base, octaves, seed, aspect=1.0):
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w))
    amp, total = 1.0, 0.0
    for o in range(octaves):
        cx = max(2, int(base * 2 ** o))
        cy = max(2, int(base * aspect * 2 ** o))
        out += amp * value_noise(h, w, cy, cx, rng)
        total += amp
        amp *= 0.5
    return out / total


def lerp(a, b, t):
    return a + (b - a) * t


def tex_cloth(w, h):
    yy, xx = np.mgrid[0:h, 0:w]
    v = yy / h
    base = np.array([196, 146, 38], float)
    low = fbm(h, w, 3, 5, 1)
    weave = 0.5 + 0.25 * np.sin(xx * math.pi / 2) + 0.25 * np.sin(yy * math.pi / 2)
    streak = fbm(h, w, 40, 2, 2, aspect=0.08)
    col = base[None, None] * (0.78 + 0.32 * low[..., None]) * (0.97 + 0.03 * weave[..., None])
    col *= (0.9 + 0.12 * streak[..., None])
    # bleached, sun-faded upper folds
    col = lerp(col, np.array([226, 196, 120.0]), (0.18 * (1 - v) * fbm(h, w, 6, 3, 3))[..., None])
    # grime climbing up from the hem, with a sickly green tinge
    drips = fbm(h, w, 24, 3, 8, aspect=0.12)
    grime = np.clip((v - 0.30) / 0.70, 0, 1) ** 1.2 * (0.45 + 0.55 * fbm(h, w, 8, 4, 4))
    grime = np.clip(grime + 0.35 * np.clip(drips - 0.55, 0, 1) * np.clip(v * 1.5, 0, 1), 0, 1)
    col = lerp(col, np.array([52, 50, 26.0]), (grime * 0.85)[..., None])
    col = lerp(col, np.array([70, 92, 40.0]), (grime * 0.18 * fbm(h, w, 12, 3, 5))[..., None])
    # stains and scorch marks
    stains = np.clip((fbm(h, w, 10, 4, 6) - 0.62) * 6, 0, 1)
    col = lerp(col, np.array([70, 40, 22.0]), (stains * 0.7)[..., None])
    height = 0.15 * weave + 0.5 * fbm(h, w, 24, 3, 7) + 0.3 * streak
    spec = np.stack([np.zeros((h, w)), 14 + 10 * grime, np.zeros((h, w)), 225 - 30 * grime], -1)
    return col, height, spec


def tex_lining(w, h):
    yy, xx = np.mgrid[0:h, 0:w]
    weave = 0.5 + 0.25 * np.sin(xx * math.pi / 2) + 0.25 * np.sin(yy * math.pi / 2)
    col = np.array([34, 27, 19.0])[None, None] * (0.8 + 0.4 * fbm(h, w, 6, 4, 11)[..., None])
    height = 0.4 * weave + 0.4 * fbm(h, w, 20, 3, 12)
    spec = np.stack([np.zeros((h, w)), np.full((h, w), 10.0), np.zeros((h, w)), np.full((h, w), 235.0)], -1)
    return col, height, spec


def tex_bandage(w, h):
    yy, xx = np.mgrid[0:h, 0:w]
    ang = math.radians(28)
    coord = (xx * math.sin(ang) + yy * math.cos(ang)) / 15.0
    frac = coord - np.floor(coord)
    ridge = np.sin(frac * math.pi) ** 0.6
    strip_id = np.floor(coord).astype(int)
    rng = np.random.default_rng(13)
    tone = rng.uniform(0.75, 1.05, strip_id.max() + 2)[strip_id]
    base = np.array([168, 158, 138.0])
    col = base[None, None] * tone[..., None] * (0.55 + 0.45 * ridge[..., None])
    dirt = fbm(h, w, 8, 4, 14)
    col = lerp(col, np.array([80, 72, 55.0]), (np.clip(dirt - 0.45, 0, 1) * 1.4)[..., None])
    old_blood = np.clip((fbm(h, w, 5, 4, 15) - 0.66) * 5, 0, 1)
    col = lerp(col, np.array([84, 40, 30.0]), (old_blood * 0.65)[..., None])
    height = ridge + 0.25 * fbm(h, w, 30, 3, 16)
    spec = np.stack([np.zeros((h, w)), np.full((h, w), 16.0), np.zeros((h, w)), np.full((h, w), 215.0)], -1)
    return col, height, spec


def tex_tentacle(w, h):
    yy, xx = np.mgrid[0:h, 0:w]
    u = xx / w
    underside = np.exp(-((u - 0.5) / 0.18) ** 2)
    top = np.array([62, 62, 52.0])
    under = np.array([138, 124, 108.0])
    col = lerp(top[None, None], under[None, None], underside[..., None])
    mottle = fbm(h, w, 10, 5, 21)
    col *= (0.75 + 0.45 * mottle[..., None])
    spots = np.clip((fbm(h, w, 22, 3, 22) - 0.6) * 4, 0, 1)
    col = lerp(col, np.array([38, 44, 30.0]), (spots * 0.6 * (1 - underside))[..., None])
    wrinkles = fbm(h, w, 6, 3, 24, aspect=8.0)
    # iridescent green slime in the crevices
    col = lerp(col, np.array([90, 140, 60.0]), (0.22 * (1 - wrinkles) * mottle)[..., None])
    height = 0.25 * wrinkles + 0.7 * fbm(h, w, 26, 4, 23)
    spec = np.stack([np.zeros((h, w)), 70 + 50 * mottle, np.zeros((h, w)), 85 - 30 * mottle], -1)
    return col, height, spec


def tex_leather(w, h):
    n1 = fbm(h, w, 6, 5, 31)
    cells = np.abs(fbm(h, w, 18, 3, 32) - 0.5) * 2
    wrinkle = 1 - np.clip(cells * 3, 0, 1)
    col = np.array([58, 46, 50.0])[None, None] * (0.7 + 0.55 * n1[..., None])
    col = lerp(col, np.array([30, 22, 26.0]), (wrinkle * 0.6)[..., None])
    scars = np.clip((fbm(h, w, 9, 3, 33) - 0.68) * 5, 0, 1)
    col = lerp(col, np.array([110, 80, 78.0]), (scars * 0.5)[..., None])
    height = 0.7 * (1 - wrinkle) + 0.4 * n1
    spec = np.stack([np.zeros((h, w)), 40 + 30 * n1, np.zeros((h, w)), 140 - 40 * n1], -1)
    return col, height, spec


def tex_membrane(w, h):
    img = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(img)
    rng = np.random.default_rng(41)
    for k in range(7):
        x = (k + 0.5) * w / 7
        pts = [(x, 0)]
        for s in range(1, 9):
            x += rng.uniform(-14, 14)
            pts.append((x, s * h / 8))
        d.line(pts, fill=255, width=5)
        for _ in range(5):
            sx, sy = pts[rng.integers(1, 8)]
            d.line([(sx, sy), (sx + rng.uniform(-60, 60), sy + rng.uniform(10, 60))], fill=170, width=2)
    veins = np.array(img.filter(ImageFilter.GaussianBlur(1.2)), float) / 255
    mottle = fbm(h, w, 7, 5, 42)
    col = np.array([84, 52, 60.0])[None, None] * (0.65 + 0.5 * mottle[..., None])
    col = lerp(col, np.array([40, 22, 30.0]), (veins * 0.8)[..., None])
    rot = np.clip((fbm(h, w, 12, 3, 43) - 0.6) * 4, 0, 1)
    col = lerp(col, np.array([30, 30, 18.0]), (rot * 0.6)[..., None])
    height = 0.9 * veins + 0.3 * mottle
    spec = np.stack([np.zeros((h, w)), 50 + 30 * mottle, np.zeros((h, w)), 110 - 30 * mottle], -1)
    return col, height, spec


def tex_simple(w, h, color, seed, rough, specv, metal=0.0, grain_aspect=1.0, cracks=False):
    n1 = fbm(h, w, 6, 5, seed, aspect=grain_aspect)
    col = np.array(color, float)[None, None] * (0.72 + 0.5 * n1[..., None])
    height = n1.copy()
    if cracks:
        c = 1 - np.clip(np.abs(fbm(h, w, 14, 3, seed + 1) - 0.5) * 14, 0, 1)
        col = lerp(col, np.array([50, 44, 34.0]), (c * 0.7)[..., None])
        height -= 0.6 * c
    spec = np.stack([np.zeros((h, w)), np.full((h, w), float(specv)), np.full((h, w), metal),
                     np.full((h, w), float(rough))], -1)
    return col, height, spec


def tex_metal(w, h):
    col, height, spec = tex_simple(w, h, (88, 84, 76), 51, 120, 120, metal=190)
    rust = np.clip((fbm(h, w, 8, 4, 52) - 0.5) * 3, 0, 1)
    col = lerp(col, np.array([112, 58, 28.0]), (rust * 0.8)[..., None])
    spec[..., 2] *= 1 - rust
    spec[..., 3] = lerp(spec[..., 3], 230, rust)
    return col, height, spec


def tex_banner(w, h):
    cloth, height, spec = tex_lining(w, h)
    cloth = cloth * 1.15
    s = int(min(w, h) * 0.85)
    sign = Image.new("L", (s * 2, s * 2), 0)
    d = ImageDraw.Draw(sign)
    S = s * 2
    for k in range(3):
        base = math.radians(90 + k * 120)
        pts = []
        for i in range(70):
            t = i / 69
            r = (0.08 + 0.32 * t) * S
            a = base + t * math.radians(150)
            pts.append((S / 2 + r * math.cos(a), S / 2 - r * math.sin(a)))
        for i in range(len(pts) - 1):
            d.line([pts[i], pts[i + 1]], fill=255, width=max(4, int(S * (0.06 - 0.04 * i / 70))))
        ex, ey = pts[-1]
        d.ellipse([ex - S * 0.03, ey - S * 0.03, ex + S * 0.03, ey + S * 0.03], fill=255)
    d.ellipse([S * 0.42, S * 0.42, S * 0.58, S * 0.58], outline=255, width=int(S * 0.03))
    sign = np.array(sign.resize((s, s), Image.LANCZOS), float) / 255
    mask = np.zeros((h, w))
    oy, ox = (h - s) // 2, (w - s) // 2
    mask[oy:oy + s, ox:ox + s] = sign
    wear = np.clip(fbm(h, w, 10, 4, 61) * 1.6 - 0.25, 0, 1)
    mask *= wear
    col = lerp(cloth, np.array([196, 150, 52.0]), mask[..., None])
    grime = fbm(h, w, 6, 4, 62)
    col *= (0.75 + 0.35 * grime[..., None])
    height = height + 0.4 * mask
    return col, height, spec


def make_textures():
    diff = np.zeros((ATLAS, ATLAS, 3))
    height = np.zeros((ATLAS, ATLAS))
    spec = np.zeros((ATLAS, ATLAS, 4))
    glow = np.zeros((ATLAS, ATLAS))
    painters = {
        "cloth": tex_cloth,
        "lining": tex_lining,
        "bandage": tex_bandage,
        "tentacle": tex_tentacle,
        "leather": tex_leather,
        "membrane": tex_membrane,
        "bone": lambda w, h: tex_simple(w, h, (196, 184, 152), 71, 170, 40, cracks=True),
        "metal": tex_metal,
        "wood": lambda w, h: tex_simple(w, h, (92, 64, 40), 81, 200, 20, grain_aspect=0.06),
        "glow": lambda w, h: tex_simple(w, h, (226, 236, 120), 91, 120, 90),
        "sucker": lambda w, h: tex_simple(w, h, (176, 150, 138), 95, 70, 110),
        "banner": tex_banner,
    }
    strength = {"cloth": 2.0, "lining": 1.5, "bandage": 3.0, "tentacle": 2.5, "leather": 4.0, "membrane": 3.0,
                "bone": 2.5, "metal": 1.5, "wood": 3.0, "glow": 0.5, "sucker": 2.0, "banner": 1.5}
    normals = np.zeros((ATLAS, ATLAS, 3))
    for name, (x0, y0, x1, y1) in REGIONS.items():
        col, hgt, spc = painters[name](x1 - x0, y1 - y0)
        diff[y0:y1, x0:x1] = col
        spec[y0:y1, x0:x1] = spc
        # tangent-space normal from the height field (x along +u, y along +v/down)
        gy, gx = np.gradient(hgt * strength[name])
        nrm = np.stack([-gx, -gy, np.ones_like(gx)], -1)
        normals[y0:y1, x0:x1] = nrm / np.linalg.norm(nrm, axis=-1, keepdims=True)
        if name == "glow":
            glow[y0:y1, x0:x1] = 1.0
    diff_img = Image.fromarray(np.dstack([diff.clip(0, 255), np.full((ATLAS, ATLAS), 255)]).astype(np.uint8),
                               "RGBA")
    save_dds_mips(diff_img, f"{MODEL_DIR}/{TEXTURE}_diffuse.dds")
    # Paradox layout: X in green, Y (up, i.e. towards -v) in alpha, emissive mask in blue.
    nx = (normals[..., 0] * 0.5 + 0.5) * 255
    ny_up = (-normals[..., 1] * 0.5 + 0.5) * 255
    nmap = np.dstack([nx, nx, glow * 255, ny_up]).clip(0, 255).astype(np.uint8)
    save_dds_mips(Image.fromarray(nmap, "RGBA"), f"{MODEL_DIR}/{TEXTURE}_normal.dds")
    spec_img = Image.fromarray(spec.clip(0, 255).astype(np.uint8), "RGBA").resize((SPEC_SIZE, SPEC_SIZE),
                                                                                    Image.BOX)
    save_dds_mips(spec_img, f"{MODEL_DIR}/{TEXTURE}_spec.dds")
    return diff_img, nmap


# ---------------------------------------------------------------------------
# Definitions
# ---------------------------------------------------------------------------

def write_definitions():
    gfx = ["#####################################################################",
           "# Eldritch Pacts - King in Yellow 3D models (pdxmesh definitions)",
           "# Generated by tools/generate_models.py. Change MESH_SCALE there (or",
           "# the scale values below) if the models look too large or too small.",
           "#####################################################################",
           "", "objectTypes = {"]
    for mesh in MODELS:
        gfx += ["\tpdxmesh = {", f'\t\tname = "{mesh}_mesh"', f'\t\tfile = "{MODEL_DIR}/{mesh}.mesh"',
                f"\t\tscale = {MESH_SCALE}", "\t}"]
    gfx.append("}")
    with open(os.path.join(ROOT, "gfx/entities/eldritch_hastur_meshes.gfx"), "w") as f:
        f.write("\n".join(gfx) + "\n")

    asset = ["#####################################################################",
             "# Eldritch Pacts - King in Yellow unit entities",
             "# Generated by tools/generate_models.py. A battalion with",
             "# sprite = X is drawn with X_entity. The models are static (no",
             "# animation states).",
             "#####################################################################", ""]
    for sprite, mesh in ENTITIES.items():
        asset += ["entity = {", f'\tname = "{sprite}_entity"', f'\tpdxmesh = "{mesh}_mesh"', "}", ""]
    with open(os.path.join(ROOT, "gfx/entities/eldritch_hastur_units.asset"), "w") as f:
        f.write("\n".join(asset))


# ---------------------------------------------------------------------------
# Preview renderer (software rasteriser with per-pixel texturing, normal
# mapping, key and rim light - only for checking the models by eye)
# ---------------------------------------------------------------------------

def render_preview(a, diffuse, nmap, size=640, yaw=-30, pitch=-12):
    p = np.array(a["p"]).reshape(-1, 3)
    n = np.array(a["n"]).reshape(-1, 3)
    ta = np.array(a["ta"]).reshape(-1, 4)
    uv = np.array(a["u0"]).reshape(-1, 2)
    tris = np.array(a["tri"]).reshape(-1, 3)
    rot = rot_x(math.radians(pitch)) @ rot_y(math.radians(yaw))
    centre = (p.min(axis=0) + p.max(axis=0)) / 2
    q = (p - centre) @ rot.T
    extent = np.abs(q[:, :2]).max() * 1.08
    sx = (q[:, 0] / extent * 0.5 + 0.5) * size
    sy = (0.5 - q[:, 1] / extent * 0.5) * size
    depth = q[:, 2]
    nv = n @ rot.T
    tv = ta[:, :3] @ rot.T
    img = np.zeros((size, size, 3)) + np.array([14, 18, 14])
    zbuf = np.full((size, size), np.inf)
    # sample half-resolution copies, roughly what the game's mipmaps show at distance
    tex = np.array(diffuse.resize((ATLAS // 2, ATLAS // 2), Image.BOX).resize((ATLAS, ATLAS), Image.NEAREST))
    tex = tex[..., :3].astype(float) / 255
    nm = np.array(Image.fromarray(nmap, "RGBA").resize((ATLAS // 2, ATLAS // 2), Image.BOX)
                  .resize((ATLAS, ATLAS), Image.NEAREST)).astype(float) / 255
    key = normalize((-0.5, 0.6, -0.6))
    rim = normalize((0.6, 0.3, 0.8))
    for t in tris:
        P = q[t]
        if np.cross(P[1] - P[0], P[2] - P[0])[2] >= 0:  # back face (camera looks along +Z)
            continue
        xs, ys, zs = sx[t], sy[t], depth[t]
        x0, x1 = max(int(xs.min()), 0), min(int(xs.max()) + 1, size)
        y0, y1 = max(int(ys.min()), 0), min(int(ys.max()) + 1, size)
        if x0 >= x1 or y0 >= y1:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
        d = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
        if abs(d) < 1e-9:
            continue
        w0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / d
        w1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / d
        w2 = 1 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        z = w0 * zs[0] + w1 * zs[1] + w2 * zs[2]
        sub = zbuf[y0:y1, x0:x1]
        mask = inside & (z < sub)
        if not mask.any():
            continue
        W = np.stack([w0[mask], w1[mask], w2[mask]], -1)
        uvp = W @ uv[t]
        px = np.clip((uvp[:, 0] * ATLAS).astype(int), 0, ATLAS - 1)
        py = np.clip((uvp[:, 1] * ATLAS).astype(int), 0, ATLAS - 1)
        albedo = tex[py, px]
        N = W @ nv[t]
        N /= np.linalg.norm(N, axis=1, keepdims=True)
        T = W @ tv[t]
        T = T - N * np.sum(T * N, axis=1, keepdims=True)
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
        B = np.cross(N, T) * ta[t[0], 3]  # points along +v
        tx = nm[py, px, 1] * 2 - 1
        ty_up = nm[py, px, 3] * 2 - 1
        tz = np.sqrt(np.clip(1 - tx ** 2 - ty_up ** 2, 0, 1))
        Np = T * tx[:, None] - B * ty_up[:, None] + N * tz[:, None]
        Np /= np.linalg.norm(Np, axis=1, keepdims=True)
        lk = np.clip(Np @ key, 0, 1)
        lr = np.clip(Np @ rim, 0, 1) ** 2
        emit = nm[py, px, 2]
        col = albedo * (0.18 + 0.95 * lk[:, None]) + lr[:, None] * np.array([0.35, 0.75, 0.3]) * 0.6
        col += albedo * emit[:, None] * 1.5
        sub[mask] = z[mask]
        img[y0:y1, x0:x1][mask] = np.clip(col, 0, 1) * 255
    return Image.fromarray(img.clip(0, 255).astype(np.uint8))


def main():
    preview_dir = None
    if "--preview" in sys.argv:
        preview_dir = sys.argv[sys.argv.index("--preview") + 1]
    diffuse, nmap = make_textures()
    for name, build in MODELS.items():
        a = mesh_arrays(build())
        path = f"{MODEL_DIR}/{name}.mesh"
        write_mesh(path, f"{name}Shape", a)
        nv, nt, lo, hi = verify_mesh(os.path.join(ROOT, path))
        print(f"{name}: {nv} vertices, {nt} triangles, height {hi[1] - lo[1]:.2f}")
        if preview_dir:
            os.makedirs(preview_dir, exist_ok=True)
            front = render_preview(a, diffuse, nmap, yaw=-30)
            back = render_preview(a, diffuse, nmap, yaw=150)
            sheet = Image.new("RGB", (front.width * 2, front.height))
            sheet.paste(front, (0, 0))
            sheet.paste(back, (front.width, 0))
            sheet.save(os.path.join(preview_dir, f"{name}.png"))
    write_definitions()
    print("Models generated.")


if __name__ == "__main__":
    main()
