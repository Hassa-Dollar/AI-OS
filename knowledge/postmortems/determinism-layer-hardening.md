# Determinism-Layer Hardening Registry

> Living record of bugs/edge-cases in the OS scripts (the "determinism layer": `scripts/*.sh`, the
> workflows, the hooks), each with **root cause**, a **robust fix** (not a patch), and a **regression
> guard**. Born from the first real build run (Shrink T01), which surfaced several harness bugs because the
> determinism layer had **no automated tests** — the true root tech-debt this registry exists to retire.
>
> **Append-only, grows forever:** every bug, patch, root cause, and fix we ever find is logged here — one
> *terse* entry each (precise and direct, never padded). Never pruned for length; a long registry is expected.

## 0. Why this exists
A live run patched reactively, one bug at a time, accretes instability. The fix is a discipline: when the
harness breaks, we find the *deepest* cause, fix it at the root, prove it can't recur with a test, and
record it here. The single highest-leverage robustness investment is a **test harness for the scripts**
(§3) — every bug below would have been caught by one.

## 1. Bug-handling procedure (follow for every harness bug)
1. **Capture** — exact command, exact error, context (branch, state). Add a row to §2.
2. **Reproduce** minimally — the smallest input that triggers it.
3. **Root-cause** — not the symptom. Ask: *what class of inputs triggers this, and what's the deepest
   assumption that's wrong?* A fix that only handles today's input is a patch.
4. **Fix at the root** — and **revert any prior patch** so there's one correct mechanism, not two.
5. **Regression guard** — a test in the harness (§3) that fails before the fix and passes after.
6. **Record** — update §2; write an ADR if the fix is a design decision.
7. **Only then resume** the interrupted work.

## 2. Registry

| ID | Sev | Status | One-line |
|---|---|---|---|
| BUG-01 | med | fixed (robust) | edits over the mount strip the exec bit; git tracked it |
| BUG-02 | med | **patched** | deps-allowlist false-positive on YAML-quoted scoped pkg (`"@x/y"`) |
| BUG-03 | high | **patched** | verifier prompt (incl. diff) passed as one `argv` → `MAX_ARG_STRLEN` |
| BUG-04 | med | open | `land.sh` leaves the handoff dirty on main → trips the next task rebase |
| BUG-05 | low | open | gate preflight blames a dirty handoff on "worker forgot to commit" |
| BUG-06 | high | open (imminent) | `npm audit --audit-level=high` audits dev deps → blocks on tooling CVEs |
| BUG-07 | med | open (imminent @T18) | non-component task (docs/research) → gate component-resolution dies |
| BUG-08 | med | worked-around | no task-id uniqueness guard → Shrink ids collided with old demos |
| BUG-09 | low | open | gate reuses any non-empty verdict, even a partial one from a failed run |
| BUG-10 | low | open | `dispatch.sh` also passes the worker prompt as one `argv` (same root as BUG-03) |

### BUG-01 — exec bit stripped by mount edits  ·  fixed (robust)
- **Symptom:** edited scripts committed `100644` → `Permission denied` on direct invocation.
- **Root:** the Windows/9P mount write path drops the Unix exec bit; `core.fileMode=true` then records it.
- **Fix:** `git config core.fileMode false` (set by `bootstrap.sh`); ADR-0010.
- **Regression guard (MISSING — add):** an os-ci check that every tracked `scripts/*.sh` / `bootstrap.sh` /
  `.githooks/*` has mode `100755` (was deferred in ADR-0009 discussion; wire it in §3).

### BUG-02 — deps-allowlist false-positive on quoted scoped packages  ·  patch → ROOT FIX NEEDED
- **Symptom:** `runtime dependency added without pre-approval: @hono/node-server` — though it *was* approved.
- **Root:** `fm_list` (in `_lib.sh`) returns YAML list items **without stripping surrounding quotes**.
  `"@hono/node-server"` (quoted because `@` is a YAML indicator) compared unequal to `@hono/node-server`.
