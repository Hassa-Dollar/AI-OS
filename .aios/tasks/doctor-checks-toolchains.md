+++
id = "doctor-checks-toolchains"
title = "aios doctor proves each component's toolchains inside the sandbox, and --fix installs Node"
files_allowed = ["aios/doctor.py", "tests/test_doctor.py"]
contracts = ["architecture/contracts/project.schema.md"]
depends_on = ["component-toolchain-setting"]
blast_radius = "medium"
kind = "feature"
budget_usd = 0.8
+++

## Goal
Read ADR-0035, sections 4 to 6. A worker sees only the system directories and aios's toolchains folder. Before any
worker starts, `aios doctor` must prove that each toolchain the project declares is there and new enough, from
inside that same sandbox. `aios doctor --fix` installs Node itself.

## Context
- **Standard library only**; ASCII source; fail loud. Follow `AGENTS.md`: the comment rule (add the new section to
  the section map, with its header), and never compress code to fit a line cap.
- **`aios/toolchains.py`** (component-toolchain-setting): `KNOWN[name]` with `version_cmd`, `default` and `fix`;
  `version_of(text)`; `meets(found, minimum)`.
- **`aios/config.py`:**
  - `find_root(path)` gives the project root, or None.
  - `load_project(root).components`: each has a `name` and a `toolchain`, for example `{"node": "22"}`.
  - `paths(env).data / "toolchains"` is aios's toolchains folder.
- **`harness.sandbox(p, network=False)`** returns `(args, env)`. `aios/gate.py` runs a check in it like this:
  `subprocess.run(["bwrap", *args, ..., "bash", "-c", check], env=env, capture_output=True, text=True, timeout=...)`.
  The sandbox puts every `<toolchains>/*/bin` on PATH.
- **`aios/doctor.py`:**
  - `Check(status, name, detail, fix)`;
  - `run(env)` builds the list of checks;
  - `main(fix, ask)` runs the fixes first, then prints the checks.
- **`tests/test_doctor.py`:** `doctor_run(...)` calls the real `run()`. Its tests must keep working without bwrap
  and without the network.

## Required changes
1. **`aios/doctor.py`, a new section "Toolchains"** (after "The checks"):
   1. **`check_toolchains(p, root: Path | None, runner=subprocess.run) -> list[Check]`:**
      - When `root` is None (not inside a project), return `[]`.
      - For each component, and each `name, minimum` in its `toolchain`, run `KNOWN[name].version_cmd` in a worker
        sandbox: `runner(["bwrap", *args, *version_cmd], env=env, capture_output=True, text=True, timeout=30)`.
      - The check's name is `<name> (<component>)`, for example `node (app)`.
      - **PASS** when the printed version meets the minimum. The detail reads, for example,
        `22.23.4, needs 22 or newer`.
      - **FAIL** when the command cannot run (a non-zero exit, `subprocess.TimeoutExpired`, or `OSError`), or prints
        no version. The detail is `not found inside the worker sandbox`, and the fix is `KNOWN[name].fix`.
      - **FAIL** when the version is older. The detail is `<found> is older than <minimum>`, and the fix is
        `KNOWN[name].fix`.
   2. **`install_node(p, major: int, fetch=_fetch, machine=platform.machine) -> Path`:**
      - `_fetch(url) -> bytes` reads a URL with a 300-second timeout.
      - The architecture is `x64` for `x86_64` and `arm64` for `aarch64`. Any other raises `ConfigError`.
      - Read `https://nodejs.org/dist/latest-v<major>.x/SHASUMS256.txt`. Each line is `<sha256>  <file name>`. Find
        the line for `node-v<version>-linux-<arch>.tar.xz`. If there is none, raise `ConfigError`.
      - If `<toolchains>/node-v<version>-linux-<arch>` already exists, return its `bin` without downloading.
      - Otherwise, download the file from the same folder. If its SHA-256 differs from the listed one, raise
        `ConfigError`.
      - Unpack it with `tarfile.open(..., "r:xz").extractall(tmp, filter="data")` into a temporary folder inside the
        toolchains folder. Then rename the unpacked folder into place. On any failure, remove the temporary folder,
        so a failed install leaves nothing behind.
      - Return the new `bin` folder.
   3. **`run(env=os.environ, cwd: Path | None = None)`** adds
      `check_toolchains(p, config.find_root(cwd or Path.cwd()))` at the end of its list.
   4. **`main(fix=True)`,** before printing the checks: for each failing `node` check, print
      `installing Node <major> into <toolchains folder>...` and install Node. `major` is the first number of the
      declared minimum. Then run the checks again, so the printed rows show the result.
2. **`tests/test_doctor.py`** (temp dirs only; never the network, never bwrap):
   - `doctor_run(...)` passes a temp `cwd` outside any project, so the existing tests never reach a real project.
   - **`check_toolchains`,** with a temp project and a fake runner:
     - PASS for a new-enough version;
     - FAIL for an older one;
     - FAIL for a non-zero exit, a timeout, and output with no version;
     - the check name and the fix as above;
     - `[]` outside a project.
   - **`install_node`,** with a fake `fetch` serving a `SHASUMS256.txt` and a small `.tar.xz` built in the test (a
     folder holding `bin/node`):
     - the right file is chosen for `x86_64` and for `aarch64`;
     - the checksum is verified;
     - the folder is unpacked under the toolchains folder, and its `bin` is returned;
     - a checksum mismatch raises and leaves nothing behind;
     - an existing folder skips the download;
     - an unknown machine raises.
   - **`main(fix=True)`** installs Node when the node check fails. Use fakes for the check and the install.

## Acceptance criteria
- `python3 -m unittest discover -s tests -t .` passes, offline and without bwrap.
- `aios/doctor.py`'s section map lists the new section.

## Out of scope
- installers for Python, Rust, Go and PlatformIO (ADR-0035: they come when a project needs them);
- the sandbox and the harness;
- any other file.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
