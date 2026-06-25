#!/usr/bin/env bash
# verify-coherence.sh — CI fitness function (ADR-0018, analysis Step 4): fail if the repo's generated docs
# or its component/profile graph have drifted. Four checks; ALL problems are aggregated, printed, then a
# single non-zero exit:
#   1. generated AUTO-INVENTORY blocks match a fresh gen_inventory (block-compare, NOT a whole-file git diff
#      — architecture/README.md is mixed prose+block and ci-local.sh runs on a dirty tree; see ADR-0018).
#   2. component/profile GRAPH integrity — every .ai-os.yml registration resolves to a real component dir +
#      profile leaf, every component dir is registered, and .ai-os.yml agrees with each .component.yml.
#      Unused profiles are allowed (profiles/ is a template library, ADR-0003).
#   3. dead relative links — markdown links/images whose target file no longer exists (history under
#      architecture/adr/, reports/, knowledge/postmortems/ is exempt — it may cite the past).
#   4. stubs — markdown that is empty/whitespace/comment-only, or carries an explicit <!-- STUB --> marker.
# Only DETERMINISTIC generated blocks are checked; AUTO-STATE/AUTO-SHIPPED (timestamp + live git/PR state)
# are out of scope by design.
# Invoke: bash scripts/verify-coherence.sh   (runs in ci-local.sh and os-ci)
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$DIR/_lib.sh"
cd "$(repo_root)"
shopt -s nullglob

problems=0
problem() { printf '\033[31m  ✗ %s\033[0m\n' "$1" >&2; problems=$((problems + 1)); }

# md_files — null-delimited list of LIVING markdown to scan (checks 3+4). Tracked files only when the repo
# has a commit, so .gitignored vendored trees (node_modules/) are never scanned and it's fast; a find
# fallback covers a fresh repo with no HEAD (the bats fixture). History that may cite the past is excluded
# either way: architecture/adr/, reports/, knowledge/postmortems/.
md_files() {
  if git rev-parse --verify -q HEAD >/dev/null 2>&1; then
    git ls-files -z -- '*.md' ':!:architecture/adr/*' ':!:reports/*' ':!:knowledge/postmortems/*'
  else
    find . -type f -name '*.md' \
      -not -path './.git/*' -not -path '*/node_modules/*' \
      -not -path './architecture/adr/*' -not -path './reports/*' -not -path './knowledge/postmortems/*' -print0
  fi
}

# --- check 1: generated inventory blocks still match the repo ----------------------------------------
fresh="$(gen_inventory)"
for f in architecture/README.md docs/handoff/SESSION-HANDOFF.md; do
  [[ -f "$f" ]] || continue
  grep -q 'AUTO-INVENTORY:BEGIN' "$f" || continue
  if [[ "$(block_inclusive "$f" AUTO-INVENTORY)" != "$fresh" ]]; then
    problem "stale AUTO-INVENTORY in $f — hand-edited, or components/profiles changed without 'bash scripts/handoff.sh'"
    diff <(block_inclusive "$f" AUTO-INVENTORY) <(printf '%s\n' "$fresh") >&2 || true
  fi
done

# --- check 2: component/profile graph integrity (declared <-> present) -------------------------------
declared="$(ai_os_components)"   # "name profile" per registered component

# declared -> present: every registration resolves to a real dir + profile leaf
while read -r name prof; do
  [[ -n "$name" ]] || continue
  [[ -d "components/$name" ]]             || problem ".ai-os.yml registers '$name' but components/$name/ is missing (dangling registration)"
  [[ -f "profiles/$prof/profile.json" ]] || problem ".ai-os.yml maps '$name' -> '$prof' but profiles/$prof/ is not a profile (no profile.json)"
done <<< "$declared"

# present -> declared: every component dir is registered, and its .component.yml agrees
for d in components/*/; do
  [[ -d "$d" ]] || continue
  name="${d#components/}"; name="${name%/}"
  awk -v n="$name" '$1==n{f=1} END{exit !f}' <<< "$declared" \
    || problem "components/$name/ exists but is not registered in .ai-os.yml (orphan — register it, or extract/remove it)"
  [[ -f "${d}.component.yml" ]] || continue
  cprof="$(yaml_scalar "${d}.component.yml" profile)"
  [[ -n "$cprof" ]] || continue
  [[ -f "profiles/$cprof/profile.json" ]] || problem "components/$name/.component.yml profile '$cprof' has no profiles/$cprof/ leaf"
  dprof="$(awk -v n="$name" '$1==n{print $2}' <<< "$declared")"
  [[ -z "$dprof" || "$dprof" == "$cprof" ]] || problem "profile mismatch for '$name': .ai-os.yml='$dprof' vs .component.yml='$cprof'"
done

# --- checks 3+4: living markdown — dead relative links (4.3) + stub/placeholder docs (4.4) -----------
# History that may legitimately cite removed files is exempt: ADRs, reports, postmortems.
while IFS= read -r -d '' mdf; do
  rel="${mdf#./}"
  if grep -q '<!-- STUB -->' "$mdf"; then
    problem "stub marker in $rel — fill it in or remove the file ('<!-- STUB -->' must not ship)"
  fi
  if [[ -z "$(sed -E 's/<!--.*-->//g' "$mdf" | tr -d '[:space:]')" ]]; then
    problem "empty doc $rel — only whitespace/comments, no content (write it or remove the file)"
  fi
  while IFS= read -r tgt; do
    [[ -n "$tgt" ]] || continue
    problem "dead link in $rel — '$tgt' does not resolve to a repo file"
  done < <(dead_links_in "$mdf")
done < <(md_files)

if (( problems )); then
  die "coherence: $problems problem(s) — the repo and its generated/declared maps disagree" \
    "a generated block was hand-edited, or a component/profile was added/removed/renamed without updating its registration" \
    "fix the ✗ lines above — inventory: 'bash scripts/handoff.sh'; graph: edit .ai-os.yml or the component's .component.yml"
fi
log "coherence: inventory + graph + links + stubs OK ✓"
