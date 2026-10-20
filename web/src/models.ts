import type { CatalogModel, EnvironmentInfo, Inventory, ModelAction, ModelsView, Readiness, UvStore } from "./api.ts";

/** What each stage is for, said to the user. */
const STAGE_WORDS: Partial<Record<CatalogModel["stage"], string>> = {
  transcribe: "Transcription",
  align: "Alignement des mots",
  diarize: "Qui parle quand",
};

/** Sizes as the catalog gives them: in decimal gigabytes (4,7 Go). */
export function gigabytes(bytes: number): string {
  if (bytes < 1e9) return `${Math.max(1, Math.round(bytes / 1e6))} Mo`;
  return `${(bytes / 1e9).toFixed(1).replace(".", ",")} Go`;
}

export type ModelState =
  | { kind: "running"; action: ModelAction }
  /** `replacement`: no longer needed, another model does its job (engine v1.10.0); the
   *  engine's note says why, in French. */
  | { kind: "installed"; size: number; outdated: boolean; replacement: { by: string; note: string | null } | null }
  /** Damaged, or a folder Coulisses did not install: to remove, then download again. */
  | { kind: "altered"; size: number; problem: string | null }
  | { kind: "partial"; done: number }
  | { kind: "missing" };

export interface ModelRow {
  key: string;
  /** Null for what is on the disk but not in the catalog (an older engine's, a stray folder). */
  model: CatalogModel | null;
  /** What it is for, in French. */
  purpose: string;
  /** Needed by the chain that processes the sessions. */
  required: boolean;
  state: ModelState;
  /** The last download, finished or stopped, with what it said. */
  last: ModelAction | null;
}

/** What a model of the catalog is for, said to the user. */
export function purposeOf(model: CatalogModel): string {
  return STAGE_WORDS[model.stage] ?? model.role;
}

function stateOf(
  key: string,
  inventory: Inventory,
  action: ModelAction | null,
  model: CatalogModel | null,
): ModelState {
  const there = inventory.models.find((m) => m.key === key);
  const partial = inventory.partial_downloads.find((p) => p.key === key);
  if (action?.state === "running") return { kind: "running", action };
  if (there && there.state !== "intact") return { kind: "altered", size: there.size_bytes, problem: there.problem };
  if (there)
    return {
      kind: "installed",
      size: there.size_bytes,
      outdated: there.outdated,
      replacement: there.replaced_by ? { by: there.replaced_by, note: model?.replacement_note ?? null } : null,
    };
  if (partial) return { kind: "partial", done: partial.size_bytes };
  return { kind: "missing" };
}

/** One row per model of the catalog, then one per thing on the disk outside it: from what
 *  is on the disk and what runs. Nothing taking space is left unseen. */
export function modelRows(view: ModelsView, actions: ModelAction[]): ModelRow[] {
  const { inventory, readiness } = view;
  const actionOf = (key: string) => actions.find((a) => a.kind === "model" && a.name === key) ?? null;
  const known = new Set(view.catalog.models.map((m) => m.key));
  const rows: ModelRow[] = view.catalog.models.map((model) => {
    const action = actionOf(model.key);
    return {
      key: model.key,
      model,
      purpose: purposeOf(model),
      required: model.required_by.includes(readiness.profile),
      state: stateOf(model.key, inventory, action, model),
      last: action && action.state !== "running" ? action : null,
    };
  });
  const strays = [
    ...inventory.models.map((m) => m.key),
    ...inventory.partial_downloads.map((p) => p.key),
  ].filter((key, i, all) => !known.has(key) && all.indexOf(key) === i);
  for (const key of strays) {
    const action = actionOf(key);
    rows.push({
      key,
      model: null,
      purpose: "Hors catalogue",
      required: false,
      state: stateOf(key, inventory, action, null),
      last: action && action.state !== "running" ? action : null,
    });
  }
  return rows;
}

/** An environment, said to the user. */
export function environmentState(env: EnvironmentInfo): string {
  if (!env.current) return "Ancienne version : ne fait que prendre de la place";
  return env.installed ? "Installé" : "Installation interrompue";
}

/** Where an environment's Python is, when that is worth saying: outside Coulisses (an
 *  install from before engine v1.7.0), it works as long as that Python stays in place. */
export function interpreterNote(env: EnvironmentInfo): string | null {
  return env.installed && env.interpreter_outside
    ? "Son Python est installé hors de Coulisses : il fonctionne tant que ce Python reste en place."
    : null;
}

/** uv's folders for the environments, as the list says them; an empty one is not shown. */
export function uvStoreRows(inventory: Inventory): { key: string; title: string; note: string; store: UvStore }[] {
  return inventory.uv_stores
    .filter((store) => store.size_bytes > 0)
    .map((store) =>
      store.kind === "python"
        ? { key: store.path, title: "Python des environnements", note: "Utilisé par les environnements de calcul", store }
        : {
            key: store.path,
            title: "Cache des installations",
            note: "Hors du total : ses fichiers sont partagés avec les environnements",
            store,
          },
    );
}

