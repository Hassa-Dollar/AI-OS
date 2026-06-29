#!/usr/bin/env bash
# _lib.sh -- shared helpers for the AI-Dev-OS scripts. Source this; do not run it.
# Pure bash + coreutils/awk/sed/git. No yq dependency.
# Tolerates inline "# comments" after YAML keys/values (the documented schema uses them).
# awk uses [ \t] not POSIX classes, because Ubuntu default mawk lacks [[:space:]].

# --- operator-facing output (ADR-0004 #4) ----------------------------------
# log  <msg>                  informational (cyan)
# warn <what> [cause] [try]   recoverable problem (yellow); cause/try optional
# die  <what> [cause] [try]   fatal (red) + exit 1; cause/try optional
# The optional 2nd/3rd args make a failure say WHAT broke, the LIKELY CAUSE, and what to TRY —
# so the operator can act without pasting the message into a model. Old single-arg calls still work.
log()  { printf '\033[36m[ai-os]\033[0m %s\n' "$*" >&2; }
warn() {
  printf '\033[33m[ai-os][warn]\033[0m %s\n' "$1" >&2
  [[ -n "${2:-}" ]] && printf '\033[33m              ↳ likely cause:\033[0m %s\n' "$2" >&2
  [[ -n "${3:-}" ]] && printf '\033[33m              ↳ try:\033[0m %s\n' "$3" >&2
  return 0
}
die()  {
  printf '\033[31m[ai-os][err]\033[0m %s\n' "$1" >&2
  [[ -n "${2:-}" ]] && printf '\033[31m             ↳ likely cause:\033[0m %s\n' "$2" >&2
  [[ -n "${3:-}" ]] && printf '\033[31m             ↳ try:\033[0m %s\n' "$3" >&2
  _capture error "$1" "$(printf '%s | %s' "${2:-}" "${3:-}")"   # autonomous log (ADR-0016), best-effort
  AI_OS_NO_CAPTURE=1                                            # we just logged; don't let the EXIT trap double-log
  exit 1
}

repo_root() {
  git rev-parse --show-toplevel 2>/dev/null \
    || die "not inside a git repo" "the script was run outside the repo tree" "cd into the repo (or any subdir of it) and re-run"
}

# fm_block <file> -- print the YAML front matter (lines between the first two --- fences).
fm_block() { awk '/^---[ \t]*$/{n++;next} n==1{print} n>=2{exit}' "$1"; }

# fm_scalar <file> <key> -- top-level scalar value; strips inline "# comment" and trailing space.
fm_scalar() { fm_block "$1" | sed -n "s/^$2:[[:space:]]*//p" | head -1 | sed 's/[[:space:]]*#.*$//; s/[[:space:]]*$//'; }

# yaml_scalar <file> <key> -- like fm_scalar but for a PLAIN yaml file with NO --- fences (e.g. .component.yml).
# Reads a top-level "key: value"; strips an inline "# comment", trailing space, and surrounding quotes.
yaml_scalar() { sed -n "s/^$2:[[:space:]]*//p" "$1" 2>/dev/null | head -1 | sed -E 's/[[:space:]]*#.*$//; s/[[:space:]]*$//; s/^"(.*)"$/\1/; s/^'\''(.*)'\''$/\1/'; }

# fm_list <file> <key> -- list items under "key:" (key line may carry an inline comment).
# Trailing sed strips a surrounding pair of quotes from each value, so YAML-quoted scalars like
# "@scope/pkg" or 'x' parse to their bare value (registry BUG-02). Bare values pass through unchanged.
fm_list() { fm_block "$1" | awk -v k="$2" '$0 ~ "^"k":"{g=1;next} g&&/^[ \t]+-[ \t]+/{sub(/^[ \t]+-[ \t]+/,"");sub(/[ \t]+#.*$/,"");print;next} g&&/^[^ \t]/{g=0}' | sed -E 's/^"(.*)"$/\1/; s/^'\''(.*)'\''$/\1/'; }

# family_of <model-slug> -- model family, for the P8 different-family rule.
family_of() {
  case "$1" in
    *glm*)      echo zhipu    ;;
    *kimi*)     echo moonshot ;;
    *qwen*)     echo alibaba  ;;
    *deepseek*) echo deepseek ;;
    *minimax*)  echo minimax  ;;
    *mimo*)     echo xiaomi   ;;
    *)          echo unknown  ;;
  esac
}

