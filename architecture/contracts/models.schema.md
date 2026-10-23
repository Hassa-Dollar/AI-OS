# Contract: model policy (`aios/models.toml` and `[models]` in `.aios/project.toml`)

**Owner:** Lead. **Implemented by:** `aios/catalog.py` and `aios/router.py`. **Decided in:** ADR-0034.

There is **no list of allowed models**, and no model is assigned to a role. Each task, every model in OpenRouter's
live catalog is a candidate for each role (ADR-0034 §3), and the cheapest expected cost at the required level wins.
This file only holds *policy*:
- the level thresholds;
- blocks for measured problems;
- family groupings for P8.

`aios/models.toml` applies to every project. A project's `[models]` table uses the same keys, and its entries are
added to the tool-wide ones. A project's `levels`, if set, replace the tool-wide levels.

```toml
models_version = 1

[levels]                    # minimum Artificial Analysis intelligence index for each level (ADR-0034 §2)
junior = 40
mid = 45
senior = 52

[[block]]                   # a measured problem only; never a preference
model = "vendor/model-id"   # an exact OpenRouter id
roles = ["reviewer"]        # any of: implementer, adversarial_tester, reviewer, security_reviewer
reason = "what was measured, and where (a record, lesson or PR)"
review_by = "2026-12-31"    # `aios doctor` warns after this date; the block stays until a PR removes it

[[family]]                  # treat several models as one family for P8 (cross-family review)
family = "lineage-name"
models = ["vendor-a/model-x", "vendor-b/model-y"]
reason = "for example: model-y is a fine-tune of model-x"
```

Rules:
- Unknown keys and unknown role names are errors.
- `levels` must be increasing (junior < mid < senior).
- When no `[[family]]` entry covers a model, its family is the vendor prefix of its id.
- A spec's `pin` (spec contract) still forces one model for one task and raises a LEAD flag. Nothing else may name a
  model for a role.
