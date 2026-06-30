#!/usr/bin/env bash
# db.sh — the AI-Dev-OS memory DB (ADR-0016): the ONE reader/writer for episodic + semantic + bug memory.
# SQLite + FTS5, local + gitignored. Callers use defined, parameterized, secret-scanned ops — never raw SQL.
#   db.sh remember <kind> "<summary>" [--detail D --task T --component C --scope S --refs R --actor A --role R]
#   db.sh learn <category> "<title>" "<body>" [--tags T --scope S --source-task T]
#   db.sh bug <add|update> BUG-NN [--severity --status --symptom --root-cause --fix --guard --scope --fixed-pr --found-by]
#   db.sh recall "<query>" [--kind K --scope S --since DAYS --limit N]
#   db.sh state [--scope S]   ·   db.sh export registry   ·   db.sh sync   ·   db.sh ledger <event> <task_id> "<note>"
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$DIR/_lib.sh"
cd "$(repo_root)"
export AI_OS_NO_CAPTURE=1   # db.sh is the logger; never let the autonomous-capture hook recurse into it

DB="${AI_OS_DB:-$(repo_root)/reports/metrics/memory.db}"   # AI_OS_DB override lets tests use a throwaway DB
SCHEMA="$DIR/db/schema.sql"
command -v sqlite3 >/dev/null 2>&1 || die "sqlite3 not found" \
  "the memory DB needs the SQLite CLI (FTS5-enabled, which Ubuntu's package is)" \
  "install it: sudo apt-get install -y sqlite3"
mkdir -p "$(dirname "$DB")"
[[ -f "$SCHEMA" ]] || die "missing $SCHEMA" "the schema file is gone" "restore scripts/db/schema.sql"
sqlite3 "$DB" < "$SCHEMA" >/dev/null   # idempotent; >/dev/null silences PRAGMA journal_mode's 'wal' echo

now_ms() {                                                          # epoch ms; portable: some `date` builds
  local s n; read -r s n < <(date '+%s %N')                         # ignore %3N and emit 9-digit %N (→ ns),
  [[ "$n" =~ ^[0-9]+$ ]] || n=0                                     # so build ms from %s and %N ourselves
  printf '%s\n' "$(( s * 1000 + (10#$n) / 1000000 ))"
}
esc()     { printf "%s" "${1:-}" | sed "s/'/''/g"; }                 # SQLite string escaping (double the quote)
q()       { sqlite3 -batch "$DB" "$1"; }                             # statements (INSERT/UPDATE)
qlist()   { sqlite3 -batch -cmd ".mode list" "$DB" "$1"; }           # SELECTs that emit one display column/row
ftsterms(){ printf '%s' "${1:-}" | tr -c 'A-Za-z0-9 ' ' ' | tr -s ' '; }   # strip FTS5 syntax → plain terms

# idempotent migrations — CREATE TABLE IF NOT EXISTS can't add a column to a table that already exists (ADR-0017).
_has_col() { [[ -n "$(sqlite3 "$DB" "SELECT 1 FROM pragma_table_info('$1') WHERE name='$2' LIMIT 1;")" ]]; }
_has_col bug found_by || sqlite3 "$DB" "ALTER TABLE bug ADD COLUMN found_by TEXT;"

has_secret() {   # ADR-0014: memory must never store a credential. Env-var REFERENCES (process.env.X, ${X},
  # <PLACEHOLDER>) are the CORRECT pattern, not credentials — strip them first so they don't trip the
  # generic 'secret: <20+ chars>' rule (BUG-26).
  printf '%s' "${1:-}" \
    | sed -E 's#(process\.env\.[A-Za-z_][A-Za-z0-9_]*|import\.meta\.env\.[A-Za-z_][A-Za-z0-9_]*|os\.environ\[[^]]*\]|Deno\.env\.[A-Za-z_][A-Za-z0-9_]*|\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|<[A-Za-z_][A-Za-z0-9_]*>)##g' \
    | grep -iqE \
    -e 'sk_(live|test)_[0-9A-Za-z]{16,}' -e 'gh[pousr]_[0-9A-Za-z]{30,}' -e 'github_pat_[0-9A-Za-z_]{30,}' \
    -e 'AKIA[0-9A-Z]{16}' -e 'whsec_[0-9A-Za-z]{16,}' -e 'BEGIN [A-Z ]*PRIVATE KEY' \
    -e '(secret|token|api[_-]?key|password|passwd|bearer)[[:space:]]*[:=][[:space:]]*[A-Za-z0-9/+_=.-]{20,}'
}
guard_secret() { if has_secret "$1"; then die "refusing to store a secret in memory" \
  "the text matches a credential pattern (ADR-0014)" "store an env-var NAME / reference, never the value"; fi; }

