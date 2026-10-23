import { test } from "node:test";
import assert from "node:assert/strict";
import type { ActionInfo, Generation, PendingGeneration } from "./api.ts";
import { summaryTabs, writable } from "./summaries.ts";

const gen = (id: number, ref: string): Generation => ({
  id,
  run_id: `r${id}`,
  action_ref: ref,
  action_name: ref.toUpperCase(),
  model: "m",
  created_at: "2026-10-23T10:00:00Z",
  strategy: "unique",
  calls: 1,
  duration_s: 1,
  output: "texte",
  stale: false,
  problem: null,
  restored: false,
  restorable: false,
});
const job = (
  job_id: number,
  ref: string,
  state = "running",
): PendingGeneration =>
  ({
    job_id,
    action_ref: ref,
    action_name: ref.toUpperCase(),
    model: "m",
    state,
    error: null,
  }) as PendingGeneration;
const action = (ref: string): ActionInfo =>
  ({
    ref,
    name: ref,
    description: "",
    prompt: "",
    provided: true,
    modified: false,
  }) as ActionInfo;

test("one tab per summary, its latest version, in the order first asked", () => {
  // Latest first, as the service sends them.
  const tabs = summaryTabs(
    [gen(5, "a"), gen(4, "b"), gen(2, "a"), gen(1, "b")],
    [],
    null,
  );
  assert.deepEqual(
    tabs.map((t) => t.ref),
    ["b", "a"],
  );
  assert.equal(tabs[1].latest?.id, 5);
});

test("the space's summary comes first, and one being written has its tab", () => {
  const tabs = summaryTabs(
    [gen(3, "a"), gen(2, "b")],
    [job(9, "c"), job(8, "a")],
    "b",
  );
  assert.deepEqual(
    tabs.map((t) => t.ref),
    ["b", "a", "c"],
  );
  assert.equal(tabs[1].pending?.job_id, 8);
  assert.equal(tabs[2].latest, null);
});

test("what can still be written: not a tab already, the space's own first", () => {
  const tabs = summaryTabs([gen(1, "a")], [], null);
  assert.deepEqual(
    writable([action("a"), action("b"), action("c")], tabs, "c").map(
      (a) => a.ref,
    ),
    ["c", "b"],
  );
});
