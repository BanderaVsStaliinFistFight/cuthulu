#!/usr/bin/env python3
"""Procedurally generate every texture used by Eldritch Pacts.

Writes uncompressed 32-bit DDS files (A8R8G8B8) that HoI4 can load directly,
thumbnail.png for the launcher, and interface/eldritch.gfx with a sprite for
every texture. Run from anywhere:

    python3 tools/generate_art.py

Requires Pillow and numpy. Output is deterministic (fixed random seeds).
The King in Yellow's portrait is sculpted, lit and painted by
tools/art_portraits.py, which takes about a minute; the battalion icons are
small rendered scenes from tools/art_units.py, rendered in parallel (a few
minutes in all); everything else is drawn here. To redo only some of it:

    python3 tools/generate_art.py units       # battalion icons only
"""

import math
import os
import random
import struct
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import art_portraits
import art_units

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SS = 4  # supersampling factor for anti-aliased drawing

IDEA_SIZE = (64, 67)
DECISION_SIZE = (46, 46)
REPORT_SIZE = (210, 176)
NEWS_SIZE = (397, 153)
PORTRAIT_SIZE = (156, 210)
TRAIT_SIZE = (40, 40)

GODS = ["cthulhu", "hastur", "azathoth"]

PALETTE = {
    "cthulhu": {"main": (95, 179, 122), "dark": (25, 70, 52), "glow": (120, 255, 170), "bg": (8, 28, 26)},
    "hastur": {"main": (240, 197, 65), "dark": (110, 80, 15), "glow": (255, 225, 120), "bg": (30, 22, 8)},
    "azathoth": {"main": (230, 60, 170), "dark": (70, 10, 60), "glow": (255, 170, 80), "bg": (26, 6, 24)},
}


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_dds(img, rel_path):
    """Save an RGBA image as an uncompressed A8R8G8B8 DDS (no mipmaps)."""
    img = img.convert("RGBA")
    w, h = img.size
    header = struct.pack(
        "<4sIIIIIII11I",
        b"DDS ", 124,
        0x1 | 0x2 | 0x4 | 0x8 | 0x1000,  # CAPS | HEIGHT | WIDTH | PITCH | PIXELFORMAT
        h, w, w * 4, 0, 0,
        *([0] * 11),
    )
    pixel_format = struct.pack(
        "<II4sIIIII",
        32, 0x41, b"\0\0\0\0", 32,  # RGB | ALPHAPIXELS
        0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000,
    )
    caps = struct.pack("<IIIII", 0x1000, 0, 0, 0, 0)
    bgra = np.array(img)[:, :, [2, 1, 0, 3]].tobytes()
    path = os.path.join(ROOT, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(header + pixel_format + caps + bgra)


# ---------------------------------------------------------------------------
# Drawing helpers (all coordinates are fractions of the canvas size)
# ---------------------------------------------------------------------------

class Canvas:
    """Supersampled transparent RGBA canvas addressed in 0..1 coordinates."""

    def __init__(self, w, h):
        self.w, self.h = w * SS, h * SS
        self.img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def p(self, x, y):
        return (x * self.w, y * self.h)

    def s(self, v):
        return v * min(self.w, self.h)

    def ellipse(self, cx, cy, rx, ry, fill, outline=None, width=0):
        x, y = self.p(cx, cy)
        rx, ry = self.s(rx), self.s(ry)
        self.d.ellipse([x - rx, y - ry, x + rx, y + ry], fill=fill, outline=outline,
                       width=int(self.s(width)))

    def poly(self, pts, fill, outline=None, width=0):
        self.d.polygon([self.p(x, y) for x, y in pts], fill=fill, outline=outline)
        if outline and width:
            self.line(pts + [pts[0]], outline, width)

    def line(self, pts, fill, width):
        self.d.line([self.p(x, y) for x, y in pts], fill=fill, width=max(1, int(self.s(width))),
                    joint="curve")

    def stroke(self, pts, fill, r0, r1):
        """Tapered stroke: circles of radius r0 -> r1 along a polyline."""
        n = len(pts)
        for i, (x, y) in enumerate(pts):
            t = i / max(1, n - 1)
            r = r0 + (r1 - r0) * t
            self.ellipse(x, y, r, r, fill)

    def done(self, w, h):
        return self.img.resize((w, h), Image.LANCZOS)


def glow_under(img, color, radius, strength=1.0):
    """Return img composited over a blurred, coloured copy of its alpha."""
    alpha = img.split()[3]
    blurred = alpha.filter(ImageFilter.GaussianBlur(radius))
    if strength != 1.0:
        blurred = blurred.point(lambda v: min(255, int(v * strength)))
    halo = Image.new("RGBA", img.size, color + (0,))
    halo.putalpha(blurred)
    return Image.alpha_composite(halo, img)


def radial_bg(size, inner, outer, center=(0.5, 0.5), scale=1.0):
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w]
    cx, cy = center[0] * w, center[1] * h
    dist = np.sqrt(((xx - cx) / (w * scale)) ** 2 + ((yy - cy) / (h * scale)) ** 2) * 1.6
    t = np.clip(dist, 0, 1)[..., None]
    rgb = np.array(inner) * (1 - t) + np.array(outer) * t
    a = np.full((h, w, 1), 255)
    return Image.fromarray(np.concatenate([rgb, a], axis=2).astype(np.uint8), "RGBA")


def vertical_bg(size, top, bottom):
    w, h = size
    t = np.linspace(0, 1, h)[:, None, None]
    rgb = np.array(top) * (1 - t) + np.array(bottom) * t
    rgb = np.broadcast_to(rgb, (h, w, 3))
    a = np.full((h, w, 1), 255)
    return Image.fromarray(np.concatenate([rgb, a], axis=2).astype(np.uint8), "RGBA")


def vignette(img, strength=0.7):
    w, h = img.size
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2) / math.sqrt(2)
    factor = 1 - strength * np.clip(d, 0, 1) ** 2
    arr = np.array(img).astype(float)
    arr[..., :3] *= factor[..., None]
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")


def grain(img, amount=8, seed=0):
    rng = np.random.default_rng(seed)
    arr = np.array(img).astype(float)
    noise = rng.normal(0, amount, arr.shape[:2])[..., None]
    arr[..., :3] += noise
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")


def stars(img, count, max_y=1.0, seed=0):
    rng = random.Random(seed)
    d = ImageDraw.Draw(img)
    w, h = img.size
    for _ in range(count):
        x, y = rng.uniform(0, w), rng.uniform(0, h * max_y)
        b = rng.randint(120, 255)
        r = rng.choice([0, 0, 0, 1])
        d.ellipse([x - r, y - r, x + r, y + r], fill=(b, b, min(255, b + 20), 255))
    return img


def paste_center(base, layer, cx, cy):
    """Alpha-composite layer onto base, centred at fractional (cx, cy)."""
    x = int(cx * base.width - layer.width / 2)
    y = int(cy * base.height - layer.height / 2)
    out = base.copy()
    tmp = Image.new("RGBA", base.size, (0, 0, 0, 0))
    tmp.paste(layer, (x, y), layer)
    return Image.alpha_composite(out, tmp)


def tint(img, color, amount):
    arr = np.array(img).astype(float)
    arr[..., :3] = arr[..., :3] * (1 - amount) + np.array(color) * amount
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")


def to_sepia(img):
    arr = np.array(img).astype(float)
    g = arr[..., :3].mean(axis=2)
    arr[..., 0] = g * 1.07 + 10
    arr[..., 1] = g * 0.97 + 4
    arr[..., 2] = g * 0.82
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")


def tentacle(c, x0, y0, length, sway, phase, r0, r1, color, freq=1.6, steps=90, dx=0.0):
    pts = []
    for i in range(steps):
        t = i / (steps - 1)
        x = x0 + dx * t + sway * math.sin(freq * math.pi * t + phase) * t
        y = y0 + length * t
        pts.append((x, y))
    c.stroke(pts, color, r0, r1)


# ---------------------------------------------------------------------------
# Symbols - each returns an RGBA image of the given pixel size
# ---------------------------------------------------------------------------

