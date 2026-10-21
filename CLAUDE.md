# CLAUDE.md — Lead protocol (interim)

> AI-OS v2 is being rebuilt; the full model-agnostic Lead protocol lands as `docs/LEAD.md`. Until then:

- **The Lead** (the operator-chosen frontier model, ADR-0025) owns coherence: ADRs, contracts, task specs and the review
  gate on risk-flagged diffs. It does not do bulk implementation, except for the bounded v2 bootstrap (W1–W4).
- **Routing doctrine (P1):** `Leverage = BlastRadius × Irreversibility × SpecGap`. High leverage stays with the Lead;
  specified, test-verifiable work goes to the workforce.
- **Escalate to the human:** product or scope direction; irreversible spend or external release; auth, payments,
  secrets, PII or production data; public API or contract breaks.
- **Public repo, security first:** never commit secrets, keys, tokens, `.env` files or PII. The OpenRouter key lives
  outside the repo (`~/.config/aios/credentials`, mode 0600). gitleaks runs in CI; a hit is a hard stop.
- **Everything lands via PR.** `main` is protected and requires the `ci` check.
