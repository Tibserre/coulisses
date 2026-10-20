-- Step 13 of the plan (schema-donnees.md, ADR 0052): only the three latest copies of the
-- database are kept; the older ones are deleted, and each deletion is in the journal.

-- A copy of the database belongs to no session: `session_id` may be empty, and the journal
-- accepts `backup_pruning`. SQLite cannot change a CHECK nor a NOT NULL: the table is made
-- again, its rows kept as they are.
CREATE TABLE deletion_log_new (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (
        kind IN ('purge', 'audio_deletion', 'session_deletion', 'conversion', 'backup_pruning')
    ),
    session_id TEXT CHECK ((session_id IS NULL) = (kind = 'backup_pruning')),
    session_title TEXT,
    detail TEXT NOT NULL
);

INSERT INTO deletion_log_new (id, at, kind, session_id, session_title, detail)
    SELECT id, at, kind, session_id, session_title, detail FROM deletion_log;

DROP TABLE deletion_log;

ALTER TABLE deletion_log_new RENAME TO deletion_log;

CREATE INDEX deletion_log_by_date ON deletion_log (at);
