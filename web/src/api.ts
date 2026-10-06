/** The local service (same origin, 127.0.0.1). Errors carry the service's French message. */

export type JobState = "queued" | "running" | "done" | "failed";

export interface Session {
  id: string;
  title: string | null;
  recorded_at: string;
  created_at: string;
  space_id: number;
  space_name: string;
  /** People checked as present. */
  attendee_ids: number[];
  /** People present whom nobody named, in addition to the checked ones. */
  unnamed_attendees: number | null;
  /** Minimum of voices asked of the engine by the latest processing (P3). */
  min_voices: number | null;
  reference_source_id: string;
  duration_s: number | null;
  job_state: JobState | null;
  job_error: string | null;
}

export interface Space {
  id: number;
  name: string;
  voice_recognition: boolean;
  archived: boolean;
}

export interface Person {
  id: number;
  space_id: number;
  kind: "member" | "guest";
  name: string;
  role: string | null;
  /** Palette slot, the same from one session to the next. */
  color_slot: number;
  archived: boolean;
}

export interface GlossaryEntry {
  id: number;
  space_id: number;
  term: string;
  category: string | null;
  variants: string[];
  archived: boolean;
}

export interface AudioSource {
  source_id: string;
  origin: "captured" | "imported";
  original_name: string;
  file_name: string;
  sha256: string;
  size_bytes: number;
  duration_s: number | null;
  sample_rate: number | null;
  channels: number | null;
  codec: string | null;
  file_present: boolean;
}

export type ErrorCode =
  | "model_missing"
  | "model_altered"
  | "environment_missing"
  | "audio_unreadable"
  | "too_few_speakers"
  | "out_of_memory"
  | "interrupted"
  | "cancelled"
  | "scratch_not_cleared"
  | "engine_failed";

export type StageState =
  "pending" | "running" | "stalled" | "succeeded" | "failed";

export interface StageView {
  stage: string;
  label: string;
  state: StageState;
  run_id: string | null;
  progress: {
    phase: string;
    done: number;
    total: number;
    unit: "s" | "windows" | "steps";
  } | null;
  started_at: string | null;
  finished_at: string | null;
  duration_s: number | null;
  max_rss_bytes: number | null;
  error: string | null;
  /** The engine's closed list of error codes (engine ADR 0021), null for the
   *  application's own errors and runs closed before engine v1.3.0. */
  error_code: ErrorCode | null;
  error_details: Record<string, unknown> | null;
  folder_missing: boolean;
}

export interface SessionDetail {
  session: Session;
  source: AudioSource | null;
  stages: StageView[];
}

export interface AppInfo {
  data_dir: string;
  engine_version: string;
  app_version: string;
  profile: string;
  recovery_problems: string[];
  processing_error: string | null;
}

/** The corrected view: the engine's « who said what » with the user's corrections
 *  applied by the service. Times are measured or null, never estimated (P2). */
export interface Word {
  text: string;
  start: number | null;
  end: number | null;
  confidence: number | null;
  uncertain: boolean;
  corrected: boolean;
  /** Added by hand: no measured time of its own. */
  added: boolean;
  /** A glossary term this word is a known wrong spelling of. */
  suggestion: string | null;
}

export interface Turn {
  /** Index in the engine's run: what corrections point at. */
  index: number;
  speaker: string | null;
  start: number | null;
  end: number | null;
  words: Word[];
  edited: boolean;
}

export interface Speaker {
  label: string | null;
  number: number | null;
  name: string;
  named: boolean;
  person_id: number | null;
  character: string | null;
  played_by: string | null;
  color_slot: number | null;
  seconds: number;
  turns: number;
}

export interface EditInfo {
  id: number;
  kind: string;
  description: string;
  created_at: string;
  reverted: boolean;
  /** Journal entry that undid it: the latest undone is the one Cmd-Shift-Z redoes. */
  undone_by: number | null;
  /** Undone, then applied again by a later copy still in force. */
  redone: boolean;
  /** For a text correction: the line it corrects. */
  turn: number | null;
}

export interface CorrectedView {
  run_id: string;
  turns: Turn[];
  speakers: Speaker[];
  untranscribed: { start: number; end: number }[];
  edits: EditInfo[];
  /** Corrections made on another run, not carried over yet: shown, never dropped. */
  other_run_edits: number;
  word_count: number;
  timed_share: number;
}

