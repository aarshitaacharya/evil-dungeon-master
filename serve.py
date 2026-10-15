"""Serve the UI and your replays: python3 serve.py [port]

Everything is local and uses only the standard library. No AI calls happen here.
  /                -> ui/
  /assets/pack/    -> "2D Pixel Dungeon Asset Pack/"   (download it yourself, see README)
  /assets/enemies/ -> "Enemy_Animations_Set/"
  /api/replays     -> list of replay files (replays/*.jsonl, logs/*/events.jsonl)
  /replay/<path>   -> one replay file
  /api/start       -> POST: start a live run (real API calls, bounded by your token budgets)
  /api/stream      -> Server-Sent Events: the live run's events
"""
import json
import os
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).parent.resolve()
os.chdir(ROOT)  # main.py writes logs/ relative to the project root
MAX_LIVE_ROUNDS = 10
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


class LiveRun:
    """One live arena run in a background thread; events are kept so the browser can (re)attach."""

    def __init__(self):
        self.events, self.running = [], False
        self.cond = threading.Condition()

    def emit(self, event):
        with self.cond:
            self.events.append(event)
            self.cond.notify_all()

    def start(self, rounds):
        import llm
        import main
        with self.cond:
            if self.running:
                return False
            self.events, self.running = [], True

        def work():
            try:
                record = main.file_recorder(ROOT / "logs" / time.strftime("%Y%m%d-%H%M%S"))
                main.run(rounds, lambda e: (record(e), self.emit(e)), pause=0.0)
            except Exception as err:  # surface API errors in the UI instead of dying silently
                self.emit({"type": "error", "message": str(err)[:300]})
            finally:
                self.emit({"type": "usage", "report": llm.usage_report()})
                with self.cond:
                    self.running = False
                    self.cond.notify_all()

        threading.Thread(target=work, daemon=True).start()
        return True


LIVE = LiveRun()


def request_allowed(headers):
    """Starting a run spends API tokens, so only our own page may do it: a local Host plus a
    custom header that other websites cannot send cross-origin without our consent."""
    host = headers.get("Host", "").split(":")[0]
    return host in ("localhost", "127.0.0.1") and headers.get("X-EDM") == "1"


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

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/replays":
            self.send_json(list_replays())
        elif path == "/api/status":
            self.send_json({"running": LIVE.running, "events": len(LIVE.events)})
        elif path == "/api/stream":
            self.stream_events()
        else:
            super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path != "/api/start" or not request_allowed(self.headers):
            return self.send_json({"error": "forbidden"}, 403)
        size = int(self.headers.get("Content-Length") or 0)
        try:
            rounds = int(json.loads(self.rfile.read(size) or b"{}").get("rounds", 3))
        except (ValueError, TypeError):
            return self.send_json({"error": "bad request"}, 400)
        rounds = max(1, min(rounds, MAX_LIVE_ROUNDS))
        if not LIVE.start(rounds):
            return self.send_json({"error": "a run is already in progress"}, 409)
        self.send_json({"started": True, "rounds": rounds})

    def stream_events(self):
        """Server-Sent Events. Reconnecting browsers resume from Last-Event-ID."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        nxt = int(self.headers.get("Last-Event-ID", -1)) + 1
        try:
            while True:
                with LIVE.cond:
                    while nxt >= len(LIVE.events) and LIVE.running:
                        LIVE.cond.wait(timeout=15)
                        if nxt >= len(LIVE.events) and LIVE.running:
                            self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                    batch, finished = LIVE.events[nxt:], not LIVE.running
                for event in batch:
                    self.wfile.write(f"id: {nxt}\ndata: {json.dumps(event)}\n\n".encode())
                    nxt += 1
                self.wfile.flush()
                if finished and not batch:
                    self.wfile.write(b"event: done\ndata: {}\n\n")
                    return
        except (BrokenPipeError, ConnectionResetError):
            pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Evil Dungeon Master UI -> http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
