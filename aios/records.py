"""Build, write and read the per-task record (`.aios/records/<id>.json`, ADR-0030/0031)."""
from __future__ import annotations

import getpass
import json
import re
from pathlib import Path
from typing import Any

RECORD_SCHEMA = 1
POLICY_VERSION = 1
PATH_REDACTION_PATTERN = re.compile(r"(?<![\w.])/(home|Users|root|tmp|mnt|var)/[^\s\"'\]\)]*", re.IGNORECASE)


def _redact(value: Any, username: str) -> Any:
    if isinstance(value, dict):
        return {k: _redact(v, username) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v, username) for v in value]
    if isinstance(value, str):
        if len(username) >= 3:
            value = value.replace(username, "<user>")
        return PATH_REDACTION_PATTERN.sub("<path>", value)
    return value


def load_runs(runs_dir: Path) -> list[dict]:
    """Parses attempt.json of every direct subdirectory of runs_dir, ordered by name."""
    if not runs_dir.is_dir():
        return []
    runs = []
    for d in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        if (p := d / "attempt.json").is_file():
            with open(p, "r", encoding="utf-8") as f:
                runs.append(json.load(f))
    return runs


def build(task_id: str, runs: list[dict], *, spec_blob: str, tool_version: str, roster_version: str = "",
          verdict: dict | None = None, flags: list[str] | tuple[str, ...] = (), gate: str = "AUTO",
          approval: dict | None = None, summary: str = "", lessons: list[str] | tuple[str, ...] = ()) -> dict:
    """Builds the record from the routing decision and the worker attempts."""
    record: dict[str, Any] = {"record_schema": RECORD_SCHEMA, "task": task_id, "spec_blob": spec_blob,
                              "tool_version": tool_version, "flags": list(flags), "gate": gate,
                              "approval": approval, "summary": summary, "lessons": list(lessons)}
    if runs:
        d = runs[0]["decision"]
        record["routing"] = {"router": d["router"], "answers": d["answers"], "tier": d["tier"],
                             "author": {"model": d["author"], "family": d["author_family"]},
                             "verifier": {"model": d["verifier"], "family": d["verifier_family"]},
                             "gate": d["gate"], "reasons": d["reasons"], "policy_version": POLICY_VERSION,
                             "roster_version": roster_version}
    else:
        record["routing"] = None
    attempts, usd_total = [], 0.0
    for n, run in enumerate(runs, 1):
        a = run["attempt"]
        attempt = {"n": n, "model": a["model"], "harness": a["harness"], "secs": a["secs"], "steps": a["steps"],
                   "usd": a["usd"], "exit": a["exit"]}
        usd_total += a["usd"]
        if n == len(runs) and verdict is not None:
            attempt["verdict"] = verdict
            usd_total += verdict.get("usd", 0.0)
        attempts.append(attempt)
    record["attempts"] = attempts
    record["usd_total"] = round(usd_total, 6)
    return record


def write(worktree: Path, record: dict) -> Path:
    """Writes the redacted record to `<worktree>/.aios/records/<id>.json`."""
    out = worktree / ".aios" / "records"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{record['task']}.json"
    redacted = _redact(record, getpass.getuser())
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(redacted, indent=1, sort_keys=True) + "\n")
    return path


def read(repo: Path, task_id: str) -> dict | None:
    """Reads `.aios/records/<task_id>.json`; returns None if the record is absent."""
    path = repo / ".aios" / "records" / f"{task_id}.json"
    if not path.is_file():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
