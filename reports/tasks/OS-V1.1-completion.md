# OS-V1.1 — status-ux (completion)

**Task:** OS-V1.1 · `task/OS-V1.1-status-ux`
**Model:** opencode-go/glm-5.2 (implementer) · verifier: opencode-go/deepseek-v4-pro
**Files touched:** `scripts/os`, `scripts/dispatch.sh`, `scripts/test/status.bats`,
`scripts/test/test_status.py`, `docs/handoff/SESSION-HANDOFF.md`, `tasks/active/OS-V1.1-status-ux.md`.

## What landed

Every operator-reported gap from OS-V1's first live day + round-2 requirements:

1. **Width-aware `os status`** — respects `$COLUMNS` (fallback 100); priority-truncates
   REPORT → LAST_LINE first, then BRANCH/LOG/AGENT; ID/STATE never shrink; droppable
   columns (report, last_line) are removed when space is exhausted; ANSI stripped from
   LAST_LINE (incl. the bare `[0m` leak). `--wide` disables fitting (full natural
   widths, ANSI still stripped). `--json` unchanged (machine surface).
2. **`os status --watch`** — self-refreshing view every 5s (`--watch-interval`), C-c to
   stop; one frame is emitted immediately so a bounded run captures it.
3. **Multi-run state bug (T09)** — `derive_state` now keys on the LAST run block
   (`last_run()` = last header + its trailing terminator), not the first/any footer.
   A re-dispatched fix round shows `running` while live, `waiting-gate` after exit 0.
4. **`verifying` state** — the gate.sh/verifier run in flight (last header is gate.sh
   with no exit footer) shows `verifying` instead of being invisible.
5. **Agent column from the last run header** — `<model-short>/<role>` read from the
   header's `model=<slug>` (dispatch.sh + gate.sh already write it); gate.sh run →
   `<vmodel>/verifier`, dispatch.sh run → the spec's owner_role. Falls back to the
   spec's resolved author when the log has no header.
6. **`os verdict <id>`** — prints the verdict file (`reviews/verdicts/<id>.txt`) + the
   ledger qa row (verifier/risk/verdict) + the opus-gate tier/flags + the PR link;
   post-land falls back to the last gate.sh block in `logs/<id>.log` + the ledger;
   exits 0 with a clear message when neither exists.
7. **`os stop <id>` / `os resume <id>`** — laptop-close workflow. `stop` SIGTERMs the
   opencode PID recorded in `logs/<id>.pid` (dispatch.sh now writes it), appends
   `=== stopped <utc> ===`, removes the pidfile; status then derives `stopped`. `resume`
   prints `scripts/dispatch.sh <id>` only (binding: no auto-dispatch). Documented that a
   generation stream cannot be paused — only killed.
   **Safety hardening (Lead gate REQUEST-CHANGES):** before signaling, `os stop` reads
   `/proc/<pid>/cmdline` (via injectable `_read_cmdline`) and requires the joined cmdline
   to contain `opencode`; a stale/recycled PID (cmdline mismatch or unreadable) is refused
   — exit 1, no SIGTERM, no stopped footer, pidfile left in place for manual removal — so a
   crashed-dispatch pidfile can never SIGTERM an innocent process. The dead
   `return 0 if killed else 0` was collapsed to `return 0`.
8. **`os tail [id | --all] [--diffs]`** — the live agent monitor: mtime-polls `logs/`,
   auto-attaches new runs, prefixes `[<id>·<role>·<model>]`, strips ANSI, colorizes per
   task on a TTY, re-plays existing content on attach (deterministic snapshot). `--diffs`
   surfaces new commits via read-only `git log --oneline` polling.

## How it was verified

- `python3 scripts/test/test_status.py` → 47 tests green (state derivation, last_run,
  verifying, stopped, agent-from-header, ANSI strip, width table, verdict fallback, and
  the `os stop` cmdline-identity injection paths — refuse non-opencode / refuse unreadable
  / proceed on opencode).
