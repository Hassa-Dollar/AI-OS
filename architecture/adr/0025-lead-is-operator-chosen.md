# ADR-0025: The Lead is operator-chosen, never model-fixed

- **Status:** Accepted
- **Date:** 2026-07-14
- **Deciders:** human operator + Lead

## Context
The docs stated the Lead **is** Claude Opus 4.8 — a specific model baked into CLAUDE.md, AGENTS.md,
the manual, role cards, and prompts. That contradicts the system's own design: roles are hats, not
standing daemons (manual §5), and workforce roles are already dynamically bound per profile
(ADR-0003/0022). The Lead seat deserves the same treatment: it is defined by its FUNCTION (coherence
owner, spec author, review gate, hard-bug breaker) and filled by whatever frontier model the operator
judges best at the time. The seat has now changed occupants (Opus 4.8 through T03; Claude Fable 5
since), proving the need.

## Decision
1. **The Lead is a role, not a model.** The binding is the operator's call, recorded here and in
   `agents/lead.md`; changing it requires no code change and no ADR beyond a one-line update of the
   "currently" pointer. Current binding: **Claude Fable 5**.
2. **Docs/prompts/scripts speak of "the Lead" and the "Lead gate."** All statements that fixed the
   Lead to a model were rewritten; budget discipline (msgs-per-merged-task targets, reserve) is
   plan-generic, not model-specific.
3. **Historical data keeps its names — never rewritten:** the ledger event kinds `opus-gate` /
   `opus-msg`, the completion-report header field `opus_gate`, `agent:opus-lead` provenance in the
   bug registry, and every existing ADR/report. New events keep the same kind strings for ledger
   continuity; read them as "Lead gate" / "Lead message."
4. The Lead is still **never a workforce model** (P8 and the catalog guard are unchanged); coherence
   check 5 continues to ban workforce-model names in role docs while allowing the Lead to be named.

## Consequences
- The scaffold is honest about its own economics: forks bind their own Lead exactly like they bind
  their own workforce; nothing assumes an Anthropic-specific model or plan.
- A future Lead swap is a two-line doc edit (this ADR's pointer + `agents/lead.md`), not a rename storm.
- Greppers will find `opus-gate`/`opus-lead` strings in data and history; this ADR is the decoder.

## Alternatives considered
- **Rename ledger kinds too (`lead-gate`):** breaks continuity of the metrics the whole control loop
  reads (§12.4, ADR-0024 AUTO-METRICS) or forces dual-kind parsing forever. Rejected.
- **Keep "Opus" as a generic title meaning "the Lead":** confusing the moment the seat is held by a
  non-Opus model — which is already the case. Rejected.
