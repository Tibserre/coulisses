import { useRef, useState, type DragEvent, type ReactNode } from "react";
import { IconButton } from "@astryxdesign/core/IconButton";
import { MoreMenu } from "@astryxdesign/core/MoreMenu";
import {
  ChevronDown,
  ChevronRight,
  Folder,
  House,
  ListChecks,
  Plus,
  Settings,
} from "lucide-react";
import { api, type Session } from "../api.ts";
import {
  sessionDot,
  sessionHref,
  sessionName,
  shortDay,
  visibleSessions,
  type ProjectNode,
  type SpaceNode,
} from "../library.ts";

const FOLDED_KEY = "coulisses.repli";
const DRAG_TYPE = "application/x-coulisses-seance";

function readFolded(): Set<string> {
  try {
    return new Set(
      JSON.parse(window.localStorage.getItem(FOLDED_KEY) ?? "[]") as string[],
    );
  } catch {
    return new Set(); // storage blocked or unreadable: everything open
  }
}

/** The side column (ADR 0030): the spaces, each with its projects and its sessions, the
 *  most recent first; a click opens a session beside it. A session is dragged onto a
 *  project (or onto its space: no project) to move it. Folding is remembered per browser. */
export function Sidebar({
  tree,
  archived,
  recordingId,
  stepsLeft = 0,
  current,
  onNewSession,
  onNewSpace,
  onChanged,
  onError,
}: {
  tree: SpaceNode[];
  /** Archived spaces: shown apart, folded, their sessions still there. */
  archived: SpaceNode[];
  recordingId: string | null;
  /** Steps an update asks on this Mac, not dismissed (ADR 0049): a dot on « Réglages ». */
  stepsLeft?: number;
  /** What the main pane shows: a session, or a space's settings. */
  current: { sessionId: string | null; spaceId: number | null; page: string };
  onNewSession: (spaceId: number, projectId: number | null) => void;
  onNewSpace: () => void;
  onChanged: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const [folded, setFolded] = useState<Set<string>>(readFolded);
  const [creatingIn, setCreatingIn] = useState<number | null>(null);
  const [renaming, setRenaming] = useState<number | null>(null);

  const toggle = (key: string) =>
    setFolded((before) => {
      const next = new Set(before);
      if (!next.delete(key)) next.add(key);
      try {
        window.localStorage.setItem(FOLDED_KEY, JSON.stringify([...next]));
      } catch {
        // Storage blocked: folded for this page only.
      }
      return next;
    });

  const act = async (action: () => Promise<unknown>) => {
    try {
      await action();
      await onChanged();
    } catch (e) {
      onError((e as Error).message);
    }
  };

  const move = (e: DragEvent, spaceId: number, projectId: number | null) => {
    e.preventDefault();
    const raw = e.dataTransfer.getData(DRAG_TYPE);
    if (!raw) return;
    const { id, space } = JSON.parse(raw) as { id: string; space: number };
    if (space !== spaceId)
      return onError(
        "Une séance reste dans son espace : on la range dans un de ses projets.",
      );
    void act(() => api.setSessionProject(id, projectId));
  };

  return (
    <nav className="cl-sidebar" aria-label="Espaces et séances">
      <a
        className="cl-sidebar__link"
        href="#/"
        aria-current={current.page === "home" ? "page" : undefined}
      >
        <House size={16} strokeWidth={1.75} aria-hidden /> Accueil
      </a>
      <div className="cl-sidebar__heading">
        <span>Espaces</span>
        <IconButton
          label="Nouvel espace"
          icon={<Plus size={14} strokeWidth={1.75} />}
          variant="ghost"
          size="sm"
          onClick={onNewSpace}
        />
      </div>
      <ul className="cl-tree">
        {tree.map((node) => {
          const key = `e:${node.space.id}`;
          const open = !folded.has(key);
          return (
            <li key={key}>
              <Row
                level={0}
                strong
                open={open}
                onToggle={() => toggle(key)}
                label={node.space.name}
                isCurrent={
                  current.page === "space" && current.spaceId === node.space.id
                }
                onDrop={(e) => move(e, node.space.id, null)}
                actions={
                  <>
                    <IconButton
                      label={`Nouvelle séance dans ${node.space.name}`}
                      icon={<Plus size={14} strokeWidth={1.75} />}
                      variant="ghost"
                      size="sm"
                      onClick={() => onNewSession(node.space.id, null)}
                    />
                    <MoreMenu
                      label={`Options de ${node.space.name}`}
                      size="sm"
                      alignment="end"
                      items={[
                        {
                          label: "Nouveau projet",
                          onClick: () => setCreatingIn(node.space.id),
                        },
                        {
                          label: "Paramètres de l'espace",
                          onClick: () =>
                            (window.location.hash = `#/espaces/${node.space.id}`),
                        },
                        { type: "divider" as const },
                        {
                          label: "Archiver l'espace",
                          onClick: () =>
                            void act(() =>
                              api.updateSpace(node.space.id, {
                                archived: true,
                              }),
                            ),
                        },
                      ]}
                    />
                  </>
                }
              />
              {open && (
                <ul>
                  {creatingIn === node.space.id && (
                    <li>
                      <InlineName
                        placeholder="Nom du projet"
                        onDone={(name) => {
                          setCreatingIn(null);
                          if (name)
                            void act(() =>
                              api.createProject(node.space.id, name),
                            );
                        }}
                      />
                    </li>
                  )}
                  {node.projects.map((p) => (
                    <ProjectRow
                      key={p.project.id}
                      node={p}
                      folded={folded}
                      toggle={toggle}
                      renaming={renaming === p.project.id}
                      onRename={(name) => {
                        setRenaming(null);
                        if (name && name !== p.project.name)
                          void act(() =>
                            api.updateProject(p.project.id, { name }),
                          );
                      }}
                      menu={[
                        {
                          label: "Nouvelle séance dans ce projet",
                          onClick: () =>
                            onNewSession(node.space.id, p.project.id),
                        },
                        {
                          label: "Renommer",
                          onClick: () => setRenaming(p.project.id),
                        },
                        {
                          label: "Archiver le projet",
                          onClick: () =>
                            void act(() =>
                              api.updateProject(p.project.id, {
                                archived: true,
                              }),
                            ),
                        },
                      ]}
                      onDrop={(e) => move(e, node.space.id, p.project.id)}
                      recordingId={recordingId}
                      currentId={current.sessionId}
                    />
                  ))}
                  <SessionRows
                    sessions={node.loose}
                    level={1}
                    recordingId={recordingId}
                    currentId={current.sessionId}
                  />
                  {node.projects.length === 0 &&
                    node.loose.length === 0 &&
                    creatingIn !== node.space.id && (
                      <li className="cl-tree__empty">Aucune séance</li>
                    )}
                  {node.archived.length > 0 && (
                    <li>
                      <Row
                        level={1}
                        muted
                        open={folded.has(`a:${node.space.id}`) /* archived: closed unless opened */}
                        onToggle={() => toggle(`a:${node.space.id}`)}
                        label={`Projets archivés (${node.archived.length})`}
                      />
                      {folded.has(`a:${node.space.id}`) && (
                        <ul>
                          {node.archived.map((p) => (
                            <ProjectRow
                              key={p.project.id}
                              node={p}
                              folded={folded}
                              toggle={toggle}
                              renaming={false}
                              onRename={() => undefined}
                              menu={[
                                {
                                  label: "Désarchiver le projet",
                                  onClick: () =>
                                    void act(() =>
                                      api.updateProject(p.project.id, {
                                        archived: false,
                                      }),
                                    ),
                                },
                              ]}
                              recordingId={recordingId}
                              currentId={current.sessionId}
                              muted
                            />
                          ))}
                        </ul>
                      )}
                    </li>
                  )}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
      {archived.length > 0 && (
        <details className="cl-sidebar__archived">
          <summary>Espaces archivés ({archived.length})</summary>
          <ul className="cl-tree">
            {archived.map((node) => (
              <li key={node.space.id}>
                <div className="cl-tree__row" data-level={0} data-muted>
                  <a className="cl-tree__label" href={`#/espaces/${node.space.id}`}>
                    {node.space.name}
                  </a>
                  <span className="cl-tree__actions">
                    <MoreMenu
                      label={`Options de ${node.space.name}`}
                      size="sm"
                      alignment="end"
                      items={[
                        {
                          label: "Désarchiver l'espace",
                          onClick: () => void act(() => api.updateSpace(node.space.id, { archived: false })),
                        },
                      ]}
                    />
                  </span>
                </div>
                <ul>
                  {[...node.projects, ...node.archived]
                    .flatMap((p) => p.sessions)
                    .concat(node.loose)
                    .map((s) => (
                      <SessionRow key={s.id} session={s} level={1} recordingId={recordingId} currentId={current.sessionId} />
                    ))}
                </ul>
              </li>
            ))}
          </ul>
        </details>
      )}
      <div className="cl-sidebar__bottom">
        <a
          className="cl-sidebar__link"
          href="#/actions"
          aria-current={current.page === "actions" ? "page" : undefined}
        >
          <ListChecks size={16} strokeWidth={1.75} aria-hidden /> Actions de résumé
        </a>
        <a
          className="cl-sidebar__link"
          href="#/reglages"
          aria-current={current.page === "settings" ? "page" : undefined}
        >
          <Settings size={16} strokeWidth={1.75} aria-hidden /> Réglages
          {stepsLeft > 0 && (
            <span
              className="cl-tree__dot cl-sidebar__dot"
              data-dot="steps"
              title="Une mise à jour demande un geste sur ce Mac"
              aria-label="Une mise à jour demande un geste sur ce Mac"
            />
          )}
        </a>
      </div>
    </nav>
  );
}

function Row({
  level,
  label,
  open,
  onToggle,
  actions,
  strong,
  muted,
  isCurrent,
  onDrop,
  icon,
  count,
}: {
  level: number;
  label: string;
  open: boolean;
  onToggle: () => void;
  actions?: ReactNode;
  strong?: boolean;
  muted?: boolean;
  isCurrent?: boolean;
  onDrop?: (e: DragEvent) => void;
  icon?: ReactNode;
  count?: number;
}) {
  const [over, setOver] = useState(false);
  return (
    <div
      className="cl-tree__row"
      data-level={level}
      data-strong={strong || undefined}
      data-muted={muted || undefined}
      data-current={isCurrent || undefined}
      data-drop={over || undefined}
      onDragOver={
        onDrop
          ? (e) => {
              if (!e.dataTransfer.types.includes(DRAG_TYPE)) return;
              e.preventDefault();
              setOver(true);
            }
          : undefined
      }
      onDragLeave={() => setOver(false)}
      onDrop={
        onDrop
          ? (e) => {
              setOver(false);
              onDrop(e);
            }
          : undefined
      }
    >
      <button
        type="button"
        className="cl-tree__toggle"
        onClick={onToggle}
        aria-expanded={open}
      >
        {open ? (
          <ChevronDown size={14} strokeWidth={1.75} aria-hidden />
        ) : (
          <ChevronRight size={14} strokeWidth={1.75} aria-hidden />
        )}
        {icon}
        <span className="cl-tree__label">{label}</span>
        {count != null && <span className="cl-tree__count">{count}</span>}
      </button>
      {actions && <span className="cl-tree__actions">{actions}</span>}
    </div>
  );
}

function ProjectRow({
  node,
  folded,
  toggle,
  renaming,
  onRename,
  menu,
  onDrop,
  recordingId,
  currentId,
  muted,
}: {
  node: ProjectNode;
  folded: Set<string>;
  toggle: (key: string) => void;
  renaming: boolean;
  onRename: (name: string | null) => void;
  menu: { label: string; description?: string; onClick: () => void }[];
  onDrop?: (e: DragEvent) => void;
  recordingId: string | null;
  currentId: string | null;
  muted?: boolean;
}) {
  const key = `p:${node.project.id}`;
  const open = !folded.has(key);
  return (
    <li>
      {renaming ? (
        <InlineName
          initial={node.project.name}
          placeholder="Nom du projet"
          onDone={onRename}
        />
      ) : (
        <Row
          level={1}
          muted={muted}
          open={open}
          onToggle={() => toggle(key)}
          icon={<Folder size={14} strokeWidth={1.75} aria-hidden />}
          label={node.project.name}
          count={node.sessions.length}
          onDrop={onDrop}
          actions={
            <MoreMenu
              label={`Options de ${node.project.name}`}
              size="sm"
              alignment="end"
              items={menu}
            />
          }
        />
      )}
      {open && node.sessions.length > 0 && (
        <ul>
          <SessionRows
            sessions={node.sessions}
            level={2}
            recordingId={recordingId}
            currentId={currentId}
          />
        </ul>
      )}
    </li>
  );
}

/** At first, the latest sessions of a group; the others on demand (none hidden). The one
 *  open or recording is always among those shown. */
const SHOWN_SESSIONS = 5;

function SessionRows({
  sessions,
  level,
  recordingId,
  currentId,
}: {
  sessions: Session[];
  level: number;
  recordingId: string | null;
  currentId: string | null;
}) {
  const [all, setAll] = useState(false);
  const pinned = (s: Session) =>
    s.id === currentId || sessionDot(s, recordingId, s.id) !== null;
  const shown = all ? sessions : visibleSessions(sessions, SHOWN_SESSIONS, pinned);
  const more = sessions.length - shown.length;
  return (
    <>
      {shown.map((s) => (
        <SessionRow key={s.id} session={s} level={level} recordingId={recordingId} currentId={currentId} />
      ))}
      {(more > 0 || all) && sessions.length > SHOWN_SESSIONS && (
        <li>
          <button
            type="button"
            className="cl-tree__row cl-tree__more"
            data-level={level}
            aria-expanded={all}
            onClick={() => setAll(!all)}
          >
            {all ? "Moins" : `Voir ${more === 1 ? "l'autre séance" : `les ${more} autres`}`}
          </button>
        </li>
      )}
    </>
  );
}

const DOT_LABEL = {
  recording: "En cours d'enregistrement",
  processing: "En traitement",
  failed: "Traitement en échec",
} as const;

function SessionRow({
  session,
  level,
  recordingId,
  currentId,
}: {
  session: Session;
  level: number;
  recordingId: string | null;
  currentId: string | null;
}) {
  const dot = sessionDot(session, recordingId, session.id);
  return (
    <li>
      <a
        className="cl-tree__row cl-tree__session"
        data-level={level}
        href={
          session.id === recordingId
            ? "#/enregistrement"
            : sessionHref(session.id)
        }
        aria-current={session.id === currentId ? "page" : undefined}
        draggable
        onDragStart={(e) => {
          e.dataTransfer.setData(
            DRAG_TYPE,
            JSON.stringify({ id: session.id, space: session.space_id }),
          );
          e.dataTransfer.effectAllowed = "move";
        }}
      >
        <span className="cl-tree__label">{sessionName(session)}</span>
        {/* A title says what, not when: its day beside it (an untitled one has it). */}
        {session.title && <span className="cl-tree__date">{shortDay(session.recorded_at)}</span>}
        {dot && (
          <span
            className="cl-tree__dot"
            data-dot={dot}
            title={DOT_LABEL[dot]}
            aria-label={DOT_LABEL[dot]}
          />
        )}
      </a>
    </li>
  );
}

/** A name typed in place (a new project, a renamed one): Enter keeps it, Escape or leaving
 *  it empty gives up. */
function InlineName({
  initial = "",
  placeholder,
  onDone,
}: {
  initial?: string;
  placeholder: string;
  onDone: (name: string | null) => void;
}) {
  const [value, setValue] = useState(initial);
  const done = useRef(false);
  const finish = (name: string | null) => {
    if (done.current) return; // Enter, then the blur of the field going away
    done.current = true;
    onDone(name);
  };
  return (
    <input
      className="cl-tree__input"
      autoFocus
      value={value}
      placeholder={placeholder}
      aria-label={placeholder}
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => finish(value.trim() || null)}
      onKeyDown={(e) => {
        if (e.key === "Enter") finish(value.trim() || null);
        else if (e.key === "Escape") finish(null);
      }}
    />
  );
}
