-- ADR 0083: two fixed reminders before a purge, 7 days then 3 days before it.
-- `purge_announced_at` stays the first one (the notice counts from it, ADR 0029);
-- `purge_reminded_at` is when the second one was given (banner and notification), so it is
-- given once, even across a restart. Cleared with the announcement, whenever that is.
ALTER TABLE session ADD COLUMN purge_reminded_at TEXT;
