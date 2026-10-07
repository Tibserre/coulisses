/** The library's logic (spec §7.11, ADR 0030), kept apart from the components to be
 *  tested: the routes, the tree of the side column, the name and state of a session. */
import type { Project, Session, Space } from "./api.ts";
import { formatDay } from "./retention.ts";

export type Route =
  | { page: "home" }
  | { page: "session"; id: string; at: number | null; tab: "summary" | null }
  | { page: "space"; id: number }
  | { page: "actions"; ref: string | null }
  | { page: "recording" }
  | { page: "settings" };

/** `#/seance/<id>?t=12.5` opens a session at a measured time (a search hit). */
export function parseRoute(hash: string): Route {
  const [path, query = ""] = hash.split("?");
  const params = new URLSearchParams(query);
  const session = /^#\/seance\/([^/?#]+)/.exec(path);
  if (session) {
    const t = Number(params.get("t"));
    return {
      page: "session",
      id: decodeURIComponent(session[1]),
      at: params.has("t") && Number.isFinite(t) ? t : null,
      tab: params.get("onglet") === "resume" ? "summary" : null,
    };
  }
  const space = /^#\/espaces\/(\d+)/.exec(path);
  if (space) return { page: "space", id: Number(space[1]) };
  if (path.startsWith("#/enregistrement")) return { page: "recording" };
  if (path.startsWith("#/reglages")) return { page: "settings" };
  const actions = /^#\/actions(?:\/([^/?#]+))?/.exec(path);
  if (actions) return { page: "actions", ref: actions[1] ? decodeURIComponent(actions[1]) : null };
  return { page: "home" };
}

export function sessionHref(id: string, at?: number | null, tab?: "summary"): string {
  const query = at != null ? `?t=${Math.round(at * 10) / 10}` : tab === "summary" ? "?onglet=resume" : "";
  return `#/seance/${encodeURIComponent(id)}${query}`;
}

const HOUR = new Intl.DateTimeFormat("fr-FR", { hour: "numeric", minute: "2-digit" });

/** How a session is named: its title, else its day and hour (two sessions the same day
 *  are told apart). */
export function sessionName(s: Pick<Session, "title" | "recorded_at">, now: Date = new Date()): string {
  if (s.title) return s.title;
  const [h, m] = HOUR.format(new Date(s.recorded_at)).split(":");
  return `Séance du ${formatDay(s.recorded_at, now)}, ${Number(h)} h ${m}`;
}

export type SessionDot = "recording" | "processing" | "failed" | null;

/** The one mark a session carries in the side column, when something is going on. */
export function sessionDot(s: Pick<Session, "job_state" | "duration_s">, recording: string | null, id: string): SessionDot {
  if (recording === id) return "recording";
  if (s.job_state === "queued" || s.job_state === "running") return "processing";
  if (s.job_state === "failed") return "failed";
  return null;
}

export interface ProjectNode {
  project: Project;
  sessions: Session[];
}

export interface SpaceNode {
  space: Space;
  projects: ProjectNode[];
  /** Sessions in no project. */
  loose: Session[];
  archived: ProjectNode[];
}

const byDate = (a: Session, b: Session) => b.recorded_at.localeCompare(a.recorded_at) || b.id.localeCompare(a.id);
const byName = (a: ProjectNode, b: ProjectNode) =>
  a.project.name.localeCompare(b.project.name, "fr", { sensitivity: "base" });

/** The side column: each space (archived ones too, the column shows them apart), its
 *  projects (by name), then its sessions in no project; the most recent session first
 *  everywhere. */
export function buildTree(spaces: Space[], projects: Project[], sessions: Session[]): SpaceNode[] {
  return spaces.map((space) => {
      const own = sessions.filter((s) => s.space_id === space.id).sort(byDate);
      const nodes = projects
        .filter((p) => p.space_id === space.id)
        .map((project) => ({ project, sessions: own.filter((s) => s.project_id === project.id) }));
      const known = new Set(nodes.map((n) => n.project.id));
      return {
        space,
        projects: nodes.filter((n) => !n.project.archived).sort(byName),
        loose: own.filter((s) => s.project_id == null || !known.has(s.project_id)),
        archived: nodes.filter((n) => n.project.archived).sort(byName),
      };
    });
}

const CHANGED = "coulisses:bibliotheque";

/** Something the side column shows changed (a title, a project, a deletion): it reads the
 *  library again at once rather than at its next poll. */
export function libraryChanged(): void {
  window.dispatchEvent(new Event(CHANGED));
}

export function onLibraryChanged(listener: () => void): () => void {
  window.addEventListener(CHANGED, listener);
  return () => window.removeEventListener(CHANGED, listener);
}
