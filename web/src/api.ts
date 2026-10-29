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
  /** Its project in its space, or none. */
  project_id: number | null;
  /** People checked as present. */
  attendee_ids: number[];
  /** People present whom nobody named, in addition to the checked ones. */
  unnamed_attendees: number | null;
  /** Minimum of voices asked of the engine by the latest processing (P3). */
  min_voices: number | null;
  /** Whether the people present now are that minimum (false once checked after its voices
   *  were being separated, or when another number was chosen); null if never processed. */
  attendees_taken: boolean | null;
  reference_source_id: string;
  duration_s: number | null;
  job_state: JobState | null;
  job_error: string | null;
  /** Kept, removed (when, why), or when its purge is due (spec §7.10). */
  audio: AudioStatus;
}

export interface Project {
  id: number;
  space_id: number;
  name: string;
  archived: boolean;
}

export interface SearchPart {
  text: string;
  hit: boolean;
}

export interface SearchHit {
  kind: "title" | "turn" | "note" | "summary";
  /** The line's index, the note's id, the generation's id; empty for the title. */
  ref: string;
  at_s: number | null;
  excerpt: SearchPart[];
}

export interface SearchResults {
  query: string;
  sessions: { session_id: string; hits: SearchHit[] }[];
  /** Some hits are not shown: said, so that the search is made more precise. */
  more: boolean;
  problems: string[];
}

export interface ExportFolder {
  folder: string | null;
  /** There and writable (a disk unplugged, a Drive logged out: no). */
  present: boolean;
}

// -- the engine's models (engine schemas model-catalog, model-inventory, readiness; ADR 0036)

export type StageName =
  | "prepare" | "dereverb" | "transcribe" | "align" | "diarize" | "attribute"
  | "segment_phases" | "title" | "summarize";

/** model-catalog.schema.json: a model the engine can download. */
export interface CatalogModel {
  key: string;
  stage: StageName;
  /** The stage in French, as the catalog writes it. */
  role: string;
  description: string;
  /** Rounded; the exact size is asked when downloading. */
  announced_bytes: number;
  repo: string;
  revision: string;
  licence: string;
  /** Its terms must be accepted on this page before downloading. */
  terms_url: string | null;
  engine: string | null;
  /** The engine's profiles that need it (the retained chain: « chaine-retenue »). */
  required_by: string[];
  /** The model that does this one's job in the retained chain now (engine v1.10.0). */
  replaced_by: string | null;
  /** Why, in French, written by the engine for the user: shown as it is (engine v1.10.0). */
  replacement_note: string | null;
  /** For a replaced model, measured at the engine's bench (engine v1.11.0), null when not
   *  measured: how many times faster its successor is… */
  replacement_speedup?: number | null;
  /** …how right it is compared with this one (`same`: within the measure's noise)… */
  replacement_quality?: "same" | "better" | "worse" | null;
  /** …the peak memory it saves… */
  replacement_memory_saved_bytes?: number | null;
  /** …and where these figures come from (developer mode). */
  replacement_evidence?: string | null;
}

/** model-inventory.schema.json */
export interface InstalledEngineModel {
  key: string;
  /** altered: files missing or of another size; no_manifest: a folder Coulisses did not install. */
  state: "intact" | "altered" | "no_manifest";
  in_catalog: boolean;
  repo: string | null;
  revision: string | null;
  /** Its revision is not the one the catalog pins now. */
  outdated: boolean;
  size_bytes: number;
  downloaded_at: string | null;
  problem: string | null;
  /** A profile of the engine needs it. */
  required: boolean;
  /** Installed, no longer needed, replaced by this model: it only takes space (engine
   *  v1.10.0). Its removal is offered, the user decides (P8). */
  replaced_by: string | null;
}

export interface PartialDownload {
  key: string;
  size_bytes: number;
}

