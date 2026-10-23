+++
id = "roster-removal"
title = "Remove the fixed model list: aios models shows live candidates only"
files_allowed = ["aios/catalog.py", "aios/cli.py", "aios/roster.toml", "tests/test_catalog.py", "tests/test_cli.py"]
contracts = ["architecture/contracts/models.schema.md"]
depends_on = ["router-roles"]
blast_radius = "medium"
kind = "refactor"
budget_usd = 0.5
+++

## Goal
The router now picks every model from the live catalog (ADR-0034). The old fixed list of 9 models
(`aios/roster.toml`) and the code that reads it are no longer used for routing. Remove them, so that nothing in aios
suggests a fixed list of allowed models any more.

## Context
- **Standard library only**; ASCII source; fail loud. Follow `AGENTS.md`: the comment rule (update the section map
  of each file you touch), and never compress code to fit a line cap.
- **`aios/catalog.py`** section 1 ("Roster") holds `Entry`, `load_roster`, `DEFAULT_ROSTER`, `TIERS`, `ROLES`, the
  `Diff` dataclass, `diff()` and `eligible()`. Nothing in `aios/` uses them except `cmd_models` in `aios/cli.py`.
- **`aios/cli.py`, `cmd_models`:** for `list`, `sync` and the default, it prints the roster lines, then
  `show_candidates`. `diff` prints SUSPENDED / MISSING / EXPIRING / NEW lines against the roster. It returns 1 when a
  roster model is suspended.

## Required changes
1. **Delete `aios/roster.toml`.**
2. **`aios/catalog.py`:** delete `Entry`, `load_roster`, `DEFAULT_ROSTER`, `TIERS`, `ROLES`, `Diff`, `diff` and
   `eligible`. Renumber the section map and headers, and update the module docstring so it no longer mentions a
   roster.
3. **`aios/cli.py`, `aios models`:**
   - `list`, and the default with no action, print only `show_candidates(live)`.
   - `sync` writes the cache, prints `synced <n> models -> <file>`, then shows the candidates.
   - `calibrate` is unchanged.
   - Remove the `diff` action.
   - Update the `models` help text, and return 0.
4. **Tests:**
   - In `tests/test_catalog.py`, remove the roster, diff and eligible tests, and keep every other test.
   - In `tests/test_cli.py`, remove or adapt any test that relies on the roster, `diff`, or the roster lines.

## Acceptance criteria
- `grep -rn "roster" aios/*.py aios/*.toml` finds nothing.
- `python3 -m unittest discover -s tests -t .` passes.
- `aios models` on a cached catalog prints the candidate lines and the Artificial Analysis attribution line.

## Out of scope
- `aios/config.py`, project settings, and `aios init` (the project-models-settings task);
- the contract file `architecture/contracts/roster.schema.md` (the Lead deletes it);
- any other file.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
