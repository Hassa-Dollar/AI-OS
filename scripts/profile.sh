#!/usr/bin/env bash
# profile.sh — apply a profile to a component (ADR-0003): copy the profile's seam files to their
# canonical locations and record the binding. This is the ONE place that moves a profile's files into
# place; the rest of the determinism layer just reads the canonical files (never branches on a name).
#   profile.sh apply <family/variant> [component]   # default component: service
#   profile.sh show                                  # print the .ai-os.yml registry
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$DIR/_lib.sh"
cd "$(repo_root)"

# update_registry <component> <profile> — upsert the mapping in .ai-os.yml
update_registry() {
  local name="$1" prof="$2" f=".ai-os.yml"
  [[ -f "$f" ]] || printf 'components:\n' > "$f"
  grep -q '^components:' "$f" || printf 'components:\n' >> "$f"
  if grep -qE "^[[:space:]]+${name}:" "$f"; then
    sed -i -E "s#^([[:space:]]+)${name}:.*#\1${name}: ${prof}#" "$f"
  else
    awk -v n="$name" -v p="$prof" 'BEGIN{d=0}{print} /^components:/&&!d{print "  " n ": " p; d=1}' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
  fi
}

cmd="${1:-show}"
case "$cmd" in
  apply)
    prof="${2:?usage: profile.sh apply <family/variant> [component]}"
    comp_name="${3:-service}"
    src="profiles/$prof"
    [[ -d "$src" ]] || die "no profile '$prof'" \
      "there is no directory profiles/$prof" \
      "list options: ls -d profiles/*/* — or add one by copying a sibling leaf (ADR-0003)"
    [[ -f "$src/profile.json" ]] || die "profile '$prof' has no profile.json" \
      "a profile leaf must carry profile.json (contract profile.schema)" \
      "create profiles/$prof/profile.json with roles + thresholds"
    comp="components/$comp_name"; mkdir -p "$comp"

    # seam copies (idempotent). Canonical destinations the scripts/CI read.
    [[ -f "$src/conventions.md" ]] && { mkdir -p architecture; cp "$src/conventions.md" architecture/conventions.md; log "conventions -> architecture/conventions.md"; }
    [[ -f "$src/ci-env.sh" ]]     && { cp "$src/ci-env.sh" scripts/ci-env.sh; log "ci-env -> scripts/ci-env.sh"; }
    [[ -f "$src/ci.yml" ]]        && { mkdir -p .github/workflows; cp "$src/ci.yml" .github/workflows/ci.yml; log "ci.yml -> .github/workflows/ci.yml"; }
    if [[ -d "$src/product-skeleton" ]]; then
      if [[ -z "$(ls -A "$comp" 2>/dev/null | grep -vxF '.component.yml' || true)" ]]; then
        cp -r "$src/product-skeleton/." "$comp/"; log "skeleton -> $comp/"
      else
        warn "component $comp is not empty — skeleton NOT copied" \
          "refusing to overwrite existing component files" \
          "delete $comp first if you really want a fresh skeleton from the profile"
      fi
    fi

    printf '# profile governing this component (ADR-0003); locked for its life.\nprofile: %s\n' "$prof" > "$comp/.component.yml"
    update_registry "$comp_name" "$prof"
    log "applied '$prof' to component '$comp_name' (recorded in .ai-os.yml + $comp/.component.yml)"
    log "review the copied seam files, then commit."
    ;;
  show)
    [[ -f .ai-os.yml ]] && cat .ai-os.yml || echo "(no .ai-os.yml yet — run: scripts/profile.sh apply <family/variant>)"
    ;;
  *)
    die "unknown subcommand '$cmd'" "profile.sh supports: apply, show" \
      "e.g. scripts/profile.sh apply web-app/ts-node-service service"
    ;;
esac
