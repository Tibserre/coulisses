-- Step 6 of the plan (schema-donnees.md): recording in the application.

-- A source captured by the service: `recording` while it is written (still so after a
-- crash, until the next start repairs it), `complete` once stopped, `recovered` when an
-- interrupted recording was repaired at start. Empty for an imported file.
ALTER TABLE audio_source ADD COLUMN capture_state TEXT
    CHECK (capture_state IN ('recording', 'complete', 'recovered'));
ALTER TABLE audio_source ADD COLUMN capture_ended_at TEXT;

-- Markers set while recording, at a time of the recording (pauses left out).
CREATE TABLE marker (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES session (id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('scene', 'discussion', 'key_moment')),
    at_s REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX marker_by_session ON marker (session_id, at_s);
