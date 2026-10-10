#!/usr/bin/env python3
"""Generate the 3D map models for the King in Yellow (Hastur) units.

Builds three low-poly static models procedurally and writes them in the
Clausewitz binary .mesh format, together with their textures and the
mesh/entity definitions HoI4 needs:

    gfx/models/units/eldritch/*.mesh            the models
    gfx/models/units/eldritch/*.dds             shared texture atlas (diffuse, normal, specular)
    gfx/entities/eldritch_hastur_meshes.gfx     pdxmesh definitions (with the in-game scale)
    gfx/entities/eldritch_hastur_units.asset    <sprite>_entity definitions used by the battalions

Clausewitz mesh conventions (matching the community io_pdx_mesh exporter):
Y is up, models face -Z, UV v=0 is the top of the texture, and triangles are
wound so that (B - A) x (C - A) points out of the surface.

Usage:
    python3 tools/generate_models.py            write everything
    python3 tools/generate_models.py --preview DIR   also render preview PNGs into DIR

Requires numpy and Pillow.
"""

import math
import os
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = "gfx/models/units/eldritch"
TEXTURE = "eldritch_hastur"
ATLAS = 256

# In-game size multiplier written into the pdxmesh definitions. The models are
# authored at roughly human scale (a zealot is ~1.9 units tall); raise or lower
# this if units look too small or too large on the map.
MESH_SCALE = 2.0

# Atlas bands (left half of the texture, mirrored top/bottom so either V
# convention samples the same colour).
ROBE, OCHRE, IVORY, BLACK, GOLD, LEATHER, FLESH, GLOW = range(8)
BAND_COLORS = {
    ROBE: (214, 168, 40),
    OCHRE: (140, 98, 22),
    IVORY: (236, 230, 210),
    BLACK: (22, 18, 16),
    GOLD: (226, 182, 70),
    LEATHER: (58, 44, 52),
    FLESH: (196, 186, 132),
    GLOW: (255, 236, 120),
}
# Special regions in the right half of the atlas.
SIGN_REGION = (0.5, 0.0, 1.0, 0.5)    # u0, v0, u1, v1 - banner with the Yellow Sign
MEMBRANE_REGION = (0.5, 0.5, 1.0, 1.0)  # Byakhee wing membrane


