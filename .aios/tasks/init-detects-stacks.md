+++
id = "init-detects-stacks"
title = "aios init detects Node, Python, Rust, Go and PlatformIO projects and proposes their toolchains and checks"
files_allowed = ["aios/toolchains.py", "aios/cli.py", "tests/test_toolchains.py", "tests/test_cli.py"]
contracts = ["architecture/contracts/project.schema.md"]
depends_on = ["component-toolchain-setting"]
blast_radius = "low"
kind = "feature"
budget_usd = 0.6
+++

## Goal
Read ADR-0035: section 7, and the "Dependency caches" consequence. `aios init` reads a repo's marker files and
proposes the toolchain table, the setup and the checks. Any project in the five known stacks can then be onboarded
without hand-written commands. The operator still reviews the file before committing it.

## Context
- **Standard library only** (`tomllib` and `json` read the marker files); ASCII source; fail loud. Follow
  `AGENTS.md`: the comment rule (keep the section maps true), and never compress code to fit a line cap.
- **`aios/toolchains.py`** (component-toolchain-setting): `KNOWN[name].default`, `VERSION_RE`.
- **`aios/cli.py`:**
  - `detect_checks(root)` returns `(toolchain table, checks)` for Node (`package.json`) and Python
    (`pyproject.toml`, or a `tests/` directory).
  - `cmd_init` writes `PROJECT_TEMPLATE`. `--toolchain` and `--check` override what detection proposes.

## Required changes
1. **`aios/toolchains.py`, a new section "Detection":**
   ```python
   @dataclass(frozen=True)
   class Detected:
       toolchain: dict[str, str]
       setup: list[str]
       checks: list[str]

   def detect(root: Path) -> Detected: ...
   ```
   It uses the first row whose marker exists at the repo root:

   | Marker | toolchain, version from | setup | checks |
   |---|---|---|---|
   | `platformio.ini` | `platformio`: the default | none | `pio run`, plus `pio test -e native` when the file has an `[env:native]` section |
   | `Cargo.toml` | `rust`: `[package] rust-version` | none | `cargo test` |
   | `go.mod` | `go`: the `go` directive line | none | `go vet ./...`, `go test ./...` |
   | `package.json` | `node`: `engines.node` | `npm ci --no-audit --no-fund`, only when `package-lock.json` exists | `npm run -s <name>` for each of `lint`, `typecheck` and `test` found in `scripts` |
   | `pyproject.toml`, `setup.py`, `requirements.txt`, or a `tests/` directory | `python`: `[project] requires-python` | none | `python3 -m unittest discover -s tests -t .` |
   | none of these | `{}` | none | none |

   - **The version** is the first run of digits joined by dots in that field. For example, `">=20.6"` gives
     `"20.6"`, and the go directive `go 1.23.0` gives `"1.23.0"`. When the field is missing or holds no version, use
     `KNOWN[name].default`.
   - A marker that exists but cannot be parsed raises `ConfigError` naming the file.
   - Rust, Go and PlatformIO get no setup, because their dependency caches don't yet survive into the worker's
     sandbox (ADR-0035).
2. **`aios/cli.py`:**
   - `cmd_init` uses `toolchains.detect`. Remove `detect_checks`.
   - When detection proposes setup commands, the template writes a `setup = [...]` line right after the `toolchain`
     line. Otherwise it writes none.
   - When the detected checks are empty and `--check` is not given, `cmd_init` raises the existing "could not detect
     how to verify changes here" error.
3. **Tests:**
   - **`tests/test_toolchains.py`:**
     - one temp repo per row of the table, each asserting the toolchain table, the setup and the checks;
     - each marker's version read from its field, and the default when the field is missing;
     - an `[env:native]` section adding `pio test -e native`;
     - a `package.json` without a lockfile giving no setup;
     - a broken `Cargo.toml` raising `ConfigError`;
     - `platformio.ini` winning when a `package.json` exists too.
   - **`tests/test_cli.py`:**
     - `aios init` in a temp Cargo repo writes `toolchain = { rust = "..." }` and `checks = ["cargo test"]`, and the
       file loads;
     - in a temp Node repo with a lockfile, it writes the `setup` line.

## Acceptance criteria
- `python3 -m unittest discover -s tests -t .` passes.
- `grep -n "detect_checks" aios/cli.py` finds nothing.

## Out of scope
- `aios doctor` and installing toolchains (the doctor-checks-toolchains task);
- dependency caches for Rust, Go and PlatformIO;
- any other file.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
