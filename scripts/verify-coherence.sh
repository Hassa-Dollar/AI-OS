#!/usr/bin/env bash
# verify-coherence.sh — CI fitness function (ADR-0018, analysis Step 4): fail if the repo's generated docs
# or its component/profile graph have drifted. Nine checks; ALL problems are aggregated, printed, then a
# single non-zero exit:
#   1. generated AUTO-INVENTORY blocks match a fresh gen_inventory (block-compare, NOT a whole-file git diff
#      — architecture/README.md is mixed prose+block and ci-local.sh runs on a dirty tree; see ADR-0018).
#   2. component/profile GRAPH integrity — every .ai-os.yml registration resolves to a real component dir +
#      profile leaf, every component dir is registered, and .ai-os.yml agrees with each .component.yml.
#      Unused profiles are allowed (profiles/ is a template library, ADR-0003).
#   3. dead relative links — markdown links/images whose target file no longer exists (history under
#      architecture/adr/, reports/, knowledge/postmortems/ is exempt — it may cite the past).
#   4. stubs — markdown that is empty/whitespace/comment-only, or carries an explicit <!-- STUB --> marker.
#   5. role docs — agents/*.md + prompts/*.md must NOT hard-code a workforce model (it's bound per-profile in
#      profile.json + AGENTS.md §1, ADR-0003); the Lead (Opus) is fixed and allowed.
#   6. exec bits — every executed scripts/*.sh is mode 100755 in the index (env-independent; ADR-0010).
#   7. spec roles — a component task spec names a role (owner_role); any model pin needs override_reason (ADR-0022).
#   8. profile lint — every profile.json binding is on-catalog and P8 is solvable for every author role (ADR-0022).
#   9. catalog table — the AGENTS.md §1 slugs match architecture/catalog.json, the machine source (ADR-0022).
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

# role_docs — null-delimited agents/*.md + prompts/*.md (role cards + prompt headers). Tracked when possible;
# find fallback for the bats fixture (silent if the dirs don't exist).
role_docs() {
  if git rev-parse --verify -q HEAD >/dev/null 2>&1; then
    git ls-files -z -- 'agents/*.md' 'prompts/*.md'
  else
    find agents prompts -type f -name '*.md' -print0 2>/dev/null
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

# --- check 5: role cards + prompts name no workforce model (ADR-0003 / #87) -------------------------
# Which model plays a role is bound per-profile (profile.json) + the AGENTS.md §1 catalog — never in a role
# card or prompt (those describe the durable ROLE). The Lead (Opus) is fixed, so opus/claude is fine.
while IFS= read -r -d '' rf; do
  if grep -iqE '\b(glm|kimi|qwen|deepseek|mimo|minimax)' "$rf"; then
    problem "role doc ${rf#./} hard-codes a workforce model — bind it per-profile (profile.json, ADR-0003) + AGENTS.md §1, not here"
  fi
done < <(role_docs)

# --- check 6: executed scripts carry the exec bit IN THE INDEX (ADR-0010) ---------------------------
# The Windows<->WSL (\\wsl.localhost) bridge drops Unix mode bits and core.fileMode=false makes git ignore
# the on-disk bit — so the TREE must own +x or a fresh Linux clone can't run ./scripts/x.sh. Turns the
# recurring "restore exec bits" chore into a deterministic guard. Sourced-only libs are exempt.
if git rev-parse --verify -q HEAD >/dev/null 2>&1; then
  sourced_only=" _lib.sh ci-env.sh "
  while IFS=$'\t' read -r meta path; do
    [[ -n "$path" ]] || continue
    [[ "$path" == scripts/*/* ]] && continue            # only top-level scripts/, not scripts/test/
    base="${path##*/}"
    [[ "$sourced_only" == *" $base "* ]] && continue    # sourced libraries are not executed
    [[ "${meta%% *}" == "100755" ]] || problem "scripts/$base is mode ${meta%% *} in the index, not 100755 — run: git add --chmod=+x $path  (exec-bit env-independence, ADR-0010)"
  done < <(git ls-files -s -- 'scripts/*.sh')
fi

# --- check 7: component task specs name a role; a model pin is an audited exception (ADR-0022) -------
# The profile is the SINGLE source of role→model. Any model/verifier pin on a spec whose component has a
# profile requires override_reason: — an unreasoned pin silently drifts when the profile is re-bumped (the
# failure mode behind BUG-27/30). ACTIVE specs only; OS/chore specs (no profile) are exempt.
for spec in tasks/active/*.md; do
  [[ -f "$spec" ]] || continue
  pj="$(profile_of_spec "$spec")"; [[ -n "$pj" ]] || continue
  pins="$(override_of_spec "$spec")"
  [[ -n "$pins" && -z "$(fm_scalar "$spec" override_reason)" ]] \
    && problem "spec ${spec#./} pins '$pins' without override_reason — the profile is the single source (ADR-0022): omit to inherit via owner_role, or state the reason"
done

# --- check 8: profile lint (ADR-0022) — bindings on-catalog; P8 solvable for every author role -------
# Structural P8: for each bound author role that shares the verifier's family, a cross-family
# verifier_secondary must exist, or resolve_roles cannot produce a legal pairing.
for pj in profiles/*/*/profile.json; do
  [[ -f "$pj" ]] || continue
  ver="$(json_get "$pj" verifier)"; vsec="$(json_get "$pj" verifier_secondary)"
  while IFS=$'\t' read -r role slug; do
    [[ -n "$role" ]] || continue
    _catalog_table | awk -v s="$slug" '$1==s{f=1} END{exit !f}' \
      || problem "profile $pj binds $role -> '$slug' which is off-catalog (ADR-0009; see architecture/catalog.json)"
    case "$role" in verifier|verifier_secondary) continue ;; esac
    if [[ -n "$ver" && "$(family_of "$slug")" == "$(family_of "$ver")" ]]; then
      [[ -n "$vsec" && "$(family_of "$slug")" != "$(family_of "$vsec")" ]] \
        || problem "profile $pj: author role $role ('$slug') shares the verifier's family and no cross-family verifier_secondary exists — P8 unsolvable (ADR-0022)"
    fi
  done < <(json_roles "$pj")
done

# --- check 9: AGENTS.md §1 catalog table matches architecture/catalog.json (ADR-0022) ----------------
# catalog.json is the machine source; the human-readable table must not drift from it. Skipped when either
# file is absent (the bats fixture repos).
if [[ -f AGENTS.md && -f architecture/catalog.json ]]; then
  tbl="$(grep -oE '`opencode-go/[A-Za-z0-9._-]+`' AGENTS.md | tr -d '\`' | sort -u)"
  cat_slugs="$(_catalog_table | awk '{print $1}' | sort -u)"
  [[ "$tbl" == "$cat_slugs" ]] || problem "AGENTS.md §1 catalog table != architecture/catalog.json — out-of-sync slugs: $(comm -3 <(printf '%s\n' "$tbl") <(printf '%s\n' "$cat_slugs") | tr -s '\n\t' ' ')"
fi

if (( problems )); then
  die "coherence: $problems problem(s) — the repo and its generated/declared maps disagree" \
    "a generated block was hand-edited, or a component/profile was added/removed/renamed without updating its registration" \
    "fix the ✗ lines above — inventory: 'bash scripts/handoff.sh'; graph: edit .ai-os.yml or the component's .component.yml"
fi
log "coherence: inventory + graph + links + stubs + roles OK ✓"
