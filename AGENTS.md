# AGENTS.md — rules for any agent working on AI-OS itself

- **Language:** Python ≥ 3.11, **standard library only** in `aios/` (ADR-0023/0029). No third-party imports at runtime.
- **Tests:** `python3 -m unittest discover -s tests -t .` must pass. New code needs tests.
  - Tests use temp dirs and repos only.
  - Never touch the real `~/.config`, and never use the network.
- **Scope:** edit only the files your task grants. If you need to change a contract (`architecture/contracts/`) or
  a schema, stop and reply `ESCALATE: <reason>`.
- **Size:** `aios/` has a line budget enforced in CI (ADR-0029). Prefer deleting code to adding it.
- **Security:** this repo is public. Never read, log or commit secrets. Never pass large prompts as command-line
  arguments.
- **Formats:** humans write TOML (specs and config), aios writes JSON (records). See `architecture/contracts/`.
