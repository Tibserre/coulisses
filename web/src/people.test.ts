import assert from "node:assert/strict";
import { test } from "node:test";
import { freeName } from "./people.ts";

test("a taken « Paul » gives « Paul 2 »", () => {
  assert.equal(freeName("Paul", [{ name: "Paul" }]), "Paul 2");
});

test("the numbers already borne are skipped, whatever the accents and case", () => {
  assert.equal(freeName("Élise", [{ name: "Élise" }, { name: "elise 2" }]), "Élise 3");
});

test("a taken « Paul 2 » gives « Paul 3 », not « Paul 2 2 »", () => {
  assert.equal(freeName("Paul 2", [{ name: "Paul" }, { name: "Paul 2" }]), "Paul 3");
});
