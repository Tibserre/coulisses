-- ADR 0091: « Jeu et personnages », a setting of the space (Jeu ⇄ Discussion while recording,
-- the genre of the chapters, the characters played when naming the voices). Off at first in
-- every space, those already there included (the user's choice); a session already made keeps
-- what it has.
ALTER TABLE space ADD COLUMN theatre INTEGER NOT NULL DEFAULT 0 CHECK (theatre IN (0, 1));
