# Contract: `.aios/project.toml` (target-repo configuration)

**Owner:** Lead. **Implemented by:** `aios/config.py`. **Decided in:** ADR-0030.

```toml
schema = 1                        # required; aios refuses newer schemas and reads the previous one
name = "shrink"                   # required; together with the root-commit hash it forms the project id
forge = "github"                  # github | local
remote = "origin"
default_branch = "main"           # optional; defaults to origin/HEAD

[[components]]                    # at least one; each file maps to the component with the longest matching path prefix
name = "api"
path = "components/api/"         # a relative directory ending in "/", or "./" for the repo root
toolchain = { node = "22" }       # optional; what the component needs, each the oldest version it accepts (ADR-0035)
setup = ["npm ci --no-audit --no-fund"]                   # optional. Runs sandboxed, network allowed
checks = ["npm run -s lint", "npm run -s typecheck", "npm run -s test", "npm run -s coverage"]  # optional override
checks_waiver = ""                # required (non-empty) if checks = []; otherwise the component fails closed

[budget]
per_task_usd = 1.0
per_day_usd = 5.0

[privacy]
data_collection = "deny"          # deny | allow; applied to every model call
zdr = true                        # ask for zero-data-retention endpoints on every call (the account setting also applies)
deny_vendors = []                 # e.g. ["x-ai"]

[models]                          # optional project policy (contract: models.schema.md); added to aios/models.toml
levels = { junior = 40, mid = 45, senior = 52 }

[routing]
router_model = "clef-flash"
router_escalation_model = "clef"
escalate_below_confidence = 0.6

[sensitive]
paths = []                        # changes under these paths raise a LEAD flag
```

Validation rules:
- Unknown keys are errors.
- Commands are argument lists split by `shlex` and run without a shell. Shell features such as pipes or `&&` need an
  explicit `["bash", "-c", "..."]`.
- `max_tier` and `frontier_auto` (ADR-0031) were removed by ADR-0034. Every model is a candidate, and money caps bound
  the spending. For now, aios still reads both keys and ignores them with a warning, so existing projects keep
  loading.
- `toolchain` names must be known to aios: `node`, `python`, `rust`, `go` or `platformio`. Each version is digits
  and dots, such as `"22"` or `"3.12"`, and is a minimum. `aios doctor` checks them inside the worker sandbox.
- `profile` (ADR-0030) was retired by ADR-0035. aios still reads it and ignores it with a warning.
