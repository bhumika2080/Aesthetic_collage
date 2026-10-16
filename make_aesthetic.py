"""Turn a vibe into one aesthetic scrapbook page / mood board.

    python make_aesthetic.py "cozy autumn"
    python make_aesthetic.py "dark academia" -s journal
    python make_aesthetic.py "cottagecore" -s all

Pipeline:
  1. Tarka LLM (art director)   -> title, search terms, palette, quote, journal text, word, style
  2. Openverse (free, CC images) -> candidate photos
  3. Tarka LLM (vision curator)  -> looks at a contact sheet, picks the most cohesive set
  4. Pillow (styles.py)          -> composes the page: grid, journal, layered or heritage

`prepare` runs steps 1-3 once; `render` can then lay the same photos out in any
style as often as you like. The web UI (app.py) uses both.
"""
from __future__ import annotations

import argparse
import os
import random
import re
import sys
from datetime import datetime
from pathlib import Path

from sources import curate, gather, plan_moodboard
from styles import COUNTS, compose

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def print_step(stage: str, msg: str) -> None:
    print(f"  {msg}", flush=True)


def prepare(vibe: str, style: str = "auto", on_step=print_step) -> dict:
    """Plan with Tarka, find photos, let Tarka curate. Returns a session for `render`."""
    if not os.environ.get("TARKA_API_KEY"):
        raise RuntimeError("TARKA_API_KEY is not set. Put it in .env (see .env.example).")

    on_step("plan", f"art-directing “{vibe}” with Tarka…")
    plan = plan_moodboard(vibe)
    on_step("plan", f"title: {plan['title']} — {plan['subtitle']}")
    on_step("plan", f"palette: {' '.join(plan['palette'])}")
    styles = list(COUNTS) if style == "all" else [plan["style"] if style == "auto" else style]
    on_step("plan", f"style: {', '.join(styles)}" + (" (Tarka's pick)" if style == "auto" else ""))

    on_step("search", f"searching Openverse: {', '.join(plan['queries'])}")
    candidates = gather(plan["queries"], per_query=4)
    on_step("search", f"{len(candidates)} usable photos")
    if len(candidates) < 3:
        raise RuntimeError("Not enough photos found — try a different vibe.")

    # Curate enough photos for any style, so the session can be re-rendered freely.
    want = min(len(candidates), max(COUNTS.values()))
    on_step("curate", "letting Tarka pick the most cohesive set…")
    try:
        picks, why = curate(vibe, plan, candidates, want)
        if why:
            on_step("curate", f"curator: {why}")
    except Exception as e:
        on_step("curate", f"curation skipped ({e}); using a mix of all searches")
        picks = []
    picks += [i for i in range(len(candidates)) if i not in picks]
    return {"vibe": vibe, "plan": plan, "styles": styles, "chosen": [candidates[i] for i in picks[:want]]}


def credits(chosen: list) -> list:
    return [{
        "title": c.get("title") or "untitled",
        "creator": c.get("creator") or "unknown",
        "license": f"{(c.get('license') or '').upper()} {c.get('license_version') or ''}".strip(),
        "link": c.get("foreign_landing_url") or c.get("url"),
    } for c in chosen]


def render(session: dict, style: str, seed: int | None = None, out: Path | None = None) -> dict:
    """Compose one page from a prepared session; saves PNG + credits file."""
    random.seed(seed)
    used = session["chosen"][:COUNTS[style]]
    page = compose(style, session["plan"], [c["img"] for c in used])
    slug = re.sub(r"[^a-z0-9]+", "-", session["vibe"].lower()).strip("-") or "aesthetic"
    out = out or OUTPUT / f"{slug}-{style}-{datetime.now():%Y%m%d-%H%M%S-%f}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    page.save(out, optimize=True)
    cr = credits(used)
    lines = [f"{session['plan']['title']} — photo credits (via Openverse)\n"]
    lines += [f"- “{c['title']}” by {c['creator']} — {c['license']} — {c['link']}" for c in cr]
    out.with_suffix(".credits.txt").write_text("\n".join(lines) + "\n")
    return {"style": style, "path": out, "credits": cr}


def main() -> None:
    ap = argparse.ArgumentParser(description="Make one aesthetic scrapbook page from a vibe.")
    ap.add_argument("vibe", help='e.g. "cozy autumn", "y2k summer", "dark academia"')
    ap.add_argument("-s", "--style", default="auto", choices=["auto", "all", *COUNTS],
                    help="page format (default: auto — Tarka picks one that suits the vibe)")
    ap.add_argument("-o", "--out", type=Path, help="output PNG path (single style only)")
    ap.add_argument("--seed", type=int, help="fix the random layout jitter for repeatable pages")
    args = ap.parse_args()

    load_env()
    try:
        session = prepare(args.vibe, args.style)
    except RuntimeError as e:
        sys.exit(str(e))
    for style in session["styles"]:
        print(f"✦ composing {style} page…")
        out = args.out if args.out and len(session["styles"]) == 1 else None
        result = render(session, style, seed=args.seed, out=out)
        print(f"  saved {result['path']}")


if __name__ == "__main__":
    main()
