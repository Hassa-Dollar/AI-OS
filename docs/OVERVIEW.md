# How AI-OS works: a plain-language tour

AI-OS (the command is `aios`) takes a written task and does the following:
1. It has an AI model write the code inside a locked-down sandbox.
2. It checks the result automatically: the project's tests, plus a review by a second model from another company.
3. It merges the change.
4. It keeps a record of what happened and what it cost.

You point it at any git repository. One OpenRouter key gives it access to the models.

## Who does what
| Who | Role |
|---|---|
| **Operator** (you) | Sets the budget and privacy rules. Approves risky work. Is the only one who can overrule a failed review. |
| **Lead** (Claude Code) | Writes each task's spec. Reviews what the checks flag. Writes the design records (ADRs). |
| **Router** (Clef, a small model running locally in Ollama) | Reads a task and judges how hard and how risky it is. It runs on your machine, so the task never leaves it for this step. |
| **Worker** | The model that writes the code, chosen per task. |
| **Verifier** | A second model, from a *different* company, that reviews the worker's change. |

## One task, from start to finish
```
 1. Spec      .aios/tasks/<id>.md        the Lead writes it, it lands on main through a pull request
      |
 2. Route     aios route <spec>          spec.py reads it -> router.py asks Clef -> a decision:
      |                                  review level, worker model, verifier model
 3. Work      aios dispatch <spec>       run.py creates a branch in its own folder (a "worktree")
      |                                  -> harness.py runs the worker in the sandbox
      |                                     (no network, no keys, no home folder)
      |                                  -> run.py commits what the worker wrote
 4. Check     aios gate <spec>           gate.py: what changed? only allowed files? new dependencies?
      |                                  -> the project's tests, run in the sandbox
      |                                  -> the verifier's review, bound to the exact change
      |                                  -> records.py saves the record on the branch
 5. Approve   aios approve <spec>        land.py: you or the Lead sign off, when the review level requires it
      |
 6. Land      aios land <spec>           land.py -> forge.py: pull request, CI checks, merge, cleanup
```
If the check fails, `aios fix <spec>` runs a **fix round**: the work goes back to a worker, with the review
attached. Round 1 uses the same model, round 2 the next cheapest at the same level, round 3 one level up. After
4 attempts, you and the Lead decide.

Three more commands:
- `aios rollback <spec>` undoes a landed task. The undo goes through the forge like any other change.
- `aios status` lists every task: what needs you, what is running, what is ready, and what is done.
- `aios brief` sums up the tasks, what landed lately, and the spend.

## Review levels
A task's review level is the higher of two things: the router's decision, and any flags the check raises.

| Level | Who reviews before merge | Examples |
|---|---|---|
| **AUTO** | No one. The checks are enough | Small, low-risk changes |
| **OPERATOR** | You skim the result | Large but routine changes |
| **LEAD** | The Lead reviews | Sensitive files, contracts, high blast radius |
| **HUMAN** | You must approve | Logins, payments, secrets, personal data, irreversible changes, hardware |

## Which file does what (`aios/`)
| File | Job |
|---|---|
| `cli.py` | The `aios` command. Turns `aios <command>` into a call to the right module. |
| `config.py` | Settings: machine paths, the key file, `.aios/project.toml`. |
| `spec.py` | Reads and validates task specs (Markdown with TOML settings on top). |
| `router.py` | Asks Clef about a task, then applies the decision table: review level, level, and the models for each role. |
| `catalog.py` | The whole live model list, with prices and quality scores, fetched from OpenRouter. Picks the candidates for each role and level. |
| `models.toml` | The model policy: the quality score each level needs, and blocks on models measured to misbehave. There is no list of allowed models. |
| `review.py` | The reviewer's call on a change. A first "fail" gets a second opinion from another company's model. |
| `calibrate.py`, `calibration/` | `aios models calibrate`: tries reviewer candidates on known changes. Only models that judge all of them correctly may review. |
| `gateway.py` | Talks to OpenRouter: the model list, key and spend info, and the verifier's chat calls. |
| `harness.py` | Installs and runs the worker program (mini-swe-agent) inside the sandbox (bubblewrap). |
| `run.py` | `aios dispatch` and `aios fix`: one worker attempt, from routing to commit, within the budget limits. |
| `gate.py` | `aios gate`: the automatic checks, the verifier and the record. |
| `records.py` | Writes and reads the per-task record. It strips your paths and username. |
| `land.py` | `aios approve`, `aios land` and `aios rollback`. |
| `status.py` | `aios status` and `aios brief`, worked out from git and the records. |
| `forge.py` | Merging: through GitHub (pull request, waiting for CI, merge) or locally. |
| `git.py` | Small git helpers. Every call has a time limit. |
| `doctor.py` | `aios doctor`: checks the machine is ready (key, budget, Clef, sandbox, worker program, and the project's toolchains). `--fix` installs what it can. |
| `toolchains.py` | The runtimes a project can need (Node, Python, Rust, Go, PlatformIO): how to read their version, and how `aios init` recognises a project. |
| `prompts/worker.md`, `prompts/verifier.md` | The instructions given to the worker and to the verifier. |

## Where things are kept
- **In the AI-OS repository (public):**
  - the tool itself (`aios/`);
  - design decisions (`architecture/adr/`) and data formats (`architecture/contracts/`);
  - these docs.
- **In your project's repository, under `.aios/`:**
  - `project.toml`: your settings (checks, budget, privacy, sensitive files);
  - `tasks/`: the specs;
  - `records/`: one JSON file per finished task. The project's status is worked out from these files and git, so
    nothing important lives only on one machine.
- **On your machine only (never committed):**
  - `~/.config/aios/credentials`: the OpenRouter key, readable only by you;
  - `~/.cache/aios/`: the model list;
  - `~/.local/state/aios/`: each attempt's logs;
  - `~/.local/share/aios/`: worktrees, the worker program and toolchains.

## Where the project stands (2026-10-24)
- **Working today,** every part built by aios itself and merged through its own pipeline:
  - Clef reads each task; models come from the whole OpenRouter catalog, the cheapest one fit for each role and level;
  - sandboxed workers; the automatic check, with a calibrated reviewer from another company;
  - money limits per task, per day, per month and on the key;
  - fix rounds; `aios approve`, `aios land`, and your override of a wrong review;
  - `aios rollback`, `aios status` and `aios brief`;
  - toolchains: each part of a project names the runtimes it needs, `aios doctor` checks them inside the sandbox
    and installs Node, and `aios init` recognises Node, Python, Rust, Go and PlatformIO projects.
- **Next:** onboarding Shrink, then building its product with aios.
- **Later:**
  - model choice that also weighs each model's measured speed;
  - dependency caches, so Rust, Go and PlatformIO projects can build offline in the sandbox.
- **Read more:**
  - [`doctrine.md`](doctrine.md): the principles;
  - [`../architecture/README.md`](../architecture/README.md): the design records;
  - [`lessons.md`](lessons.md): what went wrong and the rule that now prevents it.
