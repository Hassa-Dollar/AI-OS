# AGENTS.md — rules for any agent working on AI-OS itself

- **Language:** Python ≥ 3.11, **standard library only** in `aios/` (ADR-0023/0029). No third-party imports at runtime.
- **Tests:** `python3 -m unittest discover -s tests -t .` must pass. New code needs tests.
  - Tests use temp dirs and repos only.
  - Never touch the real `~/.config`, and never use the network.
- **Scope:** edit only the files your task grants. If you need to change a contract (`architecture/contracts/`) or
  a schema, stop and reply `ESCALATE: <reason>`.
- **Size:** `aios/` has a line budget enforced in CI (ADR-0029). Prefer deleting code to adding it.
  - **Never compress code to fit a line cap.** Do not join lines, write one-line `if`/`try`/`for` statements, use
    walrus assignments or lambdas instead of plain code, or reformat code your task does not need to change.
    Readable code matters more than the cap: if the cap is too tight, stop and reply `ESCALATE: <reason>`.
- **Security:** this repo is public. Never read, log or commit secrets. Never pass large prompts as command-line
  arguments.
- **Formats:** humans write TOML (specs and config), aios writes JSON (records). See `architecture/contracts/`.
- **Name tasks by their descriptive id** (for example `approve-and-land`) in comments, docstrings and commit messages.
  Never use codes such as `D2b`.
- **ASCII only in source code and comments.** Some model/provider paths mis-encode non-ASCII (mojibake).
- **Comments: a section map plus section headers** (the operator's chosen style). Every module in `aios/` has three
  things.
  1. **A module docstring** that says what the file is for, followed by a numbered **section map**. The map has one
     line per section, saying what the section does and its data flow (`input -> output`).
  2. **A header before each section:** `# --- N. <name> ---`, then a `# From: ...` line and a `# To: ...` line saying
     where the section's data comes from and where it goes.
  3. **A one-line docstring on every function**, saying what it takes and what it returns.

  Don't comment every block. `#` comments don't count against the line budget, but docstrings do, so keep each
  docstring to one line. Comments must stay true, so update them together with the code. Example:
  ```python
  """Gate: decides whether a task's branch may merge.

  Sections:
    1. What changed   git diff -> changed files, authored lines
    2. Run checks     the component's commands -> (command, exit code, output tail)
  """

  # --- 2. Run checks ---------------------------------------------------------------------
  # From: the component's `checks` in .aios/project.toml
  # To:   one (command, exit code, output tail) per check, for the verifier and the record
  def run_checks(paths, wt, component):
      """Run each check in the sandbox; return one result per check."""
  ```
