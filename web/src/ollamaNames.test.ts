// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import { ollamaLabels } from "./ollamaNames.ts";

const label = (name: string, others: string[] = []) =>
  ollamaLabels([name, ...others]).get(name);

test("a model is said by its family, its version and its size", () => {
  assert.equal(label("qwen3.8:27b-mlx"), "Qwen 3.8 – 27b");
  assert.equal(label("gemma4:e2b-mlx"), "Gemma 4 – e2b");
  assert.equal(label("ministral-3:8b"), "Ministral 3 – 8b");
  assert.equal(label("mistral-small3.2:24b"), "Mistral small 3.2 – 24b");
});

test("a tag that says no size is left out", () => {
  assert.equal(label("llama3.2:latest"), "Llama 3.2");
  assert.equal(label("phi4"), "Phi 4");
});

test("a model pulled from elsewhere is said by its own name", () => {
  assert.equal(label("hf.co/someone/qwen3:8b"), "Qwen 3 – 8b");
});

test("two models that would read the same keep the rest of their tag", () => {
  const labels = ollamaLabels([
    "qwen3.5:9b-nvfp4",
    "qwen3.5:9b-mlx",
    "qwen3.5:4b-mlx",
  ]);
  assert.equal(labels.get("qwen3.5:9b-nvfp4"), "Qwen 3.5 – 9b nvfp4");
  assert.equal(labels.get("qwen3.5:9b-mlx"), "Qwen 3.5 – 9b mlx");
  assert.equal(labels.get("qwen3.5:4b-mlx"), "Qwen 3.5 – 4b");
});

test("two that still read the same are said by their exact name", () => {
  const labels = ollamaLabels(["qwen3:8b", "someone/qwen3:8b"]);
  assert.equal(labels.get("qwen3:8b"), "qwen3:8b");
  assert.equal(labels.get("someone/qwen3:8b"), "someone/qwen3:8b");
});

test("the rest of the tag is not enough when two still read the same", () => {
  const labels = ollamaLabels(["qwen3:8b-q4", "hf.co/x/qwen3:8b-q4", "qwen3:8b-q8"]);
  assert.equal(labels.get("qwen3:8b-q4"), "qwen3:8b-q4");
  assert.equal(labels.get("hf.co/x/qwen3:8b-q4"), "hf.co/x/qwen3:8b-q4");
  assert.equal(labels.get("qwen3:8b-q8"), "Qwen 3 – 8b q8");
});
