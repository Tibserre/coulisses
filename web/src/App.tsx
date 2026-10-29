import { useCallback, useEffect, useRef, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { IconButton } from "@astryxdesign/core/IconButton";
import { InternationalizationProvider } from "@astryxdesign/core/i18n";
import frFR from "@astryxdesign/core/locales/fr-FR.generated.js";
import { Theme } from "@astryxdesign/core/theme";
import { AudioLines, PanelLeft, Plus, Upload } from "lucide-react";
import { MotionConfig } from "motion/react";
import {
  api,
  type AppInfo,
  type Project,
  type RecordingState,
  type Session,
  type Space,
} from "./api.ts";
import { ErrorBoundary } from "./components/ErrorBoundary.tsx";
import {
  UpdateNoticesDialog,
  useUpdateNotices,
} from "./components/UpdateNotices.tsx";
import { SearchBox } from "./components/SearchBox.tsx";
import { Sidebar } from "./components/Sidebar.tsx";
import { useUpdateReady } from "./appBridge.ts";
import {
  IMPORT_ACCEPT,
  buildTree,
  droppedFile,
  importPlace,
  latestFirst,
  onLibraryChanged,
  parseRoute,
  rememberedSpace,
  sessionHref,
  startSpace,
  type Route,
} from "./library.ts";
import { ProgressBar } from "@astryxdesign/core/ProgressBar";
import { ActionsPage } from "./pages/ActionsPage.tsx";
import { HomePage } from "./pages/HomePage.tsx";
import { RecordingPage } from "./pages/RecordingPage.tsx";
import { SessionPage } from "./pages/SessionPage.tsx";
import { SettingsPage } from "./pages/SettingsPage.tsx";
import { NewSpaceForm, SpacePage } from "./pages/SpacesPage.tsx";
import { coulissesTheme } from "./theme/coulisses.js";

export function App() {
  const [route, setRoute] = useState<Route>(() =>
    parseRoute(window.location.hash),
  );
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return (
    <InternationalizationProvider locale="fr-FR" messages={{ "fr-FR": frFR }}>
      <Theme theme={coulissesTheme}>
        <MotionConfig reducedMotion="user">
          <Shell route={route} />
        </MotionConfig>
      </Theme>
    </InternationalizationProvider>
  );
}

const SIDEBAR_KEY = "coulisses.colonne";
/** Under this width, the side column is folded away by default, and comes over the page
 *  when asked (⌘\), without pushing it. */
const NARROW = "(max-width: 1100px)";

function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(() => window.matchMedia(NARROW).matches);
  useEffect(() => {
    const query = window.matchMedia(NARROW);
    const onChange = () => setNarrow(query.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);
  return narrow;
}

function readSidebar(): boolean {
  try {
    return window.localStorage.getItem(SIDEBAR_KEY) !== "fermee";
  } catch {
    return true;
  }
}

/** The application's frame (ADR 0030): the search and « Nouvelle note » at the top, the
 *  spaces and their sessions in the side column, what is open in the main pane. */
function Shell({ route }: { route: Route }) {
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [info, setInfo] = useState<AppInfo | null>(null);
  const [recording, setRecording] = useState<RecordingState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sideError, setSideError] = useState<string | null>(null);
  const [wide, setWide] = useState(readSidebar);
  const narrow = useNarrow();
  const [overlay, setOverlay] = useState(false);
  const sidebar = narrow ? overlay : wide;
  // On a narrow window, the column over the page closes once something is opened, on
  // Escape, or on a click beside it.
  useEffect(() => setOverlay(false), [route, narrow]);
  useEffect(() => {
    if (!(narrow && overlay)) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOverlay(false);
    };
    const onPointer = (e: PointerEvent) => {
      const target = e.target as Element | null;
      if (target?.closest(".cl-sidebar a"))
        setOverlay(false); // even the page already open
      else if (!target?.closest(".cl-sidebar, .cl-topbar")) setOverlay(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerup", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerup", onPointer);
    };
  }, [narrow, overlay]);
  // What an update (or the first launch) asks on this Mac (ADR 0049): a window at launch,
  // a dot on « Réglages » while one not kept for good is left.
  const updates = useUpdateNotices(route.page === "recording");
  // A new version waiting for a click (ADR 0051): « Mettre à jour » in the column, a dot on
  // its button while it is closed; not offered during a recording, nor before the service
  // has said whether one runs (nothing shown then hidden).
  const updateReady =
    useUpdateReady() && info !== null && !recording?.session_id;
  const closeUpdates = useCallback(() => {
    updates.setOpen(false);
    updates.clearAsked();
  }, [updates.setOpen, updates.clearAsked]);
  const [newSpace, setNewSpace] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [s, p, list, about, current] = await Promise.all([
        api.spaces(),
        api.projects(),
        api.sessions(),
        api.info(),
        api.recording(),
      ]);
      setSpaces(s);
      setProjects(p);
      setSessions(list);
      setInfo(about);
      setRecording(current);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 4000);
    const stop = onLibraryChanged(() => void refresh());
    return () => {
      window.clearInterval(timer);
      stop();
    };
  }, [refresh]);

  const toggleSidebar = useCallback(() => {
    if (narrow) {
      setOverlay((open) => !open);
      return;
    }
    setWide((open) => {
      try {
        window.localStorage.setItem(SIDEBAR_KEY, open ? "fermee" : "ouverte");
      } catch {
        // Storage blocked: for this page only.
      }
      return !open;
    });
  }, [narrow]);

  const openSession =
    route.page === "session"
      ? sessions?.find((s) => s.id === route.id)
      : undefined;
  /** A recording started in one gesture (« Nouvelle note », ⌘N, « + » on a space; spec
   *  §7.11): online or hybrid by default (the microphone and the computer's sound), the
   *  default microphone, nobody checked yet. Where it goes, who was there, the computer's
   *  sound: changed on the recording screen. During a recording, back to it. */
  const [startError, setStartError] = useState<{
    message: string;
    where: { spaceId: number | null; projectId: number | null };
    system: boolean;
  } | null>(null);
  const starting = useRef(false);
  const startNow = useCallback(
    async (
      where: { spaceId: number | null; projectId: number | null },
      system = true,
    ) => {
      if (recording) {
        window.location.hash = "#/enregistrement";
        return;
      }
      if (starting.current) return;
      starting.current = true;
      try {
        await api.startRecording({
          espace: where.spaceId,
          projet: where.projectId,
          presents: [],
          non_nommes: null,
          micro: null,
          micros_en_plus: [],
          // Only the Mac's microphone in use (or the earphones plugged in) and its sound:
          // any other microphone is added on demand (the user's choice, ADR 0067).
          son_ordinateur: system,
        });
        setStartError(null);
        window.location.hash = "#/enregistrement";
        void refresh();
      } catch (e) {
        // One started elsewhere meanwhile: that is where to go, nothing to retry.
        const running = await api.recording().catch(() => null);
        if (running) {
          window.location.hash = "#/enregistrement";
          return;
        }
        setStartError({ message: (e as Error).message, where, system });
      } finally {
        starting.current = false;
      }
    },
    [recording, refresh],
  );
  // The space selected: the open session's (and its project), the space whose page is
  // open, else where the home page's button would record.
  const here = useCallback(
    (): { spaceId: number | null; projectId: number | null } =>
      openSession
        ? { spaceId: openSession.space_id, projectId: openSession.project_id }
        : route.page === "space"
          ? { spaceId: route.id, projectId: null }
          : {
              spaceId: startSpace(
                spaces,
                [...(sessions ?? [])].sort((a, b) =>
                  b.recorded_at.localeCompare(a.recorded_at),
                ),
                rememberedSpace(),
              ),
              projectId: null,
            },
    [openSession, route, spaces, sessions],
  );
  const askNew = useCallback(() => void startNow(here()), [here, startNow]);
  /** Import in one gesture, as one records (ADR 0069): the file is sent at once, into the
   *  space selected (an archived one: where the home page would record), and its session
   *  opens; who was there is checked on it afterwards. One file at a time. */
  const [sending, setSending] = useState<{ name: string; fraction: number } | null>(null);
  // Each refusal or failure said, none hiding another: dismissed together.
  const [importErrors, setImportErrors] = useState<string[]>([]);
  const sayImport = useCallback(
    (message: string) => setImportErrors((before) => [...before, message]),
    [],
  );
  const sendingNow = useRef(false);
  const importFile = useCallback(
    async (file: File, where: { spaceId: number | null; projectId: number | null }) => {
      if (sendingNow.current) {
        sayImport(`« ${file.name} » n'est pas envoyé : un autre fichier est en cours d'envoi.`);
        return;
      }
      sendingNow.current = true;
      setSending({ name: file.name, fraction: 0 });
      const place = importPlace(where, spaces, latestFirst(sessions ?? []), rememberedSpace());
      try {
        const { id } = await api.importRecording(
          file,
          { ...place, personIds: [], unnamed: null },
          (fraction) => setSending({ name: file.name, fraction }),
        );
        void refresh();
        window.location.hash = sessionHref(id);
      } catch (e) {
        sayImport(`« ${file.name} » : ${(e as Error).message}`);
      } finally {
        sendingNow.current = false;
        setSending(null);
      }
    },
    [spaces, sessions, refresh, sayImport],
  );
  const picker = useRef<HTMLInputElement>(null);
  const pickFor = useRef<{ spaceId: number | null; projectId: number | null }>({
    spaceId: null,
    projectId: null,
  });
  /** « Importer un fichier… », « ou importer un fichier », ⌘O: the Finder's window, then the
   *  file is sent where it was asked. */
  const askImport = useCallback(
    (where?: { spaceId: number | null; projectId: number | null }) => {
      pickFor.current = where ?? here();
      picker.current?.click();
    },
    [here],
  );

  // ⌘N: a new session (where the open one is); ⌘O: import a file there; ⌘\ : the side
  // column.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      if (e.key.toLowerCase() === "n") {
        e.preventDefault();
        askNew();
      } else if (e.key.toLowerCase() === "o") {
        e.preventDefault();
        askImport();
      } else if (e.key === "\\") {
        e.preventDefault();
        toggleSidebar();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [askNew, askImport, toggleSidebar]);

  // A file dragged from the Finder anywhere on the window: dropped, it is sent. A session
  // dragged in the column carries no file, and is left to it.
  const [dropping, setDropping] = useState(false);
  // Read through refs, so the listeners stay put during a long drag (the library refreshes
  // every 4 s) and their count of entered elements is not lost.
  const dropTo = useRef({ importFile, here, sayImport });
  dropTo.current = { importFile, here, sayImport };
  useEffect(() => {
    let depth = 0;
    const carriesFiles = (e: DragEvent) =>
      e.dataTransfer?.types.includes("Files") ?? false;
    const onEnter = (e: DragEvent) => {
      if (!carriesFiles(e)) return;
      depth += 1;
      setDropping(true);
    };
    const onOver = (e: DragEvent) => {
      if (!carriesFiles(e)) return;
      e.preventDefault(); // else the browser opens the file in place of the app
      if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
    };
    const onLeave = (e: DragEvent) => {
      if (!carriesFiles(e)) return;
      depth = Math.max(0, depth - 1);
      if (depth === 0) setDropping(false);
    };
    const onDrop = (e: DragEvent) => {
      if (!carriesFiles(e)) return;
      e.preventDefault();
      depth = 0;
      setDropping(false);
      const taken = droppedFile([...(e.dataTransfer?.files ?? [])]);
      const to = dropTo.current;
      if ("refusal" in taken) to.sayImport(taken.refusal);
      else void to.importFile(taken.file, to.here());
    };
    window.addEventListener("dragenter", onEnter);
    window.addEventListener("dragover", onOver);
    window.addEventListener("dragleave", onLeave);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragenter", onEnter);
      window.removeEventListener("dragover", onOver);
      window.removeEventListener("dragleave", onLeave);
      window.removeEventListener("drop", onDrop);
    };
  }, []);
  const dropSpace = dropping
    ? spaces.find(
        (sp) =>
          sp.id ===
          importPlace(here(), spaces, latestFirst(sessions ?? []), rememberedSpace()).spaceId,
      )
    : undefined;

  const tree = buildTree(spaces, projects, sessions ?? []);
  const mainKey =
    route.page === "session"
      ? `session:${route.id}`
      : route.page === "space"
        ? `space:${route.id}`
        : route.page;

  return (
    <div
      className="cl-shell"
      data-sidebar={sidebar ? "ouverte" : "fermee"}
      data-etroit={narrow || undefined}
    >
      <header className="cl-topbar">
        <IconButton
          label={
            (sidebar
              ? "Masquer la colonne (⌘\\)"
              : "Afficher la colonne (⌘\\)") +
            (!sidebar && updateReady ? " · une mise à jour attend" : "")
          }
          icon={
            <span className="cl-topbar__toggle">
              <PanelLeft size={18} strokeWidth={1.75} />
              {!sidebar && updateReady && (
                <span className="cl-topbar__dot" aria-hidden />
              )}
            </span>
          }
          variant="ghost"
          onClick={toggleSidebar}
        />
        <a className="cl-brand" href="#/">
          <AudioLines
            size={20}
            strokeWidth={1.75}
            color="var(--color-accent)"
            aria-hidden
          />
          <span>Coulisses</span>
        </a>
        <SearchBox sessions={sessions ?? []} />
        <Button
          variant="primary"
          size="sm"
          label="Nouvelle note"
          icon={<Plus size={16} strokeWidth={1.75} />}
          onClick={askNew}
        />
      </header>
      <div className="cl-shell__body">
        {sidebar && (
          <Sidebar
            tree={tree.filter((n) => !n.space.archived)}
            archived={tree.filter((n) => n.space.archived)}
            recordingId={recording?.session_id ?? null}
            stepsLeft={updates.notices.length}
            updateReady={updateReady}
            current={{
              sessionId:
                route.page === "session"
                  ? route.id
                  : route.page === "recording"
                    ? (recording?.session_id ?? null)
                    : null,
              spaceId: route.page === "space" ? route.id : null,
              page: route.page,
            }}
            onNewSession={(spaceId, projectId) =>
              void startNow({ spaceId, projectId })
            }
            onImport={(spaceId, projectId) => askImport({ spaceId, projectId })}
            onNewSpace={() => setNewSpace(true)}
            onChanged={refresh}
            onError={setSideError}
          />
        )}
        <div className="cl-shell__main">
          {sending && (
            <div className="cl-shell__notice">
              <ProgressBar
                label={`Envoi de « ${sending.name} »`}
                value={sending.fraction * 100}
                hasValueLabel
              />
            </div>
          )}
          {importErrors.length > 0 && (
            <div className="cl-shell__notice">
              <Banner
                status="error"
                title={
                  importErrors.length > 1
                    ? "Des fichiers n'ont pas été importés"
                    : "Le fichier n'a pas été importé"
                }
                description={importErrors.map((m, k) => (
                  <span key={k} style={{ display: "block" }}>
                    {m}
                  </span>
                ))}
                isDismissable
                onDismiss={() => setImportErrors([])}
              />
            </div>
          )}
          {startError && (
            <div className="cl-shell__notice">
              <Banner
                status="error"
                title="L'enregistrement n'a pas démarré"
                description={startError.message}
                isDismissable
                onDismiss={() => setStartError(null)}
                endContent={
                  startError.system ? (
                    <Button
                      size="sm"
                      label="Le micro seul"
                      onClick={() => void startNow(startError.where, false)}
                    />
                  ) : undefined
                }
              />
            </div>
          )}
          {sideError && (
            <div className="cl-shell__notice">
              <Banner
                status="error"
                title="Refusé"
                description={sideError}
                isDismissable
                onDismiss={() => setSideError(null)}
              />
            </div>
          )}
          <ErrorBoundary key={mainKey}>
            {route.page === "session" ? (
              <SessionPage
                id={route.id}
                at={route.at}
                tab={route.tab}
                projects={projects}
              />
            ) : route.page === "space" ? (
              <SpacePage id={route.id} onChanged={refresh} />
            ) : route.page === "recording" ? (
              <RecordingPage
                spaces={spaces}
                projects={projects}
                onMoved={() => void refresh()}
              />
            ) : route.page === "actions" ? (
              <ActionsPage selectedRef={route.ref} />
            ) : route.page === "settings" ? (
              <SettingsPage
                part={route.part}
                info={info}
                stepsLeft={updates.notices.length}
                // « Remplacer… »: the window that downloads the new model, then removes the old.
                onReplace={(() => {
                  const replacement = updates.notices.find(
                    (n) => n.kind === "replacement",
                  );
                  return replacement
                    ? () => updates.openOn(replacement.id)
                    : undefined;
                })()}
              />
            ) : (
              <HomePage
                sessions={sessions}
                spaces={spaces}
                projects={projects}
                info={info}
                recording={recording}
                error={error}
                onRecord={(spaceId) => void startNow({ spaceId, projectId: null })}
                onImport={(spaceId) => askImport({ spaceId, projectId: null })}
              />
            )}
          </ErrorBoundary>
        </div>
      </div>
      {dropping && (
        <div className="cl-filedrop" aria-hidden>
          <div className="cl-filedrop__panel">
            <Upload size={22} strokeWidth={1.75} />
            <span>
              Déposez pour importer
              {dropSpace ? ` dans ${dropSpace.name}` : ""}
            </span>
            <span className="cl-filedrop__note">
              Audio ou vidéo : seul le son est traité, le fichier est gardé tel quel
            </span>
          </div>
        </div>
      )}
      <UpdateNoticesDialog
        isOpen={updates.open}
        notices={updates.notices}
        asked={updates.asked}
        onAskedAnswered={updates.clearAsked}
        actions={updates.actions}
        failed={updates.failed}
        onChoose={updates.choose}
        onStop={updates.stop}
        onClose={closeUpdates}
        onFailedRead={updates.clearFailed}
      />
      <input
        ref={picker}
        type="file"
        accept={IMPORT_ACCEPT}
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = ""; // the same file can be chosen again
          if (!file) return;
          const taken = droppedFile([file]);
          if ("refusal" in taken) sayImport(taken.refusal);
          else void importFile(taken.file, pickFor.current);
        }}
      />
      <Dialog
        isOpen={newSpace}
        onOpenChange={(open) => !open && setNewSpace(false)}
        width={480}
      >
        <DialogHeader
          title="Nouvel espace"
          onOpenChange={() => setNewSpace(false)}
        />
        {newSpace && (
          <NewSpaceForm
            onCancel={() => setNewSpace(false)}
            onCreated={(space) => {
              setNewSpace(false);
              void refresh();
              window.location.hash = `#/espaces/${space.id}`;
            }}
          />
        )}
      </Dialog>
    </div>
  );
}
