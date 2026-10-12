import { useCallback, useEffect, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { NumberInput } from "@astryxdesign/core/NumberInput";
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
import { ExportFolderSection } from "../components/ExportFolderSection.tsx";
import { ModelsSection } from "../components/ModelsSection.tsx";
import { setDevMode } from "../devMode.ts";
import { formatBytes, formatDate, formatDateTime, plural } from "../format.ts";
import { LOG_KIND, formatDay } from "../retention.ts";
import { useDevMode } from "../devMode.ts";

/** Settings (spec §7.12): the audio's keeping (§7.10: how long, the notice, what is about to
 *  be purged, the log of every purge and deletion, the backups of the base), the export
 *  folder, Coulisses itself (its version, its folders shown in the Finder), developer mode. */
type Part = "general" | "modeles" | "donnees" | "avance";
const PARTS: [Part, string][] = [
  ["general", "Général"],
  ["modeles", "Modèles"],
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
                L'audio d'une séance traitée est supprimé au bout de cette
                durée, comptée depuis son entrée dans Coulisses, après un
                préavis. Le texte, les noms et les résumés restent. Une séance
                peut garder son audio (menu « … » de la séance).
              </Text>
              <div className="cl-settings__fields">
                <NumberInput
                  label="Garder l'audio"
                  description="En jours."
                  value={shownDays}
                  onChange={(v) =>
                    setDays(Number.isFinite(v) ? Math.round(v) : null)
                  }
                />
                <NumberInput
                  label="Préavis"
                  description="En jours, avant la suppression."
                  value={shownNotice}
                  onChange={(v) =>
                    setNotice(Number.isFinite(v) ? Math.round(v) : null)
                  }
                />
              </div>
              <div>
                <Button
                  variant="primary"
                  size="sm"
                  label={saved && !changed ? "Enregistré" : "Enregistrer"}
                  isDisabled={!changed}
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
