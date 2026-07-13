# ADR-0024: OS change budget — stop the meta-work bleed, grow the evidence base

- **Status:** Accepted
- **Date:** 2026-07-13
- **Deciders:** Lead + human operator

## Context
The ledger's first month: ~59 OS lands vs 2 merged product tasks. The system mostly built and repaired
itself — the classic agent-framework failure mode where the harness eats the effort the product was
supposed to get. Meanwhile the core thesis (cheap workers ship real product under a scarce Lead) is
proven at n=2, with auth/payments/frontend (the hard parts) still ahead.

## Decision
1. **OS feature freeze.** After the roles-v2 batch (ADR-0022) lands, an OS change may merge only if it is:
   (a) one of the sanctioned epic tasks (OS-P1..P5 port, ADR-0023; OS-G1 guardrail upgrade), or
   (b) a fix that unblocks a **dispatched** product task (cite the task id in the commit).
   Everything else goes to `tasks/backlog/` and waits for the weekly review.
2. **Product first.** Shrink T04→T18 is the priority queue; OS-P*/OS-G* tasks fill spare capacity only
   and are themselves dispatched through the pipeline (they double as validation reps).
3. **The ratio is measured, not felt.** OS-P2 adds an AUTO-METRICS block to the handoff §3 computed
   from the ledger: weekly product:OS land ratio, `first_pass_qa`, dispatch count, Opus msgs/merged task.
4. **Success criteria** (weekly review, manual §14 knobs): `first_pass_qa ≥ 60%`; product:OS land
   ratio ≥ 1:1 and rising; Opus messages per merged task < 8. The MiniMax frontend tasks (T09/T12/T14)
   are the deliberate n-growth test for the never-exercised binding.

## Consequences
- The OS stops being the product; drift back into meta-work becomes visible in a generated block
  instead of requiring a ledger audit to notice.
- Some OS niceties will sit in backlog for weeks. That is the point.

## Alternatives considered
- **No policy, just intent:** the first month shows intent loses to the pull of harness-polishing. Rejected.
- **Hard freeze (no OS changes at all):** starves real unblockers and the sanctioned port. Rejected.
