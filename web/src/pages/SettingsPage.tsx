import { useCallback, useEffect, useRef, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { Popover } from "@astryxdesign/core/Popover";
import {
  SegmentedControl,
  SegmentedControlItem,
} from "@astryxdesign/core/SegmentedControl";
import { Skeleton } from "@astryxdesign/core/Skeleton";
import { Switch } from "@astryxdesign/core/Switch";
import { Tab, TabList } from "@astryxdesign/core/TabList";
import { Text } from "@astryxdesign/core/Text";
import { Bell, Mic } from "lucide-react";
import {
  api,
  type AppInfo,
  type Folders,
  type PurgeAnnouncement,
  type Reminders,
  type RetentionInfo,
} from "../api.ts";
import { DayStepper } from "../components/DayStepper.tsx";
import { ExportFolderSection } from "../components/ExportFolderSection.tsx";
import { LanguagesSection } from "../components/LanguagesSection.tsx";
import { ModelsSection } from "../components/ModelsSection.tsx";
import { UpdatesSection } from "../components/UpdatesSection.tsx";
import { WritingModels } from "../components/WritingModels.tsx";
import { useAppNotifications } from "../appBridge.ts";
import { setDevMode, useDevMode } from "../devMode.ts";
import { formatBytes, formatDate, formatDateTime, plural } from "../format.ts";
import {
  LOG_KIND,
  daysUntil,
  formatDay,
  retentionChoices,
  retentionWrite,
  remindersLine,
  sessionsWithoutAudio,
  untilWords,
} from "../retention.ts";
import { CreditsSection } from "../components/ModelCredits.tsx";
import { buildShown, PARTS, partOf, type Part } from "../settingsParts.ts";

/** Lists that only grow (the deletion log, the backups): the latest first, the rest on
 *  demand. */
const SHOWN_ROWS = 5;
/** A purge this close is said in full colour: three days or less (the second reminder). */
const CLOSE_DAYS = 3;
/** The service gives the latest 200 entries of the log (retention.journal). */
const JOURNAL_LIMIT = 200;

/** Settings (spec §7.12, ADR 0051), sorted by what one comes to do: the sessions (how long
 *  their audio is kept, what is about to go and what went, where reports are exported), the
 *  writing (the language model of each), the transcription (what the processing needs), and
 *  the rest (updates, folders, the technical log, developer mode). */
export function SettingsPage({
  info: about,
  part: asked = null,
  stepsLeft = 0,
  onReplace,
}: {
  info: AppInfo | null;
  /** The tab asked in the address. */
  part?: string | null;
  /** Steps an update asks on this Mac (ADR 0049): a dot on « Transcription ». */
  stepsLeft?: number;
  /** Opens the window that replaces an old model by the new one (ADR 0049), when it has one. */
  onReplace?: () => void;
}) {
  const dev = useDevMode();
  const [part, setPart] = useState<Part>(() => partOf(asked));
  // A link to another tab while this page is open (the purge banner, an error).
  useEffect(() => setPart(partOf(asked)), [asked]);
  const [allBackups, setAllBackups] = useState(false);
  const [info, setInfo] = useState<RetentionInfo | null>(null);
  const [days, setDays] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
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

  const shownDays = days ?? info?.settings.retention_days ?? null;
  const reminders = info
    ? (info.settings.reminder_days ?? [info.settings.notice_days])
    : [];

  // One click, one decision, written at once (each write announces the coming purges anew).
  // Writes go one after the other; the value chosen shows meanwhile, and a refusal is said,
  // the value kept shown again. The notice is no longer chosen here: it is kept as it is,
  // never above the keeping.
  const queue = useRef<Promise<void>>(Promise.resolve());
  const setRetentionDays = (value: number) => {
    if (info === null || value === shownDays) return;
    setDays(value);
    const settings = retentionWrite(value, info.settings.notice_days);
    queue.current = queue.current.then(async () => {
      try {
        await api.setRetention(settings);
        setError(null);
      } catch (e) {
        setError((e as Error).message);
      }
      await load();
      setDays((shown) => (shown === value ? null : shown));
    });
  };

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
            <Tab
              key={key}
              value={key}
              label={label}
              endContent={
                key === "transcription" && stepsLeft > 0 ? (
                  <span
                    className="cl-tree__dot cl-settings__dot"
                    data-dot="steps"
                    title="Une mise à jour demande un geste sur ce Mac"
                    aria-label="Une mise à jour demande un geste sur ce Mac"
                  />
                ) : undefined
              }
            />
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

        {part === "seances" && (
          <>
            <section className="cl-settings__section">
              <Heading level={3}>L'audio des séances</Heading>
              <div className="cl-retention__keep">
                <Text>Garder l'audio</Text>
                {shownDays === null ? (
                  <Skeleton width={380} height={36} radius={2} />
                ) : (
                  <SegmentedControl
                    label="Garder l'audio"
                    value={String(shownDays)}
                    onChange={(v) => setRetentionDays(Number(v))}
                  >
                    {retentionChoices(shownDays).map((d) => (
                      <SegmentedControlItem
                        key={d}
                        value={String(d)}
                        label={`${d} jours`}
                      />
                    ))}
                  </SegmentedControl>
                )}
              </div>
              <div className="cl-retention__coming">
                <div className="cl-retention__head">
                  <Text weight="medium">Bientôt supprimés</Text>
                  {info && (
                    <span className="cl-retention__reminders">
                      <Bell size={14} strokeWidth={1.75} aria-hidden />
                      {remindersLine(reminders)}
                    </span>
                  )}
                </div>
                {info === null ? (
                  <RowsSkeleton rows={2} />
                ) : info.coming.length === 0 ? (
                  <Text color="secondary">
                    Aucune séance ne perd son audio d'ici{" "}
                    {Math.max(...reminders, 1)} jours.
                  </Text>
                ) : (
                  <ul className="cl-retention__list">
                    {[...info.coming]
                      .sort((x, y) => x.purge_on.localeCompare(y.purge_on))
                      .map((c) => {
                        const left = daysUntil(c.purge_on);
                        return (
                          <li key={c.session_id}>
                            <span className="cl-settings__text">
                              <a
                                href={`#/seance/${encodeURIComponent(c.session_id)}`}
                              >
                                {name(c)}
                              </a>
                              <Text type="supporting">
                                Audio supprimé le {formatDay(c.purge_on)}
                              </Text>
                            </span>
                            <span
                              className="cl-retention__left"
                              data-close={left <= CLOSE_DAYS || undefined}
                            >
                              {untilWords(left)}
                            </span>
                            <Button
                              size="sm"
                              variant="ghost"
                              label="Garder"
                              clickAction={() =>
                                act(() => api.keepAudio(c.session_id, true))
                              }
                            />
                          </li>
                        );
                      })}
                  </ul>
                )}
              </div>
              {info && (
                <div className="cl-retention__gone">
                  <Text color="secondary">
                    {goneLine(
                      sessionsWithoutAudio(info.journal),
                      info.journal.length >= JOURNAL_LIMIT,
                    )}
                  </Text>
                  {info.journal.length > 0 && (
                    <DeletedPanel journal={info.journal} />
                  )}
                </div>
              )}
            </section>

            <RemindersSection />

            <ExportFolderSection />
          </>
        )}

        {part === "redaction" && <WritingModels />}

        {part === "transcription" && (
          <>
            <ModelsSection
              onReplace={onReplace}
              onOpenFolder={() => void act(() => api.openFolder("modeles"))}
            />
            <LanguagesSection onError={setError} />
          </>
        )}

        {part === "avance" && (
          <>
            <UpdatesSection version={about?.app_version ?? null} />

            <section className="cl-settings__section">
              <Heading level={3}>Dossiers</Heading>
              <Text color="secondary">
                Tout reste sur ce Mac. Le journal technique aide à comprendre
                une erreur.
              </Text>
              <div className="cl-settings__buttons">
                <Button
                  label="Ouvrir les séances"
                  size="sm"
                  onClick={() => void act(() => api.openFolder("donnees"))}
                />
                {folders?.log && (
                  <Button
                    label="Ouvrir le journal technique"
                    size="sm"
                    onClick={() => void act(() => api.openFolder("journal"))}
                  />
                )}
              </div>
              {dev && folders && (
                <Text type="supporting">
                  Données : {folders.data} · modèles : {folders.models}
                  {folders.log ? ` · journal : ${folders.log}` : ""}
                </Text>
              )}
            </section>

            <section className="cl-settings__section">
              <Heading level={3}>Mode développeur</Heading>
              <Switch
                label="Afficher les détails techniques"
                description="Noms des modèles, chemins, provenance des étapes, durées de calcul, mémoire, versions, copies de la base, erreurs brutes."
                value={dev}
                onChange={setDevMode}
              />
              {dev && about && (
                <Text type="supporting">
                  Coulisses {about.app_version}
                  {buildShown(about.app_version, about.app_build) !== null &&
                    ` (code ${about.app_build})`}{" "}
                  · moteur {about.engine_version}{" "}
                  · chaîne « {about.profile} »
                </Text>
              )}
            </section>


            {dev && (
              <section className="cl-settings__section">
                <Heading level={3}>Copies de la base</Heading>
                <Text color="secondary">
                  Une copie est faite quand une mise à jour change le format de
                  la base ; les trois dernières sont gardées, plus celle d'un
                  rapatriement des données. Supprimer une séance l'efface aussi
                  de ces copies.
                </Text>
                {info === null && <RowsSkeleton />}
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
                            {formatBytes(b.bytes)} · {b.name}
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
            )}
            <CreditsSection />
          </>
        )}
      </main>
    </div>
  );
}

