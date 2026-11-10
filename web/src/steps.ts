import {
  api,
  type CatalogModel,
  type ModelAction,
  type ModelsView,
  type StageName,
} from "./api.ts";
import { environmentBytes, gigabytes, missingEnvironments } from "./models.ts";
import type { PieceKind } from "./onboarding.ts";
import { LABELS, WHAT } from "./components/pieceWords.ts";

/** What the engine's state asks of the user on this Mac (ADR 0049; « geste demandé » in the
 *  glossary), grouped in updates the user decides one at a time: what changed, in a
 *  sentence and a few figures, then two ways out, the recommended one first. Kept light:
 *  it speaks to people, not to engineers. Made from the models' view alone: nothing here
 *  names a model or a version (P6). */
export type ChoiceKind =
  /** Download the new model, then remove the old one once the new one is there. */
  | "replace"
  /** The new one is there: remove the old one. */
  | "removeOld"
  /** Remove the environments an older engine left. */
  | "removeEnvironments"
  /** Nothing now: asked again at the next launch. */
  | "later"
  /** Nothing, for good: not asked again (it only takes space). */
  | "keep";

export interface Choice {
  kind: ChoiceKind;
  /** Says what it does before it is done: the size downloaded, the space freed. */
  label: string;
  recommended: boolean;
}

/** One thing the update is about, drawn as a tile (ADR 0079): the model in use and its
 *  successor, or what no longer serves. Said by what it is for, never by its name (P6). */
export interface NoticeTile {
  /** The model or environment folder it stands for. */
  key: string;
  role: "old" | "new";
  piece: PieceKind;
  name: string;
  what: string;
  bytes: number | null;
}

export interface Gain {
  label: string;
  value: string;
}

/** An update that asks a choice in the update window: a model replaced, old environments
 *  left. */
export interface ChoiceNotice {
  /** Stable while the update is the same: what « keep » keeps. */
  id: string;
  kind: "replacement" | "cleanup";
  title: string;
  /** What it is about, in one sentence. */
  explanation: string;
  /** What it is about, as tiles. */
  tiles: NoticeTile[];
  /** A few figures, measured by the engine. */
  gains: Gain[];
  /** The engine's own sentence, as it is: only when it gave no figures. */
  note: string | null;
  /** Where the figures come from (the engine's bench): developer mode. */
  evidence: string | null;
  choices: [Choice, Choice];
  /** What the choices act on: models to download, environments to install, models and
   *  environments (by folder) to remove. */
  download: string[];
  install: string[];
  remove: string[];
  removeEnvironments: string[];
}

/** What the processing lacks on this Mac (ADR 0079): the onboarding at the first launch,
 *  else the « Ce qui manque » window, its tiles and its « Télécharger ». No text of its own:
 *  those screens say it. */
export interface InstallNotice {
  id: string;
  kind: "install";
  download: string[];
  install: string[];
  remove: [];
  removeEnvironments: [];
  /** The first launch: nothing of the engine on this Mac yet but what the app ships. */
  welcome: boolean;
}

export type UpdateNotice = ChoiceNotice | InstallNotice;

/** What a model does, by its stage. */
const WHAT_OF: Partial<Record<StageName, string>> = {
  transcribe: "de transcription",
  align: "d'alignement des mots",
  diarize: "de reconnaissance des voix",
};
const QUALITY = {
  same: "identique",
  better: "meilleure",
  worse: "moindre",
} as const;
const PIECE_OF: Partial<Record<StageName, PieceKind>> = {
  transcribe: "transcribe",
  align: "align",
  diarize: "diarize",
};

const folderName = (path: string) =>
  path.split("/").filter(Boolean).pop() ?? path;
const signed = (bytes: number) =>
  `${bytes > 0 ? "−" : "+"}${gigabytes(Math.abs(bytes))}`;

/** What a replacement brings, in three figures the engine measured or its catalog gives:
 *  speed, weight on the disk, quality. One it does not give is left out. */
export function replacementGains(
  was: CatalogModel | undefined,
  now: CatalogModel | undefined,
): Gain[] {
  if (!was) return [];
  const gains: Gain[] = [];
  const speedup = was.replacement_speedup;
  if (speedup)
    gains.push({
      label: "Vitesse",
      value:
        Math.round(speedup * 10) === 10
          ? "aussi rapide"
          : speedup > 1
            ? `×${String(Math.round(speedup * 10) / 10).replace(".", ",")}`
            : "plus lente",
    });
  const disk = now ? was.announced_bytes - now.announced_bytes : 0;
  if (disk !== 0) gains.push({ label: "Poids", value: signed(disk) });
  if (was.replacement_quality)
    gains.push({ label: "Qualité", value: QUALITY[was.replacement_quality] });
  return gains;
}

