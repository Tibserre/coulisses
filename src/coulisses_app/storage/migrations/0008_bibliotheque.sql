-- Step 8 of the plan (schema-donnees.md, ADR 0030): projects, and the full-text search.

-- A project groups sessions of a space (a show, for a troupe). Archived, never deleted:
-- its sessions stay in it.
CREATE TABLE project (
    id INTEGER PRIMARY KEY,
    space_id INTEGER NOT NULL REFERENCES space (id),
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    archived_at TEXT
);

CREATE INDEX project_by_space ON project (space_id, name);

-- A session belongs to one project of its space, or to none.
ALTER TABLE session ADD COLUMN project_id INTEGER REFERENCES project (id);

-- The search: a cache rebuilt from the corrected transcripts, the notes and the summaries,
-- never a source of truth. Accents and case ignored. `kind`: turn, note, summary, title;
-- `ref`: the line's index, the note's id, the generation's id; `at_s`: its measured time.
CREATE VIRTUAL TABLE search_index USING fts5 (
    session_id UNINDEXED,
    kind UNINDEXED,
    ref UNINDEXED,
    at_s UNINDEXED,
    text,
    tokenize = 'unicode61 remove_diacritics 2'
);

-- What each session's indexed text was made from: when it changed, the session is indexed
-- again (lazily, at the next search).
CREATE TABLE search_state (
    session_id TEXT PRIMARY KEY REFERENCES session (id) ON DELETE CASCADE,
    key TEXT NOT NULL
);
