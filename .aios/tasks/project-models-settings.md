+++
id = "project-models-settings"
title = "Project settings: a [models] table of its own, and the old tier settings retired"
files_allowed = ["aios/config.py", "aios/run.py", "aios/cli.py", ".aios/project.toml", "tests/test_config.py", "tests/test_cli.py"]
contracts = ["architecture/contracts/project.schema.md", "architecture/contracts/models.schema.md"]
depends_on = ["roster-removal"]
blast_radius = "medium"
kind = "refactor"
budget_usd = 0.5
+++

## Goal
ADR-0034 removed the model tiers. A project's `.aios/project.toml` should now be able to:
- carry its own model policy, in a `[models]` table that uses the same keys as `aios/models.toml`, for example its
  own level thresholds or a measured block;
- stop using `max_tier` and `frontier_auto`, which no longer mean anything.

Read the project contract's `[models]` note and the models contract.

## Context
- **Standard library only**; ASCII source; fail loud. Follow `AGENTS.md`: the comment rule (keep the section maps
  true), and never compress code to fit a line cap.
- **`aios/config.py`:**
  - `TIERS = ("T1", "T2", "T3")`;
  - `Project` has `max_tier` and `frontier_auto`;
  - `load_project` reads `[privacy] max_tier` and `[routing] frontier_auto`, and rejects unknown keys and sections.
- **`catalog.load_policy(path=DEFAULT_POLICY, project=None)`:** `project` is a dict that uses the same keys as
  `models.toml` (`levels`, `block`, `family`). It is validated, and merged in.
- **`run.route`** calls `catalog.load_policy()` with no project table.
- **`aios init`** (`cli.PROJECT_TEMPLATE`) still writes `max_tier = "T3"` and a `[routing]` `frontier_auto` line.
- **AI-OS's own `.aios/project.toml`** still has both old keys.

## Required changes
1. **`aios/config.py`:**
   - Remove `TIERS`, `Project.max_tier` and `Project.frontier_auto`.
   - `load_project` still **accepts** `max_tier` and `frontier_auto` but ignores them. It prints one warning line to
     stderr per key, naming the key and saying it was retired by ADR-0034, so that existing projects keep loading.
   - It reads an optional `[models]` table into a new field, `Project.models: dict | None` (the raw dict). Its
     validation is done by `catalog.load_policy`.
2. **`aios/run.py`:** `route` calls `catalog.load_policy(project=proj.models if proj else None)`.
3. **`aios/cli.py`, `PROJECT_TEMPLATE`:**
   - Remove `max_tier` and the `frontier_auto` line. Keep `[routing]` only if other keys remain in the template;
     otherwise drop the section.
   - Add a commented example:
     ```
     # [models]                       # optional: this project's model policy (contract: models.schema.md)
     # levels = { junior = 40, mid = 45, senior = 52 }
     ```
4. **`.aios/project.toml`:** remove `max_tier` and `frontier_auto` from AI-OS's own project file. Keep the
   operator's comment on `per_task_usd`, and every other line.
5. **Tests:**
   - `tests/test_config.py` covers:
     - a `[models]` table being read;
     - the old keys being accepted with one warning each;
     - unknown keys still being rejected.
   - `tests/test_cli.py`: `aios init` no longer writes the old keys.

## Acceptance criteria
- `python3 -m unittest discover -s tests -t .` passes.
- Loading AI-OS's own project file prints no warning about retired keys. Check it with
  `python3 -c "from pathlib import Path; from aios import config; config.load_project(Path('.'))"`.
- `aios/config.py` has at most 200 non-blank, non-comment lines.

## Out of scope
The model choice itself, budgets, and any other file.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