function replacements(view: ModelsView, lacking: Set<string>): ChoiceNotice[] {
  const { catalog, inventory } = view;
  const notices: ChoiceNotice[] = [];
  for (const old of inventory.models) {
    if (!old.replaced_by) continue;
    const by = old.replaced_by;
    const was = catalog.models.find((m) => m.key === old.key);
    const now = catalog.models.find((m) => m.key === by);
    const stage = (now ?? was)?.stage;
    const what = stage && WHAT_OF[stage] ? ` ${WHAT_OF[stage]}` : "";
    const piece = (stage && PIECE_OF[stage]) || "tools";
    const lighter = !!(was && now && now.announced_bytes < was.announced_bytes);
    const freed = gigabytes(old.size_bytes);
    const gains = replacementGains(was, now);
    const base = {
      kind: "replacement" as const,
      gains,
      note: gains.length ? null : was?.replacement_note || null,
      evidence: was?.replacement_evidence ?? null,
      install: [],
      remove: [old.key],
      removeEnvironments: [],
    };
    if (lacking.has(by)) {
      notices.push({
        ...base,
        id: `remplacement:${old.key}:${by}`,
        title: `Un nouveau modèle${what}`,
        explanation: `${lighter ? "Plus léger, il" : "Il"} remplace celui que vous utilisez. D'ici là, les séances attendent.`,
        tiles: [
          { key: old.key, role: "old", piece, name: "Actuel", what: "Supprimé ensuite", bytes: old.size_bytes },
          { key: by, role: "new", piece, name: "Nouveau", what: WHAT[piece], bytes: now?.announced_bytes ?? null },
        ],
        choices: [
          {
            kind: "replace",
            label: now ? `Remplacer · ${gigabytes(now.announced_bytes)}` : "Remplacer",
            recommended: true,
          },
          { kind: "later", label: "Plus tard", recommended: false },
        ],
        download: [by],
      });
    } else {
      notices.push({
        ...base,
        // Its own id: keeping the old one for good never hides a later « Remplacer ».
        id: `ancien:${old.key}:${by}`,
        title: `L'ancien modèle${what} ne sert plus`,
        explanation: "Le nouveau est installé.",
        tiles: [
          { key: old.key, role: "old", piece, name: "Ancien modèle", what: "Ne sert plus", bytes: old.size_bytes },
        ],
        choices: [
          { kind: "removeOld", label: `Libérer ${freed}`, recommended: true },
          { kind: "keep", label: "Le garder", recommended: false },
        ],
        download: [],
      });
    }
  }
  return notices;
}

function installation(view: ModelsView, keys: string[]): InstallNotice | null {
  const { catalog, inventory, readiness } = view;
  const environments = missingEnvironments(readiness, inventory);
  if (!keys.length && !environments.length) return null;
  // Nothing on this Mac yet but what the app ships and installs itself (a bundled model,
  // engine v1.15.0): still the first launch.
  const bundled = (key: string) =>
    catalog.models.find((m) => m.key === key)?.bundled === true;
  return {
    id: `installation:${[...keys, ...environments.map(([name]) => name)].join(",")}`,
    kind: "install",
    download: keys,
    install: environments.map(([name]) => name),
    remove: [],
    removeEnvironments: [],
    welcome:
      inventory.models.every((m) => bundled(m.key)) &&
      !inventory.environments.some((e) => e.installed),
  };
}