export interface EnvironmentInfo {
  name: string;
  path: string;
  /** Built for this engine version; an old one only takes space. */
  current: boolean;
  /** Usable (an interrupted install is not). */
  installed: boolean;
  size_bytes: number;
  /** The Python it runs (engine v1.7.0), null if absent. */
  interpreter: string | null;
  /** Its Python lives outside the engine's folder (installed before v1.7.0, usually in
   *  ~/.local/share/uv): it works as long as that one stays, and is not counted. */
  interpreter_outside: boolean;
  /** What it is for, in French, said by the engine (v1.9.0): shown as it is. */
  label: string;
  /** The stages of the retained chain that run in it (engine v1.9.0). */
  stages: StageName[];
}

/** uv's Python interpreters, or its download cache, for the environments (engine v1.7.0). */
export interface UvStore {
  kind: "python" | "cache";
  path: string;
  size_bytes: number;
}

export interface Inventory {
  models_dir: string;
  envs_dir: string;
  models: InstalledEngineModel[];
  partial_downloads: PartialDownload[];
  environments: EnvironmentInfo[];
  /** Counted in `total_bytes`, except the cache (its files are cloned into the environments). */
  uv_stores: UvStore[];
  total_bytes: number;
}

/** readiness.schema.json: what a chain lacks to run. */
export interface MissingPiece {
  code: "model_missing" | "model_altered" | "environment_missing";
  stage: StageName;
  model: string | null;
  environment: string | null;
  /** For a missing environment: what it is for, in French, said by the engine (v1.9.0). */
  label: string | null;
  message: string;
}

export interface Readiness {
  profile: string;
  ready: boolean;
  missing: MissingPiece[];
}

/** A download or an install, running or just over (said by the service, in French). Not a
 *  `job`: those are a session's. */