# --- ADR-0019: least-privilege write policy for workforce runs --------------------------------------
# A run is "confined" when AI_OS_ROLE is set and != lead — i.e. a worker that dispatch.sh/gate.sh launched
# with an injected role+component+actor. The operator (or Lead) running db.sh by hand has no AI_OS_ROLE and
# is unrestricted. Confined writes are pinned to the worker's OWN component scope + its injected actor, and
# may not write semantic (learn) memory. This is least-privilege + trusted provenance, NOT a sandbox: a
# worker with shell access could forge env or call sqlite3 directly — real isolation is separate (ADR-0019).
is_confined()    { [[ -n "${AI_OS_ROLE:-}" && "${AI_OS_ROLE:-}" != lead ]]; }
confined_actor() { printf '%s' "${AI_OS_ACTOR:-agent:unknown}"; }
confined_scope() {
  [[ -n "${AI_OS_COMPONENT:-}" ]] || die "confined write without a component" \
    "AI_OS_ROLE=${AI_OS_ROLE:-} but AI_OS_COMPONENT is unset — a workforce run must declare its component (ADR-0019)" \
    "dispatch.sh/gate.sh set it for component tasks; if you are the operator, unset AI_OS_ROLE"
  printf 'component:%s' "${AI_OS_COMPONENT}"
}