export type EditRequest =
  | {
      kind: "assign_speaker";
      speaker: string;
      person_id?: number | null;
      name?: string | null;
      character?: string | null;
    }
  | { kind: "merge_speakers"; source: string; target: string }
  | { kind: "reassign_turns"; turns: number[]; target?: string | null }
  | { kind: "edit_text"; turn: number; text: string };

export type Provenance = Record<string, unknown> & {
  run_id: string;
  stage: string;
  engine_id: string;
  status: "succeeded" | "failed";
  versions: Record<string, string>;
  model: { repo: string; revision: string; fingerprint?: string | null } | null;
  settings: Record<string, unknown>;
  started_at: string;
  finished_at: string;
  duration_s: number;
  max_rss_bytes: number;
  coulisses_version: string;
  machine: Record<string, string>;
  error: { type: string; message: string; traceback: string } | null;
};

export interface Generation {
  id: number;
  run_id: string;
  action_ref: string;
  action_name: string;
  model: string;
  created_at: string;
  /** "unique", or "sections": summarised in parts, then merged. */
  strategy: string;
  calls: number;
  duration_s: number;
  /** null when the output file is missing (moved or deleted in the Finder). */
  output: string | null;
  /** Corrections were made, or the transcript changed, since it was generated. */
  stale: boolean;
  /** Why it cannot be read as usual (missing or unreadable files). */
  problem: string | null;
}

export interface PendingGeneration {
  job_id: number;
  action_ref: string;
  action_name: string;
  model: string;
  state: JobState;
  error: string | null;
}

export interface Generations {
  generations: Generation[];
  pending: PendingGeneration[];
}

export interface InstalledModel {
  name: string;
  size_bytes: number;
  digest: string;
  family: string | null;
  parameter_size: string | null;
}

export interface ModelsInfo {
  reachable: boolean;
  error: string | null;
  default: string;
  models: InstalledModel[];
}

export interface ActionInfo {
  ref: string;
  name: string;
  description: string;
}

export interface SpaceAction {
  action_ref: string;
  auto_run: boolean;
  model: string | null;
}

export type SpaceTemplate = "impro" | "reunion" | "vide";

export class ServiceError extends Error {}

async function readError(response: Response): Promise<ServiceError> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return new ServiceError(body.detail);
  } catch {
    // Not JSON: fall through to the generic message, which keeps the HTTP status.
  }
  return new ServiceError(
    `Le service a répondu ${response.status} ${response.statusText}.`,
  );
}

async function send<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers:
        body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ServiceError(
      "Le service Coulisses ne répond pas. Est-il lancé ?",
    );
  }
  if (!response.ok) throw await readError(response);
  return (await response.json()) as T;
}

const getJson = <T>(path: string) => send<T>("GET", path);
const sessionPath = (id: string) => `/api/seances/${encodeURIComponent(id)}`;

