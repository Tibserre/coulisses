import type {
  CatalogModel,
  ModelAction,
  ModelsView,
  StageName,
} from "./api.ts";
import { gigabytes, missingEnvironments } from "./models.ts";

/** What the engine's state asks of the user on this Mac (ADR 0049; « geste demandé » in the
 *  glossary), grouped in updates the user decides one at a time: what changed, in a
 *  sentence and a few figures, then two ways out, the recommended one first. Kept light:
 *  it speaks to people, not to engineers. Made from the models' view alone: nothing here
 *  names a model or a version (P6). */
export type NoticeKind = "replacement" | "install" | "cleanup";

export type ChoiceKind =
  /** Download the new model, then remove the old one once the new one is there. */
  | "replace"
  /** The new one is there: remove the old one. */
  | "removeOld"
  /** Download the models and install the environments the processing lacks. */
  | "install"
  /** Remove the environments an older engine left. */
  | "removeEnvironments"
  /** Nothing now: asked again at the next launch. */
  | "later"
  /** Nothing, for good: not asked again (it only takes space). */
  | "keep";

export interface Choice {
  kind: ChoiceKind;
  label: string;
  /** What it does, said before it is done: the network, the space freed, what is lost. */
  description: string;
  recommended: boolean;
}

export interface Gain {
  label: string;
  value: string;
}

export interface UpdateNotice {
  /** Stable while the update is the same: what « keep » keeps. */
  id: string;
  kind: NoticeKind;
  /** The nature of the change, above the title. */
  eyebrow: string;
  title: string;
  /** What it is about, in one sentence. */
  explanation: string;
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

/** Whose update it is, and what a model does, by its stage. */
const ENGINE_OF: Partial<Record<StageName, string>> = {
  transcribe: "du moteur de transcription",
  align: "de l'alignement des mots",
  diarize: "de la reconnaissance des voix",
};
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
const TITLE = "Une action est attendue de votre part";

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

function replacements(view: ModelsView, lacking: Set<string>): UpdateNotice[] {
  const { catalog, inventory } = view;
  const notices: UpdateNotice[] = [];
  for (const old of inventory.models) {
    if (!old.replaced_by) continue;
    const by = old.replaced_by;
    const was = catalog.models.find((m) => m.key === old.key);
    const now = catalog.models.find((m) => m.key === by);
    const stage = (now ?? was)?.stage;
    const what = stage && WHAT_OF[stage] ? ` ${WHAT_OF[stage]}` : "";
    const lighter = !!(was && now && now.announced_bytes < was.announced_bytes);
    const freed = gigabytes(old.size_bytes);
    const gains = replacementGains(was, now);
    const base = {
      kind: "replacement" as const,
      eyebrow: `Mise à jour ${(stage && ENGINE_OF[stage]) || "du moteur"}`,
      title: TITLE,
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
        explanation: `Un nouveau modèle${what}${lighter ? ", plus léger," : ""} peut remplacer celui que vous utilisez.`,
        choices: [
          {
            kind: "replace",
            label: "Remplacer l'ancien par le nouveau",
            description: `Télécharge ${now ? gigabytes(now.announced_bytes) : "le nouveau"} depuis internet, puis supprime l'ancien (${freed} libérés).`,
            recommended: true,
          },
          {
            kind: "later",
            label: "Garder l'ancien pour l'instant",
            description:
              "Les séances ne pourront pas être traitées tant que le nouveau n'est pas installé.",
            recommended: false,
          },
        ],
        download: [by],
      });
    } else {
      notices.push({
        ...base,
        // Its own id: keeping the old one for good never hides a later « Remplacer ».
        id: `ancien:${old.key}:${by}`,
        explanation: `Le nouveau modèle${what} est installé : l'ancien ne sert plus.`,
        choices: [
          {
            kind: "removeOld",
            label: "Supprimer l'ancien modèle",
            description: `Libère ${freed} sur ce Mac.`,
            recommended: true,
          },
          {
            kind: "keep",
            label: "Garder l'ancien modèle",
            description: "Il reste sur ce Mac, sans servir.",
            recommended: false,
          },
        ],
        download: [],
      });
    }
  }
  return notices;
}

function installation(view: ModelsView, keys: string[]): UpdateNotice | null {
  const { catalog, inventory, readiness } = view;
  const environments = missingEnvironments(readiness, inventory);
  if (!keys.length && !environments.length) return null;
  const firstLaunch =
    inventory.models.length === 0 &&
    !inventory.environments.some((e) => e.installed);
  const bytes = keys.reduce(
    (sum, key) =>
      sum + (catalog.models.find((m) => m.key === key)?.announced_bytes ?? 0),
    0,
  );
  return {
    id: `installation:${[...keys, ...environments.map(([name]) => name)].join(",")}`,
    kind: "install",
    eyebrow: firstLaunch ? "Bienvenue dans Coulisses" : "Mise à jour du moteur",
    title: TITLE,
    explanation: firstLaunch
      ? "Pour traiter vos séances, Coulisses doit d'abord télécharger ce qui lui sert à les écouter."
      : "Pour continuer à traiter vos séances, Coulisses doit télécharger un complément.",
    gains: [],
    note: null,
    evidence: null,
    choices: [
      {
        kind: "install",
        label: firstLaunch ? "Tout télécharger" : "Télécharger",
        description:
          bytes && !environments.length
            ? `Environ ${gigabytes(bytes)} depuis internet, une seule fois.`
            : `Depuis internet, une seule fois${bytes ? ` (plus de ${gigabytes(bytes)})` : ""}.`,
        recommended: true,
      },
      {
        kind: "later",
        label: "Plus tard",
        description: "Les séances ne pourront pas être traitées d'ici là.",
        recommended: false,
      },
    ],
    download: keys,
    install: environments.map(([name]) => name),
    remove: [],
    removeEnvironments: [],
  };
}

function cleanup(view: ModelsView): UpdateNotice | null {
  const old = view.inventory.environments.filter((e) => !e.current);
  if (!old.length) return null;
  const freed = gigabytes(old.reduce((sum, e) => sum + e.size_bytes, 0));
  return {
    id: `nettoyage:${old.map((e) => folderName(e.path)).join(",")}`,
    kind: "cleanup",
    eyebrow: "Mise à jour du moteur",
    title: TITLE,
    explanation:
      "Une ancienne version d'un composant du moteur est restée sur ce Mac. Elle ne sert plus.",
    gains: [],
    note: null,
    evidence: null,
    choices: [
      {
        kind: "removeEnvironments",
        label: "La supprimer",
        description: `Libère ${freed} sur ce Mac.`,
        recommended: true,
      },
      {
        kind: "keep",
        label: "La garder",
        description: "Elle reste sur ce Mac, sans servir.",
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
