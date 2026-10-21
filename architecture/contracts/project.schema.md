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
path = "components/api/"
profile = "node"                  # aios/profiles/<profile>/
setup = ["npm ci --no-audit --no-fund"]                   # optional; overrides the profile. Runs sandboxed, network allowed
checks = ["npm run -s lint", "npm run -s typecheck", "npm run -s test", "npm run -s coverage"]  # optional override
checks_waiver = ""                # required (non-empty) if checks = []; otherwise the component fails closed

[budget]
per_task_usd = 1.0
per_day_usd = 5.0

[privacy]
data_collection = "deny"          # deny | allow; applied to every model call
zdr = false
deny_vendors = []                 # e.g. ["x-ai"]
max_tier = "T3"                   # T1 | T2 | T3

[routing]
frontier_auto = false             # whether the ladder may climb to T3 by itself
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
