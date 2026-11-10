import type { CatalogModel, Language, ModelAction, ModelsView } from "./api.ts";
import { FRENCH } from "./languages.ts";
import { environmentBytes, missingEnvironments } from "./models.ts";
import type { Everything } from "./steps.ts";

/** The first launch, in steps (ADR 0079): what will be downloaded, one tile per thing it is
 *  for, the languages to add, one total, then each piece's progress. Said by what each
 *  piece is for, never by a model's name (P6). */

export type PieceKind = "transcribe" | "align" | "diarize" | "tools";

export interface Piece {
  kind: PieceKind;
  /** The models it downloads (none for the calculation tools). */
  models: string[];
  /** The environments it installs (only the calculation tools). */
  environments: string[];
  /** Their announced size; null when one of them has none (an environment the engine
   *  does not size). */
  bytes: number | null;
  /** The size counts an environment's order of magnitude: said « environ ». */
  approximate?: boolean;
}

const ORDER: PieceKind[] = ["transcribe", "align", "diarize", "tools"];

function sizeOf(catalog: CatalogModel[], keys: string[]): number | null {
  let sum = 0;
  for (const key of keys) {
    const size = catalog.find((m) => m.key === key)?.announced_bytes;
    if (!size) return null;
    sum += size;
  }
  return sum;
}

/** What the chain lacks on this Mac, one piece per thing it is for, in the order of the
 *  processing; a piece with nothing missing is left out. */
export function basePieces(view: ModelsView): Piece[] {
  const catalog = view.catalog.models;
  const keys = [
    ...new Set(
      view.readiness.missing
        .filter((p) => p.code === "model_missing" && p.model)
        .map((p) => p.model!),
    ),
  ];
  const byStage = (stage: string) =>
    keys.filter((key) => catalog.find((m) => m.key === key)?.stage === stage);
  const environments = missingEnvironments(view.readiness, view.inventory).map(
    ([name]) => name,
  );
  const pieces: Piece[] = (["transcribe", "align", "diarize"] as const).map(
    (kind) => {
      const models = byStage(kind);
      return { kind, models, environments: [], bytes: sizeOf(catalog, models) };
    },
  );
  // A model of another stage still counts: with the calculation tools, never dropped.
  const placed = new Set(pieces.flatMap((p) => p.models));
  const other = keys.filter((key) => !placed.has(key));
  const toolSizes = [
    sizeOf(catalog, other),
    ...environments.map((name) => environmentBytes(view.readiness, name)),
  ];
  pieces.push({
    kind: "tools",
    models: other,
    environments,
    bytes: toolSizes.includes(null)
      ? null
      : toolSizes.reduce<number>((sum, size) => sum + (size ?? 0), 0),
    approximate: environments.length > 0,
  });
  return pieces
    .filter((p) => p.models.length || p.environments.length)
    .sort((a, b) => ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind));
}

/** A language the first launch can add: not French (included), and its own models only:
 *  what it adds to the rest. */
export interface LanguageChoice {
  language: Language;
  models: string[];
  bytes: number | null;
}

export function languageChoices(
  languages: Language[],
  catalog: CatalogModel[],
): LanguageChoice[] {
  return languages
    .filter((l) => l.language !== FRENCH && !l.installed)
    .map((language) => {
      const models = language.missing_models.filter((key) =>
        language.own_models.includes(key),
      );
      return { language, models, bytes: sizeOf(catalog, models) };
    });
}

/** The size said for a piece or a language: « 1,3 Go », « environ 1,4 Go » for an order of
 *  magnitude, or « selon ce Mac » when unknown. */
export function sizeWords(
  bytes: number | null,
  gigabytes: (b: number) => string,
  approximate = false,
): string {
  if (bytes === null) return "selon ce Mac";
  return approximate ? `environ ${gigabytes(bytes)}` : gigabytes(bytes);
}

/** What « Télécharger » fetches: the pieces, plus the chosen languages' own models. */
export function onboardingDownload(
  pieces: Piece[],
  chosen: LanguageChoice[],
): Everything {
  const download = [
    ...new Set([
      ...pieces.flatMap((p) => p.models),
      ...chosen.flatMap((c) => c.models),
    ]),
  ];
  const install = pieces.flatMap((p) => p.environments);
  const sizes = [...pieces.map((p) => p.bytes), ...chosen.map((c) => c.bytes)];
  return {
    download,
    install,
    bytes: sizes.reduce<number>((sum, size) => sum + (size ?? 0), 0),
    more: sizes.includes(null),
    approximate: pieces.some((p) => p.approximate && p.bytes !== null),
  };
}

/** A line of the progress (step 5): a piece, or one language's alignment. */
export interface ProgressLine {
  key: string;
  label: string;
  models: string[];
  environments: string[];
}

