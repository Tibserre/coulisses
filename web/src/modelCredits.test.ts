// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import type { CatalogModel } from "./api.ts";
import { modelCredits } from "./modelCredits.ts";

const model = (key: string, attribution?: string | null): CatalogModel => ({
  key,
  stage: "diarize",
  role: "qui parle",
  description: "",
  announced_bytes: 1,
  repo: "r",
  revision: "v",
  licence: "l",
  terms_url: null,
  engine: null,
  required_by: [],
  replaced_by: null,
  replacement_note: null,
  ...(attribution === undefined ? {} : { attribution }),
});

test("the credits: one per model that has one, each once, as the catalog writes it", () => {
  const catalog = [model("a", "Par A, sous CC BY 4.0."), model("b", null), model("c"), model("d", " Par A, sous CC BY 4.0. "), model("e", "Par E.")];
  assert.deepEqual(modelCredits(catalog), ["Par A, sous CC BY 4.0.", "Par E."]);
});

test("an older engine: nothing to credit", () => {
  assert.deepEqual(modelCredits([model("a"), model("b")]), []);
});
