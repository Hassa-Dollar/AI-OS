#!/usr/bin/env bash
# _lib.sh -- shared helpers for the AI-Dev-OS scripts. Source this; do not run it.
# Pure bash + coreutils/awk/sed/git. No yq dependency.
# Tolerates inline "# comments" after YAML keys/values (the documented schema uses them).
# awk uses [ \t] not POSIX classes, because Ubuntu default mawk lacks [[:space:]].

log()  { printf '\033[36m[ai-os]\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[33m[ai-os][warn]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m[ai-os][err]\033[0m %s\n' "$*" >&2; exit 1; }

repo_root() { git rev-parse --show-toplevel 2>/dev/null || die "not inside a git repo"; }

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
