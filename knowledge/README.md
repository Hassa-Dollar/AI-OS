# knowledge/ — durable, cross-cutting wisdom

**This directory = hard-won know-how that isn't a decision and isn't a task.** Decisions are ADRs
(`architecture/adr/`); how-to is `docs/`; this is the stuff in between that should survive months.

- `patterns/` — reusable solutions discovered in this repo ("how we do X here").
- `postmortems/` — what broke + the lesson (feeds failure-mode vigilance, manual §14).
- `external/` — distilled research keepers (library gotchas, benchmarks, decision memos worth keeping).

Append as the system earns it; prune nothing silently. If something is a *decision*, write an ADR
instead; if it's *how to use a component*, put it in that component's README.
