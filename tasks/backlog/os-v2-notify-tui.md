# Backlog: OS-V2 — notifications + TUI visibility (phase 2, after OS-V1 proves out)

> Deliberately NOT designed yet (operator decision, 2026-07-14): ship logs + `os status` first
> (OS-V1), live with them, then decide what phase 2 needs.

Candidate scope, to be specced by the Lead when OS-V1 has real usage behind it:
- **Push notifications** on worker exit / `ESCALATE:` / gate verdict — channel TBD (ntfy.sh topic,
  desktop toast, webhook). Must be optional + secret-free (public-repo posture, ADR-0014).
- **TUI or minimal web view** over the same data `os status --json` already emits (never a second
  data source): live task table, tailing logs, ledger stream.
- Escalation routing: an `ESCALATE:` in a worker log should reach the operator's channel, not sit in
  a file.

Preconditions: OS-V1 landed + at least one multi-task week of `os status` usage; OS-P6 helpful but
not required.
