// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import { meterValue } from "./meter.ts";

test("the meter runs from -60 dBFS (empty) to 0 dBFS (full), clamped", () => {
  assert.equal(meterValue(-120), 0);
  assert.equal(meterValue(-60), 0);
  assert.equal(meterValue(-30), 50);
  assert.equal(meterValue(0), 100);
  assert.equal(meterValue(3), 100);
});
