"""The gate: what a task branch changed, whether it is in scope, what it added, a cross-family verifier's verdict,
and how much review it needs - decided before anything merges (ADR-0026, ADR-0030, ADR-0031).

Sections:
  1. change set      a worktree and its base -> the files changed and how many lines the branch authored
  2. scope           the change and the spec -> the files out of scope
  3. dependencies    the changed manifest files -> the dependencies the branch added
  4. flags and tier  the change, the spec and the verdict's risk -> what raises the review tier, and the tier
  5. run checks      a component's commands -> each one run in the sandbox, with its exit code and output tail
  6. verify          the diff, the checks and a verifier model -> a verdict, a risk, and a cost
  7. run gate        a spec path -> the record written to the branch, and 0 when the verdict passes else 1
"""
from __future__ import annotations

import json
import string
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import __version__, catalog, config, gateway, records, run
from . import git, harness, review, spec
from .run import CACHES

TIERS = ("AUTO", "OPERATOR", "LEAD", "HUMAN")
LOCKFILES = ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "uv.lock", "Cargo.lock")
LOCKFILE_EXCLUDES = tuple(f":(exclude,glob)**/{n}" for n in LOCKFILES)
RECORD_EXCLUDE = ":(exclude).aios/records/{}.json"


# --- 1. change set ---------------------------------------------------------------------
# From: the task's worktree and the base ref it branched from
# To:   a Changes (files changed, authored lines) for the flags and the verifier
def _excludes(task_id: str | None) -> tuple[str, ...]:
    """Pathspecs that are never part of the change being judged (the task's own record)."""
    return () if task_id is None else (RECORD_EXCLUDE.format(task_id),)
MAX_FILES, MAX_LINES = 12, 350
_REQ_SPLIT = "<>=!~;[ "
_CACHE_NAMES = {c.rstrip("/") for c in CACHES}


@dataclass(frozen=True)
class Changes:
    """The files changed and how many lines the branch authored."""
    files: tuple[str, ...]
    authored_lines: int


def _excluded(path: str) -> bool:
    """Whether `path` is compiled bytecode or sits in a build cache, so it is not source to judge."""
    return path.endswith(".pyc") or any(seg in _CACHE_NAMES for seg in path.split("/")[:-1])


def changes(wt: Path, base: str) -> Changes:
    """The files and the authored line count the branch changed since `base`; lockfiles never count."""
    raw = git.git(["diff", "--name-only", "--no-renames", f"{base}...HEAD"], wt)
    files = tuple(sorted(f for f in raw.splitlines() if f and not _excluded(f)))
    numstat = git.git(["diff", "--numstat", "--no-renames", f"{base}...HEAD"], wt)
    kept = set(files)
    authored = 0
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) < 3 or parts[2] not in kept or Path(parts[2]).name in LOCKFILES:
            continue
        authored += sum(int(n) for n in parts[:2] if n.isdigit())
    return Changes(files, authored)


# --- 2. scope --------------------------------------------------------------------------
# From: the change and the spec's allowed paths
# To:   the files out of scope, for the flags and the gate's own verdict
def out_of_scope(s, task_id: str, files: tuple[str, ...]) -> list[str]:
    """The changed files the spec's paths forbid, apart from the task's own record; one entry per file."""
    return [f for f in files if not spec.path_allowed(s, f) and f != f".aios/records/{task_id}.json"]


# --- 3. dependencies -------------------------------------------------------------------
# From: the changed manifest files and their contents before and after
# To:   the dependencies the branch added, for the dependency-change flag
def _req_name(req: str) -> str:
    """A requirement line's package name, stripped of its version specifiers."""
    idx = next((i for i, ch in enumerate(req) if ch in _REQ_SPLIT), len(req))
    return req[:idx].strip().lower()


def _manifest_names(kind: str, text: str) -> set[str]:
    """The package names one manifest of `kind` (package.json, pyproject.toml, requirements*) declares."""
    if kind == "package.json":
        data = json.loads(text)
        keys = ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
        return {k.lower() for key in keys for k in (data.get(key) or {})}
    if kind == "pyproject.toml":
        proj = tomllib.loads(text).get("project") or {}
        reqs = list(proj.get("dependencies") or [])
        for group in (proj.get("optional-dependencies") or {}).values():
            reqs.extend(group or [])
        return {_req_name(r) for r in reqs if r}
    return {_req_name(line.strip()) for line in text.splitlines()
            if line.strip() and not line.strip().startswith(("#", "-"))}


