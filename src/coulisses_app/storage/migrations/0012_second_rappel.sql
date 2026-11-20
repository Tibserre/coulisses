-- ADR 0083: two fixed reminders before a purge, 7 days then 3 days before it.
-- `purge_announced_at` stays the first one (the notice counts from it, ADR 0029);
-- `purge_reminded_at` is when the second one was given (banner and notification), so it is
-- given once, even across a restart. Cleared with the announcement, whenever that is.
ALTER TABLE session ADD COLUMN purge_reminded_at TEXT;

-- The audio is kept 90 days at most (ADR 0083, the user's choice): a longer delay set before
-- comes down to 90 days, and its notice with it if it was longer. A shorter delay is
-- announced again, as when the user shortens it (ADR 0029): every coming purge is announced
-- anew with its full notice, never one without it. Nothing changes when no delay was above.
UPDATE session SET purge_announced_at = NULL, purge_reminded_at = NULL
    WHERE EXISTS (
        SELECT 1 FROM app_setting
        WHERE key = 'conservation_jours' AND CAST(value AS INTEGER) > 90
    );
UPDATE app_setting SET value = '90'
    WHERE key = 'preavis_jours' AND CAST(value AS INTEGER) > 90;
UPDATE app_setting SET value = '90'
    WHERE key = 'conservation_jours' AND CAST(value AS INTEGER) > 90;