/** An environment that can be removed: one the processing does not use (an older one, or an
 *  interrupted install), and not being installed right now. */
export function removableEnvironment(env: EnvironmentInfo, actions: ModelAction[]): boolean {
  const installing = actions.some((a) => a.kind === "environment" && a.name === env.name && a.state === "running");
  return !installing && (!env.current || !env.installed);
}

/** The share done, 0 to 100; null while the total is unknown. */
export function percent(action: ModelAction): number | null {
  if (!action.total_bytes) return null;
  return Math.min(100, Math.round((action.done_bytes / action.total_bytes) * 100));
}

/** What the chain lacks, said in a sentence; null when all is there. Outside developer mode
 *  (`purposeOfKey` given, ADR 0051), a model is said by what it is for and an environment as
 *  the calculation tools, never by their names. */
export function readinessLine(
  readiness: Readiness,
  inventory: Inventory,
  purposeOfKey?: (key: string) => string | undefined,
): string | null {
  if (readiness.ready) return null;
  const parts = readiness.missing.map((piece) => {
    if (piece.environment)
      return purposeOfKey
        ? "les outils de calcul"
        : `l'environnement de calcul « ${piece.label || piece.environment} »`;
    const there = inventory.models.find((m) => m.key === piece.model);
    const purpose = piece.model ? purposeOfKey?.(piece.model) : undefined;
    // Outside developer mode, never the key: a model it cannot place is « un modèle ».
    const said = purposeOfKey
      ? purpose
        ? `le modèle « ${purpose} »`
        : "un modèle du traitement"
      : `le modèle « ${piece.model} »`;
    return piece.code === "model_altered" || (there && there.state !== "intact")
      ? `${said} (abîmé)`
      : said;
  });
  // An environment several stages need is said once.
  return `Les séances ne peuvent pas être traitées : il manque ${[...new Set(parts)].join(", ")}.`;
}

/** The environments the chain lacks (not installed), once each however many stages need
 *  them: [name, its role as the engine says it, or "" when it does not]. */
export function missingEnvironments(
  readiness: Readiness,
  inventory: Inventory,
): [string, string][] {
  const found = new Map<string, string>();
  for (const piece of readiness.missing) {
    const name = piece.environment;
    if (!name || inventory.environments.some((e) => e.name === name && e.installed)) continue;
    found.set(name, found.get(name) || piece.label || "");
  }
  return [...found];
}

/** A step whose models are all there and sound: said in one line, outside developer mode. */
export interface StepLine {
  purpose: string;
  size: number;
}

/** The engine's pieces as the page says them outside developer mode (ADR 0051): what the
 *  processing uses and is sound folds into one line per step, then one for the calculation
 *  tools (the environments and their Python); anything else keeps its own row, with its
 *  action: missing, downloading, interrupted, damaged, replaced, optional, outside the
 *  catalog, an older or interrupted environment; uv's cache has a quiet line of its own,
 *  outside the total. Nothing taking space is left unseen. Where an environment's Python
 *  lives is said in developer mode. */
export function quietRows(
  rows: ModelRow[],
  inventory: Inventory,
): {
  steps: StepLine[];
  tools: number | null;
  cache: number | null;
  apart: ModelRow[];
  apartEnvironments: EnvironmentInfo[];
} {
  const steps: StepLine[] = [];
  const apart: ModelRow[] = [];
  const sound = (row: ModelRow) =>
    row.required &&
    row.state.kind === "installed" &&
    row.state.replacement === null &&
    row.last === null;
  // A step folds only when every model it needs is sound: never two lines of one name.
  const unsoundStep = new Set(rows.filter((r) => r.required && !sound(r)).map((r) => r.purpose));
  for (const row of rows) {
    if (!sound(row) || unsoundStep.has(row.purpose) || row.state.kind !== "installed") {
      apart.push(row);
      continue;
    }
    const step = steps.find((s) => s.purpose === row.purpose);
    if (step) step.size += row.state.size;
    else steps.push({ purpose: row.purpose, size: row.state.size });
  }
  const used = inventory.environments.filter((e) => e.current && e.installed);
  const stored = (kind: UvStore["kind"]) =>
    inventory.uv_stores
      .filter((store) => store.kind === kind)
      .reduce((sum, store) => sum + store.size_bytes, 0);
  const python = stored("python");
  const cache = stored("cache");
  return {
    steps,
    // Their Python is said with them, even when none is installed yet.
    tools:
      used.length || python > 0
        ? used.reduce((sum, e) => sum + e.size_bytes, 0) + python
        : null,
    cache: cache > 0 ? cache : null,
    apart,
    apartEnvironments: inventory.environments.filter((e) => !(e.current && e.installed)),
  };
}
