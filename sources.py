"""Talking to the outside world: Tarka (art direction + curation) and Openverse (photos)."""
from __future__ import annotations

import base64
import io
import json
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageDraw, ImageOps

from ephemera import font

TARKA_URL = "https://tarka.rest/v1/chat/completions"
OPENVERSE_URL = "https://api.openverse.org/v1/images/"
USER_AGENT = "aesthetic-collage/1.0 (personal project)"
STYLE_NAMES = ("journal", "layered", "heritage", "grid")


def http_get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def log(msg: str) -> None:
    print(f"  {msg}", flush=True)


# ---------------------------------------------------------------- tarka

def tarka_chat(content, max_tokens: int = 1000, retries: int = 3) -> str:
    """Call Tarka's OpenAI-compatible chat endpoint and return the reply text.

    Thinking is switched off: the model reasons at ~13 tokens/s, which turns a
    simple pick-the-photos reply into a multi-minute wait.
    """
    body = json.dumps({
        "model": os.environ.get("TARKA_MODEL", "qwen3.8-flash-next"),
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    headers = {
        "Authorization": f"Bearer {os.environ['TARKA_API_KEY']}",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    for attempt in range(retries):
        try:
            req = urllib.request.Request(TARKA_URL, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.load(r)
            return data["choices"][0]["message"].get("content") or ""
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503, 504) and attempt < retries - 1:
                time.sleep(float(e.headers.get("Retry-After") or 2 ** (attempt + 1)))
                continue
            raise RuntimeError(f"Tarka API error {e.code}: {e.read().decode(errors='replace')[:300]}")
    return ""


def extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError(f"no JSON in model reply: {text[:200]!r}")
    return json.loads(match.group(0))


def plan_moodboard(vibe: str) -> dict:
    prompt = f"""You are the art director for an aesthetic scrapbook page / mood board.
The vibe is: "{vibe}"

Reply with ONLY this JSON, no commentary:
{{
  "title": "a short poetic title, 1-4 words, lowercase",
  "subtitle": "one evocative line, max 8 words, lowercase",
  "queries": ["5 plain, common photo search terms of 1-2 words each (like \\"beach\\", \\"seashells\\", \\"linen dress\\") that together capture the vibe: mix scenes, textures, objects. No adjectives like aesthetic, film, grain, vintage"],
  "palette": ["5 hex colors that define the vibe, from lightest to darkest"],
  "headline": "a 2-4 word vintage newspaper headline that fits the vibe",
  "quote": "a short handwritten line, max 7 words, lowercase",
  "journal": "3 short poetic sentences, like a diary entry about this vibe",
  "word": {{"word": "an evocative, slightly rare word fitting the vibe", "pos": "adj. or n. or v.", "definition": "its real definition, max 14 words"}},
  "style": "the page style that suits the vibe best: journal (vintage junk journal, handwriting, torn paper, clippings), layered (botanical layered papers, paper flowers, butterflies), heritage (lace, roses, black-and-white heirloom photo) or grid (clean modern mood board)"
}}"""
    plan = extract_json(tarka_chat(prompt))
    palette = [c for c in plan.get("palette", []) if re.fullmatch(r"#[0-9a-fA-F]{6}", str(c))]
    word = plan.get("word") if isinstance(plan.get("word"), dict) else {}
    title = str(plan.get("title") or vibe).strip()
    style = str(plan.get("style") or "").strip().lower()
    return {
        "title": title,
        "subtitle": str(plan.get("subtitle") or "").strip(),
        "queries": [str(q) for q in plan.get("queries", [])][:5] or [vibe],
        "palette": palette or ["#f4efe6", "#d9c7b0", "#a68a6d", "#6b5544", "#2f2622"],
        "headline": str(plan.get("headline") or title).strip(),
        "quote": str(plan.get("quote") or plan.get("subtitle") or title).strip(),
        "journal": str(plan.get("journal") or plan.get("subtitle") or vibe).strip(),
        "word": {
            "word": str(word.get("word") or title.split()[0]).strip(),
            "pos": str(word.get("pos") or "n.").strip().strip("()"),
            "definition": str(word.get("definition") or plan.get("subtitle") or vibe).strip(),
        },
        "style": style if style in STYLE_NAMES else random.choice(STYLE_NAMES[:3]),
    }


def contact_sheet(images: list, cell: int = 180, cols: int = 5) -> Image.Image:
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * cell), "white")
    draw = ImageDraw.Draw(sheet)
    label = font("bold", 30)
    for i, img in enumerate(images):
        x, y = (i % cols) * cell, (i // cols) * cell
        sheet.paste(ImageOps.fit(img, (cell - 6, cell - 6)), (x + 3, y + 3))
        draw.rectangle((x + 3, y + 3, x + 50, y + 42), fill="black")
        draw.text((x + 8, y + 5), str(i + 1), fill="white", font=label)
    return sheet


def curate(vibe: str, plan: dict, candidates: list, want: int) -> tuple:
    """Show the model a numbered contact sheet; returns (indices of the best fits, its reasoning)."""
    buf = io.BytesIO()
    contact_sheet([c["img"] for c in candidates]).save(buf, "JPEG", quality=80)
    data_url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    prompt = f"""This contact sheet shows {len(candidates)} numbered photos for a mood board.
Vibe: "{vibe}". Palette: {", ".join(plan["palette"])}.

Pick the {want} photos that best fit the vibe AND look beautiful together (cohesive colors, light and mood).
Avoid text-heavy images, screenshots, low quality, or near-duplicates. Put the single strongest image first (it becomes the hero).
Reply with ONLY JSON: {{"picks": [numbers], "why": "one short sentence"}}"""
    reply = extract_json(tarka_chat([
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]))
    picks = []
    for n in reply.get("picks", []):
        i = int(n) - 1
        if 0 <= i < len(candidates) and i not in picks:
            picks.append(i)
    return picks, str(reply.get("why") or "")


# ---------------------------------------------------------------- openverse

def search_images(query: str, n: int) -> list:
    """Search Openverse; if a term is too specific, retry with fewer words."""
    words = query.split()
    results = []
    for k in range(len(words), 0, -1):
        params = urllib.parse.urlencode({"q": " ".join(words[-k:]), "page_size": n * 3, "mature": "false"})
        try:
            results = json.loads(http_get(f"{OPENVERSE_URL}?{params}"))["results"]
        except Exception as e:
            log(f"search failed for {query!r}: {e}")
            return []
        if len(results) >= n * 2:
            break
    random.shuffle(results)
    return [dict(r, query=query) for r in results[: n * 2]]


def download(result: dict) -> dict | None:
    for url in (result.get("url"), result.get("thumbnail")):
        if not url:
            continue
        try:
            img = Image.open(io.BytesIO(http_get(url)))
            img = ImageOps.exif_transpose(img).convert("RGB")
            if min(img.size) >= 400:
                img.thumbnail((1800, 1800))
                return {**result, "img": img}
        except Exception:
            continue
    return None


def gather(queries: list, per_query: int) -> list:
    with ThreadPoolExecutor(8) as pool:
        results = [r for rs in pool.map(lambda q: search_images(q, per_query), queries) for r in rs]
        downloaded = [d for d in pool.map(download, results) if d]
    # keep at most per_query per search term, interleaved so every term is represented
    by_query = {}
    for d in downloaded:
        by_query.setdefault(d["query"], []).append(d)
    out = []
    for i in range(per_query):
        out += [items[i] for items in by_query.values() if i < len(items)]
    return out
