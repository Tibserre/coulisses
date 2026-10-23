// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import type { StageView } from "./api.ts";
import { processingDiscs } from "./processing.ts";

const stage = (
  name: string,
  state: StageView["state"],
  progress: [number, number] | null = null,
): StageView =>
  ({
    stage: name,
    label: name,
    state,
    progress: progress
      ? { phase: "", done: progress[0], total: progress[1], unit: "s" }
      : null,
  }) as StageView;

test("the text disc weighs the transcription three times the alignment", () => {
  const d = processingDiscs(
    [
      stage("transcribe", "succeeded"),
      stage("align", "running", [1, 2]),
      stage("diarize", "pending"),
    ],
    3600,
  );
  assert.equal(d.text, (3 + 0.5) / 4);
  assert.equal(d.voices, 0);
  assert.equal(d.joining, false);
});

test("both done: who said what joins them", () => {
  const d = processingDiscs(
    [
      stage("transcribe", "succeeded"),
      stage("align", "succeeded"),
      stage("diarize", "succeeded"),
      stage("attribute", "running"),
    ],
    3600,
  );
  assert.equal(d.joining, true);
  assert.equal(d.minutesLeft, 1);
});

test("a stage without progress counts as not started, and no length says no time", () => {
  const d = processingDiscs(
    [stage("transcribe", "running"), stage("diarize", "stalled", [5, 10])],
    null,
  );
  assert.equal(d.text, 0);
  assert.equal(d.voices, 0.5);
  assert.equal(d.stalled, true);
  assert.equal(d.minutesLeft, null);
});

test("what is left is what the slower one has left", () => {
  const d = processingDiscs(
    [stage("transcribe", "running", [1, 4]), stage("diarize", "succeeded")],
    3600,
  );
  assert.equal(d.minutesLeft, Math.round(10 * 0.75));
});
