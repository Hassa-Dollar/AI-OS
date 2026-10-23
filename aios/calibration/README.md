# Reviewer calibration cases

Each folder is a change whose correct verdict is known. `aios models calibrate <model>` asks the model to judge every
case with the real reviewer prompt (`aios/prompts/verifier.md`). A model may fill the reviewer role only after it
judges every case right (ADR-0034 section 6).

- `spec.md`: the spec the change was judged against.
- `change.diff`: the change itself.
- `case.toml`: `expected` (`pass` or `fail`), a one-line `note`, and the `[[checks]]` that ran (command, exit code,
  output tail).

These are real changes from this repository's history. Add a case when a reviewer gets something wrong in practice.
