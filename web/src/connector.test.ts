// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import type { ConnectorAccess, ConnectorSettings } from "./api.ts";
import {
  accessNames,
  accessSubject,
  connectorReach,
  launcherProblem,
  spaceReading,
} from "./connector.ts";

const entry = (over: Partial<ConnectorAccess>): ConnectorAccess => ({
  id: 1,
  at: "2026-10-29T14:02:11Z",
  tool: "lire_transcript",
  session_id: "20261012-201500-a1b2",
  session_title: "Répétition du 12 octobre",
  session_deleted: false,
  names_shared: false,
  ...over,
});

test("a read names its session by its title now, or says why it cannot", () => {
  assert.equal(accessSubject(entry({})), "« Répétition du 12 octobre »");
  assert.equal(
    accessSubject(entry({ session_title: null, session_deleted: true })),
    "une séance supprimée depuis",
  );
  assert.equal(
    accessSubject(entry({ session_title: null })),
    "une séance sans titre",
  );
  assert.equal(
    accessSubject(
      entry({ tool: "chercher", session_id: null, session_title: null }),
    ),
    null,
  );
});

const space = (access: boolean, names: boolean) => ({
  id: 1,
  name: "Troupe",
  archived: false,
  connector_access: access,
  connector_names: names,
});

test("a space says how the connector reads it", () => {
  assert.equal(spaceReading(space(false, true)), "fermé");
  assert.equal(spaceReading(space(true, false)), "accessible, noms masqués");
  assert.equal(spaceReading(space(true, true)), "accessible, avec les noms");
});

test("an open connector reads nothing while no space is open to it", () => {
  const settings = (
    open: boolean,
    spaces: ConnectorSettings["spaces"],
  ): ConnectorSettings => ({
    open,
    launcher: "/x/coulisses-mcp",
    launcher_ready: true,
    launcher_problem: null,
    claude_code_command: "claude mcp add coulisses -- /x/coulisses-mcp",
    mcpb: null,
    spaces,
  });
  assert.equal(connectorReach(settings(false, [space(true, false)])), "closed");
  assert.equal(
    connectorReach(settings(true, [space(false, false)])),
    "no-space",
  );
  assert.equal(connectorReach(settings(true, [])), "no-space");
  assert.equal(
    connectorReach(settings(true, [space(false, false), space(true, false)])),
    "reads",
  );
});

test("a read without a session says nothing of the names", () => {
  assert.equal(accessNames(entry({})), "noms masqués");
  assert.equal(accessNames(entry({ names_shared: true })), "avec les noms");
  assert.equal(accessNames(entry({ session_id: null, names_shared: null })), null);
});

const base: ConnectorSettings = {
  open: true,
  launcher: "/x/coulisses-mcp",
  launcher_ready: true,
  launcher_problem: null,
  claude_code_command: "claude mcp add coulisses -- /x/coulisses-mcp",
  mcpb: null,
  spaces: [],
};

test("a launcher not ready says why, in the service's words when it has them", () => {
  assert.equal(launcherProblem(base), null);
  assert.equal(
    launcherProblem({ ...base, launcher_ready: false, launcher_problem: "Le lanceur n'est pas exécutable." }),
    "Le lanceur n'est pas exécutable.",
  );
  assert.match(launcherProblem({ ...base, launcher_ready: false }) ?? "", /journal technique/);
});

test("an archived space left accessible is read", () => {
  assert.equal(
    connectorReach({ ...base, spaces: [{ ...space(true, false), archived: true }] }),
    "reads",
  );
});
