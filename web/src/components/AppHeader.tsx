import { Heading } from "@astryxdesign/core/Heading";
import { AudioLines } from "lucide-react";

/** The application's header: its name and the two places of the library. */
export function AppHeader({ current }: { current: "library" | "spaces" }) {
  return (
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
      </nav>
    </header>
  );
}
