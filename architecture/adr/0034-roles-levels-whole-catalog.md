# ADR-0034: Roles and levels, filled from the whole catalog

- **Status:** Accepted
- **Date:** 2026-10-22
- **Deciders:** Lead + human operator
- **Supersedes:** the roster, tier and model-choice parts of ADR-0031 (rule 1, decision-table steps 4–6, and the
  `frontier.auto` switch). Clef, the gate decision table and the escalation ladder stay.

## Context
ADR-0031 routed every task to one of nine hand-picked models listed in `aios/roster.toml`, sorted into tiers T1/T2/T3,
some of them with fixed roles. It rejected "routing over the whole catalog" because there was no quality signal for
most models. Three things have changed:

1. **OpenRouter now publishes a quality signal for each model, keyed by its id.** Verified 2026-10-22:
   - `GET /api/v1/models` carries `benchmarks.artificial_analysis` (intelligence, coding and agentic indexes) for 303
     of 468 models. New flagships are included, for example Gemini 4 Argon, released 2026-10-13.
   - `GET /api/v1/benchmarks` serves the same indexes for the coding and agentic tasks.
   - `GET /api/v1/models/user` lists the models usable under the account's privacy settings: 391 of 468 with
     "Zero retention only" enforced.
2. **The hand-made tiers were wrong.** `deepseek-v4-pro`, filed as T2 "strong", scores 36. The T1 "cheap"
   `glm-5.3-flash` scores 41.8. As the default verifier, DeepSeek V4 Pro also overran every reasoning budget we gave
   it, and its fallback verdicts were mostly wrong (lessons 18–19, and the reasoning-fallback task).
3. **The operator set the direction:**
   - One key, every model: new releases must appear without anyone editing a file.
   - "Cheapest" means best-suited at the lowest price. A frontier model is used when it is that model.
   - **No model has a pinned role.** Roles mirror a real software team, at junior, mid or senior level. The model
     that fills a role is chosen per task.
   - Spending is bounded by money caps, not by artificial token caps.

## Decision

### 1. Roles: what a task needs, in logical order
| # | Role | Does | Runs when | Needs |
|---|---|---|---|---|
| 1 | **implementer** | Writes the change, in the sandbox | always | tool calls (the worker harness sends a bash tool) |
| 2 | **adversarial tester** | Tries to break the change: writes failing tests and edge cases against the implementer's branch | blast radius medium or high, security-sensitive, or senior level | tool calls; a family other than the implementer's |
| 3 | **reviewer** (the verifier) | Judges the diff against the spec and returns the JSON verdict | always | structured outputs; a family other than the implementer's; a passing reviewer calibration (§6) |
| 4 | **security reviewer** | A second, security-only review | security-sensitive tasks | as for reviewer, and a family other than both the implementer's and the reviewer's |

Roles that only the Lead or aios fills today are named here so the list stays complete. Their models are not routed
yet:
- planner and architect: the Lead;
- test writer, before the implementation;
- documentation writer;
- release: deterministic, done by aios.

### 2. Levels: how senior each role must be
Each level is a minimum quality score: the Artificial Analysis intelligence index served by OpenRouter.

| Level | For | Default minimum |
|---|---|---|
| **junior** | easy, low-risk tasks | 40 |
| **mid** | intermediate tasks | 45 |
| **senior** | hard or critical tasks | 52 |

- **The task's level** comes from Clef's reading of the task:
  - **senior:** security-sensitive work, work that needs the HUMAN gate, or work that is both hard and broad in context;
  - **mid:** hard or broad work, or a class that needs judgement (contract change, data migration, research,
    hardware);
  - **junior:** everything else;
  - **low classifier confidence** raises the level by one.
- **The implementer and the adversarial tester** work at the task's level.
- **The reviewers** are chosen by measured fitness, not by the general score. A reviewer must have passed the
  reviewer calibration (§6), and the cheapest calibrated reviewer wins. For a **senior** task, it must also score at
  least the senior minimum.
  - Why: the first calibration's best-value reviewer scores 36 on the general index, below "mid". The cheapest
    model by general score alone took 26 minutes per judgment.
