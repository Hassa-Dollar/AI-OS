# ADR-0035: Each component declares its toolchains, and aios proves them inside the sandbox

- **Status:** Accepted
- **Date:** 2026-10-24
- **Deciders:** Lead + human operator
- **Supersedes:** the `profile` key of the project contract (ADR-0030).

## Context
- **The `profile` key is a label nothing reads.** Each component in `.aios/project.toml` carries `profile = "node"`
  or `"python"`. It points at an `aios/profiles/` folder that was never built. A project's real build knowledge is
  already in its own `setup` and `checks` commands.
- **Workers see only part of the machine.** A worker's sandbox sees the system directories (`/usr`, `/bin`) and
  aios's own toolchains folder (`<data>/toolchains/*/bin`, read-only). It cannot see anything installed under the
  operator's home, such as rustup's `~/.cargo` or pipx's `~/.local/bin`. Today a missing runtime shows up only as a
  failed attempt, after the money is spent.
- **aios must build anything, from web apps to firmware.** A project must be able to say what it needs, and aios
  must check it before the first worker starts.
- **The operator asked whether profiles were worth keeping.** The answer agreed on 2026-10-23:
  - drop the label;
  - each component declares the toolchain it needs, for example `node = "22"`;
  - `aios doctor --fix` installs it;
  - `aios init` learns more stacks.

## Decision
1. **The setting.** Each `[[components]]` entry may declare `toolchain`, a table from toolchain name to the oldest
   version it accepts, for example `toolchain = { node = "22" }` or `{ python = "3.12" }`. Versions are minimums,
   the way `engines.node`, `requires-python`, `go.mod` and `rust-version` already work.
2. **`profile` is retired.** aios still reads it and ignores it with one warning, so existing projects keep loading.
3. **The known toolchains live in aios** (`aios/toolchains.py`). Each entry gives:
   - the command that prints its version;
   - the version `aios init` proposes when the repo names none;
   - how to install it when aios cannot.

   The first set is `node`, `python`, `rust`, `go` and `platformio`. A name aios does not know is an error.
4. **Where a toolchain comes from.** Either the system directories, or aios's toolchains folder
   (`<data>/toolchains/<name>-<version>/bin`). Workers cannot see anything under the operator's home, so it doesn't
   count.
5. **`aios doctor` proves each toolchain inside the sandbox.** Inside a project, doctor runs each declared toolchain's
   version command in a worker sandbox, with no network and no home directory. It then compares the version printed
   with the declared minimum. If the toolchain is missing or too old, the check fails and names the fix.
6. **`aios doctor --fix` installs what aios can.**
   - **Node** comes first: the latest release of the declared major version, downloaded from nodejs.org. Its SHA-256
     must match the release's published checksum list, and it is unpacked into the toolchains folder.
   - **The other toolchains:** the fix line names the system command, for example `sudo apt install golang-go`.

   More installers are added when a project needs them.
7. **`aios init` proposes, and the operator decides.** init reads the repo's marker files: `platformio.ini`,
   `Cargo.toml`, `go.mod`, `package.json`, and `pyproject.toml` or its peers. It proposes the toolchain table, the
   setup and the checks, and writes them for the operator to review before committing.

## Consequences
- A project's runtime needs are committed with it and reviewed like code. An aios update cannot quietly change them.
- A worker never starts on a machine that cannot run the project's checks, because `aios doctor` says so first.
- Every installed toolchain stays on the worker's PATH, as today. Two installed versions of one toolchain would be
  ambiguous. Choosing per component waits until a machine needs two versions.
- **Dependency caches.** Node's dependencies land in the worktree (`node_modules`), and the npm and pip caches are
  already redirected to aios's package cache. Rust, Go and PlatformIO keep their caches under the home directory,
  which the sandbox replaces with an empty `/tmp`. So their dependencies don't survive from setup (which has network)
  to the worker (which has none). Their setup must use aios's package cache before aios can build those projects.
  That comes with the first such project.
- **Firmware projects** declare `platformio`. Builds and host tests run in the sandbox. Flashing real hardware stays
  HUMAN-REQUIRED (doctrine).
