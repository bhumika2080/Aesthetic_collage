# aesthetic-collage

Type a vibe, get one aesthetic scrapbook page.

## Web UI

```bash
.venv/bin/python app.py
```

This opens `http://127.0.0.1:8765` in your browser. Type a vibe (or tap a suggestion), choose a format, and
watch Tarka work. Once a page is made you can download it, shuffle the layout, or re-render the same photos
in another format in a couple of seconds. Everything you make collects in the gallery at the bottom.

The server only listens on your own machine, and the Tarka key stays in the Python process.
Stop it with Ctrl+C. Options: `--port 9000`, `--no-browser`.

## Command line

Let Tarka pick the style:

```bash
.venv/bin/python make_aesthetic.py "cozy autumn"
```

Choose a style, or render one page in every style:

```bash
.venv/bin/python make_aesthetic.py "dark academia" -s journal
.venv/bin/python make_aesthetic.py "cottagecore" -s all
```

Each page is saved to `output/` with a `.credits.txt` listing the photos used.

## Styles (`-s`)

| style | look |
|---|---|
| `journal` | vintage junk journal: handwriting background, torn & burnt paper, newspaper clipping, washi tape, clock, number tag, paper flowers |
| `layered` | botanical layered papers, mesh panel behind a framed hero photo, paper-flower clusters, butterflies, name label, word-definition label |
| `heritage` | lace border, black-and-white matted photo, rose clusters, ribbon with oval nameplate, pearl swirls, pocket watch |
| `grid` | clean modern bento mood board with palette swatches |
| `auto` (default) | Tarka chooses the one that suits the vibe |
| `all` | renders every style from the same photos |

`--seed N` makes the random layout jitter repeatable; `-o PATH` sets the output file (single style only).

## How it works

1. **Tarka** (`qwen3.8-flash-next` via `https://tarka.rest/v1`) art-directs: title, search terms, palette,
   newspaper headline, handwritten quote, journal text, a word + definition, and a style suggestion.
2. **Openverse** (free, no key) supplies Creative Commons photos for each search term.
3. **Tarka** looks at a numbered contact sheet and picks the most cohesive set, hero first.
4. **Pillow** composes the page. All the ephemera — paper flowers, lace, tape, clocks, butterflies,
   labels — is drawn procedurally in `ephemera.py`; page layouts live in `styles.py`.

| file | role |
|---|---|
| `app.py` + `static/` | local web UI |
| `make_aesthetic.py` | CLI + pipeline (`prepare` once, `render` in any style) |
| `sources.py` | Tarka + Openverse calls |
| `styles.py` | page layouts and colour grading |
| `ephemera.py` | drawn scrapbook elements |

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Then paste your Tarka key into `.env`.

Fonts come from macOS (`/System/Library/Fonts`); on other systems it falls back to Pillow's default font.
Openverse photos are CC-licensed — keep the credits file if you post the page.
