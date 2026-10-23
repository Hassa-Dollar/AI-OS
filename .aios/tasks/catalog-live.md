+++
id = "catalog-live"
title = "Catalog: every usable model with its quality score, refreshed daily, listed per role and level"
files_allowed = ["aios/catalog.py", "aios/gateway.py", "aios/cli.py", "aios/models.toml", "tests/test_catalog.py"]
contracts = ["architecture/contracts/models.schema.md"]
blast_radius = "medium"
kind = "feature"
budget_usd = 1.0
+++

## Goal
This is the first step of ADR-0034 (`architecture/adr/0034-roles-levels-whole-catalog.md`; read sections 1-4, 7
and 9). It makes the whole live OpenRouter catalog usable for routing. After this task:
- The catalog cache joins three things:
  - every model, from `GET /models`, which carries the quality scores;
  - whether each model is usable under the account's privacy settings, from `GET /models/user`;
  - each model's prices and capabilities.
- The cache refreshes itself when it is more than 24 hours old.
- `catalog.candidates(...)` returns the models that can fill a role at a minimum level, cheapest expected cost first.
- `aios models` shows the top candidates for each role and level, and credits Artificial Analysis.

The router keeps using the old roster until the next task. Do not change `load_roster`, `diff` or `eligible`, and do
not touch `aios/router.py`.

## Context
- **Standard library only**; ASCII source; fail loud. Follow `AGENTS.md`, including its comment rule (a section map
  at the top, section headers with From/To lines, and one-line docstrings).
- `gateway.Gateway.models()` calls `GET /models`.
  - `GET /models/user` needs the key. It returns only the models usable under the account's privacy settings.
  - It does **not** include `benchmarks`, so join the two lists by `id`.
- The model fields used here:
  - `id`, `context_length`, `expiration_date` and `reasoning`;
  - `pricing.prompt` and `pricing.completion`: USD per token, as strings;
  - `top_provider.max_completion_tokens`;
  - `supported_parameters`, which may contain `"tools"` and/or `"structured_outputs"`;
  - `benchmarks.artificial_analysis.intelligence_index`, `coding_index` and `agentic_index`. Any of them can be
    null, and `benchmarks` itself can be missing.
- The policy file format is `architecture/contracts/models.schema.md`.

## Required changes
1. **`aios/gateway.py`:** add `models(self, *, user: bool = False)`. It calls `GET /models/user` when `user` is true.
2. **`aios/models.toml`** (new):
   - `models_version = 1`;
   - `[levels]` with `junior = 40`, `mid = 45` and `senior = 52`;
   - no `[[block]]` and no `[[family]]` entries;
   - a header comment that explains the file and points to the contract.
3. **`aios/catalog.py`.** Keep the existing roster functions unchanged, and add:
   ```python
   ROLE_NEEDS = {"implementer": "tools", "adversarial_tester": "tools",
                 "reviewer": "structured_outputs", "security_reviewer": "structured_outputs"}
   ROLE_TOKENS = {"implementer": (300_000, 15_000), "adversarial_tester": (200_000, 10_000),
                  "reviewer": (15_000, 5_000), "security_reviewer": (15_000, 5_000)}  # (input, output) per task
   DEFAULT_POLICY = Path(__file__).with_name("models.toml")

   @dataclass(frozen=True)
   class Policy:
       levels: dict[str, float]
       blocks: tuple[tuple[str, frozenset[str], str], ...]   # (model id, roles, reason)
       families: dict[str, str]                               # model id -> family

   @dataclass(frozen=True)
   class Candidate:
       id: str
       family: str
       score: float
       coding: float | None
       agentic: float | None
       usd_in: float    # per million input tokens
       usd_out: float   # per million output tokens
       context: int
       max_out: int | None
       est_usd: float   # expected cost of one task in this role

   def load_policy(path: Path = DEFAULT_POLICY, project: dict | None = None) -> Policy: ...
   def family(model_id: str, policy: Policy) -> str: ...
   def candidates(live: list[dict], *, role: str, level: str, policy: Policy, exclude_families=(),
                  context_need: int = 0, today: dt.date | None = None) -> list[Candidate]: ...
   ```
   - **`load_policy`** validates the file against the contract.
     - Unknown keys and unknown role names are errors.
     - Levels must increase from junior to mid to senior.
     - A project `[models]` dict, which uses the same keys, adds blocks and families and replaces the levels.
   - **`family`** returns the `[[family]]` grouping if one covers the model. Otherwise it returns the vendor prefix of
     the id.
   - **`sync(gateway, p)`** now stores the joined list. Each model dict gets `"usable": bool`, which is true when its
     id is in `gateway.models(user=True)`.
   - **`latest(p, *, gateway=None, max_age_h=24, out=print)`.**
     - It refreshes through `sync` when the newest cache is older than `max_age_h` and a gateway is given.
     - On `gateway.GatewayError` it keeps the old cache and prints one warning line.
     - It returns `None` when there is no cache at all.
     - Calls with only `p` keep working.
   - **`candidates`** keeps a model only if all of these hold:
     - it is usable;
     - its `intelligence_index` is not null and is at least `policy.levels[level]`;
     - its input or output price is above 0;
     - its id has no `~` prefix and no `:`;
     - it has no `expiration_date` within 14 days of `today`;
     - the role's `ROLE_NEEDS` entry is in its `supported_parameters`;
     - its `context_length` is at least `context_need`;
     - it is not blocked for the role;
     - its family is not in `exclude_families`.

     Compute `est_usd = usd_in * in_tokens / 1e6 + usd_out * out_tokens / 1e6` from `ROLE_TOKENS`. Sort by
     `est_usd`, then higher score first, then id.
4. **`aios/cli.py`:**
   - `aios models` (with no action, or with `list`) prints the three cheapest candidates for each role at each level,
     one line per role and level:
     `<role> <level>: <id> (score <s>, $<in>/$<out> per M, ~$<est> per task) | ...`.
     Then it prints the line `Quality scores: Artificial Analysis (artificialanalysis.ai), via OpenRouter.`
   - It builds the gateway when the key exists, so that `latest` can refresh.
   - `aios models sync` (which now writes the joined cache) and `aios models diff` keep working as before.

## Acceptance criteria
- `tests/test_catalog.py` (temp dirs and the fake HTTP server from `tests/helpers.py`, never the network) covers:
  - the join: a model that is missing from `/models/user` is not usable;
  - refreshing when the cache is stale, and not refreshing when it is fresh;
  - the offline fallback and its warning;
  - every `candidates` filter: usable, score against the level, price, `~` and `:`, expiry, capability per role,
    context, block and family exclusion;
  - the ordering;
  - `load_policy` validation and the project merge;
  - the `aios models` output, including the attribution line.

  The existing roster tests still pass.
- `python3 -m unittest discover -s tests -t .` passes.
- `aios/catalog.py` has at most 230 non-blank, non-comment lines.

## Out of scope
- `aios/router.py` and routing decisions (next task);
- deleting the roster (next task);
- calibration and budgets.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
