+++
id = "component-toolchain-setting"
title = "Each component declares its toolchains; the old profile label is retired"
files_allowed = ["aios/toolchains.py", "aios/config.py", "aios/cli.py", ".aios/project.toml", "tests/test_toolchains.py", "tests/test_config.py", "tests/test_cli.py", "tests/test_budget.py", "tests/test_calibrate.py", "tests/test_dispatch.py", "tests/test_fix.py", "tests/test_gate_run.py", "tests/test_land.py", "tests/test_status.py"]
contracts = ["architecture/contracts/project.schema.md"]
depends_on = ["comments-cli-harness-run"]
blast_radius = "medium"
kind = "feature"
budget_usd = 0.6
+++

## Goal
Read ADR-0035 and the `toolchain` lines of the project contract. A component in `.aios/project.toml` now says which
toolchains it needs, each with the oldest version it accepts, for example `toolchain = { node = "22" }`. This
replaces the `profile` label, which nothing reads. Two later tasks build on it: `aios init` learns more stacks, and
`aios doctor` proves each toolchain inside the sandbox and installs Node.

## Context
- **Standard library only**; ASCII source; fail loud. Follow `AGENTS.md`: the comment rule (a new module gets a
  section map and section headers; keep the maps and docstrings of the files you touch true), and never compress code
  to fit a line cap.
- **`aios/config.py`:**
  - `Component` has a required `profile: str`.
  - `_component(t, where)` lists the allowed keys and reads each one with
    `_get(table, key, kind, where, default, required)`. It raises `ConfigError` for anything wrong.
  - The keys that ADR-0034 retired show the warning pattern:
    `print(f"warning: ... was retired by ADR-0034 and is ignored", file=sys.stderr)`.
- **`aios/cli.py`:**
  - `PROJECT_TEMPLATE` writes `profile = "{profile}"`.
  - `detect_checks(root)` returns `("node", [...])`, `("python", [...])` or `("", [])`.
  - `cmd_init` uses `args.profile`, and `main` defines the `--profile` flag.
- **Nine test files write `profile = "..."` in their project fixtures.**
  - In seven of them the line stands alone: `tests/test_budget.py`, `tests/test_calibrate.py`,
    `tests/test_dispatch.py`, `tests/test_fix.py`, `tests/test_gate_run.py`, `tests/test_land.py`,
    `tests/test_status.py`.
  - In `tests/test_config.py` and `tests/test_cli.py`, the fixtures are one-line strings with `\n` inside, and some
    tests read `components[0].profile`.

## Required changes
1. **New module `aios/toolchains.py`:**
   ```python
   @dataclass(frozen=True)
   class Toolchain:
       name: str
       version_cmd: tuple[str, ...]  # prints the version; run inside the worker sandbox
       default: str                  # the minimum `aios init` proposes when the repo names none
       fix: str                      # how the operator installs it when aios cannot

   KNOWN: dict[str, Toolchain]       # the five below, keyed by name
   VERSION_RE = re.compile(r"^\d+(\.\d+)*$")   # the shape of a declared minimum

   def version_of(text: str) -> tuple[int, ...] | None: ...
   def meets(found: tuple[int, ...], minimum: str) -> bool: ...
   ```

   | name | version_cmd | default | fix |
   |---|---|---|---|
   | `node` | `node --version` | `22` | `aios doctor --fix` |
   | `python` | `python3 --version` | `3.11` | `sudo apt install python3` |
   | `rust` | `cargo --version` | `1.75` | `sudo apt install rustc cargo (rustup's ~/.cargo is invisible to workers)` |
   | `go` | `go version` | `1.22` | `sudo apt install golang-go` |
   | `platformio` | `pio --version` | `6` | `install PlatformIO Core where workers can see it, e.g. /usr/local/bin/pio` |

   - `version_of` returns the first run of digits joined by dots in `text`, as a tuple of ints, or None when there is
     none. For example, `"v22.23.4"` gives `(22, 23, 4)` and `"go version go1.23.4 linux/amd64"` gives
     `(1, 23, 4)`.
   - `meets` is True when `found >= tuple(int(x) for x in minimum.split("."))`.
