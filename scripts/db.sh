#!/usr/bin/env bash
# db.sh — the AI-Dev-OS memory DB (ADR-0016): the ONE reader/writer for episodic + semantic + bug memory.
# SQLite + FTS5, local + gitignored. Callers use defined, parameterized, secret-scanned ops — never raw SQL.
#   db.sh remember <kind> "<summary>" [--detail D --task T --component C --scope S --refs R --actor A --role R]
#   db.sh learn <category> "<title>" "<body>" [--tags T --scope S --source-task T]
#   db.sh bug <add|update> BUG-NN [--severity --status --symptom --root-cause --fix --guard --scope --fixed-pr]
#   db.sh recall "<query>" [--kind K --scope S --since DAYS --limit N]
#   db.sh state [--scope S]      ·   db.sh export registry   ·   db.sh ledger <event> <task_id> "<note>"
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
sqlite3 "$DB" < "$SCHEMA"   # idempotent (all IF NOT EXISTS) — keeps schema current

now_ms()  { date +%s%3N; }
esc()     { printf "%s" "${1:-}" | sed "s/'/''/g"; }                 # SQLite string escaping (double the quote)
q()       { sqlite3 -batch "$DB" "$1"; }                             # statements (INSERT/UPDATE)
qlist()   { sqlite3 -batch -cmd ".mode list" "$DB" "$1"; }           # SELECTs that emit one display column/row
ftsterms(){ printf '%s' "${1:-}" | tr -c 'A-Za-z0-9 ' ' ' | tr -s ' '; }   # strip FTS5 syntax → plain terms