function cleanup(view: ModelsView): ChoiceNotice | null {
  const old = view.inventory.environments.filter((e) => !e.current);
  if (!old.length) return null;
  const freed = gigabytes(old.reduce((sum, e) => sum + e.size_bytes, 0));
  return {
    id: `nettoyage:${old.map((e) => folderName(e.path)).join(",")}`,
    kind: "cleanup",
    title:
      old.length > 1
        ? "D'anciennes versions restent sur ce Mac"
        : "Une ancienne version reste sur ce Mac",
    explanation:
      "Un composant du moteur a été mis à jour ; l'ancienne version ne sert plus.",
    tiles: old.map((e) => ({
      key: e.path,
      role: "old" as const,
      piece: "tools" as const,
      name: `${LABELS.tools}, ancienne version`,
      what: "Ne sert plus",
      bytes: e.size_bytes,
    })),
    gains: [],
    note: null,
    evidence: null,
    choices: [
      { kind: "removeEnvironments", label: `Libérer ${freed}`, recommended: true },
      {
        kind: "keep",
        label: old.length > 1 ? "Les garder" : "La garder",
        recommended: false,
      },
    ],
    download: [],
    install: [],
    remove: [],
    removeEnvironments: old.map((e) => e.path),
  };
}

/** Every update the engine's state asks about, in order: replaced models, what the
 *  processing lacks besides, what an older engine left. */
export function updateNotices(view: ModelsView): UpdateNotice[] {
  const lacking = new Set(
    view.readiness.missing
      .filter((p) => p.code === "model_missing" && p.model)
      .map((p) => p.model!),
  );
  const replacing = replacements(view, lacking);
  const covered = new Set(replacing.flatMap((n) => n.download));
  return [
    ...replacing,
    installation(
      view,
      [...lacking].filter((key) => !covered.has(key)),
    ),
    cleanup(view),
  ].filter((n): n is UpdateNotice => n !== null);
}

/** What the update window still has to ask in this session: not what was answered (except
 *  the one asked from the settings, shown first), and nothing of what the processing lacks
 *  once « Ce qui manque » was closed: closing it is « later », even if what lacks changed
 *  meanwhile (a piece installed while it was open). */
export function stillAsked(
  notices: UpdateNotice[],
  passed: string[],
  asked: string | null,
  lackingLater: boolean,
): UpdateNotice[] {
  return notices
    .filter(
      (n) =>
        (n.id === asked || !passed.includes(n.id)) &&
        !(lackingLater && n.kind === "install"),
    )
    .sort((a, b) => Number(b.id === asked) - Number(a.id === asked));
}

/** A replacement the user chose: the old models go once the new ones are installed. */
export interface Replacing {
  /** The update it was chosen in. */
  id: string;
  remove: string[];
  when: string[];
  /** The downloads of the new ones that ended before this choice (`started_at`): their
   *  state says nothing about this one. */
  before: string[];
}

/** Which chosen replacements can remove their old model now (every new one installed and
 *  intact), and which still wait. One whose download failed or was stopped is dropped:
 *  nothing is removed without its successor (P8). */
export function settleReplacements(
  pending: Replacing[],
  view: ModelsView,
  actions: readonly Pick<
    ModelAction,
    "kind" | "name" | "state" | "started_at"
  >[],
): { ready: Replacing[]; left: Replacing[] } {
  const installed = (key: string) =>
    view.inventory.models.some((m) => m.key === key && m.state === "intact");
  const stopped = (r: Replacing, key: string) =>
    actions.some(
      (a) =>
        a.kind === "model" &&
        a.name === key &&
        (a.state === "failed" || a.state === "cancelled") &&
        !r.before.includes(a.started_at),
    );
  const ready = pending.filter((r) => r.when.every(installed));
  const left = pending.filter(
    (r) => !ready.includes(r) && !r.when.some((key) => stopped(r, key)),
  );
  return { ready, left };
}

/** The updates still to ask about: not kept for good. */
export function pendingNotices(
  notices: UpdateNotice[],
  dismissed: readonly string[],
): UpdateNotice[] {
  return notices.filter((n) => !dismissed.includes(n.id));
}

const CHANGED = "coulisses:gestes";
/** The last reading of the models, kept for this page's life. */
let lastView: ModelsView | null = null;

/** The models' view was read again (at launch, the settings, the window): whoever shows the
 *  updates (the dot on « Réglages ») reads it rather than asking the engine once more. */
export function stepsChanged(view: ModelsView): void {
  lastView = view;
  window.dispatchEvent(new CustomEvent<ModelsView>(CHANGED, { detail: view }));
}

/** The last reading, shown at once while the engine measures the disk again (a second or
 *  so): the Transcription tab opens without a skeleton once the app has read it. */
export function lastModelsView(): ModelsView | null {
  return lastView;
}

export function onStepsChanged(
  listener: (view: ModelsView) => void,
): () => void {
  const handle = (e: Event) => listener((e as CustomEvent<ModelsView>).detail);
  window.addEventListener(CHANGED, handle);
  return () => window.removeEventListener(CHANGED, handle);
}

