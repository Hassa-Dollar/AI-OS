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
def fake_http(routes: dict[str, tuple[int, object]]):
    """Serve canned JSON: {"/path": (status, payload)}. Yields the base URL."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            status, payload = routes.get(self.path, (404, {"error": "not found"}))
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
