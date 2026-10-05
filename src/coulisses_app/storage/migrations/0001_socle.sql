-- Step 1 of the plan: one troupe, sessions with their audio sources, the processing queue
-- and the runs (ADR 0018, docs/technique/schema-donnees.md).

CREATE TABLE troupe (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

INSERT INTO troupe (name, created_at) VALUES ('Ma troupe', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'));

CREATE TABLE session (
    id TEXT PRIMARY KEY,
    troupe_id INTEGER NOT NULL REFERENCES troupe (id),
    title TEXT,
    title_edited INTEGER NOT NULL DEFAULT 0 CHECK (title_edited IN (0, 1)),
    recorded_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    reference_source_id TEXT NOT NULL,
    attendee_count INTEGER CHECK (attendee_count >= 1)
);

CREATE TABLE audio_source (
    session_id TEXT NOT NULL REFERENCES session (id) ON DELETE CASCADE,
    source_id TEXT NOT NULL,
    origin TEXT NOT NULL CHECK (origin IN ('captured', 'imported')),
    original_name TEXT NOT NULL,
    file_name TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    duration_s REAL,
    sample_rate INTEGER,
    channels INTEGER,
    codec TEXT,
    device TEXT,
    offset_s REAL NOT NULL DEFAULT 0,
    drift_ppm REAL NOT NULL DEFAULT 0,
    added_at TEXT NOT NULL,
    removed_at TEXT,
    PRIMARY KEY (session_id, source_id)
);

-- `kind` grows with later steps (stage, generation): checked in code, not here.
CREATE TABLE job (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES session (id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('queued', 'running', 'done', 'failed')),
    params TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error TEXT
);

CREATE INDEX job_by_state ON job (state, id);

-- `status` mirrors the run's provenance once finished and never changes afterwards;
-- « périmée » (stale) is computed, never stored (ADR 0018).
CREATE TABLE run (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES session (id) ON DELETE CASCADE,
    job_id INTEGER REFERENCES job (id),
    stage TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    producer TEXT NOT NULL CHECK (producer IN ('engine', 'app')),
    engine_version TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    error_summary TEXT
);

CREATE INDEX run_by_session ON run (session_id, stage, created_at);
CREATE INDEX run_by_job ON run (job_id, stage);

-- Runs are only ever deleted with their session (whole-session deletion, step 9): these
-- links go with them.
CREATE TABLE run_upstream (
    run_id TEXT NOT NULL REFERENCES run (id) ON DELETE CASCADE,
    upstream_run_id TEXT NOT NULL REFERENCES run (id) ON DELETE CASCADE,
    PRIMARY KEY (run_id, upstream_run_id)
);

CREATE TABLE active_run (
    session_id TEXT NOT NULL REFERENCES session (id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES run (id),
    PRIMARY KEY (session_id, stage)
);
