-- Permanent ledger of every URL ever ingested, so that retention pruning a
-- story cannot let a still-linked article re-enter the feed as brand new.
CREATE TABLE IF NOT EXISTS seen_urls (
    url_normalized TEXT PRIMARY KEY,
    first_seen_at  TEXT NOT NULL
);

-- Seed from whatever survives in stories today. Anything already pruned is
-- unknown to us and may resurface once more, but only once.
INSERT OR IGNORE INTO seen_urls (url_normalized, first_seen_at)
SELECT url_normalized, MIN(first_seen_at) FROM stories GROUP BY url_normalized