/** Everything the processing lacks on this Mac, fetched in one go (« Voir ce qui manque »):
 *  the models and environments the engine's readiness names, plus the models a waiting
 *  session's language needs (`extra`). What already runs is not asked again. */
export interface Everything {
  download: string[];
  install: string[];
  /** The models' announced size; the environments' is not known before they install. */
  bytes: number;
  /** Something not sized (an environment an older engine does not size): more than `bytes`. */
  more: boolean;
  /** `bytes` counts an environment's order of magnitude: said « environ ». */
  approximate?: boolean;
}

export function everythingMissing(
  view: ModelsView,
  actions: ModelAction[] = view.actions,
  extra: string[] = [],
): Everything | null {
  const running = new Set(
    actions
      .filter((a) => a.state === "running")
      .map((a) => `${a.kind}:${a.name}`),
  );
  const keys = new Set([
    ...view.readiness.missing
      .filter((p) => p.code === "model_missing" && p.model)
      .map((p) => p.model!),
    ...extra,
  ]);
  const download = [...keys].filter((key) => !running.has(`model:${key}`));
  const install = missingEnvironments(view.readiness, view.inventory)
    .map(([name]) => name)
    .filter((name) => !running.has(`environment:${name}`));
  if (!download.length && !install.length) return null;
  const sizes = [
    ...download.map(
      (key) => view.catalog.models.find((m) => m.key === key)?.announced_bytes ?? null,
    ),
    ...install.map((name) => environmentBytes(view.readiness, name)),
  ];
  const bytes = sizes.reduce<number>((sum, size) => sum + (size ?? 0), 0);
  // Something without an announced size: more than the figure said. An environment the
  // engine sizes is an order of magnitude: « environ ».
  return {
    download,
    install,
    bytes,
    more: sizes.includes(null),
    approximate: install.length > 0 && !sizes.includes(null),
  };
}

/** Whether a waiting session needs more than its language's own download (a new install):
 *  then « Voir ce qui manque », else the language's « Télécharger ». */
export function beyondLanguage(
  everything: Everything | null,
  languageMissing: readonly string[],
): boolean {
  return (
    everything !== null &&
    (everything.install.length > 0 ||
      everything.download.some((key) => !languageMissing.includes(key)))
  );
}

/** Whether a model's row gives way to « Voir ce qui manque », outside developer mode: missing,
 *  with nothing of its own to say (no last download, no old model it replaces). */
export function coveredByEverything(
  everything: Everything | null,
  row: { key: string; state: { kind: string }; last: unknown },
  replacing: boolean,
): boolean {
  return (
    everything !== null &&
    row.state.kind === "missing" &&
    row.last === null &&
    !replacing &&
    everything.download.includes(row.key)
  );
}

/** Whether everything the processing lacks is downloading or installing: then it says so,
 *  rather than what lacks. A damaged model, or one nothing fetches, keeps it said. */
export function allLackingRunning(
  view: ModelsView,
  actions: ModelAction[] = view.actions,
): boolean {
  const running = (kind: string, name: string | null) =>
    name !== null &&
    actions.some((a) => a.state === "running" && a.kind === kind && a.name === name);
  return (
    view.readiness.missing.length > 0 &&
    view.readiness.missing.every((p) =>
      p.code === "model_missing"
        ? running("model", p.model)
        : p.code === "environment_missing"
          ? running("environment", p.environment)
          : false,
    )
  );
}

/** Starts it, each piece by the route that exists (ADR 0036); the models' view read again
 *  after, for whoever follows the downloads. A refusal is thrown, with what had started. */
export async function downloadEverything(everything: Everything): Promise<void> {
  const total = everything.download.length + everything.install.length;
  let started = 0;
  try {
    for (const key of everything.download) {
      await api.downloadModel(key);
      started += 1;
    }
    for (const name of everything.install) {
      await api.installEnvironment(name);
      started += 1;
    }
  } catch (e) {
    const said = (e as Error).message;
    throw new Error(
      started ? `${started} sur ${total} ont démarré ; le suivant a été refusé : ${said}` : said,
    );
  } finally {
    try {
      stepsChanged(await api.engineModels());
    } catch (e) {
      // The service gone: the frame says it; what started runs on.
      console.warn("everything: reading the models again:", (e as Error).message);
    }
  }
}
