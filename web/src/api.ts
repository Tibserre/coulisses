/** The local service (same origin, 127.0.0.1). Errors carry the service's French message. */

export type JobState = "queued" | "running" | "done" | "failed";

export interface Session {
  id: string;
  title: string | null;
  /** Written by the user: a proposed title never replaces it. */
  title_edited: boolean;
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
  /** Kept, removed (when, why), or when its purge is due (spec §7.10). */
  audio: AudioStatus;
}

export interface AudioStatus {
  /** kept: « Garder l'audio » ; removed: gone ; never_processed: never purged until its
   *  processing succeeds ; scheduled: due on `purge_on` ; announced: the purge was
   *  announced and happens on `purge_on`. */
  state: "kept" | "removed" | "scheduled" | "announced" | "never_processed";
  purge_on: string | null;
  removed_at: string | null;
  removed_reason: "purge" | "audio_deletion" | null;
}

export interface RetentionSettings {
  retention_days: number;
  notice_days: number;
}

export interface PurgeAnnouncement {
  session_id: string;
  title: string | null;
  recorded_at: string;
  purge_on: string;
}

export interface DeletionLogEntry {
  id: number;
  at: string;
  kind: "purge" | "audio_deletion" | "session_deletion";
  session_id: string;
  /** None for a deleted session: nothing of its text is kept. */
  session_title: string | null;
  files: number;
  bytes: number;
  /** What could not be done: an incomplete deletion is said, never shown as done. */
  problems: string[];
}

export interface RetentionInfo {
  settings: RetentionSettings;
  /** Purges announced and not done yet. */
  coming: PurgeAnnouncement[];
  journal: DeletionLogEntry[];
  /** `name` only in developer mode; `made_on` reads « 7 octobre 2026 ». */
  backups: { name: string; made_on: string; bytes: number }[];
  problems: string[];
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
  /** A recording made in the application: being written, complete, or repaired after a
   *  crash. Null for an imported file. */
  capture_state: "recording" | "complete" | "recovered" | null;
  device: string | null;
}

export interface InputDevice {
  index: number;
  name: string;
  channels: number;
  default: boolean;
}

export type MarkerKind = "scene" | "discussion" | "key_moment";

/** Set while recording, at a recorded time (pauses left out). */
export interface Marker {
  id: number;
  kind: MarkerKind;
  at_s: number;
}

/** A note taken while recording, at the time its first letter was typed. */
export interface TimedNote {
  id: number;
  at_s: number;
  text: string;
}

export interface RecordingState {
  session_id: string;
  state: "recording" | "paused";
  /** Recorded so far, pauses left out. */
  elapsed_s: number;
  device: string;
  channels: number;
  levels: { peak_db: number; rms_db: number };
  too_quiet: boolean;
  clipping: boolean;
  /** Times the Mac could not keep up and lost some sound. */
  dropouts: number;
  error: string | null;
  markers: Marker[];
  notes: TimedNote[];
}

export interface StopResult {
  session_id: string;
  duration_s: number;
  processing: boolean;
  on_battery: boolean;
}

export interface RecordingRequest {
  espace: number | null;
  presents: number[];
  non_nommes: number | null;
  micro: number | null;
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
  /** The run of the version shown, which a rerun under way (or stopped) is making
   *  again: kept and still shown until the new version is complete. */
  stale: boolean;
}

export interface SessionDetail {
  session: Session;
  source: AudioSource | null;
  stages: StageView[];
  /** The « who said what » run of the version shown; null before the first one. */
  version: string | null;
  /** What the latest processing runs again; null for the first one. */
  rerun: Rerun | null;
}

export type Rerun = "transcribe" | "diarize";

export interface Version {
  run_id: string;
  /** 1 for the first processing, then in the order they were made. */
  number: number;
  finished_at: string | null;
  shown: boolean;
  origin: "first" | Rerun;
  min_voices: number | null;
  engine_version: string | null;
  /** Corrections in force on it. */
  corrections: number;
  /** When it replaced another version: corrections carried over, and not. */
  carried: number | null;
  not_carried: number | null;
}

export interface RerunFacts {
  possible: boolean;
  why_not: string | null;
  /** Measured computing time of the shown version's transcription. */
  transcribe_s: number | null;
  /** Measured computing time of its voice separation. */
  diarize_s: number | null;
  /** Glossary terms its transcription did not have. */
  glossary_added: string[];
  engine_updated: boolean;
  min_voices: number | null;
  attendees_now: number | null;
}

export interface Versions {
  /** Newest first. */
  versions: Version[];
  rerun: RerunFacts;
}

