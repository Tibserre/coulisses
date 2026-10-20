// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import { appUpdates } from "./appBridge.ts";

const sent: unknown[] = [];
const app = (updates: object | undefined) => ({
  coulissesApp: updates === undefined ? undefined : { updates },
  webkit: {
    messageHandlers: {
      coulisses: { postMessage: (m: unknown) => sent.push(m) },
    },
  },
});

test("no updates where the app gives none (development app, browser)", () => {
  assert.equal(appUpdates({}), null);
  assert.equal(appUpdates(app(undefined)), null);
  assert.equal(
    appUpdates({ coulissesApp: { updates: { automatic: true } } }),
    null,
  );
});

test("the published app's state is read, never guessed", () => {
  const updates = appUpdates(
    app({ automatic: true, lastCheck: "2026-10-13T08:00:00Z" }),
  );
  assert.deepEqual(updates?.state, {
    automatic: true,
    lastCheck: "2026-10-13T08:00:00Z",
    ready: false,
  });
  assert.equal(appUpdates(app({ automatic: true, lastCheck: null, ready: true }))?.state.ready, true);
  // Anything else than a plain yes is a no: the checks stay off.
  assert.deepEqual(appUpdates(app({ automatic: "oui", lastCheck: 3, ready: "oui" }))?.state, {
    automatic: false,
    lastCheck: null,
    ready: false,
  });
});

test("the page asks the app; it decides nothing itself", () => {
  sent.length = 0;
  const updates = appUpdates(app({ automatic: false, lastCheck: null }));
  updates?.setAutomatic(true);
  updates?.checkNow();
  assert.deepEqual(sent, [
    { action: "mises-a-jour-automatiques", value: true },
    { action: "rechercher-mises-a-jour" },
  ]);
});
