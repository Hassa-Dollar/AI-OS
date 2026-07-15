# Backlog: OS-V1.1 — status/monitor UX (operator requirements, 2026-07-15)

> **Design pass with the operator required before dispatch** — these are captured requirements, not
> a finished spec. Builds on OS-V1's `scripts/os` + `logs/<id>.log`.

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
