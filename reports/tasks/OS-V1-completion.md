# OS-V1 — worker logs + `scripts/os status` (completion report)

- **Task:** OS-V1 / `worker-logs-status`
- **Branch:** `task/OS-V1-worker-logs-status`
- **Model:** opencode-go/glm-5.2 (implementer)
- **Verifier:** opencode-go/deepseek-v4-pro (pending cross-family QA)
- **Status:** DONE — all acceptance criteria met; `bats scripts/test` (86) + the Python unittest (20) green; `scripts/ci-local.sh` ALL GREEN (shellcheck · exec-bit · sibling-exec · component-isolation · bats · verify-coherence · gitleaks).
- **Date:** 2026-07-15

## What was built

The operator is no longer blind to a running worker / verifier, and the whole system is one command away.
Two coordinated changes, both confined to `files_allowed`:

1. **Persistent worker + verifier logs (ADR-0026 §4 / OS-V1).** `dispatch.sh run_worker` and
   `gate.sh run_verifier` now append to `logs/<id>.log` instead of a `mktemp` deleted on success:
   - one run header per run — `=== <utc> <dispatch.sh|gate.sh> model=<slug> ===`,
   - a machine-readable run footer — `=== exit <code> <utc> ===` — written on BOTH success and failure,
     so state derivation never guesses,
   - the live `tee` to stdout is preserved (the operator sees the stream AND it is captured),
   - the `die` paths still quote the *real* output (BUG-20) — the log made that free; nothing is deleted.
   `logs/` and Python bytecode (`__pycache__/`, `*.pyc`) are gitignored (`.gitignore`); logs never enter
   the diff, so the boundary audit is unaffected.

