"""Serve the UI and your replays: python3 serve.py [port]

Everything is local and uses only the standard library. No AI calls happen here.
  /                -> ui/
  /assets/pack/    -> "2D Pixel Dungeon Asset Pack/"   (download it yourself, see README)
  /assets/enemies/ -> "Enemy_Animations_Set/"
  /api/replays     -> list of replay files (replays/*.jsonl, logs/*/events.jsonl)
  /replay/<path>   -> one replay file
"""
import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).parent.resolve()
MOUNTS = {
    "/assets/pack/": ROOT / "2D Pixel Dungeon Asset Pack",
    "/assets/enemies/": ROOT / "Enemy_Animations_Set",
    "/replay/": ROOT,
}


def list_replays():
    files = sorted(ROOT.glob("replays/*.jsonl")) + sorted(ROOT.glob("logs/*/events.jsonl"), reverse=True)
    out = []
    for f in files:
        if f.stat().st_size and b'"run_end"' in f.read_bytes():  # only finished runs
            rel = f.relative_to(ROOT).as_posix()
            out.append({"name": rel.removesuffix("/events.jsonl").removesuffix(".jsonl"), "path": rel})
    return out


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = unquote(urlparse(path).path)
        for prefix, base in MOUNTS.items():
            if path.startswith(prefix):
                target = (base / path[len(prefix):]).resolve()
                # Replays may only come from replays/ and logs/, and only as .jsonl.
                allowed = [ROOT / "replays", ROOT / "logs"] if prefix == "/replay/" else [base]
                ok = any(a.resolve() in target.parents for a in allowed)
                if prefix == "/replay/":
                    ok = ok and target.suffix == ".jsonl"
                return str(target) if ok else str(ROOT / "__forbidden__")
        target = (ROOT / "ui" / (path.lstrip("/") or "index.html")).resolve()
        return str(target) if (ROOT / "ui") in target.parents else str(ROOT / "__forbidden__")

    def do_GET(self):
        if urlparse(self.path).path == "/api/replays":
            body = json.dumps(list_replays()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Evil Dungeon Master UI -> http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
