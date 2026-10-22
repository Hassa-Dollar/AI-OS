"""Shared test helpers: temp git repos, a fake HTTP server (no network in tests), cwd switching."""
import contextlib
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