- **The thresholds live in `.aios/project.toml` `[models] levels`.** The Artificial Analysis index has a version (see
  the benchmarks endpoint's `meta`). When it is re-versioned, the thresholds are retuned in a PR.

### 3. Candidates: every model that can do the role
A model is a candidate for a role when all of the following hold:
- it is in `/api/v1/models/user`, so it is usable under the account's privacy settings;
- it has a quality score;
- it has a price above zero;
- it is not a `~` alias or a `:variant` (`:free`, `:batch`, ...);
- it does not expire within 14 days;
- it has the role's capabilities;
- its context window fits the task;
- it is not blocked for that role by the override file (§7).

There is **no allowlist**. A new model becomes a candidate as soon as OpenRouter lists it with a score, which usually
happens within days of release.

### 4. Choice: the lowest expected cost to a merged result (P12)
Among the candidates at or above the level, the cheapest *expected cost per task* wins. A tie goes to the higher
score.
- **Before a model has records,** the estimate is its token price times a per-role token estimate, for example
  implementer 300K in / 15K out per attempt and reviewer 15K in / 5K out.
- **Once a model has 3 or more records in that role,** the estimate becomes its measured median dollars per attempt,
  divided by its measured pass rate.
- **Frontier models are ordinary candidates.** `frontier_auto` is removed.
- **A model whose estimated task cost is above the task's money cap (§5) is skipped.** If no candidate fits, aios
  stops and asks. It never quietly drops to a weaker level.

### 5. Money, not token caps
- **Every call's `max_tokens`** is what the remaining task budget can pay for at that model's output price, up to the
  model's own maximum. A model is never cut off below what its budget allows.
- **Caps come from the operator:**
  - a **monthly** budget, asked at setup, which matches the OpenRouter key's limit with a monthly reset;
  - a **daily** cap;
  - a **per-task** cap.

  The governor reads the key's remaining amount and its monthly usage before every call.

### 6. Reviewer calibration
A quality index measures general ability, not whether a model judges diffs reliably. A model can fill the
**reviewer** role only after it has passed a calibration on this machine:
- `aios models calibrate <model>` runs the real reviewer prompt on known changes, some with real bugs and some
  correct;
- the model must judge every one of them right, within its money cap.

Results are cached locally with the date and the prompt version. aios suggests calibrating any cheaper, uncalibrated
model that would otherwise be chosen.

**A failing verdict must be confirmed.** A reviewer's `fail` counts only if a second, independent review of the same
change also fails it. That second review comes from a different family when a calibrated one fits the budget, and
otherwise from the same model. Both verdicts are recorded. A `pass` is not re-checked: no calibration run below
passed buggy code. This removes most false fails, which cost Lead time and override decisions, and the extra spend
happens only on fails.

The first calibration ran on 2026-10-22, with "Zero retention only" enforced and a money cap of $0.20 per call. Three
changes whose answer is known were judged:
- the gate command's first attempt, which has real bugs (answer: **fail**);
- the merged approve/land commands (**pass**);
- the merged forge cleanup fix (**pass**).

| Model | Right | Cost (3 judgments) | Time | Notes |
|---|---|---|---|---|
| `deepseek/deepseek-v4-pro-0813` | 3/3, then 16/18 over 6 more runs of each case | **$0.01** | 5 s | Served by Wafer with no reasoning. It caught the bugs every time; its errors were false fails ("if X does not exist..."). At temperature 0 it was no better, and cost 7× more |
| `google/gemini-4-argon` | 3/3 | $0.08 | 37 s | |
| `anthropic/claude-sonnet-5.5` | 3/3 | $0.12 | 38 s | Found the most issues in the buggy change |
| `xiaomi/mimo-v2.6-pro` | 3/3 | $0.04 | **26 min** | Reasoned for up to 25K tokens: too slow to review |

Before this setting, the same DeepSeek model was served by Alibaba, which ignored every reasoning budget (16–32K+
tokens). The privacy setting removed that provider from routing. **Provider behaviour is part of a model's
measured fitness, so calibration results are dated and redone when they get old.**

### 7. Overrides: `aios/models.toml` (tool-wide) and `[models]` in `.aios/project.toml` (per project)
- **`block`**: a model, the roles it is blocked from, a reason, and a review date. Use it for measured problems only.
- **`family`**: merges models into one family for P8 (for example a fine-tune of another vendor's model).
- **Spec `pin`** (unchanged): the Lead forces a model for one task, which raises a LEAD flag.

There is no `allow` list, and no model is assigned to a role.

### 8. The record explains the choice
`routing.roles` records the following for each role that ran:
- model, family and level;
- the score and price at that moment;
- the estimated cost;
- why it won ("cheapest of N candidates at mid").

`author` and `verifier` stay for older readers. `record_schema` becomes 2, and readers handle both versions.

### 9. Freshness
The joined catalog (usable ids, scores, prices and capabilities) refreshes automatically when it is more than 24
hours old. Offline, aios uses the last cache and says so.

## Consequences
- **Gains:**
  - New models enter on their own.
  - Every choice can be explained, and the explanation is recorded.
  - Prices and scores stay current.
  - Seniority words (junior/mid/senior) replace the opaque tiers.
- **Costs:**
  - The adversarial tester and the security reviewer add spend on risky tasks; policy gates when they run.
  - A model has to be calibrated before it can review.
  - Choices now depend on OpenRouter's benchmark data. Unscored models are simply not candidates, which fails safe.
  - Artificial Analysis must be credited wherever its scores are shown.
- **Contracts:**
  - `architecture/contracts/roster.schema.md` is replaced by `models.schema.md`, which covers the override file.
  - `record.schema.md` gains `routing.roles`, and the schema version becomes 2.
  - `project.schema.md` gains `[models]` and the budget fields.

## Alternatives considered
- **Keep a curated roster and refresh it more often.** It still needs a human to admit every release, and it already
  went wrong.
- **OpenRouter's own Auto Router.** It is opaque, ranks by popularity, and its scores are not in the API.
- **Scraping benchmark sites:**
  - SWE-bench bash-only stopped updating in February 2026 and is non-commercial;
  - vals.ai has no API;
  - LMArena measures preference.

  OpenRouter's keyed data is the only one that needs no name mapping.
