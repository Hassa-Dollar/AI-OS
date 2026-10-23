# AI-OS

An AI development orchestrator for building software of any kind, from web apps to embedded firmware, at the lowest
cost that still gets work merged.

- **One key, every model.** A single OpenRouter API key reaches every current model, and new releases appear
  automatically. No list of allowed models: every model in the live catalog is a candidate (ADR-0034).
- **Roles, like a real team.** Implementer (junior, mid or senior), adversarial tester, reviewer, security reviewer.
  A local decision model (Clef, via Ollama) reads each task and sets the level. Each role then gets the model
  that is best for the price right now, frontier models included, within your monthly budget.
- **Spec → sandbox → verify → merge.** Each task runs in this loop:
  - A spec with executable acceptance criteria is the unit of work.
  - A worker implements it in a sandboxed git worktree, with no network, no home directory and no keys.
  - A model from a *different* family verifies the diff.
  - A code gate decides between auto-merge and review by the Lead or a human.
- **Your repo, your state.** AI-OS is a tool you point at any repo. Specs and per-task records (model, dollars, outcome)
  live in that repo's `.aios/` folder, so products can stay private (ADR-0030).

> **Status: v2 is under construction.** The v1 system (bash engine, fixed catalog, Shrink product) is preserved at tag
> [`v1-final`](https://github.com/Hassa-Dollar/AI-OS/tree/v1-final).

## Read next
- [`docs/OVERVIEW.md`](docs/OVERVIEW.md): **start here.** A plain-language tour: who does what, how one task flows
  through the files, and where the project stands.
- [`docs/INSTALL.md`](docs/INSTALL.md): setup (Python, git, one OpenRouter key, Ollama).
- [`docs/doctrine.md`](docs/doctrine.md): the principles, including P12 (cost-route to the cheapest *merged* result).
- [`architecture/`](architecture/): ADRs and contracts. Start at [`architecture/README.md`](architecture/README.md).
- [`docs/lessons.md`](docs/lessons.md): what v1 taught us, and how v2 enforces each lesson.

## License
[MIT](LICENSE)
