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
    img = R.blur(img, 0.3)  # soft old lens
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
    lumps = 0.35 * R.fbm3(p * 22, 3, seed + 4)
    return amount * (depth * (0.7 * big + 0.3 * fine) + lumps)


# ---------------------------------------------------------------------------
# The King in Yellow (Hastur's avatar, "The Pallid Mask")
# ---------------------------------------------------------------------------

def king_in_yellow():
    seed = 21
    ochre = (0.34, 0.24, 0.07)
    bone_col = (0.60, 0.55, 0.43)
    rng = np.random.default_rng(seed)

    def bone_tex(p, n):
        crack = smoothstep(0.86, 0.97, R.ridged3(p * 34, 4, seed))
        stain = np.clip(R.fbm3(p * 8, 5, seed + 4) * 1.5 + 0.25, 0, 1)
        col = np.asarray(bone_col) * (0.8 + 0.3 * R.fbm3(p * 28, 3, seed + 1))[:, None]
        col = col * (1 - 0.5 * stain)[:, None] + np.array([0.16, 0.12, 0.06]) * (0.5 * stain)[:, None]
        return col * (1 - 0.85 * crack)[:, None]

    def gold_tex(p, n):
        tarn = np.clip(R.fbm3(p * 35, 4, seed + 7) * 2.0 + 0.45, 0, 1)
        return np.array([0.60, 0.44, 0.16]) * (1 - 0.7 * tarn)[:, None] + np.array([0.07, 0.07, 0.04]) * (0.7 * tarn)[:, None]

    def feather_tex(p, n):
        base = np.array([0.30, 0.22, 0.22]) * (1 + 0.4 * R.fbm3(p * 9, 4, seed + 5))[:, None]
        barbs = 0.78 + 0.22 * np.sin((np.abs(p[:, 0]) * 0.6 + p[:, 1]) * 700 + 3 * R.noise3(p * 60, seed))
        return base * (barbs * (1 - 0.5 * smoothstep(1.85, 1.35, p[:, 1])))[:, None]

    mats = [
        Material(ochre, tex=rough_cloth_tex(ochre, seed, grime_y=1.45), tex_mode="replace", wrap=0.4, spec=0.03,
                 gloss=5, sheen=0.4),                                                     # 0 robe
        Material((0.24, 0.025, 0.02), wrap=0.3, spec=0.2, gloss=25, sheen=0.3),          # 1 dried-blood ribbon
        Material(bone_col, tex=bone_tex, tex_mode="replace", wrap=0.12, spec=0.25, gloss=28),    # 2 bone
        Material((0.004, 0.003, 0.002)),                                                 # 3 eye voids
        Material((0.6, 0.44, 0.16), tex=gold_tex, tex_mode="replace", spec=0.9, gloss=45),       # 4 tarnished gold
        Material((0.30, 0.22, 0.22), tex=feather_tex, tex_mode="replace", wrap=0.35, spec=0.05, gloss=10,
                 sheen=0.6),                                                              # 5 feathers
        Material((0.16, 0.12, 0.06), spec=0.5, gloss=35),                                # 6 blackened rod
        Material((0.9, 0.75, 0.3), emit=np.array([0.45, 0.33, 0.06])),                  # 7 glints in the voids
        Material((0.10, 0.07, 0.06), spec=0.1, gloss=20),                                # 8 feather shafts
    ]

    # ----- head: hood, mask, crown --------------------------------------------
    spikes = []
    for k, ang in enumerate([0, 48, -46, 95, -97, 145, -142]):
        top = (2.00 if k == 0 else 1.93 - 0.012 * (k // 2)) + rng.normal(0, 0.012)
        lean = rng.normal(0, 0.012, 2)
        spikes.append((math.radians(ang + rng.normal(0, 4)), top, lean, 0.012 if k == 0 else 0.009))

    def head(p):
        f = Field(len(p))
        q = R.mirror_x(p)
        # hood: heavy cloth close round the mask, hanging onto the shoulders
        shell = np.abs(R.sd_ellipsoid(p, (0, 1.725, -0.03), (0.100, 0.125, 0.122))) - 0.009
        opening = R.sd_ellipsoid(p, (0, 1.695, 0.105), (0.072, 0.118, 0.10))
        hood = R.smax(shell, -opening, 0.012)
        hood = R.smax(hood, 1.47 - p[:, 1], 0.03)
        near = np.abs(hood) < 0.02
        if near.any():
            hq = p[near]
            hood[near] -= 0.006 * np.abs(np.sin(np.arctan2(hq[:, 0], hq[:, 2] + 0.06) * 7
                                                + 2.5 * R.fbm3(hq * 9, 3, seed))) ** 0.8 \
                + 0.002 * R.fbm3(hq * 40, 3, seed + 2)
        f.add(hood, 0)
        f.add(np.maximum(hood - 0.002, np.abs(opening) - 0.006), 1)  # narrow frayed trim
        # the mask: a cracked bird skull, its long beak hooked over the chest
        mask = R.sd_ellipsoid(p, (0, 1.732, 0.0), (0.066, 0.084, 0.078))
        pb = p * np.array([1.55, 1.0, 1.0])
        beak = R.sd_tube(pb, [(0, 1.712, 0.048), (0, 1.650, 0.096), (0, 1.582, 0.122), (0, 1.515, 0.127),
                              (0, 1.462, 0.114), (0, 1.440, 0.094)],
                         [0.036, 0.026, 0.017, 0.010, 0.005, 0.0018]) / 1.55
        mask = R.smin(mask, beak, 0.028)
        keel = R.sd_tube(p, [(0, 1.70, 0.080), (0, 1.62, 0.118), (0, 1.54, 0.131)], [0.005, 0.004, 0.0025])
        mask = R.smin(mask, keel, 0.008)
        sockets = R.sd_ellipsoid(q, (0.031, 1.740, 0.066), (0.021, 0.014, 0.04), R.rot_z(-22))
        mask = R.smax(mask, -sockets, 0.005)
        nares = R.sd_ellipsoid(q, (0.010, 1.655, 0.100), (0.0025, 0.022, 0.006), R.rot_x(38))
        mask = R.smax(mask, -nares, 0.002)
        near = np.abs(mask) < 0.008
        if near.any():  # cracks as grooves, pitting
            mq = p[near]
            mask[near] += 0.0018 * smoothstep(0.86, 0.97, R.ridged3(mq * 34, 4, seed)) \
                + 0.0006 * R.fbm3(mq * 220, 2, seed + 3)
        f.add(mask, 2)
        f.add(R.sd_ellipsoid(q, (0.031, 1.740, 0.050), (0.019, 0.012, 0.012), R.rot_z(-22)), 3)
        f.add(R.sd_sphere(q, (0.033, 1.739, 0.058), 0.0028), 7)
        # crown: a hammered, uneven band with sharp, leaning spikes
        ring = np.sqrt(p[:, 0] ** 2 + ((p[:, 2] + 0.03) * 0.92) ** 2)
        band = np.maximum(np.abs(ring - 0.082 - 0.002 * R.noise3(p * 60, seed)) - 0.005,
                          np.abs(p[:, 1] - 1.83 - 0.006 * np.sin(np.arctan2(p[:, 0], p[:, 2]) * 7)) - 0.018)
        crown = band
        for a, top, lean, r0 in spikes:
            bx, bz = 0.083 * math.sin(a), 0.083 * math.cos(a) / 0.92 - 0.03
            tx, tz = 0.094 * math.sin(a) + lean[0], 0.094 * math.cos(a) / 0.92 - 0.03 + lean[1]
            crown = R.smin(crown, R.sd_round_cone(p, (bx, 1.84, bz), (tx, top, tz), r0, 0.0012), 0.008)
            crown = np.minimum(crown, R.sd_sphere(p, (tx, top - 0.012, tz), r0 * 0.55))
        near = np.abs(crown) < 0.006
        if near.any():  # hammer marks
            crown[near] += 0.0012 * np.abs(R.noise3(p[near] * 150, seed + 8))
        f.add(crown, 4)
        return f

    # ----- body: robe, cowl, sleeves ------------------------------------------
    def body(p):
        f = Field(len(p))
        d = R.sd_ellipsoid(p, (0, 1.40, -0.04), (0.23, 0.11, 0.15))
        d = R.smin(d, R.sd_box(p, (0, 1.00, -0.04), (0.215, 0.40, 0.14), round_=0.09), 0.08)
        d = R.smin(d, R.sd_torus(p, (0, 1.47, -0.025), 0.10, 0.05, R.rot_x(-8)), 0.05)  # bunched cowl
        near = np.abs(d) < 0.03
        if near.any():
            d[near] -= drapery(p[near], 0.009, 26, seed, (0.0, -0.04), top=1.47)
        f.add(d, 0)
        f.add(np.maximum(d - 0.003, np.abs(p[:, 0] + 0.012 * np.sin(p[:, 1] * 9) + 0.004 * R.noise3(p * 30, seed))
                         - 0.014), 1)
        for sx in (1, -1):
            sleeve = R.sd_round_cone(p, (sx * 0.235, 1.25, -0.01), (sx * 0.135, 1.43, 0.10), 0.056, 0.045)
            drape = R.sd_ellipsoid(p, (sx * 0.20, 1.24, 0.05), (0.06, 0.13, 0.05), R.rot_z(sx * 30) @ R.rot_x(-25))
            sleeve = R.smin(sleeve, drape, 0.05)
            near = np.abs(sleeve) < 0.03
            if near.any():
                sq = p[near]
                fold = sq[:, 0] * sx * 1.2 + sq[:, 2] * 0.6 + 0.7 * R.fbm3(sq * 6, 3, seed + sx)
                sleeve[near] -= 0.007 * np.abs(np.sin(fold * 45)) ** 0.8 * (0.5 + 0.5 * np.abs(R.noise3(sq * 8, seed))) \
                    + 0.002 * R.fbm3(sq * 30, 2, seed)
            f.add(sleeve, 0, 0.03)
            f.add(R.sd_torus(p, (sx * 0.135, 1.435, 0.10), 0.046, 0.008, R.rot_x(-50) @ R.rot_z(sx * 25)), 1)
        return f

    def hand(p, sx, grip):
        """Skeletal hand rising from the cuff; grip curls the fingers round a rod."""
        f = Field(len(p))
        wrist = np.array([sx * 0.130, 1.455, 0.11])
        d = R.sd_ellipsoid(p, wrist + np.array([0, 0.035, 0.008]), (0.024, 0.032, 0.009), R.rot_z(sx * 8))
        for i in range(4):
            off = (i - 1.5) * 0.012
            base = wrist + np.array([sx * off * 0.9 + sx * 0.002, 0.064, 0.010])
            if grip:
                pts = [base, base + np.array([0, 0.012, 0.022]), base + np.array([0, -0.004, 0.034]),
                       base + np.array([0, -0.016, 0.026])]
            else:
                ln = 0.032 - abs(i - 1.2) * 0.004
                pts = [base, base + np.array([sx * off * 0.15, ln, 0.008]),
                       base + np.array([sx * off * 0.25, ln * 1.6, 0.020]),
                       base + np.array([sx * off * 0.3, ln * 1.95, 0.034])]
            finger = R.sd_tube(p, pts, [0.0052, 0.0043, 0.0036, 0.0022])
            for k in (1, 2):
                finger = R.smin(finger, R.sd_sphere(p, pts[k], 0.0058), 0.003)
            d = R.smin(d, finger, 0.003)
        thumb = R.sd_tube(p, [wrist + np.array([-sx * 0.018, 0.020, 0.012]), wrist + np.array([-sx * 0.033, 0.040, 0.026]),
                              wrist + np.array([-sx * 0.038, 0.057, 0.034])], [0.006, 0.0046, 0.0026])
        d = R.smin(d, thumb, 0.004)
        near = np.abs(d) < 0.006
        if near.any():
            d[near] -= 0.001 * R.fbm3(p[near] * 300, 2, seed)
        f.add(d, 2)
        if grip:  # scepter: a blackened rod with a pierced, key-like head
            rx = wrist[0] + sx * 0.002
            f.add(R.sd_capsule(p, (rx, 1.33, 0.142), (rx, 1.72, 0.142), 0.005), 6)
            head_ = np.minimum(R.sd_torus(p, (rx, 1.762, 0.142), 0.024, 0.005, R.rot_x(90)),
                               R.sd_torus(p, (rx, 1.762, 0.142), 0.011, 0.0035, R.rot_x(90)))
            head_ = np.minimum(head_, R.sd_round_cone(p, (rx, 1.785, 0.142), (rx, 1.815, 0.142), 0.006, 0.001))
            f.add(head_, 4)
        return f

    # ----- wings ------------------------------------------------------------
    def wing_feathers(sx):
        out = []
        arm = [np.array([sx * 0.10, 1.50, -0.14]), np.array([sx * 0.24, 1.80, -0.20]),
               np.array([sx * 0.36, 2.04, -0.24]), np.array([sx * 0.52, 2.10, -0.27])]
        wr = np.random.default_rng(7 if sx > 0 else 8)
        for length_, width, count, back in [(0.09, 0.026, 12, 0.0), (0.20, 0.030, 14, 0.012), (0.38, 0.033, 14, 0.024)]:
            for k in range(count):
                t = (k + 0.5) / count
                seg = min(int(t * 3), 2)
                u = t * 3 - seg
                root = arm[seg] * (1 - u) + arm[seg + 1] * u
                spread = -0.9 + 1.25 * t + 0.09 * wr.normal()
                dirv = np.array([sx * math.sin(spread) * 0.9, -math.cos(spread), -0.25 + 0.1 * wr.normal()])
                L = length_ * (0.6 + 0.8 * t) * (1 + 0.15 * wr.normal())
                c = root + R.normalize(dirv) * L * 0.5 + np.array([0, 0, -back])
                out.append((c, frame_axes(dirv, np.array([0.0, 0.25, 1.0])), (width * (0.8 + 0.4 * t), L * 0.5, 0.0055)))
        return out, arm

    wings = {sx: wing_feathers(sx) for sx in (1, -1)}

    def wing(p, sx):
        f = Field(len(p))
        feathers, arm = wings[sx]
        d = R.sd_tube(p, arm, [0.035, 0.028, 0.020, 0.010])
        shafts = np.full(len(p), 1e9)
        for c, axes, radii in feathers:
            d = np.minimum(d, R.sd_ellipsoid(p, c, radii, axes))
            v = axes[:, 1] * radii[1] * 0.95
            shafts = np.minimum(shafts, R.sd_capsule(p, c - v + axes[:, 2] * 0.003, c + v * 0.8 + axes[:, 2] * 0.003, 0.002))
        near = np.abs(d) < 0.01
        if near.any():  # ragged barbs
            d[near] += 0.004 * np.clip(R.fbm3(p[near] * 60, 3, seed + 2), 0, 1)
        f.add(d, 5)
        f.add(shafts, 8)
        return f

    def scene(p):
        f = Field(len(p))
        f.add_group(p, (0, 1.80, 0.0), 0.26, head)
        f.add_group(p, (0, 1.15, -0.03), 0.50, body)
        f.add_group(p, (0.13, 1.52, 0.11), 0.08, lambda q: hand(q, 1, False))
        f.add_group(p, (-0.13, 1.56, 0.12), 0.27, lambda q: hand(q, -1, True))
        for sx in (1, -1):
            f.add_group(p, (sx * 0.40, 1.80, -0.24), 0.48, lambda q, s=sx: wing(q, s))
        return f

    cam = Camera((0.30, 1.58, 2.5), (0.0, 1.665, 0.0), fov=17.0)
    lights = [
        # one hard lamp high to the left, pooled on the mask and crown
        Light((1.0, 0.82, 0.55), 3.4, pos=(-0.75, 2.75, 1.05), aim=(0.0, 1.70, 0.05), cone=(7, 20),
              softness=24, falloff=0.25),
        # a cold sliver of back light to cut the silhouette out of the dark
        Light((0.55, 0.62, 0.75), 0.9, direction=(0.55, 0.45, -0.75), softness=10),
    ]
    bg = gloom(seed, base=(0.010, 0.008, 0.006), glow=(0.10, 0.07, 0.02), glow_at=(-0.05, 0.12), glow_size=18)
    out = R.render(scene, mats, cam, lights, PORTRAIT_SIZE, ss=3, background=bg, ambient=(0.012, 0.011, 0.010),
                   rim=((0.025, 0.02, 0.012), 3.0), ao_scale=0.12, max_dist=6.0, shadow_dist=2.5)
    return print_finish(out, seed, sat=0.38, sepia=0.45, contrast=1.25, exposure=1.0,
                        shadows=(0.0, 0.004, 0.008), highlights=(0.02, 0.01, -0.02), focus=(2.5, 0.9, 0.8),
                        smoke=0.30, smoke_src=(0.25, 0.08))


PORTRAITS = {
    "eldritch_avatar_pallid_mask": king_in_yellow,
}
