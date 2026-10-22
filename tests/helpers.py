"""Shared test helpers: temp git repos, a fake HTTP server (no network in tests), cwd switching."""
import contextlib
import datetime as dt
import json
import os
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def git_repo(files: dict[str, str] | None = None, remote: str | None = None) -> Path:
    """A throwaway git repo with one commit on branch main."""
    root = Path(tempfile.mkdtemp(prefix="aios-repo-"))
    for rel, text in (files or {"README.md": "x\n"}).items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    run = lambda *a: subprocess.run(["git", *a], cwd=root, check=True, capture_output=True)  # noqa: E731
    run("init", "-q", "-b", "main")
    run("add", "-A")
    run("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "init")
    if remote:
        run("remote", "add", "origin", remote)
    return root


@contextlib.contextmanager
def cwd(path: Path):
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


@contextlib.contextmanager
def fake_http(routes: dict, log: list | None = None):
    """Serve canned JSON; yields the base URL.

    routes: {"/path" or "POST /path": (status, payload) or [(status, payload), ...]}. A list is served in order
    and its last item repeats. Each request is appended to `log` as (method, path, json_body).
    """
    state = {k: list(v) if isinstance(v, list) else [v] for k, v in routes.items()}

    class Handler(BaseHTTPRequestHandler):
        def _serve(self, method):
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n)) if n else None
            if log is not None:
                log.append((method, self.path, body))
            seq = state.get(f"{method} {self.path}") or state.get(self.path) or [(404, {"error": "not found"})]
            status, payload = seq.pop(0) if len(seq) > 1 else seq[0]
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            self._serve("GET")

        def do_POST(self):  # noqa: N802
            self._serve("POST")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


NOW = dt.datetime(2026, 10, 21).timestamp()


def live_from(roster, **changes):
    """A live catalog matching `roster` (prices rise with roster order), with per-id overrides; `_drop` removes."""
    out = [{"id": e.id, "canonical_slug": e.canonical_slug, "created": NOW - 86400 * 200,
            "pricing": {"prompt": str(1e-6 * (i + 1)), "completion": str(2e-6 * (i + 1))}}
           for i, e in enumerate(roster)]
    for m in out:
        m.update(changes.get(m["id"], {}))
    return [m for m in out if not m.get("_drop")]


def clef_answers(cls="feature_backend", conf=0.9, acs=3, cx=1, ctx=1, **noul):
    """A System One answer set in Clef's shape (fake classifier output for router tests)."""
    from aios import router
    flags = {"ambiguity": 0.05, "contract_change_needed": 0.05, "security_sensitive": 0.05, "irreversible": 0.05,
             "needs_vision": 0.05, "needs_hardware": 0.05} | noul
    return {"task_class": {"choice": cls, "confidence": conf, "probabilities": {cls: conf}},
            "acs_executable": router._score(acs, 4), "complexity": router._score(cx, 5),
            "context_breadth": router._score(ctx, 4), **{k: {"noul": v} for k, v in flags.items()}}
