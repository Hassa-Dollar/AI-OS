"""Deterministic gate checks: what a task branch changed, whether it is in scope, what it added, and how much
review it needs â decided before any model sees the diff (ADR-0026, ADR-0030, ADR-0031)."""
from __future__ import annotations

import json
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import git, harness, spec
from .run import CACHES

TIERS = ("AUTO", "OPERATOR", "LEAD", "HUMAN")
LOCKFILES = ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "uv.lock", "Cargo.lock")
MAX_FILES, MAX_LINES = 12, 350
_REQ_SPLIT = "<>=!~;[ "
_CACHE_NAMES = {c.rstrip("/") for c in CACHES}


@dataclass(frozen=True)
class Changes:
    files: tuple[str, ...]
    authored_lines: int


def _excluded(path: str) -> bool:
    return path.endswith(".pyc") or any(seg in _CACHE_NAMES for seg in path.split("/")[:-1])


def changes(wt: Path, base: str) -> Changes:
    raw = git.git(["diff", "--name-only", f"{base}...HEAD"], wt)
    files = tuple(sorted(f for f in raw.splitlines() if f and not _excluded(f)))
    numstat = git.git(["diff", "--numstat", f"{base}...HEAD"], wt)
    kept = set(files)
    authored = 0
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) < 3 or parts[2] not in kept or Path(parts[2]).name in LOCKFILES:
            continue
        authored += sum(int(n) for n in parts[:2] if n.isdigit())
    return Changes(files, authored)


def out_of_scope(s, task_id: str, files: tuple[str, ...]) -> list[str]:
    return [f for f in files if not spec.path_allowed(s, f) and f != f".aios/records/{task_id}.json"]


def _req_name(req: str) -> str:
    idx = next((i for i, ch in enumerate(req) if ch in _REQ_SPLIT), len(req))
    return req[:idx].strip().lower()


def _manifest_names(kind: str, text: str) -> set[str]:
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
    added: set[str] = set()
    for f in files:
        kind = Path(f).name
        if kind not in ("package.json", "pyproject.toml") and not kind.startswith("requirements"):
            continue
        try:
            base_text = git.git(["show", f"{base}:{f}"], wt, timeout=30)
        except git.GitError:
            base_text = ""
        head_text = (wt / f).read_text(encoding="utf-8")
        added |= _manifest_names(kind, head_text) - _manifest_names(kind, base_text)
    return sorted(added)


def flags(s, files: tuple[str, ...], authored_lines: int, deps_added: list[str], *,
          sensitive_paths: tuple[str, ...] = (), verifier_risk: str | None = None) -> list[tuple[str, str]]:
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
    best = TIERS.index(router_gate) if router_gate in TIERS else 0
    for _, t in flag_list:
        if t in TIERS:
            best = max(best, TIERS.index(t))
    return TIERS[best]


def run_checks(paths, wt: Path, component, *, runner: Callable = subprocess.run) -> list[tuple[str, int, str]]:
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
