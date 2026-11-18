// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import { waveBars, WAVE } from "./liveWave.ts";

test("draws only the bars heard, the newest at the present", () => {
  const levels = new Map([
    [0, -60],
    [2, 0],
  ]);
  const bars = waveBars(levels, 5, []);
  assert.deepEqual(
    bars.map((b) => b.height),
    [0, 1],
  ); // bar 1 never heard: none
  assert.equal(bars[1].x, WAVE.nowX - (5 - 4) * WAVE.pxPerSecond + 1);
});

test("leaves out what went past the left edge", () => {
  assert.deepEqual(waveBars(new Map([[0, -20]]), 1000, []), []);
});

test("marks the bars around a key moment", () => {
  const levels = new Map([
    [5, -20],
    [20, -20],
  ]);
  const [near, far] = waveBars(levels, 50, [10]);
  assert.equal(near.marked, true);
  assert.equal(far.marked, false);
});
