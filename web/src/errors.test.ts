import assert from "node:assert/strict";
import { test } from "node:test";
import { friendlyError } from "./errors.ts";

test("no error, no message", () => {
  assert.equal(friendlyError(null), null);
});

test("the engine's own error types are said in plain French", () => {
  assert.match(friendlyError("Interrupted : caller stopped")!, /^Interrompue/);
  assert.equal(friendlyError("Cancelled : cancel()"), "Annulée.");
  assert.match(friendlyError("ChildCrash : child exited with code -9")!, /mémoire/);
  assert.match(friendlyError("ApplicationStoppingError : align non lancée")!, /s'arrêtait/);
  assert.match(friendlyError("Exécution x : le moteur refuse de la clore (vivant)")!, /encore tourner/);
  assert.equal(friendlyError("Interrompue avant d'avoir démarré"), "Interrompue avant d'avoir démarré.");
});

test("an unknown error is still shown, never swallowed (P8)", () => {
  assert.match(friendlyError("RuntimeError : DiariZen failed (exit code 1)")!, /a échoué/);
});
