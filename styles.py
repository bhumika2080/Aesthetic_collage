"""Page styles. Each takes the plan, the curated photos (hero first) and a
colour theme, and returns a finished RGB page.

  grid      clean bento mood board
  journal   vintage junk journal: handwriting, torn/burnt paper, clippings, tape, clock
  layered   botanical layered papers, mesh panel, paper-flower clusters, butterflies
  heritage  lace border, monochrome matted photo, roses, ribbon + nameplate, pearls
"""
from __future__ import annotations

import random
from datetime import datetime
from types import SimpleNamespace

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageOps

from ephemera import (
    butterfly, clock, darken, definition_label, faded, flourish, flower, flower_cluster, font, gauze,
    hex_rgb, label_card, lace_frame, lace_strip, lighten, luminance, mesh, mix, nameplate, newsprint, number_tag,
    paper, pattern_paper, pearl_swirl, photo_print, place, rgba, ribbon, script_paper, tape, text_piece, torn,
)

# How many photos each style uses (hero first).
COUNTS = {"grid": 7, "journal": 6, "layered": 5, "heritage": 3}


# ---------------------------------------------------------------- shared helpers

def theme(plan: dict) -> SimpleNamespace:
    pal = [hex_rgb(c) for c in plan["palette"]]
    s = sorted(pal, key=luminance)
    ink = s[0] if luminance(s[0]) < 90 else darken(s[0], 0.55)
    return SimpleNamespace(
        pal=pal,
        paper=s[-1] if luminance(s[-1]) >= 200 else lighten(s[-1], 0.75),
        ink=ink,
        dark=s[1] if len(s) > 2 else s[0],
        mid=s[len(s) // 2],
        light=s[-2] if len(s) > 1 else s[-1],
    )


def grade(img: Image.Image, mode: str, th: SimpleNamespace, tint=None) -> Image.Image:
    """Colour-grade a photo so pieces from different sources read as one set."""
    img = img.convert("RGB")
    if mode == "mono":
        g = ImageOps.autocontrast(ImageOps.grayscale(img), cutoff=1)
        return ImageOps.colorize(g, black=darken(th.ink, 0.4), white=lighten(th.paper, 0.5), mid=(128, 126, 122))
    sat, default_tint, amount = {
        "film": (0.82, th.mid, 0.09),
        "vintage": (0.55, (196, 154, 108), 0.18),
        "soft": (0.8, th.mid, 0.12),
    }[mode]
    img = ImageEnhance.Color(img).enhance(sat)
    img = ImageEnhance.Contrast(img).enhance(0.94)
    img = img.point(lambda v: int(16 + v * 0.92))
    return Image.blend(img, Image.new("RGB", img.size, tint or default_tint), amount)


def fit_size(img: Image.Image, width: float, lo: float = 0.72, hi: float = 1.45) -> tuple:
    """Keep roughly the photo's own shape, within sensible limits."""
    ar = min(hi, max(lo, img.width / img.height))
    return int(width), int(width / ar)


def finish(canvas: Image.Image) -> Image.Image:
    """Unifying film grain over the whole page."""
    canvas = canvas.convert("RGB")
    noise = Image.effect_noise(canvas.size, 40).convert("RGB")
    return Image.blend(canvas, ImageChops.overlay(canvas, noise), 0.3)


def jitter(v: float, amount: float) -> float:
    return v + random.uniform(-amount, amount)


# ---------------------------------------------------------------- grid

GRID_LAYOUTS = {  # (col, row, colspan, rowspan) on a 3x4 grid; first slot is the hero
    7: [(0, 0, 2, 2), (2, 0, 1, 1), (2, 1, 1, 1), (0, 2, 1, 2), (1, 2, 1, 1), (2, 2, 1, 2), (1, 3, 1, 1)],
    5: [(0, 0, 2, 2), (2, 0, 1, 2), (0, 2, 1, 2), (1, 2, 2, 1), (1, 3, 2, 1)],
    4: [(0, 0, 3, 2), (0, 2, 1, 2), (1, 2, 1, 2), (2, 2, 1, 2)],
}


def grid(plan, images, th):
    W, H, margin, gap, radius = 2400, 3000, 120, 28, 18
    images = images[:max(n for n in GRID_LAYOUTS if n <= len(images))]
    canvas = Image.new("RGBA", (W, H), rgba(th.paper))
    d = ImageDraw.Draw(canvas)

    d.text((W / 2, margin + 130), plan["title"], fill=rgba(th.ink), font=font("display", 150), anchor="ms")
    if plan["subtitle"]:
        d.text((W / 2, margin + 230), plan["subtitle"], fill=rgba(th.ink), font=font("italic", 52), anchor="ms")
    d.line((W / 2 - 60, margin + 290, W / 2 + 60, margin + 290), fill=rgba(th.ink), width=3)

    mids = sorted(th.pal, key=luminance)[1:-1] or th.pal
    top, bottom = margin + 340, H - margin - 300
    cw = (W - 2 * margin - 2 * gap) / 3
    rh = (bottom - top - 3 * gap) / 4
    for i, (img, (c, r, cs, rs)) in enumerate(zip(images, GRID_LAYOUTS[len(images)])):
        x, y = margin + c * (cw + gap), top + r * (rh + gap)
        w, h = int(cs * cw + (cs - 1) * gap), int(rs * rh + (rs - 1) * gap)
        tile = grade(ImageOps.fit(img, (w, h), Image.LANCZOS), "film", th, tint=mids[i % len(mids)])
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=255)
        canvas.paste(tile, (int(x), int(y)), mask)

    sw, sy = 100, H - margin - 90
    start = W / 2 - (len(th.pal) * sw + (len(th.pal) - 1) * 40) / 2
    for i, (rgb, hx) in enumerate(zip(th.pal, plan["palette"])):
        x = start + i * (sw + 40)
        d.ellipse((x, sy - sw, x + sw, sy), fill=rgba(rgb), outline=rgba(th.ink), width=2)
        d.text((x + sw / 2, sy + 55), hx.lower(), fill=rgba(th.ink), font=font("serif", 30), anchor="ms")
    return finish(canvas)


