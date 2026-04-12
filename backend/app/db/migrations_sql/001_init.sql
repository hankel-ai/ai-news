CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    key             TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    type            TEXT NOT NULL,
    url             TEXT,
    enabled         INTEGER NOT NULL DEFAULT 1,
    keywords        TEXT,
    max_stories     INTEGER NOT NULL DEFAULT 5,
    min_score       INTEGER,
    subreddit       TEXT,
    sort            TEXT,
    extra_config    TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sources_enabled ON sources(enabled);

CREATE TABLE IF NOT EXISTS stories (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id           INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    title               TEXT NOT NULL,
    url                 TEXT NOT NULL,
    url_normalized      TEXT NOT NULL,
    source_name         TEXT NOT NULL,
    summary             TEXT,
    article_content     TEXT,
    score               INTEGER,
    published_at        TEXT,
    keywords_matched    TEXT,
    first_seen_at       TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(url_normalized)
);
CREATE INDEX IF NOT EXISTS idx_stories_published_desc ON stories(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_stories_first_seen_desc ON stories(first_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_stories_source ON stories(source_id);

CREATE TABLE IF NOT EXISTS settings (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fetch_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT NOT NULL,
    stories_new     INTEGER NOT NULL DEFAULT 0,
    stories_seen    INTEGER NOT NULL DEFAULT 0,
    sources_ok      INTEGER NOT NULL DEFAULT 0,
    sources_failed  INTEGER NOT NULL DEFAULT 0,
    duration_ms     INTEGER,
    error           TEXT
);
CREATE INDEX IF NOT EXISTS idx_fetch_runs_started_desc ON fetch_runs(started_at DESC);

CREATE TABLE IF NOT EXISTS source_health (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    run_id          INTEGER REFERENCES fetch_runs(id) ON DELETE SET NULL,
    fetched_at      TEXT NOT NULL,
    ok              INTEGER NOT NULL,
    story_count     INTEGER NOT NULL DEFAULT 0,
    latency_ms      INTEGER NOT NULL DEFAULT 0,
    error           TEXT
);
CREATE INDEX IF NOT EXISTS idx_source_health_source_fetched ON source_health(source_id, fetched_at DESC);
