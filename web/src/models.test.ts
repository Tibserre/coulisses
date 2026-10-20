// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import type { CatalogModel, ModelAction, ModelsView } from "./api.ts";
import { environmentState, gigabytes, modelRows, percent, readinessLine, removableEnvironment } from "./models.ts";

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
  replaced_by: null,
  replacement_note: null,
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
    uv_stores: [],
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
          required: true,
          replaced_by: null,
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
      label: null,
      message: "",
    },
    {
      code: "environment_missing",
      stage: "diarize",
      model: null,
      environment: "diarizen",
      label: "Diarisation DiariZen : qui parle quand",
      message: "",
    },
    {
      code: "environment_missing",
      stage: "align",
      model: null,
      environment: "diarizen",
      label: "Diarisation DiariZen : qui parle quand",
      message: "",
    },
  ]);
  assert.equal(
    readinessLine(lacking.readiness, lacking.inventory),
    "Les séances ne peuvent pas être traitées : il manque le modèle « asr », l'environnement de calcul « Diarisation DiariZen : qui parle quand ».",
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
  required: false,
  replaced_by: null,
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
  const env = { name: "diarizen", path: "", size_bytes: 1, interpreter: null, interpreter_outside: false, label: "", stages: [] };
  assert.match(environmentState({ ...env, current: false, installed: false }), /^Ancienne version/);
  assert.equal(environmentState({ ...env, current: true, installed: true }), "Installé");
  assert.equal(environmentState({ ...env, current: true, installed: false }), "Installation interrompue");
});

test("only an environment the processing does not use can be removed, never while it installs", () => {
  const env = { name: "diarizen", path: "", size_bytes: 1, interpreter: null, interpreter_outside: false, label: "", stages: [] };
  const old = { ...env, current: false, installed: true };
  const interrupted = { ...env, current: true, installed: false };
  const used = { ...env, current: true, installed: true };
  assert.equal(removableEnvironment(old, []), true);
  assert.equal(removableEnvironment(interrupted, []), true);
  assert.equal(removableEnvironment(used, []), false);
  const installing = { ...task("diarizen", "running"), kind: "environment" as const };
  assert.equal(removableEnvironment(interrupted, [installing]), false);
});

test("uv's folders have their row, the cache said apart from the total; an empty one is left out", async () => {
  const { uvStoreRows } = await import("./models.ts");
  const rows = uvStoreRows(
    view({
      uv_stores: [
        { kind: "python", path: "/E/uv/python", size_bytes: 70_000_000 },
        { kind: "cache", path: "/E/uv/cache", size_bytes: 900_000_000 },
        { kind: "cache", path: "/vide", size_bytes: 0 },
      ],
    }).inventory,
  );
  assert.deepEqual(
    rows.map((r) => r.title),
    ["Python des environnements", "Cache des installations"],
  );
  assert.match(rows[1].note, /Hors du total/);
});

test("an environment whose Python lives outside Coulisses says so", async () => {
  const { interpreterNote } = await import("./models.ts");
  const env = {
    name: "diarizen",
    path: "/E/diarizen-abc",
    current: true,
    installed: true,
    size_bytes: 1,
    interpreter: "/Users/x/.local/share/uv/python/cpython-3.10/bin/python3.10",
    interpreter_outside: true,
    label: "Diarisation DiariZen : qui parle quand",
    stages: ["diarize" as const],
  };
  assert.match(interpreterNote(env)!, /hors de Coulisses/);
  assert.equal(interpreterNote({ ...env, interpreter_outside: false }), null);
  assert.equal(interpreterNote({ ...env, installed: false }), null); // an interrupted install says that first
});

test("an environment several stages need is listed once, with its role", async () => {
  const { missingEnvironments } = await import("./models.ts");
  const piece = (stage: "transcribe" | "align", label: string | null) => ({
    code: "environment_missing" as const,
    stage,
    model: null,
    environment: "torch",
    label,
    message: "",
  });
  const lacking = view({}, [piece("transcribe", "Calcul des modèles"), piece("align", null)]);
  assert.deepEqual(missingEnvironments(lacking.readiness, lacking.inventory), [
    ["torch", "Calcul des modèles"],
  ]);
  const unnamed = view({}, [piece("align", null)]);
  assert.deepEqual(missingEnvironments(unnamed.readiness, unnamed.inventory), [["torch", ""]]);
});

test("a replaced model says by what, with the engine's note", () => {
  const catalog = { models: [{ ...model("ancien"), required_by: [], replaced_by: "asr", replacement_note: "Il ne sert plus." }, model("asr")] };
  const rows = modelRows({ ...view({ models: [there("ancien", { replaced_by: "asr" }), there("asr", { required: true })] }), catalog }, []);
  assert.deepEqual(rows.map((r) => r.state.kind === "installed" && r.state.replacement), [
    { by: "asr", note: "Il ne sert plus." },
    null,
  ]);
});