- `bats scripts/test` → 96 tests green (+15 new); includes the width/COLUMNS=80,
  `--watch`, multi-run T09 fixture, verifying, verdict (file + post-land fallback +
  neither), stop (real `exec -a opencode sleep` kill + stopped footer + resume prints the
  command without dispatching; NEW refuse-path test: a plain `sleep` PID is refused, stays
  alive, pidfile kept, no stopped footer), tail --all two logs, no-pidfile path.
- `bash scripts/ci-local.sh` → ALL GREEN (shellcheck, exec-bit, sibling-exec,
  component-isolation, coherence, bats, gitleaks).
- `scripts/os` stays READ-ONLY for `status`/`verdict`/`tail`; only `stop` mutates
  (appends a log line + removes a pidfile — no worktree source change), matching
  OS-V1's read-only contract for the view commands.

## Acceptance criteria map

- [x] `os status` ≤ terminal width (COLUMNS=80 test); `--wide` full; `--watch`
      refreshes (parse + one-cycle test); ANSI stripped from LAST_LINE.
- [x] Re-dispatched task (two header/footer pairs) shows `running` then `waiting-gate`
      — unittest on a T09 fixture.
- [x] Agent column shows `<model-short>/<role>` from the last run header.
- [x] `verifying` when the last run header is gate.sh with no footer.
- [x] `os verdict <id>` prints verdict + tier + flags (gated), falls back post-land,
      exits 0 with a clear message when neither exists.
- [x] `os stop` terminates a fake worker (sleep + pidfile), appends the stopped
      footer, status shows `stopped`; `os resume` prints the re-dispatch command.
- [x] `os tail --all` follows two fixture logs with correct prefixes (bats).
- [x] `bats scripts/test` fully green; SESSION-HANDOFF §2 documents `status --watch`,
      `tail`, `verdict`, `stop/resume` in the daily-cycle notes.

## Lessons

- **BUG-31-header-stopped-ambig** (memory DB; to be promoted to the registry by the
  Lead): `HEADER_RE` matched `=== stopped <utc> ===` as a run header (utc=`"stopped"`,
  script=`<utc>`), so `last_run` saw the stopped line as the last header with no
  terminator → `running` instead of `stopped`. **Root cause:** the header regex was
  too permissive (any two space-separated tokens). **Fix:** require the script token
  end in `.sh`; add a dedicated `STOPPED_RE`; prefer the stopped terminator over an exit
  footer (the laptop-close race where dispatch.sh's tee-close lands an exit footer after
  the stopped line). **Gotcha:** run-header and `os stop` terminator formats share the
  `=== <...> ===` envelope — keep their parsers disjoint and check stopped BEFORE exit.
- **recycled-pid-kill-trap (Lead gate, OS-V1.1):** `os stop` SIGTERM's a pidfile'd PID,
  but a pidfile survives a dispatch crash (`rm -f` only after a clean `wait`) and PIDs
  recycle → a bare `os.kill(pid)` can SIGTERM an unrelated (innocent) process.
  **Root cause:** trust in a stored PID number with no liveness/identity proof.
  **Fix:** read `/proc/<pid>/cmdline` first and require `opencode` in the joined argv;
  on mismatch/unreadable refuse (exit 1) WITHOUT deleting the pidfile or writing a
  stopped footer — the operator removes the stale pidfile manually. The cmdline reader
  is injectable so unit tests need no real `/proc`.
  **Gotcha:** black-box bats still needs an opencode-NAMED fake worker for the happy
  path — use `bash -c 'exec -a opencode sleep 30'` so `/proc/<pid>/cmdline` starts with
  `opencode`; a plain `sleep` exercises the refuse path.

## Out of scope (respected)

No scheduler/parallel dispatch (OS-P6), no autonomy ladder (OS-A1), no
notifications/TUI (OS-V2). No gate.sh changes. No pip packages (Python 3 stdlib only,
ADR-0023). `dispatch.sh` was changed only to write `logs/<id>.pid` (an addition, no
contract change — `os stop` consumes it; the run header/footer contract is unchanged).