def sym_cthulhu(size, color=None):
    pal = PALETTE["cthulhu"]
    main = color or pal["main"]
    dark = tuple(int(v * 0.45) for v in main)
    c = Canvas(size, size)
    # wings
    c.poly([(0.36, 0.30), (0.05, 0.10), (0.12, 0.30), (0.03, 0.42), (0.14, 0.48), (0.08, 0.62), (0.36, 0.50)], dark + (255,))
    c.poly([(0.64, 0.30), (0.95, 0.10), (0.88, 0.30), (0.97, 0.42), (0.86, 0.48), (0.92, 0.62), (0.64, 0.50)], dark + (255,))
    # tentacles
    for i, x in enumerate([0.36, 0.42, 0.47, 0.53, 0.58, 0.64]):
        tentacle(c, x, 0.50, 0.44 - abs(x - 0.5) * 0.6, 0.06 * (1 if i % 2 else -1), i * 0.9,
                 0.045, 0.008, main + (255,), dx=(x - 0.5) * 0.5)
    # head
    c.ellipse(0.5, 0.34, 0.20, 0.23, main + (255,))
    c.ellipse(0.45, 0.26, 0.07, 0.08, tuple(min(255, v + 25) for v in main) + (255,))
    # eyes
    for ex in (0.42, 0.58):
        c.ellipse(ex, 0.40, 0.045, 0.03, (255, 230, 90, 255))
        c.ellipse(ex, 0.40, 0.012, 0.028, (20, 10, 0, 255))
    return glow_under(c.done(size, size), pal["glow"], size / 18, 0.8)


def sym_hastur(size, color=None):
    pal = PALETTE["hastur"]
    main = color or pal["main"]
    c = Canvas(size, size)
    for k in range(3):
        base = math.radians(90 + k * 120)
        pts = []
        for i in range(70):
            t = i / 69
            r = 0.08 + 0.34 * t
            a = base + t * math.radians(140)
            pts.append((0.5 + r * math.cos(a), 0.52 - r * math.sin(a)))
        c.stroke(pts, main + (255,), 0.055, 0.018)
        # hook at the end
        ex, ey = pts[-1]
        a_end = base + math.radians(140)
        hook = []
        for i in range(30):
            t = i / 29
            a = a_end + math.radians(90) + t * math.radians(150)
            hook.append((ex + 0.07 * math.cos(a) + 0.07 * math.cos(a_end + math.radians(-90)),
                         ey - 0.07 * math.sin(a) - 0.07 * math.sin(a_end + math.radians(-90))))
        c.stroke(hook, main + (255,), 0.018, 0.01)
    c.ellipse(0.5, 0.52, 0.07, 0.07, main + (255,))
    c.ellipse(0.5, 0.52, 0.035, 0.035, (40, 25, 5, 255))
    return glow_under(c.done(size, size), pal["glow"], size / 14, 0.8)


def sym_azathoth(size, color=None):
    pal = PALETTE["azathoth"]
    c = Canvas(size, size)
    for arm in range(4):
        base = arm * math.pi / 2
        pts = []
        for i in range(120):
            t = i / 119
            a = base + t * 3.4 * math.pi
            r = 0.02 + 0.42 * t
            pts.append((0.5 + r * math.cos(a), 0.5 + r * math.sin(a)))
        n = len(pts)
        for i, (x, y) in enumerate(pts):
            t = i / (n - 1)
            col = (int(255 - 40 * t), int(220 - 190 * t), int(160 - 30 * t), int(255 - 100 * t))
            c.ellipse(x, y, 0.05 - 0.04 * t, 0.05 - 0.04 * t, col)
    rng = random.Random(11)
    for _ in range(40):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(0.1, 0.48)
        c.ellipse(0.5 + r * math.cos(a), 0.5 + r * math.sin(a), 0.008, 0.008, (255, 230, 200, 230))
    c.ellipse(0.5, 0.5, 0.08, 0.08, (255, 250, 230, 255))
    return glow_under(c.done(size, size), pal["main"], size / 10, 1.0)


def sym_tome(size, color=None):
    c = Canvas(size, size)
    c.poly([(0.22, 0.16), (0.78, 0.16), (0.82, 0.86), (0.18, 0.86)], (225, 210, 170, 255))
    c.poly([(0.20, 0.12), (0.76, 0.12), (0.76, 0.82), (0.20, 0.82)], (90, 30, 25, 255))
    c.line([(0.25, 0.12), (0.25, 0.82)], (50, 15, 12, 255), 0.03)
    gold = (225, 185, 80, 255)
    c.ellipse(0.50, 0.46, 0.17, 0.17, None, gold, 0.02)
    star = [(0.50 + 0.15 * math.cos(math.radians(90 + k * 144)),
             0.46 - 0.15 * math.sin(math.radians(90 + k * 144))) for k in range(6)]
    c.line(star, gold, 0.018)
    c.ellipse(0.50, 0.46, 0.03, 0.03, (120, 255, 170, 255))
    return glow_under(c.done(size, size), (120, 255, 170), size / 20, 0.5)


def sym_altar(size, color=None):
    c = Canvas(size, size)
    c.poly([(0.18, 0.62), (0.82, 0.62), (0.76, 0.92), (0.24, 0.92)], (80, 75, 85, 255))
    c.poly([(0.14, 0.56), (0.86, 0.56), (0.86, 0.64), (0.14, 0.64)], (110, 105, 115, 255))
    for x in (0.24, 0.76):
        c.poly([(x - 0.03, 0.56), (x + 0.03, 0.56), (x + 0.03, 0.36), (x - 0.03, 0.36)], (30, 25, 25, 255))
        c.ellipse(x, 0.30, 0.03, 0.06, (255, 200, 90, 255))
    c.poly([(0.5, 0.06), (0.62, 0.30), (0.58, 0.50), (0.42, 0.50), (0.38, 0.30)], (140, 255, 170, 255))
    c.poly([(0.5, 0.20), (0.56, 0.36), (0.54, 0.48), (0.46, 0.48), (0.44, 0.36)], (230, 255, 230, 255))
    return glow_under(c.done(size, size), (120, 255, 160), size / 12, 0.8)


def sym_sacrifice(size, color=None):
    c = Canvas(size, size)
    c.poly([(0.20, 0.80), (0.70, 0.18), (0.80, 0.12), (0.76, 0.24), (0.26, 0.86)], (210, 210, 220, 255))
    c.poly([(0.20, 0.80), (0.70, 0.18), (0.80, 0.12), (0.23, 0.83)], (240, 240, 250, 255))
    c.line([(0.12, 0.70), (0.34, 0.92)], (120, 90, 40, 255), 0.05)
    c.line([(0.06, 0.96), (0.20, 0.82)], (60, 30, 20, 255), 0.07)
    for x, y, r in [(0.62, 0.55, 0.05), (0.72, 0.70, 0.04), (0.58, 0.78, 0.035)]:
        c.ellipse(x, y, r, r, (190, 15, 20, 255))
        c.poly([(x - r * 0.9, y - r * 0.3), (x, y - r * 2.4), (x + r * 0.9, y - r * 0.3)], (190, 15, 20, 255))
    return glow_under(c.done(size, size), (255, 40, 40), size / 18, 0.6)


def sym_eye(size, color=(120, 255, 170), rays=(200, 255, 220)):
    c = Canvas(size, size)
    for k in range(12):
        a = math.radians(k * 30)
        c.line([(0.5 + 0.30 * math.cos(a), 0.5 + 0.30 * math.sin(a)),
                (0.5 + 0.46 * math.cos(a), 0.5 + 0.46 * math.sin(a))], rays + (200,), 0.025)
    upper = [(0.12 + 0.76 * t, 0.5 - 0.22 * math.sin(math.pi * t)) for t in np.linspace(0, 1, 40)]
    lower = [(0.88 - 0.76 * t, 0.5 + 0.22 * math.sin(math.pi * t)) for t in np.linspace(0, 1, 40)]
    c.poly(upper + lower, (235, 230, 215, 255))
    c.ellipse(0.5, 0.5, 0.16, 0.16, color + (255,))
    c.ellipse(0.5, 0.5, 0.035, 0.14, (5, 5, 5, 255))
    return glow_under(c.done(size, size), color, size / 14, 0.8)


def sym_deepen(size, color=None):
    return sym_eye(size, (120, 255, 170), (200, 255, 220))


def sym_curse(size, color=None):
    return sym_eye(size, (255, 50, 40), (255, 120, 90))


def sym_chalice(size, color=None):
    c = Canvas(size, size)
    gold = (220, 180, 80, 255)
    c.poly([(0.22, 0.14), (0.78, 0.14), (0.68, 0.40), (0.50, 0.50), (0.32, 0.40)], gold)
    c.poly([(0.25, 0.14), (0.75, 0.14), (0.72, 0.20), (0.28, 0.20)], (60, 10, 70, 255))
    c.poly([(0.46, 0.48), (0.54, 0.48), (0.55, 0.78), (0.45, 0.78)], gold)
    c.poly([(0.28, 0.86), (0.72, 0.86), (0.62, 0.76), (0.38, 0.76)], gold)
    for x, y in [(0.30, 0.30), (0.70, 0.27)]:
        c.ellipse(x, y, 0.02, 0.05, (120, 30, 140, 255))
    c.ellipse(0.5, 0.30, 0.05, 0.05, (160, 255, 200, 255))
    return glow_under(c.done(size, size), (180, 120, 255), size / 14, 0.8)


