"""`aios dispatch`: route a spec, prepare a fresh worktree, run the sandboxed worker, and commit its work.

ADR-0030: aios never writes to the operator's main checkout; each task gets its own worktree on branch aios/<id>.
ADR-0031: the routing decision is made once and stored with the attempt. ADR-0032: the worker runs in the harness.
"""
from __future__ import annotations

import json
import os
import string
import subprocess
import time
from pathlib import Path

from . import catalog, config, gateway, git, harness, router
from . import spec as specs

PROMPT = Path(__file__).with_name("prompts") / "worker.md"
# Build caches are never source, even in repos without ignore rules for them (lesson #3).
CACHES = ("__pycache__/", ".pytest_cache/", ".mypy_cache/", ".ruff_cache/", "node_modules/", "coverage/", ".nyc_output/")
_NOT_CACHES = [f":(exclude,glob)**/{c}**" for c in CACHES] + [":(exclude,glob)**/*.pyc", ":(exclude,glob)**/.coverage"]


class SetupError(RuntimeError):
    """A profile/project setup command failed: infrastructure, never counted against a model."""


def route(s, proj: config.Project | None) -> router.Decision:
    live = catalog.latest(config.paths())
    if live is None:
        raise config.ConfigError("no catalog cached yet; run 'aios models sync'")
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    answers, used = router.classify(s, host=host, model=proj.router_model if proj else "clef-flash",
                                    escalation_model=proj.router_escalation_model if proj else "clef")
    return router.decide(s, answers, roster=catalog.load_roster(), live=live, router=used,
                         max_tier=proj.max_tier if proj else "T3", frontier_auto=proj.frontier_auto if proj else False,
                         deny_vendors=proj.deny_vendors if proj else (),
                         confidence_floor=proj.escalate_below_confidence if proj else 0.6)


def project_id(proj: config.Project) -> str:
    return f"{proj.name}-{git.root_commit(proj.root)[:8]}"


def worker_prompt(spec_text: str, root: Path) -> str:
    agents = root / "AGENTS.md"
    return string.Template(PROMPT.read_text()).substitute(
        agents=agents.read_text() if agents.is_file() else "(none)", spec=spec_text)


def setup(p: config.Paths, wt: Path, comp: config.Component) -> None:
    """Run the component's setup (e.g. `npm ci`) sandboxed: network allowed, but no home directory and no key."""
    cache = p.cache / "pkg"
    cache.mkdir(parents=True, exist_ok=True)
    for command in comp.setup or ():
        args, env = harness.sandbox(p, network=True)
        caches = ["--setenv", "npm_config_cache", str(cache / "npm"), "--setenv", "PIP_CACHE_DIR", str(cache / "pip")]
        cmd = ["bwrap", *args, *caches, "--bind", str(wt), str(wt), "--bind", str(cache), str(cache),
               "--chdir", str(wt / comp.path), "bash", "-c", command]
        r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=1800)
        if r.returncode:
            raise SetupError(f"setup '{command}' failed in {comp.name}: {(r.stdout + r.stderr)[-600:]}")


def dispatch(spec_path: Path, *, dry_run: bool = False, out=print) -> int:
    s = specs.load_spec(spec_path)
    root = config.find_root(spec_path.resolve().parent)
    if root is None:
        raise config.ConfigError(f"{spec_path}: not inside a project with .aios/project.toml (run 'aios init')")
    proj, p = config.load_project(root), config.paths()
    d = route(s, proj)
    out(f"{s.id}: {d.action} · gate {d.gate} · tier {d.tier} · author {d.author} · verifier {d.verifier} ({d.router})")
    for reason in d.reasons:
        out(f"  - {reason}")
    if d.action != "dispatch":
        return 3
    comps = {proj.component_for(f) for f in s.files_allowed}
    if None in comps:
        raise config.ConfigError(f"{s.id}: files_allowed reaches outside every [[components]] path")
    comp = max(comps, key=lambda c: len(c.path))
    remote = proj.remote if git.remote_url(root, proj.remote) else None
    default = proj.default_branch or git.default_branch(root, proj.remote)
    base = f"{remote}/{default}" if remote else default
    wt = p.data / "worktrees" / project_id(proj) / s.id
    out(f"  worktree {wt} · branch {s.branch} from {base} · component {comp.name}")
    if dry_run:
        return 0
    if wt.exists():
        raise config.ConfigError(f"{wt} already exists: {s.id} is in flight")
    if remote:
        git.git(["fetch", "--quiet", remote], root, timeout=300)
    wt.parent.mkdir(parents=True, exist_ok=True)
    git.git(["worktree", "add", "--quiet", "-b", s.branch, str(wt), base], root, timeout=300)
    setup(p, wt, comp)
    run_dir = p.state / project_id(proj) / "runs" / s.id / time.strftime("%Y%m%dT%H%M%S")
    attempt = harness.run(p, wt, d.author, worker_prompt(spec_path.read_text(encoding="utf-8"), root),
                          key=config.load_key(p), run_dir=run_dir, privacy=gateway.privacy_of(proj),
                          cost_limit=s.budget_usd or proj.per_task_usd)
    (run_dir / "attempt.json").write_text(json.dumps({"decision": d.record(), "attempt": attempt.record()}, indent=1))
    if attempt.exit in ("submitted", "limits"):
        git.git(["add", "--all", "--", ".", *_NOT_CACHES], wt)
    if attempt.exit in ("submitted", "limits") and git.git(["diff", "--cached", "--name-only"], wt).strip():
        git.git(["commit", "--quiet", "-m", f"{s.id}: {s.title}\n\nImplemented-By: {d.author} via {attempt.harness}\n"
                 f"Routed: gate {d.gate}, tier {d.tier}, router {d.router}"], wt)
    out(f"  attempt: {attempt.exit} · {attempt.steps} steps · ${attempt.usd:.4f} · {attempt.secs}s"
        + (f"\n  {attempt.summary}" if attempt.exit in ("escalated", "error", "infra") else ""))
    return 0 if attempt.exit == "submitted" else 4
