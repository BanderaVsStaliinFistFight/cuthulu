"""A small procedural painter: dry-brush acrylic strokes on dark canvas.

Pictures are painted at several times their final size and reduced at the
end. A stroke is a polyline in normalised picture coordinates (x right, y
down, both 0..1 of the canvas width/height) drawn as a bundle of bristles;
each bristle runs out of paint along the stroke and skips where the canvas
weave is high, so the dark ground shows through like real dry brushing.
"""

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import art_render as R


def catmull(points, n=40):
    """Smooth curve through control points -> (n, 2) array."""
    pts = np.asarray(points, float)
    P = np.vstack([pts[0] * 2 - pts[1], pts, pts[-1] * 2 - pts[-2]])
    out = []
    segs = len(pts) - 1
    for i in range(n):
        u = i / (n - 1) * segs
        k = min(int(u), segs - 1)
        t = u - k
        p0, p1, p2, p3 = P[k], P[k + 1], P[k + 2], P[k + 3]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t +
                          (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t))
    return np.array(out)


class Curve:
    """Polyline sampled densely so points can be fetched by parameter t."""

    def __init__(self, points, n=200):
        self.pts = catmull(points, n)

    def at(self, t):
        t = np.clip(np.asarray(t, float), 0, 1) * (len(self.pts) - 1)
        i = np.minimum(t.astype(int), len(self.pts) - 2)
        f = (t - i)[..., None]
        return self.pts[i] * (1 - f) + self.pts[i + 1] * f


def ramp(stops):
    """Colour ramp: list of (value, rgb) -> function v -> rgb."""
    xs = np.array([s[0] for s in stops])
    cs = np.array([s[1] for s in stops], float)

    def f(v):
        v = np.asarray(v, float)
        return np.stack([np.interp(v, xs, cs[:, i]) for i in range(3)], -1)
    return f


class Painter:
    def __init__(self, size, scale=4, seed=0, ground=(0.035, 0.03, 0.025)):
        self.w, self.h = size[0] * scale, size[1] * scale
        self.size = size
        self.scale = scale
        self.rng = np.random.default_rng(seed)
        self.seed = seed
        self.img = Image.new("RGB", (self.w, self.h), tuple(int(v * 255) for v in ground))
        self.draw = ImageDraw.Draw(self.img, "RGBA")
        yy, xx = np.mgrid[0:self.h, 0:self.w]
        # canvas weave: where it is high, a nearly dry brush still leaves paint
        self.weave = 0.5 + 0.25 * np.sin(xx * 1.9) * np.sin(yy * 1.9) + 0.25 * R.fbm2(xx / 6.0, yy / 6.0, 2, seed)

    def px(self, pts):
        pts = np.asarray(pts, float)
        return np.stack([pts[..., 0] * self.w, pts[..., 1] * self.h], -1)

    def stroke(self, pts, width, color, alpha=0.9, bristles=6, load=(1.0, 0.45), jitter=0.06, dry=0.25):
        """Paint a bristle-bundle stroke along pts (normalised coords).

        width is in canvas widths; load = paint at the start and end; dry
        raises how much the bristles skip, letting the ground show."""
        p = self.px(pts)
        if len(p) < 2:
            return
        seg = np.diff(p, axis=0)
        tang = np.vstack([seg, seg[-1:]])
        tang /= np.maximum(np.linalg.norm(tang, axis=1, keepdims=True), 1e-9)
        nrm = np.stack([-tang[:, 1], tang[:, 0]], 1)
        wpx = width * self.w
        nb = max(2, bristles)
        bw = max(1, int(round(wpx / nb * 1.6)))
        color = np.asarray(color, float)
        n = len(p)
        prog = np.linspace(0, 1, n)
        paint = load[0] + (load[1] - load[0]) * prog
        for k in range(nb):
            off = (k / (nb - 1) - 0.5) * wpx * (0.9 + 0.2 * self.rng.random())
            q = p + nrm * off + self.rng.normal(0, 0.25, p.shape)
            c = np.clip(color * (1 + self.rng.normal(0, jitter, 3)) + self.rng.normal(0, jitter * 0.3), 0, 1)
            a = alpha * (0.55 + 0.45 * self.rng.random())
            # where does this bristle still carry paint?
            xi = np.clip(q[:, 0].astype(int), 0, self.w - 1)
            yi = np.clip(q[:, 1].astype(int), 0, self.h - 1)
            noise = self.rng.random(n) * 0.35 + self.weave[yi, xi] * 0.65
            wet = noise + paint - 0.5 - dry > 0
            if not wet.any():
                continue
            # draw contiguous wet runs
            idx = np.where(wet)[0]
            breaks = np.where(np.diff(idx) > 1)[0]
            starts = np.concatenate([[0], breaks + 1])
            ends = np.concatenate([breaks, [len(idx) - 1]])
            fill = tuple(int(v * 255) for v in c) + (int(a * 255),)
            for s, e in zip(starts, ends):
                run = q[idx[s]:idx[e] + 1]
                if len(run) >= 2:
                    self.draw.line([tuple(v) for v in run], fill=fill, width=bw, joint="curve")

    def dab(self, x, y, r, color, alpha=0.8):
        px, py = x * self.w, y * self.h
        rp = r * self.w
        self.draw.ellipse([px - rp, py - rp, px + rp, py + rp],
                          fill=tuple(int(v * 255) for v in color) + (int(alpha * 255),))

    def array(self):
        return np.asarray(self.img).astype(float) / 255

    def finish(self, sharpen=True):
        """Reduce to the final size."""
        img = self.img.resize(self.size, Image.LANCZOS)
        if sharpen:
            img = img.filter(ImageFilter.UnsharpMask(radius=0.8, percent=60, threshold=1))
        return np.asarray(img).astype(float) / 255


def band_strokes(painter, inner, outer, n, color_fn, width=0.012, length=(0.10, 0.25), t_range=(0.0, 1.0),
                 s_range=(0.0, 1.0), alpha=0.9, bristles=6, dry=0.25, steps=24, load=(1.0, 0.45)):
    """Strokes running along the family of lines between two curves.

    A point in the band is (s, t): s = 0 on `inner`, 1 on `outer`; t runs
    along both curves. color_fn(s, t) -> rgb for the stroke's start."""
    rng = painter.rng
    for _ in range(n):
        s = rng.uniform(*s_range)
        t0 = rng.uniform(t_range[0] - 0.05, t_range[1])
        L = rng.uniform(*length)
        ts = np.linspace(t0, t0 + L, steps)
        ts = ts[(ts >= t_range[0]) & (ts <= t_range[1])]
        if len(ts) < 3:
            continue
        s_wob = s + 0.008 * np.sin(ts * 9 + s * 20)
        pts = inner.at(ts) * (1 - s_wob)[:, None] + outer.at(ts) * s_wob[:, None]
        painter.stroke(pts, width * rng.uniform(0.7, 1.3), color_fn(s, t0), alpha, bristles, load=load, dry=dry)