def sym_crown(size, color=None):
    c = Canvas(size, size)
    gold = (230, 190, 80, 255)
    c.poly([(0.14, 0.78), (0.14, 0.34), (0.32, 0.52), (0.50, 0.18), (0.68, 0.52), (0.86, 0.34), (0.86, 0.78)], gold)
    c.poly([(0.14, 0.70), (0.86, 0.70), (0.86, 0.80), (0.14, 0.80)], (170, 130, 50, 255))
    for x, y in [(0.14, 0.32), (0.50, 0.16), (0.86, 0.32)]:
        c.ellipse(x, y, 0.04, 0.04, (255, 90, 60, 255))
    c.ellipse(0.5, 0.56, 0.09, 0.06, (240, 235, 220, 255))
    c.ellipse(0.5, 0.56, 0.05, 0.05, (120, 255, 170, 255))
    c.ellipse(0.5, 0.56, 0.012, 0.045, (0, 0, 0, 255))
    return glow_under(c.done(size, size), (255, 210, 120), size / 16, 0.6)


def sym_servitors(size, color=None):
    c = Canvas(size, size)
    col = (70, 160, 130, 255)
    for i, (x, h) in enumerate([(0.28, 0.62), (0.5, 0.82), (0.72, 0.58)]):
        pts = []
        for k in range(80):
            t = k / 79
            pts.append((x + 0.08 * math.sin(2.2 * math.pi * t + i), 0.95 - h * t))
        c.stroke(pts, col, 0.07, 0.012)
    c.poly([(0.0, 0.92), (1.0, 0.92), (1.0, 1.0), (0.0, 1.0)], (40, 35, 30, 255))
    return glow_under(c.done(size, size), (120, 255, 200), size / 16, 0.6)


def sym_elder_sign(size, color=None):
    c = Canvas(size, size)
    gold = (220, 180, 90, 255)
    c.ellipse(0.5, 0.5, 0.42, 0.42, None, gold, 0.035)
    star = [(0.5 + 0.40 * math.cos(math.radians(90 + k * 144)),
             0.5 - 0.40 * math.sin(math.radians(90 + k * 144))) for k in range(6)]
    c.line(star, gold, 0.03)
    c.ellipse(0.5, 0.52, 0.10, 0.07, (240, 235, 220, 255))
    c.ellipse(0.5, 0.52, 0.055, 0.055, (120, 255, 170, 255))
    c.ellipse(0.5, 0.52, 0.014, 0.05, (0, 0, 0, 255))
    return glow_under(c.done(size, size), (150, 255, 190), size / 14, 0.8)


def sym_incarnate(size, color=None):
    c = Canvas(size, size)
    body = (25, 18, 35, 255)
    for i, x in enumerate([0.22, 0.34, 0.66, 0.78]):
        tentacle(c, 0.5 + (x - 0.5) * 0.4, 0.42, 0.42, 0.06 * (1 if i % 2 else -1), i, 0.05, 0.012, body,
                 dx=(x - 0.5) * 0.9)
    c.ellipse(0.5, 0.50, 0.22, 0.20, body)
    c.ellipse(0.5, 0.26, 0.14, 0.16, body)
    for ex in (0.44, 0.56):
        c.ellipse(ex, 0.26, 0.03, 0.022, (255, 220, 90, 255))
    c.poly([(0.0, 0.86), (0.08, 0.86), (0.08, 0.78), (0.16, 0.78), (0.16, 0.86), (0.84, 0.86), (0.84, 0.74),
            (0.92, 0.74), (0.92, 0.86), (1.0, 0.86), (1.0, 1.0), (0.0, 1.0)], (10, 10, 14, 255))
    return glow_under(c.done(size, size), (190, 120, 255), size / 10, 1.2)


def sym_commune(size, color=None):
    return sym_eye(size, (190, 120, 255), (220, 190, 255))


def sym_fever(size, color=None):
    return sym_eye(size, (255, 140, 40), (255, 200, 120))


def _prophet(c, robe, face, arms_up=True):
    """A robed, hooded figure; arms raised to the crowd or folded."""
    c.poly([(0.41, 0.40), (0.59, 0.40), (0.70, 0.90), (0.30, 0.90)], robe)
    c.ellipse(0.5, 0.33, 0.075, 0.085, robe)
    c.ellipse(0.5, 0.345, 0.032, 0.04, face)
    if arms_up:
        c.line([(0.43, 0.45), (0.31, 0.32), (0.25, 0.17)], robe, 0.05)
        c.line([(0.57, 0.45), (0.69, 0.32), (0.75, 0.17)], robe, 0.05)
    else:
        c.line([(0.43, 0.45), (0.40, 0.60), (0.56, 0.62)], robe, 0.05)


def sym_preach(size, color=None):
    c = Canvas(size, size)
    for k in range(9):
        a = math.radians(200 + k * 17.5)
        c.line([(0.5 + 0.22 * math.cos(a), 0.42 + 0.22 * math.sin(a)),
                (0.5 + 0.48 * math.cos(a), 0.42 + 0.48 * math.sin(a))], (240, 200, 110, 210), 0.025)
    _prophet(c, (78, 58, 96, 255), (245, 235, 205, 255))
    c.poly([(0.20, 0.76), (0.80, 0.76), (0.80, 0.96), (0.20, 0.96)], (95, 72, 45, 255))
    c.poly([(0.20, 0.76), (0.80, 0.76), (0.80, 0.80), (0.20, 0.80)], (150, 118, 70, 255))
    return glow_under(c.done(size, size), (255, 210, 120), size / 14, 0.8)


def sym_vessel(size, color=None):
    c = Canvas(size, size)
    c.ellipse(0.5, 0.33, 0.20, 0.20, None, (150, 255, 190, 230), 0.03)
    for i, x in enumerate([0.34, 0.42, 0.58, 0.66]):
        tentacle(c, x, 0.52, 0.40, 0.07 * (1 if i % 2 else -1), i * 1.3, 0.035, 0.008, (40, 70, 55, 255),
                 dx=(x - 0.5) * 1.6)
    _prophet(c, (70, 52, 88, 255), (150, 255, 190, 255), arms_up=False)
    return glow_under(c.done(size, size), (120, 255, 170), size / 12, 0.9)


def sym_tithe(size, color=None):
    c = Canvas(size, size)
    gold, rim = (225, 185, 85, 255), (150, 110, 40, 255)
    for x, y in [(0.36, 0.78), (0.36, 0.70), (0.36, 0.62), (0.64, 0.78), (0.64, 0.70)]:
        c.ellipse(x, y, 0.20, 0.07, rim)
        c.ellipse(x, y - 0.015, 0.20, 0.065, gold)
    c.ellipse(0.52, 0.34, 0.24, 0.24, rim)
    c.ellipse(0.52, 0.34, 0.21, 0.21, gold)
    c.ellipse(0.52, 0.34, 0.11, 0.07, (240, 235, 220, 255))
    c.ellipse(0.52, 0.34, 0.055, 0.055, (120, 255, 170, 255))
    c.ellipse(0.52, 0.34, 0.014, 0.05, (0, 0, 0, 255))
    return glow_under(c.done(size, size), (255, 210, 120), size / 16, 0.6)


def sym_council(size, color=None):
    c = Canvas(size, size)
    c.ellipse(0.5, 0.52, 0.30, 0.22, (60, 42, 30, 255))
    c.ellipse(0.5, 0.52, 0.26, 0.18, (85, 60, 40, 255))
    c.ellipse(0.5, 0.52, 0.10, 0.07, None, (150, 255, 190, 255), 0.02)
    c.ellipse(0.5, 0.52, 0.03, 0.03, (190, 255, 210, 255))
    for k in range(7):
        a = math.radians(90 + k * 360 / 7)
        x, y = 0.5 + 0.40 * math.cos(a), 0.52 + 0.31 * math.sin(a)
        c.ellipse(x, y, 0.075, 0.085, (24, 18, 32, 255))
        c.ellipse(x + 0.012 * math.cos(a + math.pi), y + 0.012 * math.sin(a + math.pi), 0.025, 0.03,
                  (230, 220, 195, 255))
    return glow_under(c.done(size, size), (150, 255, 190), size / 14, 0.7)


