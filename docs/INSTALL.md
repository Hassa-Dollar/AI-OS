# Install

AI-OS v2 needs **Python ≥ 3.11 and git**, plus **one OpenRouter key**. The router needs **Ollama**, and GitHub targets
need **`gh`**. The worker harness is installed by aios itself, into its own sandbox-ready location (ADR-0032).


## 1. Git and GitHub
```bash
git config --global user.name  "<you>"
git config --global user.email "<you@example.com>"
gh auth login            # HTTPS; scopes: repo, workflow
gh auth setup-git
```

## 2. OpenRouter key (one key for every model)
1. Create a key at <https://openrouter.ai/settings/keys> **with a credit limit**. That limit is the hard spend cap.
2. In <https://openrouter.ai/settings/privacy>, enable the data-policy filter so no provider that trains on prompts is
   ever used.
3. Store the key so it never lands in shell history and is never world-readable:
   ```bash
   mkdir -p ~/.config/aios && (umask 077; read -rs K && printf %s "$K" > ~/.config/aios/credentials)
   ```

## 3. Ollama + the router models
```bash
curl -fsSL https://ollama.com/install.sh | sh     # needs Ollama ≥ 0.35.1 for the System One API
ollama pull clef-flash                             # primary router (~10 GB on disk, sub-second answers)
ollama pull clef                                   # 27B second opinion for low-confidence cases (~20 GB)
```
With less than ~20 GB of VRAM, the 27B runs partly on the CPU. That is fine, because it is only consulted when
`clef-flash` is unsure (ADR-0031).

## 4. Sandbox and Python venv support (Linux / WSL2)
```bash
sudo apt install bubblewrap python3-venv
```
On WSL2, make sure Linux binaries come first in `PATH`. Windows `npm` or `node` under `/mnt/c` will not work.
`aios doctor` checks this.

## 5. AI-OS
```bash
git clone https://github.com/Hassa-Dollar/AI-OS ~/.local/share/aios/tool
export PATH="$HOME/.local/share/aios/tool/bin:$PATH"
aios doctor --fix                                       # checks everything above; installs the pinned harness
cd /path/to/your/project && aios init                   # writes .aios/project.toml
```
