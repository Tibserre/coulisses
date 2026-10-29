-- The assistants' connector (ADR 0065): two options of each space, both closed by default,
-- and the journal of what the connector read, never purged. Whether the connector is open
-- is the `connector_open` key of `app_setting` (absent: closed).

ALTER TABLE space ADD COLUMN connector_access INTEGER NOT NULL DEFAULT 0
    CHECK (connector_access IN (0, 1));

ALTER TABLE space ADD COLUMN connector_names INTEGER NOT NULL DEFAULT 0
    CHECK (connector_names IN (0, 1));

-- No foreign key on the session: the trace outlives a deleted session, and keeps no text
-- of it (its title is read at display time, from the session if it still exists).
CREATE TABLE connector_access_log (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    tool TEXT NOT NULL CHECK (
        tool IN ('chercher', 'lister_seances', 'lire_seance', 'lire_resume', 'lire_transcript')
    ),
    session_id TEXT,
    -- Empty with the session: a search or a list that gave nothing passed nothing on.
    names_shared INTEGER CHECK (names_shared IN (0, 1)),
    CHECK ((session_id IS NULL) = (names_shared IS NULL))
);

CREATE INDEX connector_access_log_by_date ON connector_access_log (at);