- **Patch applied:** stripped quotes *in the gate's deps check only* (`| tr -d "\"'"`).
- **Root fix:** strip surrounding quotes in `fm_list` itself, so **every** caller is correct; then drop the
  local patch. (Also audit `fm_scalar` for the same.)
- **Guard:** unit test — `fm_list` on a spec with `- "@scope/pkg"`, `- 'single'`, `- bare` returns the
  three unquoted; `assert_in_catalog`/deps-check accept a quoted scoped slug.

### BUG-03 — verifier prompt exceeds the single-argument limit  ·  patch → ROOT FIX NEEDED
- **Symptom:** `opencode: Argument list too long` at the QA step.
- **Root:** the entire prompt (`code-review.md` + **full diff** + spec) is passed as one `argv` string;
  Linux caps a single arg at ~128 KB (`MAX_ARG_STRLEN`). A 4,110-line lockfile blew it.
- **Patch applied:** excluded lockfiles from the review diff (good practice regardless, keep it).
- **Root fix:** stop passing large prompts as `argv` — write the prompt to a temp file and feed `opencode`
  via **stdin** (or a `--prompt-file` if it supports one; verify `opencode run --help`). Apply to the
  verifier **and** the worker dispatch (BUG-10). Keep lockfile exclusion as a separate good-practice trim.
- **Guard:** integration test — gate (dry-run-ish) with a synthetic 200 KB diff must not error on arg size.

### BUG-04 — handoff left dirty on main trips the next task rebase  ·  open
- **Symptom:** after a chore PR lands, `git rebase` on a task branch → `cannot rebase: unstaged changes`
  (the `docs/handoff/SESSION-HANDOFF.md` refresh). Recurred every chore→task cycle.
- **Root:** `land.sh` runs `handoff.sh` post-merge on `main`, which **modifies but cannot commit** the
  handoff (main is branch-protected — no direct push), so it's intentionally left to "ride the next PR"
  (`pr.sh` folds it). Non-`pr.sh` flows (a manual task rebase) hit the dirty worktree.
- **Root fix (decide in ADR):** make the auto-generated handoff *never* block an operation. Options:
  (a) regenerate+commit the handoff **on the branch during `gate.sh`/`pr.sh`** (so it lands with the PR and
  main is never left dirty — accept AUTO-STATE.main being "merging into" the pre-merge hash); or
  (b) every flow that needs a clean tree treats the handoff as the known pending file (auto-stash/ignore),
  mirroring `pr.sh`'s existing carve-out. (a) is cleaner — eliminates the dirty-main state entirely.
- **Guard:** test that a task rebase/gate proceeds with a pending handoff present.

### BUG-05 — gate preflight misattributes a dirty handoff  ·  open
- **Symptom:** with a pending handoff, `gate.sh` would die "worktree is DIRTY — worker output is not fully
  committed" (wrong cause).
- **Root:** the preflight dirty check (`gate.sh`) doesn't exclude the auto-generated handoff (unlike `pr.sh`).
- **Root fix:** exclude `docs/handoff/SESSION-HANDOFF.md` from the preflight (single source of truth: a
  shared `_worktree_dirty_excluding_handoff` helper used by `gate.sh` and `pr.sh`). Folds into BUG-04.
- **Guard:** same test as BUG-04.

### BUG-06 — npm audit blocks on dev-tooling advisories  ·  open (IMMINENT — would block T01)
- **Symptom:** `npm install` already reported "3 moderate, 1 high, 2 critical" in the eslint/vitest trees;
  `product-ci`'s `npm audit --audit-level=high` audits **all** deps → the task PR's CI would fail.
- **Root:** the audit step (added in #57) doesn't distinguish **runtime** deps (the real attack surface,
  and what the deps-allowlist gates) from **dev tooling** (built, not shipped).
