"""`aios dispatch` and `aios fix`: prepare a worktree, run the sandboxed worker there, and commit its work.

ADR-0030: aios never writes to the operator's main checkout; each task gets its own worktree on branch aios/<id>.
ADR-0031: the routing decision is made once and stored with the attempt; its rule 5 is the fix-round ladder.
ADR-0032/0034: the worker runs in the harness; the implementer and reviewer roles come from the whole catalog.

Sections:
  1. Route       a spec + the project -> one Decision (Clef's answers, then the decision table)
  2. Prepare     the project and its component -> the worktree path, the base ref and a sandboxed setup
                (raises SetupError when the setup command fails)
  3. Budget      the spent money + the four caps -> the money left for the next attempt (raises BudgetError)
  4. Dispatch    a spec file -> a worktree, one attempt, and a commit on the task branch
  5. Fix         the task's record + the fix-round ladder -> one more attempt on the same worktree
"""
from __future__ import annotations

import datetime as dt
import json
import os
import string
import subprocess
from pathlib import Path

from . import catalog, config, gateway, git, harness, records, router
from . import spec as specs

PROMPT = Path(__file__).with_name("prompts") / "worker.md"
# Build caches are never source, even in repos without ignore rules for them (lesson 3 in docs/lessons.md).
CACHES = ("__pycache__/", ".pytest_cache/", ".mypy_cache/", ".ruff_cache/", "node_modules/", "coverage/", ".nyc_output/")
_NOT_CACHES = [f":(exclude,glob)**/{c}**" for c in CACHES] + [":(exclude,glob)**/*.pyc", ":(exclude,glob)**/.coverage"]


# --- 1. Route ----------------------------------------------------------------------------
# From: the spec file, the project's [routing] and [privacy], and the cached catalog
# To:   one router.Decision, printed by dispatch and stored with the attempt
def _gateway(p: config.Paths) -> gateway.Gateway | None:
    """The OpenRouter client when a key is stored, else None (the router then works from the cache alone)."""
    if not p.credentials.exists():
        return None
    return gateway.Gateway(config.load_key(p), base=os.environ.get("AIOS_OPENROUTER_URL", gateway.BASE))


def route(s, proj: config.Project | None) -> router.Decision:
    """Classify the spec, then decide its level and its two roles from the live catalog (ADR-0034)."""
    from . import calibrate  # imported late: gate imports CACHES from this module, so a module-level import cycles
    p = config.paths()
    live = catalog.latest(p, gateway=_gateway(p))
    if live is None:
        raise config.ConfigError("no catalog cached yet; run 'aios models sync'")
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    answers, used = router.classify(s, host=host, model=proj.router_model if proj else "clef-flash",
                                    escalation_model=proj.router_escalation_model if proj else "clef")
    return router.decide(s, answers, live=live,
                         policy=catalog.load_policy(project=proj.models if proj else None), router=used,
                         deny_vendors=proj.deny_vendors if proj else (),
                         confidence_floor=proj.escalate_below_confidence if proj else 0.6,
                         reviewer_ok=lambda m: calibrate.passed(p, m))


# --- 2. Prepare --------------------------------------------------------------------------
# From: the project (components, remote, default branch) and the spec's id
# To:   a fresh worktree under <data>/worktrees with the component's setup run inside it
def project_id(proj: config.Project) -> str:
    """The state directory name for a project: its name plus the first 8 hex of its root commit."""
    return f"{proj.name}-{git.root_commit(proj.root)[:8]}"


def worker_prompt(spec_text: str, root: Path) -> str:
    """The worker's task text: the repo's AGENTS.md around the spec."""
    agents = root / "AGENTS.md"
    return string.Template(PROMPT.read_text()).substitute(
        agents=agents.read_text() if agents.is_file() else "(none)", spec=spec_text)


def base_ref(proj: config.Project, root: Path) -> str:
    """The ref a task branch starts from: `<remote>/<default>` when the remote exists, else the default branch."""
    remote = proj.remote if git.remote_url(root, proj.remote) else None
    default = proj.default_branch or git.default_branch(root, proj.remote)
    return f"{remote}/{default}" if remote else default


def worktree_path(p: config.Paths, proj: config.Project, task_id: str) -> Path:
    """One worktree per task, keyed by project + task id (ADR-0030)."""
    return p.data / "worktrees" / project_id(proj) / task_id


def component_of(proj: config.Project, spec) -> config.Component:
    """The component owning every file in spec.files_allowed; raises if none covers them all."""
    comps = {proj.component_for(f) for f in spec.files_allowed}
    if None in comps:
        raise config.ConfigError(f"{spec.id}: files_allowed reaches outside every [[components]] path")
    return max(comps, key=lambda c: len(c.path))


class SetupError(RuntimeError):
    """A profile/project setup command failed: infrastructure, never counted against a model."""


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


