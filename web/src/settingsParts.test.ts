// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import { folderName, partOf } from "./settingsParts.ts";

test("the tab asked opens, else the first", () => {
  assert.equal(partOf("historique"), "historique");
  assert.equal(partOf(null), "seances");
  assert.equal(partOf("inconnu"), "seances");
  assert.equal(partOf("toString"), "seances");
});

test("the former tabs lead to the new ones", () => {
  assert.equal(partOf("general"), "seances");
  assert.equal(partOf("modeles"), "mac");
  assert.equal(partOf("donnees"), "mac");
  assert.equal(partOf("avance"), "mac");
});

test("a folder is said by its own name", () => {
  assert.equal(folderName("/Users/x/Google Drive/Comptes rendus"), "Comptes rendus");
  assert.equal(folderName("/Users/x/Comptes rendus/"), "Comptes rendus");
});
