-- Step 5 of the plan (schema-donnees.md): the user's actions and the session's notes.

-- An action written or modified by the user. `based_on`: the provided action it stands in
-- for (the original stays in the repository, restorable by archiving this row); empty for
-- an action of the user's own, whose key is `perso-<id>`. Never deleted: archived.
CREATE TABLE action (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    prompt TEXT NOT NULL,
    based_on TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT
);

-- At most one modified version in force per provided action.
CREATE UNIQUE INDEX action_in_force_for ON action (based_on)
    WHERE based_on IS NOT NULL AND archived_at IS NULL;

-- Notes taken by hand: `at_s` empty for a note written after the session (step 5); timed
-- notes taken while recording come at step 6.
CREATE TABLE note (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES session (id) ON DELETE CASCADE,
    at_s REAL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX note_by_session ON note (session_id, at_s);