# --- 3. Budget ----------------------------------------------------------------------------
# From: the OpenRouter key's usage, the spec's/project's caps and the task's record
# To:   the money left for the next attempt, or a BudgetError when every cap is spent
class BudgetError(RuntimeError):
    """A budget cap is exhausted: no attempt may start."""


MIN_ATTEMPT_USD = 0.05


def task_spent(runs: list[dict], record: dict | None) -> float:
    """The total USD a task has already cost: its attempts plus the record's last verdict."""
    verdict = 0.0
    if record and record.get("attempts"):
        verdict = float(record["attempts"][-1].get("verdict", {}).get("usd") or 0.0)
    attempts = sum(float(r.get("attempt", {}).get("usd") or 0.0) for r in runs)
    return round(attempts + verdict, 6)


def budget_left(gw, proj, s, machine, runs: list[dict], record: dict | None) -> float:
    """The smallest remaining cap for the next attempt, or BudgetError when every cap is spent."""
    info = gw.key_info()
    spent = task_spent(runs, record)
    task_cap = s.budget_usd or proj.per_task_usd
    caps = [(task_cap - spent, "the task's budget", spent, task_cap),
            (proj.per_day_usd - info["usage_daily"], "the day's budget", info["usage_daily"], proj.per_day_usd)]
    if machine.per_month_usd is not None:
        caps.append((machine.per_month_usd - info["usage_monthly"], "the month's budget",
                     info["usage_monthly"], machine.per_month_usd))
    if info.get("limit_remaining") is not None:
        caps.append((info["limit_remaining"], "the key limit", None, None))
    left, name, used, cap = min(caps)
    if left < MIN_ATTEMPT_USD:
        tail = f" (${used:.2f} of ${cap:.2f})" if cap is not None else f" (${left:.2f} left)"
        raise BudgetError(f"{s.id}: {name} is spent{tail}")
    return round(left, 4)
# --- 4. Dispatch --------------------------------------------------------------------------
# From: the spec file, the routing decision and the worker attempt
# To:   the printed decision, a commit on the task branch, and the attempt's record
def _project(spec_path: Path) -> tuple:
    """The spec, its project, the machine's paths and the repo root; raises outside every project."""
    s = specs.load_spec(spec_path)
    root = config.find_root(spec_path.resolve().parent)
    if root is None:
        raise config.ConfigError(f"{spec_path}: not inside a project with .aios/project.toml (run 'aios init')")
    return s, config.load_project(root), config.paths(), root


def _run(p, proj, s, wt: Path, model: str, prompt: str, left: float, decision: dict, subject: str) -> harness.Attempt:
    """One worker attempt in a fresh run dir, saved with the decision, then its work staged and committed."""
    run_dir = p.state / project_id(proj) / "runs" / s.id / dt.datetime.now().strftime("%Y%m%dT%H%M%S-%f")
    a = harness.run(p, wt, model, prompt, key=config.load_key(p), run_dir=run_dir,
                    privacy=gateway.privacy_of(proj), cost_limit=left)
    (run_dir / "attempt.json").write_text(json.dumps({"decision": decision, "attempt": a.record()}, indent=1))
    if a.exit in ("submitted", "limits"):
        git.git(["add", "--all", "--", ".", *_NOT_CACHES], wt)
        if git.git(["diff", "--cached", "--name-only"], wt).strip():
            git.git(["commit", "--quiet", "-m", f"{s.id}: {subject}\n\nImplemented-By: {model} via {a.harness}\n"
                     f"Routed: gate {decision['gate']}, level {decision['level']}, router {decision['router']}"], wt)
    return a


def dispatch(spec_path: Path, *, dry_run: bool = False, gw=None, out=print) -> int:
    """`aios dispatch <spec>`: route it, prepare the worktree, run one worker attempt and commit its work."""
    s, proj, p, root = _project(spec_path)
    d = route(s, proj)
    out(f"{s.id}: {d.action} | gate {d.gate} | level {d.level} | implementer {d.author} | reviewer {d.verifier}"
        f" ({d.router})")
    for reason in d.reasons:
        out(f"  - {reason}")
    if d.action != "dispatch":
        return 3
    comp = component_of(proj, s)
    base = base_ref(proj, root)
    wt = worktree_path(p, proj, s.id)
    out(f"  worktree {wt} | branch {s.branch} from {base} | component {comp.name}")
    if dry_run:
        return 0
    gw = gw or gateway.Gateway(config.load_key(p), privacy=gateway.privacy_of(proj))
    runs_dir = p.state / project_id(proj) / "runs" / s.id
    left = budget_left(gw, proj, s, config.load_machine(p), records.load_runs(runs_dir), records.read(wt, s.id))
    out(f"  budget: ${left:.4f} for this attempt")
    if wt.exists():
        raise config.ConfigError(f"{wt} already exists: {s.id} is in flight")
    if git.remote_url(root, proj.remote):  # base_ref() folded the remote into the ref
        git.git(["fetch", "--quiet", proj.remote], root, timeout=300)
    wt.parent.mkdir(parents=True, exist_ok=True)
    git.git(["worktree", "add", "--quiet", "-b", s.branch, str(wt), base], root, timeout=300)
    setup(p, wt, comp)
    attempt = _run(p, proj, s, wt, d.author, worker_prompt(spec_path.read_text(encoding="utf-8"), root), left,
                   d.record(), s.title)
    out(f"  attempt: {attempt.exit} | {attempt.steps} steps | ${attempt.usd:.4f} | {attempt.secs}s"
        + (f"\n  {attempt.summary}" if attempt.exit in ("escalated", "error", "infra") else ""))
    return 0 if attempt.exit == "submitted" else 4