export function progressLines(
  pieces: Piece[],
  chosen: LanguageChoice[],
  labels: Record<PieceKind, string>,
): ProgressLine[] {
  const of = (kind: PieceKind) => pieces.filter((p) => p.kind === kind);
  const line = (piece: Piece, label: string): ProgressLine => ({
    key: piece.kind,
    label,
    models: piece.models,
    environments: piece.environments,
  });
  const languages = chosen.map((c) => ({
    key: `align-${c.language.language}`,
    label: `Alignement, ${c.language.label.toLocaleLowerCase("fr")}`,
    models: c.models,
    environments: [],
  }));
  return [
    ...of("transcribe").map((p) => line(p, labels.transcribe)),
    ...of("align").map((p) => line(p, "Alignement, français")),
    ...languages,
    ...of("diarize").map((p) => line(p, labels.diarize)),
    ...of("tools").map((p) => line(p, labels.tools)),
  ];
}

export type LineState =
  | { kind: "waiting" }
  | { kind: "running"; percent: number | null }
  | { kind: "done" }
  | { kind: "failed"; error: string }
  | { kind: "stopped" };

/** Where a line stands: done once none of its pieces lacks any more (read from the
 *  engine), else its downloads' progress, a failure said as the service says it. */
export function lineState(
  line: ProgressLine,
  view: ModelsView,
  actions: ModelAction[],
): LineState {
  const lacking = new Set(
    view.readiness.missing
      .flatMap((p) => [p.model, p.environment])
      .filter(Boolean),
  );
  const own = (a: ModelAction) =>
    a.kind === "model"
      ? line.models.includes(a.name)
      : line.environments.includes(a.name);
  const mine = actions.filter(own);
  const failed = mine.find((a) => a.state === "failed");
  if (failed)
    return {
      kind: "failed",
      error: failed.error ?? "Le téléchargement a échoué.",
    };
  const running = mine.filter((a) => a.state === "running");
  if (running.length) {
    const total = running.reduce((sum, a) => sum + (a.total_bytes ?? 0), 0);
    const done = running.reduce((sum, a) => sum + a.done_bytes, 0);
    return {
      kind: "running",
      percent:
        total > 0 ? Math.min(100, Math.round((done / total) * 100)) : null,
    };
  }
  // A piece of the chain: done once the engine no longer says it lacks. A chosen
  // language (not checked by the engine's readiness, which is French's): once each of its
  // models' download is over.
  const doneNow = line.key.startsWith("align-")
    ? line.models.every((k) =>
        mine.some((a) => a.kind === "model" && a.name === k && a.state === "done"),
      )
    : !line.models.some((k) => lacking.has(k)) &&
      !line.environments.some((n) => lacking.has(n));
  // Stopped (here or from the settings) and not over: said, with its way to resume.
  if (!doneNow && mine.some((a) => a.state === "cancelled")) return { kind: "stopped" };
  return doneNow ? { kind: "done" } : { kind: "waiting" };
}

/** What « Reprendre » starts again on a line: its pieces neither running nor over. */
export function toResume(
  line: ProgressLine,
  view: ModelsView,
  actions: ModelAction[],
): { models: string[]; environments: string[] } {
  const lacking = new Set(
    view.readiness.missing.flatMap((p) => [p.model, p.environment]).filter(Boolean),
  );
  const last = (kind: ModelAction["kind"], name: string) =>
    actions.find((a) => a.kind === kind && a.name === name);
  const left = (kind: ModelAction["kind"], name: string) => {
    const a = last(kind, name);
    if (a?.state === "running" || a?.state === "done") return false;
    // A chosen language's model is not in the readiness: its own last action says.
    return lacking.has(name) || a?.state === "failed" || a?.state === "cancelled";
  };
  return {
    models: line.models.filter((k) => left("model", k)),
    environments: line.environments.filter((n) => left("environment", n)),
  };
}

/** Whether a line has something running, to stop (even beside a failure). */
export function lineRunning(line: ProgressLine, actions: ModelAction[]): boolean {
  return actions.some(
    (a) =>
      a.state === "running" &&
      (a.kind === "model" ? line.models.includes(a.name) : line.environments.includes(a.name)),
  );
}

/** Whether a line has been started already (running, over, failed or stopped): the window
 *  of a waiting session then follows it rather than offering it again. */
export function lineStarted(line: ProgressLine, actions: ModelAction[]): boolean {
  return actions.some((a) =>
    a.kind === "model" ? line.models.includes(a.name) : line.environments.includes(a.name),
  );
}

/** What runs for these lines (ADR 0079): the downloads are all needed, so they stop
 *  together, never one piece apart. */
export function linesRunning(
  lines: ProgressLine[],
  actions: ModelAction[],
): ModelAction[] {
  return actions.filter(
    (a) =>
      a.state === "running" &&
      lines.some((line) =>
        a.kind === "model"
          ? line.models.includes(a.name)
          : line.environments.includes(a.name),
      ),
  );
}

/** What « Reprendre » starts again for these lines, all of it at once. */
export function linesToResume(
  lines: ProgressLine[],
  view: ModelsView,
  actions: ModelAction[],
): { models: string[]; environments: string[] } {
  const left = lines.map((line) => toResume(line, view, actions));
  return {
    models: [...new Set(left.flatMap((l) => l.models))],
    environments: [...new Set(left.flatMap((l) => l.environments))],
  };
}