def sym_march(size, color=None):
    c = Canvas(size, size)
    for i, x in enumerate([0.60, 0.70, 0.80, 0.90]):
        tentacle(c, 0.75, 0.40, 0.5, 0.06 * (1 if i % 2 else -1), i, 0.05, 0.01, (45, 30, 50, 255),
                 dx=(x - 0.75) * 1.2)
    c.ellipse(0.75, 0.30, 0.17, 0.22, (45, 30, 50, 255))
    for ex in (0.70, 0.80):
        c.ellipse(ex, 0.28, 0.025, 0.02, (255, 80, 60, 255))
    _prophet(c, (78, 58, 96, 255), (245, 235, 205, 255))
    return glow_under(c.done(size, size), (255, 90, 70), size / 14, 0.7)


def sym_dread(size, color=None):
    return tint(sym_incarnate(size), (220, 40, 30), 0.5)


def sym_path(size, color=None):
    """A trunk splitting into three branches: Lore, Zeal and Will."""
    c = Canvas(size, size)
    trunk = (190, 160, 100, 255)
    c.line([(0.5, 0.92), (0.5, 0.58)], trunk, 0.05)
    for (x, y), col in (((0.20, 0.24), (120, 170, 255)), ((0.5, 0.13), (255, 90, 70)),
                        ((0.80, 0.24), (130, 255, 170))):
        c.line([(0.5, 0.58), ((0.5 + x) / 2, 0.42), (x, y)], trunk, 0.035)
        c.ellipse(x, y, 0.085, 0.085, col + (255,))
        c.ellipse(x, y, 0.035, 0.035, (255, 255, 240, 255))
    c.ellipse(0.5, 0.58, 0.05, 0.05, trunk)
    return glow_under(c.done(size, size), (255, 220, 150), size / 14, 0.6)


def sym_quest(size, color=None):
    """A torn map with a dotted route to a red mark."""
    c = Canvas(size, size)
    c.poly([(0.12, 0.20), (0.88, 0.14), (0.84, 0.86), (0.16, 0.84)], (205, 185, 140, 255))
    c.poly([(0.12, 0.20), (0.88, 0.14), (0.87, 0.20), (0.13, 0.26)], (170, 150, 105, 255))
    route = [(0.24, 0.74), (0.34, 0.60), (0.30, 0.46), (0.46, 0.40), (0.58, 0.52), (0.70, 0.36)]
    for i in range(len(route) - 1):
        (x0, y0), (x1, y1) = route[i], route[i + 1]
        for t in (0.15, 0.5, 0.85):
            c.ellipse(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, 0.014, 0.014, (90, 60, 40, 255))
    c.line([(0.64, 0.30), (0.76, 0.42)], (200, 30, 30, 255), 0.04)
    c.line([(0.76, 0.30), (0.64, 0.42)], (200, 30, 30, 255), 0.04)
    c.ellipse(0.26, 0.76, 0.035, 0.035, (120, 255, 170, 255))
    return glow_under(c.done(size, size), (255, 220, 150), size / 16, 0.5)


def sym_carcosa(size, color=None):
    """Lost Carcosa: black towers on the shore of Lake Hali under twin suns."""
    c = Canvas(size, size)
    c.ellipse(0.5, 0.46, 0.44, 0.40, (150, 105, 30, 255))
    c.ellipse(0.5, 0.46, 0.40, 0.36, (200, 150, 50, 255))
    c.ellipse(0.36, 0.30, 0.10, 0.10, (255, 225, 120, 255))
    c.ellipse(0.62, 0.24, 0.06, 0.06, (255, 240, 170, 255))
    for x, y in ((0.24, 0.20), (0.76, 0.40), (0.70, 0.16)):
        c.ellipse(x, y, 0.016, 0.016, (25, 12, 20, 255))
    for x, top, w in ((0.20, 0.56, 0.06), (0.31, 0.40, 0.05), (0.42, 0.50, 0.045), (0.54, 0.32, 0.06),
                      (0.66, 0.46, 0.045), (0.78, 0.54, 0.055)):
        c.poly([(x - w, 0.80), (x + w, 0.80), (x + w * 0.7, top + 0.06), (x, top), (x - w * 0.7, top + 0.06)],
               (28, 18, 26, 255))
    c.poly([(0.08, 0.78), (0.92, 0.78), (0.86, 0.90), (0.14, 0.90)], (70, 55, 30, 255))
    for y in (0.82, 0.86):
        c.line([(0.24, y), (0.76, y)], (210, 170, 70, 200), 0.008)
    return glow_under(c.done(size, size), (255, 210, 90), size / 14, 0.7)


def sym_temple(size, color=None):
    c = Canvas(size, size)
    stone = [(70, 66, 74, 255), (88, 84, 92, 255), (106, 102, 110, 255)]
    for i, (w, y0, y1) in enumerate([(0.40, 0.70, 0.92), (0.30, 0.50, 0.70), (0.20, 0.32, 0.50)]):
        c.poly([(0.5 - w, y1), (0.5 + w, y1), (0.5 + w * 0.92, y0), (0.5 - w * 0.92, y0)], stone[i])
    c.poly([(0.46, 0.92), (0.54, 0.92), (0.54, 0.78), (0.46, 0.78)], (150, 255, 180, 255))
    c.poly([(0.47, 0.50), (0.53, 0.50), (0.53, 0.40), (0.47, 0.40)], (150, 255, 180, 255))
    c.ellipse(0.5, 0.17, 0.09, 0.09, None, (230, 190, 90, 255), 0.025)
    c.ellipse(0.5, 0.17, 0.03, 0.03, (150, 255, 190, 255))
    return glow_under(c.done(size, size), (130, 255, 170), size / 14, 0.8)


SYMBOLS = {
    "cthulhu": sym_cthulhu,
    "hastur": sym_hastur,
    "azathoth": sym_azathoth,
    "tome": sym_tome,
    "altar": sym_altar,
    "sacrifice": sym_sacrifice,
    "deepen": sym_deepen,
    "anoint": sym_chalice,
    "crown": sym_crown,
    "servitors": sym_servitors,
    "curse": sym_curse,
    "rites": sym_elder_sign,
    "incarnate": sym_incarnate,
    "commune": sym_commune,
    "preach": sym_preach,
    "tithe": sym_tithe,
    "council": sym_council,
    "temple": sym_temple,
    "vessel": sym_vessel,
    "fever": sym_fever,
    "march": sym_march,
    "dread": sym_dread,
    "path": sym_path,
    "quest": sym_quest,
    "carcosa": sym_carcosa,
}

# Relics won by the Prophet's quests: picture name -> symbol.
RELICS = {
    "relic_necronomicon": "tome",
    "relic_elder_archive": "rites",
    "relic_rlyeh": "cthulhu",
    "relic_full_play": "hastur",
    "relic_engine": "azathoth",
}

# The Prophet's Path: one icon per branch (symbol, border colour).
PATH_ICONS = {
    "path_lore": ("tome", (120, 170, 255)),
    "path_zeal": ("preach", (230, 90, 70)),
    "path_will": ("rites", (130, 255, 170)),
}

# Decision icons beyond the gods' own (GFX_decision_eldritch_<name>).
DECISION_ICONS = ["tome", "altar", "sacrifice", "deepen", "anoint", "crown", "servitors", "curse", "incarnate",
                  "commune", "preach", "tithe", "council", "temple", "vessel", "carcosa"]

# National spirits that belong to no single god (the Prophet's rites, the
# god incarnate): picture name -> (symbol, inner, outer, border colour).
EXTRA_SPIRITS = {
    "fever": ("fever", (90, 40, 20), (28, 10, 6), (230, 120, 50)),
    "council": ("council", (45, 30, 70), (14, 8, 22), (165, 150, 215)),
    "march": ("march", (80, 22, 24), (24, 6, 8), (200, 60, 50)),
    "temple": ("temple", (40, 50, 45), (10, 14, 12), (235, 195, 90)),
    "god_walks": ("incarnate", (60, 50, 30), (18, 14, 8), (235, 195, 90)),
    "dread": ("dread", (70, 15, 20), (22, 4, 6), (200, 40, 40)),
    "mantle": ("preach", (50, 34, 70), (16, 10, 24), (235, 195, 90)),
    "carcosa_road": ("hastur", (70, 52, 18), (22, 16, 6), (200, 160, 60)),
    "yellow_throne": ("carcosa", (80, 60, 20), (24, 18, 6), (255, 215, 90)),
}


# ---------------------------------------------------------------------------
# Icon compositions
# ---------------------------------------------------------------------------

