import { useEffect, useState } from "react";
import { InternationalizationProvider } from "@astryxdesign/core/i18n";
import frFR from "@astryxdesign/core/locales/fr-FR.generated.js";
import { Theme } from "@astryxdesign/core/theme";
import { MotionConfig } from "motion/react";
import { coulissesTheme } from "./theme/coulisses.js";
import { LibraryPage } from "./pages/LibraryPage.tsx";
import { SessionPage } from "./pages/SessionPage.tsx";
import { SpacesPage } from "./pages/SpacesPage.tsx";
import { ErrorBoundary } from "./components/ErrorBoundary.tsx";

type Route =
  | { page: "library" }
  | { page: "session"; id: string }
  | { page: "spaces"; id: number | null };

function parseRoute(hash: string): Route {
  const session = /^#\/seance\/([^/?#]+)/.exec(hash);
  if (session) return { page: "session", id: decodeURIComponent(session[1]) };
  const spaces = /^#\/espaces(?:\/(\d+))?/.exec(hash);
  if (spaces) return { page: "spaces", id: spaces[1] ? Number(spaces[1]) : null };
  return { page: "library" };
}

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
          <ErrorBoundary key={window.location.hash}>
            {route.page === "session" ? (
            <SessionPage id={route.id} />
          ) : route.page === "spaces" ? (
            <SpacesPage id={route.id} />
          ) : (
            <LibraryPage />
          )}
          </ErrorBoundary>
        </MotionConfig>
      </Theme>
    </InternationalizationProvider>
  );
}