test("outside developer mode, what the processing uses and is sound is one line per step", async () => {
  const { quietRows } = await import("./models.ts");
  const installed = (key: string, size: number) => ({
    key,
    state: "intact" as const,
    in_catalog: true,
    repo: null,
    revision: null,
    outdated: false,
    size_bytes: size,
    downloaded_at: null,
    problem: null,
    required: true,
    replaced_by: null,
  });
  const env = { path: "", interpreter: null, interpreter_outside: false, label: "", stages: [] };
  const v: ModelsView = {
    ...view({
      models: [installed("asr", 2_500_000_000), installed("voix", 30_000_000), installed("voix2", 270_000_000)],
      environments: [
        { ...env, name: "torch", current: true, installed: true, size_bytes: 1_300_000_000 },
        { ...env, name: "diarizen-old", current: false, installed: true, size_bytes: 800_000_000 },
      ],
      uv_stores: [
        { kind: "python", path: "/p", size_bytes: 65_000_000 },
        { kind: "cache", path: "/c", size_bytes: 1_200_000_000 },
      ],
    }),
    catalog: {
      models: [
        model("asr"),
        { ...model("asr-grand"), required_by: [] },
        model("voix", "diarize"),
        model("voix2", "diarize"),
      ],
    },
  };
  const quiet = quietRows(modelRows(v, []), v.inventory);
  assert.deepEqual(quiet.steps, [
    { purpose: "Transcription", size: 2_500_000_000 },
    { purpose: "Qui parle quand", size: 300_000_000 },
  ]);
  // The one the processing does not use is not shown while not on the disk; the old
  // environment keeps its row, to be removed.
  assert.deepEqual(quiet.apart.map((r) => r.key), []);
  assert.equal(quiet.old.size, 0);
  assert.deepEqual(quiet.apartEnvironments.map((e) => e.name), ["diarizen-old"]);
  // The tools: the environments in use and their Python, the cache apart from the total.
  assert.equal(quiet.tools, 1_365_000_000);
  assert.equal(quiet.cache, 1_200_000_000);
});

test("outside developer mode, what the chain lacks is said by what it is for", () => {
  const line = readinessLine(
    view({}, [
      { stage: "transcribe", code: "model_missing", model: "qwen-xyz", environment: null, label: null, message: "" },
      { stage: "diarize", code: "environment_missing", model: null, environment: "diarizen", label: "DiariZen", message: "" },
    ]).readiness,
    view().inventory,
    (key) => (key === "qwen-xyz" ? "Transcription" : undefined),
  );
  assert.equal(
    line,
    "Les séances ne peuvent pas être traitées : il manque le modèle « Transcription », les outils de calcul.",
  );
});

test("a step folds only when every model it needs is sound", async () => {
  const { quietRows } = await import("./models.ts");
  const v: ModelsView = {
    ...view({
      models: [
        {
          key: "voix",
          state: "intact",
          in_catalog: true,
          repo: null,
          revision: null,
          outdated: false,
          size_bytes: 30,
          downloaded_at: null,
          problem: null,
          required: true,
          replaced_by: null,
        },
      ],
    }),
    catalog: { models: [model("voix", "diarize"), model("voix2", "diarize")] },
  };
  const quiet = quietRows(modelRows(v, []), v.inventory);
  assert.deepEqual(quiet.steps, []);
  assert.deepEqual(quiet.apart.map((r) => r.key), ["voix", "voix2"]);
});

test("outside developer mode, a model it cannot place is never said by its key", () => {
  const line = readinessLine(
    view({}, [{ stage: "transcribe", code: "model_missing", model: "qwen-xyz", environment: null, label: null, message: "" }]).readiness,
    view().inventory,
    () => undefined,
  );
  assert.equal(line, "Les séances ne peuvent pas être traitées : il manque un modèle du traitement.");
});

test("an old model on the disk is said with its step; the new one missing, both together", async () => {
  const { quietRows } = await import("./models.ts");
  const installed = (key: string, size: number, required: boolean, replaced_by: string | null = null) => ({
    key,
    state: "intact" as const,
    in_catalog: true,
    repo: null,
    revision: null,
    outdated: false,
    size_bytes: size,
    downloaded_at: null,
    problem: null,
    required,
    replaced_by,
  });
  const catalog = {
    models: [{ ...model("ancien"), required_by: [], replaced_by: "asr", replacement_note: null }, model("asr")],
  };
  // The new one there: one line, the old one with it.
  const both: ModelsView = {
    ...view({ models: [installed("ancien", 4_700_000_000, false, "asr"), installed("asr", 2_500_000_000, true)] }),
    catalog,
  };
  const quiet = quietRows(modelRows(both, []), both.inventory);
  assert.deepEqual(quiet.steps, [{ purpose: "Transcription", size: 2_500_000_000 }]);
  assert.deepEqual(quiet.old.get("Transcription")?.map((r) => r.key), ["ancien"]);
  assert.deepEqual(quiet.apart, []);
  // The new one missing: its row, with the old one known to replace.
  const lacking: ModelsView = { ...view({ models: [installed("ancien", 4_700_000_000, false, "asr")] }), catalog };
  const q2 = quietRows(modelRows(lacking, []), lacking.inventory);
  assert.deepEqual(q2.steps, []);
  assert.deepEqual(q2.apart.map((r) => r.key), ["asr"]);
  assert.deepEqual(q2.old.get("Transcription")?.map((r) => r.key), ["ancien"]);
});

test("an optional model on the disk, never replaced, keeps its row: it is not an old one", async () => {
  const { quietRows } = await import("./models.ts");
  const installed = (key: string, required: boolean) => ({
    key,
    state: "intact" as const,
    in_catalog: true,
    repo: null,
    revision: null,
    outdated: false,
    size_bytes: 1,
    downloaded_at: null,
    problem: null,
    required,
    replaced_by: null,
  });
  const v: ModelsView = {
    ...view({ models: [installed("asr", true), installed("asr-grand", false)] }),
    catalog: { models: [model("asr"), { ...model("asr-grand"), required_by: [] }] },
  };
  const quiet = quietRows(modelRows(v, []), v.inventory);
  assert.equal(quiet.old.size, 0);
  assert.deepEqual(quiet.apart.map((r) => r.key), ["asr-grand"]);
});
