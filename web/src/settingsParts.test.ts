// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import { buildShown, folderName, partOf } from "./settingsParts.ts";

test("the tab asked opens, else the first", () => {
  assert.equal(partOf("transcription"), "transcription");
  assert.equal(partOf(null), "seances");
  assert.equal(partOf("inconnu"), "seances");
  assert.equal(partOf("toString"), "seances");
});

test("the former tabs lead to the new ones", () => {
  assert.equal(partOf("general"), "seances");
  assert.equal(partOf("historique"), "seances");
  assert.equal(partOf("modeles"), "transcription");
  assert.equal(partOf("mac"), "transcription");
  assert.equal(partOf("donnees"), "avance");
  assert.equal(partOf("avance"), "avance");
});

test("a folder is said by its own name", () => {
  assert.equal(folderName("/Users/x/Google Drive/Comptes rendus"), "Comptes rendus");
  assert.equal(folderName("/Users/x/Comptes rendus/"), "Comptes rendus");
});

test("the code that runs is named only when it is not the version", () => {
  assert.equal(buildShown("0.35.0", "v0.35.0"), null);
  assert.equal(buildShown("0.34.0", "v0.34.0-36-gcac1f05"), "v0.34.0-36-gcac1f05");
  assert.equal(
    buildShown("0.34.0", "v0.34.0-36-gcac1f05-modifie"),
    "v0.34.0-36-gcac1f05-modifie",
  );
});
