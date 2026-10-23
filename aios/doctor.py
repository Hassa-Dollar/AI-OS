"""`aios doctor`: is this machine ready? Each failing check says what failed and how to fix it (ADR-0004).

Sections:
  1. The check record and helpers   a result -> Check(status, name, detail, fix); HTTP and version parsing
  2. The checks                     this machine -> one Check (or a list) per part of the setup
  3. First setup, run and print     the answer -> the budget saved; the checks -> rows and an exit code
"""
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


# --- 1. The check record and helpers ----------------------------------------------------
# From: the results the checks report, and the JSON and version strings they read
# To:   Check, the row `aios doctor` prints; the helpers the checks below call


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


# --- 2. The checks ----------------------------------------------------------------------
# From: this machine (PATH, the config dir, OpenRouter, Ollama, bubblewrap, the worker harness)
# To:   one Check (or a list of them) per part of the setup, for run()


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


def fetch_key(p: config.Paths, base: str) -> tuple[dict | None, Check | None]:
    """GET <base>/key once; return (its `data`, None), or (None, a Check saying what went wrong)."""
    try:
        key = config.load_key(p)
        return _get_json(f"{base}/key", {"Authorization": f"Bearer {key}"})["data"], None
    except config.ConfigError as e:
        return None, Check("FAIL", "openrouter key", str(e), "see docs/INSTALL.md, step 2")
    except urllib.error.HTTPError as e:
        e.close()
        return None, Check("FAIL", "openrouter key", f"rejected by OpenRouter (HTTP {e.code})", "create a new key")
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
        return None, Check("FAIL", "openrouter key", f"could not verify: {e}", "check the network, then retry")


def check_key(p: config.Paths, base: str, d: dict | None = None, err: Check | None = None) -> Check:
    """The OpenRouter key: valid, with a credit limit; `d` and `err` come from a shared fetch_key."""
    if d is None and err is None:
        d, err = fetch_key(p, base)
    # the fetch failed, or the key is valid but has no credit limit at all
    if err or d.get("limit") is None:
        return err or Check("FAIL", "openrouter key", "valid, but has no credit limit",
                            "set a credit limit on this key in OpenRouter: it is the hard spend cap")
    left = d.get("limit_remaining")
    return Check("PASS", "openrouter key", f"valid; ${left:.2f} of ${d['limit']:.2f} left" if left is not None
                 else f"valid; limit ${d['limit']:.2f}")


def check_monthly(budget: float | None, d: dict | None) -> Check:
    """The monthly budget: the machine config's budget against the key's limit and reset period."""
    if budget is None:
        return Check("FAIL", "monthly budget", "no monthly budget is set", "run 'aios doctor --fix'")
    limit, reset = (d or {}).get("limit"), (d or {}).get("limit_reset")
    if limit is None or reset != "monthly" or abs(limit - budget) > 0.01:
        return Check("WARN", "monthly budget", f"the key's limit is {limit or 'not set'} ({reset or 'never'} "
                     f"reset); the budget is ${budget:.2f} a month", f"set the key's limit to ${budget} with a monthly reset")
    return Check("PASS", "monthly budget", f"${d.get('usage_monthly') or 0:.2f} of ${budget:.2f} spent this month")


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


# --- 3. First setup, run and print ------------------------------------------------------
# From: the operator, asked at the terminal until the answer is a positive number; the environment
# To:   the budget saved in <config>/config.toml; the printed rows and the exit code


def setup_budget(p: config.Paths, ask=input) -> None:
    """First setup: ask for the monthly budget, save it, and tell the operator to mirror it on the key."""
    if config.load_machine(p).per_month_usd is not None:
        return
    while True:
        try:
            amount = float(ask("How much do you want to spend per month on models, in USD? "))
        except EOFError:
            print(f"There is no terminal to ask in. Write {config.machine_file(p)} by hand:\n\n"
                  "    schema = 1\n\n    [budget]\n    per_month_usd = 20.0\n\n"
                  "Then set your OpenRouter key's credit limit to that same amount, with a monthly reset (https://openrouter.ai/settings/keys).")
            return
        except ValueError:
            amount = 0.0
        if amount > 0:
            break
        print("Enter a positive number of US dollars, e.g. 20")
    config.save_machine(p, config.Machine(amount))
    print(f"Now set your OpenRouter key's credit limit to ${amount} with a monthly reset "
          "(https://openrouter.ai/settings/keys). aios reads that limit to know what is left this month.")


def run(env=os.environ) -> list[Check]:
    p = config.paths(env)
    base = env.get("AIOS_OPENROUTER_URL", "https://openrouter.ai/api/v1")
    d, err = fetch_key(p, base)
    checks = [check_python(),
              check_tool("git", True, "sudo apt install git"),
              check_tool("gh", False, "needed for GitHub targets: https://cli.github.com, then 'gh auth login'"),
              check_key(p, base, d, err), check_monthly(config.load_machine(p).per_month_usd, d),
              *check_ollama(env.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")),
              check_sandbox(p), check_harness(p)]
    return checks


def main(fix: bool = False, ask=input) -> int:
    if fix:
        setup_budget(config.paths(), ask)
    if fix and not harness.installed_version(config.paths()):
        print("installing the pinned worker harness (ADR-0032)...")
        harness.install(config.paths())
    checks = run()
    for c in checks:
        print(f"{c.status:<5} {c.name:<22} {c.detail}" + (f"\n      fix: {c.fix}" if c.fix and c.status != "PASS" else ""))
    failed = sum(c.status == "FAIL" for c in checks)
    print(f"\n{'ready' if not failed else f'{failed} check(s) failed'}")
    return 1 if failed else 0