# --- the fixed model catalog (ADR-0005), machine-enforced (ADR-0009) -------
# The seven hosted models every project binds from -- the SAME set for every project type; a profile
# re-binds roles among them, it never adds or swaps one. The gateway ALSO serves superseded predecessors
# (glm-5.1, kimi-k2.6, mimo-v2.5, minimax-m2.7, qwen3.6-plus) and typos, which would run SILENTLY against
# the wrong model. This allowlist is the guard. A version bump is a tracked CHANGE: edit this list in the
# SAME commit as its ADR (Failure Mode #3 / ADR-0005/0007).
CATALOG=(
  opencode-go/deepseek-v4-pro
  opencode-go/glm-5.2
  opencode-go/kimi-k2.7-code
  opencode-go/mimo-v2.5-pro
  opencode-go/minimax-m3
  opencode-go/qwen3.7-max
  opencode-go/qwen3.7-plus
)

# assert_in_catalog <model-slug> [role-label] -- die unless the slug is one of the fixed seven (ADR-0009).
assert_in_catalog() {
  local m="$1" role="${2:-model}" c
  for c in "${CATALOG[@]}"; do [[ "$m" == "$c" ]] && return 0; done
  die "off-catalog model '$m' ($role)" \
    "not one of the fixed seven (ADR-0005); the gateway also serves superseded/typo slugs that would run silently" \
    "use an exact catalog slug (see CATALOG in scripts/_lib.sh); a version bump needs an ADR + a CATALOG edit"
}

# intersect <listA> <listB> -- lines present in BOTH newline-separated strings (pure awk).
intersect() { awk -v A="$1" -v B="$2" 'BEGIN{n=split(A,a,"\n");for(i=1;i<=n;i++)if(a[i]!="")s[a[i]]=1;m=split(B,b,"\n");for(i=1;i<=m;i++)if(b[i]!=""&&(b[i] in s))print b[i]}'; }

ledger_path() { echo "$(repo_root)/reports/metrics/ledger.csv"; }

