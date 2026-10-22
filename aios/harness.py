"""The worker harness: mini-swe-agent inside a bubblewrap sandbox (ADR-0032).

The model loop runs in the harness process. Every command the model issues runs inside bubblewrap with no network,
no home directory, no key and its own PID namespace. The task text travels in the generated config, never in argv
(lesson #1: a model's `pkill -f` once matched a prompt passed on the command line and killed its own harness).
"""
from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
import time
from pathlib import Path

from .config import Paths

LOCK = Path(__file__).with_name("harness.lock")
SYSTEM_RO = ["--ro-bind", "/usr", "/usr", "--ro-bind-try", "/bin", "/bin", "--ro-bind-try", "/lib", "/lib",
             "--ro-bind-try", "/lib64", "/lib64", "--ro-bind", "/etc", "/etc"]
INFRA = ("API", "RateLimit", "Authentication", "ConnectionError")  # exit statuses that are not the model's fault


class HarnessError(RuntimeError):
    """The harness is missing or could not be started."""


@dataclasses.dataclass
class Attempt:
    exit: str  # submitted | limits | escalated | error | infra
    model: str
    steps: int
    usd: float
    secs: int
    summary: str
    harness: str

    def record(self) -> dict:
        return dataclasses.asdict(self)


def home(p: Paths) -> Path:
    return p.data / "harness"


def installed_version(p: Paths) -> str | None:
    hits = sorted((home(p) / "lib").glob("python3*/site-packages/mini_swe_agent-*.dist-info"))
    return hits[-1].name.removesuffix(".dist-info").split("-", 1)[1] if hits else None


def install(p: Paths) -> str | None:
    """Create the harness venv and install the exact locked set (no resolution: --no-deps)."""
    subprocess.run([sys.executable, "-m", "venv", str(home(p))], check=True, timeout=300)
    subprocess.run([str(home(p) / "bin" / "pip"), "install", "--quiet", "--disable-pip-version-check", "--no-deps",
                    "-r", str(LOCK)], check=True, timeout=1800)
    return installed_version(p)


def sandbox(p: Paths, *, network: bool) -> tuple[list[str], dict]:
    """bubblewrap arguments and the environment inside. Workers never get network; setup steps do (no home, no key).

    `--clearenv` matters: bubblewrap otherwise hands the parent's environment (which holds the harness's API key)
    to every sandboxed command. Only the variables set here (and any the caller adds with --setenv) get through.
    """
    args = ["--unshare-user-try", "--die-with-parent", "--new-session", "--unshare-pid", "--clearenv", *SYSTEM_RO,
            "--tmpfs", "/tmp", "--proc", "/proc", "--dev", "/dev"]
    args += ["--ro-bind-try", "/mnt/wsl/resolv.conf", "/mnt/wsl/resolv.conf"] if network else ["--unshare-net"]
    path = ["/usr/local/bin", "/usr/bin", "/bin"]
    toolchains = p.data / "toolchains"  # aios-managed runtimes (e.g. Node): read-only, nothing secret lives there
    if toolchains.is_dir():
        args += ["--ro-bind", str(toolchains), str(toolchains)]
        path = sorted({str(d.resolve()) for d in toolchains.glob("*/bin") if d.is_dir()}) + path
    env = {"PATH": ":".join(path), "HOME": "/tmp", "LANG": "C.UTF-8"}
    return args + [x for k, v in env.items() for x in ("--setenv", k, v)], env


def _mini_yaml(p: Paths) -> Path:
    hits = sorted((home(p) / "lib").glob("python3*/site-packages/minisweagent/config/mini.yaml"))
    if not hits:
        raise HarnessError("harness not installed; run 'aios doctor --fix'")
    return hits[-1]


def _instance_template(p: Paths) -> str:
    code = "import json,sys,yaml; print(json.dumps(yaml.safe_load(open(sys.argv[1]))['agent']['instance_template']))"
    out = subprocess.run([str(home(p) / "bin" / "python"), "-c", code, str(_mini_yaml(p))],
                         capture_output=True, text=True, check=True, timeout=60).stdout
    template = json.loads(out)
    if "{{task}}" not in template:
        raise HarnessError("unexpected mini-swe-agent template: no {{task}} slot")
    return template


def run(p: Paths, ws: Path, model: str, task_text: str, *, key: str, run_dir: Path, privacy: dict,
        cost_limit: float, step_limit: int = 60, timeout_s: int = 1800, cmd_timeout: int = 180) -> Attempt:
    version = f"mini-swe-agent {installed_version(p)}"
    run_dir.mkdir(parents=True, exist_ok=True)
    args, inside = sandbox(p, network=False)
    template = _instance_template(p).replace("{{task}}", "\n{% raw %}" + task_text + "{% endraw %}\n")
    cfg = {"agent": {"step_limit": step_limit, "cost_limit": cost_limit, "mode": "yolo", "instance_template": template},
           "model": {"model_class": "openrouter", "model_name": model, "model_kwargs": {"provider": privacy}},
           "environment": {"environment_class": "bubblewrap", "cwd": str(ws), "timeout": cmd_timeout,
                           "wrapper_args": args, "env": inside | {"PAGER": "cat", "TQDM_DISABLE": "1"}}}
    (run_dir / "cfg.yaml").write_text(json.dumps(cfg))  # JSON is YAML; mini only accepts *.yaml paths
    env = {"PATH": "/usr/bin:/bin", "HOME": str(run_dir), "LANG": "C.UTF-8", "OPENROUTER_API_KEY": key,
           "MSWEA_CONFIGURED": "true", "MSWEA_GLOBAL_CONFIG_DIR": str(run_dir / "mswea")}
    cmd = [str(home(p) / "bin" / "mini"), "-c", str(_mini_yaml(p)), "-c", str(run_dir / "cfg.yaml"),
           "-t", "(see the task above)", "-y", "--exit-immediately", "-o", str(run_dir / "traj.json")]
    start = time.time()
    try:
        with open(run_dir / "harness.log", "w") as log:
            subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                           timeout=timeout_s)
    except subprocess.TimeoutExpired:
        a = parse(run_dir / "traj.json", model, int(time.time() - start), version)
        return dataclasses.replace(a, exit="limits", summary="wall-clock limit reached")
    return parse(run_dir / "traj.json", model, int(time.time() - start), version)


def parse(traj: Path, model: str, secs: int, version: str) -> Attempt:
    """Read mini-swe-agent's trajectory: exit status, exact $ (OpenRouter usage.cost), steps, ESCALATE requests."""
    if not traj.exists():
        return Attempt("infra", model, 0, 0.0, secs, "the harness produced no trajectory", version)
    t = json.loads(traj.read_text())
    info, msgs = t.get("info", {}), t.get("messages", [])
    stats = info.get("model_stats", {})
    final = next((str(m.get("content") or "") for m in reversed(msgs) if m.get("role") == "assistant"), "")
    text = f"{info.get('submission') or ''}\n{final}"
    escalation = next((ln.strip() for ln in text.splitlines() if ln.strip().startswith("ESCALATE:")), None)
    status = str(info.get("exit_status") or "")
    if escalation:
        exit_ = "escalated"
    elif status in ("Submitted", "LimitsExceeded"):
        exit_ = {"Submitted": "submitted", "LimitsExceeded": "limits"}[status]
    else:
        exit_ = "infra" if any(word in status for word in INFRA) else "error"
    return Attempt(exit_, model, int(stats.get("api_calls") or 0), round(float(stats.get("instance_cost") or 0), 6),
                   secs, (escalation or final or status)[-500:], version)
