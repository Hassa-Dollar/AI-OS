-- AI-Dev-OS memory DB (ADR-0016). Applied idempotently by scripts/db.sh. SQLite + FTS5.
-- Local + gitignored (the file is *.db). Holds EPISODIC + SEMANTIC + BUG memory; git stays the
-- source of truth for procedural/source (scripts, prompts, contracts, ADRs, specs).
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', '1');

-- EPISODIC — the dated event log / black box. actor = agent:<model> | system:<script> | human:<user>.
CREATE TABLE IF NOT EXISTS episodic (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ts        INTEGER NOT NULL,                       -- epoch ms
  actor     TEXT NOT NULL,
  role      TEXT,
  scope     TEXT NOT NULL DEFAULT 'os',             -- os | component:<name>
  task_id   TEXT,
  component TEXT,
  kind      TEXT NOT NULL,                          -- dispatch|qa|land|guardrail|opus-gate|ci|bug|error|warn|fix|observation|decision
  summary   TEXT NOT NULL,
  detail    TEXT,
  refs      TEXT
);
CREATE INDEX IF NOT EXISTS idx_epi_ts    ON episodic(ts);
CREATE INDEX IF NOT EXISTS idx_epi_scope ON episodic(scope);
CREATE INDEX IF NOT EXISTS idx_epi_kind  ON episodic(kind);
-- append-only ⇒ an insert trigger keeps the FTS index in sync (no update/delete path needed).
CREATE VIRTUAL TABLE IF NOT EXISTS episodic_fts USING fts5(summary, detail, content='episodic', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS epi_ai AFTER INSERT ON episodic BEGIN
  INSERT INTO episodic_fts(rowid, summary, detail) VALUES (new.id, new.summary, new.detail);
END;

-- SEMANTIC — distilled, mutable knowledge.
CREATE TABLE IF NOT EXISTS semantic (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  created_ts  INTEGER NOT NULL,
  updated_ts  INTEGER NOT NULL,
  scope       TEXT NOT NULL DEFAULT 'os',
  category    TEXT NOT NULL,                        -- pattern|postmortem|root-cause|research-memo|convention|gotcha
  title       TEXT NOT NULL,
  body        TEXT NOT NULL,
  tags        TEXT,
  source_task TEXT,
  status      TEXT NOT NULL DEFAULT 'active'
);
CREATE VIRTUAL TABLE IF NOT EXISTS semantic_fts USING fts5(title, body, tags, content='semantic', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS sem_ai AFTER INSERT ON semantic BEGIN
  INSERT INTO semantic_fts(rowid, title, body, tags) VALUES (new.id, new.title, new.body, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS sem_ad AFTER DELETE ON semantic BEGIN
  INSERT INTO semantic_fts(semantic_fts, rowid, title, body, tags) VALUES ('delete', old.id, old.title, old.body, old.tags);
END;
CREATE TRIGGER IF NOT EXISTS sem_au AFTER UPDATE ON semantic BEGIN
  INSERT INTO semantic_fts(semantic_fts, rowid, title, body, tags) VALUES ('delete', old.id, old.title, old.body, old.tags);
  INSERT INTO semantic_fts(rowid, title, body, tags) VALUES (new.id, new.title, new.body, new.tags);
END;

-- BUG — the determinism-layer registry as a queryable, dated, lifecycle table (small ⇒ LIKE search, no FTS).
CREATE TABLE IF NOT EXISTS bug (
  id         TEXT PRIMARY KEY,                      -- BUG-NN
  found_ts   INTEGER NOT NULL,
  fixed_ts   INTEGER,
  severity   TEXT,
  status     TEXT NOT NULL,                         -- open|patched|fixed
  scope      TEXT NOT NULL DEFAULT 'os',
  symptom    TEXT,
  root_cause TEXT,
  fix        TEXT,
  guard      TEXT,
  fixed_pr   TEXT
);
