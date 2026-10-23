+++
id = "reviewer-calibration"
title = "aios models calibrate: measure whether a model judges known changes correctly before it may review"
files_allowed = ["aios/calibrate.py", "aios/cli.py", "tests/test_calibrate.py"]
contracts = ["architecture/contracts/models.schema.md"]
blast_radius = "medium"
kind = "feature"
budget_usd = 0.75
+++

## Goal
ADR-0034 section 6: a model may fill the **reviewer** role only after it has judged a set of known changes
correctly. Some of the changes have real bugs and some are correct. This task adds the measurement and its result
cache. Choosing reviewers from the cache comes in a later task.

## Context
- **Standard library only**; ASCII source; fail loud. Follow `AGENTS.md`, including its comment rule (a section map,
  section headers with From/To lines, and one-line docstrings).
- **The known changes are already in the repository**, written by the Lead, under `aios/calibration/<case>/`. Read
  `aios/calibration/README.md`. Each case folder holds:
  - `spec.md`: the spec the change was judged against;
  - `change.diff`: the change;
  - `case.toml`: `expected` (`"pass"` or `"fail"`), `note`, and one `[[checks]]` table per check (`command`, `exit`,
    `tail`).

  Do not edit these files.
- **The production reviewer call is `gate.verify(gw, model, spec_text, diff_text, checks)`.** It returns the verdict
  dict, including `verdict` and `usd`.
  - It raises `ValueError` for a malformed reply and `gateway.GatewayError` for an API failure.
  - Calibration must use exactly this call, so that what is measured is what runs in production.
- **The cache lives in the machine's cache dir:** `config.paths().cache`, which is `~/.cache/aios`.

## Required changes
1. **New `aios/calibrate.py`:**
   ```python
   CASES_DIR = Path(__file__).with_name("calibration")
   CACHE_NAME = "calibration.json"

   @dataclass(frozen=True)
   class Case:
       id: str
       expected: str
       spec_text: str
       diff_text: str
       checks: list[tuple[str, int, str]]

   @dataclass(frozen=True)
   class Judgment:
       case: str
       expected: str
       got: str
       right: bool
       usd: float
       secs: int
       note: str  # the first blocking item, or the error text

   def load_cases(directory: Path = CASES_DIR) -> list[Case]: ...
   def fingerprint(cases: list[Case]) -> str: ...  # sha256 over the verifier prompt text and every case's files
   def run(gw, model: str, cases: list[Case], *, repeat: int = 1, clock=time.monotonic) -> list[Judgment]: ...
   def save(p, model: str, judgments: list[Judgment], cases: list[Case], *, today: dt.date | None = None) -> None: ...
   def passed(p, model: str, cases: list[Case] | None = None, *, max_age_days: int = 30,
              today: dt.date | None = None) -> bool: ...
   ```
   - **`load_cases`** reads every sub-folder, sorted by name. A missing file, or an `expected` that is not `pass` or
     `fail`, raises `ValueError` naming the case.
   - **`run`** calls `gate.verify` once per case, `repeat` times each.
     - A `ValueError` or `GatewayError` gives a judgment with `got="error"`, which counts as wrong, and the error text
       in `note`.
     - It never stops early, so every case is measured.
   - **`save`** writes or updates the model's entry in `<cache>/calibration.json`:
     `{"date": "YYYY-MM-DD", "fingerprint": ..., "right": n, "total": n, "usd": total, "secs": total}`.
     It keeps other models' entries.
   - **`passed`** is true only when all of these hold:
     - the model has an entry;
     - `right == total`, and `total > 0`;
     - the entry is at most `max_age_days` old;
     - its fingerprint equals `fingerprint(cases or load_cases())`. Changing the prompt or the cases invalidates every
       old result.
2. **`aios/cli.py`:** add `aios models calibrate <model> [<model> ...] [--repeat N]`.
   - It builds the gateway with the project's privacy settings when inside a project, or with the defaults otherwise.
   - It prints one line per judgment:
     `<model> | <case> | want <expected> got <got> | RIGHT/WRONG | $<usd .4f> | <secs>s | <note, at most 100 chars>`.
   - Then one summary line per model: `<model>: <right>/<total> right, $<usd .4f>, <secs>s -> may review | may not review`.
   - It saves each model's result. It returns 0 if every model passed, otherwise 1.

## Acceptance criteria
- `tests/test_calibrate.py` (unittest, temp dirs, never the network) uses a **fake gateway**. Its `chat()` returns a
  canned verdict chosen by a marker in the prompt.
- It covers:
  - `load_cases` on the real `aios/calibration` folder: three cases, one expected to fail;
  - `load_cases` errors on a broken temp case;
  - `run`: right and wrong judgments, `repeat`, and an error that counts as wrong while the run continues;
  - `save` and `passed`: pass, one wrong, too old, a changed fingerprint, and another model's entry being kept;
  - the CLI's lines and exit code.
- `python3 -m unittest discover -s tests -t .` passes.
- `aios/calibrate.py` has at most 100 non-blank, non-comment lines.

## Out of scope
- Using the cache to choose reviewers (a later task);
- confirming fail verdicts and token budgets (a later task);
- editing `aios/calibration/`;
- any other file.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
