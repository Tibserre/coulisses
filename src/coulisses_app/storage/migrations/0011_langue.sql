-- ADR 0072: the language a session is transcribed in. Each space has a default one, taken
-- by its new sessions; each session has its own, which follows its version shown. A code of
-- the engine (ISO 639-1), never a list fixed here (P6): the languages are the engine's.
-- Every existing space and session is French, the only language before.
ALTER TABLE space ADD COLUMN language TEXT NOT NULL DEFAULT 'fr';

ALTER TABLE session ADD COLUMN language TEXT NOT NULL DEFAULT 'fr';