def band_v(band):
    return (band * 16 + 8) / ATLAS


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def normalize(v):
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


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
        if np.linalg.norm(cross) < 1e-12:
            return  # degenerate
        if outward is None:
            outward = self.n[a] + self.n[b] + self.n[c]
        if np.dot(cross, outward) < 0:
            b, c = c, b
        self.tris.append((a, b, c))

    def grid(self, rings, u_closed=False):
        """Triangulate a grid of vertex indices (rows of equal length)."""
        for i in range(len(rings) - 1):
            r0, r1 = rings[i], rings[i + 1]
            for j in range(len(r0) - 1):
                a, b, c, d = r0[j], r0[j + 1], r1[j + 1], r1[j]
                self.tri(a, b, c)
                self.tri(a, c, d)

    # -- primitives ---------------------------------------------------------

    def lathe(self, profile, band, segs=16, center=(0, 0, 0), rot=None, scale=(1, 1, 1),
              theta=(0.0, 2 * math.pi), double_sided=False):
        """Surface of revolution around local +Y. profile: [(r, y), ...] bottom to top."""
        rot = np.eye(3) if rot is None else rot
        scale = np.asarray(scale, dtype=float)
        center = np.asarray(center, dtype=float)
        pts = np.asarray(profile, dtype=float)
        # 2D outward normals of the profile
        prof_n = []
        for i in range(len(pts)):
            a = pts[max(i - 1, 0)]
            b = pts[min(i + 1, len(pts) - 1)]
            dr, dy = b[0] - a[0], b[1] - a[1]
            prof_n.append(normalize((dy, -dr)))
        sides = (1, -1) if double_sided else (1,)
        for side in sides:
            rings = []
            for i, (r, y) in enumerate(pts):
                ring = []
                for j in range(segs + 1):
                    t = theta[0] + (theta[1] - theta[0]) * j / segs
                    local = np.array([r * math.cos(t), y, r * math.sin(t)])
                    nr, ny = prof_n[i]
                    ln = np.array([nr * math.cos(t), ny, nr * math.sin(t)]) * side
                    p = rot @ (local * scale) + center
                    n = rot @ (ln / scale)
                    u = 0.02 + 0.46 * j / segs
                    ring.append(self.vert(p, n, (u, band_v(band))))
                rings.append(ring)
            self.grid(rings)

    def ellipsoid(self, center, radii, band, segs=14, rings=8, rot=None):
        profile = [(math.sin(math.pi * k / rings), -math.cos(math.pi * k / rings)) for k in range(rings + 1)]
        self.lathe(profile, band, segs=segs, center=center, rot=rot, scale=radii)

    def cone(self, base, apex, radius, band, segs=10):
        base, apex = np.asarray(base, float), np.asarray(apex, float)
        h = np.linalg.norm(apex - base)
        self.lathe([(0.0, 0.0), (radius, 0.0), (0.0, h)], band, segs=segs, center=base, rot=align_y_to(apex - base))

    def tube(self, path, radii, band, segs=10, cap_start=False, cap_end=True):
        """Tube along a polyline with per-point radius (parallel-transport frames)."""
        path = [np.asarray(p, float) for p in path]
        n_pts = len(path)
        tangents = []
        for i in range(n_pts):
            a = path[max(i - 1, 0)]
            b = path[min(i + 1, n_pts - 1)]
            tangents.append(normalize(b - a))
        ref = np.array([0.0, 0.0, 1.0]) if abs(tangents[0][2]) < 0.9 else np.array([1.0, 0.0, 0.0])
        normal = normalize(np.cross(tangents[0], ref))
        frames = []
        for i in range(n_pts):
            if i > 0:
                normal = normalize(normal - np.dot(normal, tangents[i]) * tangents[i])
            frames.append((normal, np.cross(tangents[i], normal)))
        rings = []
        for i, (p, r) in enumerate(zip(path, radii)):
            nrm, bin_ = frames[i]
            ring = []
            for j in range(segs + 1):
                a = 2 * math.pi * j / segs
                dirv = math.cos(a) * nrm + math.sin(a) * bin_
                ring.append(self.vert(p + dirv * r, dirv, (0.02 + 0.46 * j / segs, band_v(band))))
            rings.append(ring)
        self.grid(rings)
        for flag, idx, sign in ((cap_start, 0, -1), (cap_end, n_pts - 1, 1)):
            if flag and radii[idx] > 1e-4:
                cn = tangents[idx] * sign
                c = self.vert(path[idx], cn, (0.25, band_v(band)))
                ring = rings[idx]
                cap = [self.vert(self.p[k], cn, self.uv[k]) for k in ring]
                for j in range(segs):
                    self.tri(c, cap[j], cap[j + 1], outward=cn)

    def flat(self, poly, uv_fn, double_sided=True):
        """Planar polygon (may be concave), triangulated by ear clipping."""
        poly = [np.asarray(p, float) for p in poly]
        # Newell normal
        nrm = np.zeros(3)
        for i in range(len(poly)):
            a, b = poly[i], poly[(i + 1) % len(poly)]
            nrm += np.array([(a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]),
                             (a[0] - b[0]) * (a[1] + b[1])])
        nrm = normalize(nrm)
        # 2D basis in the plane
        ax = normalize(poly[1] - poly[0])
        ay = np.cross(nrm, ax)
        pts2 = [(float(np.dot(p - poly[0], ax)), float(np.dot(p - poly[0], ay))) for p in poly]
        tris = ear_clip(pts2)
        for side in ((1, -1) if double_sided else (1,)):
            n = nrm * side
            idx = [self.vert(p, n, uv_fn(p)) for p in poly]
            for a, b, c in tris:
                self.tri(idx[a], idx[b], idx[c], outward=n)

    def transformed(self, rot, offset, scale=1.0):
        """Copy of this builder's geometry, rotated/scaled/moved (for re-using parts)."""
        out = MeshBuilder()
        for p, n, uv in zip(self.p, self.n, self.uv):
            out.vert(rot @ (p * scale) + offset, rot @ n, uv)
        out.tris = list(self.tris)
        return out

    def merge(self, other):
        base = len(self.p)
        self.p += other.p
        self.n += other.n
        self.uv += other.uv
        self.tris += [(a + base, b + base, c + base) for a, b, c in other.tris]


