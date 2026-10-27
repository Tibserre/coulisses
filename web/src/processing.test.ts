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

test("a stage under way never fills its disc: only its end does", () => {
  const d = processingDiscs([stage("diarize", "running", [95, 95])], 3600);
  assert.equal(d.voices, 0.9);
  assert.equal(
    processingDiscs([stage("diarize", "succeeded")], 3600).voices,
    1,
  );
});

test("a disc never goes back when the engine counts a new phase from zero", () => {
  const d = processingDiscs(
    [
      stage("transcribe", "running", [10, 100]),
      stage("align", "pending"),
      stage("diarize", "running", [0, 95]),
    ],
    3600,
    { text: 0.05, voices: 0.9 },
  );
  assert.equal(d.voices, 0.9);
  assert.equal(d.text, (3 * 0.1) / 4);
  // What is left follows what is shown.
  assert.equal(d.minutesLeft, Math.round(10 * (1 - d.text)));
});

test("the text disc goes on from the transcription to the alignment", () => {
  const d = processingDiscs(
    [
      stage("transcribe", "succeeded"),
      stage("align", "running", [100, 100]),
      stage("diarize", "running", [1, 2]),
    ],
    3600,
  );
  assert.equal(d.text, (3 + 0.9) / 4);
});

const phase = (step: number, steps: number, done: number, total: number) =>
  ({
    stage: "diarize",
    label: "diarize",
    state: "running",
    progress: { phase: "", done, total, unit: "windows", step, steps },
  }) as StageView;

test("the voices disc goes through the phases the engine counts, each a part", () => {
  const at = (s: StageView) => processingDiscs([s], 3600).voices;
  assert.equal(at(phase(1, 3, 0, 95)), 0);
  assert.equal(at(phase(1, 3, 95, 95)), 1 / 3);
  assert.equal(at(phase(2, 3, 19, 95)), (1 + 0.2) / 3);
  // The last phase done still stops short of full: only the end of the stage fills it.
  assert.equal(at(phase(3, 3, 1, 1)), 0.9);
});

test("a phase more, and the disc waits rather than go back", () => {
  const before = processingDiscs([phase(3, 3, 1, 1)], 3600);
  const after = processingDiscs([phase(4, 4, 0, 1)], 3600, before);
  assert.equal(after.voices, 0.9);
});

test("phases left out, or out of range, are read as one", () => {
  const at = (step: number | null, steps: number | null) =>
    processingDiscs(
      [
        {
          stage: "diarize",
          label: "diarize",
          state: "running",
          progress: {
            phase: "",
            done: 1,
            total: 2,
            unit: "windows",
            step,
            steps,
          },
        } as StageView,
      ],
      3600,
    ).voices;
  assert.equal(at(null, null), 0.5);
  // A step past the count is the last one.
  assert.equal(at(5, 3), (2 + 0.5) / 3);
});
