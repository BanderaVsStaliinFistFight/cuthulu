"""Avatar portraits.

The King in Yellow (Hastur's avatar, the Pallid Mask) is painted after a
dark-fantasy oil: an emaciated thing whose head is wrapped in folds of its
own skin, crimson tentacles writhing behind it, a clawed hand raised, a
tattered ochre mantle, all backlit by a blazing glow. Its forms are sculpted
as signed distance fields and lit (art_render), then repainted stroke by
stroke (art_paint) with smoke, embers and a dark warm grade.

Subjects face +Z with their heads around y = 1.6 (metres).
"""

import math

import numpy as np
from PIL import Image, ImageDraw

import art_paint as A
import art_render as R
from art_render import Field, Material, Camera, Light, smoothstep

PORTRAIT_SIZE = (156, 210)


def spiral_tentacle(base, direction, length, r0, curl_dir, curl_turns=1.4, curl_r=0.05, n=26):
    """Points and radii for a tentacle that rises along direction and coils
    at its tip in the plane of direction and curl_dir."""
    base = np.asarray(base, float)
    d = R.normalize(direction)
    c = R.normalize(np.asarray(curl_dir, float) - d * np.dot(curl_dir, d))
    side = np.cross(d, c)
    pts, radii = [], []
    straight = 0.68
    for i in range(n):
        u = i / (n - 1)
        if u <= straight:
            # a sweeping S-bend with a little writhing to the side
            pos = base + d * length * u + c * length * 0.22 * math.sin(u * 4.2) * u + side * 0.025 * math.sin(u * 9)
        else:
            k = (u - straight) / (1 - straight)
            ang = k * curl_turns * 2 * math.pi
            rad = curl_r * (1 - 0.65 * k)
            tip0 = base + d * length * straight + c * length * 0.22 * math.sin(straight * 4.2) * straight \
                + side * 0.025 * math.sin(straight * 9)
            pos = tip0 + d * rad * math.sin(ang) + c * rad * (1 - math.cos(ang))
        pts.append(pos)
        radii.append(r0 * (1 - 0.9 * u ** 0.8) + 0.0012)
    return pts, radii


