"""Procedurally drawn scrapbook ephemera: paper, torn edges, tape, paper flowers,
lace, labels, clocks, butterflies, pearls…

Every element comes back as an RGBA image so a page style can rotate, shadow
and layer it with `place`. Nothing here downloads anything — it's all Pillow.
"""
from __future__ import annotations

import math
import random
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

FONT_DIRS = [Path("/System/Library/Fonts/Supplemental"), Path("/System/Library/Fonts")]
FONTS = {
    "display": ["Didot.ttc", "Bodoni 72.ttc", "Georgia.ttf"],
    "serif": ["Georgia.ttf"],
    "italic": ["Georgia Italic.ttf"],
    "bold": ["Georgia Bold.ttf"],
    "script": ["SnellRoundhand.ttc", "Savoye LET.ttc", "Apple Chancery.ttf"],
    "type": ["AmericanTypewriter.ttc", "Courier New.ttf"],
    "news": ["Rockwell.ttc", "Georgia Bold.ttf"],
}
CLEAR = (0, 0, 0, 0)


# ---------------------------------------------------------------- colour

def hex_rgb(h: str) -> tuple:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def mix(a, b, t: float) -> tuple:
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def lighten(c, t: float) -> tuple:
    return mix(c, (255, 255, 255), t)


def darken(c, t: float) -> tuple:
    return mix(c, (0, 0, 0), t)


def luminance(c) -> float:
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def rgba(c, a: int = 255) -> tuple:
    return (*c[:3], a)


# ---------------------------------------------------------------- type

@lru_cache(maxsize=None)
def font(kind: str, size: float) -> ImageFont.FreeTypeFont:
    size = max(8, int(size))
    for name in FONTS.get(kind, []) + FONTS["serif"]:
        for d in FONT_DIRS:
            if (d / name).exists():
                try:
                    return ImageFont.truetype(str(d / name), size)
                except OSError:
                    pass
    return ImageFont.load_default(size)


def fit_font(kind: str, text: str, max_w: float, max_h: float) -> ImageFont.FreeTypeFont:
    size = int(max_h)
    while size > 8:
        f = font(kind, size)
        l, t, r, b = f.getbbox(text)
        if r - l <= max_w and b - t <= max_h:
            return f
        size = int(size * 0.92)
    return font(kind, 8)


def wrap(text: str, fnt, max_w: float) -> list:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if not line or fnt.getlength(trial) <= max_w:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def text_piece(text: str, kind: str, size: float, color, max_w: float | None = None, align: str = "left"):
    """Render (optionally wrapped) text onto a transparent image."""
    f = font(kind, size)
    lines = wrap(text, f, max_w) if max_w else [text]
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * 1.1)
    pad = int(size * 0.4)  # room for script swashes
    w = int(max(f.getlength(l) for l in lines)) + 2 * pad
    im = Image.new("RGBA", (w, lh * len(lines) + pad), CLEAR)
    d = ImageDraw.Draw(im)
    for i, line in enumerate(lines):
        x = pad if align == "left" else (w - f.getlength(line)) / 2
        d.text((x, i * lh + pad // 3), line, font=f, fill=rgba(color))
    return im


# ---------------------------------------------------------------- layering

def composite_at(canvas: Image.Image, im: Image.Image, x: float, y: float) -> None:
    """alpha_composite that tolerates pieces hanging off the canvas edge."""
    x, y = int(round(x)), int(round(y))
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + im.width, canvas.width), min(y + im.height, canvas.height)
    if x1 > x0 and y1 > y0:
        canvas.alpha_composite(im.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


def place(canvas, piece, center, angle: float = 0.0, shadow: float = 0.35, blur: float | None = None):
    """Rotate a piece, drop a soft shadow under it and stick it on the canvas."""
    if angle:
        piece = piece.rotate(angle, resample=Image.BICUBIC, expand=True)
    x, y = center[0] - piece.width / 2, center[1] - piece.height / 2
    if shadow:
        blur = blur or max(3, min(piece.size) / 45)
        pad = int(blur * 3)
        a = Image.new("L", (piece.width + 2 * pad, piece.height + 2 * pad), 0)
        a.paste(piece.getchannel("A"), (pad, pad))
        a = a.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * shadow))
        sh = Image.new("RGBA", a.size, (30, 20, 12, 0))
        sh.putalpha(a)
        lift = blur * 0.7
        composite_at(canvas, sh, x - pad + lift * 0.5, y - pad + lift)
    composite_at(canvas, piece, x, y)


