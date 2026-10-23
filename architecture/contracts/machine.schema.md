# Contract: `~/.config/aios/config.toml` (this machine's operator settings)

**Owner:** Lead. **Implemented by:** `aios/config.py` and `aios/doctor.py`. **Decided in:** ADR-0034 §5.

This file holds the operator's own settings for this machine. It is never committed. The API key does not go here:
it lives in `~/.config/aios/credentials`, with mode 0600.

```toml
schema = 1

[budget]
per_month_usd = 20.0   # asked at first setup ("How much do you want to spend per month?")
```

Rules:
- **First setup** (`aios doctor --fix`) asks for `per_month_usd` when the file has none. It then tells the operator to
  set the same amount as the OpenRouter key's limit, with a **monthly** reset. `aios doctor` warns when the key's limit
  or reset period differs.
- **Spending.** The budget governor stops work when it would cross the monthly budget. It reads the key's `usage_monthly`
  and `limit_remaining`. The per-day and per-task caps in `.aios/project.toml` still apply.
- **Model choice.** A candidate whose estimated cost for the task is above what the budgets allow is skipped
  (ADR-0034 §4).
- Unknown keys are errors.
