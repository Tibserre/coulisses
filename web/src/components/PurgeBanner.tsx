import { useEffect, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { api, type PurgeAnnouncement } from "../api.ts";
import { formatDate, plural } from "../format.ts";
import { formatDay } from "../retention.ts";

/** Purges announced and not done yet (spec §7.10): said on every page until each session
 *  is kept, extended or purged. The macOS notification says it once; this stays. */
export function PurgeBanner() {
  const [coming, setComing] = useState<PurgeAnnouncement[]>([]);
  const [problems, setProblems] = useState<string[]>([]);
  useEffect(() => {
    const load = () =>
      api.retention().then(
        (r) => {
          setComing(r.coming);
          setProblems(r.problems);
        },
        (e: Error) => setProblems([`Les suppressions à venir n'ont pas pu être lues : ${e.message}`]),
      );
    load();
    // Checked by the service every hour; read again every 10 minutes and on return.
    const timer = window.setInterval(load, 10 * 60 * 1000);
    window.addEventListener("focus", load);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", load);
    };
  }, []);
  if (!coming.length && !problems.length) return null;
  if (!coming.length)
    return (
      <div className="cl-purge-banner">
        <Banner status="error" title="Conservation de l'audio" description={problems.join(" ")} />
      </div>
    );
  const first = coming.reduce((a, b) => (a.purge_on < b.purge_on ? a : b));
  const name = (c: PurgeAnnouncement) => c.title ?? `Séance du ${formatDate(c.recorded_at).toLowerCase()}`;
  return (
    <div className="cl-purge-banner">
      <Banner
        status="warning"
        title={
          coming.length === 1
            ? `L'audio de « ${name(first)} » sera supprimé le ${formatDay(first.purge_on)}`
            : `L'audio de ${plural(coming.length, "séance", "séances")} sera bientôt supprimé, dès le ${formatDay(first.purge_on)}`
        }
        description={`Le texte, les noms et les résumés restent. Gardez l'audio ou prolongez s'il vous sert encore.${problems.length ? ` ${problems.join(" ")}` : ""}`}
        endContent={<Button size="sm" label="Voir" onClick={() => (window.location.hash = "#/reglages?onglet=general")} />}
      />
    </div>
  );
}
