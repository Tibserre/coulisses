/** The local service (same origin, 127.0.0.1). Errors carry the service's French message. */

export type JobState = "queued" | "running" | "done" | "failed";

export interface Session {
  id: string;
  title: string | null;
  recorded_at: string;
  created_at: string;
  attendee_count: number | null;
  reference_source_id: string;
  duration_s: number | null;
  job_state: JobState | null;
  job_error: string | null;
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

/** Engine output (attributed-transcript.schema.json). Times in seconds, or null when
 *  not measured: never estimated (P2). */
export interface AttributedWord {
  text: string;
  start: number | null;
  end: number | null;
  confidence: number | null;
  speakers: string[];
  speaker: string | null;
  uncertain: boolean;
}

export interface Turn {
  speaker: string | null;
  first_word: number;
  end_word: number;
  start: number | null;
  end: number | null;
}

export interface UntranscribedSpan {
  start: number;
  end: number;
  reason: string;
}

export interface AttributedTranscript {
  run_id: string;
  reference_source: string;
  language: string;
  words: AttributedWord[];
  turns: Turn[];
  speakers: string[];
  untranscribed: UntranscribedSpan[];
}

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

async function getJson<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path);
  } catch {
    throw new ServiceError(
      "Le service Coulisses ne répond pas. Est-il lancé ?",
    );
  }
  if (!response.ok) throw await readError(response);
  return (await response.json()) as T;
}

export const api = {
  info: () => getJson<AppInfo>("/api/etat"),
  sessions: () => getJson<Session[]>("/api/seances"),
  session: (id: string) =>
    getJson<SessionDetail>(`/api/seances/${encodeURIComponent(id)}`),
  transcript: (id: string) =>
    getJson<AttributedTranscript>(
      `/api/seances/${encodeURIComponent(id)}/transcript`,
    ),
  provenance: (id: string, runId: string) =>
    getJson<Provenance>(
      `/api/seances/${encodeURIComponent(id)}/executions/${encodeURIComponent(runId)}/provenance`,
    ),
  audioUrl: (id: string) => `/api/seances/${encodeURIComponent(id)}/audio`,
  async resume(id: string): Promise<Session> {
    const response = await fetch(
      `/api/seances/${encodeURIComponent(id)}/reprendre`,
      {
        method: "POST",
      },
    );
    if (!response.ok) throw await readError(response);
    return (await response.json()) as Session;
  },
  /** Upload with progress: recordings of two hours weigh hundreds of megabytes. */
  importRecording(
    file: File,
    attendees: number | null,
    onProgress: (fraction: number) => void,
  ): Promise<{ id: string }> {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      form.append("fichier", file, file.name);
      if (attendees != null) form.append("presents", String(attendees));
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
