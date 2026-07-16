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
