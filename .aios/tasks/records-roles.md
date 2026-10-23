+++
id = "records-roles"
title = "Records: schema 2 with the task's level and, for each role, the model chosen and why"
files_allowed = ["aios/records.py", "tests/test_records.py"]
contracts = ["architecture/contracts/record.schema.md"]
blast_radius = "medium"
kind = "feature"
budget_usd = 0.4
+++

## Goal
ADR-0034 section 8 and the record contract (`record_schema` 2): each record should say which model filled each role,
and why. The router will start providing that in a separate task. This task makes records ready for it, while still
reading the routing decisions written so far.

## Context
- **Standard library only**; ASCII source; fail loud. Follow `AGENTS.md`, including its comment rule.
- `records.build(task_id, runs, ...)` builds `record["routing"]` from `runs[0]["decision"]`. Today it copies
  `decision["tier"]`.
- **Decisions from now on** carry:
  - `level` (`"junior"`, `"mid"` or `"senior"`) in place of `tier`;
  - a `roles` dict, for example
    `{"implementer": {"model", "family", "level", "score", "usd_per_m": [in, out], "est_usd", "why"}, "reviewer": {...}}`.
- **Older decisions**, already stored in local attempt files, have `tier` and no `roles`. Both shapes must work.
- Read `architecture/contracts/record.schema.md`, especially the routing example and the "record_schema 2" rule.

## Required changes
1. **`RECORD_SCHEMA = 2`.**
2. **In `build`, `routing`** gets:
   - `level`: `decision.get("level")`, or else `decision.get("tier")`;
   - `roles`: `decision.get("roles") or {}`.

   Keep every existing routing key (`router`, `answers`, `author`, `verifier`, `gate`, `reasons`, `policy_version`
   and `roster_version`). Drop `tier` from routing; `level` replaces it.
3. **`read`** still returns older records unchanged. No migration happens on read.

## Acceptance criteria
- `tests/test_records.py` covers:
  - a decision with `level` and `roles`, which ends up in `routing`;
  - an old decision with `tier` and no `roles`, which gives `level` equal to that tier and `roles == {}`;
  - `record_schema == 2`;
  - every existing behaviour still holding: redaction, usd totals, the verdict on the last attempt, and no mutation
    of the caller's dict.
- `python3 -m unittest discover -s tests -t .` passes.
- `aios/records.py` has at most 85 non-blank, non-comment lines.

## Out of scope
The router, and any other file.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
