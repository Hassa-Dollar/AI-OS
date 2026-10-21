# Lead protocol

The **Lead** is the operator-chosen frontier model (ADR-0025). It runs either interactively (Claude Code, or any
console holding the gateway key) or as the T3 tier called by aios. It owns coherence: specs, contracts, ADRs, and the
review gate on flagged diffs. The workforce does the implementation. See `docs/doctrine.md`.

## 1. Load context compressed, never the whole tree
Read in this order:
1. `architecture/README.md` (the map);
2. the ADR index;
3. only the contracts the work touches;
4. the target's `aios brief` output (computed from git: open tasks, recent records, spend);
5. the request in front of you.

If you feel you need the whole repo, the map is stale: fix the map.

## 2. Plan
Planning produces three things:
- **Specs in `.aios/tasks/`** following `architecture/contracts/spec.schema.md`. Each one must be complete enough that a
  worker needs nothing else; executable acceptance criteria are mandatory. Grant `files_allowed` narrowly, and never
  let it overlap another active task. Name the `deps_preapproved` explicitly.
- **An ADR for every high-leverage decision**, and a contract change wherever an interface moves.
- **Specs land via `aios plan`** (a PR), never by pushing to the default branch.

Spec quality is measured, not asserted. If first-pass verification falls below ~60–70% (`aios report`), the specs are
too vague: fix the specs before adding more tasks.

## 3. Review gate
You only see diffs the gate flagged at the LEAD tier: contract, architecture, security path, new dependency,
sensitive path, pin, or a `needs_decision` escalation. For each one, judge leverage and coherence:
- Are contracts and invariants honored? Did any contract change implicitly?
- Is the abstraction right-sized, with no scope creep beyond the Goal and Out of scope?
- Are security and failure modes sane for this change?
- Is it reversible, with no data-shape lock-in that lacks an ADR?

Reply with `APPROVE` or `REQUEST-CHANGES` plus the minimal changes needed. Review the queue in one batch, never diff by
diff.

## 4. Escalate to the human
Escalate everything in doctrine's HUMAN-REQUIRED list. Never decide those yourself.

## 5. Budget (dollars, not messages)
Watch three numbers in `aios report`:
- dollars per merged task, by tier;
- Lead touches per merged task (target < 4);
- the frontier share of spend.

If the Lead is being used as a worker, push specified work back to the workforce, or raise the gate threshold.

## 6. Security posture (the AI-OS repo is public)
- Treat the tool repo as world-readable.
- Never commit secrets, keys, tokens, `.env` files or PII. The gateway key lives in `~/.config/aios/credentials`
  (mode 0600).
- Anything touching auth, secrets, input validation or the supply chain (dependencies, CI workflows, the harness lock)
  goes to the Lead even when the diff is small.
- CI never echoes secrets, and `GITHUB_TOKEN` stays least-privilege.
