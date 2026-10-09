// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import type { CatalogModel, ModelAction, ModelsView } from "./api.ts";
import { environmentState, gigabytes, modelRows, percent, readinessLine } from "./models.ts";

const model = (
  key: string,
  stage: CatalogModel["stage"] = "transcribe",
): CatalogModel => ({
  key,
  stage,
  role: "transcription",
  description: "",
  announced_bytes: 4_700_000_000,
  repo: "r",
  revision: "v",
  licence: "l",
  terms_url: null,
  engine: null,
  required_by: ["chaine-retenue"],
});

const view = (
  over: Partial<ModelsView["inventory"]> = {},
  missing: ModelsView["readiness"]["missing"] = [],
): ModelsView => ({
  catalog: { models: [model("asr"), model("voix", "diarize")] },
  inventory: {
    models_dir: "",
    envs_dir: "",
    models: [],
    partial_downloads: [],
    environments: [],
    total_bytes: 0,
    ...over,
  },
  readiness: {
    profile: "chaine-retenue",
    ready: missing.length === 0,
    missing,
  },
  actions: [],
});

const task = (
  name: string,
  state: ModelAction["state"],
  done = 0,
  total: number | null = null,
): ModelAction => ({
  kind: "model",
  name,
  state,
  done_bytes: done,
  total_bytes: total,
  error: state === "failed" ? "La source n'a pas pu être jointe." : null,
  code: null,
  detail: null,
  terms_url: null,
  started_at: "",
  finished_at: null,
});

test("sizes are said as the catalog says them, in decimal gigabytes", () => {
  assert.equal(gigabytes(4_700_000_000), "4,7 Go");
  assert.equal(gigabytes(30_000_000), "30 Mo");
});

test("each model is installed, damaged, half downloaded, missing, or downloading", () => {
  const rows = modelRows(
    view({
      models: [
        {
          key: "asr",
          state: "intact",
          in_catalog: true,
          repo: null,
          revision: null,
          outdated: true,
          size_bytes: 9,
          downloaded_at: null,
          problem: null,
        },
      ],
      partial_downloads: [{ key: "voix", size_bytes: 5 }],
    }),
    [],
  );
  assert.deepEqual(
    rows.map((r) => [r.purpose, r.state.kind, r.required]),
    [
      ["Transcription", "installed", true],
      ["Qui parle quand", "partial", true],
    ],
  );
  const running = modelRows(view(), [task("voix", "running", 1, 4)]);
  assert.equal(running[1]?.state.kind, "running");
  const failed = modelRows(view(), [task("asr", "failed")]);
  assert.equal(failed[0]?.state.kind, "missing");
  assert.match(failed[0]?.last?.error ?? "", /jointe/);
});

test("the share done is known only with a total", () => {
  assert.equal(percent(task("asr", "running", 1_000, 4_000)), 25);
  assert.equal(percent(task("env", "running", 1_000, null)), null);
});

test("what the chain lacks is said in one sentence", () => {
  assert.equal(readinessLine(view().readiness, view().inventory), null);
  const lacking = view({}, [
    {
      code: "model_missing",
      stage: "transcribe",
      model: "asr",
      environment: null,
      message: "",
    },
    {
      code: "environment_missing",
      stage: "diarize",
      model: null,
      environment: "diarizen",
      message: "",
    },
  ]);
  assert.equal(
    readinessLine(lacking.readiness, lacking.inventory),
    "Les séances ne peuvent pas être traitées : il manque le modèle « asr », l'environnement de calcul « diarizen ».",
  );
});

const there = (key: string, over: Partial<ModelsView["inventory"]["models"][number]> = {}) => ({
  key,
  state: "intact" as const,
  in_catalog: true,
  repo: null,
  revision: null,
  outdated: false,
  size_bytes: 9,
  downloaded_at: null,
  problem: null,
  ...over,
});

test("a folder Coulisses did not install is never said installed", () => {
  const rows = modelRows(view({ models: [there("asr", { state: "no_manifest", problem: "no manifest" })] }), []);
  assert.equal(rows[0]?.state.kind, "altered");
});

test("what takes space outside the catalog has its row, to be removed", () => {
  const rows = modelRows(
    view({
      models: [there("ancien", { in_catalog: false })],
      partial_downloads: [{ key: "abandonne", size_bytes: 3 }],
    }),
    [],
  );
  assert.deepEqual(rows.slice(2).map((r) => [r.key, r.purpose, r.state.kind, r.model]), [
    ["ancien", "Hors catalogue", "installed", null],
    ["abandonne", "Hors catalogue", "partial", null],
  ]);
});

test("an old environment is said old, not interrupted", () => {
  const env = { name: "diarizen", path: "", size_bytes: 1 };
  assert.match(environmentState({ ...env, current: false, installed: false }), /^Ancienne version/);
  assert.equal(environmentState({ ...env, current: true, installed: true }), "Installé");
  assert.equal(environmentState({ ...env, current: true, installed: false }), "Installation interrompue");
});