# ---------------------------------------------------------------- journal

def journal(plan, images, th):
    W, H = 2000, 2800
    parchment = mix(th.paper, (236, 222, 196), 0.55)
    ink = th.ink
    canvas = script_paper((W, H), plan["journal"], parchment, ink, alpha=55, fsize=62)
    d = ImageDraw.Draw(canvas)
    for y in range(70, H - 40, 78):  # spiral-bound punch holes
        d.ellipse((30, y, 58, y + 28), fill=rgba(darken(parchment, 0.55)))

    # backing scraps
    strip = script_paper((560, 1700), plan["journal"], darken(parchment, 0.12), ink, alpha=150, fsize=52)
    place(canvas, torn(strip, amp=16, burn=34), (330, 1000), angle=1.2, shadow=0.25)
    news = newsprint(640, 780, plan["headline"], plan["journal"], ink, lighten(parchment, 0.15))
    place(canvas, news, (1060, 520), angle=-2.5, shadow=0.3)

    slots = [  # (cx, cy, width, angle, treatment) as fractions of the page; slot 0 is the hero
        (0.62, 0.44, 0.46, -2.5, "print"),
        (0.25, 0.22, 0.30, 4, "torn"),
        (0.85, 0.19, 0.24, -7, "polaroid"),
        (0.27, 0.58, 0.34, -4, "print"),
        (0.80, 0.71, 0.32, 6, "torn"),
        (0.55, 0.78, 0.30, -1.5, "polaroid"),
    ]
    tape_colors = [lighten(c, 0.3) for c in th.pal[1:]] or [th.light]
    for i in [*range(1, len(slots)), 0]:  # hero last so it sits on top
        if i >= len(images):
            continue
        fx, fy, wf, ang, kind = slots[i]
        img = grade(images[i], "vintage", th)
        size = fit_size(img, wf * W)
        if kind == "torn":
            piece = torn(ImageOps.fit(img, size, Image.LANCZOS), amp=14, burn=26)
        elif kind == "polaroid":
            piece = photo_print(img, size, border=0.05, bottom=0.17)
        else:
            piece = photo_print(img, size, border=0.035)
        cx, cy, ang = jitter(fx * W, 20), jitter(fy * H, 20), jitter(ang, 1.5)
        place(canvas, piece, (cx, cy), ang)
        if i == 0:
            for sx in (-1, 1):
                place(canvas, tape(size[0] * 0.3, 68, random.choice(tape_colors), pattern="stripes"),
                      (cx + sx * (size[0] / 2 - 40), cy - size[1] / 2 + 40), angle=-sx * 40, shadow=0.12)
        elif kind != "torn":
            place(canvas, tape(size[0] * 0.45, 64, random.choice(tape_colors), pattern=random.choice([None, "dots"])),
                  (jitter(cx, size[0] * 0.12), cy - size[1] / 2 + 8), angle=ang + random.uniform(-10, 10),
                  shadow=0.12)

    place(canvas, clock(W * 0.13, ring=th.dark, face=lighten(parchment, 0.2), ink=ink),
          (W * 0.24, H * 0.77), angle=random.uniform(-8, 8))
    place(canvas, number_tag(str(random.randint(100, 999)), 280, 140, ink, lighten(parchment, 0.25)),
          (W * 0.11, H * 0.88), angle=-3)
    for fx, fy, fr in ((0.80, 0.05, 0.10), (0.95, 0.37, 0.08)):
        place(canvas, flower(W * fr, th.mid, "round"), (fx * W, fy * H), angle=random.uniform(0, 360), shadow=0.45)
    flower_cluster(canvas, (W * 0.93, H * 0.94), W * 0.17, [lighten(th.mid, 0.3), th.dark, parchment], th.dark,
                   kinds=("rose", "round"))

    q = text_piece(plan["quote"], "script", 88, ink)
    strip = paper((q.width + 80, q.height + 30), lighten(parchment, 0.3), mottle=0.05)
    strip.alpha_composite(q, (40, 15))
    place(canvas, torn(strip, amp=7), (W * 0.55, H * 0.93), angle=-2, shadow=0.3)
    return finish(canvas)


