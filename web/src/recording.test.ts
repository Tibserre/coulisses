// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import type { Marker } from "./api.ts";
import { AHEAD_MAX_S, currentMode, liveSegments, shownElapsed } from "./liveStrip.ts";
import { meterValue } from "./meter.ts";
import { PEAK_HOLD_S, step } from "./smoothLevel.ts";

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

test("the needle rises fast, falls slowly, and the peak holds before falling", () => {
  let needle = { level: 0, peak: 0, held: 0 };
  for (let i = 0; i < 6; i++) needle = step(needle, 80, 90, 1 / 60); // 0.1 s
  assert.ok(needle.level > 60, `rose to ${needle.level}`); // most of the way in 0.1 s
  assert.equal(needle.peak, 90);
  const top = needle.level;
  for (let i = 0; i < 6; i++) needle = step(needle, 0, 0, 1 / 60);
  assert.ok(needle.level > top * 0.6, `fell only to ${needle.level}`); // gently
  assert.equal(needle.peak, 90); // still held
  for (let i = 0; i < Math.ceil((PEAK_HOLD_S + 1) * 60); i++) needle = step(needle, 0, 0, 1 / 60);
  assert.ok(needle.peak < 50 && needle.level < 5);
});

test("between two times given, the strip carries on a little, never back, and stops when still", () => {
  assert.equal(shownElapsed(10, 0.1, 10, false), 10.1);
  assert.equal(shownElapsed(10, 2, 10, false), 10 + AHEAD_MAX_S); // capped
  // A time given slightly behind what was shown: the strip waits instead of going back.
  assert.equal(shownElapsed(10.05, 0, 10.2, false), 10.2);
  assert.equal(shownElapsed(10, 0.5, 10.2, true), 10); // paused: exactly the time measured
});
