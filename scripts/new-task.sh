#!/usr/bin/env bash
# new-task.sh — scaffold a self-contained task spec in tasks/active/ (schema = manual §6.6).
# Usage: new-task.sh <id> <slug> [model] [verifier_model]
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$DIR/_lib.sh"
cd "$(repo_root)"

id="${1:?usage: new-task.sh <id> <slug> [model] [verifier_model]}"
slug="${2:?slug required}"
model="${3:-opencode-go/glm-5.2}"
vmodel="${4:-opencode-go/deepseek-v4-pro}"

# Enforce P8 at creation: verifier family must differ from author family.
if [[ "$(family_of "$model")" == "$(family_of "$vmodel")" ]]; then
  if [[ "$(family_of "$model")" == "moonshot" ]]; then vmodel="opencode-go/deepseek-v4-pro";
  else vmodel="opencode-go/kimi-k2.7-code"; fi
  warn "verifier shared author's family; auto-switched verifier_model -> $vmodel" \
    "model and the requested verifier are the same family — P8 forbids a model grading its own family" \
    "to choose the verifier yourself, pass a different-family model as arg 4: new-task.sh $id $slug $model <verifier>"
fi

out="tasks/active/${id}-${slug}.md"
[[ -e "$out" ]] && die "$out already exists"
mkdir -p tasks/active

cat > "$out" <<EOF
---
id: ${id}
slug: ${slug}
owner_role: implementer
model: ${model}
verifier_model: ${vmodel}
branch: task/${id}-${slug}
blast_radius: low          # low|med|high  (high ⇒ Lead designs the contract first)
files_allowed:             # hard authority boundary; must be disjoint across active tasks
  - path/to/file.ext
  - path/to/file.test.ext
  - reports/tasks/${id}-completion.md   # required output (AGENTS.md §6) — keep this line
depends_on_contracts: []   # e.g. architecture/contracts/<name>.yaml
deps_preapproved: []       # any new library must be listed here or the task STOPS
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

log "created $out"
log "next: edit files_allowed + acceptance criteria, then: scripts/dispatch.sh ${id}"