export const api = {
  info: () => getJson<AppInfo>("/api/etat"),
  sessions: () => getJson<Session[]>("/api/seances"),
  session: (id: string) => getJson<SessionDetail>(sessionPath(id)),
  transcript: (id: string) =>
    getJson<CorrectedView>(`${sessionPath(id)}/transcript`),
  addEdit: (id: string, edit: EditRequest) =>
    send<CorrectedView>("POST", `${sessionPath(id)}/corrections`, edit),
  undo: (id: string, editId: number) =>
    send<CorrectedView>("POST", `${sessionPath(id)}/corrections/${editId}/annuler`),
  redo: (id: string, editId: number) =>
    send<CorrectedView>("POST", `${sessionPath(id)}/corrections/${editId}/retablir`),
  resetText: (id: string, turn: number) =>
    send<CorrectedView>("POST", `${sessionPath(id)}/repliques/${turn}/texte-d-origine`),
  setAttendees: (id: string, personIds: number[], unnamed: number | null) =>
    send<Session>("PUT", `${sessionPath(id)}/presents`, {
      person_ids: personIds,
      unnamed,
    }),
  provenance: (id: string, runId: string) =>
    getJson<Provenance>(
      `${sessionPath(id)}/executions/${encodeURIComponent(runId)}/provenance`,
    ),
  audioUrl: (id: string) => `${sessionPath(id)}/audio`,
  resume: (id: string, attendees?: number) =>
    send<Session>(
      "POST",
      `${sessionPath(id)}/reprendre`,
      attendees != null ? { presents: attendees } : {},
    ),

  spaces: () => getJson<Space[]>("/api/espaces"),
  createSpace: (name: string, template: SpaceTemplate) =>
    send<Space>("POST", "/api/espaces", { name, template }),
  spaceActions: (spaceId: number) => getJson<SpaceAction[]>(`/api/espaces/${spaceId}/actions`),
  setSpaceAction: (spaceId: number, ref: string, autoRun: boolean, model: string | null) =>
    send<SpaceAction[]>("PUT", `/api/espaces/${spaceId}/actions/${encodeURIComponent(ref)}`, {
      auto_run: autoRun,
      model,
    }),
  models: () => getJson<ModelsInfo>("/api/modeles"),
  setModel: (model: string) => send<ModelsInfo>("PUT", "/api/reglages/modele", { model }),
  actions: () => getJson<ActionInfo[]>("/api/actions"),
  generations: (id: string) => getJson<Generations>(`${sessionPath(id)}/resumes`),
  requestGeneration: (id: string, actionRef: string, model: string | null) =>
    send<Generations>("POST", `${sessionPath(id)}/resumes`, { action_ref: actionRef, model }),
  async generationPrompts(id: string, generationId: number): Promise<string> {
    const response = await fetch(`${sessionPath(id)}/resumes/${generationId}/prompts`);
    if (!response.ok) throw await readError(response);
    return response.text();
  },
  renameSession: (id: string, title: string) => send<Session>("PATCH", sessionPath(id), { title }),
  exportUrl: (id: string, contenu: "resume" | "transcript" | "tout", generationId?: number) =>
    `${sessionPath(id)}/export?contenu=${contenu}${generationId != null ? `&resume=${generationId}` : ""}`,
  updateSpace: (
    id: number,
    changes: Partial<Pick<Space, "name" | "voice_recognition" | "archived">>,
  ) => send<Space>("PATCH", `/api/espaces/${id}`, changes),
  people: (spaceId: number) =>
    getJson<Person[]>(`/api/espaces/${spaceId}/personnes`),
  addPerson: (
    spaceId: number,
    person: { name: string; kind: Person["kind"]; role?: string | null },
  ) => send<Person>("POST", `/api/espaces/${spaceId}/personnes`, person),
  updatePerson: (
    id: number,
    changes: Partial<Pick<Person, "name" | "role" | "kind" | "archived">>,
  ) => send<Person>("PATCH", `/api/personnes/${id}`, changes),
  glossary: (spaceId: number) =>
    getJson<GlossaryEntry[]>(`/api/espaces/${spaceId}/glossaire`),
  addEntry: (
    spaceId: number,
    entry: { term: string; category?: string | null; variants?: string[] },
  ) => send<GlossaryEntry>("POST", `/api/espaces/${spaceId}/glossaire`, entry),
  updateEntry: (
    id: number,
    changes: Partial<
      Pick<GlossaryEntry, "term" | "category" | "variants" | "archived">
    >,
  ) => send<GlossaryEntry>("PATCH", `/api/glossaire/${id}`, changes),

  /** Upload with progress: recordings of two hours weigh hundreds of megabytes. */
  importRecording(
    file: File,
    who: {
      spaceId: number | null;
      personIds: number[];
      unnamed: number | null;
    },
    onProgress: (fraction: number) => void,
  ): Promise<{ id: string }> {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      form.append("fichier", file, file.name);
      if (who.spaceId != null) form.append("espace", String(who.spaceId));
      for (const id of who.personIds) form.append("presents", String(id));
      if (who.unnamed != null) form.append("non_nommes", String(who.unnamed));
      form.append("date_fichier_ms", String(file.lastModified));
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/seances");
      xhr.responseType = "json";
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(e.loaded / e.total);
      };
      xhr.onload = () => {
        const body = xhr.response as { id?: string; detail?: unknown } | null;
        if (xhr.status === 201 && body?.id) resolve({ id: body.id });
        else
          reject(
            new ServiceError(
              typeof body?.detail === "string"
                ? body.detail
                : `L'import a échoué (réponse ${xhr.status}).`,
            ),
          );
      };
      xhr.onerror = () =>
        reject(new ServiceError("Le service Coulisses ne répond pas."));
      xhr.send(form);
    });
  },
};
