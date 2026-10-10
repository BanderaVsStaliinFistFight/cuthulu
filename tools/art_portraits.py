"""Avatar portraits (156x210): sculpted subjects lit by a single hard lamp and
printed like damaged 1920s photographs - low key, smoky, near-monochrome,
grainy and scratched. Each portrait function returns an RGBA PIL image.

Subjects face +Z with their heads around y = 1.7 (metres)."""

import math

import numpy as np

import art_render as R
from art_render import Field, Material, Camera, Light, smoothstep

PORTRAIT_SIZE = (156, 210)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def gloom(seed, base=(0.012, 0.010, 0.008), glow=(0.0, 0.0, 0.0), glow_at=(0.0, 0.1), glow_size=30.0):
    """Near-black background with faint drifting smoke and an optional glow."""
    base, glow = np.asarray(base, float), np.asarray(glow, float)

    def bg(rd):
        cl = np.clip(R.fbm3(rd * np.array([4, 7, 4]) + 3, 6, seed) * 1.8 + 0.15, -0.5, 1.3)[:, None]
        g = np.exp(-((rd[:, 0] - glow_at[0]) ** 2 + (rd[:, 1] - glow_at[1]) ** 2) * glow_size)[:, None]
        return base * (1 + 1.3 * cl) + glow * g * (0.4 + 0.8 * np.clip(cl, 0, 1))
    return bg


def print_finish(out, seed, sat=0.3, sepia=0.55, contrast=1.3, exposure=1.0, shadows=(0, 0, 0),
                 highlights=(0, 0, 0), focus=None, smoke=0.25, smoke_src=(0.25, 0.1), vig=0.85, grain=0.08,
                 scratches=2):
    """Develop a render like an old, worn photographic print."""
    img = R.tonemap(out["rgb"], exposure)
    if focus is not None:
        img = R.depth_of_field(img, out["depth"], *focus)
    if smoke:
        img = R.smoke(img, out["depth"], seed, smoke, (0.42, 0.38, 0.32), smoke_src, 3.0,
                      far=(focus[0] - 0.2, focus[0] + 0.8) if focus else None)
    img = R.grade(img, saturation=sat, shadows=shadows, highlights=highlights, contrast=contrast, black=0.05)
    img = R.sepia(img, sepia)
    img = R.blur(img, 0.15)  # slightly soft old lens
    img = R.halation(img, 0.8, 2.0, 0.25)
    img = R.vignette(img, vig, 1.8)
    img = R.film(img, seed, grain=grain, dust=0.6, scratches=scratches, scratch_strength=0.16, blotches=0.12)
    return R.to_image(img)


def frame_axes(direction, flat_normal):
    """Rotation whose columns are (width, length, thickness) axes for a long
    flat part pointing along direction."""
    v = R.normalize(direction)
    w = R.normalize(np.asarray(flat_normal, float) - v * (np.dot(flat_normal, v)))
    u = np.cross(v, w)
    return np.column_stack([u, v, w])


def rough_cloth_tex(color, seed, grime_y=None, stain=0.5, grime_col=(0.06, 0.05, 0.035)):
    """Heavy, filthy cloth: coarse weave, blotches, stains, grime from below."""
    color, grime_col = np.asarray(color, float), np.asarray(grime_col, float)

    def tex(p, n):
        wv = 0.88 + 0.12 * np.sin(p[:, 0] * 300 + 2 * R.noise3(p * 40, seed)) * np.sin(p[:, 1] * 300)
        mott = 1 + 0.35 * R.fbm3(p * 14, 4, seed)
        st = 1 - stain * np.clip(R.fbm3(p * 4 + 3, 5, seed + 3) * 1.8, 0, 1)
        col = color * (wv * mott * st)[:, None]
        if grime_y is not None:
            g = smoothstep(grime_y, grime_y - 0.4, p[:, 1] + 0.1 * R.fbm3(p * 6, 3, seed + 9))[:, None]
            col = col * (1 - 0.75 * g) + grime_col * 0.75 * g
        return col
    return tex


def drapery(p, amount, count, seed, axis_center=(0.0, 0.0), top=1.5):
    """Hanging folds round a body: irregular ridges by angle that wander,
    merge and deepen toward the hem, finer creases, and lumpy heavy cloth."""
    ang = np.arctan2(p[:, 0] - axis_center[0], p[:, 2] - axis_center[1])
    wob = 1.8 * R.fbm3(p * np.array([2.5, 0.7, 2.5]), 3, seed)
    depth = np.clip(0.35 + (top - p[:, 1]) * 1.4, 0.3, 1.6) * (0.5 + 0.7 * np.abs(R.noise3(p * 3, seed + 1)))
    big = np.abs(np.sin(ang * count / 2 + wob)) ** 0.8
    fine = np.abs(np.sin(ang * count * 1.7 + 2.5 * wob + 1.0)) ** 1.5
    lumps = 0.15 * R.fbm3(p * 22, 3, seed + 4)
    return amount * (depth * (0.7 * big + 0.3 * fine) + lumps)


# ---------------------------------------------------------------------------
# Human-proportioned parts (a 1.80 m figure: head 0.23 m tall and 0.155 m
# wide, shoulders 0.44 m, upper arm 0.28 m, forearm 0.27 m, hand 0.19 m)
# ---------------------------------------------------------------------------

def hand_frame(along, across, palm_toward=None):
    """Unit axes for a hand: a = fingers' direction, b = across the knuckles
    toward the thumb, c = out of the palm."""
    a = R.normalize(np.asarray(along, float))
    b = np.asarray(across, float)
    b = R.normalize(b - a * np.dot(a, b))
    c = np.cross(a, b)
    if palm_toward is not None and np.dot(c, palm_toward) < 0:
        c = -c
    return a, b, c


def bony_hand(p, wrist, a, b, c, curl, seed, thumb_curl=0.3):
    """A gaunt hand of real size: palm, four jointed fingers with knobbly
    knuckles curling toward the palm by `curl` radians per joint, and a thumb."""
    wrist = np.asarray(wrist, float)
    d = R.sd_ellipsoid(p, wrist + a * 0.046, (0.038, 0.050, 0.011), np.column_stack([b, a, c]))
    d = R.smin(d, R.sd_ellipsoid(p, wrist + a * 0.006, (0.026, 0.020, 0.016), np.column_stack([b, a, c])), 0.015)
    lengths = [(0.040, 0.025, 0.020), (0.046, 0.029, 0.022), (0.043, 0.027, 0.021), (0.034, 0.021, 0.018)]
    for i in range(4):
        off = (1.5 - i) * 0.0185  # index finger on the thumb side
        pts = [wrist + a * 0.094 + b * off - c * 0.002]
        ang = 0.0
        for k, ln in enumerate(lengths[i]):
            ang += curl * (0.8 + 0.2 * k)
            spread = b * (off * 0.25)
            dirv = R.normalize(a * math.cos(ang) + c * math.sin(ang) + spread)
            pts.append(pts[-1] + dirv * ln)
        finger = R.sd_tube(p, pts, [0.0078, 0.0066, 0.0056, 0.0040])
        for k in (0, 1, 2):
            finger = R.smin(finger, R.sd_sphere(p, pts[k], 0.0088 - k * 0.0012), 0.004)
        d = R.smin(d, finger, 0.006)
    t0 = wrist + a * 0.025 + b * 0.030 + c * 0.006
    t1 = t0 + R.normalize(a * 0.6 + b * 0.8 + c * thumb_curl) * 0.042
    t2 = t1 + R.normalize(a * 0.9 + b * 0.3 + c * thumb_curl * 1.6) * 0.032
    t3 = t2 + R.normalize(a * 0.8 + b * 0.1 + c * thumb_curl * 2.2) * 0.025
    thumb = R.sd_tube(p, [t0, t1, t2, t3], [0.010, 0.0085, 0.0068, 0.0045])
    thumb = R.smin(thumb, R.sd_sphere(p, t1, 0.0095), 0.004)
    d = R.smin(d, thumb, 0.008)
    near = np.abs(d) < 0.006
    if near.any():  # tendons and dry, wrinkled skin
        d[near] -= 0.0008 * R.fbm3(p[near] * 260, 2, seed) + 0.0007 * R.ridged3(p[near] * 120, 2, seed + 1)
    return d