# component_dir [name] -- resolve the active component path (ADR-0002).
# Precedence: explicit arg / COMPONENT env -> the sole components/* dir -> error.
# Scripts cd into this; they never branch on the component's name (invariant OS-3 / #7).
component_dir() {
  local c="${1:-${COMPONENT:-}}"
  if [[ -n "$c" ]]; then
    [[ -d "$c" ]]              && { echo "${c%/}"; return; }
    [[ -d "components/$c" ]]   && { echo "components/$c"; return; }
    die "component '$c' not found" \
      "no directory '$c' or 'components/$c'" \
      "pass a name under components/ (e.g. COMPONENT=service) or a path"
  fi
  shopt -s nullglob; local d=( components/*/ )
  case ${#d[@]} in
    1) echo "${d[0]%/}" ;;
    0) die "no components/ directory yet" \
         "the product hasn't been moved into a component (ADR-0002)" \
         "create components/<name>/ or run: bootstrap.sh --profile <family/variant>" ;;
    *) die "multiple components — can't pick a default" \
         "found: ${d[*]}" \
         "set COMPONENT=<name> for this run, e.g. COMPONENT=api scripts/gate.sh <id>" ;;
  esac
}

# component_of_spec <spec-file> -- the single component a task targets, inferred from its files_allowed
# (ADR-0013). Prints the component path (e.g. components/api), or nothing if the spec touches no component.
# Dies if files_allowed spans more than one component (one-task-one-component, ADR-0002).
component_of_spec() {
  local spec="$1" roots n
  roots="$(fm_list "$spec" files_allowed | sed -nE 's#^(components/[^/]+)/.*#\1#p' | sort -u)"
  n="$(printf '%s\n' "$roots" | grep -c . || true)"
  if (( n > 1 )); then
    die "spec files_allowed spans multiple components" \
      "a task must stay within one component (ADR-0002): $(printf '%s' "$roots" | tr '\n' ' ')" \
      "split into one task per component, each on its own branch"
  fi
  printf '%s' "$roots"
}

# json_get <file> <key> -- first string value for "key": "value" in a (flat-ish) JSON file.
# No jq dependency; sufficient for profile.json's small, flat shape (roles + thresholds).
json_get() { sed -nE "s/.*\"$2\"[[:space:]]*:[[:space:]]*\"([^\"]+)\".*/\1/p" "$1" 2>/dev/null | head -1; }

# verdict_field <verdict-file> <FIELD> -- value of a RISK:/VERDICT:-style field from a verifier verdict:
# line-anchored (markdown prefixes ok), LAST occurrence wins (the conclusion), lowercased; empty if absent.
# Used by gate.sh; unit-tested in scripts/test/lib.bats (ADR-0009 / registry BUG-09).
verdict_field() {
  grep -ioE "^[[:space:]>*_#]*$2:[[:space:]*_#]*[A-Za-z]+" "$1" 2>/dev/null \
    | tail -1 | sed -E "s/.*$2:[[:space:]*_#]*//I" | tr 'A-Z' 'a-z'
}

# --- pipeline diff + push helpers (one source of truth, used by gate/land/approve) ------------------
# GENERATED_PATHSPEC — git pathspecs for MECHANICAL/vendored files (lockfiles, build output, snapshots).
# Excluded from code REVIEW and from the risk-router's size metrics: they are not authored, so a 4k-line
# lockfile must neither be graded by the verifier nor inflate a "lines>MAX" Opus-gate flag (BUG-23). The
# boundary audit still sees them — it uses the FULL file list; this only scopes review + metrics.
GENERATED_PATHSPEC=(
  ':(exclude)**/package-lock.json'
  ':(exclude)**/pnpm-lock.yaml'
  ':(exclude)**/yarn.lock'
  ':(exclude)**/dist/**'
  ':(exclude)**/coverage/**'
  ':(exclude)**/*.snap'
)

# reviewable_diff <base> <branch> [extra git-diff args…] — `git diff base...branch` with generated/vendored
# paths excluded: the one diff a human or the verifier should actually read.
reviewable_diff() { local base="$1" br="$2"; shift 2; git diff "$@" "${base}...${br}" -- . "${GENERATED_PATHSPEC[@]}"; }

# risk_nfiles / risk_nlines <base> <branch> — changed-file count / added+deleted line count for the RISK
# ROUTER, generated/vendored excluded (so a lockfile can't trip lines>MAX). Authored size only (BUG-23).
risk_nfiles() { git diff --name-only "$1...$2" -- . "${GENERATED_PATHSPEC[@]}" | grep -c . || true; }
risk_nlines() { git diff --numstat  "$1...$2" -- . "${GENERATED_PATHSPEC[@]}" | awk '{a+=$1+$2} END{print a+0}'; }

# git_push_resilient <git-push-args…> — push, retrying TRANSIENT network failures (a push is idempotent),
# and on a real failure DIE with git's verbatim stderr. NEVER `>/dev/null` a push: the HTTP 408 that landed
# the branch but reported an error was lost precisely because its stderr was swallowed (BUG-23). Deterministic
# recovery — no AI needed to "find" a transient error: we keep the bytes and retry.
git_push_resilient() {
  local attempt out rc
  for attempt in 1 2 3; do
    out="$(git push "$@" 2>&1)"; rc=$?
    if [[ $rc -eq 0 ]]; then [[ -n "$out" ]] && log "$out"; return 0; fi
    if grep -qiE 'HTTP 4(08|29)|HTTP 5[0-9][0-9]|RPC failed|early EOF|connection reset|timed out|TLS|unexpectedly closed|hung up|could not read from remote' <<<"$out"; then
      warn "git push transient failure (attempt $attempt/3) — retrying" "$(printf '%s' "$out" | tail -n 3)"
      sleep $(( attempt * 3 )); continue
    fi
    break   # non-transient → stop and report the real error
  done
  die "git push failed: git push $*" "$out" \
    "this is git's real error (no longer suppressed) — check auth (gh auth status), network, or branch protection"
}

# --- generated doc blocks (ONE source: handoff.sh writes them, verify-coherence.sh checks them) ------
# gen_inventory — print the AUTO-INVENTORY block (each component → its profile binding, + available profiles),
# DISCOVERED from the repo (paths relative to repo root; callers cd there first). Injected into every doc
# that opts in (handoff + architecture/README) so the inventory has ONE source and the two can't disagree.
# DETERMINISTIC — no timestamp — so verify-coherence.sh can compare it byte-for-byte (ADR-0018 / Step 4).
gen_inventory() {
  local bt='`' d cn cprof p pn cfound=0 pfound=0
  echo "<!-- AUTO-INVENTORY:BEGIN — generated by scripts/handoff.sh; do not hand-edit (deterministic: no timestamp, so verify-no-diff works — Step 4) -->"
  echo "**Components (the deliverables built by the system):**"
  for d in components/*/; do
    [[ -d "$d" ]] || continue
    cn="${d#components/}"; cn="${cn%/}"
    cprof="(no .component.yml)"
    [[ -f "${d}.component.yml" ]] && cprof="$(yaml_scalar "${d}.component.yml" profile)"
    echo "- ${bt}${cn}${bt} → profile ${bt}${cprof:-?}${bt}"; cfound=1
  done
  (( cfound )) || echo "- (none yet)"
  echo
  echo "**Profiles available** (each a fixed-catalog binding under ${bt}profiles/<family>/<variant>/${bt}):"
  for p in profiles/*/*/; do
    [[ -f "${p}profile.json" ]] || continue
    pn="${p#profiles/}"; pn="${pn%/}"
    echo "- ${bt}${pn}${bt}"; pfound=1
  done
  (( pfound )) || echo "- (none yet)"
  echo "<!-- AUTO-INVENTORY:END -->"
}

# block_inclusive <file> <TAG> — print the block from <TAG>:BEGIN through <TAG>:END, inclusive of both
# marker lines. The read-only mirror of handoff.sh's replace_block: verify-coherence.sh compares the block
# IN the file to gen_inventory's output without touching git or the working tree.
block_inclusive() {
  awk -v b="$2:BEGIN" -v e="$2:END" 'index($0,b){p=1} p{print} index($0,e){p=0}' "$1"
}

# ai_os_components [file] -- print "name profile" for each component registered in .ai-os.yml's
# components: map (ADR-0003). Strips inline "# comments"; awk uses [ \t] (mawk lacks [[:space:]]).
# Used by verify-coherence.sh's component/profile graph-integrity check (ADR-0018 / Step 4.2).
ai_os_components() {
  local f="${1:-.ai-os.yml}"
  [[ -f "$f" ]] || return 0
  awk '
    /^components:[ \t]*$/             { inc=1; next }
    inc && /^[^ \t]/                  { inc=0 }
    inc && /^[ \t]+[A-Za-z0-9._-]+:/  {
      line=$0; sub(/^[ \t]+/,"",line)
      name=line; sub(/:.*/,"",name)
      val=line; sub(/^[^:]*:[ \t]*/,"",val); sub(/[ \t]*#.*$/,"",val); sub(/[ \t]+$/,"",val)
      print name, val
    }
  ' "$f"
}

# dead_links_in <markdown-file> -- print each RELATIVE link/image target in the file whose path does NOT
# resolve to an existing repo file (the orphaned-reference half of coherence, ADR-0018 / Step 4.3). Skips
# external URLs (any scheme), in-page anchors, and link titles; strips a #fragment/?query; resolves targets
# relative to the file's own directory (CommonMark). Fenced code blocks are stripped so example paths inside
# triple-backtick blocks don't false-positive. Caller is at repo root; a target starting with / is root-relative.
dead_links_in() {
  local mdf="$1" dir
  dir="$(dirname "$mdf")"
  awk 'BEGIN{c=0} /^```/{c=!c; next} !c' "$mdf" \
    | grep -oE '\]\([^)]+\)' \
    | sed -E 's/^\]\(//; s/\)$//' \
    | while IFS= read -r tgt; do
        case "$tgt" in
          '<'*'>') tgt="${tgt#<}"; tgt="${tgt%>}" ;;   # <dest> may contain spaces
          *' '*)   tgt="${tgt%% *}" ;;                  # strip a ` "title"` suffix (bare dests have no spaces)
        esac
        case "$tgt" in
          ''|\#*|//*|*://*|mailto:*|tel:*|data:*) continue ;;
        esac
        tgt="${tgt%%#*}"; tgt="${tgt%%\?*}"
        [[ -n "$tgt" ]] || continue
        if [[ "$tgt" == /* ]]; then resolved=".${tgt}"; else resolved="${dir}/${tgt}"; fi
        [[ -e "$resolved" ]] || printf '%s\n' "$tgt"
      done
}

# --- autonomous episodic capture (ADR-0016) ---------------------------------------------------------
# die + any non-zero exit -> the memory DB, with NO AI in the loop. Best-effort + NON-FATAL (never breaks
# the caller); guarded against recursion (db.sh sets AI_OS_NO_CAPTURE) and against subshells (main shell only).
# _AI_OS_LIB_DIR is THIS file's own dir, so capture finds db.sh even when the caller never set $DIR (BUG-17).
_AI_OS_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_capture() {  # <kind> <summary> [detail]
  [[ -n "${BATS_TEST_DIRNAME:-}" && -z "${AI_OS_DB:-}" ]] && return 0   # under bats, only write when a test opted into a temp AI_OS_DB (no real-db pollution)
  [[ -n "${AI_OS_NO_CAPTURE:-}" ]] && return 0
  [[ -f "$_AI_OS_LIB_DIR/db.sh" ]] || return 0
  ( AI_OS_NO_CAPTURE=1 bash "$_AI_OS_LIB_DIR/db.sh" remember "$1" "$2" --detail "${3:-}" \
      --actor "${AI_OS_ACTOR:-system:$(basename "${0:-script}")}" --task "${AI_OS_TASK:-}" ) >/dev/null 2>&1 || true
}
_ai_os_on_exit() {
  local code="${1:-0}"
  [[ "$code" -eq 0 ]] && return 0                 # only failures are noteworthy
  [[ "${BASHPID:-$$}" != "$$" ]] && return 0      # subshells don't log
  [[ -n "${AI_OS_NO_CAPTURE:-}" ]] && return 0    # die already logged, or we're inside db.sh
  _capture error "non-zero exit ($code) from $(basename "${0:-script}")" "${_ai_os_errcmd:-unhandled failure}"
}
# Arm the failure-capture traps only in real script runs — never under bats (would clobber bats's own EXIT
# trap) or when _lib is merely sourced for inspection. die() captures directly, so it is unaffected.
# errtrace makes ERR fire inside functions/subshells too; it records the command that tripped, so the EXIT
# capture says WHAT failed (the deterministic base for unpredictable errors), not just "non-zero exit N".
_ai_os_errcmd=""
if [[ -z "${BATS_TEST_DIRNAME:-}" ]]; then
  set -o errtrace
  trap '_ai_os_errcmd=$BASH_COMMAND' ERR
  trap '_ai_os_on_exit $?' EXIT
fi
