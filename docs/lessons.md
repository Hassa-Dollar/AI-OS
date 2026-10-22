# Lessons from v1 → how v2 enforces them

Sources: `docs/history/v1-bug-registry.md` (BUG-01…31) and `docs/history/v1-determinism-layer-hardening.md`. Each
lesson is enforced mechanically. A lesson without a test or check below is only advice.

| # | v1 lesson (bugs) | v2 enforcement |
|---|---|---|
| 1 | Never pass big prompts on the command line: ARG_MAX overflows, and a model's `pkill -f` once killed its own harness (BUG-03/10; re-hit in the 2026-10 bake-off) | The harness receives the task in a file or config, and the argv only carries a short pointer. Regression test in `harness` |
| 2 | Never discard network output; retry transient errors and log the real stderr (BUG-20/23) | `gateway` keeps raw error bodies and retries only 429/5xx, with a timeout on every call |
| 3 | Exclude lockfiles and build output from diff metrics and review (BUG-23) | `gate` uses one generated-paths list, drawn from the profile's `generated` set plus lockfiles |
| 4 | One resolver for "which model runs" (BUG-27/30) | The router decides once and records it, and the gate re-reads the record (ADR-0031) |
| 5 | Parse verdicts fail-closed and never reuse a stale one (BUG-09) | The verdict is JSON-schema output bound to `patch-id` and SHA; a mismatch means re-verify |
| 6 | Don't log expected outcomes as errors (BUG-25) | Exit statuses are an enum (`submitted`/`limits`/`escalated`/`error`/`infra`) |
| 7 | Clean-room CI catches shared-environment assumptions (BUG-29) | Tests use temp dirs, temp repos and fakes only. CI runs offline. Every worker runs in a sandbox with no home directory |
| 8 | Put a timeout on every probe (BUG-28) | `doctor` and every subprocess call takes a timeout argument. A lint check in tests enforces it |
| 9 | Secret scanners must allowlist env-var references (BUG-26) | gitleaks in CI with a reviewed allowlist. Keys never appear in env or argv |
| 10 | Tests must never touch real state (BUG-21) | Tests set `HOME` and `XDG_*` to temp dirs; a guard test fails if `~/.config/aios` is opened |
| 11 | Verify a process's identity before killing it (OS-V1.1 gate) | `stop` checks the recorded pid and start time. The harness runs in its own PID namespace (`--unshare-pid`) |
| 12 | Worker-written "done" isn't done: v1 escalations were never parsed, and CI failed open when unset | The `ESCALATE:` line becomes `needs_decision`. A component with no checks fails closed |
| 13 | Machine-local history gets lost (v1 ledger and memory DB) | Durable state is the committed per-task records (ADR-0030) |
| 14 | A sandbox inherits its parent's environment: bubblewrap forwards env vars, including the harness's API key, unless told `--clearenv` (found by the W4 seeded-escape test) | `harness.sandbox()` always uses `--clearenv` plus an explicit `--setenv` allowlist; `test_seeded_escapes_fail_for_real` plants a key in the parent's env |
| 15 | Workers leave build caches (`__pycache__`, `node_modules`, coverage) behind, and a repo without ignore rules would commit them (found in the first live dispatch) | `run.dispatch` stages with cache excludes; `test_runs_in_a_worktree_and_commits_there_only` |

The procedure is unchanged from v1: root-cause the bug, revert the patch, add a regression test, then record it in the
task record's `lessons`.
