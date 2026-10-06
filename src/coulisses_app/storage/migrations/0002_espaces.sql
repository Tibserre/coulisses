-- Step 2 of the plan: spaces instead of a troupe (ADR 0020), people, attendees, glossary
-- and the journal of the user's corrections (ADR 0018, docs/technique/schema-donnees.md).

ALTER TABLE troupe RENAME TO space;
ALTER TABLE space ADD COLUMN voice_recognition INTEGER NOT NULL DEFAULT 0
    CHECK (voice_recognition IN (0, 1));
ALTER TABLE space ADD COLUMN archived_at TEXT;

ALTER TABLE session RENAME COLUMN troupe_id TO space_id;
-- Until now the only count was the number typed at import, nobody being checked: it is the
-- number of attendees nobody named, added to the checked ones.
ALTER TABLE session RENAME COLUMN attendee_count TO unnamed_attendees;

-- A person belongs to one space (ADR 0020). `color_slot` keeps the same colour for them
-- from one session to the next.
CREATE TABLE person (
    id INTEGER PRIMARY KEY,
    space_id INTEGER NOT NULL REFERENCES space (id),
    kind TEXT NOT NULL CHECK (kind IN ('member', 'guest')),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    role TEXT,
    color_slot INTEGER NOT NULL CHECK (color_slot >= 0),
    created_at TEXT NOT NULL,
    archived_at TEXT
);

CREATE INDEX person_by_space ON person (space_id, kind, name);

CREATE TABLE attendee (
    session_id TEXT NOT NULL REFERENCES session (id) ON DELETE CASCADE,
    person_id INTEGER NOT NULL REFERENCES person (id),
    PRIMARY KEY (session_id, person_id)
);

CREATE TABLE glossary_entry (
    id INTEGER PRIMARY KEY,
    space_id INTEGER NOT NULL REFERENCES space (id),
    term TEXT NOT NULL CHECK (length(trim(term)) > 0),
    category TEXT,
    variants TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    archived_at TEXT
);

-- Corrections are only ever added: undoing one adds an entry pointing at it (ADR 0018).
CREATE TABLE edit (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES session (id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES run (id),
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    person_id INTEGER REFERENCES person (id),
    anchor_start_s REAL,
    anchor_end_s REAL,
    reverts_edit_id INTEGER REFERENCES edit (id),
    created_at TEXT NOT NULL
);

CREATE INDEX edit_by_session ON edit (session_id, id);
