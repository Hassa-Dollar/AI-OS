+++
id = "monthly-budget-setup"
title = "Setup asks for a monthly budget; aios doctor checks the key's limit matches it"
files_allowed = ["aios/config.py", "aios/doctor.py", "tests/test_config.py", "tests/test_doctor.py"]
contracts = ["architecture/contracts/machine.schema.md"]
blast_radius = "medium"
kind = "feature"
budget_usd = 0.5
+++

## Goal
The operator decides how much aios may spend per month. On first setup, aios:
- asks for that amount;
- stores it in the machine config;
- tells the operator to set the same amount as the OpenRouter key's limit, with a monthly reset.

After that, `aios doctor` warns when the two disagree. Enforcing the budget is the next task.

## Context
- **Standard library only**; ASCII source; fail loud. Follow `AGENTS.md`, including its comment rule (a section map,
  section headers with From/To lines, and one-line docstrings).
- **Contract:** `architecture/contracts/machine.schema.md`. Read it.
- **Paths:** `config.paths()` returns `Paths(config, cache, state, data)`. The machine config file is
  `<config>/config.toml`, which is `~/.config/aios/config.toml`.
- **`doctor.check_key(p, base)`** reads `GET <base>/key`. The response holds `limit`, `limit_remaining`,
  `limit_reset` (`"monthly"`, `"weekly"`, `"daily"` or null) and `usage_monthly`.
- **`doctor.run()`** returns a list of `Check(status, name, detail, fix)`. `doctor.main(fix=...)` prints them, and
  counts only `FAIL` rows as failures. The status `WARN` is new: it is printed but does not fail.

## Required changes
1. **`aios/config.py`:**
   ```python
   @dataclass(frozen=True)
   class Machine:
       per_month_usd: float | None = None

   def machine_file(p: Paths) -> Path: ...                 # <config>/config.toml
   def load_machine(p: Paths) -> Machine: ...              # a missing file gives Machine()
   def save_machine(p: Paths, m: Machine) -> Path: ...     # writes `schema = 1` and `[budget] per_month_usd = X`
   ```
   `load_machine` validates the file against the contract. It raises `ConfigError` on any of:
   - a `schema` other than 1;
   - unknown keys;
   - a `per_month_usd` that is not a positive number.
2. **`aios/doctor.py`:**
   - **`main(fix=True, ask=input)`.** When `load_machine(p).per_month_usd` is None:
     - ask `How much do you want to spend per month on models, in USD? `, and keep asking until the answer is a
       positive number;
     - save it;
     - print:
       `Now set your OpenRouter key's credit limit to $<X> with a monthly reset (https://openrouter.ai/settings/keys). aios reads that limit to know what is left this month.`

     If `ask` raises `EOFError`, the session is not interactive. Then print how to write the file by hand, and go on.
   - **A new check, `monthly budget`.** It is added to `run()` and uses the same `/key` response as `check_key`.
     Refactor so that `run()` makes only one `GET /key`.
     - **FAIL** when `per_month_usd` is not set. Fix: `run 'aios doctor --fix'`.
     - **WARN** when the key's `limit` differs from `per_month_usd` by more than $0.01, or `limit_reset` is not
       `"monthly"`. The detail shows both values. Fix: `set the key's limit to $<X> with a monthly reset`.
     - **PASS** otherwise, with `$<usage_monthly .2f> of $<per_month .2f> spent this month`.

## Acceptance criteria
- `tests/test_config.py` and `tests/test_doctor.py` (temp dirs, the fake HTTP server from `tests/helpers.py`, never
  the network, never the real `~/.config`) cover:
  - `load_machine` / `save_machine`: a round trip, a missing file, and each validation error;
  - `doctor --fix`: it asks once with a fake `ask`, saves the answer, prints the instruction, re-asks after an invalid
    answer, and handles the non-interactive path;
  - each status of the new check: FAIL, WARN for the limit, WARN for the reset, and PASS;
  - that `run()` makes exactly one `/key` request.
- `python3 -m unittest discover -s tests -t .` passes.
- `aios/config.py` has at most 185 and `aios/doctor.py` at most 140 non-blank, non-comment lines.

## Out of scope
Enforcing the budget (the budget-governor task) and any other file.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
