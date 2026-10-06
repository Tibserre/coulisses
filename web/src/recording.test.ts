// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import type { Marker } from "./api.ts";
import { currentMode, liveSegments } from "./liveStrip.ts";
import { meterValue } from "./meter.ts";

test("the meter runs from -60 dBFS (empty) to 0 dBFS (full), clamped", () => {
  assert.equal(meterValue(-120), 0);
  assert.equal(meterValue(-60), 0);
  assert.equal(meterValue(-30), 50);
  assert.equal(meterValue(0), 100);
  assert.equal(meterValue(3), 100);
});

const m = (id: number, kind: Marker["kind"], at_s: number): Marker => ({ id, kind, at_s });

test("no marker yet: no mode, one stretch left to the detection", () => {
  assert.equal(currentMode([]), null);
  assert.deepEqual(liveSegments([], 30), [{ kind: "none", start: 0, end: 30 }]);
});

test("play then discussion markers make the strip; key moments cut nothing", () => {
  const marks = [m(1, "scene", 10), m(2, "key_moment", 15), m(3, "discussion", 40)];
  assert.deepEqual(currentMode(marks), { mode: "discussion", since: 40 });
  assert.deepEqual(liveSegments(marks, 60), [
    { kind: "none", start: 0, end: 10 },
    { kind: "scene", start: 10, end: 40 },
    { kind: "discussion", start: 40, end: 60 },
  ]);
});

test("a marker at the very start leaves no empty stretch", () => {
  assert.deepEqual(liveSegments([m(1, "scene", 0)], 5), [{ kind: "scene", start: 0, end: 5 }]);
});
