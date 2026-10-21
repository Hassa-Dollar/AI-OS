# AI-OS

An AI development orchestrator.
- **One key:** a single OpenRouter API key covers every model.
- **Local routing:** a local decision model (Clef, via Ollama) sends each task to the cheapest model that can do it.
- **One loop:** spec → branch → sandboxed worker → cross-family verification → merge, on any target repo, from web
  apps to embedded.

> **v2 is being rebuilt.** The v1 system (bash engine, fixed OpenCode-Go catalog, and the Shrink product, now in its own
> repo) is preserved at tag [`v1-final`](https://github.com/Hassa-Dollar/AI-OS/tree/v1-final). Decisions live in
> [`architecture/adr/`](architecture/adr/), and the lessons from v1 in [`docs/history/`](docs/history/).

License: [MIT](LICENSE).
