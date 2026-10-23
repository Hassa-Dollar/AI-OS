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
If the check fails, a **fix round** sends the work back to a worker, with the review attached.

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
| `router.py` | Asks Clef about a task, then applies the decision table: review level, worker, verifier. |
| `catalog.py` | The list of models and their prices, fetched from OpenRouter. |
| `gateway.py` | Talks to OpenRouter: the model list, key and spend info, and the verifier's chat calls. |
| `harness.py` | Installs and runs the worker program (mini-swe-agent) inside the sandbox (bubblewrap). |
| `run.py` | `aios dispatch`: one worker attempt, from routing to commit. |
| `gate.py` | `aios gate`: the automatic checks, the verifier and the record. |
| `records.py` | Writes and reads the per-task record. It strips your paths and username. |
| `land.py` | `aios approve` and `aios land`. |
| `forge.py` | Merging: through GitHub (pull request, waiting for CI, merge) or locally. |
| `git.py` | Small git helpers. Every call has a time limit. |
| `doctor.py` | `aios doctor`: checks the machine is ready (key, Clef, sandbox, worker program). |
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

## Where the project stands (2026-10-22)
- **Working today:**
  - routing with Clef;
  - sandboxed workers;
  - the automatic check with a cross-company review;
  - records;
  - merging through GitHub or locally;
  - `aios approve` and `aios land`.

  Every one of these was built by aios itself and merged through its own pipeline.
- **Being changed now:**
  - **Model choice over the whole OpenRouter catalog.** No more fixed list. Roles (implementer at junior, mid or senior
    level, reviewer, adversarial tester, and so on) get the best model for the price for each task.
  - **A reliable verifier,** picked by calibration on known changes.
  - **A monthly budget,** asked at setup and used to cap spending and choose models.
  - **Only you can overrule a failed review.**
- **Next:**
  - a rollback command;
  - automatic fix rounds;
  - `aios status` and `aios brief`, so you can see everything at a glance;
  - then building the Shrink product with aios.
- **Read more:**
  - [`doctrine.md`](doctrine.md): the principles;
  - [`../architecture/README.md`](../architecture/README.md): the design records;
  - [`lessons.md`](lessons.md): what went wrong and the rule that now prevents it.