# ---------------------------------------------------------------------------
# The King in Yellow (Hastur's avatar, "The Pallid Mask")
# ---------------------------------------------------------------------------

def king_setup():
    """Scene function, materials and seed for the King in Yellow."""
    seed = 21
    ochre = (0.33, 0.235, 0.075)
    bone_col = (0.47, 0.43, 0.34)
    rng = np.random.default_rng(seed)

    def bone_tex(p, n):
        crack = smoothstep(0.87, 0.97, R.ridged3(p * 30, 4, seed))
        stain = np.clip(R.fbm3(p * 7, 5, seed + 4) * 1.6 + 0.25, 0, 1)
        col = np.asarray(bone_col) * (0.8 + 0.3 * R.fbm3(p * 26, 3, seed + 1))[:, None]
        col = col * (1 - 0.55 * stain)[:, None] + np.array([0.13, 0.10, 0.05]) * (0.55 * stain)[:, None]
        return col * (1 - 0.85 * crack)[:, None]

    def hand_tex(p, n):  # parchment skin over bone, darker in the creases
        col = np.array([0.30, 0.25, 0.18]) * (0.8 + 0.3 * R.fbm3(p * 60, 3, seed + 6))[:, None]
        return col * (1 - 0.4 * smoothstep(0.8, 0.95, R.ridged3(p * 120, 2, seed + 1)))[:, None]

    def gold_tex(p, n):
        tarn = np.clip(R.fbm3(p * 35, 4, seed + 7) * 2.0 + 0.45, 0, 1)
        return np.array([0.58, 0.43, 0.16]) * (1 - 0.7 * tarn)[:, None] + np.array([0.07, 0.07, 0.04]) * (0.7 * tarn)[:, None]

    def feather_tex(p, n):
        base = np.array([0.30, 0.22, 0.22]) * (1 + 0.4 * R.fbm3(p * 9, 4, seed + 5))[:, None]
        barbs = 0.8 + 0.2 * np.sin((np.abs(p[:, 0]) * 0.6 + p[:, 1]) * 650 + 3 * R.noise3(p * 50, seed))
        return base * (barbs * (1 - 0.5 * smoothstep(1.6, 1.0, p[:, 1])))[:, None]

    mats = [
        Material(ochre, tex=rough_cloth_tex(ochre, seed, grime_y=1.15), tex_mode="replace", wrap=0.4, spec=0.03,
                 gloss=5, sheen=0.4),                                                     # 0 robe
        Material((0.22, 0.025, 0.02), wrap=0.3, spec=0.2, gloss=25, sheen=0.3),          # 1 dried-blood trim
        Material(bone_col, tex=bone_tex, tex_mode="replace", wrap=0.1, spec=0.25, gloss=28),     # 2 bone mask
        Material((0.004, 0.003, 0.002)),                                                 # 3 eye holes
        Material((0.58, 0.43, 0.16), tex=gold_tex, tex_mode="replace", spec=0.9, gloss=45),      # 4 tarnished gold
        Material((0.30, 0.22, 0.22), tex=feather_tex, tex_mode="replace", wrap=0.35, spec=0.05, gloss=10,
                 sheen=0.6),                                                              # 5 feathers
        Material((0.14, 0.11, 0.06), spec=0.5, gloss=35),                                # 6 blackened rod
        Material((0.9, 0.75, 0.3), emit=np.array([0.30, 0.22, 0.04])),                  # 7 eyes glinting inside
        Material((0.10, 0.07, 0.06), spec=0.1, gloss=20),                                # 8 feather shafts
        Material((0.30, 0.25, 0.18), tex=hand_tex, tex_mode="replace", wrap=0.3, spec=0.12, gloss=18,
                 sss=(0.25, 0.08, 0.04)),                                                 # 9 hands
    ]

    # ----- the head: a life-size bird-skull mask in a fitted hood -----------
    spikes = []
    for k, ang in enumerate([0, 45, -44, 92, -94, 140, -138]):
        h = (0.130 if k == 0 else 0.085 - 0.007 * (k // 2)) + rng.normal(0, 0.006)
        spikes.append((math.radians(ang + rng.normal(0, 4)), h, rng.normal(0, 0.006, 2), 0.0075 if k == 0 else 0.006))

    def head(p):
        f = Field(len(p))
        q = R.mirror_x(p)
        # hood fitted round a 0.155 m wide head, flowing into a capelet over the shoulders
        hood = np.abs(R.sd_ellipsoid(p, (0, 1.712, -0.018), (0.094, 0.122, 0.115))) - 0.008
        # the hood flares down into a cowl bunched round the neck and shoulders
        flare = np.abs(R.sd_round_cone(p, (0, 1.62, -0.025), (0, 1.52, -0.03), 0.090, 0.125)) - 0.008
        cloth = R.smin(hood, flare, 0.04)
        cloth = R.smax(cloth, 1.50 - p[:, 1], 0.02)
        opening = R.sd_ellipsoid(p, (0, 1.685, 0.095), (0.064, 0.108, 0.075))
        cloth = R.smax(cloth, -opening, 0.012)
        near = np.abs(cloth) < 0.02
        if near.any():
            cq = p[near]
            cloth[near] -= 0.006 * np.abs(np.sin(np.arctan2(cq[:, 0], cq[:, 2] + 0.06) * 8
                                                 + 2.5 * R.fbm3(cq * 8, 3, seed))) ** 0.8 \
                + 0.002 * R.fbm3(cq * 40, 3, seed + 2)
        f.add(cloth, 0)
        f.add(np.maximum(cloth - 0.002, np.abs(opening) - 0.005), 1)
        # the mask over a human face: brow, sockets, a curved beak 0.2 m long
        mask = R.sd_ellipsoid(p, (0, 1.700, 0.004), (0.074, 0.100, 0.094))
        mask = R.smin(mask, R.sd_ellipsoid(q, (0.030, 1.712, 0.078), (0.030, 0.014, 0.020)), 0.012)  # brow
        pb = p * np.array([1.45, 1.0, 1.0])
        beak = R.sd_tube(pb, [(0, 1.676, 0.080), (0, 1.645, 0.132), (0, 1.602, 0.172), (0, 1.556, 0.194),
                              (0, 1.522, 0.196), (0, 1.505, 0.186)],
                         [0.034, 0.024, 0.016, 0.009, 0.0045, 0.0015]) / 1.45
        mask = R.smin(mask, beak, 0.025)
        keel = R.sd_tube(p, [(0, 1.690, 0.104), (0, 1.630, 0.160), (0, 1.565, 0.200)], [0.004, 0.0035, 0.002])
        mask = R.smin(mask, keel, 0.006)
        sockets = R.sd_ellipsoid(q, (0.032, 1.700, 0.086), (0.017, 0.012, 0.03), R.rot_z(-15))
        mask = R.smax(mask, -sockets, 0.004)
        mask = R.smax(mask, -R.sd_ellipsoid(q, (0.009, 1.652, 0.132), (0.0022, 0.016, 0.005), R.rot_x(42)), 0.002)
        near = np.abs(mask) < 0.008
        if near.any():
            mq = p[near]
            mask[near] += 0.0015 * smoothstep(0.87, 0.97, R.ridged3(mq * 30, 4, seed)) \
                + 0.0005 * R.fbm3(mq * 220, 2, seed + 3)
        f.add(mask, 2)
        f.add(R.sd_ellipsoid(q, (0.032, 1.700, 0.072), (0.016, 0.011, 0.012), R.rot_z(-15)), 3)
        f.add(R.sd_sphere(q, (0.032, 1.699, 0.074), 0.0022), 7)
        # crown sized to the hooded head: a 3.5 cm band, spikes 7-13 cm
        ring = np.sqrt((p[:, 0] / 0.084) ** 2 + ((p[:, 2] + 0.016) / 0.100) ** 2)
        band = np.maximum(np.abs(ring - 1.0) * 0.09 - 0.0045 - 0.0015 * R.noise3(p * 60, seed),
                          np.abs(p[:, 1] - 1.800) - 0.0175)
        crown = band
        for a, h, lean, r0 in spikes:
            bx, bz = 0.085 * math.sin(a), 0.101 * math.cos(a) - 0.016
            tx, tz = 0.092 * math.sin(a) + lean[0], 0.109 * math.cos(a) - 0.016 + lean[1]
            crown = R.smin(crown, R.sd_round_cone(p, (bx, 1.812, bz), (tx, 1.812 + h, tz), r0, 0.0010), 0.006)
            crown = np.minimum(crown, R.sd_sphere(p, (tx, 1.812 + h - 0.008, tz), r0 * 0.6))
        near = np.abs(crown) < 0.005
        if near.any():
            crown[near] += 0.0010 * np.abs(R.noise3(p[near] * 150, seed + 8))
        f.add(crown, 4)
        return f

    # ----- the body under the robe -------------------------------------------
    shoulder = {sx: np.array([sx * 0.190, 1.445, -0.035]) for sx in (1, -1)}
    elbow = {1: np.array([0.245, 1.185, 0.025]), -1: np.array([-0.235, 1.170, 0.030])}
    wrist = {1: np.array([0.175, 1.420, 0.150]), -1: np.array([-0.105, 1.290, 0.170])}
    # left hand (+x) raised open beside the beak, palm out; right hand (-x) grips the scepter
    open_axes = hand_frame((0.10, 1.0, 0.12), (-1.0, 0.0, 0.08), palm_toward=(0, 0, 1))
    grip_axes = hand_frame((0.25, 0.10, 1.0), (0.0, 1.0, 0.0), palm_toward=(1, 0, 0))
    ga, gb, gc = grip_axes
    rod_c = wrist[-1] + ga * 0.075 + gc * 0.028

    def body(p):
        f = Field(len(p))
        chest = R.sd_ellipsoid(p, (0, 1.32, -0.025), (0.165, 0.19, 0.115))
        belly = R.sd_ellipsoid(p, (0, 1.08, -0.015), (0.150, 0.20, 0.110))
        traps = np.minimum(R.sd_round_cone(p, (0, 1.53, -0.04), shoulder[1], 0.06, 0.05),
                           R.sd_round_cone(p, (0, 1.53, -0.04), shoulder[-1], 0.06, 0.05))
        torso = R.smin(R.smin(chest, belly, 0.08), traps, 0.06)
        # the robe hangs from the chest, falling loose and widening to the floor
        skirt = R.sd_round_cone(p, (0, 1.20, -0.025), (0, 0.40, -0.03), 0.175, 0.27)
        robe = R.smin(torso + 0.012, skirt, 0.10)
        # the hood's cowl, bunched round the neck and falling onto the chest
        cowl = R.sd_torus(p, (0, 1.525, -0.035), 0.098, 0.040, R.rot_x(-6))
        bib = R.sd_ellipsoid(p, (0, 1.43, 0.03), (0.13, 0.09, 0.07))
        robe = R.smin(robe, R.smin(cowl, bib, 0.05), 0.05)
        near = np.abs(robe) < 0.03
        if near.any():
            robe[near] -= drapery(p[near], 0.010, 22, seed, (0.0, -0.03), top=1.40)
        f.add(robe, 0)
        # dried-blood ribbon down the front opening
        f.add(np.maximum(robe - 0.003, np.abs(p[:, 0] + 0.012 * np.sin(p[:, 1] * 8) + 0.004 * R.noise3(p * 30, seed))
                         - 0.013), 1)
        for sx in (1, -1):
            # sleeve over upper arm and forearm, a wide mouth hanging under the wrist
            up = R.sd_round_cone(p, shoulder[sx], elbow[sx], 0.050, 0.045)
            fore = R.sd_round_cone(p, elbow[sx], wrist[sx] - (wrist[sx] - elbow[sx]) * 0.05, 0.045, 0.055)
            mid = (elbow[sx] + wrist[sx]) / 2
            hang = R.sd_ellipsoid(p, mid + np.array([0, -0.075, 0.0]), (0.035, 0.10, 0.05),
                                  R.rot_z(sx * 25))
            sleeve = R.smin(R.smin(up, fore, 0.04), hang, 0.06)
            mouth = R.sd_sphere(p, wrist[sx] + R.normalize(wrist[sx] - elbow[sx]) * 0.03, 0.042)
            sleeve = R.smax(sleeve, -mouth, 0.01)
            near = np.abs(sleeve) < 0.03
            if near.any():
                sq = p[near]
                fold = (sq - elbow[sx]) @ R.normalize(wrist[sx] - elbow[sx]) + 0.4 * R.fbm3(sq * 6, 3, seed + sx)
                sleeve[near] -= 0.007 * np.abs(np.sin(fold * 55)) ** 0.8 * (0.4 + 0.6 * np.abs(R.noise3(sq * 7, seed))) \
                    + 0.002 * R.fbm3(sq * 30, 2, seed)
            f.add(sleeve, 0, 0.02)
            # frayed red cuff at the sleeve mouth
            cuff_axis = R.normalize(wrist[sx] - elbow[sx])
            cuff = np.maximum(np.abs(sleeve) - 0.004,
                              np.abs((p - wrist[sx]) @ cuff_axis + 0.005) - 0.012)
            f.add(cuff, 1)
        return f

    def hands(p):
        f = Field(len(p))
        oa, ob, oc = open_axes
        f.add(bony_hand(p, wrist[1], oa, ob, oc, 0.18, seed), 9)
        f.add(bony_hand(p, wrist[-1], ga, gb, gc, 1.05, seed + 1, thumb_curl=0.9), 9)
        # the scepter: a blackened rod topped with a pierced, key-like head
        f.add(R.sd_capsule(p, (rod_c[0], 0.95, rod_c[2]), (rod_c[0], 1.78, rod_c[2]), 0.0065), 6)
        top = np.array([rod_c[0], 1.835, rod_c[2]])
        knob = np.minimum(R.sd_torus(p, top, 0.030, 0.0065, R.rot_x(90)), R.sd_torus(p, top, 0.013, 0.0045, R.rot_x(90)))
        knob = np.minimum(knob, R.sd_round_cone(p, top + np.array([0, 0.030, 0]), top + np.array([0, 0.065, 0]), 0.008, 0.001))
        knob = np.minimum(knob, R.sd_sphere(p, top - np.array([0, 0.040, 0]), 0.012))
        f.add(knob, 4)
        return f

    # ----- life-size wings ---------------------------------------------------
    def wing_parts(sx):
        arm = [np.array([sx * 0.08, 1.42, -0.15]), np.array([sx * 0.32, 1.80, -0.30]),
               np.array([sx * 0.56, 1.98, -0.40]), np.array([sx * 0.82, 1.90, -0.48])]
        wr = np.random.default_rng(7 if sx > 0 else 8)
        out = []
        for length_, width, count, back in [(0.13, 0.034, 18, 0.0), (0.34, 0.040, 16, 0.016), (0.56, 0.044, 14, 0.032)]:
            for k in range(count):
                t = (k + 0.5) / count
                seg = min(int(t * 3), 2)
                u = t * 3 - seg
                root = arm[seg] * (1 - u) + arm[seg + 1] * u
                spread = -0.55 + 1.15 * t + 0.07 * wr.normal()
                dirv = np.array([sx * math.sin(spread), -math.cos(spread), -0.18 + 0.08 * wr.normal()])
                L = length_ * (0.65 + 0.7 * t) * (1 + 0.12 * wr.normal())
                c = root + R.normalize(dirv) * L * 0.5 + np.array([0, 0, -back])
                out.append((c, frame_axes(dirv, np.array([0.0, 0.2, 1.0])), (width * (0.8 + 0.4 * t), L * 0.5, 0.006)))
        return out, arm

    wings = {sx: wing_parts(sx) for sx in (1, -1)}

    def wing(p, sx):
        f = Field(len(p))
        feathers, arm = wings[sx]
        d = R.sd_tube(p, arm, [0.040, 0.032, 0.022, 0.010])
        shafts = np.full(len(p), 1e9)
        for c, axes, radii in feathers:
            d = np.minimum(d, R.sd_ellipsoid(p, c, radii, axes))
            v = axes[:, 1] * radii[1] * 0.95
            shafts = np.minimum(shafts, R.sd_capsule(p, c - v + axes[:, 2] * 0.0035, c + v * 0.8 + axes[:, 2] * 0.0035, 0.0024))
        near = np.abs(d) < 0.012
        if near.any():
            d[near] += 0.005 * np.clip(R.fbm3(p[near] * 45, 3, seed + 2), 0, 1)
        f.add(d, 5)
        f.add(shafts, 8)
        return f

    def scene(p):
        f = Field(len(p))
        f.add_group(p, (0, 1.80, 0.06), 0.30, head)
        f.add_group(p, (0, 1.05, -0.03), 0.60, body)
        f.add_group(p, (0.03, 1.40, 0.15), 0.48, hands)
        for sx in (1, -1):
            f.add_group(p, (sx * 0.50, 1.55, -0.32), 0.72, lambda q, s=sx: wing(q, s))
        return f

    return scene, mats, seed


def king_in_yellow():
    scene, mats, seed = king_setup()
    cam = Camera((0.95, 1.50, 3.0), (0.0, 1.50, 0.0), fov=21.5)
    lights = [
        # one hard lamp high on the camera's side, pooled on the mask and crown
        Light((1.0, 0.82, 0.55), 3.4, pos=(1.55, 2.9, 1.75), aim=(0.0, 1.58, 0.05), cone=(11, 30),
              softness=22, falloff=0.12),
        Light((0.50, 0.56, 0.68), 0.22, direction=(-0.9, 0.2, 0.4), shadow=False),
        Light((0.55, 0.62, 0.75), 1.0, direction=(-0.45, 0.5, -0.75), softness=10),
    ]
    bg = gloom(seed, base=(0.010, 0.008, 0.006), glow=(0.09, 0.065, 0.02), glow_at=(0.08, 0.10), glow_size=14)
    out = R.render(scene, mats, cam, lights, PORTRAIT_SIZE, ss=3, background=bg, ambient=(0.014, 0.013, 0.011),
                   rim=((0.02, 0.016, 0.01), 3.0), ao_scale=0.12, max_dist=7.0, shadow_dist=3.0)
    return print_finish(out, seed, sat=0.40, sepia=0.42, contrast=1.22, exposure=1.05,
                        shadows=(0.0, 0.004, 0.008), highlights=(0.02, 0.01, -0.02), focus=(3.05, 0.9, 0.8),
                        smoke=0.16, smoke_src=(0.8, 0.1))


# ---------------------------------------------------------------------------
# 2D (inked and hand-coloured) versions
# ---------------------------------------------------------------------------

def gritty_paper_finish(img, seed, grain=0.035, vig=0.25):
    """Age a finished drawing: paper grain, a little foxing over the ink, a
    soft darkening toward the edges."""
    img = R.vignette(img, vig, 2.0)
    return R.film(img, seed, grain=grain, dust=0.25, scratches=1, scratch_strength=0.08, blotches=0.08)


def king_in_yellow_2d():
    scene, mats, seed = king_setup()
    ss = 4
    cam = Camera((0.0, 1.50, 3.0), (0.0, 1.50, 0.0), fov=21.5)
    lights = [Light((1.0, 0.95, 0.85), 2.0, direction=(-0.55, 0.65, 0.55), softness=14),
              Light((0.7, 0.75, 0.85), 0.35, direction=(0.8, 0.2, 0.5), shadow=False)]
    gb = R.render(scene, mats, cam, lights, PORTRAIT_SIZE, ss=ss, ambient=(0.25, 0.25, 0.25),
                  ao_scale=0.10, max_dist=7.0, shadow_dist=3.0, full=True)
    colors = {
        0: (0.80, 0.64, 0.24),   # mustard robe
        1: (0.70, 0.13, 0.11),   # red ribbons
        2: (0.90, 0.84, 0.66),   # bone mask
        3: (0.08, 0.06, 0.05),   # eye holes
        4: (0.86, 0.67, 0.25),   # gold
        5: (0.78, 0.61, 0.63),   # dusty pink feathers
        6: (0.42, 0.32, 0.18),   # scepter rod
        7: (0.95, 0.80, 0.35),   # glints
        8: (0.66, 0.50, 0.52),   # feather shafts
        9: (0.86, 0.78, 0.60),   # bony hands
    }
    H, W = gb["mat"].shape
    paper = R.aged_paper((W, H), seed)
    img = R.ink_illustration(gb, colors, PORTRAIT_SIZE, paper=paper, hatch_spacing=6.0, seed=seed,
                             ignore_crease=(5, 8), same={8: 5})
    return R.to_image(gritty_paper_finish(img, seed))


# ---------------------------------------------------------------------------
# Painted (2D) portraits
# ---------------------------------------------------------------------------

def king_in_yellow_painted():
    """The King in Yellow as a dry-brush acrylic on black canvas: a tall
    pointed hood round a void, arms spread under curtain-like sleeves, the
    robe parted on darkness, a bony hand, a staff, and something stirring
    in the dark between the robes."""
    import art_paint as A
    seed = 33
    P = A.Painter(PORTRAIT_SIZE, scale=2, seed=seed)
    rng = P.rng
    # matte acrylic: raw umber shadows, yellow ochre, a little cadmium, a buff highlight
    ochre = A.ramp([(0.0, (0.05, 0.035, 0.012)), (0.25, (0.36, 0.22, 0.04)), (0.5, (0.80, 0.55, 0.10)),
                    (0.72, (0.92, 0.67, 0.15)), (0.88, (0.96, 0.78, 0.30)), (1.0, (0.96, 0.88, 0.60))])

    def nz(s, t, k, fs=3.0, ft=3.0):
        return float(R.fbm3(np.array([[s * fs + k * 1.7, t * ft, k * 0.7]]), 4, seed)[0])

    # ----- background: black canvas worked over with near-black strokes -----
    for _ in range(160):
        x, y = rng.uniform(-0.1, 1.1), rng.uniform(-0.1, 1.1)
        a = rng.uniform(0, math.pi)
        L = rng.uniform(0.15, 0.5)
        pts = np.array([[x + math.cos(a) * L * u, y + math.sin(a) * L * u + 0.03 * math.sin(u * 4)]
                        for u in np.linspace(0, 1, 16)])
        v = rng.uniform(0.035, 0.085)
        P.stroke(pts, rng.uniform(0.03, 0.08), (v, v * 0.9, v * 0.72), 0.5, 8, dry=0.35)

    # ----- shapes ------------------------------------------------------------
    hood_l = A.Curve([(0.515, 0.10), (0.470, 0.15), (0.432, 0.24), (0.400, 0.33), (0.360, 0.405)])
    hood_r = A.Curve([(0.515, 0.10), (0.560, 0.15), (0.598, 0.24), (0.630, 0.33), (0.672, 0.405)])
    void_l = A.Curve([(0.515, 0.150), (0.490, 0.20), (0.476, 0.28), (0.470, 0.37), (0.468, 0.47)])
    void_r = A.Curve([(0.515, 0.150), (0.540, 0.20), (0.554, 0.28), (0.560, 0.37), (0.562, 0.47)])
    drape_l_in = A.Curve([(0.468, 0.42), (0.462, 0.58), (0.445, 0.75), (0.420, 0.90), (0.40, 1.05)])
    drape_l_out = A.Curve([(0.040, 0.50), (0.018, 0.62), (0.035, 0.76), (0.065, 0.90), (0.09, 1.05)])
    drape_r_in = A.Curve([(0.562, 0.42), (0.570, 0.58), (0.590, 0.75), (0.618, 0.90), (0.64, 1.05)])
    drape_r_out = A.Curve([(0.940, 0.46), (0.965, 0.60), (0.955, 0.76), (0.930, 0.90), (0.91, 1.05)])
    shoulder_l_top = A.Curve([(0.43, 0.30), (0.33, 0.37), (0.20, 0.42), (0.04, 0.48)])
    shoulder_l_low = A.Curve([(0.47, 0.44), (0.33, 0.47), (0.20, 0.50), (0.05, 0.535)])
    shoulder_r_top = A.Curve([(0.60, 0.30), (0.70, 0.36), (0.83, 0.40), (0.945, 0.44)])
    shoulder_r_low = A.Curve([(0.56, 0.44), (0.70, 0.46), (0.83, 0.48), (0.94, 0.50)])

    def drape_value(side, s, t):
        """Brightness of the robe at (s, t): soft irregular folds, lit from
        the upper left, darkening downward, black inside the left sleeve."""
        streak = nz(s, t, side, 7.0, 0.55)                       # irregular streaks down the cloth
        fold = 0.5 + 0.5 * math.sin(2 * math.pi * (s * 2.6 + 0.6 * nz(s, t, 11 + side, 1.5, 0.8)))
        light = (1.15 - 0.75 * t) * (1.0 if side < 0 else 0.84)
        edge = min(1.0, s * 7) * min(1.0, (1 - s) * 6)
        v = light * (0.30 + 0.70 * smoothstep(-0.45, 0.55, streak)) * (0.55 + 0.45 * fold) * (0.4 + 0.6 * edge)
        v += 0.08 * nz(s, t, 21 + side, 12, 4)
        if side < 0:  # the open left sleeve shows its black inside under the arm
            v *= 1 - 0.85 * smoothstep(0.62, 0.85, s) * smoothstep(0.55, 0.15, t) * smoothstep(0.0, 0.08, t)
        return float(np.clip(v, 0, 1))

    def paint_band(inner, outer, value, n_base, n_mid, n_hi, n_dark, t_range=(0.0, 1.0)):
        # broad dark-ochre underpainting, then mid strokes coloured by value,
        # pale highlights on the fold crests and dark accents in the hollows
        A.band_strokes(P, inner, outer, n_base, lambda s, t: ochre(value(s, t) * 0.5), width=0.030,
                       length=(0.15, 0.35), alpha=0.6, bristles=9, dry=0.32, t_range=t_range)
        # mid strokes: where the cloth is in shadow, leave the black canvas bare
        # or drag a dry brush over it; lit cloth gets fuller, wetter strokes
        for _ in range(n_mid):
            s, t0 = rng.uniform(-0.04, 1.04), rng.uniform(t_range[0] - 0.05, t_range[1])
            v = value(min(max(s, 0.0), 1.0), max(t0, t_range[0]))
            if s < 0 or s > 1:  # strokes straying past the edge are dry and broken
                v *= 0.8
            if v < 0.2 and rng.random() < 0.8:
                continue
            ts = np.linspace(t0, t0 + rng.uniform(0.07, 0.28), 20)
            ts = ts[(ts >= t_range[0]) & (ts <= t_range[1])]
            if len(ts) < 3:
                continue
            sw = s + 0.006 * np.sin(ts * 11 + s * 30)
            pts = inner.at(ts) * (1 - sw)[:, None] + outer.at(ts) * sw[:, None]
            c = ochre(np.clip(v + rng.normal(0, 0.07), 0, 1)) * (1 + rng.normal(0, 0.05, 3))
            P.stroke(pts, rng.uniform(0.007, 0.018), c, 0.85, int(rng.integers(3, 6)),
                     dry=0.2 + 0.45 * (1 - v) + (0.2 if (s < 0.03 or s > 0.97) else 0.0),
                     load=(1.0, rng.uniform(0.15, 0.55)))

        def hi(s, t):
            v = value(s, t)
            return ochre(min(1.0, v + 0.25)) if v > 0.62 else None

        def dk(s, t):
            v = value(s, t)
            return np.array([0.03, 0.022, 0.01]) if v < 0.35 else None

        for fn, count, w, dry in ((hi, n_hi, 0.005, 0.38), (dk, n_dark, 0.007, 0.25)):
            done = 0
            for _ in range(count * 4):
                if done >= count:
                    break
                s, t0 = rng.uniform(0, 1), rng.uniform(t_range[0], t_range[1])
                c = fn(s, t0)
                if c is None:
                    continue
                done += 1
                ts = np.linspace(t0, min(t_range[1], t0 + rng.uniform(0.06, 0.22)), 14)
                pts = inner.at(ts) * (1 - s) + outer.at(ts) * s
                P.stroke(pts, w * rng.uniform(0.7, 1.4), c, 0.8, 3, dry=dry)

    for side, inner, outer in ((-1, drape_l_in, drape_l_out), (1, drape_r_in, drape_r_out)):
        paint_band(inner, outer, lambda s, t, sd=side: drape_value(sd, s, t), 240, 1500, 500, 300)
    for side, top, low in ((-1, shoulder_l_top, shoulder_l_low), (1, shoulder_r_top, shoulder_r_low)):
        val = (lambda s, t, sd=side: float(np.clip((0.95 - 0.45 * s) * (1.0 if sd < 0 else 0.8)
                                                   * (0.75 + 0.25 * math.sin(t * 14 + 3 * nz(s, t, 31 + sd)))
                                                   + 0.1 * nz(s, t, 41 + sd, 8, 8), 0, 1)))
        paint_band(top, low, val, 60, 450, 160, 60)

    def hood_value(side, s, t):
        rim = 0.35 * math.exp(-((s - 0.08) / 0.10) ** 2) + 0.15 * math.exp(-((s - 0.92) / 0.08) ** 2)
        v = (0.45 + 0.35 * math.sin(s * 8 + 2 * nz(s, t, 51 + side))) * (1.0 if side < 0 else 0.78)
        return float(np.clip((v + rim) * (1.08 - 0.25 * t), 0, 1))

    for side, inner, outer in ((-1, void_l, hood_l), (1, void_r, hood_r)):
        paint_band(inner, outer, lambda s, t, sd=side: hood_value(sd, s, t), 90, 650, 220, 70)

    # the face: a void, with only the faintest pale shapes in it
    for _ in range(14):
        x = 0.515 + rng.normal(0, 0.012)
        y0 = rng.uniform(0.19, 0.27)
        pts = np.array([[x + 0.002 * math.sin(u * 5), y0 + 0.05 * u] for u in np.linspace(0, 1, 8)])
        P.stroke(pts, 0.004, (0.55, 0.48, 0.32), 0.2, 3, dry=0.45)
    for ex in (0.503, 0.527):
        P.dab(ex, 0.243, 0.0045, (0.95, 0.78, 0.25), 0.45)
        P.dab(ex, 0.243, 0.0022, (1.0, 0.95, 0.70), 0.95)

    # ----- something stirring in the dark between the robes -------------------
    for x0, h, curl in ((0.485, 0.17, -1), (0.525, 0.24, 1), (0.56, 0.13, 1)):
        us = np.linspace(0, 1, 30)
        pts = np.array([[x0 + curl * 0.035 * math.sin(u * 3.2) * u + 0.008 * math.sin(u * 9),
                         1.04 - h * u] for u in us])
        P.stroke(pts, 0.020, (0.14, 0.09, 0.03), 0.85, 5, load=(1.0, 0.35), dry=0.2)
        P.stroke(pts + np.array([-0.004 * curl, 0]), 0.008, (0.40, 0.27, 0.07), 0.7, 3, load=(1.0, 0.2), dry=0.3)
        P.stroke(pts + np.array([-0.008 * curl, 0]), 0.003, (0.78, 0.60, 0.25), 0.5, 2, load=(1.0, 0.1), dry=0.35)

    # ----- the hands and the staff --------------------------------------------
    for k in range(5):  # long bony fingers dripping from the left sleeve
        x0 = 0.030 + k * 0.012 + rng.normal(0, 0.003)
        L = rng.uniform(0.06, 0.10)
        pts = np.array([[x0 - 0.010 * u * u + 0.003 * math.sin(u * 7), 0.50 + L * u] for u in np.linspace(0, 1, 12)])
        P.stroke(pts, 0.007, (0.88, 0.84, 0.70), 0.9, 3, load=(1.0, 0.6), dry=0.18)
        P.stroke(pts + np.array([0.003, 0]), 0.003, (0.25, 0.20, 0.12), 0.5, 2, dry=0.3)
    for _ in range(10):
        P.dab(rng.uniform(0.02, 0.09), rng.uniform(0.48, 0.52), rng.uniform(0.004, 0.009), (0.92, 0.89, 0.78), 0.8)
    for _ in range(4):  # drips of pale paint
        x0 = rng.uniform(0.025, 0.085)
        pts = np.array([[x0, 0.53 + 0.11 * u * rng.uniform(0.5, 1.0)] for u in np.linspace(0, 1, 8)])
        P.stroke(pts, 0.004, (0.82, 0.78, 0.62), 0.6, 2, load=(1.0, 0.3), dry=0.2)
    staff = np.array([[0.948 + 0.002 * math.sin(u * 13), -0.02 + 1.06 * u] for u in np.linspace(0, 1, 60)])
    P.stroke(staff, 0.011, (0.18, 0.12, 0.04), 0.8, 4, load=(1.0, 0.8), dry=0.1)
    P.stroke(staff, 0.0045, (0.86, 0.72, 0.38), 0.85, 3, load=(1.0, 0.45), dry=0.25)
    P.stroke(np.array([[0.81 + 0.21 * u, 0.125 - 0.004 * u] for u in np.linspace(0, 1, 20)]), 0.005,
             (0.88, 0.78, 0.45), 0.85, 3, dry=0.2)
    P.stroke(np.array([[0.785 + 0.165 * u, -0.02 + 0.30 * u] for u in np.linspace(0, 1, 30)]), 0.0035,
             (0.92, 0.88, 0.70), 0.8, 2, dry=0.3)
    for _ in range(7):  # knuckles round the staff
        P.dab(0.948 + rng.normal(0, 0.01), 0.465 + rng.normal(0, 0.012), rng.uniform(0.004, 0.008),
              (0.86, 0.80, 0.62), 0.8)

    img = P.finish(sharpen=False)
    # the canvas weave pressed into the paint
    h_, w_ = img.shape[:2]
    yy, xx = np.mgrid[0:h_, 0:w_]
    weave = 0.5 + 0.5 * np.sin(xx * 2.3) * np.sin(yy * 2.3)
    lum = img.mean(axis=2, keepdims=True)
    img = img * (1 - 0.10 * weave[..., None] * np.clip(lum * 3, 0, 1))
    img = R.vignette(img, 0.35, 2.0)
    img = R.film(img, seed, grain=0.03, dust=0.2, scratches=0, blotches=0.05)
    return R.to_image(img)

# ---------------------------------------------------------------------------
# The King in Yellow, realistic: a gaunt pallid face in a long yellow hood, a
# jagged iron crown bearing the spiral sign, antlers, hanging leather straps
# and a tentacle curling out from under the robe
# ---------------------------------------------------------------------------

def blade(p, base, top, width, angle, thin=3.5):
    """A tapering blade rising from base to top, flat across the radial
    direction given by angle (radians round the Y axis)."""
    r = np.array([math.sin(angle), 0.0, math.cos(angle)])
    q = p - base
    pr = q @ r
    q2 = q + np.outer(pr * (thin - 1), r)
    return R.sd_round_cone(q2 + base, base, top, width, 0.0008) / thin


def king_real_setup():
    seed = 51
    rng = np.random.default_rng(seed)
    robe_col = np.array([0.40, 0.24, 0.045])

    def robe_tex(p, n):
        wv = 0.92 + 0.08 * np.sin(p[:, 0] * 320 + 2 * R.noise3(p * 40, seed)) * np.sin(p[:, 1] * 320)
        mott = 1 + 0.18 * R.fbm3(p * 9, 4, seed)
        st = 1 - 0.45 * np.clip(R.fbm3(p * 3.5 + 3, 5, seed + 3) * 1.8, 0, 1)
        dusk = 1 - 0.35 * smoothstep(1.35, 0.95, p[:, 1])
        grime = np.clip(R.fbm3(p * 14 + 5, 4, seed + 11) * 1.5, 0, 1)[:, None]
        col = robe_col * (wv * mott * st * dusk)[:, None]
        return col * (1 - 0.4 * grime) + np.array([0.07, 0.055, 0.03]) * 0.4 * grime

    def skin_tex(p, n):
        base = np.array([0.33, 0.33, 0.27])
        mott = 1 + 0.15 * R.fbm3(p * 40, 4, seed + 1)
        green = np.clip(R.fbm3(p * 12, 3, seed + 2), 0, 1)[:, None] * np.array([-0.04, 0.0, -0.03])
        crack = smoothstep(0.90, 0.975, R.ridged3(p * 26, 4, seed + 3))
        veins = smoothstep(0.88, 0.96, R.ridged3(p * 55, 3, seed + 4)) * 0.25
        col = base * mott[:, None] + green
        return col * (1 - 0.65 * crack - veins)[:, None]

    def iron_tex(p, n):
        rust = np.clip(R.fbm3(p * 30, 4, seed + 5) * 1.8 + 0.1, 0, 1)
        col = np.array([0.085, 0.080, 0.075]) * (1 + 0.3 * R.fbm3(p * 90, 2, seed))[:, None]
        return col * (1 - rust[:, None] * 0.3) + np.array([0.10, 0.045, 0.02]) * (rust * 0.5)[:, None]

    def antler_tex(p, n):
        grooves = 0.85 + 0.15 * np.sin(R.fbm3(p * np.array([60, 8, 60]), 3, seed + 6) * 12)
        tip = smoothstep(1.86, 2.08, p[:, 1])
        col = np.array([0.24, 0.19, 0.13]) * (1 - tip)[:, None] + np.array([0.45, 0.40, 0.31]) * tip[:, None]
        return col * grooves[:, None]

    def tentacle_tex(p, n):
        under = smoothstep(0.2, 0.8, n @ np.array([0.6, 0.0, 0.8]))
        stripes = 0.9 + 0.1 * np.sin(p[:, 1] * 160 + p[:, 0] * 40)
        col = np.array([0.19, 0.11, 0.065]) * (1 - under)[:, None] + np.array([0.42, 0.30, 0.20]) * under[:, None]
        return col * (stripes * (1 + 0.2 * R.fbm3(p * 25, 3, seed + 7)))[:, None]

    mats = [
        Material(robe_col, tex=robe_tex, tex_mode="replace", wrap=0.35, spec=0.03, gloss=6, sheen=0.25),  # 0 robe
        Material((0.07, 0.04, 0.022), spec=0.18, gloss=22, wrap=0.2),                                     # 1 straps
        Material((0.50, 0.49, 0.40), tex=skin_tex, tex_mode="replace", wrap=0.30, spec=0.16, gloss=22,
                 sss=(0.12, 0.10, 0.04)),                                                                  # 2 skin
        Material((0.006, 0.005, 0.004), spec=0.5, gloss=160),                                             # 3 eyes
        Material((0.085, 0.08, 0.075), tex=iron_tex, tex_mode="replace", spec=0.55, gloss=32),          # 4 iron crown
        Material((0.80, 0.55, 0.10), spec=0.9, gloss=55),                                               # 5 gold sign
        Material((0.30, 0.24, 0.17), tex=antler_tex, tex_mode="replace", wrap=0.1, spec=0.10, gloss=15),  # 6 antler
        Material((0.018, 0.015, 0.013), spec=0.35, gloss=40),                                           # 7 hair
        Material((0.19, 0.11, 0.065), tex=tentacle_tex, tex_mode="replace", wrap=0.35, spec=0.45, gloss=45,
                 sss=(0.18, 0.05, 0.03)),                                                                  # 8 tentacle
    ]

    # ----- the gaunt face ------------------------------------------------------
    def face(p):
        f = Field(len(p))
        q = R.mirror_x(p)
        d = R.sd_ellipsoid(p, (0, 1.705, -0.012), (0.071, 0.094, 0.090))
        d = R.smin(d, R.sd_ellipsoid(p, (0, 1.712, 0.050), (0.060, 0.040, 0.034)), 0.02)       # forehead
        d = R.smin(d, R.sd_ellipsoid(q, (0.045, 1.652, 0.050), (0.017, 0.009, 0.021)), 0.012)  # cheekbones
        d = R.smin(d, R.sd_ellipsoid(p, (0, 1.603, 0.056), (0.032, 0.024, 0.032)), 0.02)       # mouth
        d = R.smin(d, R.sd_ellipsoid(p, (0, 1.588, 0.026), (0.051, 0.034, 0.058)), 0.02)       # jaw
        d = R.smin(d, R.sd_sphere(p, (0, 1.566, 0.066), 0.017), 0.015)                          # chin
        d = R.smin(d, R.sd_ellipsoid(p, (0, 1.688, 0.072), (0.056, 0.011, 0.017)), 0.008)      # brow ridge
        nose = R.sd_round_cone(p, (0, 1.678, 0.086), (0, 1.633, 0.102), 0.0062, 0.0092)
        nose = R.smin(nose, R.sd_ellipsoid(q, (0.0105, 1.628, 0.091), (0.0075, 0.006, 0.007)), 0.005)
        d = R.smin(d, nose, 0.006)
        d = R.smax(d, -R.sd_ellipsoid(q, (0.030, 1.677, 0.084), (0.019, 0.010, 0.022), R.rot_z(-12)), 0.007)
        d = R.smax(d, -R.sd_ellipsoid(q, (0.052, 1.612, 0.056), (0.017, 0.028, 0.016)), 0.018)  # hollow cheeks
        d = R.smax(d, -R.sd_ellipsoid(q, (0.066, 1.700, 0.030), (0.012, 0.025, 0.02)), 0.02)    # hollow temples
        d = R.smax(d, -R.sd_ellipsoid(p, (0, 1.600, 0.090), (0.021, 0.0022, 0.012)), 0.002)    # thin mouth
        d = R.smax(d, -R.sd_ellipsoid(q, (0.0065, 1.625, 0.097), (0.003, 0.0022, 0.004)), 0.002)
        d = R.smin(d, R.sd_round_cone(p, (0, 1.585, -0.015), (0, 1.45, -0.02), 0.045, 0.055), 0.03)  # neck
        near = np.abs(d) < 0.005
        if near.any():  # cracks in the pallid skin, fine wrinkles
            pn = p[near]
            d[near] += 0.0008 * smoothstep(0.90, 0.975, R.ridged3(pn * 26, 4, seed + 3)) \
                - 0.0003 * R.fbm3(pn * 300, 2, seed + 8)
        f.add(d, 2)
        f.add(R.sd_sphere(q, (0.030, 1.676, 0.064), 0.0112), 3)
        # lank dark hair falling inside the hood
        hair = np.full(len(p), 1e9)
        for sx in (1, -1):
            for k in range(6):
                x0 = sx * (0.050 + 0.007 * k)
                z0 = 0.030 - 0.012 * k
                pts = [(x0, 1.76, z0), (x0 + sx * 0.012, 1.68, z0 + 0.01), (x0 + sx * 0.010, 1.60, z0 + 0.006),
                       (x0 + sx * 0.016, 1.50, z0 - 0.004)]
                hair = np.minimum(hair, R.sd_tube(p, pts, [0.0045, 0.0042, 0.0035, 0.0015]))
        f.add(hair, 7)
        return f

    # ----- the hood ------------------------------------------------------------
    def hood(p):
        f = Field(len(p))
        shell = np.abs(R.sd_ellipsoid(p, (0, 1.705, -0.005), (0.098, 0.135, 0.135))) - 0.009
        flare = np.abs(R.sd_round_cone(p, (0, 1.62, -0.02), (0, 1.50, -0.03), 0.092, 0.120)) - 0.009
        cloth = R.smin(shell, flare, 0.04)
        opening = R.sd_ellipsoid(p, (0, 1.650, 0.125), (0.072, 0.120, 0.080))
        cloth = R.smax(cloth, -opening, 0.010)
        cloth = R.smax(cloth, 1.50 - p[:, 1], 0.02)
        # the hood's long sides fall down in front of the shoulders
        for sx in (1, -1):
            panel = R.sd_box(p, (sx * 0.085, 1.39, 0.085), (0.042, 0.17, 0.010), R.rot_z(sx * 6) @ R.rot_x(-8), 0.008)
            cloth = R.smin(cloth, panel, 0.03)
        near = np.abs(cloth) < 0.02
        if near.any():
            cq = p[near]
            cloth[near] -= 0.008 * np.abs(np.sin(np.arctan2(cq[:, 0], cq[:, 2] + 0.06) * 7
                                                 + 2.5 * R.fbm3(cq * 8, 3, seed))) ** 0.8 \
                + 0.006 * np.abs(np.sin(cq[:, 0] * 140 + 2.0 * R.fbm3(cq * np.array([6, 1.5, 6]), 3, seed + 3))) ** 0.7 \
                * smoothstep(1.62, 1.45, cq[:, 1]) + 0.0015 * R.fbm3(cq * 40, 3, seed + 2)
        f.add(cloth, 0)
        return f

    # ----- crown and antlers ------------------------------------------------
    spikes = []
    for k, ang in enumerate([0, 24, -26, 52, -50, 80, -82, 110, -112]):
        h = (0.23 if k == 0 else rng.uniform(0.09, 0.17) * (1 - 0.25 * abs(ang) / 110)) + rng.normal(0, 0.008)
        spikes.append((math.radians(ang + rng.normal(0, 3)), h, rng.uniform(0.011, 0.016) if k else 0.022,
                       rng.normal(0, 0.012, 2)))

    def crown(p):
        f = Field(len(p))
        cz = -0.02
        ring = np.sqrt((p[:, 0] / 0.087) ** 2 + ((p[:, 2] - cz) / 0.103) ** 2)
        band = np.maximum(np.abs(ring - 1.0) * 0.095 - 0.0045 - 0.0012 * R.noise3(p * 70, seed),
                          np.abs(p[:, 1] - 1.782) - 0.019)
        d = band
        for a, h, w, lean in spikes:
            base = np.array([0.088 * math.sin(a), 1.795, 0.104 * math.cos(a) + cz])
            top = base + np.array([0.012 * math.sin(a) + lean[0], h, 0.012 * math.cos(a) + lean[1]])
            d = R.smin(d, blade(p, base, top, w, a), 0.006)
        near = np.abs(d) < 0.005
        if near.any():  # pitted, hammered iron
            d[near] += 0.0012 * np.abs(R.noise3(p[near] * 140, seed + 9))
        f.add(d, 4)
        # the spiral sign on the front blade
        front = np.array([0.0, 1.835, 0.104 + cz + 0.005])
        th = np.linspace(0.0, 4.4 * math.pi, 50)
        rr = 0.0025 + 0.0060 * th / (4.4 * math.pi)
        pts = [front + np.array([r * math.cos(t), r * math.sin(t) * 1.15, 0.0]) for r, t in zip(rr, th)]
        f.add(R.sd_tube(p, pts, [0.0018] * len(pts)), 5)
        # antlers growing out through the crown
        ant = np.full(len(p), 1e9)
        for sx in (1, -1):
            beam = [(sx * 0.080, 1.79, -0.025), (sx * 0.135, 1.855, -0.040), (sx * 0.185, 1.945, -0.055),
                    (sx * 0.210, 2.035, -0.050), (sx * 0.220, 2.100, -0.035)]
            a = R.sd_tube(p, beam, [0.0120, 0.0100, 0.0085, 0.0062, 0.0028])
            tines = [((sx * 0.100, 1.815, -0.028), (sx * 0.112, 1.870, 0.030), 0.0070),
                     ((sx * 0.138, 1.860, -0.040), (sx * 0.122, 1.950, -0.020), 0.0065),
                     ((sx * 0.186, 1.945, -0.055), (sx * 0.255, 2.000, -0.070), 0.0060),
                     ((sx * 0.210, 2.035, -0.050), (sx * 0.185, 2.105, -0.060), 0.0045)]
            for b0, b1, r0 in tines:
                mid = (np.array(b0) * 0.5 + np.array(b1) * 0.5) + np.array([0, 0.012, 0])
                a = R.smin(a, R.sd_tube(p, [b0, mid, b1], [r0, r0 * 0.7, 0.0015]), 0.008)
            ant = np.minimum(ant, a)
        near = np.abs(ant) < 0.004
        if near.any():
            ant[near] += 0.0008 * np.sin(R.fbm3(p[near] * np.array([90, 12, 90]), 3, seed + 6) * 14)
        f.add(ant, 6)
        return f

    # ----- the body under the robe ----------------------------------------------
    def body(p):
        f = Field(len(p))
        chest = R.sd_ellipsoid(p, (0, 1.31, -0.03), (0.17, 0.19, 0.115))
        belly = R.sd_ellipsoid(p, (0, 1.08, -0.02), (0.16, 0.20, 0.11))
        sh = [np.array([sx * 0.200, 1.455, -0.04]) for sx in (1, -1)]
        traps = np.minimum(R.sd_round_cone(p, (0, 1.53, -0.045), sh[0], 0.05, 0.040),
                           R.sd_round_cone(p, (0, 1.53, -0.045), sh[1], 0.05, 0.040))
        arms = np.minimum(R.sd_round_cone(p, sh[0], (0.235, 1.10, -0.02), 0.058, 0.05),
                          R.sd_round_cone(p, sh[1], (-0.235, 1.10, -0.02), 0.058, 0.05))
        torso = R.smin(R.smin(R.smin(chest, belly, 0.08), traps, 0.06), arms, 0.05)
        skirt = R.sd_round_cone(p, (0, 1.20, -0.03), (0, 0.40, -0.035), 0.20, 0.30)
        robe = R.smin(torso + 0.016, skirt, 0.12)
        cowl = R.sd_torus(p, (0, 1.505, -0.035), 0.105, 0.036, R.rot_x(-6))
        robe = R.smin(robe, cowl, 0.05)
        near = np.abs(robe) < 0.03
        if near.any():
            robe[near] -= drapery(p[near], 0.022, 16, seed, (0.0, -0.035), top=1.52)
        f.add(robe, 0)
        # dark leather straps hanging down the front
        straps = np.full(len(p), 1e9)
        for x0, y0, y1 in ((0.075, 1.39, 1.07), (0.155, 1.40, 1.15), (-0.075, 1.39, 1.10), (-0.160, 1.41, 1.04)):
            zc = 0.088 + 0.26 * np.clip(1.39 - p[:, 1], 0, None) + 0.03 * (abs(x0) > 0.1)
            xc = x0 + 0.004 * np.sin(p[:, 1] * 20 + x0 * 50)
            sd = np.maximum.reduce([np.abs(p[:, 0] - xc) - 0.0075, np.abs(p[:, 2] - zc) - 0.0025,
                                    np.abs(p[:, 1] - (y0 + y1) / 2) - (y0 - y1) / 2]) * 0.7
            straps = np.minimum(straps, sd)
        f.add(straps, 1)
        return f

    # ----- a tentacle curling out from under the robe ---------------------------
    tent_pts = [(-0.21, 1.20, -0.15), (-0.25, 1.37, -0.12), (-0.268, 1.52, -0.09), (-0.252, 1.64, -0.06),
                (-0.215, 1.715, -0.035), (-0.175, 1.735, -0.015), (-0.152, 1.708, 0.0), (-0.163, 1.682, 0.008),
                (-0.180, 1.690, 0.012)]
    tent_r = [0.048, 0.040, 0.032, 0.024, 0.017, 0.011, 0.007, 0.0045, 0.002]

    def tentacle(p):
        f = Field(len(p))
        d = R.sd_tube(p, tent_pts, tent_r)
        near = np.abs(d) < 0.006
        if near.any():
            d[near] -= 0.0012 * R.fbm3(p[near] * 70, 3, seed + 10)
        f.add(d, 8)
        return f

    def scene(p):
        f = Field(len(p))
        f.add_group(p, (0, 1.65, 0.03), 0.17, face)
        f.add_group(p, (0, 1.55, 0.0), 0.30, hood)
        f.add_group(p, (0, 1.93, -0.03), 0.30, crown)
        f.add_group(p, (0, 1.10, -0.03), 0.55, body)
        f.add_group(p, (-0.20, 1.50, -0.07), 0.36, tentacle)
        return f

    return scene, mats, seed


def king_in_yellow_real(scale=1, ss=2):
    """Render at scale x the portrait size (for a large master), supersampled."""
    scene, mats, seed = king_real_setup()
    size = (PORTRAIT_SIZE[0] * scale, PORTRAIT_SIZE[1] * scale)
    cam = Camera((0.55, 1.70, 2.9), (0.0, 1.715, 0.0), fov=15.0)
    lights = [Light((1.0, 0.86, 0.66), 2.4, direction=(-0.45, 0.80, 0.45), softness=10),   # high key: eyes in shadow
              Light((0.50, 0.58, 0.74), 0.28, direction=(0.90, 0.10, 0.40), shadow=False),
              Light((1.0, 0.82, 0.50), 2.2, direction=(0.55, 0.35, -0.80), softness=12)]  # hard rim

    def bg(rd):
        y = np.clip(rd[:, 1] * 3.0 + 0.5, 0, 1)[:, None]
        glow = np.exp(-((rd[:, 0] + 0.01) ** 2 + (rd[:, 1] - 0.06) ** 2) * 30)[:, None]
        tex = (1 + 0.25 * R.fbm3(rd * 5 + 2, 5, seed))[:, None]
        col = np.array([0.012, 0.010, 0.008]) * (1 - y) + np.array([0.035, 0.028, 0.018]) * y
        return (col + np.array([0.09, 0.065, 0.022]) * glow) * tex

    out = R.render(scene, mats, cam, lights, size, ss=ss, background=bg, ambient=(0.03, 0.03, 0.03),
                   rim=((0.03, 0.022, 0.012), 3.0), ao_scale=0.10, max_dist=8.0, shadow_dist=3.0)
    img = R.tonemap(out["rgb"], 1.1)
    img = R.depth_of_field(img, out["depth"], 2.95, 0.35, 1.0 * scale)
    img = R.grade(img, saturation=0.72, shadows=(0.0, 0.006, 0.010), highlights=(0.02, 0.01, -0.015),
                  contrast=1.12, black=0.02)
    img = R.halation(img, 0.8, 1.5 * scale, 0.18)
    img = R.vignette(img, 0.45, 2.0)
    return R.to_image(img)



KING_PAINT = {
    0: ((0.99, 0.80, 0.22), (0.96, 0.62, 0.10), (0.82, 0.40, 0.05), (0.30, 0.12, 0.03)),    # robe
    1: ((0.42, 0.25, 0.15), (0.30, 0.17, 0.10), (0.17, 0.09, 0.05), (0.07, 0.04, 0.02)),    # straps
    2: ((0.86, 0.87, 0.72), (0.70, 0.73, 0.56), (0.45, 0.48, 0.35), (0.16, 0.16, 0.12)),    # pallid skin
    3: ((0.05, 0.04, 0.03), (0.04, 0.03, 0.02), (0.03, 0.02, 0.02), (0.02, 0.015, 0.01)),   # eyes
    4: ((0.58, 0.56, 0.55), (0.42, 0.40, 0.39), (0.24, 0.23, 0.23), (0.10, 0.10, 0.10)),    # iron crown
    5: ((1.00, 0.86, 0.35), (0.96, 0.72, 0.18), (0.75, 0.50, 0.10), (0.40, 0.25, 0.05)),    # spiral sign
    6: ((0.76, 0.66, 0.52), (0.58, 0.48, 0.36), (0.38, 0.29, 0.20), (0.18, 0.12, 0.08)),    # antlers
    7: ((0.10, 0.08, 0.06), (0.07, 0.05, 0.04), (0.04, 0.03, 0.03), (0.02, 0.02, 0.02)),    # hair
    8: ((0.66, 0.44, 0.31), (0.50, 0.31, 0.20), (0.32, 0.18, 0.11), (0.14, 0.07, 0.04)),    # tentacle
}


def king_gbuffers(scale=4):
    """Forms and light for the painted King: G-buffers at scale x the portrait."""
    scene, mats, seed = king_real_setup()
    cam = Camera((0.30, 1.70, 2.9), (0.0, 1.715, 0.0), fov=15.0)
    lights = [Light((1.0, 0.95, 0.85), 2.4, direction=(-0.80, 0.50, 0.40), softness=12),
              Light((0.75, 0.80, 0.90), 0.30, direction=(0.85, 0.10, 0.45), shadow=False)]
    return R.render(scene, mats, cam, lights, PORTRAIT_SIZE, ss=scale, ambient=(0.14, 0.14, 0.14),
                    ao_scale=0.08, max_dist=8.0, shadow_dist=3.0, full=True), seed


def king_painted_from(gb, seed, master=False):
    H, W = gb["mat"].shape
    paper = R.aged_paper((W, H), seed, base=(0.93, 0.87, 0.72), stains=0.18, edge=0.25, foxing=6)
    img = R.painted_illustration(gb, KING_PAINT, PORTRAIT_SIZE, paper, seed, master=master,
                                 ignore_crease=(7,), same=None, depth_rel=0.003)
    return img


def king_in_yellow_painted_hr():
    gb, seed = king_gbuffers(4)
    return R.to_image(king_painted_from(gb, seed))


PORTRAITS = {
    "eldritch_avatar_pallid_mask": king_in_yellow,
}
