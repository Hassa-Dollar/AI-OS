# Contract: task record `.aios/records/<id>.json`

**Owner:** Lead. **Written by:** aios only. **Decided in:** ADR-0030 and ADR-0031.

The record is committed on the task branch before the merge. It is immutable once merged; new fields may only be
added as optional fields. It never contains prompts, transcripts, absolute paths or usernames.

```json
{
  "record_schema": 2,
  "task": "SH-1",
  "spec_blob": "<git blob sha of the spec when it was dispatched>",
  "tool_version": "aios 2.0.0-dev",
  "routing": {
    "router": "clef-flash | clef | heuristic",
    "answers": { "<question>": "<answer as returned: choice/noul/score + confidence>" },
    "tier": "T1 | T2 | T3",
    "author": { "model": "deepseek/deepseek-v4-pro", "family": "deepseek" },
    "verifier": { "model": "moonshotai/kimi-k2.7-code", "family": "moonshotai" },
    "gate": "AUTO | OPERATOR | LEAD | HUMAN",
    "reasons": ["<one line per decision-table rule that fired>"],
    "policy_version": 1,
    "roster_version": "<git blob sha of roster.toml; record_schema 1 only>",
    "roles": {
      "implementer": { "model": "xiaomi/mimo-v2.6-pro", "family": "xiaomi", "level": "mid", "score": 46.3,
                       "usd_per_m": [0.435, 0.87], "est_usd": 0.14, "why": "cheapest of 23 candidates at mid" },
      "reviewer":    { "model": "anthropic/claude-sonnet-5.5", "family": "anthropic", "level": "senior", "score": 56,
                       "usd_per_m": [2.0, 10.0], "est_usd": 0.08, "why": "cheapest calibrated reviewer at senior" }
    },
    "models_policy": "<git blob sha of aios/models.toml>"
  },
  "attempts": [
    {
      "n": 1,
      "model": "deepseek/deepseek-v4-pro",
      "canonical_slug": "deepseek/deepseek-v4-pro-20260423",
      "harness": "<name> <version>",
      "secs": 177, "steps": 23, "usd": 0.057,
      "tokens": { "input": 0, "output": 0, "cache_read": 0 },
      "exit": "submitted | limits | escalated | error | infra",
      "verdict": {
        "verdict": "pass | fail | needs_decision",
        "risk": "low | medium | high",
        "blocking": ["..."],
        "verifier": "<model>",
        "usd": 0.001,
        "patch_id": "<git patch-id --stable of the reviewed diff>",
        "commit": "<sha>"
      }
    }
  ],
  "flags": ["dependency-change", "multi-component", "sensitive-path"],
  "approval": { "by": "operator | lead", "note": "HIL pass, rev B", "override": "<operator only: why a failing review is overruled>" },
  "summary": "<what changed, one paragraph>",
  "lessons": ["<durable lesson worth recalling for future tasks>"],
  "usd_total": 0.058
}
```

**Usage rules:**
- `usd` comes from OpenRouter's per-call `usage.cost`, never from harness price tables.
- The gate only accepts a verdict whose `patch_id` matches the diff being merged.
- **record_schema 2 (ADR-0034).**
  - `routing.roles` records, for each role that ran, its model, family, level, score, price, cost estimate, and why it
    won.
  - `author` and `verifier` are still written, as the implementer and the reviewer.
  - Readers handle both versions: a record that is still at schema 1 has no `roles`.
- `approval.override` (optional): only the operator can set it, to overrule a `fail` or `needs_decision` verdict that
  the Lead has shown with evidence to be wrong. The verdict stays in the record, and the gate becomes at least LEAD.
- `routing.roles.reviewer.level` is `senior` on senior tasks and `any` otherwise. A reviewer is chosen by calibration,
  with no score minimum below senior (ADR-0034 section 2).
