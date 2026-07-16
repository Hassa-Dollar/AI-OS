---
id: OS-V1.1
slug: status-ux
owner_role: implementer
model: opencode-go/glm-5.2                 # OS task (no component profile) → explicit pins
verifier_model: opencode-go/deepseek-v4-pro
branch: task/OS-V1.1-status-ux
blast_radius: med
files_allowed:
  - scripts/os
  - scripts/dispatch.sh
  - scripts/test/
  - docs/handoff/SESSION-HANDOFF.md
depends_on_contracts: []
deps_preapproved: []       # Python 3 STDLIB ONLY (ADR-0023) — pip is a STOP condition
---

# Goal
Close every operator-reported gap from OS-V1's first live day: width-aware `os status` with
`--watch`, a `verifying` state + correct multi-run state derivation, the model in the agent column,
`os verdict <id>` (works pre- AND post-land), `os tail` (the leave-open live monitor), and
`os stop / os resume <id>` for the laptop-close workflow.

# Context (compressed) — the operator requirements are the design; implement them exactly
Operator-reported gaps, first live day of OS-V1:
1. **`os status` overflows narrow terminals** — columns must fit `$COLUMNS`: priority-truncate
   (drop/shorten REPORT + LAST_LINE first), strip ANSI artifacts from LAST_LINE (seen: a bare `[0m`),
   optional `--wide` for full paths. `--json` stays the machine surface.
2. **`os status --watch`** — self-refreshing view (interim answer: `watch -n 5 ./scripts/os status`).
3. **`os tail [id | --all]` — the live agent monitor.** A terminal the operator leaves open; when any
   agent starts (implementer OR verifier), its stream appears automatically, each line prefixed
   `[<id>·<role>]` (and model), colorized per task. Implementation sketch: follow `logs/` directory,
   auto-attach on new/updated files, read role/model from the run header. Must handle multiple
   simultaneous logs (OS-P6 parallelism) without interleaving mid-line.
4. **`os verdict <id>`** — print the cross-family QA verdict (reviews/verdicts/<id>.txt), the risk
   flags + tier from the ledger, and the PR link — the operator's one command before `approve.sh`.

Constraints: python3 stdlib only (ADR-0023); read-only except nothing; bats + unittest like OS-V1;
`scripts/os` is engine → LEAD-tier gate (ADR-0026 amendment).

## Round 2 requirements (operator, 2026-07-16 — first full day of live use)
5. **`verifying` state + per-role visibility:** when gate.sh runs QA, `os status` must show it
   (`verifying` state or a second row `<id>·verifier`); today the verifier phase is invisible.
6. **Multi-run state bug:** a re-dispatched task (fix round) did not show `running` — state
   derivation must key on the LAST run header/footer pair in the log, not the first/any.
7. **Model in the agent column:** `—/implementer` → read the resolved slug from the log's run header
   (`model=<slug>`), which dispatch already writes; no profile lookup needed for past runs.
8. **`os verdict <id>` post-land:** the CLEAR path consumes reviews/verdicts/<id>.txt by design —
   verdict must fall back to the QA section of `logs/<id>.log` + the ledger row.
9. **`os stop <id>` / `os resume <id>` (laptop-close workflow):** clean-kill the worker process
   (state `stopped`), resume = re-dispatch on the same branch (small-commit discipline preserves
   progress). True pause of a generation stream is impossible — document that plainly.
10. **`os tail` honesty note:** the gateway stream is reasoning + tool headlines only; generated
    code is visible as commits — consider an optional per-commit diff view (`os tail --diffs`).

Implementation notes (binding):
- `os stop/resume`: dispatch.sh writes `logs/<id>.pid` (the opencode PID) next to the log; `stop` =
  SIGTERM that PID + append a `=== stopped <utc> ===` footer; `resume` = plain re-dispatch hint
  (print the command; do NOT auto-dispatch). Document plainly that a generation stream cannot pause.
- `os tail [id|--all]`: follow logs/ via mtime polling (stdlib), auto-attach new logs, prefix
  `[<id>·<role>·<model>]` from run headers, strip ANSI. `--diffs` may print new commits via
  `git log --oneline` polling — read-only always.
- Width: fit `$COLUMNS` (fallback 100); truncate REPORT/LAST_LINE first; `--wide` disables.
- Every behavior above gets a bats black-box test or a unittest (state derivation: cover the
  multi-run log case that produced the live bug).

# Acceptance criteria  (executable)
- [ ] `os status` output lines ≤ terminal width (test with COLUMNS=80 env); `--wide` full; `--watch`
      refreshes (test: flag parses + one refresh cycle); ANSI stripped from LAST_LINE.
- [ ] Re-dispatched task (two run header/footer pairs in one log) shows `running` while the second
      run is live and `waiting-gate` after — unittest on a fixture log reproducing the T09 bug.
- [ ] Agent column shows `<model-short>/<role>` read from the last run header.
- [ ] `verifying` state when the last run header is a gate.sh/verifier header without footer.
- [ ] `os verdict <id>`: prints verdict + tier + flags for a gated task (reviews/verdicts/ +
      ledger); for a landed task falls back to the log's QA section; exits 0 with a clear message
      when neither exists.
- [ ] `os stop <id>` terminates a fake worker (test: `sleep` process with pidfile) and appends the
      stopped footer; status then shows `stopped`; `os resume <id>` prints the re-dispatch command.
- [ ] `os tail --all` follows two fixture logs concurrently with correct prefixes (bats).
- [ ] `bats scripts/test` fully green; SESSION-HANDOFF §2 documents status --watch, tail, verdict,
      stop/resume in the daily-cycle notes.

