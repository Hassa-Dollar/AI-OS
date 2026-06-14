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

# fm_list <file> <key> -- list items under "key:" (key line may carry an inline comment).
fm_list() { fm_block "$1" | awk -v k="$2" '$0 ~ "^"k":"{g=1;next} g&&/^[ \t]+-[ \t]+/{sub(/^[ \t]+-[ \t]+/,"");sub(/[ \t]+#.*$/,"");print;next} g&&/^[^ \t]/{g=0}'; }

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
         "set COMPONENT=<name> for this run, e.g. COMPONENT=service scripts/gate.sh <id>" ;;
  esac
}

# json_get <file> <key> -- first string value for "key": "value" in a (flat-ish) JSON file.
# No jq dependency; sufficient for profile.json's small, flat shape (roles + thresholds).
json_get() { sed -nE "s/.*\"$2\"[[:space:]]*:[[:space:]]*\"([^\"]+)\".*/\1/p" "$1" 2>/dev/null | head -1; }