def added_dependencies(wt: Path, base: str, files: tuple[str, ...]) -> list[str]:
    """The dependency names present in the branch's manifests but not in the base's, sorted."""
    added: set[str] = set()
    for f in files:
        kind = Path(f).name
        if kind not in ("package.json", "pyproject.toml") and not kind.startswith("requirements"):
            continue
        try:
            base_text = git.git(["show", f"{base}:{f}"], wt, timeout=30)
        except git.GitError:
            base_text = ""
        head_text = (wt / f).read_text(encoding="utf-8") if (wt / f).exists() else ""
        added |= _manifest_names(kind, head_text) - _manifest_names(kind, base_text)
    return sorted(added)


# --- 4. flags and tier -----------------------------------------------------------------
# From: the change, the spec, the added dependencies, and the verdict's risk
# To:   the flags that raise the review tier, and the tier itself
def flags(s, files: tuple[str, ...], authored_lines: int, deps_added: list[str], *,
          sensitive_paths: tuple[str, ...] = (), verifier_risk: str | None = None) -> list[tuple[str, str]]:
    """What needs extra review: one (flag name, tier) per dependency, contract, sensitive path, size or risk."""
    out: list[tuple[str, str]] = []
    preapproved = {d.lower() for d in s.deps_preapproved}
    if any(d.lower() not in preapproved for d in deps_added):
        out.append(("dependency-change", "LEAD"))
    if any(f.startswith("architecture/contracts/") or f in s.contracts for f in files):
        out.append(("touches-contract", "LEAD"))
    for sp in sensitive_paths:
        if any(f == sp or (sp.endswith("/") and f.startswith(sp)) for f in files):
            out.append(("sensitive-path", "LEAD"))
            break
    if len(files) > MAX_FILES or authored_lines > MAX_LINES:
        out.append(("large-change", "OPERATOR"))
    if verifier_risk == "high":
        out.append(("verifier-risk-high", "LEAD"))
    return out


def tier(router_gate: str, flag_list: list[tuple[str, str]]) -> str:
    """The highest tier among the router's gate and every flag's tier.

    Fails closed: an unknown tier raises ValueError rather than quietly lowering the review bar.
    """
    if router_gate not in TIERS:
        raise ValueError(f"unknown router gate tier {router_gate!r}; expected one of {TIERS}")
    best = TIERS.index(router_gate)
    for _, t in flag_list:
        if t not in TIERS:
            raise ValueError(f"unknown flag tier {t!r}; expected one of {TIERS}")
        best = max(best, TIERS.index(t))
    return TIERS[best]


# --- 5. run checks ---------------------------------------------------------------------
# From: the component's `checks` in .aios/project.toml
# To:   one (command, exit code, output tail) per check, for the verifier and the record
def run_checks(paths, wt: Path, component, *, runner: Callable = subprocess.run) -> list[tuple[str, int, str]]:
    """Each of the component's checks run in the sandbox; one (command, exit code, output tail) per check."""
    checks = component.checks
    if checks is None:
        raise ValueError(f"component {getattr(component, 'name', '?')!r} has no checks; gate fails closed (ADR-0030)")
    args, env = harness.sandbox(paths, network=False)
    out = []
    for check in checks:
        cmd = ["bwrap", *args, "--bind", str(wt), str(wt), "--chdir", str(wt / component.path), "bash", "-c", check]
        p = runner(cmd, env=env, capture_output=True, text=True, timeout=1800)
        out.append((check, p.returncode, (p.stdout + p.stderr)[-2000:]))
    return out


