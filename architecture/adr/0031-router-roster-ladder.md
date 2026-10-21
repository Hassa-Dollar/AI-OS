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