def ear_clip(pts):
    n = len(pts)
    area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    idx = list(range(n)) if area > 0 else list(reversed(range(n)))

    def is_convex(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) > 1e-12

    def inside(p, a, b, c):
        d1 = (p[0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (p[1] - b[1])
        d2 = (p[0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (p[1] - c[1])
        d3 = (p[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (p[1] - a[1])
        return (d1 < 0 and d2 < 0 and d3 < 0) or (d1 > 0 and d2 > 0 and d3 > 0)

    tris = []
    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = pts[i0], pts[i1], pts[i2]
            if not is_convex(a, b, c):
                continue
            if any(inside(pts[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((i0, i1, i2))
            idx.pop(k)
            break
        else:
            break
    if len(idx) == 3:
        tris.append(tuple(idx))
    return tris


def region_uv(region, x0, x1, y0, y1):
    """UV function mapping a point's (x, y) extent into an atlas region."""
    u0, v0, u1, v1 = region

    def fn(p):
        fx = (p[0] - x0) / (x1 - x0)
        fy = (y1 - p[1]) / (y1 - y0)
        return (u0 + (u1 - u0) * min(max(fx, 0), 1), v0 + (v1 - v0) * min(max(fy, 0), 1))
    return fn


# ---------------------------------------------------------------------------
# Models (Y up, facing -Z)
# ---------------------------------------------------------------------------

def zealot(with_spear=True, banner=True):
    m = MeshBuilder()
    m.lathe([(0.0, 0.0), (0.36, 0.0), (0.34, 0.25), (0.30, 0.6), (0.26, 0.95), (0.24, 1.2), (0.26, 1.32),
             (0.20, 1.42), (0.08, 1.47), (0.0, 1.48)], ROBE, segs=16)
    m.lathe([(0.27, 0.80), (0.29, 0.84), (0.27, 0.88)], GOLD, segs=16)
    m.ellipsoid((0, 1.63, 0.02), (0.17, 0.20, 0.18), OCHRE)
    m.cone((0, 1.74, 0.06), (0, 1.98, 0.16), 0.11, OCHRE)
    m.ellipsoid((0, 1.61, -0.12), (0.11, 0.14, 0.05), IVORY)
    for sx in (-1, 1):
        m.ellipsoid((sx * 0.042, 1.64, -0.163), (0.02, 0.009, 0.01), BLACK, segs=8, rings=4)
    # arms
    m.tube([(0.22, 1.32, 0.0), (0.29, 1.12, -0.10), (0.30, 0.98, -0.20)], [0.07, 0.06, 0.05], ROBE)
    m.tube([(-0.22, 1.32, 0.0), (-0.28, 1.06, -0.05), (-0.24, 0.88, -0.12)], [0.07, 0.06, 0.05], ROBE)
    m.ellipsoid((0.30, 0.95, -0.22), (0.045, 0.05, 0.045), IVORY, segs=8, rings=5)
    m.ellipsoid((-0.24, 0.85, -0.14), (0.045, 0.05, 0.045), IVORY, segs=8, rings=5)
    if with_spear:
        m.tube([(0.30, 0.04, -0.22), (0.30, 2.20, -0.22)], [0.022, 0.022], BLACK, segs=6, cap_start=True)
        m.cone((0.30, 2.18, -0.22), (0.30, 2.46, -0.22), 0.055, GOLD, segs=8)
    if with_spear and banner:
        x0, x1, y0, y1 = 0.32, 0.68, 1.70, 2.14
        wave = [(x0, y1, -0.22), (0.44, y1, -0.20), (0.56, y1, -0.24), (x1, y1, -0.22),
                (x1, y0 + 0.04, -0.22), (0.56, y0, -0.24), (0.44, y0, -0.20), (x0, y0, -0.22)]
        m.flat(wave, region_uv(SIGN_REGION, x0, x1, y0, y1))
    return m


def byakhee_rider():
    m = MeshBuilder()
    # body, neck, head
    m.ellipsoid((0, 1.15, 0.10), (0.28, 0.30, 0.55), LEATHER, segs=16, rings=10)
    m.tube([(0, 1.22, -0.30), (0, 1.40, -0.58), (0, 1.55, -0.78)], [0.17, 0.12, 0.09], LEATHER, cap_end=False)
    m.ellipsoid((0, 1.58, -0.92), (0.10, 0.10, 0.21), LEATHER)
    m.cone((0, 1.55, -1.08), (0, 1.48, -1.34), 0.055, BLACK, segs=8)
    for sx in (-1, 1):
        m.ellipsoid((sx * 0.075, 1.63, -0.98), (0.03, 0.025, 0.03), GLOW, segs=8, rings=5)
        # leathery crest
        m.cone((sx * 0.05, 1.66, -0.86), (sx * 0.12, 1.82, -0.70), 0.03, BLACK, segs=6)
    # legs
    for sx in (-1, 1):
        for z, bend in ((-0.18, -0.12), (0.40, 0.10)):
            m.tube([(sx * 0.17, 1.00, z), (sx * 0.24, 0.55, z + bend), (sx * 0.22, 0.06, z - 0.05)],
                   [0.07, 0.05, 0.03], LEATHER, segs=8)
            for k in (-1, 0, 1):
                m.cone((sx * 0.22, 0.05, z - 0.05), (sx * 0.22 + k * 0.05, 0.0, z - 0.17), 0.02, BLACK, segs=5)
    # tail
    m.tube([(0, 1.10, 0.62), (0, 0.95, 0.95), (0, 0.70, 1.20), (0, 0.55, 1.42)], [0.10, 0.07, 0.04, 0.01],
           LEATHER, segs=8)
    # wings: leading-edge bones plus a scalloped membrane, raised and swept back
    for sx in (-1, 1):
        def W(x, y, z):
            return (sx * x, y, z)
        edge = [W(0.20, 1.35, -0.05), W(0.95, 1.95, 0.05), W(1.65, 2.35, 0.25), W(2.10, 2.05, 0.45)]
        membrane = edge + [W(1.85, 1.55, 0.55), W(1.55, 1.70, 0.45), W(1.30, 1.25, 0.55), W(1.00, 1.45, 0.42),
                           W(0.65, 1.10, 0.48), W(0.24, 1.18, 0.30)]
        if sx < 0:
            membrane = membrane[::-1]
        m.flat(membrane, region_uv(MEMBRANE_REGION, -2.2, 2.2, 1.0, 2.4))
        m.tube(edge, [0.05, 0.04, 0.03, 0.012], LEATHER, segs=6)
        for tip in (W(1.85, 1.55, 0.55), W(1.30, 1.25, 0.55), W(0.65, 1.10, 0.48)):
            m.tube([edge[2], tip], [0.02, 0.008], LEATHER, segs=5)
    # the rider: a seated, smaller zealot with a lance
    rider = zealot(with_spear=False)
    # squash the robe into a seated pose by scaling, then place on the back
    seated = rider.transformed(np.eye(3), np.array([0.0, 1.30, 0.12]), scale=0.62)
    m.merge(seated)
    m.tube([(0.22, 1.70, 0.20), (0.22, 2.05, -0.85)], [0.02, 0.02], BLACK, segs=6, cap_start=True)
    m.cone((0.22, 2.05, -0.85), (0.22, 2.13, -1.08), 0.045, GOLD, segs=8)
    return m


def king_in_yellow():
    m = MeshBuilder()
    # robe
    m.lathe([(0.0, 0.0), (1.02, 0.0), (0.95, 0.30), (0.80, 1.00), (0.66, 1.80), (0.56, 2.60), (0.60, 2.95),
             (0.64, 3.05), (0.46, 3.24), (0.18, 3.34), (0.0, 3.35)], ROBE, segs=22)
    m.lathe([(0.585, 2.30), (0.61, 2.36), (0.585, 2.42)], GOLD, segs=22)
    # tattered hem
    rng = np.random.default_rng(7)
    for k in range(26):
        t0 = 2 * math.pi * k / 26
        t1 = 2 * math.pi * (k + 1) / 26
        tm = (t0 + t1) / 2
        r_top, r_tip = 0.97, 1.16 + rng.uniform(-0.04, 0.06)
        y_top, y_tip = 0.42 + rng.uniform(-0.05, 0.05), 0.0
        poly = [(r_top * math.cos(t0), y_top, r_top * math.sin(t0)),
                (r_top * math.cos(t1), y_top, r_top * math.sin(t1)),
                (r_tip * math.cos(tm), y_tip, r_tip * math.sin(tm))]
        m.flat(poly, lambda p: (0.25, band_v(OCHRE)))
    # tattered mantle hanging behind (+Z is the back)
    m.lathe([(1.25, 0.05), (1.05, 1.00), (0.85, 2.10), (0.70, 3.00)], OCHRE, segs=12,
            theta=(math.radians(15), math.radians(165)), double_sided=True)
    # shoulders, hood, mask
    for sx in (-1, 1):
        m.ellipsoid((sx * 0.56, 3.00, 0.0), (0.28, 0.18, 0.28), OCHRE)
    m.ellipsoid((0, 3.62, 0.05), (0.30, 0.36, 0.32), OCHRE, segs=16, rings=10)
    m.cone((0, 3.86, 0.10), (0, 4.22, 0.36), 0.20, OCHRE, segs=12)
    m.ellipsoid((0, 3.58, -0.24), (0.20, 0.26, 0.08), IVORY, segs=16, rings=10)
    for sx in (-1, 1):
        m.ellipsoid((sx * 0.075, 3.63, -0.315), (0.04, 0.012, 0.012), BLACK, segs=8, rings=4)
    # crown
    m.lathe([(0.29, 3.82), (0.31, 3.86), (0.29, 3.90)], GOLD, segs=18)
    for k in range(7):
        t = -math.pi / 2 + (k - 3) * 0.42
        base = np.array([0.29 * math.cos(t), 3.88, 0.29 * math.sin(t)])
        tip = base + np.array([0.08 * math.cos(t), 0.36 - abs(k - 3) * 0.05, 0.08 * math.sin(t)])
        m.cone(base, tip, 0.05, GOLD, segs=6)
    # arms
    m.tube([(0.62, 3.00, 0.0), (1.10, 2.62, -0.30), (1.45, 2.30, -0.55)], [0.21, 0.18, 0.15], ROBE, segs=12)
    m.tube([(-0.62, 3.00, 0.0), (-0.95, 2.52, -0.35), (-1.05, 2.12, -0.52)], [0.21, 0.18, 0.15], ROBE, segs=12)
    m.ellipsoid((1.50, 2.24, -0.60), (0.10, 0.12, 0.10), FLESH)
    m.ellipsoid((-1.05, 2.05, -0.55), (0.10, 0.12, 0.10), FLESH)
    # sceptre topped with the Yellow Sign
    m.tube([(-1.05, 0.10, -0.55), (-1.05, 3.40, -0.55)], [0.05, 0.05], GOLD, segs=8, cap_start=True)
    m.ellipsoid((-1.05, 3.48, -0.55), (0.10, 0.10, 0.10), GOLD)
    for k in range(3):
        base_a = math.radians(90 + k * 120)
        pts, rad = [], []
        for i in range(12):
            t = i / 11
            r = 0.10 + 0.22 * t
            a = base_a + t * math.radians(150)
            pts.append((-1.05 + r * math.cos(a), 3.48 + r * math.sin(a), -0.55))
            rad.append(0.035 * (1 - t) + 0.01)
        m.tube(pts, rad, GOLD, segs=6)
    # tentacles writhing out from under the hem
    for k in range(8):
        t = 2 * math.pi * (k + 0.5) / 8
        d = np.array([math.cos(t), 0.0, math.sin(t)])
        side = np.array([-d[2], 0.0, d[0]])
        pts, rad = [], []
        for i in range(24):
            s = i / 23
            r = 0.55 + 1.75 * s
            lift = 0.10 + 0.05 * math.sin(s * 9 + k) + (0.55 * (s - 0.75) / 0.25 if s > 0.75 else 0.0)
            curl = 0.30 * math.sin(s * 5 + k * 1.3) * s
            pts.append(d * r + side * curl + np.array([0.0, lift, 0.0]))
            rad.append(0.17 * (1 - s) + 0.015)
        m.tube(pts, rad, FLESH, segs=9)
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


def mesh_arrays(m):
    p = np.array(m.p)
    n = np.array(m.n)
    uv = np.array(m.uv)
    ta = []
    for nv in n:
        ref = np.array([0.0, 1.0, 0.0]) if abs(nv[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
        t = normalize(np.cross(ref, nv))
        ta.extend([t[0], t[1], t[2], 1.0])
    lo, hi = p.min(axis=0), p.max(axis=0)
    centre = (lo + hi) / 2
    radius = float(np.max(np.linalg.norm(p - centre, axis=1)))
    return {
        "p": p.flatten().tolist(),
        "n": n.flatten().tolist(),
        "ta": ta,
        "u0": uv.flatten().tolist(),
        "tri": [i for t in m.tris for i in t],
        "boundingsphere": [*centre.tolist(), radius],
        "min": lo.tolist(),
        "max": hi.tolist(),
    }


def write_mesh(path, shape_name, m):
    a = mesh_arrays(m)
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
    return a


def read_mesh(path):
    """Minimal reader for the same format, used to verify what was written."""
    data = open(path, "rb").read()
    assert data[:4] == b"@@b@", "bad header"
    pos, tree, stack = 4, {"props": {}, "children": []}, []
    stack = [tree]
    while pos < len(data):
        ch = data[pos:pos + 1]
        if ch == b"[":
            depth = 0
            while data[pos:pos + 1] == b"[":
                depth += 1
                pos += 1
            end = data.index(b"\x00", pos)
            name = data[pos:end].decode("latin-1")
            pos = end + 1
            node = {"name": name, "props": {}, "children": []}
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
    names = [c["name"] for c in tree["children"]]
    assert names == ["object", "locator"], names
    shape = tree["children"][0]["children"][0]
    mesh = shape["children"][0]
    pr = mesh["props"]
    nv = len(pr["p"]) // 3
    assert len(pr["n"]) == nv * 3 and len(pr["ta"]) == nv * 4 and len(pr["u0"]) == nv * 2
    assert len(pr["tri"]) % 3 == 0 and max(pr["tri"]) < nv and min(pr["tri"]) >= 0
    assert nv < 65536
    kids = {c["name"]: c["props"] for c in mesh["children"]}
    assert set(kids) == {"aabb", "material"}
    assert kids["material"]["shader"] == "PdxMeshStandard"
    for slot in ("diff", "n", "spec"):
        assert os.path.exists(os.path.join(os.path.dirname(path), kids["material"][slot])), slot
    # winding: geometric normals should agree with vertex normals
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
    levels = []
    cur = img
    while True:
        levels.append(cur)
        if cur.width == 1 and cur.height == 1:
            break
        cur = cur.resize((max(1, cur.width // 2), max(1, cur.height // 2)), Image.LANCZOS)
    header = struct.pack(
        "<4sIIIIIII11I", b"DDS ", 124,
        0x1 | 0x2 | 0x4 | 0x8 | 0x1000 | 0x20000,  # + MIPMAPCOUNT
        h, w, w * 4, 0, len(levels), *([0] * 11))
    pixel_format = struct.pack("<II4sIIIII", 32, 0x41, b"\0\0\0\0", 32,
                               0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    caps = struct.pack("<IIIII", 0x1000 | 0x8 | 0x400000, 0, 0, 0, 0)  # TEXTURE | COMPLEX | MIPMAP
    body = b"".join(np.array(lv)[:, :, [2, 1, 0, 3]].tobytes() for lv in levels)
    full = os.path.join(ROOT, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as f:
        f.write(header + pixel_format + caps + body)


def yellow_sign(size, color):
    """The Yellow Sign: three hooked arms around a ring."""
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for k in range(3):
        base = math.radians(90 + k * 120)
        pts = []
        for i in range(60):
            t = i / 59
            r = (0.08 + 0.32 * t) * s
            a = base + t * math.radians(150)
            pts.append((s / 2 + r * math.cos(a), s / 2 - r * math.sin(a)))
        for i in range(len(pts) - 1):
            w = int(s * (0.06 - 0.04 * i / len(pts)))
            d.line([pts[i], pts[i + 1]], fill=color, width=max(2, w))
        ex, ey = pts[-1]
        d.ellipse([ex - s * 0.03, ey - s * 0.03, ex + s * 0.03, ey + s * 0.03], fill=color)
    d.ellipse([s * 0.42, s * 0.42, s * 0.58, s * 0.58], outline=color, width=int(s * 0.03))
    return img.resize((size, size), Image.LANCZOS)


def make_textures():
    rng = np.random.default_rng(3)
    diff = np.zeros((ATLAS, ATLAS, 4), dtype=float)
    half = ATLAS // 2
    # colour bands (left half), mirrored top/bottom
    for band, col in BAND_COLORS.items():
        stripe = np.array(col, dtype=float)[None, :] * (0.88 + 0.12 * np.sin(np.linspace(0, 18 * math.pi, half)))[:, None]
        rows = list(range(band * 16, band * 16 + 16)) + list(range(ATLAS - band * 16 - 16, ATLAS - band * 16))
        for r in rows:
            diff[r, :half, :3] = stripe
    # banner with the Yellow Sign (top right)
    cloth = np.array(BAND_COLORS[BLACK], dtype=float) + 12
    diff[:half, half:, :3] = cloth
    sign = np.array(yellow_sign(half - 16, (232, 190, 60, 255))).astype(float)
    a = sign[..., 3:4] / 255
    diff[8:half - 8, half + 8:ATLAS - 8, :3] = diff[8:half - 8, half + 8:ATLAS - 8, :3] * (1 - a) + sign[..., :3] * a
    # wing membrane with veins (bottom right)
    mem = Image.new("RGB", (half, half), (70, 40, 58))
    md = ImageDraw.Draw(mem)
    for k in range(9):
        ang = math.radians(10 + k * 9)
        md.line([(0, 0), (half * 1.2 * math.cos(ang), half * 1.2 * math.sin(ang))], fill=(38, 22, 32), width=3)
    mem = mem.filter(ImageFilter.GaussianBlur(1))
    diff[half:, half:, :3] = np.array(mem, dtype=float)
    # grain
    diff[..., :3] += rng.normal(0, 5, (ATLAS, ATLAS))[..., None]
    diff[..., 3] = 255
    diff_img = Image.fromarray(diff.clip(0, 255).astype(np.uint8), "RGBA")
    save_dds_mips(diff_img, f"{MODEL_DIR}/{TEXTURE}_diffuse.dds")
    # flat normal map (works for both RG and AG normal encodings)
    save_dds_mips(Image.new("RGBA", (ATLAS, ATLAS), (128, 128, 255, 128)), f"{MODEL_DIR}/{TEXTURE}_normal.dds")
    # low, matte specular; gold gets a little more shine
    spec = np.full((ATLAS, ATLAS, 4), (30, 30, 30, 0), dtype=np.uint8)
    for r in list(range(GOLD * 16, GOLD * 16 + 16)) + list(range(ATLAS - GOLD * 16 - 16, ATLAS - GOLD * 16)):
        spec[r, :half] = (140, 140, 140, 0)
    save_dds_mips(Image.fromarray(spec, "RGBA"), f"{MODEL_DIR}/{TEXTURE}_spec.dds")
    return diff_img


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
# Preview renderer (software z-buffer, for checking the models by eye)
# ---------------------------------------------------------------------------

def render_preview(m, atlas, size=420, yaw=-35, pitch=-18):
    a = mesh_arrays(m)
    p = np.array(a["p"]).reshape(-1, 3)
    uv = np.array(a["u0"]).reshape(-1, 2)
    tris = np.array(a["tri"]).reshape(-1, 3)
    # camera in front (-Z), to the side and slightly above, looking at the model
    rot = rot_x(math.radians(pitch)) @ rot_y(math.radians(yaw))
    centre = (p.min(axis=0) + p.max(axis=0)) / 2
    q = (p - centre) @ rot.T
    extent = np.abs(q[:, :2]).max() * 1.1
    sx = (q[:, 0] / extent * 0.5 + 0.5) * size
    sy = (0.5 - q[:, 1] / extent * 0.5) * size
    depth = q[:, 2]
    img = np.zeros((size, size, 3)) + np.array([40, 42, 50])
    zbuf = np.full((size, size), np.inf)
    tex = np.array(atlas)[..., :3].astype(float)
    light = normalize((-0.4, 0.8, -0.6))
    view = np.array([0.0, 0.0, -1.0])  # camera looks toward +Z in view space
    for t in tris:
        P = q[t]
        nrm = np.cross(P[1] - P[0], P[2] - P[0])
        if np.dot(nrm, view) <= 0:  # back face by winding
            continue
        world_n = normalize(np.cross(p[t[1]] - p[t[0]], p[t[2]] - p[t[0]]))
        shade = 0.35 + 0.65 * max(0.0, float(np.dot(world_n, light)))
        u, v = uv[t].mean(axis=0)
        col = tex[min(int(v * ATLAS), ATLAS - 1), min(int(u * ATLAS), ATLAS - 1)] * shade
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
        sub[mask] = z[mask]
        img[y0:y1, x0:x1][mask] = col
    return Image.fromarray(img.clip(0, 255).astype(np.uint8))


def main():
    preview_dir = None
    if "--preview" in sys.argv:
        preview_dir = sys.argv[sys.argv.index("--preview") + 1]
    atlas = make_textures()
    for name, build in MODELS.items():
        m = build()
        path = f"{MODEL_DIR}/{name}.mesh"
        write_mesh(path, f"{name}Shape", m)
        nv, nt, lo, hi = verify_mesh(os.path.join(ROOT, path))
        print(f"{name}: {nv} vertices, {nt} triangles, height {hi[1] - lo[1]:.2f}")
        if preview_dir:
            os.makedirs(preview_dir, exist_ok=True)
            front = render_preview(m, atlas, yaw=-35)
            back = render_preview(m, atlas, yaw=150)
            sheet = Image.new("RGB", (front.width * 2, front.height))
            sheet.paste(front, (0, 0))
            sheet.paste(back, (front.width, 0))
            sheet.save(os.path.join(preview_dir, f"{name}.png"))
    write_definitions()
    print("Models generated.")


if __name__ == "__main__":
    main()
