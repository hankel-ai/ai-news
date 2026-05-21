-- Add AI analysis columns to stories
ALTER TABLE stories ADD COLUMN ai_summary TEXT;
ALTER TABLE stories ADD COLUMN relevance_score INTEGER;
ALTER TABLE stories ADD COLUMN topics TEXT;
ALTER TABLE stories ADD COLUMN analyzed_at TEXT;

-- Index for sorting by relevance
CREATE INDEX IF NOT EXISTS idx_stories_relevance ON stories(relevance_score DESC);

-- Trends table for topic cluster tracking
CREATE TABLE IF NOT EXISTS trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'normal',
    story_count INTEGER NOT NULL DEFAULT 0,
    detected_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    notified INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_trends_expires ON trends(expires_at);
CREATE INDEX IF NOT EXISTS idx_trends_notified ON trends(notified, expires_at);