def faded(piece: Image.Image, opacity: float) -> Image.Image:
    piece = piece.copy()
    piece.putalpha(piece.getchannel("A").point(lambda v: int(v * opacity)))
    return piece


# ---------------------------------------------------------------- paper

def paper(size, color, mottle: float = 0.12, grain: float = 0.25) -> Image.Image:
    """Flat colour with blotchy fibre texture and fine grain."""
    w, h = int(size[0]), int(size[1])
    base = Image.new("RGB", (w, h), tuple(color))
    blot = Image.effect_noise((max(2, w // 28), max(2, h // 28)), 70).resize((w, h), Image.BICUBIC)
    shade = Image.new("RGB", (w, h), darken(color, 0.22))
    base = Image.composite(shade, base, blot.point(lambda v: int(max(0, v - 120) * mottle * 2.2)))
    if grain:
        noise = Image.effect_noise((w, h), 22).convert("RGB")
        base = Image.blend(base, ImageChops.overlay(base, noise), grain)
    return base.convert("RGBA")


def _jag(length: float, amp: float, step: int = 5) -> list:
    pts, v = [], random.uniform(0, amp)
    for i in range(0, int(length) + step, step):
        v = min(amp, max(0, v + random.uniform(-amp, amp) * 0.45))
        pts.append((min(i, length), v))
    return pts


def torn_mask(size, amp: float = 12, sides: str = "nesw") -> Image.Image:
    w, h = size

    def edge(side, length):
        return _jag(length, amp) if side in sides else [(0, 0), (length, 0)]

    poly = [(x, y) for x, y in edge("n", w)]
    poly += [(w - y, x) for x, y in edge("e", h)]
    poly += [(w - x, h - y) for x, y in edge("s", w)]
    poly += [(y, h - x) for x, y in edge("w", h)]
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).polygon(poly, fill=255)
    return m.filter(ImageFilter.GaussianBlur(0.7))


def torn(piece: Image.Image, amp: float = 12, sides: str = "nesw", fiber=(248, 245, 238), burn: float = 0):
    """Tear the edges of a piece, showing a pale fibrous rim and optional burnt edge."""
    piece = piece.convert("RGBA")
    outer = torn_mask(piece.size, amp, sides)
    if fiber:
        inner = ImageChops.multiply(outer, torn_mask(piece.size, amp * 2, sides))
        piece = Image.composite(piece, Image.new("RGBA", piece.size, rgba(fiber)), inner)
    if burn:
        edge = ImageChops.subtract(outer, outer.filter(ImageFilter.GaussianBlur(burn)))
        piece = Image.composite(Image.new("RGBA", piece.size, (92, 58, 30, 255)), piece,
                                edge.point(lambda v: min(170, v * 2)))
    piece.putalpha(outer)
    return piece


def script_paper(size, text: str, color, ink, alpha: int = 80, fsize: float | None = None):
    """Paper covered in faint handwriting."""
    w, h = int(size[0]), int(size[1])
    im = paper((w, h), color, mottle=0.18)
    layer = Image.new("RGBA", (w, h), CLEAR)
    d = ImageDraw.Draw(layer)
    f = font("script", fsize or w / 22)
    lh = int(f.size * 1.35)
    lines = wrap((text.strip() + " ") * 80, f, w * 0.94)
    y = -lh * 0.3
    for line in lines:
        if y > h:
            break
        d.text((w * 0.03 + random.uniform(-12, 12), y), line, font=f, fill=rgba(ink, alpha))
        y += lh
    return Image.alpha_composite(im, layer)


def pattern_paper(size, color, motif):
    """Light paper with scattered outlined leaves (botanical patterned paper)."""
    w, h = int(size[0]), int(size[1])
    im = paper((w, h), color, mottle=0.08)
    for _ in range(int(w * h / 70000)):
        lf = faded(leaf(random.uniform(60, 150), motif, outline_only=True), 0.35)
        place(im, lf, (random.uniform(0, w), random.uniform(0, h)), random.uniform(0, 360), shadow=0)
    return im


def mesh(size, color):
    """Grey craft mesh with white paint splatter and a stitched border."""
    w, h = int(size[0]), int(size[1])
    im = paper((w, h), color, mottle=0.1)
    over = Image.new("RGBA", (w, h), CLEAR)
    d = ImageDraw.Draw(over)
    step = max(8, int(min(w, h) / 55))
    line = rgba(lighten(color, 0.4), 190)
    for x in range(0, w, step):
        d.line((x, 0, x, h), fill=line, width=1)
    for y in range(0, h, step):
        d.line((0, y, w, y), fill=line, width=1)
    for _ in range(int(w * h / 9000)):
        r = random.choice((2, 3, 4, 6, 9))
        x, y = random.uniform(0, w), random.uniform(0, h)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, 235))
    m = int(min(w, h) * 0.035)
    stitch = rgba(lighten(color, 0.7), 230)
    for x in range(m, w - m, 22):
        d.line((x, m, x + 12, m), fill=stitch, width=3)
        d.line((x, h - m, x + 12, h - m), fill=stitch, width=3)
    for y in range(m, h - m, 22):
        d.line((m, y, m, y + 12), fill=stitch, width=3)
        d.line((w - m, y, w - m, y + 12), fill=stitch, width=3)
    return Image.alpha_composite(im, over)


