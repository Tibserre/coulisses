import assert from "node:assert/strict";
import { test } from "node:test";
import type { Project, Session, Space } from "./api.ts";
import { buildTree, parseRoute, sessionDot, sessionHref, sessionName } from "./library.ts";

const NOW = new Date("2026-10-07T12:00:00Z");

test("a search hit opens its session at the measured time", () => {
  assert.deepEqual(parseRoute("#/seance/abc?t=12.5"), { page: "session", id: "abc", at: 12.5, tab: null });
  assert.deepEqual(parseRoute("#/seance/abc?onglet=resume"), { page: "session", id: "abc", at: null, tab: "summary" });
  assert.deepEqual(parseRoute("#/seance/abc?t=nope"), { page: "session", id: "abc", at: null, tab: null });
  assert.equal(sessionHref("abc", 12.53), "#/seance/abc?t=12.5");
  assert.equal(sessionHref("abc", null, "summary"), "#/seance/abc?onglet=resume");
  assert.deepEqual(parseRoute("#/espaces/3"), { page: "space", id: 3 });
  assert.deepEqual(parseRoute("#/reglages"), { page: "settings", part: null });
  assert.deepEqual(parseRoute(""), { page: "home" });
});

test("a session without a title is named by its day", () => {
  const name = sessionName({ title: null, recorded_at: "2026-10-06T19:05:00Z" }, NOW);
  assert.match(name, /^Séance du 6 octobre, \d+ h 05$/); // the hour in the Mac's own time zone
  assert.equal(sessionName({ title: "Filage", recorded_at: "2026-10-06T19:00:00Z" }, NOW), "Filage");
});

test("the side column marks what is going on", () => {
  assert.equal(sessionDot({ job_state: null, duration_s: null }, "s1", "s1"), "recording");
  assert.equal(sessionDot({ job_state: "running", duration_s: 10 }, null, "s1"), "processing");
  assert.equal(sessionDot({ job_state: "failed", duration_s: 10 }, null, "s1"), "failed");
  assert.equal(sessionDot({ job_state: "done", duration_s: 10 }, null, "s1"), null);
});

const space = (id: number, archived = false): Space =>
  ({ id, name: `Espace ${id}`, voice_recognition: false, archived }) as Space;
const project = (id: number, space_id: number, name: string, archived = false): Project => ({
  id,
  space_id,
  name,
  archived,
});
const session = (id: string, space_id: number, project_id: number | null, day: string): Session =>
  ({ id, space_id, project_id, recorded_at: `2026-10-${day}T10:00:00Z`, title: null }) as Session;

test("the tree groups sessions by space and project, the most recent first", () => {
  const tree = buildTree(
    [space(1), space(2, true)],
    [project(10, 1, "Spectacle"), project(11, 1, "ateliers"), project(12, 1, "Ancien", true)],
    [
      session("a", 1, 10, "01"),
      session("b", 1, 10, "05"),
      session("c", 1, null, "03"),
      session("d", 1, 12, "02"),
      session("e", 2, null, "04"),
    ],
  );
  assert.equal(tree.length, 2); // an archived space keeps its sessions listed (apart)
  assert.deepEqual(tree[1].loose.map((s) => s.id), ["e"]);
  const [troupe] = tree;
  assert.deepEqual(troupe.projects.map((p) => p.project.name), ["ateliers", "Spectacle"]);
  assert.deepEqual(troupe.projects[1].sessions.map((s) => s.id), ["b", "a"]);
  assert.deepEqual(troupe.loose.map((s) => s.id), ["c"]);
  assert.deepEqual(troupe.archived[0].sessions.map((s) => s.id), ["d"]);
});

test("a group shows its latest sessions, and keeps in sight those that must be", async () => {
  const { visibleSessions } = await import("./library.ts");
  const ids = ["a", "b", "c", "d", "e", "f", "g"];
  assert.deepEqual(visibleSessions(ids, 5, () => false), ["a", "b", "c", "d", "e"]);
  assert.deepEqual(visibleSessions(ids, 5, (s) => s === "g"), ["a", "b", "c", "d", "e", "g"]);
});

test("the settings open on the tab the address asks for", () => {
  assert.deepEqual(parseRoute("#/reglages?onglet=modeles"), { page: "settings", part: "modeles" });
  assert.deepEqual(parseRoute("#/reglages"), { page: "settings", part: null });
});

test("the home page records where it was chosen, else where the latest session was", async () => {
  const { startSpace } = await import("./library.ts");
  const spaces = [
    { id: 1, archived: false },
    { id: 2, archived: false },
    { id: 3, archived: true },
  ];
  const latest = [{ space_id: 2 }, { space_id: 1 }];
  assert.equal(startSpace(spaces, latest, 1), 1);
  assert.equal(startSpace(spaces, latest, null), 2);
  assert.equal(startSpace(spaces, latest, 3), 2); // archived since: no session starts there
  assert.equal(startSpace(spaces, [], 9), 1);
  assert.equal(startSpace([], [], null), null);
});

test("a space's latest session, whatever the order", async () => {
  const { latestSession } = await import("./library.ts");
  const list = [
    { space_id: 1, recorded_at: "2026-09-30T18:00:00Z" },
    { space_id: 2, recorded_at: "2026-10-09T18:00:00Z" },
    { space_id: 1, recorded_at: "2026-10-07T18:00:00Z" },
  ];
  assert.equal(latestSession(1, list)?.recorded_at, "2026-10-07T18:00:00Z");
  assert.equal(latestSession(2, list)?.recorded_at, "2026-10-09T18:00:00Z");
  assert.equal(latestSession(3, list), null);
});
