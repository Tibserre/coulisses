-- Step 3 of the plan: summaries made by the application (ADR 0018, 0020, 0022): each one is
-- a run of the application (its folder keeps every prompt sent, word for word), listed here.

CREATE TABLE generation (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES session (id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES run (id),
    action_ref TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX generation_by_session ON generation (session_id, id);

-- What each space runs after processing, and with which model (ADR 0020: no space type,
-- these settings are filled once by a starting template, then edited freely).
CREATE TABLE action_preference (
    space_id INTEGER NOT NULL REFERENCES space (id),
    action_ref TEXT NOT NULL,
    model TEXT,
    auto_run INTEGER NOT NULL DEFAULT 0 CHECK (auto_run IN (0, 1)),
    PRIMARY KEY (space_id, action_ref)
);

CREATE TABLE app_setting (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- The spaces that exist today were the troupe: they keep the Résumé Impro after processing.
INSERT INTO action_preference (space_id, action_ref, auto_run)
SELECT id, 'resume-impro', 1 FROM space;
