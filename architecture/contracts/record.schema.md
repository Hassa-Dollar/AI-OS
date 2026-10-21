# Contract: task record `.aios/records/<id>.json`

**Owner:** Lead. **Written by:** aios only. **Decided in:** ADR-0030 and ADR-0031.

The record is committed on the task branch before the merge. It is immutable once merged; new fields may only be
added as optional fields. It never contains prompts, transcripts, absolute paths or usernames.

```json
{
  "record_schema": 1,
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
    "roster_version": "<git blob sha of roster.toml>"
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
  "approval": { "by": "operator | lead", "note": "HIL pass, rev B" },
  "summary": "<what changed, one paragraph>",
  "lessons": ["<durable lesson worth recalling for future tasks>"],
  "usd_total": 0.058
}
```

**Usage rules:**
- `usd` comes from OpenRouter's per-call `usage.cost`, never from harness price tables.
- The gate only accepts a verdict whose `patch_id` matches the diff being merged.