2. **`scripts/os status` — the first read-only command of the `scripts/os/` Python CLI (ADR-0023).** A
   stdlib-only executable (`scripts/os`, shebang `#!/usr/bin/env python3`, no third-party deps — `pip` stays
   a STOP condition per ADR-0023). One row per task discovered in `tasks/active/` OR on a live `task/*`
   branch (several rows at once IS the parallel view, OS-P6). Columns: `ID · AGENT · BRANCH · STATE ·
   REPORT · LOG · LAST_LINE`:
   - `AGENT` = the RESOLVED model slug (gateway prefix stripped) + role, e.g. `glm-5.2/implementer`. Profile
     resolution for component tasks is a compact port of `_lib.sh resolve_roles` (ADR-0022): spec pin wins,
     else `.component.yml` → `profile.json roles[owner_role]`.
   - `STATE` is derived **deterministically** from the ledger (`reports/metrics/ledger.csv`) + the log run
     footer, in this priority: `queued` (no dispatch event) → `done` (a `land`/`auto-approve`/`merge` event)
     → `failed` (a `guardrail` abort, or a non-zero exit footer, with no later land) → `gated-held`
     (`opus-gate` event, or a `qa` pass pending merge) → `waiting-gate` (exit-0 footer, no qa yet) →
     `running` (dispatch present, no footer).
   - `REPORT` = `reports/tasks/<id>-completion.md` when it exists (the operator reads THIS instead of
     asking the Lead), else `—`; `LOG` = `logs/<id>.log`; `LAST_LINE` = the last non-bookkeeping log line
     (truncated), so the operator sees live progress at a glance.
   - Exit 0 always; `--json` emits the same rows as JSON (OS-P6's scheduler reads it). `gh` lookups are not
     used (offline-tolerant by construction). `status` is strictly read-only — verified by a byte-identical
     worktree/tree check in the bats suite.

`scripts/test/helpers.bash` now copies `scripts/os` (+x preserved) into each fixture repo; `docs/handoff/
SESSION-HANDOFF.md` §2 daily-cycle gained the two commands (`tail -f logs/<id>.log` and `scripts/os status`).

## Acceptance criteria — final state
- [x] A dispatched task's full worker output exists in `logs/<id>.log` after the run (success AND failure),
      with the timestamped header; re-runs append. (`dispatch.sh` writes header + `tee -a` + footer; the
      failure `die` no longer deletes the log.)
- [x] `scripts/os status` prints the table for a fixture repo with one queued + one finished task; `--json`
      emits the same rows as JSON. No git/gh mutation (read-only — verified with a byte-identical worktree
      **and** tracked-blob check in `status.bats` test 2).
- [x] Python stdlib `unittest` covers state derivation (queued/running/done/failed + the intermediate
      states, footer parsing, last-line, front-matter, slug shortening) from fixture logs + ledger lines;
      `bats scripts/test` fully green — `status.bats` black-box test added AND a bats test that runs the
      Python unittest suite (so CI exercises it too; os-ci runs `bats`, not `python3 -m unittest`).
- [x] `logs/` gitignored (`__pycache__/` + `*.pyc` too); SESSION-HANDOFF §2 daily-cycle notes gained the
      two commands.

## Deviations (justified; documented here)
1. **`scripts/os` is a single executable file, not a `scripts/os/` package directory.** A directory and a
   same-named file cannot coexist in POSIX (`scripts/os` the entrypoint and `scripts/os/` the package would
   collide), and `./scripts/os status` (the documented operator invocation) requires a file with a shebang,
   not a directory. ADR-0023's "package" framing is the eventual home; OS-V1 seeds it with the first command
   as one self-contained stdlib file structured for an easy later split (front-matter / role resolution /
   ledger / state derivation / rendering are distinct sections). The `scripts/os/` directory grant in
   `files_allowed` stays permissive (unused) and the existing `path_allowed` unit test treats `scripts/os`
   as an exact file — consistent with this choice.
2. **The Python unittest is run from `bats`**, not a new CI step. `os-ci.yml` (not in `files_allowed`) runs
   only `bash scripts/test.sh` → `bats scripts/test/*.bats`; editing it is out of scope. A `status.bats`
   test copies `test_status.py` into the fixture and runs `python3 scripts/test/test_status.py`, so the
   Python suite is exercised under the same harness os-ci already runs.

## Lessons (ADR-0021) — non-obvious traps
- **bats `eval`s `@test` descriptions — a backtick in the name runs as command substitution.** Symptom:
  `status.bats` test 4 was named `...derives `failed`` and every status test printed
  `/usr/lib/bats-core/test_functions.bash: line 471: failed: command not found` (bats_core's
  `bats_test_function` does `eval "printf -v test_description '%s' \"$2\""`). Fix: keep backticks / shell
  metacharacters OUT of `@test` names; use plain words (`derives failed`). Harmless to pass/fail outcome
  but noisy and masks real failures. Gotcha: a *passing* test can still emit stderr from this path.
- **A Python file with no `.py` extension isn't importable the normal way.** `scripts/os` is an
  extensionless executable (ADR-0023 entrypoint), so `test_status.py` loads it with
  `importlib.machinery.SourceFileLoader("aios_os", ".../scripts/os")` + `spec_from_loader`, not the usual
  `spec_from_file_location` (which returns `None` for an extensionless file). Gotcha: `spec_from_file_location`
  *silently* returns a spec with `loader=None` for these files — the failure is an `AttributeError` at
  module build, not a clear "unsupported extension".

## Defects found in QA
None at implementation time. The bats-name backtick trap was caught while writing the local suite (seen as
spurious stderr before re-running).

## Local gates
- `python3 scripts/test/test_status.py` — 20/20 OK (state derivation queued/running/done/failed/gated-held/
  waiting-gate + footer/last-line/front-matter/slug).
- `bats scripts/test/*.bats` — 86/86 ok (incl. 5 status.bats black-box tests).
- `bash scripts/ci-local.sh` — ALL GREEN: shellcheck (no new warnings) · exec-bit · sibling-exec ·
  component-isolation · bats · verify-coherence · gitleaks.

## Out of scope (respected)
No notifications, no TUI/GUI (phase 2 — `tasks/backlog/os-v2-notify-tui.md`). No scheduler (OS-P6). No
changes to what `dispatch.sh` / `gate.sh` DO — only where their output lands (the run-header/footer are new
*I/O*, the audit/guardrail/risk-router logic is untouched). No new dependency (stdlib only). Only
`files_allowed` touched (plus this report and the spec's Working Notes).

## Follow-ups / notes for downstream
- A real worker run will produce `logs/<id>.log` on disk; until then `status` derives `queued` for specs
  with no ledger event and `—` for the log column (no file). Both are correct and intended.
- The later full Python port (ADR-0023, OS-P1..P5) can lift `front_matter` / `resolve_author` / `read_ledger`
  / `derive_state` out of `scripts/os` into the `scripts/os/` package unchanged — the single-file shape was
  chosen to make that split mechanical.