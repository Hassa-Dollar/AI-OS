# Backlog: OS-A1 — pipeline autonomy ladder (operator design, 2026-07-16)

> Design pass with the operator + Lead before dispatch. Depends on: OS-P6 (worktrees/locks),
> OS-V1.1 (states it must surface). This automates the loop the Lead drove by hand for T09.

The ladder (operator's spec, verbatim intent):
1. Implementer finishes → **auto-wake the verifier** (today: ship.sh is run by hand).
2. Verifier VERDICT=fail → **auto-relaunch the implementer** with the verdict attached (fix round).
3. Fix round done → **auto re-verify**. Pass → verifier path **ships automatically**
   (auto-merge when CLEAR; draft PR + notify when flagged — OPERATOR/LEAD approval stays human).
4. Ship/gate fails on infra → **one automatic retry**; second failure → wake the Lead/operator.
5. Second consecutive VERDICT=fail after a fix round → **wake the Lead** (no third blind round).

Carve-outs learned from live T09 data (2026-07-15):
- A verdict whose BLOCKING items need a **decision** (unapproved dep, contract question, anything
  matching the escalate taxonomy) must wake the Lead IMMEDIATELY — an auto fix-round cannot resolve
  it and would burn a worker run. Classify verdict → `needs-decision` vs `needs-fixes` before step 2.
- HUMAN-REQUIRED checklist items and OPERATOR/LEAD gate approvals are never automated.
- Every automated hop appends to the ledger + logs (os status shows which rung the task is on).
- Budget caps: max 2 verify rounds + 1 infra retry per task per day without a human touch.
