// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import { outlineRows, type OutlineRow } from "./outline.ts";

const line = (key: string, at: number | null): OutlineRow => ({
  key,
  at,
  kind: "line",
  text: key,
});
const note = (key: string, at: number): OutlineRow => ({
  key,
  at,
  kind: "note",
  text: key,
});

test("what was marked slips in at its time, the text keeps its order", () => {
  const rows = outlineRows(
    [line("a", 1), line("b", 10), line("c", 20)],
    [note("n", 12), note("m", 2)],
  );
  assert.deepEqual(
    rows.map((r) => r.key),
    ["a", "m", "b", "n", "c"],
  );
});

test("a line without a measured time keeps its place in the text", () => {
  const rows = outlineRows(
    [line("a", 1), line("x", null), line("b", 10)],
    [note("n", 5)],
  );
  assert.deepEqual(
    rows.map((r) => r.key),
    ["a", "x", "n", "b"],
  );
});

test("what was marked after the last line comes last; without text, it is all there is", () => {
  assert.deepEqual(
    outlineRows([line("a", 1)], [note("n", 9)]).map((r) => r.key),
    ["a", "n"],
  );
  assert.deepEqual(
    outlineRows([], [note("n", 9), note("m", 3)]).map((r) => r.key),
    ["m", "n"],
  );
});