- **Root fix:** `npm audit --omit=dev --audit-level=high` (audit production deps only) — consistent with the
  deps-allowlist's runtime-only scope. Dev-tooling advisories are surfaced (not silenced) but don't block;
  a runtime CVE still blocks.
- **Guard:** the CI step itself; a fixture component with a known-vuln *dev* dep must still pass.

### BUG-07 — non-component task breaks gate component-resolution  ·  open (imminent @ T18 docs)
- **Symptom (anticipated):** a docs/research task (files in `docs/` or `knowledge/`, no component) →
  `gate.sh` `component_of_spec` empty → `component_dir` dies "multiple components — set COMPONENT".
- **Root:** the gate assumes every task targets exactly one component; OS/docs/research tasks don't.
- **Root fix:** when a spec's `files_allowed` has **no** component path, run a **lighter gate** — skip the
  component CI/build/deps/isolation guards; keep the boundary audit, cross-family QA, and risk router.
- **Guard:** test gating a synthetic docs-only task succeeds without a component.

### BUG-08 — no task-id uniqueness guard  ·  worked-around
- **Symptom:** Shrink ids `001/002` collided with archived demo tasks (overwrote a completion report).
- **Root:** `new-task.sh` / `dispatch.sh` never check the id isn't already used in `tasks/active/` **or**
  `tasks/completed/`.
- **Root fix:** `new-task.sh` (and a dispatch guard) reject an id already present in active **or** completed.
- **Guard:** test that creating a duplicate id dies with a clear message.

### BUG-09 — stale/partial verdict reuse  ·  open
- **Symptom (latent):** `gate.sh` reuses any **non-empty** `reviews/verdicts/<id>.txt`; a partial file from
  a crashed verifier run could be reused as a real verdict.
- **Root fix:** reuse only if the verdict parses to a valid `RISK` **and** `VERDICT`; else regenerate.
- **Guard:** test that a partial verdict is ignored and regenerated.

### BUG-10 — dispatch worker prompt also arg-passed  ·  open (same root as BUG-03)
- **Root fix:** fold into BUG-03's stdin/file change (apply to `run_worker` in `dispatch.sh` too).

## 3. Keystone — a determinism-layer test harness
The scripts have **zero tests**; that is why these only surfaced in a live run. Add:
- **Unit tests** for the pure `_lib.sh` functions: `fm_scalar`, `fm_list` (quoted/bare/comment cases),
  `family_of` (all 7 slugs), `assert_in_catalog`, `component_of_spec` (none/one/many).
- **Integration tests** (fixtures = a temp git repo + synthetic specs/components) for `dispatch`/`gate`
  behaviors: off-catalog dies, P8 enforced, files_allowed disjointness, deps-allowlist (incl. scoped),
  dangerous-API grep, non-component gate, big-diff verifier, dirty-handoff tolerance, id-uniqueness.
- **Runner:** `bats-core` (standard for bash) under `scripts/test/`, plus a `scripts/test.sh` entrypoint.
- **CI:** an os-ci job runs the harness on every push — so the determinism layer can never regress silently.
- **Rule:** every future BUG-NN row ships with a test here (procedure §1.5).

## 4. Hardening plan (ordered)
1. **This registry** (done) + the bug-handling procedure (§1).
2. **Root-cause fix batch A (imminent/blocking):** BUG-06 (`--omit=dev`), BUG-02 (`fm_list` quotes, drop the
   patch), BUG-03+10 (prompt via stdin/file).
3. **Root-cause fix batch B (robustness):** BUG-04+05 (handoff never blocks), BUG-08 (id uniqueness),
   BUG-07 (non-component gate), BUG-09 (verdict validation), BUG-01 (add the exec-bit os-ci guard).
4. **Test harness (§3)** + os-ci job + a regression test per bug.
5. **ADR-0015** recording the hardening + the test-harness decision + this procedure as doctrine.
6. **Resume the SaaS build** — re-ship T01 on the hardened harness; continue T02+.

Each batch lands as its own reviewed PR (the system gating itself), newest fixes first where they unblock.