# --- 5. Fix -------------------------------------------------------------------------------
# From: the task's runs and committed record, the live catalog and the fix-round ladder (ADR-0031 rule 5)
# To:   one more attempt on the same worktree, committed, and 0 when it submitted else 4
def fix(spec_path: Path, *, review: Path | None = None, model: str | None = None, gw=None, out=print) -> int:
    """`aios fix <spec>`: the next worker attempt on the same worktree, the ladder choosing who runs it."""
    s, proj, p, root = _project(spec_path)
    wt = worktree_path(p, proj, s.id)
    if not wt.exists():
        raise config.ConfigError(f"{s.id}: {wt}: no worktree; dispatch it first")
    runs = records.load_runs(p.state / project_id(proj) / "runs" / s.id)
    if not runs:
        raise config.ConfigError(f"{s.id}: no attempts recorded; dispatch it first")
    decision, record = runs[0]["decision"], records.read(wt, s.id)
    if review is not None:  # the Lead's own review, or the decision the reviewer asked for
        text, label = "## Lead review\n\n" + review.read_text(encoding="utf-8"), "Lead review"
    else:
        if record is None:
            raise config.ConfigError(f"{s.id}: no record committed yet; run 'aios gate' first")
        v = record["attempts"][-1]["verdict"]
        if v["verdict"] == "pass":
            raise config.ConfigError(f"{s.id}: the review passed; nothing to fix")
        if v["verdict"] == "needs_decision":
            raise ValueError(f"{s.id}: the reviewer needs a decision; that goes to the Lead. Re-run with --review FILE")
        items = "\n".join(f"- {b}" for b in (v.get("blocking") or ()))
        text, label = f"## Review: fail ({v.get('risk')})\n\n{items}\n\n{v.get('summary', '')}", "review: fail"
    live = catalog.latest(p) or ()  # dispatch already needed a cached catalog; an empty one has no candidate
    policy = catalog.load_policy(project=proj.models)
    fam = decision["verifier_family"]  # a fix round never repeats the reviewer's family
    n = max(sum(1 for r in runs if r["attempt"]["exit"] != "infra"), 1)  # infra attempts never count
    if n >= 4:
        raise config.ConfigError(f"{s.id}: 4 attempts used; the operator and the Lead decide what happens next")
    if model:  # the Lead's override: any implementer candidate, at any level
        pool = catalog.candidates(live, role="implementer", level=None, policy=policy, exclude_families=(fam,))
        if not any(c.id == model for c in pool):
            raise ValueError(f"{s.id}: {model} is not an implementer candidate outside the reviewer's family {fam!r}")
        author = model
    elif n == 1:  # fix round 1: the same model that just failed, with the review appended
        author = decision["author"]
    else:
        levels = catalog.LEVELS
        level = decision["level"] if n < 3 else levels[min(levels.index(decision["level"]) + 1, len(levels) - 1)]
        used = {r["attempt"]["model"] for r in runs}
        pool = catalog.candidates(live, role="implementer", level=level, policy=policy, exclude_families=(fam,))
        author = next((c.id for c in pool if c.id not in used), None)
        if author is None:
            raise config.ConfigError(f"{s.id}: no unused implementer at {level}; the Lead decides")
    gw = gw or gateway.Gateway(config.load_key(p), privacy=gateway.privacy_of(proj))
    left = budget_left(gw, proj, s, config.load_machine(p), runs, record)
    prompt = worker_prompt(spec_path.read_text(encoding="utf-8"), root) + "\n\n" + text
    attempt = _run(p, proj, s, wt, author, prompt, left, decision, f"fix round {n} ({label})")
    if attempt.exit == "infra":  # infrastructure is never the model's fault: one retry, never counted
        attempt = _run(p, proj, s, wt, author, prompt, left, decision, f"fix round {n} ({label})")
    out(f"{s.id}: fix round {n} | {author} | {label}")
    out(f"  attempt: {attempt.exit} | {attempt.steps} steps | ${attempt.usd:.4f} | {attempt.secs}s")
    return 0 if attempt.exit == "submitted" else 4