# ---------------------------------------------------------------- layered

def layered(plan, images, th):
    W, H = 2200, 2800
    canvas = pattern_paper((W, H), th.paper, th.mid)
    cx, cy = W * 0.5, H * 0.47

    # stacked papers behind the centre
    place(canvas, paper((1550, 1550), lighten(th.mid, 0.45), mottle=0.2), (cx, cy), angle=45, shadow=0.3)
    place(canvas, paper((1300, 1300), lighten(th.dark, 0.15), mottle=0.2), (cx + 60, cy - 40), angle=33, shadow=0.35)
    place(canvas, paper((1150, 1400), lighten(th.light, 0.3), mottle=0.15), (cx - 30, cy + 20), angle=-6,
          shadow=0.35)

    # tall torn strip down the left (second photo)
    if len(images) > 1:
        strip = ImageOps.fit(grade(images[1], "soft", th), (400, 1500), Image.LANCZOS)
        place(canvas, torn(strip, amp=10, sides="ns"), (W * 0.15, H * 0.5), angle=0.6, shadow=0.35)

    place(canvas, mesh((1000, 1240), mix(th.mid, (150, 150, 150), 0.6)), (cx, cy), angle=1, shadow=0.35)
    hero = grade(images[0], "soft", th)
    place(canvas, photo_print(hero, fit_size(hero, 800, lo=0.7, hi=1.05), border=0.035), (cx - 10, cy - 10),
          angle=-1.5, shadow=0.45)

    small = [(0.80, 0.17, 0.24, 7, 0.17), (0.80, 0.75, 0.26, -6, None), (0.33, 0.82, 0.22, 5, None)]
    for (fx, fy, wf, ang, bottom), img in zip(small, images[2:]):
        img = grade(img, "soft", th)
        place(canvas, photo_print(img, fit_size(img, wf * W), border=0.05, bottom=bottom),
              (jitter(fx * W, 15), jitter(fy * H, 15)), angle=jitter(ang, 2))

    fcolors = [lighten(th.mid, 0.35), th.light, lighten(th.paper, 0.3), lighten(th.dark, 0.25)]
    flower_cluster(canvas, (W * 0.72, H * 0.29), W * 0.30, fcolors, th.dark)
    flower_cluster(canvas, (W * 0.27, H * 0.67), W * 0.30, fcolors, th.dark)
    flower_cluster(canvas, (W * 0.79, H * 0.60), W * 0.17, fcolors, th.dark, n=3)

    for bx, by, bs in ((0.12, 0.30, 0.14), (0.88, 0.07, 0.13), (0.62, 0.86, 0.11), (0.08, 0.83, 0.10)):
        place(canvas, butterfly(W * bs, random.choice([th.light, lighten(th.mid, 0.3), th.paper]), th.dark),
              (bx * W, by * H), angle=random.uniform(-25, 25), shadow=0.3)

    place(canvas, label_card(plan["title"], W * 0.40, W * 0.13, th.ink), (W * 0.30, H * 0.07), angle=-1.5)
    word = plan["word"]
    place(canvas, definition_label(word["word"], word["pos"], word["definition"], W * 0.48, th.ink),
          (W * 0.66, H * 0.93), angle=0.5)
    return finish(canvas)


