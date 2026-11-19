// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import { nextHeardVersion } from "./heardVersion.ts";

test("the first version is taken, nothing to reload", () => {
  assert.deepEqual(nextHeardVersion(null, "a"), { version: "a", reload: false });
});

test("a null keeps what is known", () => {
  assert.deepEqual(nextHeardVersion("a", null), { version: "a", reload: false });
  assert.deepEqual(nextHeardVersion(null, null), { version: null, reload: false });
});

test("the same version changes nothing, a new one reloads", () => {
  assert.deepEqual(nextHeardVersion("a", "a"), { version: "a", reload: false });
  assert.deepEqual(nextHeardVersion("a", "b"), { version: "b", reload: true });
});
