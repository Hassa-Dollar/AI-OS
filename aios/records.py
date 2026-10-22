from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import getpass

RECORD_SCHEMA = 1
PATH_REDACTION_PATTERN = re.compile(r'(?<![\w.])/(home|Users|root|tmp|mnt|var)/[^\s"\'\]\)]*', re.IGNORECASE)

def _redact_string(s: str, username: str) -> str:
    s = PATH_REDACTION_PATTERN.sub('<path>', s)
    if len(username) >= 3:
        s = s.replace(username, '<user>')
    return s

def _redact_record(record: dict, username: str) -> dict:
    if isinstance(record, dict):
        return {k: _redact_record(v, username) for k, v in record.items()}
    if isinstance(record, list):
        return [_redact_record(item, username) for item in record]
    if isinstance(record, str):
        return _redact_string(record, username)
    return record

def load_runs(runs_dir: Path) -> list[dict]:
    """Parses attempt.json of every direct subdirectory of runs_dir, ordered by name."""
    if not runs_dir.is_dir():
        return []
    runs = []
    for d in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        p = d / "attempt.json"
        if p.is_file():
            try:
                with open(p) as f:
                    runs.append(json.load(f))
            except (IOError, json.JSONDecodeError):
                continue
    return runs

def build(task_id: str, runs: list[dict], *, spec_blob: str, tool_version: str, roster_version: str = "",
          verdict: Optional[dict] = None, flags: List[str] | tuple = (), gate: str = "AUTO",
          approval: Optional[dict] = None, summary: str = "", lessons: List[str] | tuple = ()) -> dict:
    """Builds the task record from routing decision and worker attempts."""
    record: dict[str, Any] = {
        "record_schema": RECORD_SCHEMA, "task": task_id, "spec_blob": spec_blob, "tool_version": tool_version,
    }
    if runs:
        d = runs[0].get("decision", {})
        record["routing"] = {
            "router": d.get("router"), "answers": d.get("answers"), "tier": d.get("tier"),
            "author": d.get("author"), "verifier": d.get("verifier"), "gate": d.get("gate"),
            "reasons": d.get("reasons"), "policy_version": 1, "roster_version": roster_version,
        }
    else:
        record["routing"] = None

    attempts, usd_total = [], 0.0
    for i, run in enumerate(runs):
        att = run.get("attempt", {})
        attempts.append({
            "n": i + 1, "model": att.get("model"), "harness": att.get("harness"), "secs": att.get("secs"),
            "steps": att.get("steps"), "usd": att.get("usd", 0.0), "exit": att.get("exit"),
        })
        usd_total += att.get("usd", 0.0)
        if i == len(runs) - 1 and verdict is not None:
            attempts[-1]["verdict"] = verdict
            usd_total += verdict.get("usd", 0.0)
    record["attempts"] = attempts
    record["usd_total"] = round(usd_total, 6)
    record["flags"] = list(flags)
    record["gate"] = gate
    record["approval"] = approval
    record["summary"] = summary
    record["lessons"] = list(lessons)
    return record

def write(worktree: Path, record: dict) -> Path:
    """Writes the redacted record to <worktree>/.aios/records/<id>.json."""
    username = getpass.getuser()
    out_dir = worktree / ".aios" / "records"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{record['task']}.json"
    redacted = _redact_record(record.copy(), username)
    with open(out_path, "w") as f:
        json.dump(redacted, f, indent=1, sort_keys=True)
        f.write("\n")
    return out_path

def read(repo: Path, task_id: str) -> Optional[dict]:
    """Reads .aios/records/<task_id>.json from repo, returns None if missing."""
    p = repo / ".aios" / "records" / f"{task_id}.json"
    if not p.is_file():
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return None