# ---------------------------------------------------------------- heritage

def heritage(plan, images, th):
    W = H = 2400
    grey = mix(th.mid, (160, 160, 160), 0.65)
    canvas = paper((W, H), lighten(grey, 0.15), mottle=0.15)
    for sx, sy in ((0.28, 0.26), (0.74, 0.76)):  # faint stamped motif
        place(canvas, faded(flower(W * 0.16, darken(grey, 0.5), "daisy"), 0.22), (sx * W, sy * H), shadow=0)
    place(canvas, paper((W * 0.80, H * 0.80), lighten(grey, 0.35), mottle=0.12), (W / 2, H / 2), shadow=0.25)
    place(canvas, lace_frame((W, H), W * 0.085), (W / 2, H / 2), shadow=0.25)
    place(canvas, gauze((W * 0.55, H * 0.16)), (W * 0.30, H * 0.18), angle=-35, shadow=0)
    place(canvas, gauze((W * 0.55, H * 0.16)), (W * 0.70, H * 0.74), angle=-30, shadow=0)

    hx, hy = W * 0.47, H * 0.42
    for (dx, dy, ang), img in zip(((-0.17, -0.04, -7), (0.17, 0.03, 6)), images[1:]):
        place(canvas, photo_print(grade(img, "mono", th), (W * 0.24, W * 0.30), border=0.04),
              (hx + dx * W, hy + dy * H), angle=ang)
    place(canvas, paper((W * 0.36 + 50, H * 0.48 + 50), darken(grey, 0.35), mottle=0.1), (hx + 14, hy + 14),
          shadow=0.35)
    place(canvas, photo_print(grade(images[0], "mono", th), (W * 0.36, H * 0.48), border=0.025, card=(245, 244, 240)),
          (hx, hy), shadow=0.4)
    place(canvas, flourish(W * 0.2, darken(grey, 0.6)), (W * 0.74, H * 0.36), shadow=0.25)

    place(canvas, lace_strip(W * 0.76, 220), (W * 0.5, H * 0.79), shadow=0.2)
    place(canvas, ribbon(W * 0.74, 150, darken(grey, 0.25)), (W * 0.5, H * 0.73), shadow=0.3)
    place(canvas, nameplate(W * 0.26, H * 0.15, [plan["title"], str(datetime.now().year)], (58, 52, 50), th.ink),
          (W * 0.38, H * 0.73), shadow=0.4)

    blush = [lighten(th.light, 0.6), (246, 238, 234), lighten(th.mid, 0.65)]
    silver = (176, 176, 172)
    flower_cluster(canvas, (W * 0.20, H * 0.19), W * 0.28, blush, silver, n=5, kinds=("rose", "round"))
    flower_cluster(canvas, (W * 0.70, H * 0.71), W * 0.30, blush, silver, n=5, kinds=("rose", "round"))

    for (bx, by), (px, py) in (((0.77, 0.15), (0.83, 0.24)), ((0.22, 0.44), (0.17, 0.53))):
        place(canvas, pearl_swirl(W * 0.09, 9), (px * W, py * H), shadow=0.2)
        place(canvas, butterfly(W * 0.12, lighten(th.mid, 0.55), darken(grey, 0.4)), (bx * W, by * H),
              angle=random.uniform(-20, 20), shadow=0.35)
    place(canvas, clock(W * 0.065, ring=(70, 66, 64), face=(244, 242, 236), ink=(40, 38, 36)),
          (W * 0.86, H * 0.76), shadow=0.35)
    return finish(canvas)


STYLES = {"grid": grid, "journal": journal, "layered": layered, "heritage": heritage}


def compose(style: str, plan: dict, images: list) -> Image.Image:
    return STYLES[style](plan, images, theme(plan))
