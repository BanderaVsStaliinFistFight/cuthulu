"""Signed-distance-field renderer used to sculpt and light painted art.

A subject is a signed distance field - a function giving the distance from
any point to the nearest surface - built from ellipsoids, capsules, tapered
tubes and the like, blended smoothly and roughened with 3D noise. It is
ray-marched with numpy and lit with soft shadows, ambient occlusion, wrapped
(subsurface) diffuse, specular, rim light and spotlights; the result is the
reference a painter (art_paint) works from. Finishing helpers add smoke,
halation, grading and vignetting.

Coordinates: Y is up and the camera usually looks down -Z, so subjects face
+Z. Everything works on (N, 3) arrays of points so whole images march at once.
"""

import math

import numpy as np
from PIL import Image, ImageFilter

# ---------------------------------------------------------------------------
# Vector helpers
# ---------------------------------------------------------------------------


def normalize(v):
    v = np.asarray(v, float)
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def length(p):
    return np.sqrt(np.einsum("...i,...i->...", p, p))


def rot_x(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_z(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def to_local(p, center, rot=None):
    """Point in a primitive's frame: translate to center, then undo rot (the
    primitive is rotated by rot about its center)."""
    q = p - np.asarray(center, float)
    return q if rot is None else q @ rot


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------------------
# Noise (deterministic hashed value noise)
# ---------------------------------------------------------------------------

def _hash(ix, iy, iz, seed):
    h = (ix * 374761393 + iy * 668265263 + iz * 1442695041 + seed * 144665 + 1013904223) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h ^= h >> 16
    return h.astype(np.float64) * (1.0 / 4294967295.0)


def noise3(p, seed=0):
    """Smooth value noise in [-1, 1] at (N, 3) points."""
    pi = np.floor(p)
    f = p - pi
    pi = pi.astype(np.int64)
    u = f * f * (3 - 2 * f)
    x0, y0, z0 = pi[:, 0], pi[:, 1], pi[:, 2]
    x1, y1, z1 = x0 + 1, y0 + 1, z0 + 1
    ux, uy, uz = u[:, 0], u[:, 1], u[:, 2]

    def lerp(a, b, t):
        return a + (b - a) * t

    c00 = lerp(_hash(x0, y0, z0, seed), _hash(x1, y0, z0, seed), ux)
    c10 = lerp(_hash(x0, y1, z0, seed), _hash(x1, y1, z0, seed), ux)
    c01 = lerp(_hash(x0, y0, z1, seed), _hash(x1, y0, z1, seed), ux)
    c11 = lerp(_hash(x0, y1, z1, seed), _hash(x1, y1, z1, seed), ux)
    return lerp(lerp(c00, c10, uy), lerp(c01, c11, uy), uz) * 2 - 1


def fbm3(p, octaves=4, seed=0, lacunarity=2.03, gain=0.5):
    total, amp, norm = 0.0, 1.0, 0.0
    q = p
    for o in range(octaves):
        total = total + amp * noise3(q, seed + o * 31)
        norm += amp
        amp *= gain
        q = q * lacunarity + 17.17
    return total / norm


def ridged3(p, octaves=4, seed=0):
    """Ridged noise in [0, 1]: sharp creases for wrinkles, cracks and veins."""
    total, amp, norm = 0.0, 1.0, 0.0
    q = p
    for o in range(octaves):
        total = total + amp * (1 - np.abs(noise3(q, seed + o * 57)))
        norm += amp
        amp *= 0.5
        q = q * 2.1 + 3.3
    return total / norm


def fbm2(x, y, octaves=4, seed=0):
    """2D fbm over image-space coordinate arrays."""
    p = np.stack([x.ravel(), y.ravel(), np.full(x.size, 0.37)], axis=1)
    return fbm3(p, octaves, seed).reshape(x.shape)


# ---------------------------------------------------------------------------
# Distance primitives and operators
# ---------------------------------------------------------------------------

def sd_sphere(p, c, r):
    return length(p - np.asarray(c, float)) - r


def sd_ellipsoid(p, c, radii, rot=None):
    radii = np.asarray(radii, float)
    q = to_local(p, c, rot)
    k0 = length(q / radii)
    k1 = length(q / (radii * radii))
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


def sd_capsule(p, a, b, r):
    a, b = np.asarray(a, float), np.asarray(b, float)
    pa, ba = p - a, b - a
    h = np.clip((pa @ ba) / (ba @ ba), 0, 1)
    return length(pa - h[:, None] * ba) - r


def sd_round_cone(p, a, b, r1, r2):
    """Capsule whose radius tapers from r1 at a to r2 at b."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    ba = b - a
    l2 = ba @ ba
    rr = r1 - r2
    a2 = l2 - rr * rr
    il2 = 1.0 / l2
    pa = p - a
    y = pa @ ba
    z = y - l2
    xv = pa * l2 - y[:, None] * ba
    x2 = np.einsum("ij,ij->i", xv, xv)
    y2 = y * y * l2
    z2 = z * z * l2
    k = np.sign(rr) * rr * rr * x2
    out = (np.sqrt(x2 * a2 * il2) + y * rr) * il2 - r1
    out = np.where(np.sign(z) * a2 * z2 > k, np.sqrt(x2 + z2) * il2 - r2, out)
    out = np.where(np.sign(y) * a2 * y2 < k, np.sqrt(x2 + y2) * il2 - r1, out)
    return out


def sd_tube(p, pts, radii):
    """Union of tapered segments through a polyline of points and radii."""
    d = None
    for i in range(len(pts) - 1):
        di = sd_round_cone(p, pts[i], pts[i + 1], radii[i], radii[i + 1])
        d = di if d is None else np.minimum(d, di)
    return d


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b + (a - b) * h - k * h * (1 - h)


def smax(a, b, k):
    return -smin(-a, -b, k)


class Field:
    """Accumulates a scene: distance plus the material of the closest part."""

    def __init__(self, n):
        self.d = np.full(n, 1e9)
        self.m = np.zeros(n, np.int32)

    def add(self, d, mat, k=0.0):
        """Union with material mat; k > 0 blends the surfaces smoothly."""
        closer = d < self.d
        self.d = smin(self.d, d, k) if k > 0 else np.minimum(self.d, d)
        self.m = np.where(closer, mat, self.m)
        return self

    def add_group(self, p, center, radius, fn, margin=0.02):
        """Union with a multi-material sub-scene fn(points) -> Field that is
        only evaluated inside a bounding sphere."""
        db = length(p - np.asarray(center, float)) - radius
        inside = db < margin
        if inside.any():
            sub = fn(p[inside])
            idx = np.where(inside)[0]
            closer = sub.d < self.d[idx]
            self.d[idx] = np.minimum(self.d[idx], sub.d)
            self.m[idx] = np.where(closer, sub.m, self.m[idx])
        out = ~inside
        self.d[out] = np.minimum(self.d[out], db[out])
        return self


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------

class Material:
    """color: base linear RGB; tex(p, n) -> (N, 3) multiplier, or the colour
    itself when tex_mode == "replace"; wrap: light wrap for skin and cloth;
    sss: colour of light scattered under the skin near the shadow line;
    spec/gloss: specular strength and Blinn exponent; emit: self-light RGB;
    sheen: grazing-angle brightening for cloth and fur."""

    def __init__(self, color, tex=None, wrap=0.0, spec=0.04, gloss=20.0, emit=None, tex_mode="mul",
                 sheen=0.0, sss=None, spec_tex=None):
        self.color = np.asarray(color, float)
        self.tex = tex
        self.wrap = wrap
        self.spec = spec
        self.gloss = gloss
        self.emit = emit
        self.tex_mode = tex_mode
        self.sheen = sheen
        self.sss = None if sss is None else np.asarray(sss, float)
        self.spec_tex = spec_tex

    def albedo(self, p, n):
        if self.tex is None:
            return np.broadcast_to(self.color, (len(p), 3)).copy()
        t = self.tex(p, n)
        if t.ndim == 1:
            t = t[:, None]
        return np.broadcast_to(t, (len(p), 3)).copy() if self.tex_mode == "replace" else self.color * t


# ---------------------------------------------------------------------------
# Camera, lights and the renderer
# ---------------------------------------------------------------------------

class Camera:
    def __init__(self, pos, target, fov=30.0, up=(0, 1, 0)):
        self.pos = np.asarray(pos, float)
        self.target = np.asarray(target, float)
        self.fov = fov
        self.up = np.asarray(up, float)

    def rays(self, w, h):
        fwd = normalize(self.target - self.pos)
        right = normalize(np.cross(fwd, self.up))
        up = np.cross(right, fwd)
        t = math.tan(math.radians(self.fov) / 2)
        xs = ((np.arange(w) + 0.5) / w * 2 - 1) * t * w / h
        ys = (1 - (np.arange(h) + 0.5) / h * 2) * t
        gx, gy = np.meshgrid(xs, ys)
        d = fwd[None, :] + gx.ravel()[:, None] * right[None, :] + gy.ravel()[:, None] * up[None, :]
        return np.broadcast_to(self.pos, d.shape).copy(), normalize(d)


class Light:
    """Directional light when pos is None (direction points toward the light),
    otherwise a point light with distance falloff; aim + cone=(inner, outer)
    degrees turn a point light into a spotlight."""

    def __init__(self, color, intensity=1.0, direction=None, pos=None, shadow=True, softness=12.0,
                 falloff=0.15, aim=None, cone=(15.0, 35.0)):
        self.color = np.asarray(color, float) * intensity
        self.direction = None if direction is None else normalize(np.asarray(direction, float))
        self.pos = None if pos is None else np.asarray(pos, float)
        self.shadow = shadow
        self.softness = softness
        self.falloff = falloff
        self.spot = None
        if aim is not None and self.pos is not None:
            self.spot = (normalize(np.asarray(aim, float) - self.pos), math.cos(math.radians(cone[0])),
                         math.cos(math.radians(cone[1])))


def march(sdf, ro, rd, max_dist, steps, eps):
    n = len(ro)
    t = np.zeros(n)
    hit = np.zeros(n, bool)
    active = np.arange(n)
    for _ in range(steps):
        if active.size == 0:
            break
        p = ro[active] + rd[active] * t[active, None]
        d = sdf(p).d
        t[active] += d * 0.8
        done_hit = d < eps * (1 + t[active])
        done_miss = t[active] > max_dist
        hit[active[done_hit]] = True
        active = active[~(done_hit | done_miss)]
    return t, hit


def calc_normals(sdf, p, e=6e-4):
    k = np.array([[1, -1, -1], [-1, -1, 1], [-1, 1, -1], [1, 1, 1]], float)
    n = np.zeros_like(p)
    for kk in k:
        n += kk[None, :] * sdf(p + kk * e).d[:, None]
    return normalize(n)


def soft_shadow(sdf, p, l, k, tmax, steps=48):
    n = len(p)
    res = np.ones(n)
    t = np.full(n, 0.01)
    active = np.arange(n)
    for _ in range(steps):
        if active.size == 0:
            break
        h = sdf(p[active] + l[active] * t[active, None]).d
        res[active] = np.minimum(res[active], k * h / t[active])
        t[active] += np.clip(h, 0.004, 0.2)
        keep = (res[active] > 0.002) & (t[active] < tmax[active])
        active = active[keep]
    return np.clip(res, 0, 1)


def ambient_occlusion(sdf, p, n, scale):
    occ = np.zeros(len(p))
    w = 1.0
    for i in range(1, 6):
        h = scale * (0.02 + 0.22 * i / 5)
        occ += (h - sdf(p + n * h).d) * w
        w *= 0.7
    return np.clip(1 - 2.2 * occ / scale, 0, 1)


def render(scene, materials, camera, lights, size, ss=2, background=None, ambient=(0.05, 0.05, 0.06),
           ground_ambient=None, rim=None, fog=None, max_dist=40.0, steps=160, eps=4e-4, ao_scale=0.25,
           shadow_dist=12.0):
    """Ray-march scene (a function p -> Field) and shade it.

    background(rd) -> (N, 3) linear RGB for rays that miss; rim = (rgb, power)
    adds edge light; fog = (rgb, density, start). Returns linear 'rgb'
    (h, w, 3), 'alpha' coverage and 'depth', supersampled ss x ss.

    """
    w, h = size
    W, H = w * ss, h * ss
    ro, rd = camera.rays(W, H)
    t, hit = march(scene, ro, rd, max_dist, steps, eps)
    rgb = np.zeros((W * H, 3))
    if background is not None:
        rgb[~hit] = background(rd[~hit])
    idx = np.where(hit)[0]
    if idx.size:
        p = ro[idx] + rd[idx] * t[idx, None]
        n = calc_normals(scene, p)
        mat = scene(p).m
        v = -rd[idx]
        ao = ambient_occlusion(scene, p, n, ao_scale)
        albedo = np.zeros((idx.size, 3))
        wrap = np.zeros(idx.size)
        spec = np.zeros(idx.size)
        gloss = np.ones(idx.size)
        emit = np.zeros((idx.size, 3))
        sheen = np.zeros(idx.size)
        sss = np.zeros((idx.size, 3))
        for mi, m in enumerate(materials):
            sel = mat == mi
            if not sel.any():
                continue
            albedo[sel] = m.albedo(p[sel], n[sel])
            wrap[sel], gloss[sel], sheen[sel] = m.wrap, m.gloss, m.sheen
            spec[sel] = m.spec if m.spec_tex is None else m.spec * m.spec_tex(p[sel], n[sel])
            if m.emit is not None:
                emit[sel] = m.emit(p[sel], n[sel]) if callable(m.emit) else m.emit
            if m.sss is not None:
                sss[sel] = m.sss
        albedo = np.clip(albedo, 0, 4)
        amb = np.asarray(ambient, float)[None, :]
        gnd = amb * 0.35 if ground_ambient is None else np.asarray(ground_ambient, float)[None, :]
        hemi = amb * (0.5 + 0.5 * n[:, 1:2]) + gnd * (0.5 - 0.5 * n[:, 1:2])
        col = albedo * hemi * ao[:, None]
        for light in lights:
            if light.pos is None:
                ldir = np.broadcast_to(light.direction, p.shape)
                atten = np.ones(idx.size)
                tmax = np.full(idx.size, shadow_dist)
            else:
                lv = light.pos[None, :] - p
                dist = length(lv)
                ldir = lv / dist[:, None]
                atten = 1.0 / (1.0 + light.falloff * dist * dist)
                if light.spot is not None:
                    axis, cin, cout = light.spot
                    atten = atten * smoothstep(cout, cin, -(ldir @ axis))
                tmax = dist
            ndl = np.einsum("ij,ij->i", n, ldir)
            diff = np.clip((ndl + wrap) / (1 + wrap), 0, 1)
            sh = np.ones(idx.size)
            lit = diff > 0
            if light.shadow and lit.any():
                li = np.where(lit)[0]
                sh[li] = soft_shadow(scene, p[li] + n[li] * 0.003, ldir[li], light.softness, tmax[li])
                sh = np.maximum(sh, wrap * 0.3 * (1 - np.clip(ndl, 0, 1)))
            hvec = normalize(ldir + v)
            ndh = np.clip(np.einsum("ij,ij->i", n, hvec), 0, 1)
            fres = 0.25 + 0.75 * (1 - np.clip(np.einsum("ij,ij->i", v, hvec), 0, 1)) ** 5
            sp = spec * fres * ndh ** gloss * (gloss + 8) / 25.0 * (ndl > 0)
            # scattered light reddens the band just inside the shadow line
            band = np.clip(1 - np.abs(ndl) * 3, 0, 1) * (ndl > -0.3)
            lcol = light.color[None, :] * (atten * sh)[:, None]
            col += (albedo * diff[:, None] + sp[:, None] + sss * band[:, None] * 0.6) * lcol
        if rim is not None:
            rc, rp = rim
            ndv = np.clip(np.einsum("ij,ij->i", n, v), 0, 1)
            col += np.asarray(rc, float)[None, :] * ((1 - ndv) ** rp * ao)[:, None]
        if sheen.any():
            ndv = np.clip(np.einsum("ij,ij->i", n, v), 0, 1)
            col += albedo * (sheen * (1 - ndv) ** 2.5 * ao)[:, None] * 0.35
        col += emit
        if fog is not None:
            fc, dens, start = fog
            f = 1 - np.exp(-dens * np.maximum(t[idx] - start, 0))
            col = col * (1 - f[:, None]) + np.asarray(fc, float)[None, :] * f[:, None]
        rgb[idx] = col
    depth = np.where(hit, t, max_dist)
    rgb = rgb.reshape(H, W, 3).reshape(h, ss, w, ss, 3).mean(axis=(1, 3))
    alpha = hit.reshape(H, W).astype(float).reshape(h, ss, w, ss).mean(axis=(1, 3))
    depth = depth.reshape(H, W).reshape(h, ss, w, ss).min(axis=(1, 3))
    return {"rgb": rgb, "alpha": alpha, "depth": depth}


# ---------------------------------------------------------------------------
# Image finishing: tone, grade and the wear of an old print
# ---------------------------------------------------------------------------

def tonemap(rgb, exposure=1.0):
    """Filmic (ACES-like) curve from linear light to display sRGB 0..1."""
    x = np.maximum(rgb * exposure, 0)
    y = np.clip((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0, 1)
    return np.where(y <= 0.0031308, 12.92 * y, 1.055 * np.power(y, 1 / 2.4) - 0.055)


def grade(img, saturation=0.6, shadows=(0.0, 0.0, 0.0), highlights=(0.0, 0.0, 0.0), contrast=1.0, black=0.0):
    """Desaturate, split-tone, S-curve about mid grey and set the black point."""
    lum = (img @ np.array([0.299, 0.587, 0.114]))[..., None]
    out = lum + (img - lum) * saturation
    out = out + np.asarray(shadows) * np.clip(1 - lum * 1.6, 0, 1) + np.asarray(highlights) * np.clip((lum - 0.45) * 1.8, 0, 1)
    out = (out - 0.5) * contrast + 0.5
    return np.clip((out - black) / (1 - black), 0, 1)


def blur(img, radius):
    if radius <= 0:
        return img
    pil = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    return np.asarray(pil.filter(ImageFilter.GaussianBlur(radius))).astype(float) / 255


def smoke(img, depth, seed, strength=0.3, color=(0.5, 0.45, 0.38), source=(0.3, 0.1), scale=3.0, far=None):
    """Drifting smoke: a noisy veil, thickest toward a light source in the
    frame and over distant parts, so near subjects stand out of it."""
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    u, v = xx / max(h, w), yy / max(h, w)
    n = fbm2(u * scale * 2 + seed, v * scale * 3, 6, seed)
    n = np.clip(n * 1.6 + 0.35, 0, 1) ** 1.6
    lightish = np.exp(-(((xx + 0.5) / w - source[0]) ** 2 + ((yy + 0.5) / h - source[1]) ** 2) * 3.0)
    deep = 1.0 if far is None else np.clip((depth - far[0]) / (far[1] - far[0]), 0.15, 1.0)
    veil = (n * (0.35 + 0.65 * lightish) * deep * strength)[..., None]
    return img * (1 - veil * 0.5) + np.asarray(color) * veil


def halation(img, threshold=0.7, radius=3.0, strength=0.5, tint=(1.0, 0.75, 0.55)):
    """Glow round bright areas, warm like light scattering in old film."""
    bright = np.clip((img - threshold) / (1 - threshold), 0, 1)
    return np.clip(img + blur(bright, radius) * strength * np.asarray(tint), 0, 1)


def vignette(img, strength=0.5, power=2.2, center=(0.5, 0.5)):
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.sqrt(((xx + 0.5) / w - center[0]) ** 2 * (w / h) + ((yy + 0.5) / h - center[1]) ** 2) / 0.75
    return img * (1 - strength * np.clip(d, 0, 1.4) ** power)[..., None]


def to_image(img, alpha=None):
    arr = (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
    a = np.full(arr.shape[:2], 255, np.uint8) if alpha is None else (np.clip(alpha, 0, 1) * 255 + 0.5).astype(np.uint8)
    return Image.fromarray(np.dstack([arr, a]), "RGBA")
