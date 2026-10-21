# AGENTS.md — rules for any agent working on AI-OS itself

- **Language:** Python ≥3.11, **standard library only** in `aios/` (ADR-0023). No third-party imports at runtime.
- **Tests:** `python3 -m unittest`. New code needs tests. Tests use temp dirs and repos only, never the real
  `~/.config`, and never the network.
- **Scope:** edit only the files your task grants. A change to a contract or schema → stop and write `ESCALATE: <reason>`.
- **Size:** `aios/` has a line budget enforced in CI. Prefer deleting code to adding it.
- **Security:** this repo is public. Never read, log or commit secrets. Never pass large prompts as command-line arguments.