# --- 6. verify -------------------------------------------------------------------------
# From: the spec text, the diff, the checks' output, and a verifier model through the gateway
# To:   a verdict, a risk, blocking items, a summary, the verifier and the cost, or ValueError
VERIFIER_PROMPT = Path(__file__).with_name("prompts") / "verifier.md"
VERDICTS, RISKS = ("pass", "fail", "needs_decision"), ("low", "medium", "high")
# Reasoning counts against this budget: on this repo's own 32 KB verifier prompt deepseek-v4-pro spent 17,607
# reasoning tokens before answering, and 16,000 starved every provider we tried. 32000 leaves room to answer.
VERIFIER_MAX_TOKENS = 32000
VERDICT_SCHEMA = {"type": "object", "additionalProperties": False,
                  "required": ["verdict", "risk", "blocking", "summary"],
                  "properties": {"verdict": {"type": "string", "enum": list(VERDICTS)},
                                 "risk": {"type": "string", "enum": list(RISKS)},
                                 "blocking": {"type": "array", "items": {"type": "string"}},
                                 "summary": {"type": "string"}}}


def verifier_diff(wt: Path, base: str, limit: int = 60_000, task_id: str | None = None) -> str:
    """The whole diff to judge: build caches, lockfiles and the task's own record are never source."""
    text = git.git(["diff", "--no-ext-diff", f"{base}...HEAD", "--", ".", *LOCKFILE_EXCLUDES, *_excludes(task_id)], wt)
    return text if len(text) <= limit else text[:limit] + "\n[diff truncated]"


def patch_id(wt: Path, base: str, task_id: str | None = None) -> str:
    """git's canonical id for the full diff: a verdict is bound to the exact code it judged, not to a commit hash."""
    text = git.git(["diff", "--no-ext-diff", f"{base}...HEAD", "--", ".", *_excludes(task_id)], wt)
    if not text.strip():
        return ""
    p = subprocess.run(["git", "patch-id", "--stable"], cwd=wt, input=text, capture_output=True, text=True, timeout=60)
    if p.returncode or not p.stdout.strip():
        raise git.GitError(f"git patch-id failed in {wt}: {(p.stderr or p.stdout).strip()}")
    return p.stdout.strip().split(" ")[0]


def _checks_block(checks: list[tuple[str, int, str]]) -> str:
    """Every check as `$ command / exit code / output`, or `(none ran)` when no check ran."""
    return "\n\n".join(f"$ {c}\nexit {code}\n{tail.strip() or '(no output)'}" for c, code, tail in checks) \
        or "(none ran)"


def verify(gw, model: str, spec_text: str, diff_text: str, checks: list[tuple[str, int, str]],
           max_tokens: int | None = VERIFIER_MAX_TOKENS) -> dict:
    """One verifier pass over the diff. Fails closed: a reply outside VERDICT_SCHEMA raises ValueError."""
    if not model:
        raise ValueError("the routing decision has no verifier model; the gate fails closed")
    prompt = string.Template(VERIFIER_PROMPT.read_text(encoding="utf-8")).substitute(
        spec=spec_text, checks=_checks_block(checks), diff=diff_text or "(empty diff)")
    r = gw.chat(model, [{"role": "user", "content": prompt}], schema=VERDICT_SCHEMA, max_tokens=max_tokens)
    v = r.get("json")
    if not isinstance(v, dict):
        raise ValueError(f"{model}: verifier returned no JSON verdict")
    if missing := [k for k in ("verdict", "risk", "blocking", "summary") if k not in v]:
        raise ValueError(f"{model}: verdict missing {', '.join(missing)}")
    for key, allowed in (("verdict", VERDICTS), ("risk", RISKS)):
        if v[key] not in allowed:
            raise ValueError(f"{model}: {key} {v[key]!r} not in {', '.join(allowed)}")
    if not isinstance(v["blocking"], list) or any(not isinstance(b, str) for b in v["blocking"]):
        raise ValueError(f"{model}: 'blocking' must be a list of strings")
    if v["verdict"] == "pass" and v["blocking"]:
        raise ValueError(f"{model}: verdict is pass but blocking is not empty")
    return {"verdict": v["verdict"], "risk": v["risk"], "blocking": list(v["blocking"]), "summary": str(v["summary"]),
            "verifier": model, "usd": float(r.get("usd") or 0.0)}


def _flag_list(proj, s, ch, deps: list[str], scope: list[str], risk: str | None) -> list[tuple[str, str]]:
    """The flags for a change plus one out-of-scope flag per spec violation; a (name, tier) list."""
    fl = flags(s, ch.files, ch.authored_lines, deps, sensitive_paths=proj.sensitive_paths, verifier_risk=risk)
    return fl + ([("out-of-scope", "LEAD")] if scope else [])