def framed(size, bg_inner, bg_outer, symbol, border, border_width=2, sym_scale=0.82, aura=None):
    w, h = size
    img = radial_bg(size, bg_inner, bg_outer, center=(0.5, 0.45))
    s = int(min(w, h) * sym_scale)
    if aura:
        halo = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        ImageDraw.Draw(halo).ellipse([s * 0.1, s * 0.1, s * 0.9, s * 0.9], fill=aura + (170,))
        halo = halo.filter(ImageFilter.GaussianBlur(s / 7))
        img = paste_center(img, halo, 0.5, 0.5)
    img = paste_center(img, symbol(s), 0.5, 0.5)
    img = vignette(img, 0.45)
    d = ImageDraw.Draw(img)
    for i in range(border_width):
        d.rectangle([i, i, w - 1 - i, h - 1 - i], outline=border + (255,))
    d.rectangle([border_width, border_width, w - 1 - border_width, h - 1 - border_width],
                outline=(0, 0, 0, 160))
    return img


TIER_BORDERS = {1: (120, 105, 80), 2: (165, 150, 215), 3: (235, 195, 90)}


def make_ideas():
    for god in GODS:
        pal = PALETTE[god]
        inner = tuple(min(255, int(v * 2.2 + 10)) for v in pal["bg"])
        for tier in (1, 2, 3):
            aura = pal["glow"] if tier == 3 else None
            img = framed(IDEA_SIZE, inner, pal["bg"], SYMBOLS[god], TIER_BORDERS[tier],
                         border_width=tier, aura=aura)
            save_dds(img, f"gfx/interface/ideas/eldritch_{god}_{tier}.dds")
        img = framed(IDEA_SIZE, inner, pal["bg"], SYMBOLS[god], pal["glow"], border_width=2, aura=pal["glow"])
        save_dds(img, f"gfx/interface/ideas/eldritch_{god}_blessing.dds")

    def dreams(s):
        return tint(sym_cthulhu(s), (150, 60, 160), 0.45)

    def yellow(s):
        return sym_hastur(s)

    save_dds(framed(IDEA_SIZE, (70, 15, 30), (20, 4, 10), dreams, (200, 40, 40)),
             "gfx/interface/ideas/eldritch_curse_dreams.dds")
    save_dds(framed(IDEA_SIZE, (80, 20, 10), (25, 5, 5), yellow, (200, 40, 40)),
             "gfx/interface/ideas/eldritch_curse_yellow.dds")
    for name, (symbol, inner, outer, border) in EXTRA_SPIRITS.items():
        save_dds(framed(IDEA_SIZE, inner, outer, SYMBOLS[symbol], border), f"gfx/interface/ideas/eldritch_{name}.dds")
    for name, symbol in RELICS.items():
        pal = PALETTE.get(symbol, {"bg": (22, 14, 30), "glow": (255, 210, 120)})
        inner = tuple(min(255, int(v * 2.2 + 10)) for v in pal["bg"])
        save_dds(framed(IDEA_SIZE, inner, pal["bg"], SYMBOLS[symbol], (235, 195, 90), border_width=2,
                        aura=(255, 210, 120)), f"gfx/interface/ideas/eldritch_{name}.dds")


def make_decisions():
    for name in DECISION_ICONS + GODS:
        pal = PALETTE.get(name, {"bg": (16, 14, 24)})
        inner = tuple(min(255, int(v * 2.4 + 12)) for v in pal["bg"])
        img = framed(DECISION_SIZE, inner, pal["bg"], SYMBOLS[name], (150, 130, 95), border_width=1,
                     sym_scale=0.86)
        save_dds(img, f"gfx/interface/decisions/eldritch_{name}.dds")
    img = framed(DECISION_SIZE, (40, 30, 60), (12, 8, 20), SYMBOLS["rites"], (190, 160, 90), border_width=1,
                 sym_scale=0.9)
    save_dds(img, "gfx/interface/decisions/eldritch_category_rites.dds")
    for name, (symbol, border) in PATH_ICONS.items():
        img = framed(DECISION_SIZE, (40, 30, 60), (12, 8, 20), SYMBOLS[symbol], border, border_width=1,
                     sym_scale=0.86)
        save_dds(img, f"gfx/interface/decisions/eldritch_{name}.dds")
    img = framed(DECISION_SIZE, (40, 30, 60), (12, 8, 20), SYMBOLS["path"], (190, 160, 90), border_width=1,
                 sym_scale=0.9)
    save_dds(img, "gfx/interface/decisions/eldritch_category_path.dds")
    img = framed(DECISION_SIZE, (40, 30, 60), (12, 8, 20), SYMBOLS["quest"], (190, 160, 90), border_width=1,
                 sym_scale=0.9)
    save_dds(img, "gfx/interface/decisions/eldritch_category_quests.dds")


# ---------------------------------------------------------------------------
# Event pictures
# ---------------------------------------------------------------------------

def silhouette_city(img, color, base_y, seed, towers=False):
    rng = random.Random(seed)
    d = ImageDraw.Draw(img)
    w, h = img.size
    x = 0
    while x < w:
        bw = rng.randint(8, 22)
        bh = rng.randint(10, 40) + (rng.randint(10, 40) if towers and rng.random() < 0.35 else 0)
        d.rectangle([x, base_y - bh, x + bw, h], fill=color)
        if towers and rng.random() < 0.5:
            d.polygon([(x, base_y - bh), (x + bw / 2, base_y - bh - rng.randint(8, 25)), (x + bw, base_y - bh)],
                      fill=color)
        x += bw + rng.randint(0, 4)


def sea(img, top_y, color, line_color, seed):
    d = ImageDraw.Draw(img)
    w, h = img.size
    d.rectangle([0, top_y, w, h], fill=color)
    rng = random.Random(seed)
    for _ in range(60):
        y = rng.uniform(top_y + 3, h)
        x = rng.uniform(0, w)
        ln = rng.uniform(6, 22)
        d.line([(x, y), (x + ln, y)], fill=line_color, width=1)


def finish(img, seed):
    return grain(vignette(img, 0.65), 6, seed)


def make_report_events():
    w, h = REPORT_SIZE

    # Cthulhu rising from the sea
    img = vertical_bg(REPORT_SIZE, (5, 10, 20), (20, 60, 55))
    img = stars(img, 70, 0.5, 1)
    img = paste_center(img, sym_cthulhu(150), 0.5, 0.50)
    sea(img, int(h * 0.68), (8, 30, 32, 255), (40, 110, 100, 255), 2)
    save_dds(finish(img, 1), "gfx/event_pictures/eldritch_cthulhu.dds")

    # Hastur: Carcosa beneath twin suns
    img = vertical_bg(REPORT_SIZE, (20, 12, 5), (120, 80, 20))
    img = stars(img, 40, 0.4, 5)
    d = ImageDraw.Draw(img)
    for sx in (0.32, 0.68):
        sun = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        ImageDraw.Draw(sun).ellipse([4, 4, 36, 36], fill=(255, 210, 110, 255))
        img = paste_center(img, glow_under(sun, (255, 180, 60), 6), sx, 0.58)
    img = paste_center(img, sym_hastur(70), 0.5, 0.22)
    silhouette_city(img, (25, 15, 5, 255), int(h * 0.90), 6, towers=True)
    sea(img, int(h * 0.86), (60, 40, 10, 255), (140, 100, 30, 255), 7)
    save_dds(finish(img, 3), "gfx/event_pictures/eldritch_hastur.dds")

    # Azathoth: the vortex above the crater
    img = vertical_bg(REPORT_SIZE, (10, 2, 12), (60, 10, 50))
    img = stars(img, 90, 0.9, 12)
    img = paste_center(img, sym_azathoth(160), 0.5, 0.42)
    crater = Image.new("RGBA", (170, 40), (0, 0, 0, 0))
    ImageDraw.Draw(crater).ellipse([10, 10, 160, 40], fill=(255, 140, 60, 220))
    img = paste_center(img, crater.filter(ImageFilter.GaussianBlur(6)), 0.5, 0.93)
    d = ImageDraw.Draw(img)
    d.polygon([(0, h), (0, h * 0.84), (w * 0.25, h * 0.88), (w * 0.75, h * 0.88), (w, h * 0.84), (w, h)],
              fill=(20, 8, 15, 255))
    save_dds(finish(img, 6), "gfx/event_pictures/eldritch_azathoth.dds")

    # The tome on a candle-lit desk
    img = radial_bg(REPORT_SIZE, (90, 60, 30), (10, 6, 4), center=(0.5, 0.55), scale=0.9)
    d = ImageDraw.Draw(img)
    d.rectangle([0, h * 0.72, w, h], fill=(35, 20, 10, 255))
    img = paste_center(img, sym_tome(120), 0.5, 0.55)
    for cx in (0.15, 0.85):
        candle = Image.new("RGBA", (30, 70), (0, 0, 0, 0))
        cd = ImageDraw.Draw(candle)
        cd.rectangle([11, 25, 19, 70], fill=(220, 210, 180, 255))
        cd.ellipse([10, 5, 20, 25], fill=(255, 200, 90, 255))
        img = paste_center(img, glow_under(candle, (255, 170, 60), 8), cx, 0.62)
    save_dds(finish(img, 7), "gfx/event_pictures/eldritch_tome.dds")

    # Omen: eclipse with a watching eye
    img = vertical_bg(REPORT_SIZE, (3, 3, 10), (30, 15, 40))
    img = stars(img, 150, 1.0, 13)
    corona = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
    ImageDraw.Draw(corona).ellipse([15, 15, 105, 105], fill=(200, 255, 220, 255))
    corona = corona.filter(ImageFilter.GaussianBlur(9))
    img = paste_center(img, corona, 0.5, 0.42)
    disc = Image.new("RGBA", (84, 84), (0, 0, 0, 0))
    ImageDraw.Draw(disc).ellipse([2, 2, 82, 82], fill=(4, 4, 8, 255))
    img = paste_center(img, disc, 0.5, 0.42)
    img = paste_center(img, sym_eye(46, (120, 255, 170)), 0.5, 0.42)
    silhouette_city(img, (6, 6, 10, 255), int(h * 0.92), 14)
    save_dds(finish(img, 8), "gfx/event_pictures/eldritch_omen.dds")


