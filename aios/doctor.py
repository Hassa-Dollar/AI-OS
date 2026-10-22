"""`aios doctor`: is this machine ready? Each failing check says what failed and how to fix it (ADR-0004)."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

from . import config, harness

MIN_OLLAMA = (0, 35, 1)
ROUTER_MODELS = {"clef-flash": "FAIL", "clef": "WARN"}  # flash is required; 27B is the optional second opinion


@dataclass(frozen=True)
class Check:
    status: str  # PASS | WARN | FAIL
    name: str
    detail: str
    fix: str = ""


def _get_json(url: str, headers: dict | None = None, timeout: int = 10) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=timeout) as r:
        return json.load(r)


def windows_shadowed(path: str | None) -> bool:
    """On WSL, a binary under /mnt/ is a Windows executable shadowing the Linux one."""
    return bool(path) and path.startswith("/mnt/")


def version_tuple(text: str) -> tuple[int, ...]:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def check_python() -> Check:
    v = sys.version_info
    ok = v >= (3, 11)
    return Check("PASS" if ok else "FAIL", "python", f"{v.major}.{v.minor}.{v.micro}",
                 "" if ok else "install Python >= 3.11")


def check_tool(name: str, required: bool, fix: str) -> Check:
    path = shutil.which(name)
    if not path:
        return Check("FAIL" if required else "WARN", name, "not found on PATH", fix)
    if windows_shadowed(path):
        return Check("FAIL", name, f"{path} is a Windows binary", f"install the Linux {name} and put it first in PATH")
    return Check("PASS", name, path)


def check_key(p: config.Paths, base: str) -> Check:
    try:
        key = config.load_key(p)
    except config.ConfigError as e:
        return Check("FAIL", "openrouter key", str(e), "see docs/INSTALL.md, step 2")
    try:
        d = _get_json(f"{base}/key", {"Authorization": f"Bearer {key}"})["data"]
    except urllib.error.HTTPError as e:
        e.close()
        return Check("FAIL", "openrouter key", f"rejected by OpenRouter (HTTP {e.code})", "create a new key")
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
        return Check("FAIL", "openrouter key", f"could not verify: {e}", "check the network, then retry")
    if d.get("limit") is None:
        return Check("FAIL", "openrouter key", "valid, but has no credit limit",
                     "set a credit limit on this key in OpenRouter: it is the hard spend cap")
    left = d.get("limit_remaining")
    return Check("PASS", "openrouter key", f"valid; ${left:.2f} of ${d['limit']:.2f} left" if left is not None
                 else f"valid; limit ${d['limit']:.2f}")


def check_ollama(base: str) -> list[Check]:
    try:
        version = _get_json(f"{base}/api/version").get("version", "")
        tags = {m.get("name", "").split(":")[0] for m in _get_json(f"{base}/api/tags").get("models", [])}
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        return [Check("FAIL", "ollama", f"not reachable at {base}: {e}", "install and start Ollama (docs/INSTALL.md, step 3)")]
    if version_tuple(version) < MIN_OLLAMA:
        return [Check("FAIL", "ollama", f"version {version} lacks the System One API", "upgrade Ollama to >= 0.35.1")]
    out = [Check("PASS", "ollama", f"{version} at {base}")]
    for model, severity in ROUTER_MODELS.items():
        present = model in tags
        out.append(Check("PASS" if present else severity, f"router model {model}",
                         "pulled" if present else "missing", "" if present else f"ollama pull {model}"))
    return out


def check_sandbox(p: config.Paths) -> Check:
    """Prove a worker sandbox hides the key directory and has no network (ADR-0032)."""
    if not shutil.which("bwrap"):
        return Check("FAIL", "sandbox", "bubblewrap not found", "sudo apt install bubblewrap")
    probe = f"test ! -e {p.config} && ! (exec 3<>/dev/tcp/1.1.1.1/443) 2>/dev/null && echo sandbox-ok"
    cmd = ["bwrap", "--unshare-user-try", "--ro-bind", "/usr", "/usr", "--ro-bind-try", "/bin", "/bin",
           "--ro-bind-try", "/lib", "/lib", "--ro-bind-try", "/lib64", "/lib64", "--proc", "/proc", "--dev", "/dev",
           "--unshare-net", "--unshare-pid", "--new-session", "--die-with-parent", "bash", "-c", probe]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return Check("FAIL", "sandbox", "bubblewrap probe timed out", "check user namespaces are enabled")
    if "sandbox-ok" in r.stdout:
        return Check("PASS", "sandbox", "key directory invisible, network blocked")
    return Check("FAIL", "sandbox", f"probe failed: {(r.stderr or r.stdout).strip()[:200]}",
                 "enable unprivileged user namespaces for bubblewrap")


def check_harness(p: config.Paths) -> Check:
    version = harness.installed_version(p)
    if version:
        return Check("PASS", "worker harness", f"mini-swe-agent {version} at {harness.home(p)}")
    return Check("FAIL", "worker harness", "not installed", "aios doctor --fix (needs python3-venv)")


def run(env=os.environ) -> list[Check]:
    p = config.paths(env)
    checks = [check_python(),
              check_tool("git", True, "sudo apt install git"),
              check_tool("gh", False, "needed for GitHub targets: https://cli.github.com, then 'gh auth login'"),
              check_key(p, env.get("AIOS_OPENROUTER_URL", "https://openrouter.ai/api/v1")),
              *check_ollama(env.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")),
              check_sandbox(p), check_harness(p)]
    return checks


def main(fix: bool = False) -> int:
    if fix and not harness.installed_version(config.paths()):
        print("installing the pinned worker harness (ADR-0032)...")
        harness.install(config.paths())
    checks = run()
    for c in checks:
        print(f"{c.status:<5} {c.name:<22} {c.detail}" + (f"\n      fix: {c.fix}" if c.fix and c.status != "PASS" else ""))
    failed = sum(c.status == "FAIL" for c in checks)
    print(f"\n{'ready' if not failed else f'{failed} check(s) failed'}")
    return 1 if failed else 0
