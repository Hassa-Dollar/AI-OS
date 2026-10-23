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

# --- 1. Checks -------------------------------------------------------------------
# From: this machine (PATH, the key file, Ollama, bubblewrap, the harness) and one GET <base>/key
# To:   one Check per check, for run() to collect and main() to print
MIN_OLLAMA = (0, 35, 1)
ROUTER_MODELS = {"clef-flash": "FAIL", "clef": "WARN"}  # flash is required; 27B is the optional second opinion
_BWRAP = ["bwrap", "--unshare-user-try", "--ro-bind", "/usr", "/usr", "--ro-bind-try", "/bin", "/bin",
          "--ro-bind-try", "/lib", "/lib", "--ro-bind-try", "/lib64", "/lib64", "--proc", "/proc", "--dev", "/dev",
          "--unshare-net", "--unshare-pid", "--new-session", "--die-with-parent"]


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
    return tuple(int(x) for x in m.groups()) if (m := re.search(r"(\d+)\.(\d+)\.(\d+)", text)) else (0, 0, 0)


def check_python() -> Check:
    ok = (v := sys.version_info) >= (3, 11)
    return Check("PASS" if ok else "FAIL", "python", f"{v.major}.{v.minor}.{v.micro}", "" if ok else "install Python >= 3.11")


def check_tool(name: str, required: bool, fix: str) -> Check:
    path = shutil.which(name)
    if not path: return Check("FAIL" if required else "WARN", name, "not found on PATH", fix)
    if windows_shadowed(path):
        return Check("FAIL", name, f"{path} is a Windows binary", f"install the Linux {name} and put it first in PATH")
    return Check("PASS", name, path)


def fetch_key(p: config.Paths, base: str) -> tuple[dict, Check | None]:
    """GET <base>/key once per run; return its data table, or ({}, a FAIL check) when the key cannot be read."""
    try:
        key = config.load_key(p)
    except config.ConfigError as e: return {}, Check("FAIL", "openrouter key", str(e), "see docs/INSTALL.md, step 2")
    try:
        return _get_json(f"{base}/key", {"Authorization": f"Bearer {key}"})["data"], None
    except urllib.error.HTTPError as e:
        e.close()
        return {}, Check("FAIL", "openrouter key", f"rejected by OpenRouter (HTTP {e.code})", "create a new key")
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
        return {}, Check("FAIL", "openrouter key", f"could not verify: {e}", "check the network, then retry")


def check_key(p: config.Paths, base: str, d: dict | None = None) -> Check:
    """The OpenRouter key: valid, with a credit limit (`d`: a /key response the caller already fetched)."""
    d, err = fetch_key(p, base) if d is None else (d, None)
    if err: return err
    if d.get("limit") is None:
        return Check("FAIL", "openrouter key", "valid, but has no credit limit",
                     "set a credit limit on this key in OpenRouter: it is the hard spend cap")
    left = d.get("limit_remaining")
    return Check("PASS", "openrouter key", f"valid; ${left:.2f} of ${d['limit']:.2f} left" if left is not None
                 else f"valid; limit ${d['limit']:.2f}")


def check_monthly(month: float | None, d: dict) -> Check:
    """The monthly budget in the machine config against the key's limit and its reset period."""
    if month is None: return Check("FAIL", "monthly budget", "no monthly budget is set", "run 'aios doctor --fix'")
    limit, reset = d.get("limit"), d.get("limit_reset")
    if not isinstance(limit, (int, float)) or abs(limit - month) > 0.01 or reset != "monthly":
        return Check("WARN", "monthly budget", f"budget ${month:.2f}, key limit {limit}, resets {reset or 'never'}",
                     f"set the key's limit to ${month} with a monthly reset")
    return Check("PASS", "monthly budget", f"${d.get('usage_monthly') or 0:.2f} of ${month:.2f} spent this month")


def check_ollama(base: str) -> list[Check]:
    try:
        version = _get_json(f"{base}/api/version").get("version", "")
        tags = {m.get("name", "").split(":")[0] for m in _get_json(f"{base}/api/tags").get("models", [])}
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        return [Check("FAIL", "ollama", f"not reachable at {base}: {e}",
                      "install and start Ollama (docs/INSTALL.md, step 3)")]
    if version_tuple(version) < MIN_OLLAMA:
        return [Check("FAIL", "ollama", f"version {version} lacks the System One API", "upgrade Ollama to >= 0.35.1")]
    return [Check("PASS", "ollama", f"{version} at {base}")] + [
        Check("PASS" if (got := m in tags) else s, f"router model {m}", "pulled" if got else "missing",
              "" if got else f"ollama pull {m}") for m, s in ROUTER_MODELS.items()]


