import { Heading } from "@astryxdesign/core/Heading";
import { AudioLines } from "lucide-react";
import { PurgeBanner } from "./PurgeBanner.tsx";

/** The application's header: its name and the places of the library, then the purges
 *  coming, if any. */
export function AppHeader({ current }: { current: "library" | "spaces" | "actions" | "settings" }) {
  return (
    <>
    <header className="cl-page__header">
      <a className="cl-brand" href="#/">
        <AudioLines size={22} strokeWidth={1.75} color="var(--color-accent)" aria-hidden />
        <Heading level={1}>Coulisses</Heading>
      </a>
      <nav className="cl-nav" aria-label="Navigation">
        <a href="#/" aria-current={current === "library" ? "page" : undefined}>
          Enregistrements
        </a>
        <a href="#/espaces" aria-current={current === "spaces" ? "page" : undefined}>
          Espaces
        </a>
        <a href="#/actions" aria-current={current === "actions" ? "page" : undefined}>
          Actions
        </a>
        <a href="#/reglages" aria-current={current === "settings" ? "page" : undefined}>
          Réglages
        </a>
      </nav>
    </header>
    {/* Purges coming: said on every page of the library (the settings list them). */}
    {current !== "settings" && <PurgeBanner />}
    </>
  );
}
