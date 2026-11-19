// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import { recordingKey } from "./recordingKeys.ts";

const free = { inField: false, onButton: false };
const paused = { held: true, stopping: false };
const stopping = { held: true, stopping: true };
const recording = { held: false, stopping: false };

test("a key typed in a field is the field's, even paused or stopping", () => {
  const field = { inField: true, onButton: false };
  assert.equal(recordingKey(" ", field, paused), null);
  assert.equal(recordingKey("escape", field, stopping), null);
});

test("held, Space takes it back, Escape only while it stops", () => {
  assert.equal(recordingKey(" ", free, paused), "toggle");
  assert.equal(recordingKey("escape", free, paused), null);
  assert.equal(recordingKey("escape", free, stopping), "toggle");
  assert.equal(recordingKey("m", free, paused), null);
});

test("held, Space on a button reached by Tab presses that button", () => {
  assert.equal(recordingKey(" ", { inField: false, onButton: true }, stopping), null);
});

test("recording, the shortcuts", () => {
  assert.equal(recordingKey(" ", free, recording), "toggle");
  assert.equal(recordingKey("m", free, recording), "moment");
  assert.equal(recordingKey("n", free, recording), "annotate");
});

test("without « Jeu et personnages », J and D do nothing", () => {
  assert.equal(recordingKey("j", free, recording, false), null);
  assert.equal(recordingKey("d", free, recording, false), null);
  assert.equal(recordingKey("m", free, recording, false), "moment");
  assert.equal(recordingKey("j", free, recording), "scene");
});
