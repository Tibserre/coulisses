// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import type { InstalledModel, ModelsInfo, WritingAdvice } from "./api.ts";
import { adviceStep, memoryUnknown, shortMemory } from "./writingAdvice.ts";

const model = (name: string): InstalledModel => ({
  name,
  size_bytes: 1,
  digest: "d",
  family: null,
  parameter_size: null,
});

const info = (
  over: Partial<ModelsInfo>,
  advice: Partial<WritingAdvice> = {},
): ModelsInfo => ({
  reachable: true,
  error: null,
  default: "m",
  writings: { titre: "m", chapitres: "m", resume: "m" },
  models: [],
  advice: {
    memory_gb: 64,
    model: null,
    installed: false,
    minimum_gb: 16,
    ...advice,
  },
  ...over,
});

test("without Ollama, the first step is to install it", () => {
  assert.deepEqual(adviceStep(info({ reachable: false })), {
    kind: "install-ollama",
  });
});

test("the model advised for this Mac: to pull, or ready", () => {
  assert.deepEqual(adviceStep(info({}, { model: "petit:8b" })), {
    kind: "pull",
    model: "petit:8b",
    command: "ollama pull petit:8b",
  });
  assert.deepEqual(
    adviceStep(info({}, { model: "petit:8b", installed: true })),
    {
      kind: "ready",
      model: "petit:8b",
    },
  );
});

test("none advised yet: pick one if none is installed, else nothing to say", () => {
  assert.deepEqual(adviceStep(info({})), { kind: "choose" });
  assert.deepEqual(adviceStep(info({ models: [model("autre:7b")] })), {
    kind: "none",
  });
});

test("a Mac under the memory writing needs is told so", () => {
  assert.equal(shortMemory(info({}, { memory_gb: 8 })), 8);
  assert.equal(shortMemory(info({}, { memory_gb: 16 })), null);
  assert.equal(shortMemory(info({}, { memory_gb: null })), null);
});

test("a memory that cannot be read is said so, not guessed", () => {
  assert.equal(memoryUnknown(info({}, { memory_gb: null })), true);
  assert.equal(memoryUnknown(info({}, { memory_gb: 64 })), false);
});