def check_sandbox(p: config.Paths) -> Check:
    """Prove a worker sandbox hides the key directory and has no network (ADR-0032)."""
    if not shutil.which("bwrap"): return Check("FAIL", "sandbox", "bubblewrap not found", "sudo apt install bubblewrap")
    probe = f"test ! -e {p.config} && ! (exec 3<>/dev/tcp/1.1.1.1/443) 2>/dev/null && echo sandbox-ok"
    try:
        r = subprocess.run([*_BWRAP, "bash", "-c", probe], capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return Check("FAIL", "sandbox", "bubblewrap probe timed out", "check user namespaces are enabled")
    if "sandbox-ok" in r.stdout: return Check("PASS", "sandbox", "key directory invisible, network blocked")
    return Check("FAIL", "sandbox", f"probe failed: {(r.stderr or r.stdout).strip()[:200]}",
                 "enable unprivileged user namespaces for bubblewrap")


def check_harness(p: config.Paths) -> Check:
    version = harness.installed_version(p)
    if version: return Check("PASS", "worker harness", f"mini-swe-agent {version} at {harness.home(p)}")
    return Check("FAIL", "worker harness", "not installed", "aios doctor --fix (needs python3-venv)")


# --- 2. First setup --------------------------------------------------------------
# From: the operator's answer at the terminal (EOFError when the session is not interactive)
# To:   <config>/config.toml, and the instruction the operator follows in OpenRouter


def _positive(ask) -> float:
    """One answer as a positive float, else 0.0 to ask again; EOFError when the session is not interactive."""
    try: return v if (v := float(ask("How much do you want to spend per month on models, in USD? "))) > 0 else 0.0
    except ValueError: return 0.0


def setup_budget(p: config.Paths, ask=input) -> None:
    """First setup: ask for the monthly budget, save it, then tell the operator to match it on the key."""
    if config.load_machine(p).per_month_usd is not None: return
    try:
        while not (amount := _positive(ask)):
            print("Enter a positive number, e.g. 20")
    except EOFError: return print(f"No monthly budget set. Write {config.machine_file(p)} by hand:\n"
                                  "  schema = 1\n  [budget]\n  per_month_usd = 20.0\n"
                                  "Then set your OpenRouter key's limit to the same amount, monthly reset.")
    config.save_machine(p, config.Machine(amount))
    print(f"Now set your OpenRouter key's credit limit to ${amount} with a monthly reset "
          "(https://openrouter.ai/settings/keys). aios reads that limit to know what is left this month.")


# --- 3. Run and print ------------------------------------------------------------
# From: the checks above, one GET /key, and --fix
# To:   the checks on stdout, the machine config, and the exit code


def run(env=os.environ) -> list[Check]:
    """Every check, sharing one GET /key between the key check and the monthly-budget check."""
    base = env.get("AIOS_OPENROUTER_URL", "https://openrouter.ai/api/v1")
    d, err = fetch_key(p := config.paths(env), base)
    try: month = config.load_machine(p).per_month_usd
    except config.ConfigError: month = None  # a broken machine config is reported by the check below
    return [check_python(), check_tool("git", True, "sudo apt install git"),
            check_tool("gh", False, "needed for GitHub targets: https://cli.github.com, then 'gh auth login'"),
            err or check_key(p, base, d), check_monthly(month, d),
            *check_ollama(env.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")),
            check_sandbox(p), check_harness(p)]


def main(fix: bool = True, ask=input) -> int:
    """Check the machine, do what --fix can do, and print every check; only FAIL counts, 0 means ready."""
    if fix and not harness.installed_version(p := config.paths()):  # p is only read under --fix
        print("installing the pinned worker harness (ADR-0032)...")
        try: harness.install(p)
        except (OSError, subprocess.SubprocessError) as e: print(f"could not install it: {e}")
    if fix: setup_budget(p, ask)
    checks = run()
    for c in checks: print(f"{c.status:<5} {c.name:<22} {c.detail}"
                           + (f"\n      fix: {c.fix}" if c.fix and c.status != "PASS" else ""))
    print(f"\n{'ready' if not (failed := sum(c.status == 'FAIL' for c in checks)) else f'{failed} check(s) failed'}")
    return 1 if failed else 0
