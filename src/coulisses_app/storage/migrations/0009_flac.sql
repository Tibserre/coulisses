-- Step 12e of the plan (schema-donnees.md, ADR 0046): the tracks recorded in the app are
-- kept in FLAC once the recording is over, without loss.

-- The fingerprint of a track's samples (its PCM, little-endian, interleaved), whatever its
-- format: the same for a WAV and the FLAC made from it. Set when a recording closes; empty
-- for an import and for a recording made before this migration (those are not converted
-- without the user's consent).
ALTER TABLE audio_source ADD COLUMN pcm_sha256 TEXT;

-- A conversion is written in the journal: the WAV files it removed, once their FLAC was
-- proven to hold the same samples. SQLite cannot change a CHECK: the table is made again,
-- its rows kept as they are.
CREATE TABLE deletion_log_new (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    kind TEXT NOT NULL
        CHECK (kind IN ('purge', 'audio_deletion', 'session_deletion', 'conversion')),
    session_id TEXT NOT NULL,
    session_title TEXT,
    detail TEXT NOT NULL
);

INSERT INTO deletion_log_new (id, at, kind, session_id, session_title, detail)
    SELECT id, at, kind, session_id, session_title, detail FROM deletion_log;

DROP TABLE deletion_log;

ALTER TABLE deletion_log_new RENAME TO deletion_log;

CREATE INDEX deletion_log_by_date ON deletion_log (at);
