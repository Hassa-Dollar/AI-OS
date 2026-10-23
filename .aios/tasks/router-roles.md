+++
id = "router-roles"
title = "Router: fill the implementer and reviewer roles from the whole catalog by level, not from the fixed list"
files_allowed = ["aios/router.py", "aios/run.py", "aios/catalog.py", "tests/test_router.py"]
contracts = ["architecture/contracts/models.schema.md"]
depends_on = ["catalog-live", "reviewer-calibration", "records-roles"]
blast_radius = "high"
kind = "feature"
budget_usd = 1.0
+++

## Goal
The central switch of ADR-0034 (read sections 1-4 and 6). The router stops picking from `aios/roster.toml`. For each
task it:
- sets a **level** (junior, mid or senior);
- fills the **implementer** role with the cheapest candidate at that level from the live catalog;
- fills the **reviewer** role with the cheapest **calibrated** candidate from another family. For a senior task, that
  reviewer must also have a senior score.

The gate rules (AUTO / LEAD / HUMAN and spec gaps) do not change.

## Context
- **Standard library only**; ASCII source; fail loud. Follow `AGENTS.md`, including its comment rule. Update the
  section maps of the files you touch.
- **Already on main:**
  - `catalog.latest(p, gateway=...)`, `catalog.load_policy()`, `catalog.family(id, policy)`;
  - `catalog.candidates(live, *, role, level, policy, exclude_families=(), context_need=0, today=None)`, which returns
    `Candidate(id, family, score, coding, agentic, usd_in, usd_out, context, max_out, est_usd)`, cheapest first;
  - `catalog.LEVELS = ("junior", "mid", "senior")`;
  - `calibrate.passed(p, model) -> bool` (the reviewer-calibration task).
- **`router.decide`** today takes `roster`, `live`, `max_tier`, `frontier_auto` and `min_tier`, and picks with
  `_pick` / `catalog.eligible`.
  - Its gate logic (the `human` and `lead` lists, `spec_gaps`, the degraded-routing LEAD reason) stays exactly as it
    is.
- **`router.Decision`** is a dataclass. Tests elsewhere build it **positionally** with 12 arguments.
  - Keep those 12 fields in order, and rename `tier` to `level`.
  - Add `roles: dict = dataclasses.field(default_factory=dict)` last.
- **`run.route(s, proj)`** calls `router.decide`. `run.dispatch` prints a line with `tier`, and its commit trailer
  says `Routed: gate X, tier Y, router Z`.
- **Records** already read `level` and `roles` from the decision (the records-roles task).

## Required changes
1. **`aios/catalog.py`:** `candidates(..., level: str | None, ...)`. With `level=None` there is no score minimum, but
   a score is still required. Nothing else changes.
2. **`aios/router.py`:**
   - `LEVEL_FLOOR = {"security_auth": "mid", "data_migration": "mid", "contract_change": "mid", "hardware": "mid", "research": "mid"}`.
     Remove `CLASS_FLOOR`, `_pick`, and every use of tiers, the roster and `catalog.eligible`.
   - The new signature:
     ```python
     def decide(spec, answers, *, live, policy, router="clef-flash", deny_vendors=(), confidence_floor=0.6,
                reviewer_ok=lambda model_id: True, today=None) -> Decision: ...
     ```
   - **The level.** Start at `LEVEL_FLOOR.get(cls, "junior")`. Then:
     - a hard task or broad context raises it to at least `mid`;
     - a task that is hard **and** broad, security-sensitive (`security_sensitive > SEC_HUMAN`), or on the HUMAN gate
       is `senior`;
     - low classifier confidence raises it by one, up to `senior`.

     Each rule that fires appends its reason, as today.
   - **The implementer.** The first entry of `catalog.candidates(live, role="implementer", level=level, ...)` whose
     vendor (the prefix before `/`) is not in `deny_vendors`.
     - If there is none, return a refusal with the reason `no implementer candidate at <level>`.
   - **The reviewer.** Use `catalog.candidates(live, role="reviewer", level="senior" if level == "senior" else None, exclude_families=(implementer family,), ...)`.
     Filter it to `reviewer_ok(c.id)` and to vendors that are not denied, then take the first.
     - If there is none, refuse with the reason
       `no calibrated reviewer outside family '<f>': run 'aios models calibrate <ids>'`. List the three cheapest
       uncalibrated candidates.
   - **The result.** Set `author`, `author_family`, `verifier`, `verifier_family` and `level`. Set
     `roles = {"implementer": {...}, "reviewer": {...}}`, each with `model`, `family`, `level`, `score`,
     `usd_per_m: [usd_in, usd_out]`, `est_usd` (rounded to 4 decimals) and `why`:
     - for the implementer, `cheapest of <n> candidates at <level>`;
     - for the reviewer, `cheapest calibrated reviewer of <n>`.
3. **`aios/run.py`:**
   - `route()` builds the gateway when the key exists (so `latest` can refresh) and loads the policy with
     `catalog.load_policy()`. It passes `reviewer_ok=lambda m: calibrate.passed(p, m)`, and no longer passes the
     roster, `max_tier` or `frontier_auto`.
   - In `dispatch`, the printed line becomes
     `<id>: <action> | gate <g> | level <l> | implementer <a> | reviewer <v> (<router>)`, and the trailer becomes
     `Routed: gate <g>, level <l>, router <r>`.
4. **`tests/test_router.py`:**
   - Rebuild the fixtures: a small fake live catalog in the cache shape, meaning model dicts with `usable`,
     `pricing`, `supported_parameters`, `context_length` and `benchmarks.artificial_analysis.intelligence_index`, plus
     a `Policy`, in place of the roster.
   - Keep every gate test as it is.

## Acceptance criteria
- `tests/test_router.py` covers:
  - each level rule;
  - the cheapest implementer winning, with frontier models included when they are cheapest at the level;
  - denied vendors being skipped;
  - the reviewer coming from another family, being calibrated (via `reviewer_ok`), and needing a senior score only
    for senior tasks;
  - a cheap, low-scoring calibrated reviewer being chosen for a junior task;
  - both refusals and their messages;
  - the `roles` content;
  - every existing gate test still passing.
- `python3 -m unittest discover -s tests -t .` passes, including `tests/test_dispatch.py`, `tests/test_land.py` and
  `tests/test_gate_run.py` without edits.
- `aios/router.py` has at most 225 and `aios/catalog.py` at most 230 non-blank, non-comment lines.

## Out of scope
- Deleting the roster file and its code (a later cleanup task);
- the adversarial tester and security reviewer roles (later);
- the gate;
- project `[models]` settings.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
