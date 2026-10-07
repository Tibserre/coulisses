-- Step 9 of the plan (schema-donnees.md, ADR 0029): keeping the audio, purging it, deleting
-- by hand, and the trace of every deletion.

-- `keep_audio`: the user's choice for this session, never purged. `retain_until`: the
-- audio kept until then at least (« Prolonger »). `purge_announced_at`: when the coming
-- purge was announced (banner and notification); a purge only happens once the notice has
-- run its course from then. `audio_removed_at` / `audio_removed_reason`: the audio is gone
-- (`purge` when due, `audio_deletion` by hand); the text stays.
ALTER TABLE session ADD COLUMN keep_audio INTEGER NOT NULL DEFAULT 0 CHECK (keep_audio IN (0, 1));
ALTER TABLE session ADD COLUMN retain_until TEXT;
ALTER TABLE session ADD COLUMN purge_announced_at TEXT;
ALTER TABLE session ADD COLUMN audio_removed_at TEXT;
ALTER TABLE session ADD COLUMN audio_removed_reason TEXT
    CHECK (audio_removed_reason IN ('purge', 'audio_deletion'));

-- One row per purge or deletion. No foreign key: the trace outlives the session. A session
-- deleted keeps no text here (no title): only when, what kind, and the files and sizes.
CREATE TABLE deletion_log (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('purge', 'audio_deletion', 'session_deletion')),
    session_id TEXT NOT NULL,
    session_title TEXT,
    detail TEXT NOT NULL
);

CREATE INDEX deletion_log_by_date ON deletion_log (at);
