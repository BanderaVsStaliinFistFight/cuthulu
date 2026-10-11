"""Battalion icons: each unit as a small, lit scene.

Every icon is a little diorama - figures sculpted as signed distance fields
(art_render), standing on churned mud or sea under a smoky sky, lit by a low
key light with a rim behind - rendered at several times the icon size, graded
like an old war photograph (dirty, desaturated, crushed blacks, a tint of the
god's colour), then reduced and given film grain and scratches at the final
size so the grit survives.

Figures face +Z (toward the camera) with their feet at y = 0, in metres.
Each scene returns the picture and the coverage of its figures; textures()
lays them out the way the game reads battalion icons (see GAME TEXTURES).
"""

import math

import numpy as np
from PIL import Image, ImageFilter

import art_render as R
from art_render import Field, Material, Camera, Light, smoothstep

ICON_SIZE = (63, 42)  # the picture: 3:2, as tall as the designer slot
SCALE = 4          # render at SCALE x the icon size, then reduce


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rot_y(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def local(p, pos, yaw=0.0, scale=1.0):
    """Points in the frame of a figure standing at pos turned yaw degrees
    about Y (positive turns its face toward +X), scaled by scale."""
    return R.to_local(p, pos, rot_y(yaw)) / scale


def scaled(fn, p, pos, yaw=0.0, scale=1.0):
    """fn evaluated in a placed figure's frame, distances back in world units."""
    f = fn(local(p, pos, yaw, scale))
    f.d = f.d * scale
    return f


def near(d, band):
    """Indices of points within band of the surface (for costly detail)."""
    return np.where(np.abs(d) < band)[0]


def fade(d, band):
    """Weight for detail added near a surface: 1 on it, easing to 0 at the
    edge of the band, so the distance field has no step where detail stops."""
    return smoothstep(band, band * 0.35, np.abs(d))


def displace(d, p, amount, freq, seed, band=0.06, ridged=False):
    """Roughen a surface with 3D noise, evaluated only near it."""
    i = near(d, band)
    if i.size:
        q = p[i] * freq
        n = R.ridged3(q, 3, seed) - 0.5 if ridged else R.fbm3(q, 3, seed)
        d = d.copy()
        d[i] -= amount * n * fade(d[i], band)
    return d


def sd_box(p, c, half, rot=None, r=0.0):
    q = np.abs(R.to_local(p, c, rot)) - (np.asarray(half, float) - r)
    return R.length(np.maximum(q, 0)) + np.minimum(q.max(axis=1), 0) - r


def _dot2(v):
    return np.einsum("ij,ij->i", v, v)


def sd_triangle(p, a, b, c, thickness):
    """A thin triangular sheet a-b-c of the given half thickness."""
    a, b, c = (np.asarray(v, float) for v in (a, b, c))
    ba, cb, ac = b - a, c - b, a - c
    pa, pb, pc = p - a, p - b, p - c
    nor = np.cross(ba, ac)
    inside = (np.sign(pa @ np.cross(ba, nor)) + np.sign(pb @ np.cross(cb, nor)) + np.sign(pc @ np.cross(ac, nor))) >= 2
    e1 = _dot2(ba[None, :] * np.clip((pa @ ba) / (ba @ ba), 0, 1)[:, None] - pa)
    e2 = _dot2(cb[None, :] * np.clip((pb @ cb) / (cb @ cb), 0, 1)[:, None] - pb)
    e3 = _dot2(ac[None, :] * np.clip((pc @ ac) / (ac @ ac), 0, 1)[:, None] - pc)
    face = (pa @ nor) ** 2 / (nor @ nor)
    return np.sqrt(np.where(inside, face, np.minimum(np.minimum(e1, e2), e3))) - thickness


def bat_wing(p, side, shoulder, elbow, wrist, tips, back, thickness=0.012, bone=0.06):
    """A membranous bat wing: arm bones to the wrist, fingers fanning to the
    tips, skin stretched between them and back to the flank, its trailing
    edge scalloped between the fingers. side mirrors it in x (+1 / -1).
    Returns (bones, membrane) distances."""
    m = np.array([side, 1.0, 1.0])
    S, E, W, B = (np.asarray(v, float) * m for v in (shoulder, elbow, wrist, back))
    T = [np.asarray(t, float) * m for t in tips]
    bones = R.sd_tube(p, [S, E, W], [bone, bone * 0.8, bone * 0.6])
    for t in T:
        bones = np.minimum(bones, R.sd_round_cone(p, W, t, bone * 0.45, bone * 0.12))
    mem = np.minimum(sd_triangle(p, S, E, B, thickness), sd_triangle(p, E, W, B, thickness))
    edge = [W] + T + [B]
    for i in range(1, len(edge) - 1):
        mem = np.minimum(mem, sd_triangle(p, W, edge[i], edge[i + 1], thickness))
    trail = T + [B]
    for i in range(len(trail) - 1):
        a, b = trail[i], trail[i + 1]
        mid = (a + b) / 2
        out = R.normalize(mid - W)
        r = np.linalg.norm(b - a) * 0.42
        mem = np.maximum(mem, -R.sd_sphere(p, mid + out * r * 0.62, r))
    return bones, mem


# ---------------------------------------------------------------------------
# Textures
# ---------------------------------------------------------------------------

def mottled(base, seed, freq=6.0, amount=0.18, grime=0.5, grime_col=(0.045, 0.036, 0.028)):
    """Worn, dirty material: soft blotches, fine grain, and grime that
    gathers low down toward the mud."""
    base = np.asarray(base, float)
    gc = np.asarray(grime_col, float)

    def tex(p, n):
        col = base * (1 + amount * R.fbm3(p * freq, 3, seed) + 0.06 * R.fbm3(p * freq * 6, 2, seed + 7))[:, None]
        g = smoothstep(-0.35, 0.65, R.fbm3(p * 2.2 + 5, 3, seed + 1)) * 0.55
        g = np.clip(g + np.clip(0.75 - p[:, 1], 0, 0.75) * 0.9, 0, 1)[:, None] * grime
        return col * (1 - g) + gc * g
    return tex


def scaly(base, seed, freq=40.0, belly=None):
    base = np.asarray(base, float)

    def tex(p, n):
        cells = R.ridged3(p * freq, 2, seed)
        col = base * (0.8 + 0.3 * smoothstep(0.6, 0.9, cells))[:, None]
        col = col * (1 + 0.2 * R.fbm3(p * 5, 3, seed + 1))[:, None]
        if belly is not None:
            b = np.clip(-n[:, 1] * 0.8 + 0.2, 0, 1)[:, None]
            col = col * (1 - b) + np.asarray(belly) * b
        return col
    return tex


def _puddles(p, seed):
    return smoothstep(0.30, 0.42, R.fbm3(p * np.array([0.55, 0, 0.9]) + 11, 3, seed + 3))


def mud(seed, base=(0.060, 0.050, 0.038)):
    base = np.asarray(base, float)

    def tex(p, n):
        col = base * (1 + 0.35 * R.fbm3(p * 1.3, 3, seed) + 0.2 * R.fbm3(p * 9, 2, seed + 1))[:, None]
        pud = _puddles(p, seed)[:, None]
        return col * (1 - 0.7 * pud) + np.array([0.012, 0.012, 0.013]) * 0.7 * pud
    return tex


def mud_spec(seed):
    def spec(p, n):
        return 0.15 + 3.0 * _puddles(p, seed)
    return spec


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

def ground(p, seed, height=0.0):
    """Churned mud, only roughened close to the ground."""
    d = p[:, 1] - height
    i = np.where(d < 0.25)[0]
    if i.size:
        q = p[i]
        d = d.copy()
        d[i] -= (0.06 * R.fbm3(q * np.array([1.2, 0, 1.2]) + 0.3, 3, seed)
                 + 0.012 * R.fbm3(q * np.array([7, 0, 7]), 2, seed + 1)) * (1 - _puddles(q, seed)) \
            * smoothstep(0.25, 0.12, d[i])
    return d


def sea(p, seed, height=0.0):
    d = p[:, 1] - height
    i = np.where(d < 0.6)[0]
    if i.size:
        q = p[i]
        x, z = q[:, 0], q[:, 2]
        w = 0.12 * np.sin(x * 1.3 + z * 0.7) + 0.08 * np.sin(x * 2.9 - z * 1.7 + 1.0) \
            + 0.10 * R.fbm3(q * np.array([0.9, 0, 1.6]), 4, seed)
        crest = smoothstep(0.1, 0.25, w)
        d = d.copy()
        d[i] -= (w + 0.03 * crest * R.fbm3(q * 6, 2, seed + 1)) * smoothstep(0.6, 0.4, d[i])
    return d


def sky(seed, top, horizon, glow=None, glow_at=(0.3, 0.12), glow_size=60.0, clouds=0.6, stars=0.0):
    """Smoky sky: dark above, paler at the horizon, a hazy light source and
    drifting, uneven cloud; stars > 0 pricks it with that many stars."""
    top, horizon = np.asarray(top, float), np.asarray(horizon, float)

    def bg(rd):
        t = np.clip(rd[:, 1] * 3.2 + 0.15, 0, 1)[:, None]
        col = horizon * (1 - t) + top * t
        n = R.fbm3(rd * np.array([5, 9, 5]) + 3, 5, seed)
        col = col * (1 + clouds * n)[:, None]
        if stars:
            sp = smoothstep(0.93, 1.0, R.noise3(rd * 260, seed + 5) * 0.5 + 0.5) * (rd[:, 1] > 0.05)
            col = col + stars * sp[:, None] * np.clip(0.4 - 0.6 * n, 0, 1)[:, None]
        if glow is not None:
            d2 = (rd[:, 0] - glow_at[0]) ** 2 + (rd[:, 1] - glow_at[1]) ** 2
            col = col + np.asarray(glow, float) * (np.exp(-d2 * glow_size) * (1 + 0.6 * n))[:, None]
        return np.maximum(col, 0)
    return bg


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

class Kit:
    """Material slots a figure draws with."""

    def __init__(self, skin, cloth=None, gear=None, metal=None, eye=None, extra=None):
        self.skin, self.cloth, self.gear, self.metal, self.eye, self.extra = skin, cloth, gear, metal, eye, extra


def figure(p, k, seed, hunch=0.0, robe=False, head="hood", arms="rifle", stride=1.0, build=1.0,
           head_scale=1.0, legs="human", rough=0.0, fin=False):
    """A walking figure facing +Z. hunch bends the back forward (0..1);
    robe wraps it in a long tattered robe; head, arms and legs ("human" or
    the backward-jointed "goat") pick the variant; rough lumps and wrinkles
    bare skin; fin runs a spiny ridge down the back."""
    f = Field(len(p))
    h = hunch
    hip = np.array([0.0, 0.95, 0.0])
    neck = np.array([0.0, 1.47 - 0.12 * h, 0.03 + 0.30 * h])
    headc = np.array([0.0, 1.62 - 0.18 * h, 0.06 + 0.42 * h])
    sy, sz = 1.40 - 0.10 * h, 0.02 + 0.24 * h
    s = 0.13 * stride
    leg_skin = k.cloth if k.cloth is not None and not robe else k.skin
    if legs == "goat":
        # thick haunches, a knee forward, a hock back and a narrow hoof
        for side, sw in ((-1, s), (1, -s)):
            x = 0.11 * side
            pts = [(x, 0.92, -0.02), (x, 0.62, 0.16 + sw * 0.6), (x * 1.05, 0.30, -0.10 + sw * 0.8),
                   (x * 1.05, 0.05, 0.02 + sw)]
            f.add(R.sd_tube(p, pts, np.array([0.13, 0.085, 0.045, 0.035]) * build), leg_skin, 0.04)
            f.add(R.sd_ellipsoid(p, (x * 1.05, 0.035, 0.05 + sw), (0.04, 0.035, 0.06)),
                  k.gear if k.gear is not None else leg_skin, 0.01)
    else:
        for side, (kn, an) in ((-1, ((-0.10, 0.50, 0.10 + s * 0.4), (-0.10, 0.09, 0.05 + s))),
                               (1, ((0.10, 0.50, -0.03), (0.11, 0.10, -0.10 - s)))):
            hp = (0.095 * side, 0.93, 0.0)
            mid = (np.asarray(hp) + np.asarray(kn)) / 2 + (0, 0, 0.015)
            f.add(R.sd_tube(p, [hp, mid, kn, an], np.array([0.09, 0.078, 0.056, 0.042]) * build), leg_skin, 0.02)
            # the calf
            f.add(R.sd_ellipsoid(p, np.asarray(kn) * 0.6 + np.asarray(an) * 0.4 - (0, 0, 0.03),
                                 np.array([0.05, 0.11, 0.05]) * build), leg_skin, 0.03)
            f.add(R.sd_ellipsoid(p, (an[0], 0.045, an[2] + 0.07), (0.055, 0.045, 0.125)),
                  k.gear if k.gear is not None else leg_skin, 0.02)
    # torso: pelvis, belly and a chest that leans with the hunch
    chest = np.array([0.0, 1.24 - 0.04 * h, 0.03 + 0.14 * h])
    torso_mat = k.cloth if k.cloth is not None else k.skin
    f.add(R.sd_ellipsoid(p, hip + (0, 0.02, 0), (0.17 * build, 0.13, 0.12)), torso_mat, 0.04)
    f.add(R.sd_ellipsoid(p, chest, (0.20 * build, 0.25, 0.13 * build), R.rot_x(-28 * h)), torso_mat, 0.06)
    f.add(R.sd_capsule(p, chest + (0, 0.12, 0), neck, 0.06), k.skin, 0.03)
    # shoulders
    for side in (-1, 1):
        f.add(R.sd_sphere(p, (0.18 * side * build, sy, sz), 0.075 * build), torso_mat, 0.05)
    if fin:
        for j in range(7):
            t = j / 6
            b = chest * (1 - t) + hip * t + np.array([0, 0.08, -0.13 - 0.05 * (1 - t) * h])
            f.add(R.sd_round_cone(p, b, b + np.array([0, 0.05, -0.10]), 0.025, 0.004), k.skin, 0.02)
    _arms(f, p, k, arms, sy, sz, headc, build)
    if robe:
        _robe(f, p, k, seed, sy, sz, h)
    _head(f, p, k, head, headc, seed, head_scale)
    if rough:
        # lumpy, wrinkled hide on bare skin only (weapons stay straight)
        i = np.where((np.abs(f.d) < 0.05) & (f.m == k.skin))[0]
        if i.size:
            q = p[i]
            bumps = 0.6 * R.fbm3(q * 7, 3, seed + 21) + 0.4 * (R.ridged3(q * 22, 2, seed + 22) - 0.5)
            f.d[i] -= rough * bumps * fade(f.d[i], 0.05)
    return f


def _arms(f, p, k, arms, sy, sz, headc, build):
    arm_mat = k.cloth if k.cloth is not None else k.skin
    r0, r1, r2 = 0.058 * build, 0.048 * build, 0.04
    gear = k.gear if k.gear is not None else arm_mat
    metal = k.metal if k.metal is not None else gear
    if arms == "rifle":
        rs, ls = (0.19 * build, sy, sz), (-0.19 * build, sy, sz)
        rh = (0.10, sy - 0.43, sz + 0.20)
        lh = (-0.14, sy - 0.17, sz + 0.30)
        f.add(R.sd_tube(p, [rs, (0.23 * build, sy - 0.28, sz + 0.04), rh], [r0, r1, r2]), arm_mat, 0.03)
        f.add(R.sd_tube(p, [ls, (-0.25 * build, sy - 0.22, sz + 0.17), lh], [r0, r1, r2]), arm_mat, 0.03)
        for hand in (rh, lh):
            f.add(R.sd_sphere(p, hand, 0.045), k.skin, 0.01)
        butt = np.array([0.20, sy - 0.58, sz + 0.12])
        muzzle = np.array([-0.30, sy + 0.30, sz + 0.40])
        f.add(R.sd_round_cone(p, butt, butt + (muzzle - butt) * 0.42, 0.045, 0.03), gear)
        f.add(R.sd_capsule(p, butt + (muzzle - butt) * 0.4, muzzle, 0.014), metal)
        tip = muzzle + R.normalize(muzzle - butt) * 0.24
        f.add(R.sd_round_cone(p, muzzle, tip, 0.012, 0.002), metal)
    elif arms == "spear":
        rs, ls = (0.19 * build, sy, sz), (-0.19 * build, sy, sz)
        rh = (0.30, sy - 0.32, sz + 0.16)
        f.add(R.sd_tube(p, [rs, (0.30 * build, sy - 0.20, sz + 0.02), rh], [r0, r1, r2]), arm_mat, 0.03)
        f.add(R.sd_tube(p, [ls, (-0.24 * build, sy - 0.30, sz + 0.02), (-0.22, sy - 0.58, sz + 0.08)],
                        [r0, r1, r2]), arm_mat, 0.03)
        f.add(R.sd_sphere(p, rh, 0.045), k.skin, 0.01)
        base, top = np.array([0.31, 0.05, sz + 0.15]), np.array([0.33, 2.25, sz + 0.20])
        f.add(R.sd_capsule(p, base, top, 0.017), gear)
        # a trident head
        f.add(R.sd_capsule(p, top - (0.10, 0, 0), top + (0.10, 0, 0), 0.012), metal)
        for dx in (-0.10, 0.0, 0.10):
            f.add(R.sd_round_cone(p, top + (dx, 0, 0), top + (dx * 1.15, 0.26, 0.01), 0.012, 0.002), metal)
    elif arms == "shield":
        rs, ls = (0.19 * build, sy, sz), (-0.19 * build, sy, sz)
        rh = (0.30, sy - 0.30, sz + 0.12)
        f.add(R.sd_tube(p, [rs, (0.30 * build, sy - 0.20, sz + 0.02), rh], [r0, r1, r2]), arm_mat, 0.03)
        f.add(R.sd_tube(p, [ls, (-0.26 * build, sy - 0.25, sz + 0.12), (-0.18, sy - 0.32, sz + 0.28)],
                        [r0, r1, r2]), arm_mat, 0.03)
        base, top = np.array([0.31, 0.05, sz + 0.12]), np.array([0.32, 2.35, sz + 0.14])
        f.add(R.sd_capsule(p, base, top, 0.017), gear)
        f.add(R.sd_round_cone(p, top, top + (0, 0.30, 0), 0.035, 0.003), metal)
        # a tall, curved tower shield
        c = np.array([-0.14, sy - 0.46, sz + 0.36])
        q = p - c
        axis_z = -0.55
        rr = np.sqrt(q[:, 0] ** 2 + (q[:, 2] - axis_z) ** 2)
        shell = np.abs(rr + axis_z) - 0.022
        bound = sd_box(p, c + (0, 0, -0.06), (0.25, 0.50, 0.14), r=0.03)
        d = np.maximum(shell, bound)
        f.add(d, metal)
        # a boss and a faint ring of the sigil on its face
        front = c + (0, 0.06, 0.012)
        f.add(R.sd_sphere(p, front, 0.045), metal, 0.02)
        ring = np.abs(R.length((p - front) * np.array([1, 1, 0])) - 0.12) - 0.008
        f.add(np.maximum(ring, np.abs(p[:, 2] - front[2]) - 0.012), k.eye if k.eye is not None else metal)
    elif arms == "pipe":
        rs, ls = (0.19 * build, sy, sz), (-0.19 * build, sy, sz)
        mouth = headc + (0, -0.05, 0.13)
        end = mouth + (0.04, -0.42, 0.55)
        rh = mouth + (end - mouth) * 0.62
        lh = mouth + (end - mouth) * 0.30
        f.add(R.sd_tube(p, [rs, (0.24, sy - 0.25, sz + 0.08), rh], [r0, r1, r2]), arm_mat, 0.03)
        f.add(R.sd_tube(p, [ls, (-0.22, sy - 0.18, sz + 0.12), lh], [r0, r1, r2]), arm_mat, 0.03)
        f.add(R.sd_round_cone(p, mouth, end, 0.016, 0.03), gear)
        f.add(R.sd_sphere(p, end, 0.045), k.eye if k.eye is not None else gear, 0.01)
    elif arms == "claws":
        for side in (-1, 1):
            sh = (0.19 * side * build, sy, sz)
            el = (0.30 * side * build, sy - 0.30, sz + 0.12)
            ha = (0.27 * side * build, sy - 0.62, sz + 0.30)
            f.add(R.sd_tube(p, [sh, el, ha], [r0 * 1.2, r1 * 1.1, r2]), arm_mat, 0.04)
            for j in (-1, 0, 1):
                tip = (ha[0] + 0.035 * j, ha[1] - 0.16, ha[2] + 0.06 + 0.02 * abs(j))
                f.add(R.sd_round_cone(p, ha, tip, 0.016, 0.003), k.gear if k.gear is not None else arm_mat, 0.01)
    elif arms == "crossed":
        # forearms crossed on the chest, a crook in the right hand
        for side in (-1, 1):
            sh = (0.19 * side * build, sy, sz)
            el = (0.25 * side * build, sy - 0.30, sz + 0.03)
            ha = (-0.09 * side, sy - 0.14, sz + 0.20)
            f.add(R.sd_tube(p, [sh, el, ha], [r0, r1, r2]), arm_mat, 0.03)
            f.add(R.sd_sphere(p, ha, 0.042), k.skin, 0.01)
        hand = np.array([-0.09, sy - 0.14, sz + 0.20])
        top = hand + np.array([0.30, 0.55, 0.02])
        f.add(R.sd_capsule(p, hand - (top - hand) * 0.25, top, 0.016), metal)
        hook = [top, top + (0.04, 0.09, 0.0), top + (0.0, 0.15, 0.0), top + (-0.06, 0.11, 0.0)]
        f.add(R.sd_tube(p, hook, [0.016, 0.016, 0.016, 0.014]), metal)
    elif arms == "tentacle":
        # one arm is a rifle-hand, the other a writhing tentacle
        rs, ls = (0.19 * build, sy, sz), (-0.19 * build, sy, sz)
        f.add(R.sd_tube(p, [rs, (0.24 * build, sy - 0.30, sz + 0.10), (0.20, sy - 0.55, sz + 0.30)],
                        [r0, r1, r2]), arm_mat, 0.03)
        pts = [ls, (-0.32, sy - 0.05, sz + 0.18), (-0.45, sy + 0.12, sz + 0.38), (-0.40, sy + 0.32, sz + 0.55),
               (-0.30, sy + 0.38, sz + 0.62)]
        f.add(R.sd_tube(p, pts, [0.06, 0.05, 0.035, 0.02, 0.008]), k.extra if k.extra is not None else k.skin,
              0.04)
        f.add(R.sd_ellipsoid(p, (0.20, sy - 0.62, sz + 0.34), (0.06, 0.08, 0.05)), k.skin, 0.03)

    elif arms == "clap":
        # gloved hands raised together before the chin, applauding
        hands = np.array([0.0, sy - 0.04, sz + 0.34])
        glove = k.extra if k.extra is not None else k.skin
        for side in (-1, 1):
            sh = (0.19 * side * build, sy, sz)
            el = (0.27 * side * build, sy - 0.30, sz + 0.12)
            ha = hands + (0.028 * side, 0, 0)
            f.add(R.sd_tube(p, [sh, el, ha], [r0, r1, r2]), arm_mat, 0.03)
            f.add(R.sd_ellipsoid(p, ha + (0, 0.03, 0), (0.024, 0.065, 0.045)), glove, 0.01)
    elif arms == "hymnal":
        # a hymnal held open in both hands
        book = np.array([0.0, sy - 0.30, sz + 0.30])
        for side in (-1, 1):
            sh = (0.19 * side * build, sy, sz)
            el = (0.25 * side * build, sy - 0.33, sz + 0.06)
            ha = book + (0.10 * side, -0.01, 0.0)
            f.add(R.sd_tube(p, [sh, el, ha], [r0, r1, r2]), arm_mat, 0.03)
            f.add(R.sd_sphere(p, ha, 0.04), k.skin, 0.01)
        f.add(sd_box(p, book, (0.10, 0.012, 0.075), R.rot_x(-35)), k.extra if k.extra is not None else gear)
    elif arms == "limp":
        # arms hanging dead at the sides
        for side in (-1, 1):
            sh = (0.19 * side * build, sy, sz)
            el = (0.22 * side * build, sy - 0.32, sz + 0.05)
            ha = np.array([0.20 * side * build, sy - 0.66, sz + 0.12])
            f.add(R.sd_tube(p, [sh, el, ha], [r0, r1, r2]), arm_mat, 0.03)
            f.add(R.sd_ellipsoid(p, ha + (0, -0.04, 0), (0.035, 0.07, 0.04)), k.skin, 0.01)
    elif arms == "reach":
        # long arms stretched out ahead, ending in long, thin fingers
        for side in (-1, 1):
            sh = (0.19 * side * build, sy, sz)
            el = (0.26 * side * build, sy - 0.10, sz + 0.34)
            ha = (0.20 * side * build, sy - 0.04 + 0.06 * side, sz + 0.72)
            f.add(R.sd_tube(p, [sh, el, ha], [r0, r1, r2 * 0.8]), arm_mat, 0.03)
            for j in (-1.5, -0.5, 0.5, 1.5):
                tip = (ha[0] + 0.035 * j, ha[1] - 0.08 - 0.03 * abs(j), ha[2] + 0.24 - 0.04 * abs(j))
                f.add(R.sd_round_cone(p, ha, tip, 0.013, 0.004), k.skin, 0.01)

def _robe(f, p, k, seed, sy, sz, h):
    top = np.array([0.0, sy + 0.02, sz * 0.8])
    bot = np.array([0.0, 0.06, -0.05])
    d = R.sd_round_cone(p, bot, top, 0.36, 0.20)
    # folds running down the cloth, deeper toward the hem
    i = near(d, 0.06)
    if i.size:
        q = p[i]
        ang = np.arctan2(q[:, 0], q[:, 2] + 0.05)
        folds = np.sin(ang * 7 + 1.5 * R.fbm3(q * 3, 2, seed)) * 0.5 + 0.5
        d[i] -= (0.03 * folds + 0.012 * R.fbm3(q * 14, 3, seed + 3)) * (1 - np.clip(q[:, 1] / (sy + 0.1), 0, 1)) \
            * fade(d[i], 0.06)
    # a ragged, torn hem
    hem = 0.10 + 0.10 * np.clip(R.fbm3(p * np.array([9, 1, 9]), 3, seed + 4) + 0.2, 0, 1)
    d = np.maximum(d, -(p[:, 1] - hem))
    # open at the neck
    d = np.maximum(d, p[:, 1] - (sy + 0.06))
    f.add(d, k.cloth, 0.05)
    # a cape of cloth on the shoulders
    c = np.array([0.0, sy - 0.03, sz - 0.02])
    dc = R.sd_ellipsoid(p, c, (0.29, 0.20, 0.20))
    dc = np.maximum(dc, -R.sd_ellipsoid(p, c - (0, 0.05, 0), (0.25, 0.20, 0.16)))
    dc = np.maximum(dc, -(p[:, 1] - (sy - 0.20 - 0.06 * R.fbm3(p * 8, 2, seed + 5))))
    f.add(dc, k.cloth, 0.03)


def _head(f, p, k, head, c, seed, s):
    c = np.asarray(c, float)
    if head == "hood":
        # a deep hood over a pale mask
        hood_c = c + (0, 0.03, -0.02)
        d = R.sd_ellipsoid(p, hood_c, np.array([0.145, 0.17, 0.16]) * s)
        d = R.smin(d, R.sd_round_cone(p, hood_c + (0, 0.02, -0.08), hood_c + (0, 0.20, -0.20), 0.08, 0.01), 0.05)
        d = np.maximum(d, -R.sd_ellipsoid(p, c + (0, -0.01, 0.16), np.array([0.09, 0.12, 0.12]) * s))
        f.add(d, k.cloth, 0.03)
        f.add(R.sd_ellipsoid(p, c + (0, -0.02, 0.03), np.array([0.08, 0.10, 0.09]) * s),
              k.metal if k.metal is not None else k.skin)
    elif head == "faceless":
        hood_c = c + (0, 0.03, -0.02)
        d = R.sd_ellipsoid(p, hood_c, np.array([0.15, 0.18, 0.16]) * s)
        d = np.maximum(d, -R.sd_ellipsoid(p, c + (0, -0.01, 0.17), np.array([0.095, 0.12, 0.12]) * s))
        f.add(d, k.cloth, 0.03)
        # a smooth blank oval where the face should be
        f.add(R.sd_ellipsoid(p, c + (0, -0.02, 0.05), np.array([0.085, 0.115, 0.085]) * s), k.skin)
    elif head == "fish":
        # a long, narrow, sloping fish head with a heavy underslung jaw,
        # thrust forward from the shoulders with almost no neck
        hc = c + (0, -0.04, 0.08)
        d = R.sd_ellipsoid(p, hc, np.array([0.10, 0.11, 0.20]) * s, R.rot_x(18))
        jaw = R.sd_ellipsoid(p, hc + np.array([0, -0.08, 0.03]) * s, np.array([0.11, 0.06, 0.19]) * s,
                             R.rot_x(-6))
        d = R.smin(d, jaw, 0.04)
        mouth = R.sd_ellipsoid(p, hc + np.array([0, -0.05, 0.13]) * s, np.array([0.11, 0.010, 0.12]) * s)
        d = np.maximum(d, -mouth)
        # gill slits along the throat
        for j in range(3):
            g = R.sd_ellipsoid(p, hc + np.array([0.095, -0.06, -0.06 - 0.035 * j]) * s, (0.02, 0.05, 0.006))
            g2 = R.sd_ellipsoid(p, hc + np.array([-0.095, -0.06, -0.06 - 0.035 * j]) * s, (0.02, 0.05, 0.006))
            d = np.maximum(d, -np.minimum(g, g2))
        # a ridge of fin over the crown
        d = R.smin(d, R.sd_ellipsoid(p, hc + np.array([0, 0.10, -0.06]) * s, np.array([0.012, 0.06, 0.16]) * s),
                   0.02)
        f.add(d, k.skin, 0.05)
        for side in (-1, 1):
            f.add(R.sd_sphere(p, hc + np.array([0.085 * side, 0.03, 0.07]) * s, 0.024 * s), k.eye)
    elif head == "helmet":
        f.add(R.sd_sphere(p, c, 0.10 * s), k.skin, 0.02)
        d = R.sd_ellipsoid(p, c + (0, 0.03, 0), np.array([0.13, 0.13, 0.14]) * s)
        d = np.maximum(d, -(p[:, 1] - (c[1] - 0.05)))
        d = R.smin(d, sd_box(p, c + (0, 0.06, 0.12), (0.12, 0.025, 0.03)), 0.02)
        d = R.smin(d, R.sd_ellipsoid(p, c + (0, 0.17, -0.02), (0.02, 0.07, 0.15)), 0.03)
        f.add(d, k.metal)
        # a narrow visor slit glowing faintly
        f.add(sd_box(p, c + (0, 0.0, 0.10), (0.07, 0.008, 0.02)), k.eye)
    elif head == "horned":
        hc = c + (0, 0.0, 0.05)
        d = R.sd_ellipsoid(p, hc, np.array([0.09, 0.11, 0.13]) * s)
        d = R.smin(d, R.sd_ellipsoid(p, hc + (0, -0.06, 0.10), np.array([0.05, 0.05, 0.08]) * s), 0.04)
        f.add(d, k.skin, 0.03)
        for side in (-1, 1):
            pts = [hc + (0.05 * side, 0.08, 0.0), hc + (0.12 * side, 0.17, -0.07), hc + (0.20 * side, 0.12, -0.17),
                   hc + (0.22 * side, -0.02, -0.12), hc + (0.17 * side, -0.07, -0.02),
                   hc + (0.15 * side, -0.02, 0.05)]
            f.add(R.sd_tube(p, pts, [0.045, 0.042, 0.035, 0.026, 0.016, 0.006]), k.gear, 0.015)
            f.add(R.sd_sphere(p, hc + np.array([0.05 * side, 0.02, 0.11]) * s, 0.016 * s), k.eye)
        # long goat ears
        for side in (-1, 1):
            f.add(R.sd_ellipsoid(p, hc + (0.12 * side, 0.02, -0.02), (0.07, 0.02, 0.03), R.rot_z(-25 * side)),
                  k.skin, 0.02)
    elif head == "mutant":
        hc = c + (0.03, 0.0, 0.03)
        d = R.sd_ellipsoid(p, hc, np.array([0.12, 0.13, 0.13]) * s)
        d = R.smin(d, R.sd_sphere(p, hc + (-0.08, 0.07, -0.02), 0.08 * s), 0.05)
        d = displace(d, p, 0.03, 22, seed + 9, 0.05)
        f.add(d, k.skin, 0.04)
        f.add(R.sd_sphere(p, hc + np.array([0.05, 0.01, 0.11]) * s, 0.022 * s), k.eye)
        f.add(R.sd_sphere(p, hc + np.array([-0.04, 0.05, 0.11]) * s, 0.016 * s), k.eye)
    elif head == "pharaoh":
        # a blank black head under a striped nemes, lappets falling to the chest
        f.add(R.sd_ellipsoid(p, c, np.array([0.095, 0.12, 0.10]) * s), k.skin, 0.02)
        d = R.sd_ellipsoid(p, c + np.array([0, 0.04, -0.015]) * s, np.array([0.125, 0.11, 0.125]) * s)
        d = np.maximum(d, -(p[:, 1] - (c[1] - 0.005)) - 0.0)
        d = np.maximum(d, -R.sd_ellipsoid(p, c + np.array([0, -0.04, 0.10]) * s, np.array([0.10, 0.14, 0.08]) * s))
        flare = R.sd_ellipsoid(p, c + np.array([0, -0.10, -0.07]) * s, np.array([0.21, 0.20, 0.08]) * s)
        d = R.smin(d, flare, 0.04)
        for side in (-1, 1):
            lap = R.sd_round_cone(p, c + np.array([0.12 * side, -0.02, 0.02]) * s,
                                  c + np.array([0.15 * side, -0.32, 0.07]) * s, 0.03 * s, 0.06 * s)
            d = R.smin(d, np.maximum(lap, np.abs(p[:, 2] - (c[2] + 0.05 * s)) - 0.025 * s), 0.02)
        f.add(d, k.gear, 0.02)
        # the rearing cobra on the brow
        f.add(R.sd_tube(p, [c + np.array([0, 0.10, 0.10]) * s, c + np.array([0, 0.16, 0.12]) * s,
                            c + np.array([0, 0.19, 0.10]) * s], np.array([0.015, 0.012, 0.018]) * s), k.metal, 0.01)
    elif head == "octopus":
        hc = c + (0, 0.05, 0.02)
        d = R.sd_ellipsoid(p, hc + (0, 0.06, -0.05), np.array([0.15, 0.20, 0.17]) * s)
        f.add(d, k.skin, 0.05)
        for j in range(6):
            a = (j - 2.5) * 0.11
            pts = [hc + (a * 0.9, -0.04, 0.10), hc + (a * 1.2, -0.20, 0.13 + 0.03 * math.sin(j)),
                   hc + (a * 1.3 + 0.03 * math.cos(j * 2), -0.36, 0.10)]
            f.add(R.sd_tube(p, pts, np.array([0.035, 0.022, 0.007]) * s), k.skin, 0.03)
        for side in (-1, 1):
            f.add(R.sd_sphere(p, hc + np.array([0.09 * side, 0.03, 0.12]) * s, 0.025 * s), k.eye)

    elif head == "bun":
        # a pale face, the hair pinned up in a heavy bun
        f.add(R.sd_ellipsoid(p, c + (0, -0.01, 0.02), np.array([0.08, 0.105, 0.09]) * s), k.skin, 0.02)
        hair = R.sd_ellipsoid(p, c + np.array([0, 0.03, -0.01]) * s, np.array([0.095, 0.10, 0.10]) * s)
        hair = np.maximum(hair, -R.sd_ellipsoid(p, c + np.array([0, -0.04, 0.09]) * s, np.array([0.08, 0.10, 0.07]) * s))
        hair = R.smin(hair, R.sd_sphere(p, c + np.array([0, 0.11, -0.07]) * s, 0.06 * s), 0.03)
        f.add(hair, k.gear, 0.01)
        for side in (-1, 1):
            f.add(R.sd_sphere(p, c + np.array([0.032 * side, 0.0, 0.098]) * s, 0.016 * s), k.eye)
    elif head == "lidless":
        # a gaunt bare face under a steel helmet, the eyes wide, bulging and lit
        f.add(R.sd_ellipsoid(p, c + (0, -0.01, 0.01), np.array([0.085, 0.11, 0.095]) * s), k.skin, 0.02)
        d = R.sd_ellipsoid(p, c + np.array([0, 0.05, 0]) * s, np.array([0.135, 0.11, 0.145]) * s)
        d = np.maximum(d, -(p[:, 1] - (c[1] + 0.02 * s)))
        d = R.smin(d, R.sd_ellipsoid(p, c + np.array([0, 0.03, 0]) * s, np.array([0.165, 0.022, 0.175]) * s), 0.02)
        f.add(d, k.metal)
        for side in (-1, 1):
            f.add(R.sd_sphere(p, c + np.array([0.036 * side, -0.012, 0.094]) * s, 0.027 * s), k.eye)
    elif head == "tophat":
        # a pale face under a tall silk hat
        f.add(R.sd_ellipsoid(p, c + (0, -0.01, 0.02), np.array([0.085, 0.11, 0.095]) * s), k.skin, 0.02)
        crown = R.sd_round_cone(p, c + np.array([0, 0.06, -0.005]) * s, c + np.array([0, 0.30, -0.01]) * s,
                                0.082 * s, 0.09 * s)
        crown = np.maximum(crown, p[:, 1] - (c[1] + 0.31 * s))
        brim = R.sd_ellipsoid(p, c + np.array([0, 0.075, -0.005]) * s, np.array([0.15, 0.014, 0.14]) * s)
        f.add(np.minimum(crown, brim), k.gear)
        for side in (-1, 1):
            f.add(R.sd_sphere(p, c + np.array([0.033 * side, 0.0, 0.103]) * s, 0.017 * s), k.eye)
    elif head == "singer":
        # a deep hood, the pale face inside it tipped up and the mouth gaping wide
        hood_c = c + (0, 0.03, -0.03)
        d = R.sd_ellipsoid(p, hood_c, np.array([0.15, 0.18, 0.16]) * s)
        d = R.smin(d, R.sd_round_cone(p, hood_c + (0, 0.02, -0.08), hood_c + (0, 0.16, -0.20), 0.08, 0.01), 0.05)
        d = np.maximum(d, -R.sd_ellipsoid(p, c + (0, -0.01, 0.16), np.array([0.10, 0.13, 0.12]) * s))
        f.add(d, k.cloth, 0.03)
        tilt = R.rot_x(-22)
        hc = c + np.array([0, -0.01, 0.04]) * s
        d = R.sd_ellipsoid(p, hc, np.array([0.082, 0.112, 0.09]) * s, tilt)
        d = np.maximum(d, -R.sd_ellipsoid(p, hc + tilt @ (np.array([0, -0.05, 0.09]) * s),
                                          np.array([0.032, 0.052, 0.04]) * s, tilt))
        for side in (-1, 1):
            d = np.maximum(d, -R.sd_sphere(p, hc + tilt @ (np.array([0.033 * side, 0.025, 0.088]) * s), 0.018 * s))
        f.add(d, k.skin, 0.02)
    elif head == "mask":
        # a deep hood, and a pale mask too big for the face that has grown into it
        hood_c = c + (0, 0.03, -0.03)
        d = R.sd_ellipsoid(p, hood_c, np.array([0.15, 0.18, 0.16]) * s)
        d = np.maximum(d, -R.sd_ellipsoid(p, c + (0, -0.01, 0.15), np.array([0.10, 0.13, 0.12]) * s))
        f.add(d, k.cloth, 0.03)
        m = R.sd_ellipsoid(p, c + np.array([0, -0.01, 0.075]) * s, np.array([0.105, 0.14, 0.07]) * s)
        for side in (-1, 1):
            m = np.maximum(m, -R.sd_ellipsoid(p, c + np.array([0.042 * side, 0.025, 0.14]) * s,
                                              np.array([0.026, 0.007, 0.03]) * s))
        smile = [c + np.array([-0.055, -0.045, 0.128]) * s, c + np.array([0.0, -0.075, 0.142]) * s,
                 c + np.array([0.055, -0.045, 0.128]) * s]
        m = np.maximum(m, -R.sd_tube(p, smile, np.array([0.006, 0.006, 0.006]) * s))
        f.add(m, k.metal)
    elif head == "wrapped":
        # no face at all: a lump of rags wound round and round, a little too tall
        d = R.sd_ellipsoid(p, c + np.array([0, 0.05, 0.0]) * s, np.array([0.11, 0.18, 0.12]) * s)
        i = near(d, 0.05)
        if i.size:
            q = p[i]
            bands = np.sin(q[:, 1] * 40 + 3.0 * R.fbm3(q * 6, 2, seed + 7)) * 0.5 + 0.5
            d[i] -= 0.014 * bands * fade(d[i], 0.05)
        f.add(d, k.cloth, 0.05)
    elif head == "drowned":
        # a swollen, hairless head hanging forward, the jaw fallen open
        hc = c + np.array([0, -0.03, 0.04]) * s
        d = R.sd_ellipsoid(p, hc, np.array([0.115, 0.125, 0.12]) * s)
        d = R.smin(d, R.sd_ellipsoid(p, hc + np.array([0, -0.11, 0.05]) * s, np.array([0.085, 0.065, 0.075]) * s),
                   0.04)
        d = np.maximum(d, -R.sd_ellipsoid(p, hc + np.array([0, -0.085, 0.115]) * s,
                                          np.array([0.04, 0.04, 0.04]) * s))
        d = displace(d, p, 0.012, 18, seed + 9, 0.04)
        f.add(d, k.skin, 0.04)
        for side in (-1, 1):
            f.add(R.sd_sphere(p, hc + np.array([0.042 * side, 0.015, 0.105]) * s, 0.019 * s), k.eye)

# ---------------------------------------------------------------------------
# Finishing
# ---------------------------------------------------------------------------

def finish(out, seed, tint=(0.0, 0.0, 0.0), saturation=0.45, exposure=0.85, smoke_col=(0.45, 0.42, 0.38),
           smoke_amt=0.3, smoke_src=(0.3, 0.15), border=(40, 34, 27), glow=0.0, contrast=1.3):
    """Grade a render like a worn war photograph and reduce it to icon size."""
    img = R.tonemap(out["rgb"], exposure)
    img = R.smoke(img, out["depth"], seed, smoke_amt, smoke_col, smoke_src, 3.0, far=(4.0, 12.0))
    img = R.grade(img, saturation=saturation, shadows=tint, highlights=(0.02, 0.012, -0.01), contrast=contrast,
                  black=0.05)
    if glow:
        img = R.halation(img, 0.65, 1.5 * SCALE, glow)
    img = R.vignette(img, 0.7, 1.6)
    W, H = ICON_SIZE
    pil = R.to_image(img).convert("RGB").resize((W, H), Image.LANCZOS)
    pil = pil.filter(ImageFilter.UnsharpMask(radius=0.8, percent=60, threshold=1))
    a = np.asarray(pil).astype(float) / 255
    rng = np.random.default_rng(seed)
    # film grain, a few scratches and specks of dust at the final size
    a = a + rng.normal(0, 0.028, (H, W, 1)) + rng.normal(0, 0.008, (H, W, 3))
    x = rng.integers(4, W - 4)
    y0, y1 = sorted(rng.integers(0, H, 2))
    a[y0:y1, x] = a[y0:y1, x] * 0.8 + 0.2 * np.array([0.75, 0.72, 0.65])
    for _ in range(2):
        y, x = rng.integers(1, H - 1), rng.integers(1, W - 1)
        a[y, x] = a[y, x] * 0.55 + 0.45 * (0.7 if rng.random() < 0.5 else 0.02)
    b = np.asarray(border, float) / 255
    a[0, :], a[-1, :], a[:, 0], a[:, -1] = b, b, b, b
    return R.to_image(np.clip(a, 0, 1))


def render_icon(scene, mats, cam, lights, seed, bg, figure_mats, ambient=(0.03, 0.03, 0.03), rim=None,
                fog=None, ss=2, max_dist=None, **finish_kw):
    W, H = ICON_SIZE
    if max_dist is None:
        max_dist = max(150.0, np.linalg.norm(cam.pos - cam.target) * 3.0)
    out = R.render(scene, mats, cam, lights, (W * SCALE, H * SCALE), ss=ss, background=bg, ambient=ambient,
                   rim=rim, fog=fog, max_dist=max_dist, ao_scale=0.12, shadow_dist=6.0, coverage=figure_mats,
                   shadow_bias=(0.006, 0.03))
    return finish(out, seed, **finish_kw), out["coverage"]


# ---------------------------------------------------------------------------
# Scenes
# ---------------------------------------------------------------------------

def _squad(p, placements, fn, center=1.15, radius=1.8, pad=0.12):
    """Union of figures fn(local points) at (pos, yaw, scale) placements,
    each only evaluated inside its bounding sphere (center metres above its
    feet; the figure, spear tips included, stays pad inside it)."""
    f = Field(len(p))
    for pos, yaw, sc in placements:
        c = np.asarray(pos, float) + (0, center * sc, 0)
        f.add_group(p, c, radius * sc, lambda q, pos=pos, yaw=yaw, sc=sc: scaled(fn, q, pos, yaw, sc),
                     pad=pad * sc)
    return f


def _infantry_icon(seed, kit_mats, fig_fn, placements, sky_kw, key_col, key_dir, back_col=None,
                   back_dir=(-0.35, 0.35, -1.0), cam_pos=(0.55, 1.0, 6.6), cam_target=(0.0, 0.88, 0.0), fov=21.0,
                   ground_fn=None, ground_mat=None, fog_col=None, fog_density=0.07, rim=None, env=(),
                   key_power=0.9, back_power=3.2, squad_kw=None, **finish_kw):
    """A squad of figures on mud under a smoky sky: a low key light, a strong
    light behind them that rims their silhouettes, and haze in the distance.
    env: extra scenery as (distance fn, Material) pairs, kept out of the
    figures' silhouette."""
    gm = ground_mat or Material((0.06, 0.05, 0.04), tex=mud(seed), tex_mode="replace", spec=0.3, gloss=60,
                                spec_tex=mud_spec(seed))
    mats = [gm] + list(kit_mats) + [m for _, m in env]
    figure_mats = list(range(1, 1 + len(kit_mats)))
    ground_fn = ground_fn or (lambda q: ground(q, seed))

    def scene(p):
        f = _squad(p, placements, fig_fn, **(squad_kw or {}))
        for j, (fn, _) in enumerate(env):
            f.add(fn(p), 1 + len(kit_mats) + j)
        f.add(ground_fn(p), 0)
        return f

    bg = sky(seed, **sky_kw)
    lights = [Light(key_col, key_power, direction=key_dir, softness=10),
              Light(back_col if back_col is not None else key_col, back_power, direction=back_dir, softness=14),
              Light((0.30, 0.33, 0.40), 0.15, direction=(0.4, 0.5, 0.8), shadow=False)]
    fog_col = fog_col if fog_col is not None else np.asarray(sky_kw["horizon"]) * 0.85
    return render_icon(scene, mats, Camera(cam_pos, cam_target, fov), lights, seed, bg, figure_mats,
                       ambient=(0.035, 0.035, 0.04), rim=rim or ((0.28, 0.24, 0.18), 3.2),
                       fog=(fog_col, fog_density, 6.5), **finish_kw)


def glow_cracks(color, seed, freq=9.0, lo=0.86, hi=0.95):
    """Emission along a web of fissures, for flesh lit from inside."""
    color = np.asarray(color, float)

    def emit(p, n):
        return color * smoothstep(lo, hi, R.ridged3(p * freq, 3, seed))[:, None]
    return emit


def ruins(seed, z=-9.0):
    """Broken walls and a leaning chimney far behind, lost in the haze."""
    def fn(p):
        d = sd_box(p, (-3.2, 1.1, z), (1.6, 1.1, 0.25))
        d = np.minimum(d, sd_box(p, (2.8, 1.6, z - 2.0), (1.0, 1.6, 0.25)))
        d = np.minimum(d, sd_box(p, (0.9, 2.6, z - 4.0), (0.25, 2.6, 0.25), R.rot_z(6)))
        # broken tops
        d = np.maximum(d, p[:, 1] - (1.6 + 1.6 * R.fbm3(p * np.array([0.9, 0, 0.5]), 2, seed)
                                     + 2.2 * smoothstep(0.6, 1.1, np.abs(p[:, 0] - 0.9) < 0.4)))
        return d
    return fn


def dead_trees(seed, spots):
    """Bare, splintered trunks standing in the haze."""
    def fn(p):
        d = np.full(len(p), 1e9)
        for j, (x, z, hgt) in enumerate(spots):
            lean = 0.15 * math.sin(j * 2.3)
            d = np.minimum(d, R.sd_round_cone(p, (x, -0.2, z), (x + lean, hgt, z), 0.22, 0.05))
            d = np.minimum(d, R.sd_round_cone(p, (x + lean * 0.6, hgt * 0.6, z), (x + 0.8 * (1 if j % 2 else -1),
                                                                                    hgt * 0.85, z + 0.2), 0.07, 0.02))
        return d
    return fn


def deep_one_brood():
    seed = 101
    k = Kit(skin=1, gear=2, metal=3, eye=4)
    mats = [
        Material((0.10, 0.13, 0.10), tex=scaly((0.10, 0.13, 0.10), seed, belly=(0.20, 0.21, 0.15)),
                 tex_mode="replace", wrap=0.25, spec=0.9, gloss=60),                       # 1 wet scaled hide
        Material((0.06, 0.05, 0.04), tex=mottled((0.06, 0.05, 0.04), seed + 1), tex_mode="replace", spec=0.2),
        Material((0.18, 0.22, 0.15), tex=mottled((0.18, 0.22, 0.15), seed + 2, 10, 0.4, 0.4), tex_mode="replace",
                 spec=0.6, gloss=30),                                                        # 3 verdigris bronze
        Material((0.25, 0.22, 0.08), emit=(0.30, 0.26, 0.08), spec=1.5, gloss=90),        # 4 dull eyes
    ]
    water = Material((0.012, 0.018, 0.017), tex=mottled((0.012, 0.018, 0.017), seed + 3, 2, 0.3, 0.0),
                     tex_mode="replace", spec=0.5, gloss=40)

    def fig(q):
        return figure(q, k, seed, hunch=0.6, head="fish", arms="spear", stride=0.8, build=1.12, rough=0.018,
                      fin=True)

    placements = [((0.20, 0, 0.6), -14, 1.0), ((-1.05, 0, -1.0), 10, 0.97), ((1.30, 0, -2.4), -24, 1.0)]
    return _infantry_icon(seed, mats, fig, placements,
                          dict(top=(0.010, 0.016, 0.016), horizon=(0.13, 0.19, 0.17), glow=(0.5, 0.75, 0.65),
                               glow_at=(0.15, 0.10), glow_size=30.0, clouds=0.8),
                          (0.75, 0.90, 0.85), (0.8, 0.45, 0.4), back_col=(0.65, 0.95, 0.85),
                          env=[(lambda q: sea(q, seed, 0.12), water)], cam_target=(0.0, 0.95, 0.0),
                          tint=(-0.01, 0.012, 0.01), smoke_col=(0.30, 0.38, 0.35), smoke_src=(0.6, 0.3))


def faceless_cult():
    seed = 201
    k = Kit(skin=1, cloth=2, gear=3, metal=1, eye=4)
    mats = [
        Material((0.40, 0.38, 0.40), tex=mottled((0.40, 0.38, 0.40), seed, 4, 0.08, 0.1), tex_mode="replace",
                 wrap=0.4, spec=0.6, gloss=50, sheen=0.3),                                  # 1 blank faces
        Material((0.035, 0.028, 0.040), tex=mottled((0.035, 0.028, 0.040), seed + 1, grime=0.3),
                 tex_mode="replace", wrap=0.3, spec=0.05, gloss=8, sheen=0.6),              # 2 black robes
        Material((0.06, 0.045, 0.035), tex=mottled((0.06, 0.045, 0.035), seed + 2), tex_mode="replace", spec=0.2),
        Material((0.0, 0.0, 0.0)),
    ]
    stone = Material((0.10, 0.09, 0.09), tex=mottled((0.10, 0.09, 0.09), seed + 3, 1.5, 0.4, 0.3),
                     tex_mode="replace")

    def fig(q):
        return figure(q, k, seed, hunch=0.05, robe=True, head="faceless", arms="rifle", stride=0.7)

    placements = [((0.25, 0, 0.6), -10, 1.02), ((-1.0, 0, -1.3), -6, 1.0), ((1.25, 0, -2.6), -18, 1.0)]
    return _infantry_icon(seed, mats, fig, placements,
                          dict(top=(0.012, 0.008, 0.016), horizon=(0.22, 0.09, 0.07), glow=(1.3, 0.45, 0.18),
                               glow_at=(-0.25, 0.03), glow_size=40.0),
                          (0.85, 0.65, 0.75), (0.9, 0.4, 0.3), back_col=(1.0, 0.45, 0.25),
                          env=[(ruins(seed), stone)], tint=(0.012, -0.004, 0.02),
                          smoke_col=(0.30, 0.18, 0.22), smoke_src=(0.3, 0.45))


def thousand_young():
    seed = 401
    k = Kit(skin=1, gear=2, eye=3)
    mats = [
        Material((0.05, 0.04, 0.035), tex=mottled((0.05, 0.04, 0.035), seed, 18, 0.5, 0.2), tex_mode="replace",
                 wrap=0.3, spec=0.3, gloss=20, sheen=0.8),                                  # 1 matted black hide
        Material((0.30, 0.26, 0.20), tex=mottled((0.30, 0.26, 0.20), seed + 1, 20, 0.3, 0.3),
                 tex_mode="replace", spec=0.4, gloss=30),                                   # 2 horn and claw
        Material((0.0, 0.0, 0.0), emit=(1.6, 0.18, 0.06)),                                  # 3 eyes
    ]
    bark = Material((0.05, 0.045, 0.04), tex=mottled((0.05, 0.045, 0.04), seed + 2, 3, 0.4, 0.3),
                    tex_mode="replace")

    def fig(q):
        return figure(q, k, seed, hunch=0.7, head="horned", arms="claws", stride=1.2, build=1.05, legs="goat",
                      rough=0.03)

    rng = np.random.default_rng(seed)
    placements = [((0.15, 0, 0.9), -12, 0.78), ((-0.95, 0, 0.1), 14, 0.72), ((0.95, 0, -0.4), -26, 0.74),
                  ((-0.30, 0, -1.3), 4, 0.70), ((-1.70, 0, -2.0), 20, 0.72), ((1.75, 0, -2.3), -30, 0.70),
                  ((0.45, 0, -3.2), -8, 0.72)]
    trees = dead_trees(seed, [(-2.6, -4.0, 5.0), (-0.9, -6.5, 6.0), (2.3, -5.0, 5.5), (3.6, -8.0, 6.0),
                              (-4.0, -9.0, 6.0)])
    return _infantry_icon(seed, mats, fig, placements,
                          dict(top=(0.008, 0.010, 0.006), horizon=(0.12, 0.13, 0.08), glow=(0.7, 0.55, 0.30),
                               glow_at=(0.05, 0.06), glow_size=45.0),
                          (0.75, 0.70, 0.55), (0.8, 0.4, 0.4), back_col=(0.85, 0.70, 0.45),
                          env=[(trees, bark)], squad_kw=dict(center=0.9, radius=1.35, pad=0.08),
                          tint=(0.004, 0.008, -0.006), smoke_col=(0.25, 0.26, 0.20), smoke_src=(0.5, 0.4))


def gate_wardens():
    seed = 501
    k = Kit(skin=1, cloth=2, gear=3, metal=4, eye=5)
    mats = [
        Material((0.25, 0.22, 0.20), tex=mottled((0.25, 0.22, 0.20), seed), tex_mode="replace", wrap=0.3),
        Material((0.06, 0.07, 0.09), tex=mottled((0.06, 0.07, 0.09), seed + 1, grime=0.5), tex_mode="replace",
                 wrap=0.3, spec=0.05, gloss=8, sheen=0.4),                                  # 2 slate cloaks
        Material((0.07, 0.055, 0.04), tex=mottled((0.07, 0.055, 0.04), seed + 2), tex_mode="replace", spec=0.2),
        Material((0.22, 0.24, 0.27), tex=mottled((0.22, 0.24, 0.27), seed + 3, 12, 0.3, 0.45),
                 tex_mode="replace", spec=1.2, gloss=45),                                   # 4 dark steel
        Material((0.05, 0.07, 0.10), emit=(0.25, 0.45, 0.85), spec=0.5),                    # 5 the sigil's glow
    ]
    stone = Material((0.09, 0.09, 0.10), tex=mottled((0.09, 0.09, 0.10), seed + 4, 1.5, 0.4, 0.3),
                     tex_mode="replace")

    def gate(p):
        # a monumental trilithon far behind them
        d = sd_box(p, (-2.4, 3.0, -10.0), (0.7, 3.0, 0.7))
        d = np.minimum(d, sd_box(p, (2.4, 3.0, -10.0), (0.7, 3.0, 0.7)))
        d = np.minimum(d, sd_box(p, (0.0, 6.5, -10.0), (3.5, 0.6, 0.8)))
        return displace(d, p, 0.08, 1.5, seed, 0.2)

    def fig(q):
        return figure(q, k, seed, hunch=0.0, robe=True, head="helmet", arms="shield", stride=0.5)

    placements = [((0.10, 0, 0.6), -8, 1.05), ((-1.15, 0, -0.9), 4, 1.05), ((1.35, 0, -1.9), -14, 1.05)]
    return _infantry_icon(seed, mats, fig, placements,
                          dict(top=(0.008, 0.010, 0.016), horizon=(0.12, 0.15, 0.22), glow=(0.6, 0.9, 1.5),
                               glow_at=(0.0, 0.15), glow_size=25.0),
                          (0.70, 0.75, 0.85), (0.8, 0.45, 0.4), back_col=(0.55, 0.75, 1.0),
                          env=[(gate, stone)], tint=(-0.006, 0.0, 0.016), smoke_col=(0.22, 0.26, 0.34),
                          smoke_src=(0.5, 0.25), glow=0.3)


def chaos_spawn():
    seed = 601
    k = Kit(skin=1, gear=2, eye=3, extra=1)
    mats = [
        Material((0.16, 0.08, 0.08), tex=mottled((0.16, 0.08, 0.08), seed, 14, 0.5, 0.3), tex_mode="replace",
                 wrap=0.4, spec=0.7, gloss=40, sss=(0.4, 0.05, 0.1),
                 emit=glow_cracks((2.4, 0.5, 1.6), seed)),                                  # 1 split, glowing flesh
        Material((0.07, 0.06, 0.05), tex=mottled((0.07, 0.06, 0.05), seed + 1), tex_mode="replace", spec=0.3),
        Material((0.0, 0.0, 0.0), emit=(2.5, 1.6, 2.4)),                                    # 3 eyes
    ]
    stone = Material((0.08, 0.07, 0.07), tex=mottled((0.08, 0.07, 0.07), seed + 3, 1.5, 0.4, 0.3),
                     tex_mode="replace")

    def fig(q):
        return figure(q, k, seed, hunch=0.45, head="mutant", arms="tentacle", stride=1.4, build=1.2, rough=0.03)

    placements = [((0.25, 0, 0.6), -20, 1.0), ((-1.05, 0, -1.0), -6, 0.95), ((1.40, 0, -2.2), -30, 1.0)]
    return _infantry_icon(seed, mats, fig, placements,
                          dict(top=(0.016, 0.006, 0.014), horizon=(0.28, 0.08, 0.20), glow=(1.8, 0.7, 1.4),
                               glow_at=(-0.15, 0.05), glow_size=35.0),
                          (0.9, 0.6, 0.85), (0.8, 0.4, 0.4), back_col=(1.0, 0.45, 0.85),
                          env=[(ruins(seed, -8.0), stone)], tint=(0.016, -0.006, 0.012),
                          smoke_col=(0.35, 0.16, 0.30), smoke_src=(0.35, 0.4), glow=0.45, saturation=0.6)


def void_pipers():
    seed = 701
    k = Kit(skin=1, cloth=2, gear=3, metal=4, eye=5)
    mats = [
        Material((0.20, 0.17, 0.20), tex=mottled((0.20, 0.17, 0.20), seed), tex_mode="replace", wrap=0.3),
        Material((0.05, 0.03, 0.06), tex=mottled((0.05, 0.03, 0.06), seed + 1, grime=0.3), tex_mode="replace",
                 wrap=0.3, spec=0.05, gloss=8, sheen=0.7),                                  # 2 violet-black robes
        Material((0.16, 0.14, 0.12), tex=mottled((0.16, 0.14, 0.12), seed + 2, 20, 0.3, 0.2),
                 tex_mode="replace", spec=0.8, gloss=40),                                   # 3 bone pipes
        Material((0.0, 0.0, 0.0)),                                                          # 4 the void in the hood
        Material((0.0, 0.0, 0.0), emit=(2.2, 0.9, 2.4)),                                    # 5 the pipes' glow
    ]

    def fig(q):
        return figure(q, k, seed, hunch=0.2, robe=True, head="hood", arms="pipe", stride=0.4)

    placements = [((-0.35, 0, 0.5), 18, 1.0), ((0.95, 0, -0.6), -16, 1.0), ((-1.6, 0, -2.4), 24, 0.98)]
    return _infantry_icon(seed, mats, fig, placements,
                          dict(top=(0.006, 0.004, 0.012), horizon=(0.12, 0.05, 0.16), glow=(1.2, 0.5, 1.6),
                               glow_at=(0.05, 0.22), glow_size=20.0, clouds=0.9),
                          (0.7, 0.55, 0.85), (0.8, 0.4, 0.4), back_col=(0.85, 0.45, 1.0),
                          tint=(0.01, -0.004, 0.02), smoke_col=(0.25, 0.14, 0.32), smoke_src=(0.5, 0.3),
                          glow=0.5, saturation=0.6)


def yellow_zealots():
    seed = 301
    k = Kit(skin=1, cloth=2, gear=3, metal=4, eye=5)
    mats = [
        Material((0.30, 0.26, 0.22), tex=mottled((0.30, 0.26, 0.22), seed), tex_mode="replace", wrap=0.3,
                 spec=0.1),                                                                   # 1 skin
        Material((0.42, 0.28, 0.05), tex=mottled((0.42, 0.28, 0.05), seed + 1, grime=0.6), tex_mode="replace",
                 wrap=0.35, spec=0.03, gloss=6, sheen=0.3),                                  # 2 ochre robes
        Material((0.07, 0.05, 0.035), tex=mottled((0.07, 0.05, 0.035), seed + 2), tex_mode="replace", spec=0.2),
        Material((0.55, 0.52, 0.44), tex=mottled((0.55, 0.52, 0.44), seed + 3, 14, 0.15, 0.25),
                 tex_mode="replace", spec=0.5, gloss=40),                                    # 4 pale masks
        Material((0.0, 0.0, 0.0)),
    ]

    def fig(q):
        return figure(q, k, seed, hunch=0.15, robe=True, head="hood", arms="rifle", stride=1.0)

    placements = [((0.30, 0, 0.6), -16, 1.0), ((-0.95, 0, -1.2), -12, 1.0), ((1.35, 0, -2.6), -20, 1.0)]
    return _infantry_icon(seed, mats, fig, placements,
                          dict(top=(0.015, 0.012, 0.009), horizon=(0.30, 0.20, 0.07), glow=(1.5, 0.9, 0.30),
                               glow_at=(-0.10, 0.04), glow_size=55.0),
                          (1.0, 0.80, 0.50), (0.9, 0.35, 0.35), back_col=(1.0, 0.70, 0.30),
                          tint=(0.02, 0.012, -0.012), smoke_col=(0.50, 0.38, 0.20), smoke_src=(0.4, 0.4))


def _scene_icon(seed, mats, figure_mats, scene, sky_kw, cam, lights, fog_col=None, fog_density=0.05,
                fog_start=6.5, rim=((0.28, 0.24, 0.18), 3.2), ambient=(0.035, 0.035, 0.04), **finish_kw):
    bg = sky(seed, **sky_kw)
    fog_col = fog_col if fog_col is not None else np.asarray(sky_kw["horizon"]) * 0.85
    return render_icon(scene, mats, cam, lights, seed, bg, figure_mats, ambient=ambient, rim=rim,
                       fog=(fog_col, fog_density, fog_start), **finish_kw)


def winged_beast(p, k, seed, kind):
    """A bat-winged flying beast facing +Z, wings raised, with a robed rider
    on its shoulders holding a lance. kind: "byakhee" (lean, ribbed, with a
    skull-like insect head) or "shantak" (bulky, scaled, horse-headed)."""
    f = Field(len(p))
    big = kind == "shantak"
    bw = 1.25 if big else 1.0
    body = R.sd_ellipsoid(p, (0, 0, 0), np.array([0.36, 0.33, 0.95]) * bw)
    if not big:
        # a starved, ribbed trunk
        body = body + 0.015 * (np.sin(p[:, 2] * 30) * 0.5 + 0.5) * smoothstep(0.6, 0.1, np.abs(p[:, 2]))
    neck = [(0, 0.10, 0.75 * bw), (0, 0.38 * bw, 1.15 * bw), (0, 0.45 * bw, 1.40 * bw)]
    d = R.smin(body, R.sd_tube(p, neck, np.array([0.20, 0.14, 0.11]) * bw), 0.12)
    tail = [(0, 0.0, -0.8 * bw), (0, -0.15, -1.6 * bw), (0.1, 0.05, -2.3 * bw), (0.15, 0.2, -2.7 * bw)]
    d = R.smin(d, R.sd_tube(p, tail, np.array([0.17, 0.10, 0.05, 0.012]) * bw), 0.10)
    hc = np.array([0, 0.42 * bw, 1.62 * bw])
    if big:
        # a long, heavy horse head, nose down, with a frill of spines
        d = R.smin(d, R.sd_ellipsoid(p, hc + (0, -0.08, 0.16), (0.12, 0.15, 0.40), R.rot_x(30)), 0.08)
        for j in range(5):
            b = np.array([0, 0.18 + 0.10 * j * 0.3, 1.0 + 0.12 * j]) * bw
            d = R.smin(d, R.sd_round_cone(p, b, b + (0, 0.22, -0.12), 0.035, 0.004), 0.02)
    else:
        d = R.smin(d, R.sd_ellipsoid(p, hc, (0.13, 0.12, 0.20)), 0.06)
        for side in (-1, 1):
            # hooked mandibles
            pts = [hc + (0.07 * side, -0.06, 0.12), hc + (0.10 * side, -0.14, 0.25), hc + (0.03 * side, -0.20, 0.30)]
            d = np.minimum(d, R.sd_tube(p, pts, [0.03, 0.02, 0.005]))
    # hind legs tucked under, talons spread
    for side in (-1, 1):
        pts = [(0.20 * side, -0.15, -0.35), (0.28 * side, -0.55, -0.15), (0.24 * side, -0.70, -0.55)]
        d = R.smin(d, R.sd_tube(p, np.array(pts) * bw, np.array([0.12, 0.07, 0.04]) * bw), 0.05)
        for j in (-1, 0, 1):
            t0 = np.array([0.24 * side, -0.70, -0.55]) * bw
            d = np.minimum(d, R.sd_round_cone(p, t0, t0 + (0.06 * j, -0.12, -0.12 + 0.04 * abs(j)), 0.02, 0.003))
    d = displace(d, p, 0.02 if big else 0.012, 14, seed, 0.05)
    f.add(d, k.skin)
    for side in (-1, 1):
        f.add(R.sd_sphere(p, hc + np.array([0.08 * side, 0.03, 0.14 if not big else 0.20]), 0.025), k.eye)
    sc = bw
    for side in (-1, 1):
        bones, mem = bat_wing(p, side, np.array([0.25, 0.22, 0.40]) * sc, np.array([0.95, 1.00, 0.20]) * sc,
                              np.array([1.45, 1.65, 0.38]) * sc,
                              [np.array([2.55, 1.95, 0.0]) * sc, np.array([2.45, 1.10, -0.55]) * sc,
                               np.array([1.80, 0.50, -0.90]) * sc],
                              np.array([0.30, 0.06, -0.65]) * sc, bone=0.06 * sc)
        f.add(bones, k.skin, 0.03)
        f.add(mem, k.extra)
    # the rider, hunched forward on its shoulders
    hip = np.array([0, 0.36 * bw, 0.30 * bw])
    f.add(R.sd_ellipsoid(p, hip + (0, 0.30, 0.08), (0.17, 0.27, 0.13), R.rot_x(-25)), k.cloth, 0.05)
    hood = hip + (0, 0.66, 0.22)
    f.add(R.sd_ellipsoid(p, hood, (0.12, 0.14, 0.13)), k.cloth, 0.04)
    f.add(R.sd_ellipsoid(p, hood + (0, -0.02, 0.06), (0.07, 0.09, 0.08)), k.metal)
    for side in (-1, 1):
        f.add(R.sd_tube(p, [hip + (0.14 * side, 0, 0), hip + (0.36 * side, -0.12, 0.22),
                            hip + (0.32 * side, -0.42, 0.12)], [0.07, 0.055, 0.045]), k.cloth, 0.03)
        f.add(R.sd_tube(p, [hip + (0.17 * side, 0.45, 0.12), hip + (0.24 * side, 0.30, 0.38),
                            hip + (0.10 * side, 0.30, 0.55)], [0.05, 0.045, 0.04]), k.cloth, 0.03)
    # a tattered cloak streaming back
    cl = R.sd_ellipsoid(p, hip + (0, 0.35, -0.25), (0.22, 0.30, 0.35), R.rot_x(35))
    cl = np.maximum(cl, -R.sd_ellipsoid(p, hip + (0, 0.30, -0.18), (0.19, 0.30, 0.33), R.rot_x(35)))
    f.add(cl, k.cloth, 0.03)
    a, b = hip + (0.12, 0.25, -0.5), hip + (0.20, 0.75, 2.4)
    f.add(R.sd_capsule(p, a, b, 0.018), k.gear)
    f.add(R.sd_round_cone(p, b, b + R.normalize(b - a) * 0.35, 0.03, 0.002), k.metal)
    return f


def _rider_icon(seed, kind, mats, k, sky_kw, light_col, back_col, placements, cam, ground_y=0.0, **finish_kw):
    figure_mats = list(range(1, len(mats) + 1))
    gm = Material((0.06, 0.05, 0.04), tex=mud(seed), tex_mode="replace", spec=0.3, gloss=60,
                  spec_tex=mud_spec(seed))
    all_mats = [gm] + mats

    def fig(q):
        return winged_beast(q, k, seed, kind)

    def scene(p):
        f = Field(len(p))
        for pos, yaw, sc in placements:
            f.add_group(p, pos, 3.4 * sc, lambda q, pos=pos, yaw=yaw, sc=sc: scaled(fig, q, pos, yaw, sc),
                        pad=0.4 * sc)
        f.add(ground(p, seed, ground_y), 0)
        return f

    lights = [Light(light_col, 0.9, direction=(0.7, 0.3, 0.5), softness=10),
              Light(back_col, 3.0, direction=(-0.3, 0.25, -1.0), softness=14),
              Light((0.30, 0.33, 0.40), 0.2, direction=(0.0, -1.0, 0.3), shadow=False)]
    return _scene_icon(seed, all_mats, figure_mats, scene, sky_kw, cam, lights, fog_density=0.03,
                       fog_start=10.0, **finish_kw)


def byakhee_riders():
    seed = 311
    k = Kit(skin=1, cloth=2, gear=3, metal=4, eye=5, extra=6)
    mats = [
        Material((0.10, 0.09, 0.07), tex=mottled((0.10, 0.09, 0.07), seed, 16, 0.4, 0.3), tex_mode="replace",
                 wrap=0.2, spec=0.5, gloss=30),                                             # 1 leathery hide
        Material((0.40, 0.27, 0.05), tex=mottled((0.40, 0.27, 0.05), seed + 1), tex_mode="replace", wrap=0.35,
                 sheen=0.3),                                                                # 2 ochre robes
        Material((0.07, 0.05, 0.035)),
        Material((0.55, 0.52, 0.44), spec=0.5, gloss=40),                                   # 4 pale mask, steel
        Material((0.0, 0.0, 0.0), emit=(1.2, 0.8, 0.2)),
        Material((0.08, 0.06, 0.05), tex=mottled((0.08, 0.06, 0.05), seed + 2, 6, 0.3, 0.0), tex_mode="replace",
                 wrap=0.6, spec=0.2, sss=(0.35, 0.12, 0.04)),                               # 6 wing membranes
    ]
    placements = [((0.0, 3.0, 0.0), -24, 1.0), ((-4.9, 4.6, -7.0), -18, 0.95)]
    cam = Camera((0.0, 1.6, 9.4), (-0.8, 3.4, 0.0), 31.0)
    return _rider_icon(seed, "byakhee", mats, k,
                       dict(top=(0.02, 0.015, 0.01), horizon=(0.38, 0.27, 0.10), glow=(1.4, 0.9, 0.35),
                            glow_at=(-0.15, 0.25), glow_size=25.0, clouds=0.9),
                       (1.0, 0.8, 0.5), (1.0, 0.7, 0.3), placements, cam, tint=(0.02, 0.012, -0.012),
                       smoke_col=(0.45, 0.35, 0.18), smoke_src=(0.4, 0.3))


def shantak_riders():
    seed = 211
    k = Kit(skin=1, cloth=2, gear=3, metal=4, eye=5, extra=6)
    mats = [
        Material((0.07, 0.07, 0.06), tex=scaly((0.07, 0.07, 0.06), seed, 30), tex_mode="replace", wrap=0.2,
                 spec=0.9, gloss=50),                                                       # 1 scaled hide
        Material((0.03, 0.025, 0.035), tex=mottled((0.03, 0.025, 0.035), seed + 1, grime=0.3),
                 tex_mode="replace", wrap=0.3, sheen=0.6),                                  # 2 black robes
        Material((0.06, 0.05, 0.04)),
        Material((0.35, 0.33, 0.36), spec=0.6, gloss=50),                                   # 4 blank face, steel
        Material((0.0, 0.0, 0.0), emit=(1.6, 0.35, 0.15)),
        Material((0.06, 0.045, 0.05), tex=mottled((0.06, 0.045, 0.05), seed + 2, 6, 0.3, 0.0), tex_mode="replace",
                 wrap=0.6, spec=0.3, sss=(0.3, 0.06, 0.08)),                                # 6 wing membranes
    ]
    placements = [((0.0, 3.0, 0.0), -26, 1.0), ((-5.0, 4.8, -6.5), -16, 0.95)]
    cam = Camera((0.0, 1.6, 10.6), (-0.8, 3.5, 0.0), 32.0)
    return _rider_icon(seed, "shantak", mats, k,
                       dict(top=(0.012, 0.008, 0.016), horizon=(0.22, 0.09, 0.08), glow=(1.3, 0.45, 0.2),
                            glow_at=(0.2, 0.18), glow_size=30.0, clouds=0.9),
                       (0.85, 0.6, 0.7), (1.0, 0.45, 0.25), placements, cam, tint=(0.012, -0.004, 0.02),
                       smoke_col=(0.30, 0.16, 0.20), smoke_src=(0.6, 0.3))


def _silhouettes(seed, placements, **fig_kw):
    """Small dark human figures as scenery, for scale (kept out of the
    icon's silhouette)."""
    k = Kit(skin=0, cloth=0, gear=0, metal=0, eye=0)

    def fn(p):
        return _squad(p, placements, lambda q: figure(q, k, seed, **fig_kw)).d
    return fn


def star_spawn():
    seed = 121
    k = Kit(skin=1, gear=2, eye=3, extra=4)
    mats = [
        Material((0.07, 0.10, 0.08), tex=scaly((0.07, 0.10, 0.08), seed, 16, belly=(0.12, 0.13, 0.09)),
                 tex_mode="replace", wrap=0.3, spec=0.9, gloss=50, sss=(0.05, 0.15, 0.08)),  # 1 slimy hide
        Material((0.12, 0.12, 0.09), spec=0.6, gloss=40),                                     # 2 claws
        Material((0.0, 0.0, 0.0), emit=(1.4, 0.25, 0.10)),                                    # 3 eyes
        Material((0.05, 0.07, 0.06), wrap=0.6, spec=0.3, sss=(0.10, 0.18, 0.10)),             # 4 wings
    ]
    water = Material((0.012, 0.018, 0.017), spec=0.5, gloss=40)
    men = Material((0.02, 0.02, 0.02))

    def fig(q):
        f = figure(q, k, seed, hunch=0.55, head="octopus", arms="claws", stride=0.9, build=1.45, rough=0.02,
                   head_scale=1.25)
        for side in (-1, 1):
            bones, mem = bat_wing(q, side, (0.22, 1.36, -0.05), (0.55, 1.75, -0.30), (0.75, 2.15, -0.25),
                                  [(1.25, 2.30, -0.55), (1.20, 1.85, -0.75), (0.85, 1.45, -0.70)],
                                  (0.15, 1.05, -0.25), thickness=0.008, bone=0.035)
            f.add(bones, k.skin, 0.03)
            f.add(mem, k.extra)
        return f

    def scene(p):
        f = _squad(p, [((0.4, 0, -1.0), -18, 2.5)], fig, center=1.2, radius=1.8, pad=0.12)
        f.add(_silhouettes(seed, [((-1.6, 0, 3.0), 160, 1.0), ((-2.3, 0, 2.2), 150, 1.0)], hunch=0.1,
                           head="helmet", arms="rifle", stride=1.6)(p), 6)
        f.add(sea(p, seed, 0.15), 5)
        f.add(ground(p, seed, 0.0), 0)
        return f

    gm = Material((0.05, 0.05, 0.045), tex=mud(seed, (0.05, 0.05, 0.045)), tex_mode="replace", spec=0.4, gloss=60,
                  spec_tex=mud_spec(seed))
    cam = Camera((0.8, 1.4, 11.0), (0.0, 2.6, 0.0), 30.0)
    lights = [Light((0.75, 0.9, 0.85), 0.8, direction=(0.8, 0.4, 0.4), softness=10),
              Light((0.6, 0.95, 0.85), 3.0, direction=(-0.3, 0.35, -1.0), softness=14),
              Light((0.30, 0.33, 0.40), 0.15, direction=(0.4, 0.5, 0.8), shadow=False)]
    return _scene_icon(seed, [gm] + mats + [water, men], [1, 2, 3, 4], scene,
                       dict(top=(0.008, 0.013, 0.013), horizon=(0.12, 0.18, 0.16), glow=(0.45, 0.70, 0.60),
                            glow_at=(-0.05, 0.12), glow_size=25.0, clouds=0.9),
                       cam, lights, fog_density=0.04, fog_start=8.0, tint=(-0.01, 0.012, 0.01),
                       smoke_col=(0.28, 0.36, 0.33), smoke_src=(0.45, 0.3))


def dark_young_fig(p, k, seed):
    """A Dark Young of Shub-Niggurath: a knot of ropy black trunks on four
    hoofed legs, branching into tentacles, its sides split by mouths."""
    f = Field(len(p))
    d = np.full(len(p), 1e9)
    for j, (sx, sz) in enumerate(((1, 1), (-1, 1), (1, -1), (-1, -1))):
        pts = [(0.0, 1.55, 0.0), (0.42 * sx, 0.85, 0.32 * sz), (0.62 * sx, 0.06, 0.48 * sz)]
        d = R.smin(d, R.sd_tube(p, pts, [0.26, 0.15, 0.08]), 0.15)
        f.add(R.sd_ellipsoid(p, (0.62 * sx, 0.06, 0.48 * sz), (0.10, 0.07, 0.10)), k.gear, 0.03)
    for j in range(5):
        a0 = j * 2 * math.pi / 5
        pts, radii = [], []
        for i in range(7):
            t = i / 6
            a = a0 + t * 2.2
            pts.append((0.20 * math.cos(a), 1.2 + 2.3 * t, 0.20 * math.sin(a)))
            radii.append(0.17 - 0.07 * t)
        d = R.smin(d, R.sd_tube(p, pts, radii), 0.10)
    top = np.array([0.0, 3.45, 0.0])
    for j in range(9):
        a = j * 2 * math.pi / 9 + 0.3
        c, s_ = math.cos(a), math.sin(a)
        rise = 0.35 + 0.25 * math.sin(j * 1.7)
        pts = [top, top + (0.55 * c, 0.45 + rise, 0.55 * s_), top + (1.15 * c, 0.55 + rise, 1.15 * s_),
               top + (1.75 * c, 0.15 + rise * 0.5, 1.75 * s_), top + (2.0 * c, -0.45, 2.0 * s_),
               top + (1.9 * c + 0.2 * s_, -0.85, 1.9 * s_ - 0.2 * c)]
        d = R.smin(d, R.sd_tube(p, pts, [0.15, 0.11, 0.08, 0.05, 0.025, 0.006]), 0.08)
    # ropy, knotted surface
    d = displace(d, p, 0.05, 6, seed, 0.12, ridged=True)
    d = displace(d, p, 0.015, 24, seed + 1, 0.05)
    # mouths torn into the trunk
    mouths = [(0.0, 2.2, 0.26), (0.20, 2.9, 0.18), (-0.24, 1.75, 0.20), (0.05, 3.25, -0.2)]
    for m in mouths:
        m = np.asarray(m)
        d = np.maximum(d, -R.sd_ellipsoid(p, m, (0.10, 0.04, 0.08)))
        f.add(R.sd_ellipsoid(p, m * (1, 1, 0.9), (0.08, 0.025, 0.05)), k.eye)
    f.add(d, k.skin, 0.0)
    return f


def dark_young():
    seed = 421
    k = Kit(skin=1, gear=2, eye=3)
    mats = [
        Material((0.035, 0.03, 0.028), tex=mottled((0.035, 0.03, 0.028), seed, 10, 0.4, 0.2), tex_mode="replace",
                 wrap=0.3, spec=0.8, gloss=40, sss=(0.06, 0.03, 0.02)),                     # 1 black, wet hide
        Material((0.10, 0.09, 0.07), spec=0.6, gloss=40),                                    # 2 hooves
        Material((0.05, 0.10, 0.03), emit=(0.35, 1.3, 0.25)),                                # 3 glowing maws
    ]
    bark = Material((0.05, 0.045, 0.04), tex=mottled((0.05, 0.045, 0.04), seed + 2, 3, 0.4, 0.3),
                    tex_mode="replace")

    def fig(q):
        return dark_young_fig(q, k, seed)

    trees = dead_trees(seed, [(-3.3, -3.0, 6.0), (-1.4, -7.0, 7.0), (3.0, -4.0, 6.5), (4.4, -9.0, 7.0),
                              (-5.0, -8.0, 7.0), (1.5, -11.0, 7.0)])

    def scene(p):
        f = Field(len(p))
        f.add_group(p, (0.3, 2.2, 0.0), 3.3, lambda q: scaled(fig, q, (0.3, 0, 0.0), 20, 1.0), pad=0.2)
        f.add(trees(p), 4)
        f.add(ground(p, seed, 0.0), 0)
        return f

    gm = Material((0.05, 0.045, 0.035), tex=mud(seed, (0.05, 0.045, 0.035)), tex_mode="replace", spec=0.3,
                  gloss=60, spec_tex=mud_spec(seed))
    cam = Camera((0.6, 1.3, 9.8), (0.2, 2.2, 0.0), 32.0)
    lights = [Light((0.70, 0.75, 0.65), 0.8, direction=(0.8, 0.5, 0.4), softness=10),
              Light((0.70, 0.85, 0.55), 2.8, direction=(-0.3, 0.4, -1.0), softness=14),
              Light((0.30, 0.33, 0.40), 0.15, direction=(0.4, 0.5, 0.8), shadow=False)]
    return _scene_icon(seed, [gm] + mats + [bark], [1, 2, 3], scene,
                       dict(top=(0.006, 0.009, 0.005), horizon=(0.10, 0.13, 0.07), glow=(0.55, 0.65, 0.35),
                            glow_at=(0.1, 0.2), glow_size=30.0),
                       cam, lights, fog_density=0.05, fog_start=7.0, tint=(0.0, 0.01, -0.006),
                       smoke_col=(0.22, 0.27, 0.18), smoke_src=(0.5, 0.3), glow=0.3)


def dunwich_fig(p, k, seed):
    """The Dunwich Horror: a barn-sized, egg-shaped bulk of squirming ropes on
    legs like hogsheads, eyes bulging all over it."""
    f = Field(len(p))
    d = R.sd_ellipsoid(p, (0, 2.6, 0), (1.6, 1.45, 1.35))
    for j, (sx, sz) in enumerate(((1, 1), (-1, 1), (1, -1), (-1, -1), (0, 1.3))):
        pts = [(0.7 * sx, 1.8, 0.6 * sz), (0.95 * sx, 0.9, 0.85 * sz), (1.0 * sx, 0.1, 0.9 * sz)]
        d = R.smin(d, R.sd_tube(p, pts, [0.42, 0.36, 0.32]), 0.25)
    for j in range(14):
        a = j * 2 * math.pi / 14
        c, s_ = math.cos(a), math.sin(a)
        y0 = 2.0 + 0.4 * math.sin(j * 1.3)
        pts = [(1.3 * c, y0, 1.1 * s_), (1.8 * c, y0 - 0.5, 1.5 * s_), (2.0 * c + 0.3 * s_, y0 - 1.2, 1.7 * s_),
               (1.9 * c, 0.15, 1.6 * s_ + 0.2 * c)]
        d = R.smin(d, R.sd_tube(p, pts, [0.16, 0.12, 0.08, 0.04]), 0.12)
    d = displace(d, p, 0.08, 4.5, seed, 0.18, ridged=True)
    d = displace(d, p, 0.02, 16, seed + 1, 0.06)
    f.add(d, k.skin)
    rng = np.random.default_rng(seed)
    for _ in range(9):
        th, ph = rng.uniform(-0.6, 0.6), rng.uniform(-1.2, 1.2)
        e = np.array([1.6 * math.sin(ph) * math.cos(th), 2.6 + 1.45 * math.sin(th), 1.35 * math.cos(ph) * math.cos(th)])
        f.add(R.sd_sphere(p, e, rng.uniform(0.08, 0.15)), k.eye)
    return f


def dunwich_horror():
    """Mostly invisible: the farm shows through it, bent as if through
    heat-haze, with only its sheen, its eyes and its rim catching the light."""
    seed = 521
    k = Kit(skin=1, eye=2)
    mats = [
        Material((0.10, 0.10, 0.11), tex=mottled((0.10, 0.10, 0.11), seed, 8, 0.4, 0.0), tex_mode="replace",
                 wrap=0.3, spec=1.6, gloss=60, sheen=0.8),                                   # 1 glistening ropes
        Material((0.55, 0.55, 0.45), emit=(0.25, 0.30, 0.22), spec=1.5, gloss=90),           # 2 eyes
    ]
    wood = Material((0.08, 0.06, 0.045), tex=mottled((0.08, 0.06, 0.045), seed + 3, 4, 0.4, 0.3),
                    tex_mode="replace")

    def farm(p):
        d = sd_box(p, (-5.5, 1.4, -14.0), (1.8, 1.4, 1.4))
        roof = sd_box(p, (-5.5, 2.8, -14.0), (1.35, 1.35, 1.5), R.rot_z(45))
        d = np.minimum(d, np.maximum(roof, -(p[:, 1] - 2.8)))
        for x in np.arange(-4.5, 5.0, 1.4):
            d = np.minimum(d, sd_box(p, (x, 0.55, 2.4), (0.06, 0.55, 0.06)))
        d = np.minimum(d, sd_box(p, (0.0, 0.85, 2.4), (5.0, 0.04, 0.03)))
        d = np.minimum(d, sd_box(p, (0.0, 0.45, 2.4), (5.0, 0.04, 0.03)))
        return d

    def fig(q):
        return dunwich_fig(q, k, seed)

    def scene(with_horror):
        def fn(p):
            f = Field(len(p))
            if with_horror:
                f.add_group(p, (0.5, 2.3, -0.5), 4.2, lambda q: scaled(fig, q, (0.5, 0, -0.5), -15, 1.0), pad=0.3)
            f.add(farm(p), 3)
            f.add(ground(p, seed, 0.0), 0)
            return f
        return fn

    gm = Material((0.06, 0.05, 0.035), tex=mud(seed, (0.06, 0.05, 0.035)), tex_mode="replace", spec=0.3,
                  gloss=60, spec_tex=mud_spec(seed))
    all_mats = [gm] + mats + [wood]
    cam = Camera((0.5, 1.4, 11.5), (0.2, 2.2, 0.0), 32.0)
    lights = [Light((0.75, 0.75, 0.85), 0.9, direction=(0.8, 0.5, 0.4), softness=10),
              Light((0.65, 0.75, 1.0), 2.8, direction=(-0.3, 0.4, -1.0), softness=14),
              Light((0.30, 0.33, 0.40), 0.15, direction=(0.4, 0.5, 0.8), shadow=False)]
    sky_kw = dict(top=(0.008, 0.010, 0.016), horizon=(0.13, 0.15, 0.20), glow=(0.5, 0.6, 0.9), glow_at=(-0.2, 0.1),
                  glow_size=30.0)
    bg = sky(seed, **sky_kw)
    W, H = ICON_SIZE
    kw = dict(ss=2, background=bg, ambient=(0.035, 0.035, 0.04), rim=((0.45, 0.5, 0.65), 2.5),
              fog=(np.asarray(sky_kw["horizon"]) * 0.85, 0.04, 8.0), max_dist=60.0, ao_scale=0.12,
              shadow_dist=6.0, shadow_bias=(0.006, 0.03))
    full = R.render(scene(True), all_mats, cam, lights, (W * SCALE, H * SCALE), coverage=[1, 2], **kw)
    empty = R.render(scene(False), all_mats, cam, lights, (W * SCALE, H * SCALE), **kw)
    cov = full["coverage"]
    # its whole outline for the white icon, fence and all in front of it ignored
    alone = R.render(lambda p: Field(len(p)).add_group(p, (0.5, 2.3, -0.5), 4.2,
                                                       lambda q: scaled(fig, q, (0.5, 0, -0.5), -15, 1.0), pad=0.3),
                     all_mats, cam, [], (W * SCALE, H * SCALE), ss=2, max_dist=60.0, coverage=[1, 2])["coverage"]
    # the farm bent through it, as through heat haze
    h, w = cov.shape
    yy, xx = np.mgrid[0:h, 0:w]
    shift = (R.fbm2(xx / 40.0, yy / 40.0, 3, seed) * 10 * cov).astype(int)
    bent = empty["rgb"][np.clip(yy + shift // 2, 0, h - 1), np.clip(xx + shift, 0, w - 1)]
    mix = cov[..., None]
    rgb = bent * (1 - mix) + (bent * 0.4 + full["rgb"] * 0.6) * mix
    out = {"rgb": rgb, "depth": np.minimum(full["depth"], empty["depth"]), "alpha": full["alpha"]}
    return finish(out, seed, tint=(-0.004, 0.0, 0.014), smoke_col=(0.25, 0.27, 0.33), smoke_src=(0.45, 0.3)), \
        alone



# ---------------------------------------------------------------------------
# Hastur's quest battalions (the Road to Carcosa)
# ---------------------------------------------------------------------------

def sandbags(seed, z, top=1.3, x0=-7.0, x1=7.0):
    """A parapet of lumpy sandbags in staggered rows (one bag per row,
    repeated along X)."""
    def fn(p):
        d = np.full(len(p), 1e9)
        rows = 5
        h = top / rows
        for r in range(rows):
            q = p.copy()
            q[:, 0] = np.mod(q[:, 0] + 0.25 * (r % 2), 0.5) - 0.25
            d = np.minimum(d, R.sd_ellipsoid(q, (0, h * (r + 0.5), z), (0.27, h * 0.62, 0.22)))
        d = np.maximum(d, np.abs(p[:, 0] - (x0 + x1) / 2) - (x1 - x0) / 2)
        return displace(d, p, 0.025, 9, seed, 0.06)
    return fn


def barbed_wire(posts, z, heights=(0.45, 0.8)):
    """Crossed stakes with sagging strands of wire strung between them."""
    def fn(p):
        d = np.full(len(p), 1e9)
        for x in posts:
            for sx in (-1, 1):
                d = np.minimum(d, R.sd_capsule(p, (x - 0.28 * sx, -0.1, z), (x + 0.22 * sx, 1.05, z + 0.05), 0.035))
        for a, b in zip(posts[:-1], posts[1:]):
            for hgt in heights:
                m = ((a + b) / 2, hgt - 0.12, z + 0.02)
                d = np.minimum(d, R.sd_tube(p, [(a, hgt, z), m, (b, hgt, z)], [0.012, 0.012, 0.012]))
        return d
    return fn


def lidless():
    """Sentries staring over a sandbag parapet at night: the eyes never close."""
    seed = 331
    k = Kit(skin=1, cloth=2, gear=3, metal=4, eye=5)
    mats = [
        Material((0.30, 0.30, 0.26), tex=mottled((0.30, 0.30, 0.26), seed, 12, 0.2, 0.3), tex_mode="replace",
                 wrap=0.3, spec=0.3, gloss=30, sss=(0.12, 0.10, 0.05)),                      # 1 gaunt skin
        Material((0.10, 0.10, 0.075), tex=mottled((0.10, 0.10, 0.075), seed + 1, grime=0.6), tex_mode="replace",
                 wrap=0.3, sheen=0.3),                                                        # 2 greatcoats
        Material((0.06, 0.045, 0.03), spec=0.3),                                               # 3 rifle wood
        Material((0.11, 0.12, 0.10), tex=mottled((0.11, 0.12, 0.10), seed + 2, 10, 0.3, 0.4), tex_mode="replace",
                 spec=0.7, gloss=40),                                                         # 4 steel helmets
        Material((0.70, 0.65, 0.35), emit=(3.2, 2.7, 0.9), spec=1.5, gloss=90),              # 5 staring eyes
    ]
    burlap = Material((0.13, 0.11, 0.08), tex=mottled((0.13, 0.11, 0.08), seed + 3, 7, 0.3, 0.5),
                      tex_mode="replace", wrap=0.2)
    wood = Material((0.05, 0.04, 0.03))

    def fig(q):
        return figure(q, k, seed, hunch=0.1, head="lidless", arms="rifle", stride=0.3)

    placements = [((-0.85, 0, -0.30), 10, 1.0), ((0.20, 0, -0.85), -2, 1.03), ((1.15, 0, -0.25), -12, 0.98),
                  ((-0.30, 0, -2.0), 4, 1.0), ((0.75, 0, -2.4), -8, 1.0)]
    bags, wire = sandbags(seed, 0.35, top=1.15), barbed_wire([-2.6, -0.4, 1.9, 4.0], 2.2)
    gm = Material((0.05, 0.045, 0.035), tex=mud(seed, (0.05, 0.045, 0.035)), tex_mode="replace", spec=0.3,
                  gloss=60, spec_tex=mud_spec(seed))

    def scene(p):
        f = _squad(p, placements, fig)
        f.add(bags(p), 6)
        f.add(wire(p), 7)
        f.add(ground(p, seed, 0.0), 0)
        return f

    cam = Camera((0.30, 1.50, 4.6), (0.25, 1.42, -0.4), 20.0)
    lights = [Light((0.85, 0.95, 0.75), 1.5, direction=(0.45, 0.55, 0.9), softness=10),
              Light((0.55, 0.75, 0.70), 2.6, direction=(-0.3, 0.35, -1.0), softness=14),
              Light((0.30, 0.33, 0.40), 0.15, direction=(0.0, 0.3, 1.0), shadow=False)]
    return _scene_icon(seed, [gm] + mats + [burlap, wood], [1, 2, 3, 4, 5], scene,
                       dict(top=(0.006, 0.010, 0.010), horizon=(0.11, 0.15, 0.13), glow=(1.1, 1.15, 0.75),
                            glow_at=(0.32, 0.30), glow_size=70.0, clouds=0.7),
                       cam, lights, fog_density=0.04, fog_start=8.0, tint=(-0.006, 0.012, 0.004),
                       smoke_col=(0.26, 0.30, 0.26), smoke_src=(0.6, 0.2), glow=0.6)



def theatre(z=-10.0):
    """A theatre front: a pedimented wall and a great arched doorway."""
    def fn(p):
        d = sd_box(p, (0.0, 2.6, z), (4.2, 2.6, 0.4))
        arch = np.minimum(sd_box(p, (0.0, 1.4, z), (1.3, 1.4, 1.0)),
                          R.length((p - np.array([0.0, 2.8, z])) * np.array([1, 1, 0])) - 1.3)
        d = np.maximum(d, -arch)
        for x in (-2.4, 2.4, -3.6, 3.6):
            d = np.minimum(d, R.sd_capsule(p, (x, 0.0, z + 0.55), (x, 4.6, z + 0.55), 0.22))
        d = np.minimum(d, sd_box(p, (0.0, 5.0, z + 0.3), (4.5, 0.25, 0.7)))
        d = np.minimum(d, np.maximum(sd_triangle(p, (-4.4, 5.2, z + 0.3), (4.4, 5.2, z + 0.3), (0.0, 6.7, z + 0.3), 0.3),
                                     -(p[:, 1] - 5.2)))
        # a broken roofline
        return np.maximum(d, p[:, 1] - (5.8 + 1.4 * R.fbm3(p * np.array([0.8, 0, 0.3]), 2, 7)))
    return fn


def audience():
    """The Audience: theatre-goers in evening dress, applauding as they march
    through the mud, their shirt-fronts and gloves stained, the theatre
    burning behind them."""
    seed = 341
    k = Kit(skin=1, cloth=2, gear=3, eye=4, extra=5)
    kw = Kit(skin=1, cloth=6, gear=3, eye=4, extra=5)
    mats = [
        Material((0.46, 0.43, 0.38), tex=mottled((0.46, 0.43, 0.38), seed, 10, 0.12, 0.2), tex_mode="replace",
                 wrap=0.35, spec=0.35, gloss=30, sss=(0.15, 0.06, 0.04)),                   # 1 powdered faces
        Material((0.020, 0.019, 0.022), tex=mottled((0.020, 0.019, 0.022), seed + 1, grime=0.4),
                 tex_mode="replace", wrap=0.3, spec=0.25, gloss=20, sheen=0.5),              # 2 tailcoats
        Material((0.015, 0.013, 0.012), spec=0.6, gloss=40, sheen=0.6),                      # 3 silk hats, hair
        Material((0.0, 0.0, 0.0)),                                                           # 4 eye sockets
        Material((0.62, 0.60, 0.54), tex=mottled((0.62, 0.60, 0.54), seed + 2, 9, 0.2, 0.75, (0.22, 0.015, 0.01)),
                 tex_mode="replace", wrap=0.3, spec=0.2),                                    # 5 stained linen
        Material((0.10, 0.015, 0.02), tex=mottled((0.10, 0.015, 0.02), seed + 3, grime=0.5), tex_mode="replace",
                 wrap=0.35, spec=0.3, gloss=20, sheen=0.7),                                  # 6 gowns
    ]
    stone = Material((0.10, 0.085, 0.07), tex=mottled((0.10, 0.085, 0.07), seed + 4, 1.5, 0.4, 0.4),
                     tex_mode="replace")
    fire = Material((0.0, 0.0, 0.0), emit=(2.6, 1.0, 0.25))

    def shirt(f, q):
        f.add(R.sd_ellipsoid(q, (0.0, 1.30, 0.13), (0.06, 0.16, 0.035)), k.extra, 0.01)
        return f

    def man(q):
        return shirt(figure(q, k, seed, head="tophat", arms="clap", stride=0.7), q)

    def woman(q):
        return figure(q, kw, seed + 1, robe=True, head="bun", arms="clap", stride=0.6, build=0.92)

    men = [((-0.55, 0, 0.55), -8, 1.0), ((1.05, 0, -0.55), -16, 1.02), ((-1.55, 0, -1.6), 4, 0.98),
           ((0.55, 0, -2.5), -10, 1.0)]
    women = [((0.35, 0, 0.1), -6, 0.97), ((-0.65, 0, -2.3), 2, 0.96)]
    crowd = _silhouettes(seed, [((x, 0, z), 0, 1.0) for x, z in ((-2.6, -4.5), (-1.3, -5.0), (0.2, -5.5), (1.6, -4.8),
                                                             (2.8, -5.6), (-0.6, -6.5), (1.0, -7.0))],
                         head="tophat", arms="clap", stride=0.6)
    front = theatre(-11.0)
    gm = Material((0.055, 0.045, 0.035), tex=mud(seed, (0.055, 0.045, 0.035)), tex_mode="replace", spec=0.3,
                  gloss=60, spec_tex=mud_spec(seed))

    def scene(p):
        f = _squad(p, men, man)
        f.add_group(p, (0.0, 1.0, -0.9), 3.5, lambda q: _squad(q, women, woman), pad=0.1)
        f.add(crowd(p), 7)
        f.add(front(p), 7)
        f.add(sd_box(p, (0.0, 1.5, -11.6), (1.4, 1.5, 0.2)), 8)
        f.add(ground(p, seed, 0.0), 0)
        return f

    cam = Camera((0.55, 1.05, 6.8), (0.0, 1.0, 0.0), 22.0)
    lights = [Light((1.0, 0.80, 0.62), 1.8, direction=(0.45, 0.45, 0.9), softness=10),
              Light((1.0, 0.55, 0.25), 3.4, direction=(-0.2, 0.3, -1.0), softness=14),
              Light((0.30, 0.33, 0.40), 0.15, direction=(0.4, 0.5, 0.8), shadow=False)]
    return _scene_icon(seed, [gm] + mats + [stone, fire], [1, 2, 3, 4, 5, 6], scene,
                       dict(top=(0.012, 0.008, 0.006), horizon=(0.30, 0.13, 0.05), glow=(1.6, 0.7, 0.25),
                            glow_at=(0.0, 0.05), glow_size=20.0, clouds=0.9),
                       cam, lights, fog_density=0.05, fog_start=7.0, tint=(0.02, 0.0, -0.01),
                       smoke_col=(0.40, 0.22, 0.12), smoke_src=(0.5, 0.35), glow=0.3)



def twin_suns(seed, suns, **sky_kw):
    """sky() with the twin suns of Carcosa: suns are (x, y, radius, colour),
    each a hard disc in a wide halo."""
    base = sky(seed, **sky_kw)

    def bg(rd):
        col = base(rd)
        for x, y, r, c in suns:
            d2 = (rd[:, 0] - x) ** 2 + (rd[:, 1] - y) ** 2
            disc = smoothstep(r * r * 1.3, r * r * 0.7, d2)
            col = col + np.asarray(c, float) * (3.0 * disc + 0.35 * np.exp(-d2 / (r * r * 6)))[:, None]
        return col
    return bg


def lake_hali(seed, shore=-1.2, height=0.03):
    """Still, dark water beyond the shore line."""
    def fn(p):
        return np.maximum(sea(p, seed, height), p[:, 2] - shore)
    return fn


def cassildas_choir():
    """Cassilda's Choir on the shore of Lake Hali, faces turned up to the
    sky, singing, as the twin suns sink behind the lake."""
    seed = 351
    k = Kit(skin=1, cloth=2, gear=3, extra=4)
    mats = [
        Material((0.40, 0.36, 0.31), tex=mottled((0.40, 0.36, 0.31), seed, 10, 0.15, 0.3), tex_mode="replace",
                 wrap=0.35, spec=0.3, gloss=30, sss=(0.15, 0.07, 0.04)),                    # 1 pale skin
        Material((0.36, 0.26, 0.07), tex=mottled((0.36, 0.26, 0.07), seed + 1, grime=0.75), tex_mode="replace",
                 wrap=0.35, spec=0.05, gloss=8, sheen=0.4),                                 # 2 yellow robes
        Material((0.05, 0.035, 0.025)),                                                      # 3 bindings
        Material((0.55, 0.50, 0.40), tex=mottled((0.55, 0.50, 0.40), seed + 2, 12, 0.2, 0.4), tex_mode="replace",
                 wrap=0.3),                                                                  # 4 hymnal pages
    ]
    water = Material((0.004, 0.005, 0.007), tex=mottled((0.004, 0.005, 0.007), seed + 3, 2, 0.3, 0.0),
                     tex_mode="replace", spec=3.0, gloss=120)

    def fig(q):
        return figure(q, k, seed, hunch=-0.1, robe=True, head="singer", arms="limp", stride=0.2, head_scale=1.12)

    placements = [((-1.65, 0, -0.45), 18, 0.96), ((-0.55, 0, 0.45), 6, 1.03), ((0.50, 0, -0.85), -4, 1.0),
                  ((1.45, 0, 0.15), -16, 0.98), ((2.75, 0, -1.9), -22, 0.95)]
    lake = lake_hali(seed)
    gm = Material((0.07, 0.06, 0.045), tex=mud(seed, (0.07, 0.06, 0.045)), tex_mode="replace", spec=0.4,
                  gloss=60, spec_tex=mud_spec(seed))

    def scene(p):
        f = _squad(p, placements, fig)
        f.add(lake(p), 5)
        f.add(ground(p, seed, 0.0), 0)
        return f

    cam = Camera((0.35, 1.55, 8.4), (0.10, 1.0, -2.0), 24.0)
    lights = [Light((1.0, 0.75, 0.40), 2.2, direction=(-0.35, 0.10, -1.0), softness=14),
              Light((1.0, 0.85, 0.50), 1.8, direction=(0.25, 0.14, -1.0), softness=14),
              Light((0.65, 0.58, 0.60), 1.3, direction=(0.3, 0.8, 0.8), softness=10),
              Light((0.30, 0.33, 0.40), 0.15, direction=(0.0, 0.3, 1.0), shadow=False)]
    sky_kw = dict(top=(0.016, 0.010, 0.010), horizon=(0.30, 0.17, 0.06), clouds=1.0)
    bg = twin_suns(seed, [(-0.13, 0.030, 0.020, (1.6, 1.05, 0.45)), (0.17, 0.050, 0.014, (1.5, 1.2, 0.6))], **sky_kw)
    return render_icon(scene, [gm] + mats + [water], cam, lights, seed, bg, [1, 2, 3, 4],
                       ambient=(0.035, 0.03, 0.03), rim=((0.40, 0.28, 0.14), 3.0),
                       fog=(np.asarray(sky_kw["horizon"]) * 0.8, 0.012, 9.0), tint=(0.02, 0.012, -0.012),
                       smoke_col=(0.45, 0.33, 0.16), smoke_src=(0.5, 0.25), smoke_amt=0.12, glow=0.5)



def pallid_masks():
    """The Pallid Masks leading an assault through the smoke: dark hooded
    coats, fixed bayonets, and pale masks grown into the faces beneath."""
    seed = 361
    k = Kit(skin=1, cloth=2, gear=3, metal=4, eye=5)
    mats = [
        Material((0.30, 0.27, 0.23), wrap=0.3, spec=0.2),                                    # 1 hands
        Material((0.045, 0.038, 0.025), tex=mottled((0.045, 0.038, 0.025), seed + 1, grime=0.5),
                 tex_mode="replace", wrap=0.3, spec=0.08, gloss=10, sheen=0.5),             # 2 dark coats
        Material((0.06, 0.045, 0.03), spec=0.3),                                               # 3 rifle wood
        Material((0.80, 0.77, 0.68), tex=mottled((0.80, 0.77, 0.68), seed + 2, 16, 0.08, 0.25),
                 tex_mode="replace", wrap=0.4, spec=0.9, gloss=60, emit=(0.06, 0.055, 0.045)),  # 4 pale masks, steel
        Material((0.0, 0.0, 0.0)),
    ]
    stone = Material((0.09, 0.075, 0.065), tex=mottled((0.09, 0.075, 0.065), seed + 3, 1.5, 0.4, 0.3),
                     tex_mode="replace")

    def fig(q):
        return figure(q, k, seed, hunch=0.3, robe=True, head="mask", arms="rifle", stride=1.2, head_scale=1.1)

    placements = [((0.15, 0, 0.7), -14, 1.0), ((-1.10, 0, -0.9), -6, 1.0), ((1.35, 0, -1.9), -22, 1.0),
                  ((-0.30, 0, -3.2), -10, 0.98)]
    return _infantry_icon(seed, mats, fig, placements,
                          dict(top=(0.012, 0.007, 0.006), horizon=(0.26, 0.10, 0.05), glow=(1.4, 0.55, 0.2),
                               glow_at=(-0.28, 0.05), glow_size=40.0, clouds=0.9),
                          (0.95, 0.90, 0.80), (0.55, 0.45, 0.85), back_col=(1.0, 0.50, 0.22),
                          key_power=1.4, env=[(ruins(seed), stone)], tint=(0.018, 0.0, -0.008),
                          smoke_col=(0.38, 0.20, 0.12), smoke_src=(0.35, 0.4))



def tatters_fig(p, k, seed):
    """One of the King's Tatters: a tall shape of wound yellow rags with long,
    reaching fingers, strips of cloth streaming off it in the wind (toward
    +X), and a human hand pushing out through the rags of its chest."""
    f = figure(p, k, seed, hunch=0.2, robe=True, head="wrapped", arms="reach", build=0.74, stride=0.4)
    rng = np.random.default_rng(seed)
    d = np.full(len(p), 1e9)
    for j in range(13):
        side = 1 if j % 3 else -1
        y0 = rng.uniform(0.9, 1.75)
        r0 = 0.30 - 0.12 * y0 / 1.55
        a0 = np.array([r0 * side * 0.8, y0, rng.uniform(-0.15, 0.12)])
        n = rng.uniform(0.55, 1.15)
        wav = rng.uniform(0, 6.28)
        pts = [a0 + (n * t, -0.25 * n * t * t - 0.04 * t, 0.07 * math.sin(wav + 5 * t)) for t in (0.0, 0.35, 0.7, 1.0)]
        d = np.minimum(d, R.sd_tube(p, pts, [0.035, 0.026, 0.016, 0.006]))
    f.add(d, k.cloth, 0.03)
    # the hand of someone it took
    w = np.array([0.05, 1.12, 0.23])
    f.add(R.sd_ellipsoid(p, w + (0, 0.02, 0.03), (0.045, 0.055, 0.02), R.rot_x(-30)), k.extra, 0.02)
    for j, dx in enumerate((-0.035, -0.012, 0.012, 0.035)):
        f.add(R.sd_round_cone(p, w + (dx, 0.06, 0.05), w + (dx * 1.8, 0.15 - 0.02 * abs(j - 1.5), 0.10),
                              0.011, 0.007), k.extra, 0.01)
    f.add(R.sd_round_cone(p, w + (-0.05, 0.0, 0.04), w + (-0.10, 0.05, 0.09), 0.012, 0.008), k.extra, 0.01)
    return f


def kings_tatters():
    """The King's Tatters looming out of a yellow storm."""
    seed = 371
    k = Kit(skin=1, cloth=2, gear=2, extra=3)
    mats = [
        Material((0.16, 0.15, 0.13), wrap=0.3, spec=0.3, gloss=30),                           # 1 long grey fingers
        Material((0.40, 0.29, 0.07), tex=mottled((0.40, 0.29, 0.07), seed + 1, 9, 0.35, 0.8),
                 tex_mode="replace", wrap=0.4, spec=0.05, gloss=8, sheen=0.5),               # 2 yellow rags
        Material((0.50, 0.38, 0.32), wrap=0.4, spec=0.3, gloss=30, sss=(0.25, 0.08, 0.05)),   # 3 the hand
    ]
    stone = Material((0.08, 0.07, 0.06), tex=mottled((0.08, 0.07, 0.06), seed + 3, 1.5, 0.4, 0.3),
                     tex_mode="replace")

    def fig(q):
        return tatters_fig(q, k, seed)

    placements = [((-0.15, 0, 0.3), -12, 1.45), ((1.75, 0, -2.4), -24, 1.40), ((-2.4, 0, -4.5), 8, 1.35)]
    gm = Material((0.06, 0.05, 0.035), tex=mud(seed, (0.06, 0.05, 0.035)), tex_mode="replace", spec=0.3,
                  gloss=60, spec_tex=mud_spec(seed))
    town = ruins(seed, -11.0)

    def scene(p):
        f = _squad(p, placements, fig, radius=2.0, pad=0.15)
        f.add(town(p), 4)
        f.add(ground(p, seed, 0.0), 0)
        return f

    cam = Camera((0.55, 0.75, 8.2), (0.25, 1.75, 0.0), 27.0)
    lights = [Light((1.0, 0.82, 0.55), 2.0, direction=(-0.5, 0.45, 0.8), softness=10),
              Light((1.0, 0.70, 0.30), 2.4, direction=(0.4, 0.3, -1.0), softness=14),
              Light((0.30, 0.33, 0.40), 0.15, direction=(0.0, 0.3, 1.0), shadow=False)]
    return _scene_icon(seed, [gm] + mats + [stone], [1, 2, 3], scene,
                       dict(top=(0.005, 0.004, 0.004), horizon=(0.11, 0.075, 0.03), glow=(0.7, 0.45, 0.15),
                            glow_at=(0.28, 0.08), glow_size=45.0, clouds=1.1),
                       cam, lights, fog_density=0.04, fog_start=8.0, tint=(0.02, 0.012, -0.014),
                       smoke_col=(0.45, 0.35, 0.15), smoke_src=(0.3, 0.3), glow=0.2)



def halis_drowned():
    """Hali's Drowned wading out of black water in the mist, swollen and grey,
    heads hanging, jaws fallen open."""
    seed = 381
    k = Kit(skin=1, cloth=2, gear=2, eye=3)
    mats = [
        Material((0.36, 0.39, 0.37), tex=mottled((0.36, 0.39, 0.37), seed, 9, 0.3, 0.5, (0.07, 0.08, 0.06)),
                 tex_mode="replace", wrap=0.4, spec=1.2, gloss=50, sss=(0.08, 0.12, 0.10)),  # 1 drowned skin
        Material((0.16, 0.12, 0.035), tex=mottled((0.16, 0.12, 0.035), seed + 1, grime=0.8), tex_mode="replace",
                 wrap=0.3, spec=0.9, gloss=40),                                              # 2 sodden rags
        Material((0.55, 0.60, 0.56), emit=(0.30, 0.36, 0.33), spec=1.5, gloss=90),          # 3 milky eyes
    ]
    water = Material((0.005, 0.007, 0.008), tex=mottled((0.005, 0.007, 0.008), seed + 3, 2, 0.3, 0.0),
                     tex_mode="replace", spec=1.0, gloss=120)

    def fig(q):
        return figure(q, k, seed, hunch=0.3, head="drowned", arms="limp", stride=0.5, build=1.22, rough=0.015,
                      head_scale=1.1)

    placements = [((0.05, 0, 0.9), -10, 1.0), ((-1.25, 0, -0.6), 12, 1.0), ((1.30, 0, -1.4), -20, 1.0),
                  ((-0.30, 0, -3.0), 4, 1.0), ((2.2, 0, -4.4), -16, 1.0), ((-2.4, 0, -4.0), 14, 1.0)]

    def scene(p):
        f = _squad(p, placements, fig)
        # still, black water at thigh height, barely rippled
        f.add(p[:, 1] - 0.58 - 0.012 * np.sin(p[:, 0] * 4.0 + p[:, 2] * 2.5) * np.sin(p[:, 2] * 3.1), 4)
        return f

    cam = Camera((0.30, 1.15, 5.6), (0.05, 1.15, 0.0), 24.0)
    lights = [Light((0.70, 0.80, 0.80), 1.2, direction=(0.5, 0.6, 0.7), softness=10),
              Light((0.65, 0.85, 0.85), 2.8, direction=(-0.25, 0.3, -1.0), softness=14),
              Light((0.30, 0.33, 0.40), 0.15, direction=(0.0, 0.3, 1.0), shadow=False)]
    return _scene_icon(seed, [water] + mats + [water], [1, 2, 3], scene,
                       dict(top=(0.005, 0.008, 0.010), horizon=(0.10, 0.14, 0.14), glow=(0.50, 0.60, 0.55),
                            glow_at=(-0.18, 0.14), glow_size=30.0, clouds=0.8),
                       cam, lights, fog_density=0.07, fog_start=5.5, tint=(-0.01, 0.01, 0.012),
                       smoke_col=(0.30, 0.36, 0.36), smoke_src=(0.4, 0.3), smoke_amt=0.4)


# ---------------------------------------------------------------------------
# The gods incarnate
# ---------------------------------------------------------------------------

def great_cthulhu():
    """Cthulhu wading out of a storm, a destroyer at his feet."""
    seed = 131
    k = Kit(skin=1, gear=2, eye=3, extra=4)
    mats = [
        Material((0.06, 0.09, 0.07), tex=scaly((0.06, 0.09, 0.07), seed, 9, belly=(0.10, 0.11, 0.08)),
                 tex_mode="replace", wrap=0.3, spec=1.0, gloss=50, sss=(0.05, 0.15, 0.08)),
        Material((0.10, 0.10, 0.08), spec=0.6, gloss=40),
        Material((0.0, 0.0, 0.0), emit=(2.2, 0.35, 0.12)),
        Material((0.04, 0.06, 0.05), wrap=0.6, spec=0.4, sss=(0.10, 0.18, 0.10)),
    ]
    water = Material((0.008, 0.012, 0.011), spec=0.35, gloss=30)
    steel = Material((0.03, 0.03, 0.03))

    def fig(q):
        f = figure(q, k, seed, hunch=0.3, head="octopus", arms="claws", stride=0.5, build=1.6, rough=0.02,
                   head_scale=1.3)
        for side in (-1, 1):
            bones, mem = bat_wing(q, side, (0.25, 1.40, -0.08), (0.80, 1.95, -0.30), (1.10, 2.55, -0.20),
                                  [(1.95, 2.75, -0.55), (1.95, 2.05, -0.85), (1.40, 1.45, -0.80)],
                                  (0.18, 1.00, -0.25), thickness=0.008, bone=0.04)
            f.add(bones, k.skin, 0.03)
            f.add(mem, k.extra)
        return f

    S = 9.0

    def ship(p):
        c = np.array([-9.0, 0.3, 16.0])
        d = sd_box(p, c, (4.0, 0.55, 0.55), rot_y(25), r=0.2)
        d = np.minimum(d, sd_box(p, c + (0.5, 0.9, 0.0), (1.2, 0.5, 0.4), rot_y(25)))
        d = np.minimum(d, R.sd_capsule(p, c + (-0.6, 1.0, 0.25), c + (-0.6, 2.2, 0.25), 0.22))
        d = np.minimum(d, R.sd_capsule(p, c + (1.2, 1.0, -0.5), c + (1.2, 3.4, -0.5), 0.05))
        return d

    def scene(p):
        f = _squad(p, [((0.0, -0.85 * S, 0.0), -12, S)], fig, center=1.6, radius=2.9, pad=0.15)
        f.add(ship(p), 6)
        q = p / 3.0
        f.add(sea(q, seed, 0.0) * 3.0, 5)
        return f

    cam = Camera((3.0, 2.0, 52.0), (0.0, 8.0, 0.0), 28.0)
    lights = [Light((0.7, 0.85, 0.8), 0.7, direction=(0.8, 0.5, 0.4), softness=10),
              Light((0.75, 1.0, 0.9), 3.2, direction=(-0.4, 0.5, -1.0), softness=14),
              Light((0.30, 0.33, 0.40), 0.15, direction=(0.4, 0.5, 0.8), shadow=False)]
    return _scene_icon(seed, [water] + mats + [water, steel], [1, 2, 3, 4], scene,
                       dict(top=(0.004, 0.007, 0.007), horizon=(0.07, 0.10, 0.095), glow=(0.55, 0.80, 0.70),
                            glow_at=(-0.02, 0.20), glow_size=22.0, clouds=1.0),
                       cam, lights, fog_density=0.012, fog_start=40.0, rim=((0.25, 0.35, 0.30), 3.0),
                       tint=(-0.01, 0.012, 0.01), smoke_col=(0.25, 0.33, 0.30), smoke_src=(0.35, 0.2),
                       border=(150, 120, 60), glow=0.3)


def pyramid(p, base, half, height):
    """A bound for a square pyramid standing on base."""
    q = p - np.asarray(base, float)
    n = math.hypot(height, half)
    a = (height * np.maximum(np.abs(q[:, 0]), np.abs(q[:, 2])) + half * q[:, 1] - half * height) / n
    return np.maximum(a, -q[:, 1])


def crawling_chaos():
    """The Black Pharaoh standing before the pyramids, the three-lobed
    burning eye hanging over it."""
    seed = 231
    k = Kit(skin=1, cloth=2, gear=3, metal=4, eye=5)
    mats = [
        Material((0.01, 0.01, 0.012), spec=1.2, gloss=80),                                  # 1 the void of its face
        Material((0.03, 0.022, 0.03), tex=mottled((0.03, 0.022, 0.03), seed, grime=0.2), tex_mode="replace",
                 wrap=0.3, sheen=0.7),                                                       # 2 black robes
        Material((0.30, 0.22, 0.07), tex=lambda p, n: np.where((np.sin(p[:, 1] * 95) > 0)[:, None],
                                                               np.array([0.32, 0.23, 0.06]),
                                                               np.array([0.03, 0.03, 0.05])),
                 tex_mode="replace", spec=1.0, gloss=40),                                   # 3 striped nemes
        Material((0.35, 0.25, 0.06), spec=1.5, gloss=60),                                   # 4 gold
        Material((0.0, 0.0, 0.0), emit=(4.0, 0.9, 0.25)),                                   # 5 the burning eye
    ]
    sand = Material((0.10, 0.065, 0.04), tex=mottled((0.10, 0.065, 0.04), seed + 1, 0.8, 0.3, 0.2),
                    tex_mode="replace", spec=0.1)
    stone = Material((0.12, 0.08, 0.06), tex=mottled((0.12, 0.08, 0.06), seed + 2, 1.0, 0.3, 0.3),
                     tex_mode="replace")

    def fig(q):
        f = figure(q, k, seed, hunch=0.0, robe=True, head="pharaoh", arms="crossed", stride=0.3, build=1.05)
        # the three-lobed eye
        c = np.array([0.0, 2.22, 0.05])
        for j in range(3):
            a = math.pi / 2 + j * 2 * math.pi / 3
            f.add(R.sd_sphere(q, c + (0.11 * math.cos(a), 0.11 * math.sin(a), 0), 0.085), k.eye, 0.04)
        return f

    def scene(p):
        f = _squad(p, [((0.0, 0, 0.0), -8, 1.6)], fig, center=1.3, radius=1.6, pad=0.1)
        f.add(np.minimum(pyramid(p, (-13.0, 0, -45.0), 10.0, 11.5), pyramid(p, (11.0, 0, -60.0), 8.0, 9.0)), 7)
        f.add(p[:, 1] - 0.15 * R.fbm3(p * np.array([0.25, 0, 0.12]), 3, seed) * (np.abs(p[:, 1]) < 0.5), 6)
        return f

    cam = Camera((0.5, 1.4, 8.6), (0.0, 2.25, 0.0), 26.0)
    lights = [Light((1.0, 0.7, 0.5), 0.8, direction=(0.8, 0.45, 0.4), softness=10),
              Light((1.0, 0.45, 0.2), 3.2, direction=(-0.3, 0.25, -1.0), softness=14),
              Light((0.30, 0.33, 0.40), 0.12, direction=(0.4, 0.5, 0.8), shadow=False)]
    return _scene_icon(seed, [sand] + mats + [sand, stone], [1, 2, 3, 4, 5], scene,
                       dict(top=(0.012, 0.006, 0.012), horizon=(0.30, 0.10, 0.05), glow=(1.6, 0.55, 0.20),
                            glow_at=(0.0, 0.10), glow_size=30.0, stars=0.4),
                       cam, lights, fog_density=0.012, fog_start=15.0, tint=(0.014, -0.004, 0.016),
                       smoke_col=(0.35, 0.16, 0.12), smoke_src=(0.5, 0.35), border=(150, 120, 60), glow=0.6)


def king_in_yellow():
    """The King's painted portrait, cropped to his wrapped head and the
    tentacles behind it, so the icon is the same creature as the avatar."""
    import art_portraits as P
    img, seed = P.king_paint(2, 1)
    scene, mats, _ = P.king_setup()
    H, W = img.shape[:2]
    cov = R.render(scene, [Material((0, 0, 0))] * len(mats), P.king_camera(), [], (W, H), ss=1,
                   coverage=list(range(len(mats))), max_dist=8.0, ao_scale=0.08)["coverage"]
    top = int(H * 0.095)
    box = (top, top + W * 2 // 3)
    crop = img[box[0]:box[1]]
    w, h = ICON_SIZE
    pil = R.to_image(crop).convert("RGB").resize((w, h), Image.LANCZOS)
    pil = pil.filter(ImageFilter.UnsharpMask(radius=0.8, percent=60, threshold=1))
    a = np.asarray(pil).astype(float) / 255
    a = R.grade(a, saturation=0.8, contrast=1.1, black=0.02)
    rng = np.random.default_rng(seed)
    a = a + rng.normal(0, 0.028, (h, w, 1)) + rng.normal(0, 0.008, (h, w, 3))
    b = np.array([150, 120, 60]) / 255
    a[0, :], a[-1, :], a[:, 0], a[:, -1] = b, b, b, b
    return R.to_image(np.clip(a, 0, 1)), cov[box[0]:box[1]]


def black_goat_fig(p, k, seed):
    """Shub-Niggurath: a cloudy bulk of black flesh on goat legs, ropy
    tentacles trailing to the ground, horns and a scatter of eyes."""
    f = Field(len(p))
    rng = np.random.default_rng(seed)
    d = np.full(len(p), 1e9)
    for _ in range(11):
        c = np.array([rng.uniform(-1.0, 1.0), 2.9 + rng.uniform(-0.6, 0.8), rng.uniform(-0.6, 0.6)])
        d = R.smin(d, R.sd_sphere(p, c, rng.uniform(0.55, 0.95)), 0.35)
    for sx, sz in ((1, 0.6), (-1, 0.6), (0.6, -1), (-0.6, -1)):
        pts = [(0.6 * sx, 2.3, 0.5 * sz), (0.85 * sx, 1.4, 0.95 * sz), (0.9 * sx, 0.75, 0.55 * sz),
               (0.95 * sx, 0.05, 0.75 * sz)]
        d = R.smin(d, R.sd_tube(p, pts, [0.38, 0.26, 0.13, 0.10]), 0.2)
        f.add(R.sd_ellipsoid(p, (0.95 * sx, 0.05, 0.75 * sz + 0.06), (0.13, 0.09, 0.15)), k.gear, 0.03)
    for j in range(16):
        a = j * 2 * math.pi / 16 + rng.uniform(-0.2, 0.2)
        c, s_ = math.cos(a), math.sin(a)
        y0 = 2.6 + rng.uniform(-0.6, 0.9)
        reach = rng.uniform(1.6, 2.8)
        up = rng.random() < 0.35
        end_y = y0 + rng.uniform(0.5, 1.6) if up else rng.uniform(0.0, 0.8)
        pts = [(0.8 * c, y0, 0.7 * s_), (reach * 0.55 * c, y0 + (0.6 if up else -0.2), reach * 0.5 * s_),
               (reach * 0.85 * c, (y0 + end_y) / 2, reach * 0.8 * s_), (reach * c + 0.3 * s_, end_y, reach * s_)]
        d = R.smin(d, R.sd_tube(p, pts, [0.22, 0.13, 0.07, 0.015]), 0.12)
    for side in (-1, 1):
        base = np.array([0.45 * side, 3.85, 0.1])
        pts = [base, base + (0.45 * side, 0.55, -0.15), base + (1.05 * side, 0.55, -0.45),
               base + (1.30 * side, 0.05, -0.30), base + (1.05 * side, -0.25, 0.05), base + (0.85 * side, 0.0, 0.2)]
        f.add(R.sd_tube(p, pts, [0.20, 0.18, 0.14, 0.10, 0.06, 0.02]), k.gear, 0.05)
    d = displace(d, p, 0.18, 1.8, seed, 0.4)
    d = displace(d, p, 0.04, 7, seed + 1, 0.1, ridged=True)
    f.add(d, k.skin)
    for _ in range(13):
        th, ph = rng.uniform(-0.3, 0.7), rng.uniform(-1.0, 1.0)
        e = np.array([1.3 * math.sin(ph), 2.9 + 0.9 * th, 1.05 * math.cos(ph)])
        f.add(R.sd_sphere(p, e, rng.uniform(0.05, 0.10)), k.eye)
    return f


def black_goat():
    seed = 431
    k = Kit(skin=1, gear=2, eye=3)
    mats = [
        Material((0.025, 0.022, 0.02), tex=mottled((0.025, 0.022, 0.02), seed, 3, 0.4, 0.2), tex_mode="replace",
                 wrap=0.3, spec=0.9, gloss=40, sss=(0.08, 0.02, 0.02)),
        Material((0.16, 0.13, 0.09), tex=mottled((0.16, 0.13, 0.09), seed + 1, 12, 0.3, 0.3), tex_mode="replace",
                 spec=0.5, gloss=30),
        Material((0.0, 0.0, 0.0), emit=(2.0, 1.1, 0.15)),
    ]
    bark = Material((0.03, 0.03, 0.025))

    def pines(p):
        d = np.full(len(p), 1e9)
        rng = np.random.default_rng(seed + 7)
        for _ in range(22):
            x, z = rng.uniform(-22, 22), rng.uniform(6, 30)
            h = rng.uniform(4, 8)
            q = p - np.array([x, 0, z])
            r = np.sqrt(q[:, 0] ** 2 + q[:, 2] ** 2)
            cone = np.maximum(r - (h - q[:, 1]) * 0.22, -q[:, 1])
            d = np.minimum(d, np.maximum(cone, q[:, 1] - h))
        return d

    def fig(q):
        return black_goat_fig(q, k, seed)

    S = 6.0

    def scene(p):
        f = Field(len(p))
        f.add_group(p, (0.0, 2.6 * S, -4.0), 3.9 * S, lambda q: scaled(fig, q, (0.0, 0, -4.0), 15, S), pad=0.3 * S)
        f.add(pines(p), 4)
        f.add(ground(p / 3.0, seed) * 3.0, 0)
        return f

    gm = Material((0.04, 0.04, 0.03), tex=mud(seed, (0.04, 0.04, 0.03)), tex_mode="replace", spec=0.2)
    cam = Camera((2.0, 2.0, 72.0), (0.0, 14.0, 0.0), 30.0)
    lights = [Light((0.8, 0.7, 0.6), 0.6, direction=(0.8, 0.5, 0.4), softness=10),
              Light((0.9, 0.8, 0.6), 4.0, direction=(0.0, 0.35, -1.0), softness=14),
              Light((0.30, 0.33, 0.40), 0.15, direction=(0.4, 0.5, 0.8), shadow=False)]
    return _scene_icon(seed, [gm] + mats + [bark], [1, 2, 3], scene,
                       dict(top=(0.010, 0.012, 0.009), horizon=(0.17, 0.15, 0.10), glow=(1.0, 0.78, 0.45),
                            glow_at=(0.02, 0.24), glow_size=14.0, clouds=0.9),
                       cam, lights, fog_density=0.010, fog_start=30.0, rim=((0.45, 0.38, 0.25), 2.6),
                       tint=(0.004, 0.006, -0.006), smoke_col=(0.22, 0.22, 0.17), smoke_src=(0.5, 0.25),
                       border=(150, 120, 60), glow=0.3)


def iridescent(seed):
    def tex(p, n):
        ph = n @ np.array([0.5, 0.8, 0.3]) * 2.2 + R.fbm3(p * 0.8, 2, seed) * 1.2
        col = 0.5 + 0.5 * np.cos(2 * math.pi * (ph[:, None] + np.array([0.0, 0.33, 0.67])))
        return 0.12 + 0.55 * col
    return tex


def all_in_one():
    """Yog-Sothoth: a heap of iridescent globes hanging over a ring of
    standing stones."""
    seed = 531
    rng = np.random.default_rng(seed)
    globes = []
    for _ in range(34):
        v = rng.normal(0, 1, 3)
        v = v / np.linalg.norm(v) * rng.uniform(0.0, 1.0) ** 0.5
        globes.append((np.array([v[0] * 4.2, 11.0 + v[1] * 3.0, v[2] * 3.0]), rng.uniform(0.6, 1.7)))
    mats = [
        Material((0.3, 0.3, 0.3), tex=iridescent(seed), tex_mode="replace", spec=2.0, gloss=90, wrap=0.2,
                 emit=lambda p, n: np.array([0.10, 0.12, 0.20]) * (1 + R.fbm3(p * 0.5, 2, seed + 1))[:, None]),
    ]
    stone = Material((0.09, 0.09, 0.10), tex=mottled((0.09, 0.09, 0.10), seed + 2, 1.2, 0.4, 0.3), tex_mode="replace")
    grass = Material((0.04, 0.045, 0.04), tex=mud(seed, (0.04, 0.045, 0.04)), tex_mode="replace", spec=0.2)

    def stones(p):
        d = np.full(len(p), 1e9)
        for j in range(9):
            a = j * 2 * math.pi / 9 + 0.2
            c = np.array([7.5 * math.cos(a), 1.6, 7.5 * math.sin(a) - 2.0])
            d = np.minimum(d, sd_box(p, c, (0.55, 1.8 + 0.4 * math.sin(j * 2.1), 0.35), rot_y(math.degrees(a)), r=0.1))
        return displace(d, p, 0.12, 1.2, seed, 0.3)

    def cluster(p):
        f = Field(len(p))
        d = np.full(len(p), 1e9)
        for c, r in globes:
            d = R.smin(d, R.sd_sphere(p, c, r), 0.25)
        f.add(d, 1)
        return f

    def scene(p):
        f = Field(len(p))
        f.add_group(p, (0.0, 11.0, 0.0), 7.5, cluster, pad=0.2)
        f.add(stones(p), 2)
        f.add(ground(p / 3.0, seed) * 3.0, 0)
        return f

    cam = Camera((1.2, 2.2, 23.0), (0.0, 9.0, 0.0), 36.0)
    lights = [Light((0.7, 0.8, 1.0), 0.9, direction=(0.7, 0.6, 0.5), softness=10),
              Light((0.6, 0.8, 1.0), 2.5, direction=(-0.3, 0.4, -1.0), softness=14),
              Light((0.30, 0.33, 0.40), 0.2, direction=(0.4, 0.5, 0.8), shadow=False)]
    return _scene_icon(seed, [grass] + mats + [stone], [1], scene,
                       dict(top=(0.005, 0.006, 0.014), horizon=(0.10, 0.12, 0.18), glow=(0.5, 0.6, 1.0),
                            glow_at=(0.0, 0.35), glow_size=12.0, stars=0.7),
                       cam, lights, fog_density=0.015, fog_start=25.0, rim=((0.35, 0.40, 0.55), 2.5),
                       tint=(-0.004, 0.0, 0.016), smoke_col=(0.22, 0.25, 0.34), smoke_src=(0.5, 0.25),
                       border=(150, 120, 60), glow=0.4, saturation=0.75)


def azathoth_fragment():
    """A shard of Azathoth boiling over a cratered ruin: a heaving knot of
    blind matter split by nuclear light, tendrils lashing out of it."""
    seed = 631
    rng = np.random.default_rng(seed)

    def core_emit(p, n):
        heat = smoothstep(0.80, 0.97, R.ridged3(p * 0.7, 4, seed))
        return np.array([2.6, 0.6, 2.0]) * heat[:, None] + np.array([3.0, 2.6, 2.8]) * (heat ** 4)[:, None]

    mats = [
        Material((0.05, 0.02, 0.04), tex=mottled((0.05, 0.02, 0.04), seed, 1.5, 0.5, 0.0), tex_mode="replace",
                 spec=0.8, gloss=30, emit=core_emit),
    ]
    rubble = Material((0.06, 0.05, 0.05), tex=mottled((0.06, 0.05, 0.05), seed + 1, 1.0, 0.4, 0.3), tex_mode="replace")
    gm = Material((0.05, 0.04, 0.04), tex=mud(seed, (0.05, 0.04, 0.04)), tex_mode="replace", spec=0.2,
                  emit=lambda p, n: np.array([0.6, 0.15, 0.45]) * np.exp(-((p[:, 0] ** 2 + p[:, 2] ** 2) / 60.0))[:, None])
    blobs = []
    for _ in range(22):
        v = rng.normal(0, 1, 3)
        v = v / np.linalg.norm(v) * rng.uniform(0.3, 1.0)
        blobs.append((np.array([0, 9.5, 0]) + v * np.array([4.0, 3.4, 3.0]), rng.uniform(1.0, 2.4)))
    tendrils = []
    for j in range(14):
        a = j * 2 * math.pi / 14 + rng.uniform(-0.3, 0.3)
        e = rng.uniform(-0.7, 1.0)
        dirv = np.array([math.cos(a) * math.cos(e), math.sin(e), math.sin(a) * math.cos(e)])
        side = np.cross(dirv, (0, 1, 0))
        side = side / (np.linalg.norm(side) + 1e-9)
        up = np.cross(side, dirv)
        pts = [np.array([0, 9.5, 0]) + dirv * 4.2]
        L = rng.uniform(0.8, 1.3)
        for i in range(1, 5):
            ang = i * 0.9
            pts.append(pts[0] + dirv * i * L + (side * math.sin(ang) + up * (1 - math.cos(ang))) * 0.6 * i * L / 2)
        tendrils.append((pts, [0.75, 0.50, 0.30, 0.14, 0.03]))

    def mass(p):
        f = Field(len(p))
        d = np.full(len(p), 1e9)
        for c, r in blobs:
            d = R.smin(d, R.sd_sphere(p, c, r), 0.8)
        for pts, rad in tendrils:
            d = R.smin(d, R.sd_tube(p, pts, rad), 0.6)
        d = displace(d, p, 0.30, 0.6, seed, 0.9)
        d = displace(d, p, 0.06, 3.0, seed + 1, 0.25, ridged=True)
        f.add(d, 1)
        return f

    def ruin(p):
        d = sd_box(p, (-12.0, 2.5, -10.0), (2.0, 2.5, 0.5), rot_y(20))
        d = np.minimum(d, sd_box(p, (11.0, 3.5, -14.0), (0.8, 3.5, 0.8), R.rot_z(-8)))
        d = np.minimum(d, sd_box(p, (7.0, 1.0, 5.0), (2.5, 1.0, 0.5), rot_y(-30)))
        return displace(d, p, 0.3, 0.8, seed + 3, 0.6)

    def scene(p):
        f = Field(len(p))
        f.add_group(p, (0.0, 9.5, 0.0), 12.5, mass, pad=0.5)
        f.add(ruin(p), 2)
        g = ground(p / 3.0, seed) * 3.0
        crater = np.sqrt(p[:, 0] ** 2 + p[:, 2] ** 2)
        g = g + 1.2 * np.exp(-((crater - 8.0) / 2.5) ** 2) - 1.0 * np.exp(-(crater / 6.0) ** 2)
        f.add(g, 0)
        return f

    cam = Camera((2.0, 2.5, 36.0), (0.0, 8.8, 0.0), 32.0)
    lights = [Light((1.0, 0.6, 0.9), 0.7, direction=(0.6, 0.5, 0.6), softness=10),
              Light((1.0, 0.5, 0.9), 1.6, direction=(-0.3, 0.4, -1.0), softness=14),
              Light((1.0, 0.45, 0.85), 0.5, direction=(0.0, -1.0, 0.0), shadow=False)]
    return _scene_icon(seed, [gm] + mats + [rubble], [1], scene,
                       dict(top=(0.006, 0.002, 0.006), horizon=(0.12, 0.035, 0.10), glow=(0.7, 0.2, 0.55),
                            glow_at=(0.0, 0.18), glow_size=14.0, clouds=1.0),
                       cam, lights, fog_density=0.012, fog_start=25.0, rim=((0.5, 0.2, 0.4), 2.5),
                       tint=(0.016, -0.006, 0.012), smoke_col=(0.35, 0.14, 0.30), smoke_src=(0.5, 0.3),
                       border=(150, 120, 60), glow=0.6, saturation=0.65)


ICONS = {
    "eldritch_deep_one_brood": deep_one_brood,
    "eldritch_star_spawn": star_spawn,
    "eldritch_faceless_cult": faceless_cult,
    "eldritch_shantak_riders": shantak_riders,
    "eldritch_yellow_zealots": yellow_zealots,
    "eldritch_byakhee_riders": byakhee_riders,
    "eldritch_dark_young": dark_young,
    "eldritch_thousand_young": thousand_young,
    "eldritch_gate_wardens": gate_wardens,
    "eldritch_dunwich_horror": dunwich_horror,
    "eldritch_chaos_spawn": chaos_spawn,
    "eldritch_void_pipers": void_pipers,
    "eldritch_lidless": lidless,
    "eldritch_audience": audience,
    "eldritch_cassildas_choir": cassildas_choir,
    "eldritch_pallid_masks": pallid_masks,
    "eldritch_kings_tatters": kings_tatters,
    "eldritch_halis_drowned": halis_drowned,
    "eldritch_cthulhu_incarnate": great_cthulhu,
    "eldritch_nyarlathotep_incarnate": crawling_chaos,
    "eldritch_hastur_incarnate": king_in_yellow,
    "eldritch_shub_niggurath_incarnate": black_goat,
    "eldritch_yog_sothoth_incarnate": all_in_one,
    "eldritch_azathoth_incarnate": azathoth_fragment,
}


# ---------------------------------------------------------------------------
# GAME TEXTURES
#
# The game reads a battalion's icons as two frames side by side: the picture,
# and the NATO symbol shown when the player switches to NATO counters.
#   GFX_unit_<unit>_icon_medium        152 x 42 (two 76 x 42 frames): the
#                                      division designer and unit panels
#   GFX_unit_<unit>_icon_medium_white  60 x 12 (two 30 x 12 frames): the small
#                                      light icon inside a division's counter
#                                      on the map
# ---------------------------------------------------------------------------

DESIGNER_FRAME = (76, 42)
MAP_FRAME = (30, 12)

# NATO symbol per battalion: the role it plays.
NATO = {
    "eldritch_deep_one_brood": "infantry",
    "eldritch_star_spawn": "armour",
    "eldritch_faceless_cult": "infantry",
    "eldritch_shantak_riders": "cavalry",
    "eldritch_yellow_zealots": "infantry",
    "eldritch_byakhee_riders": "air_cavalry",
    "eldritch_dark_young": "armour",
    "eldritch_thousand_young": "infantry",
    "eldritch_gate_wardens": "infantry",
    "eldritch_dunwich_horror": "armour",
    "eldritch_chaos_spawn": "infantry",
    "eldritch_void_pipers": "artillery",
    "eldritch_lidless": "infantry",
    "eldritch_audience": "infantry",
    "eldritch_cassildas_choir": "artillery",
    "eldritch_pallid_masks": "infantry",
    "eldritch_kings_tatters": "armour",
    "eldritch_halis_drowned": "infantry",
}


def nato_frame(kind, frame, box, line):
    """A NATO counter symbol: a light box with the role's mark, centred in a
    transparent frame. Drawn at the frame's own resolution so lines stay crisp."""
    from PIL import ImageDraw
    fw, fh = frame
    bw, bh = box
    img = Image.new("RGBA", frame, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0, y0 = (fw - bw) // 2, (fh - bh) // 2
    x1, y1 = x0 + bw - 1, y0 + bh - 1
    dark = (22, 20, 18, 255)
    fill = (225, 192, 90, 255) if kind == "god" else (214, 208, 190, 255)
    d.rectangle([x0, y0, x1, y1], fill=fill, outline=dark, width=line)
    ix0, iy0, ix1, iy1 = x0 + line, y0 + line, x1 - line, y1 - line
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if kind == "infantry":
        d.line([ix0, iy0, ix1, iy1], fill=dark, width=line)
        d.line([ix0, iy1, ix1, iy0], fill=dark, width=line)
    elif kind == "armour":
        ew, eh = (ix1 - ix0) * 0.30, (iy1 - iy0) * 0.30
        d.ellipse([cx - ew, cy - eh, cx + ew, cy + eh], outline=dark, width=line)
    elif kind in ("cavalry", "air_cavalry"):
        d.line([ix0, iy1, ix1, iy0], fill=dark, width=line)
        if kind == "air_cavalry":
            r = (ix1 - ix0) * 0.14
            d.arc([cx - r, iy1 - r * 0.9, cx + r, iy1 + r * 0.9], 180, 360, fill=dark, width=line)
    elif kind == "artillery":
        r = max(1.0, (iy1 - iy0) * 0.22)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=dark)
    elif kind == "god":
        r = (iy1 - iy0) * 0.48
        pts = [(cx + r * (1 if k % 2 == 0 else 0.42) * math.sin(math.radians(k * 36)),
                cy - r * (1 if k % 2 == 0 else 0.42) * math.cos(math.radians(k * 36))) for k in range(10)]
        d.polygon(pts, fill=dark)
    return img


def map_silhouette(coverage, frame=MAP_FRAME):
    """The figures' silhouette, cropped to them and fitted into a small frame:
    light, with a dark rim so it reads on any counter colour."""
    fw, fh = frame
    img = Image.new("RGBA", frame, (0, 0, 0, 0))
    cov = np.clip(np.asarray(coverage, float), 0, 1)
    ys, xs = np.where(cov > 0.3)
    if ys.size == 0:
        return img
    cov = cov[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = cov.shape
    k = min((fw - 2) / w, (fh - 2) / h)
    sw, sh = max(1, round(w * k)), max(1, round(h * k))
    a = np.asarray(Image.fromarray((cov * 255).astype(np.uint8)).resize((sw, sh), Image.LANCZOS)).astype(float) / 255
    a = np.clip((a - 0.2) * 1.8, 0, 1)
    alpha = Image.fromarray((a * 255).astype(np.uint8))
    x, y = (fw - sw) // 2, (fh - sh) // 2
    rim = Image.new("L", frame, 0)
    rim.paste(alpha, (x, y))
    rim = rim.filter(ImageFilter.MaxFilter(3))
    img.paste(Image.new("RGBA", frame, (24, 22, 20, 255)), (0, 0), rim)
    body = Image.new("RGBA", (sw, sh), (238, 236, 228, 255))
    img.paste(body, (x, y), alpha)
    return img


def textures(unit):
    """(designer texture, map texture) for a battalion, in the game's layouts."""
    picture, coverage = ICONS[unit]()
    kind = NATO.get(unit, "god")
    fw, fh = DESIGNER_FRAME
    designer = Image.new("RGBA", (fw * 2, fh), (0, 0, 0, 0))
    designer.paste(picture, ((fw - picture.width) // 2, (fh - picture.height) // 2))
    designer.alpha_composite(nato_frame(kind, DESIGNER_FRAME, (52, 30), 2), (fw, 0))
    mw, mh = MAP_FRAME
    small = Image.new("RGBA", (mw * 2, mh), (0, 0, 0, 0))
    small.alpha_composite(map_silhouette(coverage), (0, 0))
    small.alpha_composite(nato_frame(kind, MAP_FRAME, (26, 12), 1), (mw, 0))
    return designer, small
