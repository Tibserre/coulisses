import assert from "node:assert/strict";
import { test } from "node:test";
import { audioLine, formatDay } from "./retention.ts";

const NOW = new Date("2026-10-07T12:00:00Z");

test("a day is said without its year when it is this year's", () => {
  assert.equal(formatDay("2026-10-14T12:00:00Z", NOW), "14 octobre");
  assert.equal(formatDay("2027-01-05T12:00:00Z", NOW), "5 janvier 2027");
});

test("the header says what becomes of the audio, only when it matters", () => {
  const base = { purge_on: null, removed_at: null, removed_reason: null } as const;
  assert.equal(audioLine({ ...base, state: "kept" }, NOW), "audio gardé");
  assert.equal(
    audioLine({ ...base, state: "removed", removed_at: "2026-10-01T08:00:00Z", removed_reason: "purge" }, NOW),
    "audio supprimé le 1er octobre",
  );
  assert.equal(
    audioLine({ ...base, state: "announced", purge_on: "2026-10-14T12:00:00Z" }, NOW),
    "suppression de l'audio le 14 octobre",
  );
  assert.equal(audioLine({ ...base, state: "scheduled", purge_on: "2026-12-26T12:00:00Z" }, NOW), null);
  assert.equal(audioLine({ ...base, state: "never_processed" }, NOW), null);
});

test("− and + go from one usual value to the next, within their bounds", async () => {
  const { nextStep } = await import("./retention.ts");
  const steps = [7, 14, 30, 60, 90];
  assert.equal(nextStep(steps, 30, true, 1, Infinity), 60);
  assert.equal(nextStep(steps, 30, false, 1, Infinity), 14);
  assert.equal(nextStep(steps, 45, true, 1, Infinity), 60); // set elsewhere, between two
  assert.equal(nextStep(steps, 45, false, 1, Infinity), 30);
  assert.equal(nextStep(steps, 90, true, 1, Infinity), 90); // the last: stays
  assert.equal(nextStep(steps, 7, false, 1, Infinity), 7);
  assert.equal(nextStep(steps, 14, false, 10, Infinity), 10); // the notice never above the keeping
  assert.equal(nextStep(steps, 7, true, 1, 12), 12);
});

test("the keepings offered stop at three months, and keep a value set before", async () => {
  const { retentionChoices, retentionWrite } = await import("./retention.ts");
  assert.deepEqual(retentionChoices(30), [7, 14, 30, 60, 90]);
  assert.deepEqual(retentionChoices(365), [7, 14, 30, 60, 90, 365]);
  assert.deepEqual(retentionChoices(45), [7, 14, 30, 45, 60, 90]);
  assert.deepEqual(retentionWrite(30, 7), { retention_days: 30, notice_days: 7 });
  assert.deepEqual(retentionWrite(7, 14), { retention_days: 7, notice_days: 7 });
});

test("the days left are counted in calendar days, never below today", async () => {
  const { daysUntil, untilWords } = await import("./retention.ts");
  const now = new Date(2026, 10, 12, 23, 30);
  assert.equal(daysUntil(new Date(2026, 10, 13, 0, 30).toISOString(), now), 1);
  assert.equal(daysUntil(new Date(2026, 10, 15, 9).toISOString(), now), 3);
  assert.equal(untilWords(0), "aujourd'hui");
  assert.equal(untilWords(-2), "aujourd'hui");
  assert.equal(untilWords(1), "demain");
  assert.equal(untilWords(7), "dans 7 jours");
});

test("the reminders are said in one line, the earliest first", async () => {
  const { remindersLine } = await import("./retention.ts");
  assert.equal(remindersLine([7]), "Rappel 7 jours avant");
  assert.equal(remindersLine([3, 7]), "Rappel 7 jours, puis 3 jours avant");
  assert.equal(remindersLine([7, 3, 1]), "Rappel 7 jours, puis 3 jours, puis 1 jour avant");
  assert.equal(remindersLine([]), "Sans rappel");
});

test("only the sessions that lost their audio, and kept their text, are counted", async () => {
  const { sessionsWithoutAudio } = await import("./retention.ts");
  const entry = (kind: string, session_id: string | null) =>
    ({ id: 0, at: "", kind, session_id, session_title: null, files: 1, bytes: 1, problems: [] }) as never;
  assert.equal(
    sessionsWithoutAudio([
      entry("purge", "a"),
      entry("audio_deletion", "b"),
      entry("purge", "a"),
      entry("session_deletion", "c"),
      entry("purge", "e"),
      entry("session_deletion", "e"),
      entry("conversion", "d"),
      entry("backup_pruning", null),
    ]),
    2,
  );
});