has_secret() {   # ADR-0014: memory must never store a credential
  printf '%s' "${1:-}" | grep -iqE \
    -e 'sk_(live|test)_[0-9A-Za-z]{16,}' -e 'gh[pousr]_[0-9A-Za-z]{30,}' -e 'github_pat_[0-9A-Za-z_]{30,}' \
    -e 'AKIA[0-9A-Z]{16}' -e 'whsec_[0-9A-Za-z]{16,}' -e 'BEGIN [A-Z ]*PRIVATE KEY' \
    -e '(secret|token|api[_-]?key|password|passwd|bearer)[[:space:]]*[:=][[:space:]]*[A-Za-z0-9/+_=.-]{20,}'
}
guard_secret() { if has_secret "$1"; then die "refusing to store a secret in memory" \
  "the text matches a credential pattern (ADR-0014)" "store an env-var NAME / reference, never the value"; fi; }

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
    guard_secret "$summary $detail"
    q "INSERT INTO episodic(ts,actor,role,scope,task_id,component,kind,summary,detail,refs) VALUES($(now_ms),'$(esc "$actor")','$(esc "$role")','$(esc "$scope")','$(esc "$task")','$(esc "$comp")','$(esc "$kind")','$(esc "$summary")','$(esc "$detail")','$(esc "$refs")');"
    ;;

  learn)
    category="${1:?usage: db.sh learn <category> <title> <body> [flags]}"; title="${2:?title required}"; body="${3:?body required}"; shift 3 || true
    tags=""; scope="os"; stask=""
    while [[ $# -gt 0 ]]; do case "$1" in
      --tags) tags="$2"; shift 2;; --scope) scope="$2"; shift 2;; --source-task) stask="$2"; shift 2;; *) die "unknown flag: $1";; esac; done
    guard_secret "$title $body"
    q "INSERT INTO semantic(created_ts,updated_ts,scope,category,title,body,tags,source_task) VALUES($(now_ms),$(now_ms),'$(esc "$scope")','$(esc "$category")','$(esc "$title")','$(esc "$body")','$(esc "$tags")','$(esc "$stask")');"
    ;;

  bug)
    act="${1:?usage: db.sh bug <add|update> BUG-NN [flags]}"; bid="${2:?BUG-NN required}"; shift 2 || true
    sev=""; st=""; scope=""; symp=""; rc=""; fix=""; guard=""; pr=""
    while [[ $# -gt 0 ]]; do case "$1" in
      --severity) sev="$2"; shift 2;; --status) st="$2"; shift 2;; --scope) scope="$2"; shift 2;;
      --symptom) symp="$2"; shift 2;; --root-cause) rc="$2"; shift 2;; --fix) fix="$2"; shift 2;;
      --guard) guard="$2"; shift 2;; --fixed-pr) pr="$2"; shift 2;; *) die "unknown flag: $1";; esac; done
    guard_secret "$symp $rc $fix $guard"
    [[ "$act" == add ]] && q "INSERT OR IGNORE INTO bug(id,found_ts,status,scope) VALUES('$(esc "$bid")',$(now_ms),'open','$(esc "${scope:-os}")');"
    [[ -n "$scope" ]] && q "UPDATE bug SET scope='$(esc "$scope")'  WHERE id='$(esc "$bid")';"
    [[ -n "$sev"  ]] && q "UPDATE bug SET severity='$(esc "$sev")'  WHERE id='$(esc "$bid")';"
    [[ -n "$symp" ]] && q "UPDATE bug SET symptom='$(esc "$symp")'  WHERE id='$(esc "$bid")';"
    [[ -n "$rc"   ]] && q "UPDATE bug SET root_cause='$(esc "$rc")' WHERE id='$(esc "$bid")';"
    [[ -n "$fix"  ]] && q "UPDATE bug SET fix='$(esc "$fix")'       WHERE id='$(esc "$bid")';"
    [[ -n "$guard" ]] && q "UPDATE bug SET guard='$(esc "$guard")'  WHERE id='$(esc "$bid")';"
    [[ -n "$pr"   ]] && q "UPDATE bug SET fixed_pr='$(esc "$pr")'   WHERE id='$(esc "$bid")';"
    if [[ -n "$st" ]]; then
      q "UPDATE bug SET status='$(esc "$st")' WHERE id='$(esc "$bid")';"
      [[ "$st" == fixed ]] && q "UPDATE bug SET fixed_ts=$(now_ms) WHERE id='$(esc "$bid")';"
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
    qlist "SELECT datetime(e.ts/1000,'unixepoch')||' · '||e.kind||' · '||e.actor||' · '||e.summary FROM episodic_fts JOIN episodic e ON e.id=episodic_fts.rowid WHERE episodic_fts MATCH '$(esc "$terms")'$where ORDER BY e.ts DESC LIMIT $limit;"
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
    qlist "SELECT datetime(ts/1000,'unixepoch')||' · '||kind||' · '||actor||' · '||summary FROM episodic $swhere ORDER BY ts DESC LIMIT 12;"
    echo "## open bugs"
    qlist "SELECT id||' · '||coalesce(severity,'')||' · '||status||' · '||coalesce(symptom,'') FROM bug WHERE status!='fixed' ORDER BY found_ts;"
    echo "## counts"
    qlist "SELECT 'episodic='||(SELECT count(*) FROM episodic)||'  semantic='||(SELECT count(*) FROM semantic)||'  bugs(open)='||(SELECT count(*) FROM bug WHERE status!='fixed');"
    ;;

  export)
    case "${1:-registry}" in
      registry)
        echo "# Bug registry — generated from the memory DB (do not hand-edit; ADR-0016)"; echo
        echo "| ID | sev | status | found | fixed | symptom |"; echo "|---|---|---|---|---|---|"
        qlist "SELECT '| '||id||' | '||coalesce(severity,'')||' | '||status||' | '||date(found_ts/1000,'unixepoch')||' | '||coalesce(date(fixed_ts/1000,'unixepoch'),'—')||' | '||replace(coalesce(symptom,''),'|','/')||' |' FROM bug ORDER BY id;"
        ;;
      *) die "unknown export target: ${1:-}" "supported: registry" "db.sh export registry";;
    esac
    ;;

  ledger)   # back-compat: ledger-append.sh <event> <task_id> <note> → episodic, actor=system
    event="${1:?usage: db.sh ledger <event> <task_id> <note>}"; tid="${2:-}"; note="${3:-}"
    "$DIR/db.sh" remember "$event" "${note:-$event}" --task "$tid" --actor "system:${AI_OS_CALLER:-ledger}" || true
    ;;

  research) die "db.sh research is researcher-role only (v2)" "broad/deep query is reserved for research tasks" "use: db.sh recall <query> --scope <s> for task-scoped retrieval";;
  sync)     log "db.sh sync (derived-index rebuild) is v1.1 — not yet implemented";;
  *) die "unknown subcommand: ${sub:-<none>}" "db.sh supports: remember · learn · bug · recall · state · export · ledger · init" "see the header of scripts/db.sh";;
esac
