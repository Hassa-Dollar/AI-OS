# Contract: `aios/roster.toml` (models eligible for routing)

> **Superseded by [`models.schema.md`](models.schema.md) (ADR-0034).** The fixed list below stays in use only until whole-catalog selection is implemented. Then this file and `aios/roster.toml` are deleted.

**Owner:** Lead. **Implemented by:** `aios/catalog.py`. **Decided in:** ADR-0031.

```toml
roster_version = 1

[[model]]
id = "deepseek/deepseek-v4-pro"   # exact OpenRouter id; never a "~" alias or a ":batch" variant
tier = "T2"                        # T1 cheap | T2 strong open-weight | T3 frontier
family = "deepseek"                # optional; defaults to the vendor prefix of `id` (used for P8)
roles = ["implement", "verify"]    # optional; defaults to both
canonical_slug = "deepseek/deepseek-v4-pro-20260423"   # pinned; a mismatch with the live catalog suspends the model
since = "2026-10-21"
note = "v1 verifier; structured outputs verified in the OpenRouter spike"
```

Rules:
- Admission and tier changes go through a PR and `aios models probe <id>`. Routing never considers a model that is not
  in the roster, or one marked suspended.
- The opt-in auto-admit of successors (ADR-0031) writes a proposed entry, and that entry still goes through a PR.