2. **`aios/config.py`:**
   - In `Component`, replace `profile` with `toolchain: dict[str, str]`, defaulting to an empty dict
     (`field(default_factory=dict)`). Update its docstring.
   - `_component` reads an optional `toolchain` table. Each key must be in `toolchains.KNOWN`, and each value a
     string that matches `VERSION_RE`. Otherwise raise a `ConfigError` that names the problem, for example
     `"<where>: toolchain 'nodejs' is unknown; known: go, node, platformio, python, rust"`.
   - `profile` is still accepted and ignored. Print one warning to stderr:
     `warning: <where> 'profile' was retired by ADR-0035 and is ignored; declare toolchain = { ... } instead`.
3. **`aios/cli.py`, `aios init`:**
   - In the template, a `toolchain = {toolchain}` line replaces the `profile` line. `{toolchain}` is a TOML inline
     table such as `{ python = "3.11" }`, or `{}` when nothing was detected.
   - `detect_checks(root)` keeps its detection, but returns the toolchain table in place of the profile name:
     `{"node": KNOWN["node"].default}`, `{"python": KNOWN["python"].default}`, or `{}`.
   - Replace `--profile` with `--toolchain NAME=VERSION`, which can be repeated. When it is given, its values form
     the whole table and replace the detected one. A value without `=` raises
     `ConfigError("--toolchain must be NAME=VERSION, e.g. node=22")`. Unknown names and bad versions are caught by
     the `config.load_project` call `cmd_init` already makes.
   - The printed line names the table, for example
     `wrote .aios/project.toml (toolchain python 3.11, forge github); review it, then commit .aios/`, or
     `(toolchain none, ...)` when the table is empty.
4. **`.aios/project.toml`:** replace `profile = "python"` with `toolchain = { python = "3.11" }`. Keep every other
   line.
5. **Tests:**
   - **`tests/test_toolchains.py`:**
     - `version_of` on the five tools' real output (`v22.23.4`, `Python 3.12.3`,
       `cargo 1.82.0 (8f40fc59f 2024-08-21)`, `go version go1.23.4 linux/amd64`,
       `PlatformIO Core, version 6.1.16`), and on text with no version;
     - `meets` at, above and below the minimum, with one-part and two-part minimums.
   - **`tests/test_config.py`:**
     - a `toolchain` table is read;
     - an unknown name and a bad version are rejected;
     - a missing table gives `{}`;
     - `profile` is accepted with exactly one warning, which the test captures.
   - **`tests/test_cli.py`:**
     - `aios init` writes a `toolchain` table and no `profile`;
     - `--toolchain node=20` is written;
     - a `--toolchain` value without `=` raises.
   - **The seven files with a standalone line:** delete that line, and change nothing else in them:
     `sed -i '/^profile = /d' <file>`. The table is optional.
   - **In `tests/test_config.py` and `tests/test_cli.py`,** edit the one-line fixtures and the `.profile` reads by
     hand.

## Acceptance criteria
- `python3 -m unittest discover -s tests -t .` passes. Its output has no line with `retired by ADR-0035`: the one
  test of that warning captures it.
- `grep -rn "profile" aios/ .aios/project.toml tests/` finds only the retirement handling in `aios/config.py` and its
  test.
- Loading AI-OS's own project prints no warning.
  `python3 -c "from pathlib import Path; from aios import config; print(config.load_project(Path('.')).components[0].toolchain)"`
  prints `{'python': '3.11'}`.
- `aios/toolchains.py` has a section map and section headers.

## Out of scope
- detecting more stacks (the init-detects-stacks task);
- checking or installing toolchains (the doctor-checks-toolchains task);
- the harness and the sandbox;
- any other file.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
