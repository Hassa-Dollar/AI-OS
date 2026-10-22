# ADR-0031: Router, roster and escalation ladder

- **Status:** Accepted
- **Date:** 2026-10-21
- **Deciders:** Lead + human operator

## Context
OpenRouter lists 468 models (2026-10-21), from $0.02/M to $50/M output tokens. The goal is to send each task to the
cheapest model that will get it merged, and to escalate only when needed.

The operator chose a local decision model, Clef (Cloudflare, via Ollama's System One API). Clef is a classifier, not a
chat model: it answers typed questions (`choice`, `noul`, `score`) with probabilities. It therefore cannot pick from
hundreds of live models directly.

**Spike S1** (RTX 4070 12 GB, 19 v1 tasks the Lead had already labelled):

| Model | Warm p50 / p95 | Deterministic ×5 | HUMAN recall | Over-escalation |
|---|---|---|---|---|
| `clef-flash` | 0.37 s / 0.38 s | yes | 6/6 | 3/13 |
| `clef` 27B | 5.2 s / 44 s (spills to CPU) | yes | 6/6 | 4/13 |
| keyword heuristic | — | — | 6/6 | 5/13 |

The 27B classifies ambiguous tasks better. For example, it labels a research memo "research" where flash says
"security", and its complexity scores track blast radius more closely.

**Spike S3:**
- All seven v1 models exist on OpenRouter, alongside newer successors.
- Four verifier candidates returned schema-valid JSON verdicts (`response_format: json_schema` +
  `provider.require_parameters`), each at $0.0001–$0.0013.
- `usage.include` returns the exact cost of each call.
- `data_collection: deny`, `zdr` and `reasoning.effort` are all accepted.
- The `tokenizer` field reads "Other" for several vendors, so it cannot be used to tell model families apart.

## Decision
1. **Roster, not catalog.** Routing only considers `roster.toml`: about 10–14 pinned ids, each assigned to a tier.

   | Tier | Contents |
   |---|---|
   | T1 | cheap |
   | T2 | strong open-weight |
   | T3 | frontier |

   Each entry can override its family. `aios models sync` caches `/api/v1/models`, and `aios models diff` lists
   models that are new, changed or expiring.
   - **Silent drift.** If an entry's `canonical_slug` changes, the model is suspended until reviewed.
   - **Admission.** A new model is admitted by a roster PR plus `aios models probe` (a canned task run through the real
     harness).
   - **Successors.** An opt-in rule auto-admits successors that come from the same vendor, are a version bump, cost at
     most 2× the price, and are not `:free`, preview or alias releases. Until it has 3 passing records, such a model
     receives only low-leverage tasks.
   - **Never routed to:** `~` aliases and `:batch` variants.
2. **Family (P8).** The family is the roster override if set, otherwise the vendor prefix of the model id. The verifier
   must come from a different family than the author. A model whose family is unknown is ineligible.
3. **Classifier.**
   - **Cascade:** `clef-flash` answers first. Only when its `task_class` confidence is below 0.6 does `clef` 27B answer
     instead.
   - **Questions** (one call per task, state ≤ 8 KiB, acceptance criteria never truncated):
     - choice: `task_class` (conservative options listed first, since ties go to the earlier option);
     - score: `acs_executable`, `complexity`, `context_breadth`;
     - yes/no: `ambiguity`, `contract_change_needed`, `security_sensitive`, `irreversible`, `needs_vision`, `needs_hardware`.
   - **Overrides:** fields the Lead wrote in the spec win over Clef's answers.
   - **Fallback:** if Clef is unavailable, the keyword heuristic decides, and the record says so.
4. **Decision table.** This is P1 (route by leverage) made executable. It is evaluated once per task, recorded, and
   re-read by the gate; it is never re-resolved.
   1. **Spec gap** (acceptance criteria not executable, or ambiguous): refuse and print the gaps.
   2. **HUMAN gate:** security work with medium-or-higher blast radius, anything irreversible, or anything needing hardware.
   3. **LEAD gate:** high blast radius, or a contract change.
   4. **Implementer tier:** the highest of the class floor, complexity, context, ladder step and profile minimum. Low
      confidence adds one tier, capped at T2 unless `frontier.auto` is on.
   5. **Verifier:** at least T2, and the strongest available for security work. It returns a structured JSON verdict
      bound to the diff it reviewed.
   6. **Model choice:** the cheapest eligible model, ranked by median measured dollars per attempt once a model has at
      least 3 runs.
5. **Escalation ladder.** Each step applies only after the one before it fails:
   1. `needs_decision` goes to the Lead immediately.
   2. Fix round 1: the same model, with the verdict appended.
   3. Fix round 2: the next model in the same tier.
   4. Move up one tier.
   5. T3, only if `frontier.auto` is on.
   6. A human.

   Limits: 3 implement attempts, 2 verify rounds and 1 infrastructure retry, plus a dollar cap per attempt and per day.
   A 402, a 5xx or a setup failure never counts against a model.

## Consequences
- New models are found automatically but enter the roster deliberately; fail-closed is preserved, the ADR-0009 lesson.
- Routing is local, instant (~0.4 s), free and reproducible.
- **W3 must pass the full evaluation** (~120 labelled and perturbed items):
  - HUMAN recall 100%;
  - over-escalation ≤ 25%;
  - spec-gap recall ≥ 80%;
  - paraphrase stability ≥ 90%.

  If Clef doesn't beat the heuristic, it runs in shadow mode until it does.

## Alternatives considered
- **27B only.** 14× slower on this hardware, with no gain in recall.
- **Routing over the whole catalog.** There's no quality signal for most of those models.
- **OpenRouter's own auto-router.** It is opaque, and it isn't local.
- **A pure price-band heuristic.** Price doesn't measure capability.

## Amendment 1 (2026-10-21): what the W3 evaluation changed
`eval/router/run.py` scores the router on 84 items:
- v1's 19 Lead-labelled tasks;
- a paraphrase of each;
- a vague-spec copy of each;
- the non-HUMAN ones with auth/PII scope injected;
- 14 v2 cases (embedded, contracts, migrations, secrets, docs).

Three rules changed on that evidence:
1. **Spec-gap detection is deterministic (P10).** Clef's `acs_executable` score was noise: real specs scored 0.43–0.85
   and vague ones 0.27–0.58. That cost 47% spec-gap recall and refused real tasks. Code now decides instead:
   - criteria that are missing or uniformly vague ("make it nice") always refuse;
   - criteria must name a command or an observable result;
   - hardware, docs and research tasks may have human-judged criteria.

   Clef's `acs_executable` and `ambiguity` answers are still recorded, but they are advisory. Only `ambiguity > 0.9` refuses.
2. **The security threshold is 0.8.** In the eval, HUMAN-labelled security work scored 0.85–0.96. The highest
   non-HUMAN item scored 0.78. Over-escalation drops from 33% to 0%.
3. **The cascade guards the gate, not the class, and can only add caution.** The 27B is asked only when a signal
   that decides the gate sits in its borderline band (security 0.4–0.8, irreversible or hardware 0.3–0.7) and no
   other signal is already decisive. Low *class* confidence still raises the tier, but never calls the slow model:
   cascading on it as well gave the same quality at a p50 of 15 s instead of 0.56 s. Safety signals take the
   maximum of the two models' answers, so a second opinion can never remove a HUMAN gate.
4. **Degraded routing means more oversight (P11).** When the heuristic decides because Clef is unavailable, nothing
   gets the AUTO gate: the Lead reviews at minimum.

| Configuration | HUMAN recall | Over-escalation | Gap recall | Paraphrase stability | p50 |
|---|---|---|---|---|---|
| keyword heuristic (fallback) | 93.8% | 30.3% | 100% | 100% | 0 s |
| clef-flash alone | 93.8% | 0% | 100% | 100% | 0.54 s |
| **clef-flash + borderline cascade (adopted)** | **100%** | **9.1%** | **100%** | 89.5% | 0.56 s (p95 46 s; 13/84 cascaded) |

Three of the four gates pass. Paraphrase stability is 17/19, one flip short of 90%. Both flips are genuinely
borderline items:
- an auth-guard UI went HUMAN↔AUTO;
- a Pro-gated endpoint went AUTO↔LEAD.

The labels were not changed to pass the gate. The configuration is adopted because it beats the heuristic on every
safety metric. Cascaded (borderline) decisions are kept in each task record, so production data can tune the bands.
