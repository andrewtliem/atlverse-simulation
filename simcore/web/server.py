"""Local web editor server: python -m simcore.web [--port 8765] [--models DIR]

GET  /                 editor page
GET  /api/models       list saved models (*.json in the models directory)
GET  /api/models/NAME  load a model graph
PUT  /api/models/NAME  save a model graph
POST /api/run?id=X     run a graph; returns report, statistics and the animation trace
GET  /api/progress?id=X replication and simulated time of a run in progress
POST /api/stop?id=X     end a run in progress (Arena's End button); its results so far are returned
POST /api/yaml         convert a graph to the YAML model format
POST /api/validate     list validation problems per module
POST /api/upgrade      convert a graph saved by the first editor version to the current format
"""

from __future__ import annotations

import argparse
import json
import re
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import api
from .api import GraphError

STATIC = Path(__file__).parent / "static"
SAFE_NAME = re.compile(r"^[\w\- ]{1,80}$")
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}

RUNS: dict[str, dict] = {}  # run id -> {"stop", "rep", "time"} for runs in progress
RUNS_LOCK = threading.Lock()


def run_graph(graph: dict, run_id: str | None = None) -> dict:
    state = {"stop": False, "rep": 1, "time": 0.0, "reps": 1}

    def progress(rep, reps, time) -> bool:
        state["rep"], state["reps"], state["time"] = rep, reps, time
        return state["stop"]

    if run_id:
        with RUNS_LOCK:
            RUNS[run_id] = state
    try:
        return api.run_graph(graph, progress)
    finally:
        if run_id:
            with RUNS_LOCK:
                RUNS.pop(run_id, None)


class Handler(BaseHTTPRequestHandler):
    models_dir: Path = Path.cwd()

    def log_message(self, fmt, *args):  # quieter console
        pass

    def _send(self, code: int, body, ctype: str = "application/json") -> None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def _model_path(self, name: str) -> Path | None:
        if not SAFE_NAME.match(name):
            return None
        return self.models_dir / f"{name}.json"

    def _run_id(self) -> str | None:
        rid = parse_qs(urlparse(self.path).query).get("id", [None])[0]
        return rid if rid and re.match(r"^[\w-]{1,64}$", rid) else None

    def do_GET(self):
        if self.path.startswith("/api/progress"):
            st = RUNS.get(self._run_id() or "")
            return self._send(200, {"running": st is not None, **({k: st[k] for k in ("rep", "reps", "time")} if st else {})})
        name = "index.html" if self.path == "/" else self.path.lstrip("/")
        if re.match(r"^[\w-]+\.(html|js|css|svg)$", name) and (STATIC / name).is_file():
            return self._send(200, (STATIC / name).read_bytes(), TYPES[Path(name).suffix])
        if self.path == "/api/models":
            names = sorted(p.stem for p in self.models_dir.glob("*.json"))
            return self._send(200, names)
        if self.path.startswith("/api/models/"):
            p = self._model_path(self.path.rsplit("/", 1)[1].replace("%20", " "))
            if p is None or not p.exists():
                return self._send(404, {"error": "no such model"})
            return self._send(200, json.loads(p.read_text()))
        self._send(404, {"error": "not found"})

    def do_PUT(self):
        if self.path.startswith("/api/models/"):
            p = self._model_path(self.path.rsplit("/", 1)[1].replace("%20", " "))
            if p is None:
                return self._send(400, {"error": "model names may use letters, digits, space, - and _"})
            p.write_text(json.dumps(self._body(), indent=1))
            return self._send(200, {"saved": p.name})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            if urlparse(self.path).path == "/api/run":
                return self._send(200, run_graph(self._body(), self._run_id()))
            if urlparse(self.path).path == "/api/stop":
                st = RUNS.get(self._run_id() or "")
                if st:
                    st["stop"] = True
                return self._send(200, {"stopping": st is not None})
            if self.path == "/api/yaml":
                return self._send(200, {"yaml": api.to_yaml(self._body())})
            if self.path == "/api/upgrade":
                return self._send(200, api.upgrade(self._body()))
            if self.path == "/api/validate":
                return self._send(200, {"problems": api.validate(self._body())})
        except GraphError as e:
            return self._send(400, {"error": str(e), "problems": e.problems})
        except Exception as e:  # report model errors to the page instead of failing silently
            return self._send(400, {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()})
        self._send(404, {"error": "not found"})


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m simcore.web")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--models", default="models", help="directory for saved models")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    d = Path(a.models)
    d.mkdir(parents=True, exist_ok=True)
    Handler.models_dir = d
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"Atlverse Simulation at {url}  (models in {d.resolve()})  Ctrl+C to stop")
    if not a.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
