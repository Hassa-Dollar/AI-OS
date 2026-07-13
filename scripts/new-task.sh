#!/usr/bin/env bash
# new-task.sh — scaffold a self-contained task spec in tasks/active/ (schema = manual §6.6).
# Roles v2 (ADR-0022): a spec names WHO-kind (owner_role); the component's profile binds role→model.
# Usage: new-task.sh <id> <slug> [owner_role]     (default owner_role: implementer)
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$DIR/_lib.sh"
cd "$(repo_root)"

id="${1:?usage: new-task.sh <id> <slug> [owner_role]}"
slug="${2:?slug required}"
role="${3:-implementer}"

# id uniqueness (registry BUG-08): an id must be unused across active AND completed — a collision
# overwrites the prior task's archived spec / completion report.
shopt -s nullglob
_dups=( "tasks/active/${id}-"*.md "tasks/active/${id}.md" "tasks/completed/${id}-"*.md "tasks/completed/${id}.md" )
[[ ${#_dups[@]} -eq 0 ]] || die "task id '${id}' already used: ${_dups[0]}" \
  "ids must be unique across tasks/active and tasks/completed" \
  "choose an unused id (check: ls tasks/active tasks/completed)"

out="tasks/active/${id}-${slug}.md"
[[ -e "$out" ]] && die "$out already exists"
mkdir -p tasks/active

cat > "$out" <<EOF
---
id: ${id}
slug: ${slug}
owner_role: ${role}        # resolved to a model via the component's profile.json (ADR-0022)
branch: task/${id}-${slug}
blast_radius: low          # low|med|high  (high ⇒ Lead designs the contract first)
files_allowed:             # hard authority boundary; must be disjoint across active tasks
  - path/to/file.ext
  - path/to/file.test.ext
  - reports/tasks/${id}-completion.md   # required output (AGENTS.md §6) — keep this line
depends_on_contracts: []   # e.g. architecture/contracts/<name>.yaml
deps_preapproved: []       # any new library must be listed here or the task STOPS
# model_override: + override_reason:  — audited exception only; the gate risk-flags it (ADR-0022).
# OS/chore task (no component)? there is no profile — set model: and verifier_model: explicitly (P8!).
---

# Goal
<one sentence: what must be true when this is done>

# Context (compressed)
<3–6 sentences; link contracts, do NOT inline the repo>

# Acceptance criteria  (executable where possible)
- [ ] <observable behavior 1>
- [ ] <observable behavior 2>
- [ ] tests cover: <cases>
- [ ] typecheck + lint pass; diff coverage ≥ 90%

# Out of scope  (binding — prevents gold-plating)
- <thing not to do>

# Stop conditions  (escalate instead of guessing)
- If correct behavior requires changing a contract → STOP, escalate to Lead.
- If a needed dependency isn't in deps_preapproved → STOP, escalate.

# Working notes  (worker appends)
EOF

log "created $out (owner_role: ${role})"
log "next: edit files_allowed + acceptance criteria, then: scripts/dispatch.sh ${id}"
