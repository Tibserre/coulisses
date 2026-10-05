import { useEffect, useState } from "react";
import { InternationalizationProvider } from "@astryxdesign/core/i18n";
import frFR from "@astryxdesign/core/locales/fr-FR.generated.js";
import { Theme } from "@astryxdesign/core/theme";
import { MotionConfig } from "motion/react";
import { coulissesTheme } from "./theme/coulisses.js";
import { LibraryPage } from "./pages/LibraryPage.tsx";
import { SessionPage } from "./pages/SessionPage.tsx";

type Route = { page: "library" } | { page: "session"; id: string };

function parseRoute(hash: string): Route {
  const match = /^#\/seance\/([^/?#]+)/.exec(hash);
  return match ? { page: "session", id: decodeURIComponent(match[1]) } : { page: "library" };
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
          {route.page === "session" ? <SessionPage id={route.id} /> : <LibraryPage />}
        </MotionConfig>
      </Theme>
    </InternationalizationProvider>
  );
}
