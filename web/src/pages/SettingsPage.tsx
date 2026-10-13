import { useCallback, useEffect, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { Text } from "@astryxdesign/core/Text";
import {
  api,
  type AppInfo,
  type Folders,
  type PurgeAnnouncement,
  type RetentionInfo,
} from "../api.ts";
import { Switch } from "@astryxdesign/core/Switch";
import { Tab, TabList } from "@astryxdesign/core/TabList";
import { DayStepper } from "../components/DayStepper.tsx";
import { ExportFolderSection } from "../components/ExportFolderSection.tsx";
import { ModelsSection } from "../components/ModelsSection.tsx";
import { UpdatesSection } from "../components/UpdatesSection.tsx";
import { WritingModels } from "../components/WritingModels.tsx";
import { setDevMode } from "../devMode.ts";
import { formatBytes, formatDate, formatDateTime, plural } from "../format.ts";
import { LOG_KIND, formatDay } from "../retention.ts";
import { useDevMode } from "../devMode.ts";

/** Settings (spec §7.12): the audio's keeping (§7.10: how long, the notice, what is about to
 *  be purged, the log of every purge and deletion, the backups of the base), the export
 *  folder, Coulisses itself (its version, its folders shown in the Finder, its updates),
 *  developer mode. */
type Part = "general" | "modeles" | "redaction" | "donnees" | "avance";
const PARTS: [Part, string][] = [
  ["general", "Général"],
  // The engine's models (transcription, voices); the language models (titles, chapters,
  // summaries).
  ["modeles", "Transcription"],
  ["redaction", "Rédaction"],
  ["donnees", "Données"],
  ["avance", "Avancé"],
];

/** The tab asked in the address (« #/reglages?onglet=modeles »), else the first. */
function partOf(asked: string | null): Part {
  return PARTS.some(([key]) => key === asked) ? (asked as Part) : "general";
}

/** Lists that only grow (the deletion log, the backups): the latest first, the rest on
 *  demand. */
const SHOWN_ROWS = 5;
/** The usual values the steppers go through: a week, two, a month, a season, a year… */
const RETENTION_STEPS = [7, 14, 30, 60, 90, 120, 180, 270, 365, 730];
const NOTICE_STEPS = [1, 2, 3, 5, 7, 10, 14, 21, 30, 60];
/** The service gives the latest 200 entries of the log (retention.journal). */
const JOURNAL_LIMIT = 200;

export function SettingsPage({
  info: about,
  part: asked = null,
}: {
  info: AppInfo | null;
  /** The tab asked in the address. */
  part?: string | null;
}) {
  const dev = useDevMode();
  const [part, setPart] = useState<Part>(() => partOf(asked));
  // A link to another tab while this page is open (the purge banner, an error).
  useEffect(() => setPart(partOf(asked)), [asked]);
  const [allLog, setAllLog] = useState(false);
  const [allBackups, setAllBackups] = useState(false);
  const [info, setInfo] = useState<RetentionInfo | null>(null);
  const [days, setDays] = useState<number | null>(null);
  const [notice, setNotice] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [folders, setFolders] = useState<Folders | null>(null);
  useEffect(() => {
    api.folders().then(setFolders, (e: Error) => setError(e.message));
  }, []);

  const load = useCallback(async () => {
    try {
      setInfo(await api.retention());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const act = async (action: () => Promise<unknown>) => {
    try {
      await action();
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const shownDays = days ?? info?.settings.retention_days ?? 90;
  const shownNotice = notice ?? info?.settings.notice_days ?? 7;
  const changed =
    info !== null &&
    (shownDays !== info.settings.retention_days ||
      shownNotice !== info.settings.notice_days);
  const name = (c: PurgeAnnouncement) =>
    c.title ?? `Séance du ${formatDate(c.recorded_at).toLowerCase()}`;

  return (
    <div className="cl-page">
      <main className="cl-settings">
        <Heading level={2}>Réglages</Heading>
        <TabList
          value={part}
          onChange={(v) => {
            setPart(v as Part);
            window.location.hash = `#/reglages?onglet=${v}`;
          }}
          hasDivider
        >
          {PARTS.map(([key, label]) => (
            <Tab key={key} value={key} label={label} />
          ))}
        </TabList>
        {error && (
          <Banner
            status="error"
            title="Refusé"
            description={error}
            isDismissable
            onDismiss={() => setError(null)}
          />
        )}
        {info?.problems.map((p) => (
          <Banner key={p} status="error" title="Conservation" description={p} />
        ))}

        {part === "general" && (
          <>
            <section className="cl-settings__section">
              <Heading level={3}>Conservation de l'audio</Heading>
              <Text color="secondary">
                L'audio d'une séance traitée est supprimé après ce délai, avec
                un préavis. Le texte, les noms et les résumés restent ; une
                séance peut garder son audio depuis son menu « … ».
              </Text>
              <div className="cl-settings__steppers">
                <DayStepper
                  label="Garder l'audio"
                  description="Depuis son entrée dans Coulisses."
                  value={shownDays}
                  steps={RETENTION_STEPS}
                  min={Math.max(1, shownNotice)}
                  isDisabled={info === null}
                  onChange={(v) => {
                    setDays(v);
                    setSaved(false);
                  }}
                />
                <DayStepper
                  label="Préavis"
                  description="Avant la suppression."
                  value={shownNotice}
                  steps={NOTICE_STEPS}
                  max={shownDays}
                  isDisabled={info === null}
                  onChange={(v) => {
                    setNotice(v);
                    setSaved(false);
                  }}
                />
              </div>
              {/* Said only once something changed; its place kept, so nothing moves. */}
              <div className="cl-settings__save">
                {changed ? (
                  <>
                    <Button
                      variant="primary"
                      size="sm"
                      label="Enregistrer"
                      clickAction={() =>
                        act(async () => {
                          await api.setRetention({
                            retention_days: shownDays,
                            notice_days: shownNotice,
                          });
                          setDays(null);
                          setNotice(null);
                          setSaved(true);
                        })
                      }
                    />
                    <Button
                      variant="ghost"
                      size="sm"
                      label="Annuler"
                      onClick={() => {
                        setDays(null);
                        setNotice(null);
                      }}
                    />
                  </>
                ) : (
                  saved && <Text type="supporting">Enregistré.</Text>
                )}
              </div>
            </section>

            <section className="cl-settings__section">
              <Heading level={3}>Bientôt supprimés</Heading>
              {info && info.coming.length === 0 && (
                <Text color="secondary">
                  Aucun audio n'est sur le point d'être supprimé.
                </Text>
              )}
              <ul className="cl-settings__list">
                {info?.coming.map((c) => (
                  <li key={c.session_id}>
                    <span className="cl-settings__text">
                      <a href={`#/seance/${encodeURIComponent(c.session_id)}`}>
                        {name(c)}
                      </a>
                      <Text type="supporting">
                        suppression de l'audio le {formatDay(c.purge_on)}
                      </Text>
                    </span>
                    <Button
                      size="sm"
                      variant="ghost"
                      label="Prolonger"
                      clickAction={() =>
                        act(() => api.extendAudio(c.session_id))
                      }
                    />
                    <Button
                      size="sm"
                      label="Garder l'audio"
                      clickAction={() =>
                        act(() => api.keepAudio(c.session_id, true))
                      }
                    />
                  </li>
                ))}
              </ul>
            </section>

            <ExportFolderSection />
          </>
        )}

        {part === "modeles" && <ModelsSection />}

        {part === "redaction" && <WritingModels />}

        {part === "donnees" && (
          <>
            <section className="cl-settings__section">
              <Heading level={3}>Coulisses</Heading>
              <Text color="secondary">
                {about ? `Version ${about.app_version}. ` : ""}Tout reste sur ce
                Mac : les séances dans le dossier des données, les modèles du
                moteur dans le leur.
              </Text>
              <div className="cl-settings__buttons">
                <Button
                  label="Ouvrir les données"
                  size="sm"
                  onClick={() => void act(() => api.openFolder("donnees"))}
                />
                {dev && folders?.log && (
                  <Button
                    label="Afficher le journal"
                    size="sm"
                    onClick={() => void act(() => api.openFolder("journal"))}
                  />
                )}
              </div>
              {dev && folders && (
                <Text type="supporting">
                  Modèles : {folders.models}
                  {folders.log ? ` · journal : ${folders.log}` : ""}
                </Text>
              )}
            </section>

            <UpdatesSection />

            <section className="cl-settings__section">
              <Heading level={3}>Journal des suppressions</Heading>
              {info && info.journal.length === 0 && (
                <Text color="secondary">Rien n'a été supprimé.</Text>
              )}
              <ul className="cl-settings__list">
                {info?.journal
                  .slice(0, allLog ? undefined : SHOWN_ROWS)
                  .map((e) => (
                    <li key={e.id}>
                      <span className="cl-settings__text">
                        <Text>
                          {LOG_KIND[e.kind]}
                          {e.session_title ? ` : « ${e.session_title} »` : ""}
                        </Text>
                        <Text type="supporting">
                          {formatDateTime(e.at)} ·{" "}
                          {plural(e.files, "fichier", "fichiers")},{" "}
                          {formatBytes(e.bytes)}
                          {e.problems.length > 0 && " · incomplète"}
                        </Text>
                        {e.problems.map((p) => (
                          <Text key={p} type="supporting" color="primary">
                            {p}
                          </Text>
                        ))}
                      </span>
                    </li>
                  ))}
              </ul>
              {info && info.journal.length > SHOWN_ROWS && (
                <div>
                  <Button
                    size="sm"
                    variant="ghost"
                    label={
                      allLog
                        ? "N'afficher que les dernières"
                        : info.journal.length >= JOURNAL_LIMIT
                          ? `Voir les ${JOURNAL_LIMIT} dernières`
                          : `Voir les ${info.journal.length - SHOWN_ROWS} autres`
                    }
                    onClick={() => setAllLog(!allLog)}
                  />
                </div>
              )}
            </section>

            <section className="cl-settings__section">
              <Heading level={3}>Sauvegardes de la base</Heading>
              <Text color="secondary">
                Une copie de la base est faite avant chaque mise à jour de
                Coulisses. Supprimer une séance l'efface aussi de ces copies.
              </Text>
              <ul className="cl-settings__list">
                {/* The most recent first: those one goes back to after an update. */}
                {[...(info?.backups ?? [])]
                  .reverse()
                  .slice(0, allBackups ? undefined : SHOWN_ROWS)
                  .map((b) => (
                    <li key={b.name}>
                      <span className="cl-settings__text">
                        <Text>Copie du {b.made_on}</Text>
                        <Text type="supporting">
                          {formatBytes(b.bytes)}
                          {dev && ` · ${b.name}`}
                        </Text>
                      </span>
                    </li>
                  ))}
              </ul>
              {info && info.backups.length > SHOWN_ROWS && (
                <div>
                  <Button
                    size="sm"
                    variant="ghost"
                    label={
                      allBackups
                        ? "N'afficher que les dernières"
                        : `Voir les ${info.backups.length - SHOWN_ROWS} autres`
                    }
                    onClick={() => setAllBackups(!allBackups)}
                  />
                </div>
              )}
            </section>
          </>
        )}

        {part === "avance" && (
          <section className="cl-settings__section">
            <Heading level={3}>Mode développeur</Heading>
            <Switch
              label="Afficher les détails techniques"
              description="Provenance des étapes, durées de calcul, mémoire, versions, erreurs brutes."
              value={dev}
              onChange={setDevMode}
            />
            {dev && about && (
              <Text type="supporting">
                Données : {about.data_dir} · Coulisses {about.app_version} ·
                moteur {about.engine_version} · chaîne « {about.profile} »
              </Text>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
