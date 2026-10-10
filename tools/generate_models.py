#!/usr/bin/env python3
"""Generate the 3D map models for the King in Yellow (Hastur) units.

Builds three detailed static models procedurally and writes them in the
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

    def tube(self, path, radii, region, segs=10, inner=None, cap=True):
        """Tube along a polyline. inner: per-point 'inner side' direction; that side
        maps to u = 0.5 of the region. Returns the ring frames for placing details."""
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
        rings = []
        for i in range(n_pts):
            T, I, S = frames[i]
            ring = []
            for j in range(segs + 1):
                a = 2 * math.pi * j / segs
                d = -math.cos(a) * I + math.sin(a) * S  # a = pi -> inner side
                ring.append(self.vert(path[i] + d * radii[i], d, region_uv(region, j / segs, length[i] / total)))
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
# ---------------------------------------------------------------------------

def radial(theta):
    """Unit direction around the Y axis; theta = 0 is the back (+Z), pi the front (-Z)."""
    return np.array([math.sin(theta), 0.0, math.cos(theta)])


def hooded_figure(robe_bottom=0.0, hem_flare=0.75, seed=0, arms=True, detail=1.0):
    """A hooded cultist in a draped robe and cowl with a bandage-wrapped face.

    Authored ~1.95 units tall; the shoulders sit at y ~1.38 and the head at ~1.68.
    detail scales the mesh resolution (1.0 = hero quality).
    """
    m = MeshBuilder()
    top_y = 1.40
    span = top_y - robe_bottom

    def res(n):
        return max(6, int(n * detail))

    # Robe: deep vertical folds that grow towards a ragged, holed hem pooling on the ground.
    def robe(s, t):
        th = 2 * math.pi * s
        r = 0.19 + 0.02 * math.sin(math.pi * min(t * 2.2, 1.0)) + 0.15 * hem_flare * t ** 1.6
        amp = 0.03 + 0.17 * t ** 1.2
        fold = (0.55 * math.sin(7 * th + 0.9 + 1.4 * t) + 0.30 * math.sin(11 * th + 2.1 - 2.0 * t)
                + 0.18 * math.sin(17 * th + 4.0 + 2.5 * t * math.sin(th)))
        r *= 1 + amp * fold
        hem = robe_bottom + 0.02 + 0.05 * (0.5 + 0.5 * hash_noise(s, seed + 1))
        y = top_y - span * t + (hem - robe_bottom) * t ** 6
        d = radial(th)
        return np.array([d[0] * r * 1.06, y, d[2] * r * 0.94])

    def tatters(s, t):
        if t < 0.82:
            return False
        holes = hash_noise(s * 3 % 1.0, seed + 7) * 0.6 + hash_noise((s * 7 + t * 0.5) % 1.0, seed + 9) * 0.4
        return holes > 0.62 - (t - 0.82) * 1.4

    m.surface(robe, res(64), res(30), "cloth", closed_u=True, inner_region="lining", skip=tatters,
              outward=lambda p, s, t: np.array([p[0], 0.0, p[2]]))

    # Cowl draped over narrow shoulders, hanging lower at the front in loose folds.
    def cowl(s, t):
        th = 2 * math.pi * s
        front = 0.5 - 0.5 * math.cos(th)  # 1 at the front
        r = 0.075 + 0.19 * t ** 0.6
        r *= 1 + (0.02 + 0.11 * t) * (0.6 * math.sin(8 * th + 1.3) + 0.4 * math.sin(13 * th + 0.4 + 2 * t))
        r *= 1 + 0.16 * front * math.sin(math.pi * t)
        y = 1.54 - t * (0.40 + 0.24 * front) - 0.045 * math.sin(t * math.pi * 3.0) * front * t
        y += 0.03 * hash_noise(s, seed + 3) * t ** 3
        d = radial(th)
        return np.array([d[0] * r * 1.22, y, d[2] * r * 0.95])

    def cowl_rag(s, t):
        return t > 0.86 and hash_noise((s * 5) % 1.0, seed + 5) > 0.55

    m.surface(cowl, res(56), res(14), "cloth", closed_u=True, inner_region="lining", skip=cowl_rag,
              outward=lambda p, s, t: np.array([p[0], 0.25, p[2]]))

    # Long, bandage-wrapped head.
    m.ellipsoid((0.0, 1.68, -0.015), (0.085, 0.135, 0.098), "bandage", segs=res(18), rings=res(12))

    # Tall pointed hood, open at the front, its brim overhanging the face.
    hc = np.array([0.0, 1.69, 0.02])

    def hood(s, t):
        e = -0.30 * math.pi + t * 0.80 * math.pi
        w = 1.15 * (1 - smoothstep(-0.35, 1.05, e)) + 0.015
        a = w + s * (2 * math.pi - 2 * w)  # a = 0 is the front (-Z)
        ce, se = math.cos(e), math.sin(e)
        peak = max(0.0, se) ** 4
        front = 0.5 + 0.5 * math.cos(a)
        x = 0.140 * ce * math.sin(a) * (1 + 0.05 * math.sin(5 * a + t * 3))
        y = 0.190 * se + 0.17 * peak
        z = -0.165 * ce * math.cos(a) - 0.045 * front * max(0.0, se) + 0.11 * peak
        return hc + np.array([x, y, z])

    m.surface(hood, res(28), res(18), "cloth", inner_region="lining",
              outward=lambda p, s, t: p - hc)

    if arms:
        for sx, wrist in ((1, (0.23, 1.02, -0.20)), (-1, (-0.21, 0.97, -0.12))):
            sh = np.array([sx * 0.17, 1.32, -0.01])
            el = (sh + np.array(wrist)) / 2 + np.array([sx * 0.04, 0.0, 0.03])
            m.tube([sh, el, wrist], [0.06, 0.065, 0.08], "cloth", segs=res(12), cap=False)
            m.ellipsoid(np.array(wrist) + np.array([0.0, -0.035, -0.02]), (0.036, 0.048, 0.036), "bandage",
                        segs=res(10), rings=res(6))
    return m


def spear_with_banner(m, x, z, top=2.25, seed=11):
    m.tube([(x, 0.02, z), (x, top, z)], [0.018, 0.016], "wood", segs=8)
    m.lathe([(0.0, 0.0), (0.024, 0.0), (0.024, 0.05), (0.0, 0.06)], "metal", segs=8, center=(x, top - 0.02, z))
    # leaf-shaped iron blade, flattened
    m.lathe([(0.0, 0.0), (0.020, 0.02), (0.045, 0.10), (0.030, 0.20), (0.0, 0.30)], "metal", segs=8,
            center=(x, top + 0.03, z), scale=(1, 1, 0.3))
    # crossbar and tattered banner
    bw, bh = 0.34, 0.50
    y0 = top - 0.12
    m.tube([(x - 0.02, y0, z), (x + bw + 0.03, y0, z)], [0.012, 0.012], "wood", segs=6)

    def banner(s, t):
        return np.array([x + 0.02 + s * bw,
                         y0 - 0.02 - t * bh - 0.03 * math.sin(s * math.pi),
                         z + 0.035 * math.sin(s * 5.0 + t * 2.5) + 0.02 * t * math.sin(s * 11)])

    def rag(s, t):
        cut = 0.80 + 0.18 * hash_noise(s, seed)
        hole = t > 0.35 and hash_noise((s * 2 + t) % 1.0, seed + 2) * hash_noise((t * 3) % 1.0, seed + 4) > 0.45
        return t > cut or hole

    m.surface(banner, 14, 18, "banner", inner_region="banner", skip=rag,
              outward=lambda p, s, t: np.array([0.0, 0.0, -1.0]))


def zealot():
    m = hooded_figure(seed=0, detail=0.75)
    spear_with_banner(m, 0.23, -0.24)
    return m


def tentacle_path(L, lift, curl, twist, start_r, theta, steps=48):
    """Integrate a tentacle that runs along the ground, rises and hooks over."""
    pts, inner = [], []
    p = np.array([math.sin(theta) * start_r, 0.12, math.cos(theta) * start_r])
    d0 = radial(theta)
    up = np.array([0.0, 1.0, 0.0])
    for i in range(steps):
        s = i / (steps - 1)
        phi = (lift * smoothstep(0.10, 0.55, s) + curl * smoothstep(0.55, 1.0, s)) * math.pi / 2
        side = np.cross(up, d0)
        d = normalize(d0 * math.cos(twist * s) + side * math.sin(twist * s))
        tangent = d * math.cos(phi) + up * math.sin(phi)
        pts.append(p.copy())
        inner.append(-d * math.sin(phi) + up * math.cos(phi))
        p = p + tangent * (L / (steps - 1))
        p[1] = max(p[1], 0.06)
    return pts, inner


def add_tentacle(m, L, r0, lift, curl, twist, start_r, theta, suckers=True):
    pts, inner = tentacle_path(L, lift, curl, twist, start_r, theta)
    n = len(pts)
    radii = [r0 * (1 - i / (n - 1)) ** 1.1 + 0.01 for i in range(n)]
    # gentle irregular bulges along the length
    radii = [r * (1 + 0.06 * math.sin(i * 0.9 + theta * 3)) for i, r in enumerate(radii)]
    frames = m.tube(pts, radii, "tentacle", segs=14, inner=inner)
    if not suckers:
        return
    k = 0
    i = 3
    while i < n - 2:
        T, I, S = frames[i]
        for row in (-1, 1):
            if (k + (row > 0)) % 2:
                continue
            a = math.pi + row * 0.55
            d = -math.cos(a) * I + math.sin(a) * S
            rs = radii[i] * 0.30
            m.sucker(pts[i] + d * radii[i] * 0.92, d, rs)
        k += 1
        i += 1


def king_in_yellow():
    K = 2.5
    m = MeshBuilder()
    m.merge(hooded_figure(seed=3, arms=False, hem_flare=0.65), scale=K)
    rng = np.random.default_rng(21)
    for k in range(8):
        theta = 2 * math.pi * (k + 0.5) / 8 + rng.uniform(-0.25, 0.25)
        L = rng.uniform(3.8, 5.2)
        lift = rng.uniform(0.9, 1.1)
        curl = rng.choice([-1, 1]) * rng.uniform(0.5, 1.3)
        twist = rng.uniform(-0.5, 0.5)
        add_tentacle(m, L, 0.30, lift, curl, twist, 0.55, theta)
    return m


def byakhee_rider():
    m = MeshBuilder()
    # Gaunt body along the spine (z from the tail end 0.62 to the chest -0.38), ribs on the flanks.
    def body(s, t):
        th = 2 * math.pi * s
        z = 0.62 - t * 1.00
        w = 0.06 + 0.24 * math.sin(math.pi * min(max(t * 1.05, 0.0), 1.0)) ** 0.8
        h = 0.06 + 0.26 * math.sin(math.pi * min(max(t * 1.02, 0.0), 1.0)) ** 0.9
        ribs = 0.035 * max(0.0, math.sin(t * math.pi * 11)) * smoothstep(0.35, 0.55, t) * (1 - smoothstep(0.85, 1.0, t))
        side = abs(math.cos(th))
        r_w = w * (1 + ribs * side * 4)
        x = math.cos(th) * r_w
        y = 1.15 + math.sin(th) * h - 0.04 * (1 - math.sin(th)) * side
        return np.array([x, y, z])

    m.surface(body, 28, 30, "leather", closed_u=True,
              outward=lambda p, s, t: np.array([p[0], p[1] - 1.15, 0.0]))
    # bony spine ridge
    for i in range(9):
        z = 0.45 - i * 0.10
        m.cone((0.0, 1.38 - abs(z - 0.05) * 0.12, z), (0.0, 1.50 - abs(z - 0.05) * 0.14, z + 0.05), 0.025,
               "bone", segs=6)
    # neck and skull-like head with a long toothed beak and burning eyes
    neck = [(0.0, 1.22, -0.30), (0.0, 1.38, -0.52), (0.0, 1.52, -0.70), (0.0, 1.58, -0.82)]
    m.tube(neck, [0.14, 0.10, 0.08, 0.075], "leather", segs=12, cap=False)
    m.ellipsoid((0.0, 1.60, -0.92), (0.085, 0.09, 0.17), "bone", segs=14, rings=10)
    m.lathe([(0.0, 0.0), (0.05, 0.02), (0.04, 0.15), (0.0, 0.34)], "bone", segs=8, center=(0.0, 1.57, -1.04),
            rot=align_y_to((0.0, -0.2, -1.0)), scale=(1, 1, 0.75))
    for k in range(6):
        z = -1.06 - k * 0.045
        for sx in (-1, 1):
            m.cone((sx * 0.022, 1.545 - k * 0.006, z), (sx * 0.020, 1.505 - k * 0.006, z - 0.01), 0.008,
                   "bone", segs=4)
    for sx in (-1, 1):
        m.ellipsoid((sx * 0.062, 1.64, -0.98), (0.026, 0.022, 0.026), "glow", segs=8, rings=6)
        m.cone((sx * 0.05, 1.67, -0.86), (sx * 0.13, 1.84, -0.66), 0.025, "bone", segs=6)
    # legs with talons
    for sx in (-1, 1):
        for z, bend in ((-0.16, -0.14), (0.38, 0.12)):
            hip = (sx * 0.15, 1.02, z)
            knee = (sx * 0.27, 0.62, z + bend)
            ankle = (sx * 0.22, 0.20, z - 0.06)
            foot = (sx * 0.22, 0.06, z - 0.10)
            m.tube([hip, knee, ankle, foot], [0.06, 0.04, 0.03, 0.025], "leather", segs=8)
            for k in (-1, 0, 1):
                m.cone(foot, (sx * 0.22 + k * 0.06, 0.0, z - 0.25), 0.014, "bone", segs=5)
    # tail
    tail = [(0.0, 1.10, 0.60), (0.0, 1.00, 0.90), (0.0, 0.80, 1.15), (0.0, 0.62, 1.32), (0.05, 0.50, 1.48)]
    m.tube(tail, [0.08, 0.06, 0.04, 0.025, 0.008], "leather", segs=8)
    # wings: arm bones, finger struts and a torn membrane between them
    for sx in (-1, 1):
        sh = np.array([sx * 0.18, 1.34, -0.08])
        elbow = np.array([sx * 0.85, 1.88, 0.02])
        wrist = np.array([sx * 1.45, 2.22, 0.20])
        tips = [np.array([sx * 2.15, 2.00, 0.42]), np.array([sx * 1.95, 1.50, 0.62]),
                np.array([sx * 1.45, 1.20, 0.66]), np.array([sx * 0.95, 1.08, 0.55])]
        m.tube([sh, elbow, wrist], [0.05, 0.04, 0.03], "leather", segs=8)
        m.cone(wrist, wrist + np.array([sx * 0.05, 0.16, -0.08]), 0.02, "bone", segs=5)
        for tip in tips:
            m.tube([wrist, (wrist + tip) / 2 + np.array([0, 0.04, 0]), tip], [0.022, 0.015, 0.006], "bone", segs=6)
        edge = [sh + np.array([0, -0.06, 0.25])] + tips[::-1]  # body-side root to the leading tip

        def membrane(s, t, edge=edge, wrist=wrist, sh=sh, elbow=elbow):
            # t = 0 along the arm (shoulder -> elbow -> wrist), t = 1 at the trailing edge
            a = sh + (elbow - sh) * min(s * 2, 1) + (wrist - elbow) * max(s * 2 - 1, 0)
            k = s * (len(edge) - 1)
            i = min(int(k), len(edge) - 2)
            f = k - i
            b = edge[i] * (1 - f) + edge[i + 1] * f
            scallop = 0.10 * t * abs(math.sin(k * math.pi))
            p = a + (b - a) * t
            return p + normalize(a - b) * scallop + np.array([0, -0.03 * math.sin(t * math.pi), 0])

        def torn(s, t, sx=sx):
            rip = hash_noise((s * 1.7 + t * 0.4) % 1.0, 30 + sx) + 0.6 * hash_noise((t * 1.3 + s * 0.2) % 1.0, 40 + sx)
            return t > 0.30 and rip > 0.55 - 0.35 * t

        m.surface(membrane, 22, 10, "membrane", inner_region="membrane", skip=torn,
                  outward=lambda p, s, t: np.array([0.0, 1.0, 0.0]),
                  uv_fn=lambda s, t: region_uv("membrane", s, t))
    # the rider: a seated cultist with a lance and a ragged pennant
    rider = hooded_figure(robe_bottom=0.72, hem_flare=1.8, seed=5, detail=0.55)
    m.merge(rider, offset=(0.0, 0.80, 0.10), scale=0.70)
    lance = [(0.20, 1.60, 0.25), (0.20, 2.05, -0.95)]
    m.tube(lance, [0.016, 0.014], "wood", segs=6)
    m.lathe([(0.0, 0.0), (0.03, 0.03), (0.02, 0.18), (0.0, 0.26)], "metal", segs=8, center=lance[1],
            rot=align_y_to(np.array(lance[1]) - np.array(lance[0])), scale=(1, 1, 0.35))

    def pennant(s, t):
        base = np.array(lance[0]) + (np.array(lance[1]) - np.array(lance[0])) * (0.62 + 0.25 * s)
        return base + np.array([0.0, -0.20 * t * (1 - 0.6 * s), 0.10 * t + 0.03 * math.sin(s * 6 + t * 3)])

    m.surface(pennant, 8, 6, "banner", inner_region="banner",
              skip=lambda s, t: t > 0.7 + 0.25 * hash_noise(s, 77),
              outward=lambda p, s, t: np.array([1.0, 0.0, 0.0]))
    return m


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