export interface NotCarried {
  edit_id: number;
  description: string;
  reason: string;
  at_s: number | null;
  /** For a text correction: the corrected text, to take back by hand. */
  text: string | null;
  /** Carried for some of its lines only; the reason says how many. */
  partial: boolean;
}

export interface Carryover {
  from_run_id: string;
  /** Carried over in full. */
  carried: number;
  /** Not carried, or only in part: to take back by hand. */
  not_carried: NotCarried[];
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
  /** How sure the transcription model was (engine `asr_confidence`); absent on older runs. */
  asr_confidence: number | null;
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

export type PhaseKind = "scene" | "discussion" | "other";

/** A chapter (a phase, in the service): from its first line to the next chapter's. */
export interface Phase {
  /** Index of its first line. */
  turn: number;
  /** Index of the first line after it (exclusive). */
  end_turn: number;
  start: number | null;
  end: number | null;
  kind: PhaseKind;
  title: string;
  edited: boolean;
  /** Cut by a play or discussion marker set while recording. */
  marked: boolean;
}

export interface PhasesStatus {
  state: "none" | "queued" | "running" | "failed" | "done";
  error: string | null;
  model: string | null;
  finished_at: string | null;
  /** What the model's answer said that had to be put right (developer mode). */
  adjustments: string[];
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
  /** When this version replaced another: what was carried over from it, and what not. */
  carryover: Carryover | null;
  word_count: number;
  timed_share: number;
  /** Empty until the chapters are detected (or the user cuts one). */
  phases: Phase[];
  /** The detection the chapters come from. */
  phases_run_id: string | null;
  /** Why the detected chapters could not be read, when they could not. */
  phases_problem: string | null;
  /** Set while recording: play, discussion, key moment. */
  markers: Marker[];
  /** Notes taken while recording. */
  timed_notes: TimedNote[];
  /** Detected cuts a marker replaced, in words (developer mode). */
  phases_by_markers: string[];
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
  | { kind: "edit_text"; turn: number; text: string }
  | { kind: "set_phase"; turn: number; phase_kind?: PhaseKind | null; title?: string | null }
  | { kind: "remove_phase"; turn: number };

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
  prompt: string;
  /** Shipped with the application (possibly modified). */
  provided: boolean;
  /** Its modified version is in force: the original is restorable. */
  modified: boolean;
  updated_at: string | null;
}

export interface ActionDraft {
  name: string;
  description: string;
  prompt: string;
}

export interface Note {
  text: string;
  updated_at: string;
}

export interface SpaceAction {
  action_ref: string;
  auto_run: boolean;
  model: string | null;
}

export type SpaceTemplate = "impro" | "reunion" | "vide";

export class ServiceError extends Error {
  /** The HTTP status, when the service answered: 409 for a correction meant for a version
   *  no longer shown. */
  readonly status: number | null;
  constructor(message: string, status: number | null = null) {
    super(message);
    this.status = status;
  }
}

async function readError(response: Response): Promise<ServiceError> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return new ServiceError(body.detail, response.status);
  } catch {
    // Not JSON: fall through to the generic message, which keeps the HTTP status.
  }
  return new ServiceError(
    `Le service a répondu ${response.status} ${response.statusText}.`,
    response.status,
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
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const getJson = <T>(path: string) => send<T>("GET", path);
const sessionPath = (id: string) => `/api/seances/${encodeURIComponent(id)}`;
const versionQuery = (version: string) => `?version=${encodeURIComponent(version)}`;

export const api = {
  info: () => getJson<AppInfo>("/api/etat"),
  sessions: () => getJson<Session[]>("/api/seances"),
  session: (id: string) => getJson<SessionDetail>(sessionPath(id)),
  transcript: (id: string) =>
    getJson<CorrectedView>(`${sessionPath(id)}/transcript`),
  // `version`: the « who said what » run the page shows. A correction meant for another
  // one is refused (409) rather than written on other lines.
  addEdit: (id: string, edit: EditRequest, version: string) =>
    send<CorrectedView>("POST", `${sessionPath(id)}/corrections${versionQuery(version)}`, edit),
  undo: (id: string, editId: number, version: string) =>
    send<CorrectedView>(
      "POST",
      `${sessionPath(id)}/corrections/${editId}/annuler${versionQuery(version)}`,
    ),
  redo: (id: string, editId: number, version: string) =>
    send<CorrectedView>(
      "POST",
      `${sessionPath(id)}/corrections/${editId}/retablir${versionQuery(version)}`,
    ),
  resetText: (id: string, turn: number, version: string) =>
    send<CorrectedView>(
      "POST",
      `${sessionPath(id)}/repliques/${turn}/texte-d-origine${versionQuery(version)}`,
    ),
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
  microphones: () => getJson<InputDevice[]>("/api/micros"),
  power: () => getJson<{ on_battery: boolean }>("/api/alimentation"),
  recording: () => getJson<RecordingState | null>("/api/enregistrement"),
  startRecording: (request: RecordingRequest) =>
    send<RecordingState>("POST", "/api/enregistrement", request),
  pauseRecording: () => send<RecordingState>("POST", "/api/enregistrement/pause"),
  resumeRecording: () => send<RecordingState>("POST", "/api/enregistrement/reprise"),
  stopRecording: () => send<StopResult>("POST", "/api/enregistrement/arret"),
  levelsUrl: "/api/enregistrement/niveaux",
  mark: (kind: MarkerKind, atS?: number) =>
    send<RecordingState>("POST", "/api/enregistrement/marqueurs", { kind, at_s: atS ?? null }),
  unmark: (id: number) => send<RecordingState>("POST", `/api/enregistrement/marqueurs/${id}/retirer`),
  addTimedNote: (text: string, atS: number) =>
    send<RecordingState>("POST", "/api/enregistrement/notes", { text, at_s: atS }),
  removeTimedNote: (id: number) =>
    send<RecordingState>("POST", `/api/enregistrement/notes/${id}/retirer`),
  processSession: (id: string) => send<Session>("POST", `${sessionPath(id)}/traiter`),
  versions: (id: string) => getJson<Versions>(`${sessionPath(id)}/versions`),
  retention: () => getJson<RetentionInfo>("/api/conservation"),
  setRetention: (settings: RetentionSettings) =>
    send<RetentionInfo>("PUT", "/api/conservation", settings),
  keepAudio: (id: string, keep: boolean) =>
    send<Session>("PUT", `${sessionPath(id)}/garder-audio`, { keep }),
  extendAudio: (id: string) => send<Session>("POST", `${sessionPath(id)}/prolonger`),
  /** `problems`: what stayed on the disk; the audio is gone from Coulisses anyway. */
  removeAudio: (id: string) =>
    send<{ session: Session; problems: string[] }>("POST", `${sessionPath(id)}/supprimer-audio`),
  /** `problems`: what stayed on the disk; the session is gone from Coulisses anyway. */
  deleteSession: (id: string) => send<{ problems: string[] }>("DELETE", sessionPath(id)),
  showVersion: (id: string, runId: string) =>
    send<Versions>("POST", `${sessionPath(id)}/versions/${encodeURIComponent(runId)}/afficher`),
  rerun: (id: string, stage: Rerun, attendees: number | null) =>
    send<Session>("POST", `${sessionPath(id)}/relancer`, { etape: stage, presents: attendees }),
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
  setOfferedAction: (spaceId: number, ref: string | null) =>
    send<SpaceAction[]>("PUT", `/api/espaces/${spaceId}/resume-propose`, { action_ref: ref }),
  models: () => getJson<ModelsInfo>("/api/modeles"),
  setModel: (model: string) => send<ModelsInfo>("PUT", "/api/reglages/modele", { model }),
  actions: () => getJson<ActionInfo[]>("/api/actions"),
  createAction: (draft: ActionDraft) => send<ActionInfo>("POST", "/api/actions", draft),
  updateAction: (ref: string, draft: ActionDraft) =>
    send<ActionInfo>("PUT", `/api/actions/${encodeURIComponent(ref)}`, draft),
  restoreAction: (ref: string) =>
    send<ActionInfo>("POST", `/api/actions/${encodeURIComponent(ref)}/restaurer`),
  duplicateAction: (ref: string) =>
    send<ActionInfo>("POST", `/api/actions/${encodeURIComponent(ref)}/dupliquer`),
  archiveAction: (ref: string) =>
    send<void>("POST", `/api/actions/${encodeURIComponent(ref)}/archiver`),
  notes: (id: string) => getJson<Note | null>(`${sessionPath(id)}/notes`),
  setNotes: (id: string, text: string) => send<Note>("PUT", `${sessionPath(id)}/notes`, { text }),
  generations: (id: string) => getJson<Generations>(`${sessionPath(id)}/resumes`),
  phases: (id: string) => getJson<PhasesStatus>(`${sessionPath(id)}/chapitres`),
  detectPhases: (id: string) => send<PhasesStatus>("POST", `${sessionPath(id)}/chapitres`),
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
