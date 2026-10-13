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
