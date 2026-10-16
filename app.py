"""Local web UI for aesthetic-collage.

    .venv/bin/python app.py            -> opens http://127.0.0.1:8765

Listens on localhost only: the Tarka key stays in this process and never
reaches the browser.
"""
from __future__ import annotations

import json
import random
import re
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from make_aesthetic import OUTPUT, ROOT, load_env, prepare, render
from styles import COUNTS

HOST, PORT = "127.0.0.1", 8765
STATIC = ROOT / "static"
JOBS: dict = {}
LOCK = threading.Lock()
NAME_RE = re.compile(r"^(?P<slug>.+)-(?P<style>grid|journal|layered|heritage)-(?P<stamp>\d{8}-\d{6})(?:-\d+)?\.png$")
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript",
         ".png": "image/png", ".jpg": "image/jpeg", ".txt": "text/plain; charset=utf-8"}


def public_result(r: dict) -> dict:
    return {"style": r["style"], "url": f"/output/{r['path'].name}", "credits": r["credits"]}


def public_job(job: dict) -> dict:
    with LOCK:
        return {k: job[k] for k in ("id", "vibe", "status", "stage", "log", "plan", "results", "error")}


def run_job(job: dict, style: str) -> None:
    def on_step(stage, msg):
        with LOCK:
            job["stage"] = stage
            job["log"].append({"stage": stage, "msg": msg})

    try:
        session = prepare(job["vibe"], style, on_step)
        with LOCK:
            job["session"], job["plan"] = session, session["plan"]
        for s in session["styles"]:
            on_step("compose", f"composing {s} page…")
            result = public_result(render(session, s, seed=random.randrange(1 << 30)))
            with LOCK:
                job["results"].append(result)
        with LOCK:
            job["status"], job["stage"] = "done", "done"
    except Exception as e:  # surface every failure to the page
        with LOCK:
            job["status"], job["error"] = "error", str(e)


def gallery(limit: int = 40) -> list:
    items = []
    for p in sorted(OUTPUT.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        m = NAME_RE.match(p.name)
        items.append({
            "url": f"/output/{p.name}",
            "vibe": m["slug"].replace("-", " ") if m else p.stem,
            "style": m["style"] if m else "",
        })
    return items


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # keep the terminal quiet
        pass

    # ---- helpers
    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path, base: Path):
        try:
            path = path.resolve()
            path.relative_to(base.resolve())
        except (ValueError, OSError):
            return self.send_error(404)
        if not path.is_file() or path.suffix not in TYPES:
            return self.send_error(404)
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", TYPES[path.suffix])
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache" if path.suffix in (".html", ".js", ".css") else "max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def read_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return {}

    # ---- routes
    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path == "/":
            return self.send_file(STATIC / "index.html", STATIC)
        if path.startswith("/static/"):
            return self.send_file(STATIC / path[len("/static/"):], STATIC)
        if path.startswith("/output/"):
            return self.send_file(OUTPUT / path[len("/output/"):], OUTPUT)
        if path == "/api/gallery":
            return self.send_json(gallery())
        m = re.fullmatch(r"/api/jobs/([0-9a-f]+)", path)
        if m and m[1] in JOBS:
            return self.send_json(public_job(JOBS[m[1]]))
        self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        body = self.read_json()
        if path == "/api/generate":
            vibe = str(body.get("vibe") or "").strip()[:120]
            style = body.get("style") or "auto"
            if not vibe:
                return self.send_json({"error": "Type a vibe first."}, 400)
            if style not in ("auto", "all", *COUNTS):
                return self.send_json({"error": f"Unknown style {style!r}."}, 400)
            job = {"id": uuid.uuid4().hex[:12], "vibe": vibe, "status": "running", "stage": "plan",
                   "log": [], "plan": None, "results": [], "error": None, "session": None}
            JOBS[job["id"]] = job
            threading.Thread(target=run_job, args=(job, style), daemon=True).start()
            return self.send_json({"id": job["id"]})
        m = re.fullmatch(r"/api/jobs/([0-9a-f]+)/render", path)
        if m and m[1] in JOBS:
            job, style = JOBS[m[1]], body.get("style")
            if not job.get("session") or style not in COUNTS:
                return self.send_json({"error": "Nothing to re-render yet."}, 400)
            try:
                result = public_result(render(job["session"], style, seed=random.randrange(1 << 30)))
            except Exception as e:
                return self.send_json({"error": str(e)}, 500)
            with LOCK:
                job["results"].append(result)
            return self.send_json(result)
        self.send_error(404)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Local web UI for aesthetic-collage.")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    args = ap.parse_args()
    load_env()
    OUTPUT.mkdir(exist_ok=True)
    server = ThreadingHTTPServer((HOST, args.port), Handler)
    url = f"http://{HOST}:{args.port}"
    print(f"✦ aesthetic studio running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye ✦")


if __name__ == "__main__":
    main()
