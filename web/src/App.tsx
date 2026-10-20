import { useCallback, useEffect, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { IconButton } from "@astryxdesign/core/IconButton";
import { InternationalizationProvider } from "@astryxdesign/core/i18n";
import frFR from "@astryxdesign/core/locales/fr-FR.generated.js";
import { Theme } from "@astryxdesign/core/theme";
import { AudioLines, PanelLeft, Plus } from "lucide-react";
import { MotionConfig } from "motion/react";
import { api, type AppInfo, type Project, type RecordingState, type Session, type Space } from "./api.ts";
import { ErrorBoundary } from "./components/ErrorBoundary.tsx";
import { NewSessionDialog, type Way } from "./components/NewSessionDialog.tsx";
import { UpdateNoticesDialog, useUpdateNotices } from "./components/UpdateNotices.tsx";
import { SearchBox } from "./components/SearchBox.tsx";
import { Sidebar } from "./components/Sidebar.tsx";
import { useUpdateReady } from "./appBridge.ts";
import { buildTree, onLibraryChanged, parseRoute, rememberedSpace, sessionHref, startSpace, type Route } from "./library.ts";
import { ActionsPage } from "./pages/ActionsPage.tsx";
import { HomePage } from "./pages/HomePage.tsx";
import { RecordingPage } from "./pages/RecordingPage.tsx";
import { SessionPage } from "./pages/SessionPage.tsx";
import { SettingsPage } from "./pages/SettingsPage.tsx";
import { NewSpaceForm, SpacePage } from "./pages/SpacesPage.tsx";
import { coulissesTheme } from "./theme/coulisses.js";

export function App() {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));
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

/** The application's frame (ADR 0030): the search and « Nouvelle séance » at the top, the
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
      if (target?.closest(".cl-sidebar a")) setOverlay(false); // even the page already open
      else if (!target?.closest(".cl-sidebar, .cl-topbar")) setOverlay(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerup", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerup", onPointer);
    };
  }, [narrow, overlay]);
  const [asking, setAsking] = useState<{ spaceId: number | null; projectId: number | null; way?: Way } | null>(null);
  // What an update (or the first launch) asks on this Mac (ADR 0049): a window at launch,
  // a dot on « Réglages » while one not kept for good is left.
  const updates = useUpdateNotices(route.page === "recording");
  // A new version waiting for a click (ADR 0051): « Mettre à jour » in the column, a dot on
  // its button while it is closed; not offered during a recording, nor before the service
  // has said whether one runs (nothing shown then hidden).
  const updateReady = useUpdateReady() && info !== null && !recording?.session_id;
  const closeUpdates = useCallback(() => updates.setOpen(false), [updates.setOpen]);
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

  const openSession = route.page === "session" ? sessions?.find((s) => s.id === route.id) : undefined;
  // Where the open session is; elsewhere, where the home page's button would record.
  const askNew = useCallback(
    () =>
      setAsking(
        openSession
          ? { spaceId: openSession.space_id, projectId: openSession.project_id }
          : {
              spaceId: startSpace(
                spaces,
                [...(sessions ?? [])].sort((a, b) => b.recorded_at.localeCompare(a.recorded_at)),
                rememberedSpace(),
              ),
              projectId: null,
            },
      ),
    [openSession, spaces, sessions],
  );

  // ⌘N: a new session (where the open one is); ⌘\ : the side column.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      if (e.key.toLowerCase() === "n") {
        e.preventDefault();
        askNew();
      } else if (e.key === "\\") {
        e.preventDefault();
        toggleSidebar();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [askNew, toggleSidebar]);

  const tree = buildTree(spaces, projects, sessions ?? []);
  const mainKey =
    route.page === "session" ? `session:${route.id}` : route.page === "space" ? `space:${route.id}` : route.page;

  return (
    <div
      className="cl-shell"
      data-sidebar={sidebar ? "ouverte" : "fermee"}
      data-etroit={narrow || undefined}
    >
      <header className="cl-topbar">
        <IconButton
          label={
            (sidebar ? "Masquer la colonne (⌘\\)" : "Afficher la colonne (⌘\\)") +
            (!sidebar && updateReady ? " · une mise à jour attend" : "")
          }
          icon={
            <span className="cl-topbar__toggle">
              <PanelLeft size={18} strokeWidth={1.75} />
              {!sidebar && updateReady && <span className="cl-topbar__dot" aria-hidden />}
            </span>
          }
          variant="ghost"
          onClick={toggleSidebar}
        />
        <a className="cl-brand" href="#/">
          <AudioLines size={20} strokeWidth={1.75} color="var(--color-accent)" aria-hidden />
          <span>Coulisses</span>
        </a>
        <SearchBox sessions={sessions ?? []} />
        <Button
          variant="primary"
          size="sm"
          label="Nouvelle séance"
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
              sessionId: route.page === "session" ? route.id : route.page === "recording" ? (recording?.session_id ?? null) : null,
              spaceId: route.page === "space" ? route.id : null,
              page: route.page,
            }}
            onNewSession={(spaceId, projectId) => setAsking({ spaceId, projectId })}
            onNewSpace={() => setNewSpace(true)}
            onChanged={refresh}
            onError={setSideError}
          />
        )}
        <div className="cl-shell__main">
          {sideError && (
            <div className="cl-shell__notice">
              <Banner status="error" title="Refusé" description={sideError} isDismissable onDismiss={() => setSideError(null)} />
            </div>
          )}
          <ErrorBoundary key={mainKey}>
            {route.page === "session" ? (
              <SessionPage id={route.id} at={route.at} tab={route.tab} projects={projects} />
            ) : route.page === "space" ? (
              <SpacePage id={route.id} onChanged={refresh} />
            ) : route.page === "recording" ? (
              <RecordingPage />
            ) : route.page === "actions" ? (
              <ActionsPage selectedRef={route.ref} />
            ) : route.page === "settings" ? (
              <SettingsPage part={route.part} info={info} stepsLeft={updates.notices.length} />
            ) : (
              <HomePage
                sessions={sessions}
                spaces={spaces}
                projects={projects}
                info={info}
                recording={recording}
                error={error}
                onNewSession={(spaceId, way) => setAsking({ spaceId, projectId: null, way })}
              />
            )}
          </ErrorBoundary>
        </div>
      </div>
      <UpdateNoticesDialog
        isOpen={updates.open}
        notices={updates.notices}
        actions={updates.actions}
        failed={updates.failed}
        onChoose={updates.choose}
        onStop={updates.stop}
        onClose={closeUpdates}
        onFailedRead={updates.clearFailed}
      />
      <NewSessionDialog
        isOpen={asking !== null}
        onClose={() => setAsking(null)}
        spaces={spaces}
        projects={projects}
        initial={asking ?? { spaceId: null, projectId: null }}
        recording={recording !== null}
        onImported={(id) => {
          void refresh();
          window.location.hash = sessionHref(id);
        }}
      />
      <Dialog isOpen={newSpace} onOpenChange={(open) => !open && setNewSpace(false)} width={480}>
        <DialogHeader title="Nouvel espace" onOpenChange={() => setNewSpace(false)} />
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
