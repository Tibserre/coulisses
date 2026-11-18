// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import { liveHeights, waveBars, WAVE } from "./liveWave.ts";

const { secondsPerBar: spb, pxPerSecond: px, nowX } = WAVE;

test("draws only the bars heard, the newest at the present", () => {
  const levels = new Map([
    [0, -60],
    [2, 0],
  ]);
  const shown = 3 * spb;
  const bars = waveBars(levels, shown, []);
  assert.deepEqual(
    bars.map((b) => b.height),
    [0, 1],
  ); // bar 1 never heard: none
  assert.equal(bars[1].x, nowX - (shown - 2 * spb) * px + 1);
});

test("leaves out what went past the left edge", () => {
  assert.deepEqual(waveBars(new Map([[0, -20]]), nowX / px + 10, []), []);
});

test("marks the bars around a key moment", () => {
  const near = Math.round(10 / spb);
  const far = Math.round(30 / spb);
  const levels = new Map([
    [near, -20],
    [far, -20],
  ]);
  const [a, b] = waveBars(levels, 35, [10]);
  assert.equal(a.marked, true);
  assert.equal(b.marked, false);
});

test("the live bars are the last four levels received, the lowest before any", () => {
  assert.deepEqual(liveHeights([]), [3, 3, 3, 3]);
  const h = liveHeights([-60, -60, -60, 0, -30]);
  assert.equal(h.length, 4);
  assert.equal(h[3], WAVE.maxHalf); // -30 dB: half the height
  assert.equal(h[2], 2 * WAVE.maxHalf); // 0 dB: full
});
