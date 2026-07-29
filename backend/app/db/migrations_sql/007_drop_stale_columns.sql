-- Drop columns and settings rows left behind by removed features.
-- NOTE: migrations.py splits this file on the statement separator, so no
-- comment in a migration may contain that character.
--
-- stories.image_url  - the image pipeline was deleted 2026-07-29, its only
--                      consumer (StoryCard.tsx) was never rendered.
-- fetch_runs.error   - declared in 001_init but never once written, 0 of 2193
--                      rows populated. Run-level failure is already covered by
--                      fetch_runs.status plus per-source rows in source_health.
--
-- Neither column is indexed, so DROP COLUMN is safe. Requires SQLite 3.35 or
-- newer, the runtime image ships 3.46.
ALTER TABLE stories DROP COLUMN image_url;

ALTER TABLE fetch_runs DROP COLUMN error;

-- Orphaned settings rows. hover_preview_enabled belonged to the deleted hover
-- popup. breaking_threshold and notifications_enabled belonged to the trends
-- and alerts feature dropped in 005_drop_trends.sql. None are in DEFAULTS, so
-- nothing re-seeds them.
DELETE FROM settings WHERE key IN (
    'hover_preview_enabled',
    'breaking_threshold',
    'notifications_enabled'
)