# --- 7. run gate -----------------------------------------------------------------------
# From: a spec path, the project, the worktree's runs, the checks and the verifier
# To:   the record committed to the task branch, printed status lines, and 0 on pass else 1
def run_gate(spec_path: Path, *, gw=None, out=print) -> int:
    """`aios gate <spec>`: the deterministic checks (gate-checks), a cross-family verifier verdict, then the record (task-records).

    Returns 0 when the verdict is pass, 1 otherwise.
    """
    s = spec.load_spec(spec_path)
    root = config.find_root(spec_path.resolve().parent)
    if root is None:
        raise config.ConfigError(f"{spec_path}: not inside a project with .aios/project.toml (run 'aios init')")
    proj, paths = config.load_project(root), config.paths()
    base, wt = run.base_ref(proj, root), run.worktree_path(paths, proj, s.id)
    if not wt.exists():
        raise config.ConfigError(f"{wt}: no worktree for {s.id}; dispatch it first")
    runs_dir = paths.state / run.project_id(proj) / "runs" / s.id
    runs = records.load_runs(runs_dir)
    if not runs:
        raise config.ConfigError(f"{runs_dir}: no attempts recorded for {s.id}; dispatch it first")
    d = runs[0]["decision"]
    if d["author_family"] == d["verifier_family"]:
        raise ValueError(f"verifier {d['verifier']} shares the author's family {d['author_family']!r}: "
                         "a cross-family verifier is required")
    comp, ch = run.component_of(proj, s), changes(wt, base)
    if not ch.files:
        raise config.ConfigError(f"{wt}: nothing changed on {s.branch} since {base}")
    scope = out_of_scope(s, s.id, ch.files)
    checks = run_checks(paths, wt, comp)
    if scope or any(code for _, code, _ in checks):
        blocking = [f"out of scope: {f}" for f in scope]
        blocking += [f"check failed (exit {code}): {c}" for c, code, _ in checks if code]
        verdict = {"verdict": "fail", "risk": "high", "blocking": blocking,
                   "summary": "gate failed before verification", "usd": 0.0, "verifier": None}
    else:
        if gw is None:  # a real gate needs the key
            gw = gateway.Gateway(config.load_key(paths), privacy=gateway.privacy_of(proj))
        live = catalog.latest(paths) or []
        spent = sum(float(a["attempt"]["usd"]) for a in runs)
        usd_left = max((s.budget_usd or proj.per_task_usd) - spent, 0.0)
        confirmer = review.pick_confirmer(paths, live, catalog.load_policy(), first=d["verifier"],
                                          exclude_families=(d["author_family"], d["verifier_family"]))
        verdict = review.review(gw, d["verifier"], spec_path.read_text(encoding="utf-8"),
                                verifier_diff(wt, base, task_id=s.id), checks, confirmer=confirmer,
                                max_tokens=lambda m: review.max_tokens_for(m, live, usd_left))
    verdict["patch_id"] = patch_id(wt, base, task_id=s.id)
    verdict["commit"] = git.git(["rev-parse", "HEAD"], wt).strip()
    fl = _flag_list(proj, s, ch, added_dependencies(wt, base, ch.files), scope, verdict["risk"])
    gate_tier = tier(d["gate"], fl)
    record = records.build(s.id, runs, spec_blob=git.git(["hash-object", str(spec_path.resolve())], root).strip(),
                           tool_version=f"aios {__version__}", verdict=verdict, flags=[n for n, _ in fl],
                           gate=gate_tier, summary=verdict["summary"])
    records.write(wt, record)
    git.git(["add", "--", f".aios/records/{s.id}.json"], wt)
    if git.git(["diff", "--cached", "--name-only"], wt).strip():
        git.git(["commit", "--quiet", "-m", f"{s.id}: record (verdict {verdict['verdict']}, gate {gate_tier})"], wt)
    out(f"{s.id}: verdict {verdict['verdict']} ({verdict['risk']}) | gate {gate_tier}"
        f" | flags {', '.join(n for n, _ in fl) or 'none'} | ${record['usd_total']:.4f}")
    for b in verdict["blocking"]:
        out(f"  - {b}")
    return 0 if verdict["verdict"] == "pass" else 1