def make_news_event():
    w, h = NEWS_SIZE
    img = vertical_bg(NEWS_SIZE, (15, 15, 20), (150, 150, 155))
    img = stars(img, 120, 0.45, 20)
    beams = Image.new("RGBA", NEWS_SIZE, (0, 0, 0, 0))
    bd = ImageDraw.Draw(beams)
    for bx, tx in [(0.12, 0.30), (0.55, 0.40), (0.86, 0.70)]:
        bd.polygon([(bx * w - 2, h * 0.8), (tx * w - 14, 0), (tx * w + 14, 0), (bx * w + 2, h * 0.8)],
                   fill=(230, 230, 210, 70))
    img = Image.alpha_composite(img, beams.filter(ImageFilter.GaussianBlur(3)))
    c = Canvas(w, h)
    for i, (x, height, sway) in enumerate([(0.20, 0.95, 0.04), (0.33, 0.75, -0.03), (0.62, 1.05, 0.05),
                                           (0.75, 0.80, -0.04), (0.90, 0.70, 0.03)]):
        pts = []
        for k in range(120):
            t = k / 119
            pts.append((x + sway * math.sin(2.4 * math.pi * t + i), 1.05 - height * t))
        c.stroke(pts, (22, 22, 26, 255), 0.11, 0.012)
    img = Image.alpha_composite(img, c.done(w, h))
    silhouette_city(img, (12, 12, 16, 255), int(h * 0.82), 21, towers=True)
    img = to_sepia(finish(img, 9))
    save_dds(img, "gfx/event_pictures/eldritch_news_stars.dds")


def make_thumbnail():
    size = (512, 512)
    img = vertical_bg(size, (4, 8, 18), (16, 50, 48))
    img = stars(img, 300, 0.7, 30)
    img = paste_center(img, sym_cthulhu(360), 0.5, 0.48)
    sea(img, 360, (6, 26, 28, 255), (40, 110, 100, 255), 31)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", 46)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", 26)
    except OSError:
        font = small = ImageFont.load_default()
    for text, f, y, col in [("ELDRITCH PACTS", font, 398, (230, 220, 170)),
                            ("Call of the Old Ones", small, 458, (150, 230, 190))]:
        tw = d.textlength(text, font=f)
        d.text(((size[0] - tw) / 2 + 2, y + 2), text, font=f, fill=(0, 0, 0, 255))
        d.text(((size[0] - tw) / 2, y), text, font=f, fill=col + (255,))
    vignette(img, 0.5).convert("RGB").save(os.path.join(ROOT, "thumbnail.png"))


# ---------------------------------------------------------------------------
# Avatar portraits (156x210, used by portrait_path on the avatar commanders)
# ---------------------------------------------------------------------------

def portrait_frame(top, bottom, glow_center=(0.5, 0.35)):
    return radial_bg(PORTRAIT_SIZE, top, bottom, center=glow_center, scale=0.8)


def finish_portrait(bg, figure, rim, seed):
    figure = glow_under(figure, rim, 5, 0.9)
    img = Image.alpha_composite(bg, figure)
    # soft key light from the upper left
    w, h = img.size
    yy, xx = np.mgrid[0:h, 0:w]
    light = 1.0 + 0.18 * np.clip(1 - np.sqrt(((xx - w * 0.3) / w) ** 2 + ((yy - h * 0.25) / h) ** 2) * 2, 0, 1)
    arr = np.array(img).astype(float)
    arr[..., :3] *= light[..., None]
    img = Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")
    return grain(vignette(img, 0.55), 5, seed)


def shoulders(c, color, y=1.02, rx=0.62, ry=0.34):
    c.ellipse(0.5, y, rx, ry, color)


def fish_head(c, skin, belly, eye_col, crest_col):
    # crest fin
    c.poly([(0.34, 0.22), (0.40, 0.08), (0.45, 0.18), (0.50, 0.04), (0.55, 0.18), (0.60, 0.08), (0.66, 0.22)],
           crest_col + (255,))
    c.ellipse(0.5, 0.38, 0.30, 0.38, skin + (255,))
    c.ellipse(0.5, 0.56, 0.17, 0.10, belly + (255,))
    for side in (-1, 1):
        ex = 0.5 + side * 0.17
        c.ellipse(ex, 0.33, 0.085, 0.085, (235, 230, 190, 255))
        c.ellipse(ex, 0.33, 0.06, 0.06, eye_col + (255,))
        c.ellipse(ex, 0.33, 0.028, 0.028, (5, 5, 5, 255))
        for k in range(3):
            gx = 0.5 + side * (0.24 + k * 0.025)
            c.line([(gx, 0.42 + k * 0.03), (gx + side * 0.02, 0.47 + k * 0.03)], (30, 50, 40, 255), 0.012)
    # wide, down-turned maw with needle teeth
    mouth = [(0.33, 0.56), (0.40, 0.51), (0.60, 0.51), (0.67, 0.56), (0.60, 0.585), (0.40, 0.585)]
    c.poly(mouth, (15, 20, 18, 255))
    for k in range(7):
        x = 0.39 + k * 0.037
        c.poly([(x - 0.012, 0.515), (x + 0.012, 0.515), (x, 0.545)], (225, 220, 200, 255))


def scales(c, x0, x1, y0, y1, color, step=0.05):
    y = y0
    row = 0
    while y < y1:
        x = x0 + (step / 2 if row % 2 else 0)
        while x < x1:
            c.d.arc([c.p(x - step / 2, y)[0], c.p(x, y - step / 3)[1], c.p(x + step / 2, y)[0], c.p(x, y + step / 3)[1]],
                    0, 180, fill=color, width=max(1, int(c.s(0.008))))
            x += step
        y += step * 0.6
        row += 1


def portrait_dagon():
    bg = portrait_frame((30, 80, 75), (4, 14, 16))
    c = Canvas(*PORTRAIT_SIZE)
    shoulders(c, (20, 55, 50, 255))
    scales(c, 0.1, 0.9, 0.80, 1.0, (60, 120, 100, 255))
    c.poly([(0.43, 0.62), (0.57, 0.62), (0.60, 0.80), (0.40, 0.80)], (60, 95, 80, 255))
    fish_head(c, (80, 125, 105), (150, 175, 140), (255, 210, 60), (40, 90, 80))
    # coral crown
    for x, h in [(0.36, 0.10), (0.44, 0.14), (0.50, 0.16), (0.56, 0.14), (0.64, 0.10)]:
        c.line([(x, 0.10), (x, 0.10 - h * 0.5)], (220, 90, 70, 255), 0.022)
        c.line([(x, 0.07), (x + 0.03, 0.03)], (220, 90, 70, 255), 0.015)
    return finish_portrait(bg, c.done(*PORTRAIT_SIZE), (120, 255, 200), 41)