export interface ModelAction {
  kind: "model" | "environment";
  name: string;
  state: "running" | "done" | "failed" | "cancelled";
  done_bytes: number;
  /** Null while unknown (an environment's install never knows it). */
  total_bytes: number | null;
  error: string | null;
  code: string | null;
  /** The engine's own message (developer mode). */
  detail: string | null;
  terms_url: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface ModelsView {
  catalog: { models: CatalogModel[] };
  inventory: Inventory;
  readiness: Readiness;
  actions: ModelAction[];
}

/** What can be shown in the Finder from the settings. */
export interface Folders {
  data: string;
  models: string;
  /** Null until the app in the Dock has started the service once. */
  log: string | null;
}

/** The folders' names in the address that opens them. */
export type FolderName = "donnees" | "modeles" | "journal";

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
  /** `conversion`: WAV tracks removed once kept in FLAC, without loss (ADR 0046); `bytes`
   *  is then the room freed. `backup_pruning`: older copies of the database removed, only
   *  the three latest kept (ADR 0052). */
  kind: "purge" | "audio_deletion" | "session_deletion" | "conversion" | "backup_pruning";
  /** None for `backup_pruning` only: a copy of the database is no session's. */
  session_id: string | null;
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

/** What the mix of the microphone and the computer's sound was made of. */
export interface MixFacts {
  gain: number;
  sha256: string;
  /** The computer's sound held nothing at all (the permission, most likely). */
  system_silent: boolean;
  made_at: string;
  /** The mix heard on the session's page (the microphone turned down while nobody speaks
   *  into it); null while it is being made, for a mix made before it existed. */
  listening_mix: { gain: number; sha256: string } | null;
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
  /** `ref`: what the main microphone's cut is asked by. */
  source_id: string;
  channels: number;
  levels: { peak_db: number; rms_db: number };
  /** The main microphone, cut by the user for now: silence is written in its place. */
  muted: boolean;
  /** When it was cut and back, in recorded time, while recording only. */
  cuts: Cut[];
  too_quiet: boolean;
  clipping: boolean;
  /** Times the Mac could not keep up and lost some sound. */
  dropouts: number;
  error: string | null;
  markers: Marker[];
  notes: TimedNote[];
  /** The microphones added, recording at the same time, each with its own alerts. */
  extra: TrackState[];
  /** The microphones added then taken away: their files end there, kept (ADR 0067). */
  removed: TrackState[];
  /** The computer's sound, recorded with the microphone (a meeting online or hybrid).
   *  Silence is normal there: `too_quiet` only says it has been silent for a while. */
  system: TrackState | null;
  /** Recorded time since a voice was last heard (pauses left out). */
  silent_for_s: number;
  /** What to ask now (a long silence, a long recording), shown once by the app in the
   *  Dock (ADR 0054); never a stop by itself. */
  alert: RecordingAlert | null;
}

export interface RecordingAlert {
  key: string;
  title: string;
  text: string;
}

/** After how long a recording reminds the user (ADR 0054), in minutes. */
export interface Reminders {
  silence_min: number;
  duration_min: number;
}

/** A track cut by the user (silence written in its place), in recorded time. */
export interface Cut {
  from_s: number;
  /** Null while it lasts. */
  to_s: number | null;
}

export interface TrackState {
  device: string;
  /** `mic2`, `mic3`… or `system`: what its cut is asked by. */
  source_id: string;
  cuts: Cut[];
  /** When it was first heard, measured on the main microphone: 0 from the start. */
  started_at_s: number;
  /** When it was taken away, measured; null while it records. */
  removed_at_s: number | null;
  levels: { peak_db: number; rms_db: number };
  too_quiet: boolean;
  clipping: boolean;
  dropouts: number;
  error: string | null;
  /** Cut by the user for now: silence is written in its place. */
  muted: boolean;
}

export interface StopResult {
  session_id: string;
  duration_s: number;
  processing: boolean;
  on_battery: boolean;
  /** A second track's file (microphone, computer's sound) could not be read back. */
  second_problem: string | null;
}

export interface RecordingRequest {
  espace: number | null;
  projet: number | null;
  /** Microphones added, recording at the same time (often an iPhone), each its file. */
  micros_en_plus: number[];
  /** The computer's sound too: a meeting online or hybrid. */
  son_ordinateur: boolean;
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
    /** Which phase of the stage, from 1, out of `steps` (engine v1.13.0 on; absent
     *  before). `steps` may grow while the stage runs, never shrink. */
    step?: number | null;
    steps?: number | null;
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

/** While a session is processed (ADR 0058): the text once transcribed, before anyone is
 *  told apart, with what was marked during the recording. */
export interface Preview {
  lines: { start: number | null; text: string }[];
  aligned: boolean;
  markers: Marker[];
  notes: TimedNote[];
}

export interface SessionDetail {
  session: Session;
  source: AudioSource | null;
  stages: StageView[];
  /** The « who said what » run of the version shown; null before the first one. */
  version: string | null;
  /** What the latest processing runs again; null for the first one. */
  rerun: Rerun | null;
  /** A second microphone's track, kept beside the reference (not processed yet). */
  other_sources: AudioSource[];
  /** The microphone mixed with the computer's sound, once made. */
  mix: MixFacts | null;
}

/** transcribe: the text (transcription, alignment); diarize: the voices; all: both, from
 *  the audio. */
export type Rerun = "transcribe" | "diarize" | "all";

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
  /** The service's process (the app in the Dock takes back one left running alone). */
  pid: number;
  engine_version: string;
  /** The last published version. */
  app_version: string;
  /** Which code runs: `v` + the version, or `git describe` between two (ADR 0064). */
  app_build: string;
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
  /** While running: how far the detection is (ADR 0061); null before its first step. */
  progress?: PhasesSteps | null;
  /** While running: why its progress cannot be read (not a failure: it goes on). */
  progress_problem?: string | null;
  /** While running: the chapters so far, placed like the final ones. They may still change
   *  (the last one may go on until `read_until`, a kind when checked): never edited. */
  provisional?: Phase[];
}

export interface PhasesSteps {
  step: "reading" | "checking" | "done";
  /** Parts read so far, out of `parts`. */
  part: number;
  parts: number;
  /** Measured time of the last line read: beyond it, nothing is known yet. */
  read_until: number | null;
  checked: number;
  to_check: number;
  /** Why the chapters so far cannot be shown at this step. */
  problem: string | null;
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
  /** Unnamed, in a space that recognises voices: whose voice it seems to be (ADR 0057).
   *  Only a proposal: naming the voice confirms it. */
  proposal?: VoiceProposal | null;
}

export interface VoiceProposal {
  person_id: number;
  name: string;
  color_slot: number;
  /** Cosine distance to the person's voice profile: developer mode only. */
  distance: number;
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
  /** Why some voices could not be compared from one session to the next (P8). */
  voices_problem?: string | null;
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
  | { kind: "remove_phase"; turn: number }
  | { kind: "reject_voice_match"; speaker: string; person_id: number };

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
  /** A version brought back (« Revenir à la version d'avant »). */
  restored: boolean;
  /** The latest of its summary, made again: the version before can come back, once. */
  restorable: boolean;
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

/** What a language model writes: a title, chapters, summaries (ADR 0039). */
export type Writing = "titre" | "chapitres" | "resume";

/** The language model advised to this Mac by its memory (lot 11g of the plan). */
export interface WritingAdvice {
  /** null: the Mac's memory could not be read. */
  memory_gb: number | null;
  /** null: none advised for this Mac yet (not measured on real sessions). */
  model: string | null;
  installed: boolean;
  /** Under it, writing may run out of memory. */
  minimum_gb: number;
}

export interface ModelsInfo {
  reachable: boolean;
  error: string | null;
  /** The summaries' model, offered first when a summary is asked. */
  default: string;
  /** The model of each writing. */
  writings: Record<Writing, string>;
  models: InstalledModel[];
  advice: WritingAdvice;
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
  /** Sent as the page goes away (closed, reloaded): the browser finishes it anyway. */
  keepalive = false,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      keepalive,
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
  preview: (id: string) => getJson<Preview>(`${sessionPath(id)}/apercu`),
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
  /** Cut the computer's sound for now (true), or bring it back (false). */
  muteSystem: (cut: boolean) =>
    send<RecordingState>("POST", "/api/enregistrement/son-ordinateur", { coupe: cut }),
  /** One track cut for now (true) or back (false): `ref`, `mic2`…, `system` (ADR 0067). */
  muteTrack: (sourceId: string, cut: boolean) =>
    send<RecordingState>(
      "POST",
      `/api/enregistrement/pistes/${encodeURIComponent(sourceId)}/coupe`,
      { coupe: cut },
    ),
  /** Every microphone cut or back at once; the computer's sound keeps its own. */
  muteMicrophones: (cut: boolean) =>
    send<RecordingState>("POST", "/api/enregistrement/micros/coupe", { coupe: cut }),
  /** A microphone added, taken away while recording: its file ends there, kept with the
   *  session; the main one and the computer's sound are cut, not taken away (ADR 0067). */
  removeMicrophone: (sourceId: string) =>
    send<RecordingState>(
      "POST",
      `/api/enregistrement/pistes/${encodeURIComponent(sourceId)}/retirer`,
    ),
  /** A microphone added while recording: it records from now on. */
  addMicrophone: (index: number) =>
    send<RecordingState>("POST", "/api/enregistrement/micros", { micro: index }),
  /** Into another space, while nothing is processed yet; its people there are unchecked. */
  moveSession: (id: string, spaceId: number) =>
    send<{ session: Session; unchecked: string[] }>("PUT", `${sessionPath(id)}/espace`, {
      espace: spaceId,
    }),
  resumeRecording: () => send<RecordingState>("POST", "/api/enregistrement/reprise"),
  stopRecording: () => send<StopResult>("POST", "/api/enregistrement/arret"),
  /** Paused at once, stopped a moment later unless resumed (ADR 0058). */
  stopRecordingSoon: () =>
    send<{ state: RecordingState; delay_s: number }>("POST", "/api/enregistrement/arret-differe"),
  /** The stop taken back, the recording left paused (it was paused before « Arrêter »). */
  cancelStop: () => send<RecordingState>("POST", "/api/enregistrement/arret-annule"),
  /** How the last stop went: still under way, done (where to go), or failed. */
  lastStop: () =>
    getJson<{ pending: boolean; stopped: StopResult | null; error: string | null }>(
      "/api/enregistrement/arret",
    ),
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
  reminders: () => getJson<Reminders>("/api/reglages/rappels"),
  setReminders: (reminders: Reminders) =>
    send<Reminders>("PUT", "/api/reglages/rappels", reminders),
  folders: () => getJson<Folders>("/api/dossiers"),
  engineModels: () => getJson<ModelsView>("/api/moteur/modeles"),
  modelActions: () => getJson<ModelAction[]>("/api/moteur/telechargements"),
  downloadModel: (key: string) =>
    send<ModelAction>("POST", `/api/moteur/modeles/${encodeURIComponent(key)}/telecharger`),
  installEnvironment: (name: string) =>
    send<ModelAction>("POST", `/api/moteur/environnements/${encodeURIComponent(name)}/installer`),
  cancelModelAction: (kind: ModelAction["kind"], name: string) =>
    send<void>("POST", `/api/moteur/${kind === "model" ? "modeles" : "environnements"}/${encodeURIComponent(name)}/annuler`),
  forgetModelAction: (kind: ModelAction["kind"], name: string) =>
    send<void>("DELETE", `/api/moteur/${kind === "model" ? "modeles" : "environnements"}/${encodeURIComponent(name)}/telechargement`),
  removeModel: (key: string) => send<void>("DELETE", `/api/moteur/modeles/${encodeURIComponent(key)}`),
  /** An environment the processing does not use (an older one, or interrupted). */
  removeEnvironment: (path: string) => send<void>("POST", "/api/moteur/environnements/retirer", { chemin: path }),
  /** The requested steps the user asked not to be reminded of (ADR 0049). */
  dismissedSteps: () => getJson<string[]>("/api/gestes-ecartes"),
  dismissSteps: (ids: string[]) => send<string[]>("POST", "/api/gestes-ecartes", { gestes: ids }),
  openFolder: (which: FolderName) => send<void>("POST", `/api/dossiers/${which}/ouvrir`),
  projects: () => getJson<Project[]>("/api/projets"),
  createProject: (spaceId: number, name: string) =>
    send<Project>("POST", `/api/espaces/${spaceId}/projets`, { name }),
  updateProject: (id: number, changes: { name?: string; archived?: boolean }) =>
    send<Project>("PATCH", `/api/projets/${id}`, changes),
  setSessionProject: (id: string, projectId: number | null) =>
    send<Session>("PUT", `${sessionPath(id)}/projet`, { projet: projectId }),
  search: (query: string) =>
    getJson<SearchResults>(`/api/recherche?q=${encodeURIComponent(query)}`),
  exportFolder: () => getJson<ExportFolder>("/api/export"),
  setExportFolder: (folder: string | null) =>
    send<ExportFolder>("PUT", "/api/export", { dossier: folder }),
  /** Opens the Finder's own window on the Mac; resolves once chosen or cancelled. */
  chooseExportFolder: () => send<ExportFolder>("POST", "/api/export/choisir"),
  exportToFolder: (
    id: string,
    content: "resume" | "transcript" | "tout",
    generationId: number | null,
    replace: boolean,
  ) =>
    send<{ fichier: string; resume: string | null }>("POST", `${sessionPath(id)}/exporter-dossier`, {
      contenu: content,
      resume: generationId,
      remplacer: replace,
    }),
  setRetention: (settings: RetentionSettings, leaving = false) =>
    send<RetentionInfo>("PUT", "/api/conservation", settings, leaving),
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
  setWritingModel: (writing: Writing, model: string) =>
    send<ModelsInfo>("PUT", `/api/reglages/modeles/${writing}`, { model }),
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
  /** « Revenir à la version d'avant »: the summary before the latest one, shown again. */
  restoreGeneration: (id: string, generationId: number) =>
    send<Generations>("POST", `${sessionPath(id)}/resumes/${generationId}/revenir`),
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
      projectId: number | null;
      personIds: number[];
      unnamed: number | null;
    },
    onProgress: (fraction: number) => void,
  ): Promise<{ id: string }> {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      form.append("fichier", file, file.name);
      if (who.spaceId != null) form.append("espace", String(who.spaceId));
      if (who.projectId != null) form.append("projet", String(who.projectId));
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