sub="${1:-}"; shift || true
case "$sub" in
  init) log "memory DB ready at $DB" ;;

  remember)
    kind="${1:?usage: db.sh remember <kind> <summary> [flags]}"; summary="${2:?summary required}"; shift 2 || true
    detail=""; task=""; comp=""; scope=""; refs=""; actor="${AI_OS_ACTOR:-human:${USER:-unknown}}"; role="${AI_OS_ROLE:-}"
    while [[ $# -gt 0 ]]; do case "$1" in
      --detail) detail="$2"; shift 2;; --task) task="$2"; shift 2;; --component) comp="$2"; shift 2;;
      --scope) scope="$2"; shift 2;; --refs) refs="$2"; shift 2;; --actor) actor="$2"; shift 2;; --role) role="$2"; shift 2;;
      *) die "unknown flag: $1";; esac; done
    [[ -n "$scope" ]] || { [[ -n "$comp" ]] && scope="component:$comp" || scope="os"; }
    if is_confined; then scope="$(confined_scope)"; comp="${AI_OS_COMPONENT}"; actor="$(confined_actor)"; fi   # ADR-0019
    guard_secret "$summary $detail"
    q "INSERT INTO episodic(ts,actor,role,scope,task_id,component,kind,summary,detail,refs) VALUES($(now_ms),'$(esc "$actor")','$(esc "$role")','$(esc "$scope")','$(esc "$task")','$(esc "$comp")','$(esc "$kind")','$(esc "$summary")','$(esc "$detail")','$(esc "$refs")');"
    ;;

  learn)
    category="${1:?usage: db.sh learn <category> <title> <body> [flags]}"; title="${2:?title required}"; body="${3:?body required}"; shift 3 || true
    tags=""; scope="os"; stask=""
    while [[ $# -gt 0 ]]; do case "$1" in
      --tags) tags="$2"; shift 2;; --scope) scope="$2"; shift 2;; --source-task) stask="$2"; shift 2;; *) die "unknown flag: $1";; esac; done
    if is_confined; then die "learn (semantic memory) is denied for workforce runs (AI_OS_ROLE=${AI_OS_ROLE})" \
      "semantic / OS knowledge is Lead-curated; a confined worker may only 'remember' in its own scope (ADR-0019)" \
      "escalate the insight to the Lead, or run as the operator (unset AI_OS_ROLE)"; fi
    guard_secret "$title $body"
    q "INSERT INTO semantic(created_ts,updated_ts,scope,category,title,body,tags,source_task) VALUES($(now_ms),$(now_ms),'$(esc "$scope")','$(esc "$category")','$(esc "$title")','$(esc "$body")','$(esc "$tags")','$(esc "$stask")');"
    ;;

  bug)
    act="${1:?usage: db.sh bug <add|update> BUG-NN [flags]}"; bid="${2:?BUG-NN required}"; shift 2 || true
    sev=""; st=""; scope=""; symp=""; rc=""; fix=""; guard=""; pr=""; fb=""
    while [[ $# -gt 0 ]]; do case "$1" in
      --severity) sev="$2"; shift 2;; --status) st="$2"; shift 2;; --scope) scope="$2"; shift 2;;
      --symptom) symp="$2"; shift 2;; --root-cause) rc="$2"; shift 2;; --fix) fix="$2"; shift 2;;
      --guard) guard="$2"; shift 2;; --fixed-pr) pr="$2"; shift 2;; --found-by) fb="$2"; shift 2;;
      *) die "unknown flag: $1";; esac; done
    if is_confined; then scope="$(confined_scope)"; fb="$(confined_actor)"; fi   # ADR-0019
    guard_secret "$symp $rc $fix $guard"
    [[ "$act" == add ]] && q "INSERT OR IGNORE INTO bug(id,found_ts,status,scope,found_by) VALUES('$(esc "$bid")',$(now_ms),'open','$(esc "${scope:-os}")','$(esc "${fb:-${AI_OS_ACTOR:-human:${USER:-unknown}}}")');"
    [[ -n "$fb" ]] && q "UPDATE bug SET found_by='$(esc "$fb")' WHERE id='$(esc "$bid")';"   # explicit --found-by also re-attributes
    [[ -n "$scope" ]] && q "UPDATE bug SET scope='$(esc "$scope")'  WHERE id='$(esc "$bid")';"
    [[ -n "$sev"  ]] && q "UPDATE bug SET severity='$(esc "$sev")'  WHERE id='$(esc "$bid")';"
    [[ -n "$symp" ]] && q "UPDATE bug SET symptom='$(esc "$symp")'  WHERE id='$(esc "$bid")';"
    [[ -n "$rc"   ]] && q "UPDATE bug SET root_cause='$(esc "$rc")' WHERE id='$(esc "$bid")';"
    [[ -n "$fix"  ]] && q "UPDATE bug SET fix='$(esc "$fix")'       WHERE id='$(esc "$bid")';"
    [[ -n "$guard" ]] && q "UPDATE bug SET guard='$(esc "$guard")'  WHERE id='$(esc "$bid")';"
    [[ -n "$pr"   ]] && q "UPDATE bug SET fixed_pr='$(esc "$pr")'   WHERE id='$(esc "$bid")';"
    if [[ -n "$st" ]]; then
      q "UPDATE bug SET status='$(esc "$st")' WHERE id='$(esc "$bid")';"
      # if/then/fi, NOT a terminal `[[…]] && q`: a false `&&` makes this `if` (the branch's last command)
      # return non-zero and trips `set -e` before the script's `exit 0` (registry BUG-13 real root cause).
      if [[ "$st" == fixed ]]; then q "UPDATE bug SET fixed_ts=$(now_ms) WHERE id='$(esc "$bid")';"; fi
    fi
    ;;

  recall)
    query="${1:?usage: db.sh recall <query> [flags]}"; shift || true
    kind=""; scope=""; since=""; limit=5; where=""
    while [[ $# -gt 0 ]]; do case "$1" in
      --kind) kind="$2"; shift 2;; --scope) scope="$2"; shift 2;; --since) since="$2"; shift 2;; --limit) limit="$2"; shift 2;; *) die "unknown flag: $1";; esac; done
    terms="$(ftsterms "$query")"; [[ -n "${terms// }" ]] || die "empty query after sanitizing" "the query had no searchable terms" "pass words/codes to match"
    [[ -n "$kind"  ]] && where="$where AND e.kind='$(esc "$kind")'"
    [[ -n "$scope" ]] && where="$where AND (e.scope='$(esc "$scope")' OR e.scope='os')"
    [[ -n "$since" ]] && where="$where AND e.ts >= $(now_ms) - ${since%%[!0-9]*}*86400000"
    echo "## episodic"
    qlist "SELECT coalesce(datetime(e.ts/1000,'unixepoch'),'?')||' · '||e.kind||' · '||e.actor||' · '||e.summary FROM episodic_fts JOIN episodic e ON e.id=episodic_fts.rowid WHERE episodic_fts MATCH '$(esc "$terms")'$where ORDER BY e.ts DESC LIMIT $limit;"
    echo "## semantic"
    qlist "SELECT s.category||' · '||s.title||' · '||substr(s.body,1,160) FROM semantic_fts JOIN semantic s ON s.id=semantic_fts.rowid WHERE semantic_fts MATCH '$(esc "$terms")' AND s.status='active' ORDER BY s.updated_ts DESC LIMIT $limit;"
    echo "## bugs"
    qlist "SELECT id||' · '||status||' · '||coalesce(severity,'')||' · '||coalesce(symptom,'') FROM bug WHERE symptom LIKE '%$(esc "$query")%' OR root_cause LIKE '%$(esc "$query")%' OR id LIKE '%$(esc "$query")%' ORDER BY found_ts DESC LIMIT $limit;"
    ;;

  state)
    scope=""; [[ "${1:-}" == --scope ]] && scope="${2:-}"
    swhere=""; [[ -n "$scope" ]] && swhere="WHERE scope='$(esc "$scope")' OR scope='os'"
    echo "# AI-OS state — $(date -u +%FT%TZ)"
    echo "## recent events"
    qlist "SELECT coalesce(datetime(ts/1000,'unixepoch'),'?')||' · '||kind||' · '||actor||' · '||summary FROM episodic $swhere ORDER BY ts DESC LIMIT 12;"
    echo "## open bugs"
    qlist "SELECT id||' · '||coalesce(severity,'')||' · '||status||' · '||coalesce(symptom,'') FROM bug WHERE status!='fixed' ORDER BY found_ts;"
    echo "## counts"
    qlist "SELECT 'episodic='||(SELECT count(*) FROM episodic)||'  semantic='||(SELECT count(*) FROM semantic)||'  bugs(open)='||(SELECT count(*) FROM bug WHERE status!='fixed');"
    ;;

  export)
    case "${1:-registry}" in
      registry)
        echo "# Bug registry — generated from the memory DB (do not hand-edit; ADR-0016)"; echo
        echo "| ID | sev | status | found | fixed | by | symptom |"; echo "|---|---|---|---|---|---|---|"
        qlist "SELECT '| '||id||' | '||coalesce(severity,'')||' | '||status||' | '||coalesce(date(found_ts/1000,'unixepoch'),'?')||' | '||coalesce(date(fixed_ts/1000,'unixepoch'),'—')||' | '||coalesce(found_by,'?')||' | '||replace(coalesce(symptom,''),'|','/')||' |' FROM bug ORDER BY id;"
        echo; echo "## Details"
        qlist "SELECT char(10)||'### '||id||' — '||status||' ('||coalesce(severity,'')||') · '||coalesce(found_by,'?')||char(10)|| '- symptom: '||coalesce(symptom,'')||char(10)|| '- root cause: '||coalesce(root_cause,'')||char(10)|| '- fix: '||coalesce(fix,'')||char(10)|| '- guard: '||coalesce(guard,'') FROM bug ORDER BY id;"
        ;;
      *) die "unknown export target: ${1:-}" "supported: registry" "db.sh export registry";;
    esac
    ;;

  ledger)   # back-compat: ledger-append.sh <event> <task_id> <note> → episodic, actor=system
    event="${1:?usage: db.sh ledger <event> <task_id> <note>}"; tid="${2:-}"; note="${3:-}"
    bash "$DIR/db.sh" remember "$event" "${note:-$event}" --task "$tid" --actor "system:${AI_OS_CALLER:-ledger}" || true
    ;;

  research) die "db.sh research is researcher-role only (v2)" "broad/deep query is reserved for research tasks" "use: db.sh recall <query> --scope <s> for task-scoped retrieval";;
  sync)     # regenerate the committed registry view from the DB (durability: a wipe can't lose it — ADR-0016)
    out="${AI_OS_REGISTRY_MD:-$(repo_root)/knowledge/postmortems/registry.md}"
    bash "$DIR/db.sh" export registry > "$out"   # via bash, not direct exec: don't depend on the exec bit (BUG-01 class)
    log "regenerated $out — commit it so the registry survives a DB wipe" ;;
  *) die "unknown subcommand: ${sub:-<none>}" "db.sh supports: remember · learn · bug · recall · state · export · ledger · init" "see the header of scripts/db.sh";;
esac
exit 0   # belt-and-suspenders; real set -e safety is structural (if/then/fi, never a terminal `&&`-list)
