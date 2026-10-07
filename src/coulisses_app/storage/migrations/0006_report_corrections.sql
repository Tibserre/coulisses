-- Step 7 of the plan (schema-donnees.md): a stage run again gives a new version; the
-- corrections of the version it replaces are carried over, or listed as not carried.

-- One row per correction considered, for the new « who said what » run. `carried_edit_id`
-- is the copy made on that run (undone like any correction); none when it was not
-- carried, or when nothing had to be written (two voices already one). `partial`: carried
-- for some of its lines only, the others listed with the reason. `description`
-- says what the correction was, as it read on the run it was made on. Corrections and runs
-- are only ever deleted with their session (step 9): these rows go with them.
CREATE TABLE edit_carryover (
    edit_id INTEGER NOT NULL REFERENCES edit (id) ON DELETE CASCADE,
    target_run_id TEXT NOT NULL REFERENCES run (id) ON DELETE CASCADE,
    outcome TEXT NOT NULL CHECK (outcome IN ('applied', 'partial', 'not_applied')),
    reason TEXT,
    carried_edit_id INTEGER REFERENCES edit (id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (edit_id, target_run_id)
);

CREATE INDEX edit_carryover_by_target ON edit_carryover (target_run_id);