def king_setup():
    seed = 77
    rng = np.random.default_rng(seed)

    def flesh_tex(p, n):
        base = np.array([0.20, 0.21, 0.16])
        mott = 1 + 0.30 * R.fbm3(p * 18, 4, seed)
        sinew = smoothstep(0.78, 0.95, R.ridged3(p * np.array([30, 90, 30]), 4, seed + 1))
        veins = smoothstep(0.90, 0.97, R.ridged3(p * 45, 3, seed + 2))
        bruise = np.clip(R.fbm3(p * 6 + 3, 3, seed + 3) * 1.5, 0, 1)[:, None]
        col = base * mott[:, None]
        col = col * (1 - 0.45 * bruise) + np.array([0.22, 0.08, 0.06]) * 0.45 * bruise
        return col * (1 - 0.45 * sinew - 0.3 * veins)[:, None]

    def cloak_tex(p, n):
        col = np.array([0.52, 0.31, 0.05]) * (1 + 0.25 * R.fbm3(p * 10, 4, seed + 4))[:, None]
        grime = np.clip(R.fbm3(p * 5 + 7, 4, seed + 5) * 1.6, 0, 1)[:, None]
        blood = smoothstep(0.55, 0.75, R.fbm3(p * 9 + 1, 3, seed + 6))[:, None]
        col = col * (1 - 0.5 * grime) + np.array([0.12, 0.07, 0.02]) * 0.5 * grime
        return col * (1 - 0.6 * blood) + np.array([0.20, 0.03, 0.02]) * 0.6 * blood

    def tentacle_tex(p, n):
        col = np.array([0.30, 0.04, 0.07]) * (1 + 0.3 * R.fbm3(p * 30, 3, seed + 7))[:, None]
        rings = 0.88 + 0.12 * np.sin(R.fbm3(p * 40, 2, seed + 8) * 10)
        return col * rings[:, None]

    mats = [
        Material((0.20, 0.21, 0.16), tex=flesh_tex, tex_mode="replace", wrap=0.35, spec=0.32, gloss=30,
                 sss=(0.30, 0.08, 0.04)),                                                     # 0 flesh
        Material((0.52, 0.31, 0.05), tex=cloak_tex, tex_mode="replace", wrap=0.4, spec=0.05, gloss=8,
                 sheen=0.6),                                                                   # 1 cloak
        Material((0.30, 0.04, 0.07), tex=tentacle_tex, tex_mode="replace", wrap=0.4, spec=0.7, gloss=55,
                 sss=(0.45, 0.06, 0.06)),                                                      # 2 tentacles
        Material((0.05, 0.045, 0.04), spec=0.6, gloss=60),                                    # 3 claws
    ]

    head_rot = R.rot_x(14) @ R.rot_z(-6)
    head_c = np.array([0.0, 1.625, 0.015])

    def head(p):
        f = Field(len(p))
        q = R.to_local(p, head_c, head_rot)
        # a long head wrapped in folds of its own skin, drawn tight over where
        # the face should be: deep folds converging to the front like a knotted hood
        d = R.sd_ellipsoid(q, (0, 0.0, 0.0), (0.070, 0.118, 0.086))
        d = R.smin(d, R.sd_ellipsoid(q, (0, -0.045, 0.035), (0.050, 0.070, 0.060)), 0.03)
        near = np.abs(d) < 0.025
        if near.any():
            qn = q[near]
            # angle round an axis that leans forward, so folds gather at the front
            ax = qn - np.array([0.0, -0.02, 0.10])
            a = np.arctan2(ax[:, 0], -ax[:, 1])
            r = np.sqrt(ax[:, 0] ** 2 + ax[:, 1] ** 2)
            folds = np.abs(np.sin(a * 9 + 1.8 * R.fbm3(qn * 12, 3, seed) + r * 30)) ** 0.6
            gather = smoothstep(0.16, 0.02, r)
            d[near] -= 0.009 * folds * (0.35 + 0.65 * gather) + 0.0012 * R.fbm3(qn * 120, 2, seed + 1)
        # the knot of skin where a face should be, sunk into shadow
        d = R.smax(d, -R.sd_ellipsoid(q, (0, -0.03, 0.098), (0.020, 0.032, 0.016)), 0.01)
        f.add(d, 0)
        # neck, tendons and collarbones
        neck = R.sd_round_cone(p, (0, 1.54, 0.0), (0, 1.43, -0.01), 0.030, 0.036)
        for sx in (1, -1):
            neck = R.smin(neck, R.sd_capsule(p, (sx * 0.030, 1.56, 0.004), (sx * 0.010, 1.43, 0.040), 0.008), 0.008)
        f.add(neck, 0, 0.02)
        return f

    def torso(p):
        f = Field(len(p))
        ribs_c = np.array([0.0, 1.27, -0.01])
        d = R.sd_ellipsoid(p, ribs_c, (0.125, 0.16, 0.095))
        d = R.smin(d, R.sd_ellipsoid(p, (0, 1.06, -0.03), (0.095, 0.12, 0.07)), 0.05)   # sunken belly
        for sx in (1, -1):
            d = R.smin(d, R.sd_capsule(p, (sx * 0.020, 1.425, 0.044), (sx * 0.140, 1.448, 0.004), 0.0075), 0.012)
            d = R.smin(d, R.sd_sphere(p, (sx * 0.168, 1.43, -0.01), 0.040), 0.035)            # bony shoulders
            d = R.smin(d, R.sd_round_cone(p, (0, 1.47, -0.03), (sx * 0.16, 1.44, -0.02), 0.03, 0.025), 0.03)
        near = np.abs(d) < 0.02
        if near.any():
            pn = p[near]
            # ribs as arcs sloping down and round the front and sides only, the sternum left smooth
            rib = np.abs(np.sin((pn[:, 1] + 1.4 * pn[:, 0] ** 2 - 1.0) * 62)) ** 0.5
            ribzone = smoothstep(1.40, 1.33, pn[:, 1]) * smoothstep(1.12, 1.19, pn[:, 1]) * \
                smoothstep(0.008, 0.03, np.abs(pn[:, 0])) * smoothstep(-0.04, 0.03, pn[:, 2])
            d[near] -= 0.0045 * rib * ribzone + 0.0012 * R.fbm3(pn * 90, 2, seed + 2)
        f.add(d, 0)
        return f

    # the left arm raised, its claws spread beside the head (the right is under the mantle)
    arm_l = [(-0.17, 1.43, -0.01), (-0.26, 1.28, 0.06), (-0.195, 1.52, 0.12)]

    def finger_chain(start, dirs, lengths, r0):
        pts = [np.asarray(start, float)]
        for dvec, ln in zip(dirs, lengths):
            pts.append(pts[-1] + R.normalize(dvec) * ln)
        radii = [r0 * (1 - 0.18 * k) for k in range(len(pts))]
        return pts, radii

    def arms(p):
        f = Field(len(p))
        d = np.full(len(p), 1e9)
        claws = np.full(len(p), 1e9)
        s, e, w = (np.array(c) for c in arm_l)
        up = R.sd_round_cone(p, s, e, 0.030, 0.024)
        fore = R.sd_round_cone(p, e, w, 0.026, 0.017)
        d = np.minimum(d, R.smin(R.smin(up, R.sd_sphere(p, e, 0.028), 0.02), fore, 0.02))
        # raised hand: long fingers splayed upward like claws
        wl = np.array(arm_l[2])
        palm = R.sd_ellipsoid(p, wl + np.array([0.0, 0.040, 0.004]), (0.030, 0.040, 0.011), R.rot_z(-12))
        d = R.smin(d, palm, 0.015)
        for k, spread in enumerate((-0.55, -0.2, 0.15, 0.45)):
            start = wl + np.array([-0.022 + 0.015 * k, 0.075, 0.006])
            base_dir = np.array([math.sin(spread) * 0.8, 1.0, 0.25])
            pts, radii = finger_chain(start, [base_dir, base_dir + np.array([0, 0, 0.5]), base_dir + np.array([0, -0.2, 1.1])],
                                      [0.045, 0.034, 0.026], 0.0085)
            d = R.smin(d, R.sd_tube(p, pts, radii), 0.006)
            for kk in (1, 2):
                d = R.smin(d, R.sd_sphere(p, pts[kk], radii[kk] * 1.25), 0.004)
            tip, prev = pts[-1], pts[-2]
            claws = np.minimum(claws, R.sd_round_cone(p, tip, tip + R.normalize(tip - prev) * 0.03
                                                     + np.array([0, -0.006, 0.006]), 0.0055, 0.0005))
        thumb, tr = finger_chain(wl + np.array([0.026, 0.03, 0.012]), [(0.9, 0.7, 0.3), (0.7, 0.9, 0.6)], [0.04, 0.03], 0.009)
        d = R.smin(d, R.sd_tube(p, thumb, tr), 0.006)
        near = np.abs(d) < 0.008
        if near.any():
            pn = p[near]
            d[near] -= 0.0015 * smoothstep(0.75, 0.95, R.ridged3(pn * np.array([60, 160, 60]), 3, seed + 3)) \
                + 0.0006 * R.fbm3(pn * 200, 2, seed + 4)
        f.add(d, 0)
        f.add(claws, 3)
        return f

    tentacles = []
    for k, (bx, by, bz, dx, dy, dz, L, r0) in enumerate([
            (-0.03, 1.69, -0.05, -0.55, 1.0, -0.2, 0.30, 0.026), (0.03, 1.69, -0.05, 0.55, 1.0, -0.15, 0.32, 0.026),
            (0.00, 1.71, -0.06, 0.10, 1.0, -0.35, 0.22, 0.020), (-0.07, 1.61, -0.06, -1.0, 0.55, -0.2, 0.30, 0.025),
            (0.07, 1.61, -0.06, 1.0, 0.6, -0.15, 0.27, 0.025), (-0.12, 1.47, -0.07, -1.0, 0.25, 0.1, 0.26, 0.028),
            (0.12, 1.48, -0.07, 1.0, 0.35, 0.05, 0.24, 0.027)]):
        curl = np.array([dx * -0.3, -0.6, 0.8]) + rng.normal(0, 0.3, 3)
        tentacles.append(spiral_tentacle((bx, by, bz), (dx, dy, dz), L, r0, curl, 1.2 + 0.4 * rng.random(),
                                         0.04 + 0.02 * rng.random()))

    def tentacle_field(p):
        f = Field(len(p))
        d = np.full(len(p), 1e9)
        for pts, radii in tentacles:
            d = np.minimum(d, R.sd_tube(p, pts, radii))
        near = np.abs(d) < 0.006
        if near.any():
            d[near] -= 0.001 * R.fbm3(p[near] * 120, 2, seed + 11)
        f.add(d, 2)
        return f

    def cloak(p):
        f = Field(len(p))
        # a heavy ochre mantle over the shoulders, wrapped closed over the body
        d = R.sd_ellipsoid(p, (0, 1.30, -0.04), (0.235, 0.215, 0.165))
        d = np.maximum(d, p[:, 1] - 1.485 + 0.12 * np.abs(p[:, 0]))  # open round the neck
        near = np.abs(d) < 0.03
        if near.any():
            pn = p[near]
            # irregular folds: noise stretched downward, of varied width and depth
            ridge = R.ridged3(pn * np.array([9, 2.2, 9]) + 3, 4, seed + 12)
            d[near] -= 0.024 * smoothstep(0.55, 0.95, ridge) * smoothstep(1.48, 1.32, pn[:, 1]) \
                + 0.005 * R.fbm3(pn * 22, 3, seed + 13)
        # ragged hem lines where the cloth is torn
        d = np.maximum(d, -0.02 - (p[:, 1] - 1.22 - 0.03 * R.fbm3(p * 18, 3, seed + 17)))
        f.add(d, 1)
        return f

    def scene(p):
        f = Field(len(p))
        f.add_group(p, head_c, 0.17, head)
        f.add_group(p, (0, 1.24, -0.02), 0.32, torso)
        f.add_group(p, (-0.20, 1.45, 0.07), 0.32, arms)
        f.add_group(p, (0.0, 1.70, -0.10), 0.48, tentacle_field)
        f.add_group(p, (0.0, 1.20, -0.04), 0.42, cloak)
        return f

    return scene, mats, seed