# Out of scope  (binding)
- No scheduler/parallel dispatch (OS-P6), no autonomy ladder (OS-A1), no notifications/TUI (OS-V2).
- No gate.sh changes. No pip packages.

# Stop conditions
- Any requirement seems to need gate.sh or contract changes → STOP, escalate.
- A bats test can only pass by weakening its assertion → STOP, escalate.

# Working notes  (worker appends)

- width: priority-truncation order — LAST_LINE (floor 12) → shrink REPORT → drop
  REPORT → drop LAST_LINE → shrink BRANCH/LOG/AGENT → hard-truncate at 1. `--wide`
  disables fitting entirely (full natural widths, ANSI still stripped from LAST_LINE).
- multi-run fix: `last_run()` keys state on the LAST header + its trailing terminator
  (exit OR stopped). The T09 bug keyed on any footer; now a run-2 header with no
  footer flips `running`/`verifying` regardless of run-1's exit-0 footer.
- `verifying`: last run header is gate.sh with no terminator (QA in flight).
- agent column: model/role read from the LAST run header (`model=<slug>`); gate.sh run
  → `<vmodel>/verifier`, dispatch.sh run → `<spec owner_role>`. Fallback to the spec's
  resolved author when the log has no header (queued / never-run).
- stop/resume: `os stop` SIGTERMs the pid in `logs/<id>.pid` (dispatch.sh now writes
  it via `<(...) & wait $!`), appends `=== stopped <utc> ===`, removes the pidfile;
  `os resume` only PRINTS `scripts/dispatch.sh <id>` (binding: no auto-dispatch).
- tail: mtime-poll logs/ (1s), on attach replay existing content (so a bounded test
  captures a frame deterministically); prefix `[<id>·<role>·<model>]`; ANSI stripped;
  colorized per task ONLY on a TTY (keeps piped/captured output clean). `--diffs`
  surfaces new commits via read-only `git log --oneline` polling.
- verdict: prefer `reviews/verdicts/<id>.txt` + ledger qa + opus-gate notes (parsed
  via `_parse_note_kv`, which reassembles the space-joined `flags=<a> <b> <c>` list);
  post-land falls back to the last gate.sh block in `logs/<id>.log`; missing anything
  → exit 0 with a clear message.
- BUG-31-header-stopped-ambig (recorded in the memory DB, db.sh): `HEADER_RE`
  matched `=== stopped <utc> ===` as a run header (utc="stopped", script=<utc>),
  so `last_run` mis-saw the stopped line as the last header → `running` instead of
  `stopped`. Fix: tighten `HEADER_RE` to require the script token end in `.sh`;
  add `STOPPED_RE`; prefer the stopped terminator over an exit footer (laptop-close
  race where dispatch.sh's tee close lands an exit footer after the stopped line).
- gates: `python3 scripts/test/test_status.py` (44) + `bats scripts/test` (95) +
  `bash scripts/ci-local.sh` ALL GREEN; `verify-coherence.sh` OK.

### Lead decision (2026-07-16, LEAD gate review — REQUEST-CHANGES)
QA (DeepSeek) passed; the Lead gate found ONE blocking defect + two nits. Fix round:
1. **BLOCKING — `cmd_stop` may SIGTERM an innocent process.** The pidfile survives a dispatch
   crash (`rm -f` runs only after a clean `wait`), PIDs are recycled, and `_sigterm_pid` kills
   whatever the number points at. Before signaling: read `/proc/<pid>/cmdline` and require it to
   contain `opencode`; on mismatch or unreadable, do NOT kill — print "stale pidfile (pid <n> is
   not an opencode worker); remove logs/<id>.pid manually" and exit 1 WITHOUT deleting the
   pidfile or appending a stopped footer. Unit-test both paths (inject the cmdline-reader so the
   test needs no real /proc).
2. Restore the two-space indent on `mkdir -p logs` inside run_worker (dispatch.sh).
3. `return 0 if killed else 0` → `return 0` (dead expression).
The tee/footer ordering race handled parser-side is ACCEPTED as designed (documented + tested).
All gates must stay green; do not touch anything else.

### Fix round — Lead REQUEST-CHANGES applied (2026-07-16, implementer)
1. **stop identity check (BLOCKING, fixed):** added `_read_cmdline(pid)` which reads
   `/proc/<pid>/cmdline` (NUL-joined, UTF-8) and returns None when unreadable.
   `cmd_stop` now takes an injectable `cmdline_reader` (default `_read_cmdline`),
   and BEFORE signaling requires the joined cmdline to contain `opencode`; on
   mismatch/unreadable it prints "stale pidfile (pid <n> is not an opencode
   worker); remove logs/<id>.pid manually", returns 1, and leaves BOTH the pidfile
   AND the log untouched (no stopped footer). Covered by:
   - unittest `StopIdentityTests` (3): refuse non-opencode, refuse unreadable,
     proceed-on-opencode — all via injected readers (no real /proc).
   - bats: happy path now runs an `exec -a opencode sleep 30` worker so the real
     /proc check passes and the real SIGTERM lands; NEW refuse-path bats test uses
     a plain `sleep` (no `opencode` in cmdline) → exit 1, sleep stays alive, pidfile
     kept, no stopped footer.
2. **dispatch.sh indent:** `mkdir -p logs` inside `run_worker` restored to 2-space.
3. **dead expression:** `return 0 if killed else 0` → `return 0`.
- gates: `python3 scripts/test/test_status.py` (47) + `bats scripts/test` (96) +
  `bash scripts/ci-local.sh` ALL GREEN; `verify-coherence.sh` OK.
