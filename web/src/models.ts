import type { CatalogModel, EnvironmentInfo, Inventory, ModelAction, ModelsView, Readiness } from "./api.ts";

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
  | { kind: "installed"; size: number; outdated: boolean }
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

function stateOf(key: string, inventory: Inventory, action: ModelAction | null): ModelState {
  const there = inventory.models.find((m) => m.key === key);
  const partial = inventory.partial_downloads.find((p) => p.key === key);
  if (action?.state === "running") return { kind: "running", action };
  if (there && there.state !== "intact") return { kind: "altered", size: there.size_bytes, problem: there.problem };
  if (there) return { kind: "installed", size: there.size_bytes, outdated: there.outdated };
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
      purpose: STAGE_WORDS[model.stage] ?? model.role,
      required: model.required_by.includes(readiness.profile),
      state: stateOf(model.key, inventory, action),
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
      state: stateOf(key, inventory, action),
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

/** What the chain lacks, said in a sentence; null when all is there. */
export function readinessLine(readiness: Readiness, inventory: Inventory): string | null {
  if (readiness.ready) return null;
  const parts = readiness.missing.map((piece) => {
    if (piece.environment) return `l'environnement de calcul « ${piece.environment} »`;
    const there = inventory.models.find((m) => m.key === piece.model);
    return piece.code === "model_altered" || (there && there.state !== "intact")
      ? `le modèle « ${piece.model} » (abîmé)`
      : `le modèle « ${piece.model} »`;
  });
  return `Les séances ne peuvent pas être traitées : il manque ${parts.join(", ")}.`;
}