/** « 3 séances n'ont déjà plus leur audio ; leur texte est toujours là. » The log read is
 *  the latest only: when it is full, the count is a least. */
function goneLine(count: number, more: boolean): string {
  if (count === 0) return "Aucune séance n'a encore perdu son audio.";
  const least = more ? "Au moins " : "";
  return count === 1
    ? `${least}1 séance n'a déjà plus son audio ; son texte est toujours là.`
    : `${least}${count} séances n'ont déjà plus leur audio ; leur texte est toujours là.`;
}

/** What went, opened from « Déjà supprimés »: a list floating under its trigger, the latest
 *  first, the rest on demand; nothing below moves. */
function DeletedPanel({ journal }: { journal: RetentionInfo["journal"] }) {
  const [isOpen, setOpen] = useState(false);
  const [all, setAll] = useState(false);
  return (
    <Popover
      isOpen={isOpen}
      onOpenChange={(open) => {
        setOpen(open);
        if (!open) setAll(false);
      }}
      label="Déjà supprimés"
      placement="below"
      alignment="end"
      width={380}
      padding={3}
      content={
        <div className="cl-deleted">
          <ul className="cl-settings__list">
            {journal.slice(0, all ? undefined : SHOWN_ROWS).map((e) => (
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
          {journal.length > SHOWN_ROWS && (
            <Button
              size="sm"
              variant="ghost"
              label={
                all
                  ? "N'afficher que les dernières"
                  : journal.length >= JOURNAL_LIMIT
                    ? `Voir les ${JOURNAL_LIMIT} dernières`
                    : `Voir les ${journal.length - SHOWN_ROWS} autres`
              }
              onClick={() => setAll(!all)}
            />
          )}
        </div>
      }
    >
      <button
        type="button"
        className="cl-retention__see"
        aria-label={`Déjà supprimés : ${journal.length >= JOURNAL_LIMIT ? `${JOURNAL_LIMIT} et plus` : journal.length}. Voir`}
      >
        Voir
      </button>
    </Popover>
  );
}

/** While the copies are read: the three rows kept (ADR 0052), at their height. */
function RowsSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <ul
      className="cl-settings__list cl-skeleton"
      aria-busy="true"
      aria-label="Lecture"
    >
      {[0.5, 0.42, 0.56].slice(0, rows).map((w, i) => (
        <li key={i}>
          <span className="cl-settings__text">
            <Skeleton width={`${w * 100}%`} height={14} radius={1} index={i} />
            <Skeleton width="30%" height={11} radius={1} index={i} />
          </span>
        </li>
      ))}
    </ul>
  );
}

/** The usual values of the reminders, as the service keeps them (reminders.py). */
const SILENCE_STEPS = [2, 3, 5, 10, 15, 20, 30];
const DURATION_STEPS = [30, 45, 60, 90, 120, 180, 240];

/** « 5 min », « 1 h », « 1 h 30 ». */
function minutes(value: number): string {
  const hours = Math.floor(value / 60);
  const rest = value % 60;
  if (!hours) return `${rest} min`;
  return rest ? `${hours} h ${String(rest).padStart(2, "0")}` : `${hours} h`;
}

/** What reminds the user that a recording runs (ADR 0054): a notification after a long
 *  silence and at each duration reached, never a stop by itself; the menu bar says it
 *  records all along. Changed in place: each step is kept at once (nothing is announced). */
function RemindersSection() {
  const [kept, setKept] = useState<Reminders | null>(null);
  const [error, setError] = useState<{ title: string; text: string } | null>(
    null,
  );
  const notifications = useAppNotifications();
  useEffect(() => {
    api
      .reminders()
      .then(setKept, (e: Error) =>
        setError({ title: "Réglage non lu", text: e.message }),
      );
  }, []);
  const change = async (next: Reminders) => {
    const before = kept;
    setKept(next);
    try {
      setKept(await api.setReminders(next));
      setError(null);
    } catch (e) {
      setKept(before);
      setError({ title: "Réglage non enregistré", text: (e as Error).message });
    }
  };
  return (
    <section className="cl-settings__section">
      <Heading level={3}>Pendant un enregistrement</Heading>
      {error && (
        <Banner status="error" title={error.title} description={error.text} />
      )}
      {/* Nothing shown before it is read: never values the user did not keep. */}
      {kept === null ? (
        !error && <RowsSkeleton rows={2} />
      ) : (
        <div className="cl-settings__cards">
          <DayStepper
            title="Silence"
            icon={<Mic size={16} strokeWidth={1.75} aria-hidden />}
            label="« C'est fini ? » après un silence de"
            description="Il n'arrête jamais l'enregistrement de lui-même."
            value={kept.silence_min}
            steps={SILENCE_STEPS}
            say={minutes}
            onChange={(v) => void change({ ...kept, silence_min: v })}
          />
          <DayStepper
            title="Rappel"
            icon={<Bell size={16} strokeWidth={1.75} aria-hidden />}
            label="« Ça enregistre toujours » toutes les"
            description="La barre des menus le montre aussi."
            value={kept.duration_min}
            steps={DURATION_STEPS}
            say={minutes}
            onChange={(v) => void change({ ...kept, duration_min: v })}
          />
        </div>
      )}
      {notifications === "denied" && (
        <Text type="supporting">
          macOS bloque les notifications de Coulisses : autorisez-les dans
          Réglages Système, Notifications. La barre des menus rappelle quand
          même l'enregistrement.
        </Text>
      )}
      {notifications === "unknown" && (
        <Text type="supporting">
          macOS demandera d'autoriser les notifications au premier
          enregistrement.
        </Text>
      )}
    </section>
  );
}