def portrait_hydra():
    bg = portrait_frame((50, 60, 95), (8, 8, 22))
    c = Canvas(*PORTRAIT_SIZE)
    shoulders(c, (35, 40, 75, 255))
    for i, x in enumerate([0.22, 0.28, 0.72, 0.78]):
        tentacle(c, x, 0.20, 0.62, 0.05 * (1 if i % 2 else -1), i, 0.035, 0.012, (70, 110, 120, 255))
    c.poly([(0.43, 0.62), (0.57, 0.62), (0.60, 0.80), (0.40, 0.80)], (70, 100, 110, 255))
    fish_head(c, (85, 120, 130), (160, 180, 185), (180, 120, 255), (60, 70, 120))
    for k in range(9):
        a = math.radians(200 + k * 17.5)
        c.ellipse(0.5 + 0.20 * math.cos(a), 0.80 - 0.10 * math.sin(a), 0.022, 0.022, (240, 235, 225, 255))
    return finish_portrait(bg, c.done(*PORTRAIT_SIZE), (170, 140, 255), 42)


def portrait_piper():
    bg = portrait_frame((90, 20, 80), (8, 2, 12))
    bg = stars(bg, 50, 1.0, 47)
    c = Canvas(*PORTRAIT_SIZE)
    rng = random.Random(4)
    for _ in range(14):
        x, y = rng.uniform(0.25, 0.75), rng.uniform(0.3, 1.0)
        r = rng.uniform(0.12, 0.22)
        shade = rng.randint(30, 70)
        c.ellipse(x, y, r, r * 1.1, (shade + 30, shade // 3, shade + 40, 255))
    c.ellipse(0.5, 0.36, 0.20, 0.22, (90, 35, 100, 255))
    for x, y, r in [(0.44, 0.32, 0.03), (0.57, 0.30, 0.025), (0.5, 0.42, 0.02), (0.35, 0.55, 0.02),
                    (0.66, 0.62, 0.025), (0.45, 0.74, 0.018)]:
        c.ellipse(x, y, r, r, (255, 230, 120, 255))
        c.ellipse(x, y, r * 0.4, r * 0.4, (10, 0, 10, 255))
    c.line([(0.30, 0.50), (0.76, 0.46)], (220, 180, 80, 255), 0.022)
    for k in range(4):
        c.ellipse(0.40 + k * 0.08, 0.49 - k * 0.007, 0.008, 0.008, (60, 30, 10, 255))
    img = c.done(*PORTRAIT_SIZE)
    img = paste_center(img, sym_azathoth(70), 0.80, 0.18)
    return finish_portrait(bg, img, (255, 120, 220), 48)


PORTRAITS = {
    "eldritch_avatar_dagon": portrait_dagon,
    "eldritch_avatar_hydra": portrait_hydra,
    "eldritch_avatar_pallid_mask": art_portraits.king_in_yellow,  # painted; see tools/art_portraits.py
    "eldritch_avatar_piper": portrait_piper,
}


def make_portraits():
    for name, fn in PORTRAITS.items():
        save_dds(fn(), f"gfx/leaders/eldritch/{name}.dds")


# ---------------------------------------------------------------------------
# Battalion icons for the division designer (GFX_unit_<name>_icon_medium)
# ---------------------------------------------------------------------------

UNIT_ICONS = list(art_units.ICONS)


def _render_unit_icon(unit):
    return unit, art_units.textures(unit)


def make_unit_icons():
    """Each battalion as a small lit scene for the division designer, and its
    figures' silhouette for the counter on the map, each with its NATO symbol
    as a second frame (art_units, GAME TEXTURES). Rendered in parallel."""
    with ProcessPoolExecutor() as pool:
        for unit, (designer, small) in pool.map(_render_unit_icon, UNIT_ICONS):
            save_dds(designer, f"gfx/interface/counters/divisions_large/{unit}.dds")
            save_dds(small, f"gfx/interface/counters/divisions_small/{unit}.dds")


# ---------------------------------------------------------------------------
# Unit leader trait icons (GFX_trait_<trait>)
# ---------------------------------------------------------------------------

def trait_icon(symbol, rim):
    w, h = TRAIT_SIZE
    img = Image.new("RGBA", TRAIT_SIZE, (0, 0, 0, 0))
    disc = Canvas(w, h)
    disc.ellipse(0.5, 0.5, 0.48, 0.48, rim + (255,))
    disc.ellipse(0.5, 0.5, 0.42, 0.42, (18, 14, 24, 255))
    img = Image.alpha_composite(img, disc.done(w, h))
    return paste_center(img, symbol(int(w * 0.72)), 0.5, 0.5)


def make_trait_icons():
    for god in GODS:
        for kind, rim in (("general", (160, 140, 100)), ("admiral", (110, 150, 190))):
            save_dds(trait_icon(SYMBOLS[god], rim), f"gfx/interface/traits/eldritch_{god}_{kind}.dds")
    save_dds(trait_icon(sym_elder_sign, (235, 195, 90)), "gfx/interface/traits/eldritch_avatar_land.dds")
    save_dds(trait_icon(sym_elder_sign, (110, 190, 210)), "gfx/interface/traits/eldritch_avatar_navy.dds")



# ---------------------------------------------------------------------------
# The Eldritch doctrine folder (common/doctrines): its tab, the gods' grand
# doctrine and sub-doctrine icons, and the backgrounds of its three tracks
# ---------------------------------------------------------------------------

DOCTRINE_ICON_SIZE = (54, 58)      # fits the doctrine list row and the grand doctrine header
DOCTRINE_TAB_SIZE = (512, 61)      # two 256 x 61 frames: normal, selected (like the land tab)
TRACK_BG_SIZE = (400, 700)         # behind a track's column; the UI clips what does not fit
DOCTRINE_TRACKS = {"servitors": "servitors", "faithful": "preach", "rites": "rites"}


def doctrine_tab():
    """The Eldritch folder tab: a dark riveted plate with the Elder Sign at its
    left (the folder name is drawn by the game to its right)."""
    fw, fh = DOCTRINE_TAB_SIZE[0] // 2, DOCTRINE_TAB_SIZE[1]
    tab = Image.new("RGBA", DOCTRINE_TAB_SIZE, (0, 0, 0, 0))
    for frame, (top, bottom, rim, glow) in enumerate((((34, 36, 34), (14, 15, 15), (92, 96, 88), 0.0),
                                                       ((44, 50, 42), (18, 22, 18), (150, 170, 120), 0.9))):
        plate = grain(vertical_bg((fw - 8, fh - 8), top, bottom), 6, frame)
        img = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
        img.paste(plate, (4, 4))
        d = ImageDraw.Draw(img)
        d.rectangle([3, 3, fw - 4, fh - 4], outline=rim + (255,))
        d.rectangle([1, 1, fw - 2, fh - 2], outline=(8, 8, 8, 255))
        d.line([(5, 5), (fw - 6, 5)], fill=tuple(min(255, c + 40) for c in rim) + (160,))
        for x, y in ((9, 9), (fw - 10, 9), (9, fh - 10), (fw - 10, fh - 10)):
            d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(120, 118, 110, 255), outline=(20, 20, 20, 255))
        sign = sym_elder_sign(40)
        if glow:
            sign = glow_under(sign, (150, 255, 190), 5, glow)
        img = paste_center(img, sign, 34 / fw, 0.5)
        tab.alpha_composite(img, (frame * fw, 0))
    return tab


def doctrine_icon(god, track=None):
    """A grand doctrine icon (the god's sigil, gold rim) or a sub-doctrine icon
    (the track's symbol in the god's colours, the god's sigil in a corner)."""
    pal = PALETTE[god]
    inner = tuple(min(255, int(v * 2.2 + 10)) for v in pal["bg"])
    if track is None:
        return framed(DOCTRINE_ICON_SIZE, inner, pal["bg"], SYMBOLS[god], (235, 195, 90), border_width=2,
                      aura=pal["glow"])

    def symbol(size):
        return tint(SYMBOLS[DOCTRINE_TRACKS[track]](size), pal["glow"], 0.3)
    rim = tuple(min(255, int(v * 0.6 + 70)) for v in pal["main"])
    img = framed(DOCTRINE_ICON_SIZE, inner, pal["bg"], symbol, rim, border_width=1, sym_scale=0.8)
    badge = Image.new("RGBA", (22, 22), (0, 0, 0, 0))
    ImageDraw.Draw(badge).ellipse([0, 0, 21, 21], fill=pal["bg"] + (235,), outline=rim + (255,))
    badge = paste_center(badge, SYMBOLS[god](18), 0.5, 0.5)
    return paste_center(img, badge, 0.76, 0.79)


def track_background(track, seed):
    """A dark, stained backdrop with the track's symbol faded into it."""
    w, h = TRACK_BG_SIZE
    rng = np.random.default_rng(seed)
    base = np.zeros((h, w))
    for scale, amp in ((8, 0.5), (24, 0.3), (80, 0.2)):
        small = rng.random((h // scale + 2, w // scale + 2))
        base += amp * np.asarray(Image.fromarray((small * 255).astype(np.uint8)).resize(
            (w, h), Image.BICUBIC, box=(0, 0, w / scale, h / scale))) / 255
    t = np.linspace(0, 1, h)[:, None]
    rgb = np.stack([22 + 16 * base - 8 * t, 25 + 18 * base - 8 * t, 23 + 14 * base - 9 * t], axis=2)
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).convert("RGBA")
    sym = SYMBOLS[DOCTRINE_TRACKS[track]](360)
    a = np.array(sym).astype(float)
    grey = a[..., :3].mean(axis=2, keepdims=True)
    a[..., :3] = grey * 0.7 + np.array([110, 135, 115]) * 0.3
    a[..., 3] *= 0.6
    img = paste_center(img, Image.fromarray(a.astype(np.uint8), "RGBA"), 0.5, 0.45)
    return grain(vignette(img, 0.6), 5, seed)


def make_doctrine_art():
    save_dds(doctrine_tab(), "gfx/interface/doctrines/eldritch_doctrine_tab.dds")
    for god in GODS:
        save_dds(doctrine_icon(god), f"gfx/interface/doctrines/eldritch_doctrine_{god}.dds")
        for track in DOCTRINE_TRACKS:
            save_dds(doctrine_icon(god, track), f"gfx/interface/doctrines/eldritch_doctrine_{god}_{track}.dds")
    for k, track in enumerate(DOCTRINE_TRACKS):
        path = os.path.join(ROOT, f"gfx/interface/doctrines/eldritch_track_{track}_bg.dds")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # large and opaque: DXT1-compressed rather than raw, to keep the mod small
        track_background(track, 900 + k).convert("RGB").save(path, pixel_format="DXT1")


# ---------------------------------------------------------------------------
# Flags of the formable nation (gfx/flags/<cosmetic tag>[_ideology].tga)
# ---------------------------------------------------------------------------

FLAG_SIZES = {"": (82, 52), "medium/": (41, 26), "small/": (10, 7)}


# The King in Yellow between two sigils, gold on a black field between gold bands.
FLAG_SOURCE = os.path.join(ROOT, "tools", "art_sources", "carcosa_flag.png")
# The part of the source that becomes the flag: the full width, and the rows that
# make its black field (source rows 170-1160) exactly 40 of the flag's 52 rows, so
# the gold bands come out as whole pixels (6 px, 3 px at medium) instead of a
# blurred edge row.
FLAG_BOX = (0, 21.5, 2000, 1308.5)


def make_flags():
    flag = Image.open(FLAG_SOURCE).convert("RGBA")
    for ideology in ("", "_fascism", "_communism", "_democratic", "_neutrality"):
        for folder, size in FLAG_SIZES.items():
            path = os.path.join(ROOT, "gfx", "flags", folder, f"ELDRITCH_CARCOSA{ideology}.tga")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            flag.resize(size, Image.LANCZOS, box=FLAG_BOX).save(path)


# ---------------------------------------------------------------------------
# Sprite definitions (interface/eldritch.gfx)
# ---------------------------------------------------------------------------

def write_gfx():
    lines = [
        "#####################################################################",
        "# Eldritch Pacts - sprites",
        "# Generated by tools/generate_art.py - edit the generator, not this file.",
        "#####################################################################",
        "",
        "spriteTypes = {",
    ]

    def section(title):
        lines.extend(["", f"\t### {title} ###"])

    def sprite(name, tex, frames=1, transparent=False):
        lines.extend(["\tspriteType = {", f'\t\tname = "{name}"', f'\t\ttexturefile = "{tex}"'])
        if frames > 1:
            lines.append(f"\t\tnoOfFrames = {frames}")
        if transparent:
            lines.append("\t\talwaystransparent = yes")
        lines.append("\t}")

    section("National spirits")
    for god in GODS:
        for suffix in ("1", "2", "3", "blessing"):
            sprite(f"GFX_idea_eldritch_{god}_{suffix}", f"gfx/interface/ideas/eldritch_{god}_{suffix}.dds")
    for curse in ("dreams", "yellow"):
        sprite(f"GFX_idea_eldritch_curse_{curse}", f"gfx/interface/ideas/eldritch_curse_{curse}.dds")
    for name in EXTRA_SPIRITS:
        sprite(f"GFX_idea_eldritch_{name}", f"gfx/interface/ideas/eldritch_{name}.dds")
    for name in RELICS:
        sprite(f"GFX_idea_eldritch_{name}", f"gfx/interface/ideas/eldritch_{name}.dds")

    section("Decisions")
    for name in DECISION_ICONS + GODS:
        sprite(f"GFX_decision_eldritch_{name}", f"gfx/interface/decisions/eldritch_{name}.dds")

    section("Decision category")
    sprite("GFX_decision_category_eldritch_rites", "gfx/interface/decisions/eldritch_category_rites.dds")
    sprite("GFX_decision_eldritch_rites", "gfx/interface/decisions/eldritch_category_rites.dds")
    sprite("GFX_decision_category_eldritch_path", "gfx/interface/decisions/eldritch_category_path.dds")
    sprite("GFX_decision_category_eldritch_quests", "gfx/interface/decisions/eldritch_category_quests.dds")
    sprite("GFX_decision_category_eldritch_carcosa", "gfx/interface/decisions/eldritch_carcosa.dds")
    for name in PATH_ICONS:
        sprite(f"GFX_decision_eldritch_{name}", f"gfx/interface/decisions/eldritch_{name}.dds")

    section("Event pictures")
    for name in ["tome", "omen"] + GODS:
        sprite(f"GFX_report_event_eldritch_{name}", f"gfx/event_pictures/eldritch_{name}.dds")
    sprite("GFX_news_event_eldritch_stars", "gfx/event_pictures/eldritch_news_stars.dds")

    section("Battalion icons: the designer (152x42) and the map counter (60x12), each picture + NATO")
    for unit in UNIT_ICONS:
        sprite(f"GFX_unit_{unit}_icon_medium", f"gfx/interface/counters/divisions_large/{unit}.dds", 2)
        sprite(f"GFX_unit_{unit}_icon_medium_white", f"gfx/interface/counters/divisions_small/{unit}.dds", 2)

    section("General and admiral traits")
    for god in GODS:
        for kind in ("general", "admiral"):
            sprite(f"GFX_trait_eldritch_{god}_{kind}", f"gfx/interface/traits/eldritch_{god}_{kind}.dds")
    for kind in ("land", "navy"):
        sprite(f"GFX_trait_eldritch_avatar_{kind}", f"gfx/interface/traits/eldritch_avatar_{kind}.dds")

    section("The Eldritch doctrine folder: tab, grand doctrines, sub-doctrines (per track), track backgrounds")
    sprite("GFX_eldritch_doctrine_tab", "gfx/interface/doctrines/eldritch_doctrine_tab.dds", 2)
    sprite("GFX_eldritch_doctrine_folder_icon", "gfx/interface/doctrines/eldritch_doctrine_tab.dds", 2)
    for god in GODS:
        sprite(f"GFX_eldritch_doctrine_{god}_medium", f"gfx/interface/doctrines/eldritch_doctrine_{god}.dds",
               transparent=True)
        for track in DOCTRINE_TRACKS:
            sprite(f"GFX_eldritch_doctrine_{god}_{track}_medium",
                   f"gfx/interface/doctrines/eldritch_doctrine_{god}_{track}.dds", transparent=True)
    for track in DOCTRINE_TRACKS:
        sprite(f"GFX_eldritch_track_{track}_bg", f"gfx/interface/doctrines/eldritch_track_{track}_bg.dds")

    lines.append("}")
    with open(os.path.join(ROOT, "interface", "eldritch.gfx"), "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    if sys.argv[1:] == ["units"]:
        make_unit_icons()
        print("Battalion icons generated.")
        return
    if sys.argv[1:] == ["doctrines"]:
        make_doctrine_art()
        write_gfx()
        print("Doctrine art generated.")
        return
    make_ideas()
    make_decisions()
    make_report_events()
    make_news_event()
    make_portraits()
    make_unit_icons()
    make_trait_icons()
    make_flags()
    make_doctrine_art()
    make_thumbnail()
    write_gfx()
    print("Art generated.")


if __name__ == "__main__":
    main()