def gauze(size, color=(250, 250, 248)):
    """Wispy cheesecloth for shabby-chic layering."""
    w, h = int(size[0]), int(size[1])
    a = Image.effect_noise((max(2, w // 3), max(2, h // 3)), 90).resize((w, h), Image.BICUBIC)
    a = a.point(lambda v: 0 if v < 105 else min(215, (v - 105) * 3))
    d = ImageDraw.Draw(a)
    for _ in range(w // 7):
        x = random.uniform(0, w)
        d.line((x, 0, x + random.uniform(-20, 20), h), fill=200, width=1)
    for _ in range(h // 7):
        y = random.uniform(0, h)
        d.line((0, y, w, y + random.uniform(-20, 20)), fill=200, width=1)
    a = ImageChops.multiply(a, torn_mask((w, h), amp=min(w, h) * 0.18).filter(ImageFilter.GaussianBlur(4)))
    layer = Image.new("RGBA", (w, h), rgba(color, 0))
    layer.putalpha(a)
    return layer


# ---------------------------------------------------------------- photos

def photo_print(img, size, border: float = 0.045, bottom: float | None = None, card=(250, 247, 240)):
    """A photo mounted on a card border (pass `bottom` for a polaroid)."""
    w, h = int(size[0]), int(size[1])
    b = int(min(w, h) * border)
    bb = int(min(w, h) * bottom) if bottom else b
    out = paper((w, h), card, mottle=0.04, grain=0.15)
    out.paste(ImageOps.fit(img, (w - 2 * b, h - b - bb), Image.LANCZOS), (b, b))
    return out


def tape(length, width, color, alpha: int = 165, pattern: str | None = None):
    """Translucent washi tape with zig-zag torn ends."""
    L, W = int(length), int(width)
    t = Image.new("RGBA", (L, W), rgba(color, alpha))
    d = ImageDraw.Draw(t)
    if pattern == "stripes":
        for x in range(-W, L, max(8, W // 2)):
            d.line([(x, W), (x + W, 0)], fill=rgba(lighten(color, 0.45), alpha), width=max(3, W // 8))
    elif pattern == "dots":
        r = max(3, W // 14)
        for row, y in enumerate(range(r * 2, W - r, r * 5)):
            for x in range(r * 2 + (row % 2) * r * 2, L, r * 5):
                d.ellipse((x - r, y - r, x + r, y + r), fill=rgba(lighten(color, 0.5), alpha))
    teeth, z = max(5, W // 9), max(4, W // 14)
    left = [(z * (i % 2), W * i / teeth) for i in range(teeth + 1)]
    right = [(L - 1 - z * (i % 2), W * i / teeth) for i in range(teeth, -1, -1)]
    m = Image.new("L", (L, W), 0)
    ImageDraw.Draw(m).polygon(left + right, fill=255)
    t.putalpha(ImageChops.multiply(t.getchannel("A"), m))
    return t


# ---------------------------------------------------------------- embellishments

def _ellipse_pts(cx, cy, a, b, deg, n=40):
    r = math.radians(deg)
    return [(cx + a * math.cos(t) * math.cos(r) - b * math.sin(t) * math.sin(r),
             cy + a * math.cos(t) * math.sin(r) + b * math.sin(t) * math.cos(r))
            for t in (2 * math.pi * i / n for i in range(n))]


def _petal(cx, cy, ang, length, width, n=28):
    ca, sa = math.cos(ang), math.sin(ang)
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x, y = length / 2 * (1 + math.cos(t)), width / 2 * math.sin(t)
        pts.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    return pts


def pearl(r, color=(246, 242, 235)):
    s = int(2 * r + 2)
    im = Image.new("RGBA", (s, s), CLEAR)
    d = ImageDraw.Draw(im)
    steps = max(4, int(r))
    for i in range(steps):
        t = i / steps
        rr, off = r * (1 - t), r * 0.35 * t
        d.ellipse((r - rr - off + 1, r - rr - off + 1, r + rr - off + 1, r + rr - off + 1),
                  fill=rgba(mix(darken(color, 0.25), (255, 255, 255), t)))
    return im


def _stack(base, layer, blur, opacity=0.45):
    """Composite `layer` onto `base` with a small shadow, for dimensional paper layers."""
    sh = Image.new("RGBA", base.size, (40, 25, 15, 0))
    sh.putalpha(layer.getchannel("A").filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * opacity)))
    composite_at(base, sh, blur * 0.4, blur * 0.7)
    base.alpha_composite(layer)
    return base


def flower(r, color, kind: str = "round"):
    """Layered paper flower. kind: round (5-petal), daisy (thin petals) or rose."""
    layers, n0, wf = {"round": (3, 5, 0.95), "daisy": (2, 13, 0.30), "rose": (4, 5, 1.05)}[kind]
    s = int(r * 2.2)
    c = s / 2
    im = Image.new("RGBA", (s, s), CLEAR)
    for li in range(layers):
        lr = r * (1 - li * 0.62 / layers)
        col = mix(darken(color, 0.10), lighten(color, 0.22), li / max(1, layers - 1))
        layer = Image.new("RGBA", (s, s), CLEAR)
        d = ImageDraw.Draw(layer)
        n, rot = n0 + li % 2, random.uniform(0, 2 * math.pi)
        for k in range(n):
            a = rot + 2 * math.pi * k / n
            d.polygon(_petal(c, c, a, lr, lr * wf), fill=rgba(col), outline=rgba(darken(col, 0.22)),
                      width=max(1, int(r / 70)))
            if kind != "rose":
                d.line([(c, c), (c + math.cos(a) * lr * 0.75, c + math.sin(a) * lr * 0.75)],
                       fill=rgba(darken(col, 0.12)), width=max(1, int(r / 90)))
        im = _stack(im, layer, blur=max(2, r / 25))
    d = ImageDraw.Draw(im)
    if kind == "rose":
        for i in range(5):
            rr = r * 0.24 * (1 - i / 5)
            st = random.uniform(0, 360)
            d.arc((c - rr, c - rr, c + rr, c + rr), st, st + 250, fill=rgba(darken(color, 0.3)),
                  width=max(1, int(r / 45)))
    elif kind == "daisy":
        for _ in range(14):
            a, rr = random.uniform(0, 2 * math.pi), random.uniform(0, r * 0.14)
            x, y, dr = c + math.cos(a) * rr, c + math.sin(a) * rr, max(2, r * 0.035)
            d.ellipse((x - dr, y - dr, x + dr, y + dr), fill=rgba(darken(color, 0.45)))
    else:
        p = pearl(max(3, r * 0.15))
        im.alpha_composite(p, (int(c - p.width / 2), int(c - p.height / 2)))
    return im


def leaf(length, color, outline_only: bool = False):
    length = int(length)
    w = length * 0.38
    h = int(w) + 6
    im = Image.new("RGBA", (length + 6, h), CLEAR)
    d = ImageDraw.Draw(im)
    top = [(3 + length * i / 20, h / 2 - w / 2 * math.sin(math.pi * i / 20) ** 0.8) for i in range(21)]
    bot = [(3 + length * i / 20, h / 2 + w / 2 * math.sin(math.pi * i / 20) ** 0.8) for i in range(20, -1, -1)]
    edge = rgba(darken(color, 0.3))
    lw = max(2, length // 60)
    if outline_only:
        d.line(top + bot + [top[0]], fill=rgba(color), width=lw)
        edge = rgba(color)
    else:
        d.polygon(top + bot, fill=rgba(color), outline=edge, width=lw)
    d.line([(3, h / 2), (3 + length * 0.92, h / 2)], fill=edge, width=lw)
    for i in range(1, 6):
        x = 3 + length * i / 7
        d.line([(x, h / 2), (x + length * 0.1, h / 2 - w * 0.3)], fill=edge, width=max(1, lw - 1))
        d.line([(x, h / 2), (x + length * 0.1, h / 2 + w * 0.3)], fill=edge, width=max(1, lw - 1))
    return im


def flower_cluster(canvas, center, size, colors, leaf_color, n: int = 4, kinds=("round", "rose", "daisy")):
    """A posy: leaves fanned underneath, small blooms first, the biggest on top."""
    cx, cy = center
    for _ in range(n + 2):
        a, L = random.uniform(0, 2 * math.pi), size * random.uniform(0.5, 0.8)
        place(canvas, leaf(L, leaf_color), (cx + math.cos(a) * L * 0.55, cy + math.sin(a) * L * 0.55),
              angle=-math.degrees(a), shadow=0.3)
    spots = [(0, 0, 0.40)]
    for _ in range(n - 1):
        a = random.uniform(0, 2 * math.pi)
        spots.append((math.cos(a) * size * 0.36, math.sin(a) * size * 0.36, random.uniform(0.18, 0.28)))
    for dx, dy, rf in sorted(spots, key=lambda s: s[2]):
        place(canvas, flower(size * rf, random.choice(colors), random.choice(kinds)), (cx + dx, cy + dy),
              angle=random.uniform(0, 360), shadow=0.42)


def butterfly(size, color, accent):
    s = int(size)
    c = s / 2
    half = Image.new("RGBA", (s, s), CLEAR)
    d = ImageDraw.Draw(half)
    edge = rgba(darken(color, 0.45))
    lw = max(1, s // 90)
    d.polygon(_ellipse_pts(c + s * 0.15, c + s * 0.14, s * 0.14, s * 0.11, 35), fill=rgba(lighten(color, 0.2)),
              outline=edge, width=lw)
    d.polygon(_ellipse_pts(c + s * 0.21, c - s * 0.11, s * 0.22, s * 0.16, -28), fill=rgba(color), outline=edge,
              width=lw)
    for k in range(4):
        a = math.radians(-60 + k * 30)
        d.line([(c + s * 0.03, c), (c + s * 0.03 + math.cos(a) * s * 0.36, c + math.sin(a) * s * 0.3)],
               fill=rgba(darken(color, 0.25), 160), width=lw)
    for (x, y, r) in ((0.33, -0.18, 0.04), (0.2, 0.17, 0.03)):
        d.ellipse((c + s * x - s * r, c + s * y - s * r, c + s * x + s * r, c + s * y + s * r), fill=rgba(accent))
        d.ellipse((c + s * x - s * r * 0.35, c + s * y - s * r * 0.35, c + s * x + s * r * 0.35,
                   c + s * y + s * r * 0.35), fill=(255, 255, 255, 255))
    im = Image.alpha_composite(half, ImageOps.mirror(half))
    d = ImageDraw.Draw(im)
    body = rgba(darken(color, 0.55))
    d.ellipse((c - s * 0.022, c - s * 0.17, c + s * 0.022, c + s * 0.2), fill=body)
    for sx in (-1, 1):
        d.line([(c, c - s * 0.16), (c + sx * s * 0.08, c - s * 0.33)], fill=body, width=lw)
        d.ellipse((c + sx * s * 0.08 - 3, c - s * 0.33 - 3, c + sx * s * 0.08 + 3, c - s * 0.33 + 3), fill=body)
    return im


def clock(r, ring, face, ink, label: str = "Paris", year: str = "1888"):
    """Vintage clock face with Roman numerals."""
    r = int(r)
    s = 2 * r + 4
    c = s / 2
    im = Image.new("RGBA", (s, s), CLEAR)
    d = ImageDraw.Draw(im)
    d.ellipse((c - r, c - r, c + r, c + r), fill=rgba(ring))
    d.ellipse((c - r * 0.95, c - r * 0.95, c + r * 0.95, c + r * 0.95), outline=rgba(lighten(ring, 0.35)),
              width=max(2, r // 70))
    fr = int(r * 0.82)
    fm = Image.new("L", (2 * fr, 2 * fr), 0)
    ImageDraw.Draw(fm).ellipse((0, 0, 2 * fr - 1, 2 * fr - 1), fill=255)
    fc = paper((2 * fr, 2 * fr), face, mottle=0.25)
    edge = ImageChops.subtract(fm, fm.filter(ImageFilter.GaussianBlur(fr * 0.18)))
    fc = Image.composite(Image.new("RGBA", fc.size, rgba(darken(face, 0.35))), fc, edge.point(lambda v: int(v * 0.7)))
    fc.putalpha(fm)
    im.alpha_composite(fc, (int(c - fr), int(c - fr)))
    for m in range(60):
        a = math.radians(m * 6 - 90)
        r0 = r * (0.70 if m % 5 == 0 else 0.75)
        d.line([(c + math.cos(a) * r0, c + math.sin(a) * r0), (c + math.cos(a) * r * 0.79, c + math.sin(a) * r * 0.79)],
               fill=rgba(ink), width=max(1, r // (60 if m % 5 == 0 else 120)))
    numerals = ["XII", "I", "II", "III", "IIII", "V", "VI", "VII", "VIII", "IX", "X", "XI"]
    for i, num in enumerate(numerals):
        a = math.radians(i * 30 - 90)
        t = text_piece(num, "display", r * 0.15, ink).rotate(-i * 30, resample=Image.BICUBIC, expand=True)
        composite_at(im, t, c + math.cos(a) * r * 0.57 - t.width / 2, c + math.sin(a) * r * 0.57 - t.height / 2)
    d.ellipse((c - r * 0.42, c - r * 0.42, c + r * 0.42, c + r * 0.42), outline=rgba(ink, 120), width=max(1, r // 150))
    d.text((c, c - r * 0.2), label, font=font("italic", r * 0.12), fill=rgba(ink), anchor="mm")
    d.text((c, c + r * 0.27), year, font=font("serif", r * 0.08), fill=rgba(ink), anchor="mm")
    for length, width, a in ((0.36, 0.035, random.uniform(0, 360)), (0.6, 0.022, random.uniform(0, 360))):
        a = math.radians(a)
        d.line([(c, c), (c + math.cos(a) * r * length, c + math.sin(a) * r * length)], fill=rgba(ink),
               width=max(2, int(r * width)))
    p = pearl(max(3, r * 0.05), color=lighten(ring, 0.3))
    im.alpha_composite(p, (int(c - p.width / 2), int(c - p.height / 2)))
    return im


def flourish(size, color):
    """Tapered spiral curl, like a chipboard swirl."""
    s = int(size)
    c = s / 2
    im = Image.new("RGBA", (s, s), CLEAR)
    d = ImageDraw.Draw(im)
    pts = []
    for i in range(240):
        t = i / 239
        th, rr = t * 3.4 * math.pi, s * 0.45 * (1 - t * 0.88)
        pts.append((c + rr * math.cos(th), c + rr * math.sin(th)))
    for i in range(len(pts) - 1):
        w = int(max(2, s * 0.035 * (1 - i / len(pts)) + 2))
        d.line([pts[i], pts[i + 1]], fill=rgba(color), width=w)
    return im


def pearl_swirl(size, pr):
    """A curl of graduated pearls."""
    s = int(size)
    c = s / 2
    im = Image.new("RGBA", (s, s), CLEAR)
    thmax, last = 2 * math.pi * 1.6, None
    th = 0.0
    while th < thmax:
        rr = s * 0.42 * (1 - th / (thmax * 1.15))
        cur = pr * (1 - 0.55 * th / thmax)
        x, y = c + rr * math.cos(th), c + rr * math.sin(th)
        if last is None or math.dist(last, (x, y)) >= 2.2 * cur:
            p = pearl(cur)
            composite_at(im, p, x - p.width / 2, y - p.height / 2)
            last = (x, y)
        th += 0.01
    return im


# ---------------------------------------------------------------- labels

def label_card(text, w, h, ink, card=(251, 249, 243), kind: str = "script"):
    """Name label with notched corners and an inset border."""
    w, h = int(w), int(h)
    im = paper((w, h), card, mottle=0.03, grain=0.12)
    d = ImageDraw.Draw(im)
    n, m = int(h * 0.16), int(h * 0.09)
    for cx, cy in ((0, 0), (w, 0), (0, h), (w, h)):
        d.ellipse((cx - n, cy - n, cx + n, cy + n), fill=CLEAR)
    R = n + m
    e = math.sqrt(R * R - m * m)
    a0 = math.degrees(math.asin(m / R))
    line = rgba(ink)
    lw = max(2, h // 70)
    for (cx, cy), base in (((0, 0), 0), ((w, 0), 90), ((w, h), 180), ((0, h), 270)):
        d.arc((cx - R, cy - R, cx + R, cy + R), base + a0, base + 90 - a0, fill=line, width=lw)
    d.line((e, m, w - e, m), fill=line, width=lw)
    d.line((e, h - m, w - e, h - m), fill=line, width=lw)
    d.line((m, e, m, h - e), fill=line, width=lw)
    d.line((w - m, e, w - m, h - e), fill=line, width=lw)
    d.text((w / 2, h / 2), text, font=fit_font(kind, text, w * 0.76, h * 0.5), fill=line, anchor="mm")
    return im


def definition_label(word, pos, definition, w, ink, card=(252, 251, 247)):
    """Dictionary-entry strip: bold word, then (pos.) definition."""
    w = int(w)
    pad = int(w * 0.05)
    fw, fb = font("bold", w * 0.075), font("type", w * 0.04)
    lines = wrap(f"({pos}) {definition}", fb, w - 2 * pad)
    asc, desc = fb.getmetrics()
    lh = int((asc + desc) * 1.1)
    head = sum(fw.getmetrics())
    h = pad + head + int(pad * 0.3) + lh * len(lines) + pad
    im = paper((w, h), card, mottle=0.03, grain=0.12)
    d = ImageDraw.Draw(im)
    d.text((pad, pad), word.capitalize(), font=fw, fill=rgba(ink))
    for i, line in enumerate(lines):
        d.text((pad, pad + head + int(pad * 0.3) + i * lh), line, font=fb, fill=rgba(ink))
    return im


def number_tag(text, w, h, ink, card):
    w, h = int(w), int(h)
    im = Image.new("RGBA", (w, h), CLEAR)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), int(h * 0.2), fill=rgba(ink))
    i1, i2 = int(h * 0.07), int(h * 0.13)
    d.rounded_rectangle((i1, i1, w - i1, h - i1), int(h * 0.15), fill=rgba(card))
    d.rounded_rectangle((i2, i2, w - i2, h - i2), int(h * 0.1), outline=rgba(ink), width=max(2, h // 50))
    d.text((w / 2, h / 2), text, font=fit_font("display", text, w * 0.7, h * 0.55), fill=rgba(ink), anchor="mm")
    return im


def newsprint(w, h, headline, body, ink, color):
    """Torn newspaper clipping: headline, double rule, two columns of text."""
    w, h = int(w), int(h)
    im = paper((w, h), color, mottle=0.22, grain=0.3)
    d = ImageDraw.Draw(im)
    pad = int(w * 0.07)
    fh = font("news", w * 0.11)
    y = pad
    for line in wrap(headline.upper(), fh, w - 2 * pad):
        d.text((w / 2, y), line, font=fh, fill=rgba(ink), anchor="mt")
        y += int(fh.size * 1.1)
    y += 10
    d.line((pad, y, w - pad, y), fill=rgba(ink), width=4)
    d.line((pad, y + 10, w - pad, y + 10), fill=rgba(ink), width=1)
    y += 30
    fb = font("serif", w * 0.032)
    gap = int(w * 0.04)
    col_w = (w - 2 * pad - gap) / 2
    lh = int(fb.size * 1.3)
    lines = wrap((body.strip() + " ") * 20, fb, col_w)
    per_col = max(1, (h - pad - y) // lh)
    for col in range(2):
        for j, line in enumerate(lines[col * per_col:(col + 1) * per_col]):
            d.text((pad + col * (col_w + gap), y + j * lh), line, font=fb, fill=rgba(ink, 220))
    return torn(im, amp=10, burn=18)


def nameplate(w, h, lines, metal, ink, card=(248, 246, 240)):
    """Ornate oval metal frame holding a few lines of script text."""
    w, h = int(w), int(h)
    im = Image.new("RGBA", (w, h), CLEAR)
    d = ImageDraw.Draw(im)
    cx, cy, a, b = w / 2, h / 2, w * 0.43, h * 0.4
    rr = h * 0.06
    for i in range(40):
        t = 2 * math.pi * i / 40
        x, y = cx + a * math.cos(t), cy + b * math.sin(t)
        d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=rgba(metal))
    for sy in (-1, 1):
        y = cy + sy * (b + rr * 0.6)
        d.polygon([(cx - rr * 2, y), (cx, y + sy * rr * 2.2), (cx + rr * 2, y)], fill=rgba(metal))
    d.ellipse((cx - a, cy - b, cx + a, cy + b), fill=rgba(metal))
    d.ellipse((cx - a * 0.94, cy - b * 0.92, cx + a * 0.94, cy + b * 0.92), outline=rgba(lighten(metal, 0.3)),
              width=max(2, h // 60))
    ia, ib = a * 0.80, b * 0.72
    d.ellipse((cx - ia, cy - ib, cx + ia, cy + ib), fill=rgba(card), outline=rgba(darken(metal, 0.3)), width=2)
    lh = ib * 2 * 0.8 / max(1, len(lines))
    for i, line in enumerate(lines):
        f = fit_font("script", line, ia * 1.6, lh * 0.9)
        d.text((cx, cy - ib * 0.8 + lh * (i + 0.5)), line, font=f, fill=rgba(ink), anchor="mm")
    return im


# ---------------------------------------------------------------- lace & ribbon

def lace_frame(size, band, color=(250, 250, 248)):
    """Punched scalloped border around the whole page, with eyelets."""
    w, h = int(size[0]), int(size[1])
    band = int(band)
    s = max(6, int(band * 0.22))
    im = Image.new("RGBA", (w, h), CLEAR)
    d = ImageDraw.Draw(im)
    c = rgba(color)
    d.rectangle((s, s, w - s, h - s), fill=c)
    for x in range(s, w - s + 1, 2 * s):
        d.ellipse((x - s, 0, x + s, 2 * s), fill=c)
        d.ellipse((x - s, h - 2 * s, x + s, h), fill=c)
    for y in range(s, h - s + 1, 2 * s):
        d.ellipse((0, y - s, 2 * s, y + s), fill=c)
        d.ellipse((w - 2 * s, y - s, w, y + s), fill=c)
    er = max(2, s * 0.28)
    for x in range(s, w - s + 1, 2 * s):
        for y in (s, h - s):
            d.ellipse((x - er, y - er, x + er, y + er), fill=CLEAR)
    for y in range(s, h - s + 1, 2 * s):
        for x in (s, w - s):
            d.ellipse((x - er, y - er, x + er, y + er), fill=CLEAR)
    k, r2 = s * 2.4, max(2, s * 0.17)
    x = k
    while x < w - k:
        for y in (k, h - k):
            d.ellipse((x - r2, y - r2, x + r2, y + r2), fill=CLEAR)
        x += s
    y = k
    while y < h - k:
        for x in (k, w - k):
            d.ellipse((x - r2, y - r2, x + r2, y + r2), fill=CLEAR)
        y += s
    # faint printed rosettes on the band
    mid = (k + band) / 2
    dot = rgba(darken(color, 0.1))
    for x in range(int(mid), w - int(mid), int(s * 2.5)):
        for y in (mid, h - mid):
            for t in range(5):
                a = 2 * math.pi * t / 5
                px, py = x + math.cos(a) * s * 0.35, y + math.sin(a) * s * 0.35
                d.ellipse((px - s * 0.12, py - s * 0.12, px + s * 0.12, py + s * 0.12), fill=dot)
    d.rectangle((band, band, w - band, h - band), fill=CLEAR)
    sr = s * 0.5
    for x in range(band, w - band, int(2 * sr)):
        d.ellipse((x - sr, band - sr, x + sr, band + sr), fill=c)
        d.ellipse((x - sr, h - band - sr, x + sr, h - band + sr), fill=c)
    for y in range(band, h - band, int(2 * sr)):
        d.ellipse((band - sr, y - sr, band + sr, y + sr), fill=c)
        d.ellipse((w - band - sr, y - sr, w - band + sr, y + sr), fill=c)
    return im


def lace_strip(length, height, color=(250, 250, 248)):
    L, H = int(length), int(height)
    im = Image.new("RGBA", (L, H), CLEAR)
    d = ImageDraw.Draw(im)
    c = rgba(color)
    top, r = int(H * 0.45), int(H * 0.3)
    d.rectangle((0, 0, L, top), fill=c)
    for x in range(r, L, 2 * r):
        d.ellipse((x - r, top - r, x + r, top + r), fill=c)
        d.ellipse((x - r * 0.18, top - r * 0.18, x + r * 0.18, top + r * 0.18), fill=CLEAR)
        for j in range(5):
            a = math.pi * (0.15 + 0.7 * j / 4)
            px, py, hr = x + math.cos(a) * r * 0.62, top + math.sin(a) * r * 0.62, r * 0.1
            d.ellipse((px - hr, py - hr, px + hr, py + hr), fill=CLEAR)
    hr = H * 0.035
    for x in range(int(H * 0.1), L, int(H * 0.14)):
        y = H * 0.16
        d.ellipse((x - hr, y - hr, x + hr, y + hr), fill=CLEAR)
    return im


def ribbon(length, height, color):
    """Pleated ribbon band edged with pearls."""
    L, H = int(length), int(height)
    im = Image.new("RGBA", (L, H), CLEAR)
    d = ImageDraw.Draw(im)
    y0, y1 = H * 0.2, H * 0.8
    d.rectangle((0, y0, L, y1), fill=rgba(color))
    step = max(10, int(H * 0.45))
    for x in range(0, L, step):
        d.polygon([(x, y0), (x + step * 0.35, y0), (x + step * 0.3, y1), (x, y1)], fill=rgba(darken(color, 0.18)))
        d.line((x + step * 0.36, y0, x + step * 0.32, y1), fill=rgba(lighten(color, 0.25)), width=2)
    pr = max(3, H * 0.075)
    p = pearl(pr)
    x = pr
    while x < L - pr:
        for y in (y0 - pr * 0.4, y1 + pr * 0.4):
            composite_at(im, p, x - p.width / 2, y - p.height / 2)
        x += pr * 2.3
    return im
