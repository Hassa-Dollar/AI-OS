# ADR-0032: Worker harness — mini-swe-agent in bubblewrap, chosen by a bake-off

- **Status:** Accepted
- **Date:** 2026-10-21
- **Deciders:** Lead + human operator

## Context
A model API key gives us models, not an agent loop. Something has to let a model read files, edit them, run tests
and iterate. The operator dropped the OpenCode-Go subscription and asked that we integrate a proven open-source
harness rather than build one.

**Desk review (2026-10-21):**
- Aider is in maintenance mode, with no feature release since August 2025.
- Pi is TypeScript, and its OpenRouter support is unverified.
- OpenHands SDK is active, but it's a heavy, Docker-centric platform.
- That left two finalists:
  - **OpenCode**: the free MIT tool with an OpenRouter key; 219K stars.
  - **mini-swe-agent**: MIT, about 100 lines; the reference harness of the SWE-bench and vals.ai leaderboards.

Scale's SWE-Bench Pro v2 study found the strongest open-weight models perform on par across harnesses, and advised:
"pick the harness for the bill, not the score".

**Bake-off** (`eval/harness/`, results in `results.json`):
- **Tasks:** three real ones, all of which needed doing anyway:
  - SH-1 and SH-2: Shrink API fixes;
  - AI-1: `aios/spec.py`.
- **Grid:** 2 harnesses × 2 models (GLM-5.3, DeepSeek V4 Pro), giving 12 runs.
- **Conditions:** each run used a fresh copy of the repo and a bubblewrap sandbox, and the same task text went to both harnesses.
- **Scoring:** acceptance checks the agent never saw, plus the project's own checks and a scope audit.
- **Cost:** the OpenRouter `/key` usage delta, with runs sequential so each delta belongs to one run.

| | OpenCode | mini-swe-agent |
|---|---|---|
| Solved | **6/6** | **6/6** |
| Spend · $/solved | $1.64 · $0.274 | $1.78 · $0.297 |
| Median $/run | $0.230 | $0.202 |
| Cheaper in head-to-head pairs | 3 of 6 | 3 of 6 |

Per-pair costs swung up to 15× in **both** directions on the same task and model. The paired mean difference is
about $0.02 per task, deep inside the noise. Code quality followed the **model**, not the harness: GLM-5.3 wrote
the cleaner code under both harnesses.

## Decision
The pre-agreed rule was: the lowest $ per solved task wins, unless pass rates differ by more than 10 points, and a
tie goes to the safer harness. The result is a tie, so we adopt **mini-swe-agent**, for three reasons:
1. **Isolation by design.** The model loop runs outside the sandbox. Commands the model issues run inside
   bubblewrap with **no network, no home directory and no key**, and in their own PID namespace. OpenCode needs
   network inside its sandbox, because its model calls happen in-process.
2. **Exact cost accounting.** It records OpenRouter's `usage.cost` for every call, which the record contract
   requires. OpenCode's own estimates were off by up to 2× ($0.112 reported against $0.057 actually charged).
3. **A small, stable surface.** OpenCode removed a flag v1 relied on between versions.

### How it runs
- **Install.** The pinned version lives in its own venv under `~/.local/share/aios/harness/`, from `aios/harness.lock`
  (exact versions of every dependency, installed with `--no-deps`). Upgrades are a `sensitive` PR that re-runs a
  bake-off subset.
- **Model class.** `openrouter` makes direct calls through `requests`. litellm is installed but never on the model path.
- **Prompt.** The task text goes into the generated config's `instance_template`, **never into argv**. During the
  bake-off a model's `pkill -f` matched a prompt passed on the command line and killed the harness: lesson #1.
- **Sandbox.** Bubblewrap with our own `wrapper_args`: `--clearenv` plus an explicit `--setenv` allowlist,
  read-only system dirs, `--unshare-net`, `--unshare-pid`, `HOME=/tmp`, read-only binds for the profile's
  toolchains, and the worktree read-write.
  - **Correction (found while building the worker runner).** Bubblewrap passes its parent's environment through by default, and the harness process
    holds the key. During the bake-off, commands the model ran could therefore have read `OPENROUTER_API_KEY` with
    `env`. The network was blocked, so it couldn't have been sent anywhere directly. The seeded-escape test (a key
    planted in the parent's environment must stay invisible) found this, and `--clearenv` closes it.
- **Isolated config.** `MSWEA_CONFIGURED=true` and a per-run `MSWEA_GLOBAL_CONFIG_DIR`, so a run never prompts
  for setup or touches `~/.config`.
- **Results.** `traj.json` supplies the exit status, steps, exact $ and the submission. A submission line beginning
  `ESCALATE:` becomes `needs_decision`.

**Fallback:** OpenCode, which tied in the bake-off, can go behind the same adapter seam if mini-swe-agent ever
regresses. The next fallback after that is OpenHands.

## Consequences
- **The harness brings 83 Python packages.** They are isolated in their own venv, version-pinned, and kept out of
  the aios runtime, which stays stdlib-only.
- **Bubblewrap is labelled experimental by mini-swe-agent.** We supply our own arguments and prove them with
  `aios doctor`'s sandbox probe.
- **Operational lessons recorded during the bake-off:**
  - OpenRouter's *Sensitive Info Detection* guardrail in *Redact* mode breaks multi-turn agent runs with
    `403 redaction_context_lost`. Keep it off, and keep the no-training data policy on.
  - npm's audit service can hang or 502, so dependency audits must fail on findings and only warn on outages.
  - Cost per run varies up to 15× for the same task and model. Per-attempt dollar caps and *measured* medians (P12)
    matter more than list prices.

## Alternatives considered
- **OpenCode.** It tied on results and lost the safety tie-break. It is kept as the first fallback.
- **A custom agent loop.** About 500 lines to maintain for no measured gain.
- **OpenHands SDK.** Too heavy for a solo operator.
- **Aider.** In maintenance mode.
- **NVIDIA OpenShell** (evaluated 2026-10-22, at the operator's suggestion). An Apache-2.0 agent sandbox with
  YAML policies.
  - **What it adds:**
    - per-program network rules (for example "only `node` may reach `registry.npmjs.org`");
    - credential placeholders;
    - audit logs and resource limits.
  - **Why not now:**
    - It needs Docker, Podman, KVM or Kubernetes, and this machine has none of them.
    - WSL2 is "experimental", with open bugs.
    - It is version 0.1.x, with breaking changes every week.
    - Workspaces are copied in and out, not mounted.
    - It is stricter where we don't need it and looser where we do: our workers already have *no* network and never
      see the key, because the agent loop and the key stay outside the sandbox.
  - **Revisit when** OpenShell reaches 1.0 with WSL2 + Podman support, or if the agent loop moves inside the sandbox.
  - **Smaller step for the one real gain**, limiting the setup step (`npm ci`) to the package registry: an
    allowlisting proxy in front of the setup sandbox.

  Sources: https://github.com/NVIDIA/OpenShell , https://docs.nvidia.com/openshell/latest/