def king_camera():
    return Camera((0.06, 1.50, 1.85), (0.0, 1.57, 0.0), fov=23.0)


def king_paint(scale=2, ss=1):
    """Render the forms at scale x the portrait size, then repaint them
    stroke by stroke as a dark oil. Returns the picture (0..1) and seed."""
    scene, mats, seed = king_setup()
    size = (PORTRAIT_SIZE[0] * scale, PORTRAIT_SIZE[1] * scale)
    cam = king_camera()
    lights = [Light((1.0, 0.84, 0.55), 6.0, direction=(-0.05, 0.40, -1.0), softness=8),    # the blaze behind
              Light((1.0, 0.55, 0.25), 0.22, direction=(0.70, 0.40, 0.55), softness=10),    # a faint warm key
              Light((0.45, 0.15, 0.08), 0.10, direction=(-0.6, -0.4, 0.6), shadow=False)]   # bounce

    def glow_bg(rd):
        c = np.array([0.02, 0.13])
        d2 = (rd[:, 0] - c[0]) ** 2 + (rd[:, 1] - c[1]) ** 2
        core = np.exp(-d2 * 450)[:, None]
        halo = np.exp(-d2 * 110)[:, None]
        swirl = np.clip(1 + 0.7 * R.fbm3(rd * np.array([6, 6, 6]) + 4, 6, seed), 0.2, 2)[:, None]
        return np.array([0.014, 0.0055, 0.004]) * swirl + np.array([0.30, 0.10, 0.028]) * halo * swirl \
            + np.array([2.2, 1.75, 1.05]) * core

    out = R.render(scene, mats, cam, lights, size, ss=ss, background=glow_bg, ambient=(0.016, 0.010, 0.009),
                   rim=((0.85, 0.52, 0.18), 3.6), ao_scale=0.08, max_dist=8.0, shadow_dist=2.0)
    ref = R.tonemap(out["rgb"], 1.0)
    ref = R.smoke(ref, out["depth"], seed, 0.22, (0.55, 0.28, 0.10), (0.52, 0.22), 2.5, far=(1.6, 2.6))
    ref = R.grade(ref, saturation=0.9, shadows=(0.012, 0.0, -0.006), highlights=(0.02, 0.01, -0.02),
                  contrast=1.1, black=0.02)
    s = scale / 4
    img = A.paint_from_image(ref, brushes=(18 * s, 9 * s, 4.5 * s, 2.2 * s), seed=seed, threshold=0.045)
    img = R.halation(img, 0.72, 4.0 * s, 0.30, tint=(1.0, 0.7, 0.4))
    # embers drifting up out of the glow
    rng = np.random.default_rng(seed)
    pil = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    dr = ImageDraw.Draw(pil, "RGBA")
    H, W = img.shape[:2]
    for _ in range(int(60 * s * s)):
        x, y = rng.normal(0.52, 0.22) * W, rng.uniform(0.0, 0.7) * H
        r = rng.uniform(0.6, 1.8) * s
        dr.ellipse([x - r, y - r, x + r, y + r], fill=(255, int(rng.uniform(150, 220)), 90, int(rng.uniform(80, 200))))
    img = R.blur(np.asarray(pil).astype(float) / 255, 0.35 * s)
    img = R.vignette(img, 0.6, 1.6)
    return img, seed


def king_in_yellow():
    """The in-game portrait: painted at twice the size, reduced cleanly."""
    img, _ = king_paint(2, 1)
    return R.to_image(img).convert("RGB").resize(PORTRAIT_SIZE, Image.LANCZOS).convert("RGBA")


PORTRAITS = {
    "eldritch_avatar_pallid_mask": king_in_yellow,
}
