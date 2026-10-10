"""Stroke-based repainting: turns a rendered reference into an oil painting.

Brushes from large to small lay strokes where the canvas still differs from
the reference; each stroke takes the reference colour where it starts and
follows the contours of the forms until the colour under it changes."""

import math

import numpy as np
from PIL import Image, ImageDraw

import art_render as R


def paint_from_image(ref, brushes=(16, 8, 4, 2), seed=0, threshold=0.05, max_len=14, curve=0.6,
                     underpaint_blur=12.0, bristle=True):
    """Stroke-based repainting of a reference picture (Hertzmann's method).

    For each brush, from the largest to the smallest, strokes are started
    where the canvas still differs from the (blurred) reference, take the
    reference colour at their start, and run along the contours - across the
    colour gradient - until the colour under them changes. Big brushes block
    in, small ones only go where detail is needed, so flat areas keep broad
    strokes and edges get fine ones, like a painting. ref: (H, W, 3) 0..1."""
    rng = np.random.default_rng(seed)
    H, W, _ = ref.shape
    canvas = Image.fromarray((np.clip(R.blur(ref, underpaint_blur), 0, 1) * 255).astype(np.uint8))
    draw = ImageDraw.Draw(canvas, "RGBA")
    for radius in brushes:
        refb = R.blur(ref, radius * 0.5) if radius > 1 else ref
        lum = refb @ np.array([0.299, 0.587, 0.114])
        gy, gx = np.gradient(lum)
        gmag = np.sqrt(gx * gx + gy * gy)
        cur = np.asarray(canvas).astype(float) / 255
        diff = np.linalg.norm(cur - refb, axis=2)
        grid = max(1, int(radius))
        area = R.blur(np.repeat(diff[..., None], 3, 2), grid * 0.5)[..., 0]
        ys, xs = np.mgrid[grid // 2:H:grid, grid // 2:W:grid]
        ys, xs = ys.ravel(), xs.ravel()
        jy = np.clip(ys + rng.integers(-grid // 2, grid // 2 + 1, ys.size), 0, H - 1)
        jx = np.clip(xs + rng.integers(-grid // 2, grid // 2 + 1, xs.size), 0, W - 1)
        keep = area[jy, jx] > threshold
        order = rng.permutation(np.where(keep)[0])
        width = max(1, int(round(radius * 2)))
        for i in order:
            y, x = float(jy[i]), float(jx[i])
            c = refb[int(y), int(x)]
            pts = [(x, y)]
            dx, dy = 0.0, 0.0
            for _ in range(max_len):
                iy, ix = int(y), int(x)
                if gmag[iy, ix] < 1e-4:
                    break
                ndx, ndy = -gy[iy, ix] / gmag[iy, ix], gx[iy, ix] / gmag[iy, ix]
                if dx * ndx + dy * ndy < 0:
                    ndx, ndy = -ndx, -ndy
                if pts[1:]:
                    ndx, ndy = curve * ndx + (1 - curve) * dx, curve * ndy + (1 - curve) * dy
                    nn = math.hypot(ndx, ndy) or 1.0
                    ndx, ndy = ndx / nn, ndy / nn
                x, y = x + ndx * radius, y + ndy * radius
                if not (0 <= x < W and 0 <= y < H):
                    break
                if np.abs(refb[int(y), int(x)] - c).sum() > threshold * 3:
                    break
                pts.append((x, y))
                dx, dy = ndx, ndy
            jit = 1 + rng.normal(0, 0.035, 3)
            col = np.clip(c * jit, 0, 1)
            fill = tuple(int(v * 255) for v in col) + (225,)
            if len(pts) == 1:
                draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=fill)
                continue
            draw.line(pts, fill=fill, width=width, joint="curve")
            if bristle and width >= 3:
                # a couple of bristle tracks of slightly different paint
                for off in (-0.35, 0.35):
                    p2 = [(px - dy * off * width, py + dx * off * width) for px, py in pts]
                    bc = np.clip(col * (1 + rng.normal(0, 0.06, 3)), 0, 1)
                    draw.line(p2, fill=tuple(int(v * 255) for v in bc) + (110,), width=max(1, width // 4))
    return np.asarray(canvas).astype(float) / 255
