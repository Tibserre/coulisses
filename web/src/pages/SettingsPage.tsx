import { useCallback, useEffect, useRef, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { Popover } from "@astryxdesign/core/Popover";
import { Skeleton } from "@astryxdesign/core/Skeleton";
import { Switch } from "@astryxdesign/core/Switch";
import { Tab, TabList } from "@astryxdesign/core/TabList";
import { Text } from "@astryxdesign/core/Text";
import { ChevronDown } from "lucide-react";
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
import { LOG_KIND, formatDay } from "../retention.ts";
import { buildShown, PARTS, partOf, type Part } from "../settingsParts.ts";

/** Lists that only grow (the deletion log, the backups): the latest first, the rest on
 *  demand. */
const SHOWN_ROWS = 5;
/** The usual values the steppers go through: a week, two, a month, a season, a year… */
const RETENTION_STEPS = [7, 14, 30, 60, 90, 120, 180, 270, 365, 730];
const NOTICE_STEPS = [1, 2, 3, 5, 7, 10, 14, 21, 30, 60];
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
  const [notice, setNotice] = useState<number | null>(null);
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

  const shownDays = days ?? info?.settings.retention_days ?? 90;
  const shownNotice = notice ?? info?.settings.notice_days ?? 7;

  // Changed in place (ADR 0051), kept once one leaves the line, the tab or the page: one
  // write per decision, so the coming purges are announced again once, for the delay chosen
  // (each write announces them anew). Writes go one after the other; a refusal is said, and
  // the values shown go back to those kept.
  type Retention = { retention_days: number; notice_days: number };
  const pending = useRef<Retention | null>(null);
  const kept = useRef<RetentionInfo["settings"] | null>(null);
  kept.current = info?.settings ?? null;
  const queue = useRef<Promise<void>>(Promise.resolve());
  const change = (next: { days?: number; notice?: number }) => {
    if (next.days !== undefined) setDays(next.days);
    if (next.notice !== undefined) setNotice(next.notice);
    pending.current = {
      retention_days: next.days ?? shownDays,
      notice_days: next.notice ?? shownNotice,
    };
  };
  const flush = useCallback(
    (leaving = false) => {
      const value = pending.current;
      pending.current = null;
      if (
        value === null ||
        (kept.current?.retention_days === value.retention_days &&
          kept.current?.notice_days === value.notice_days)
      ) {
        if (value !== null) {
          setDays(null);
          setNotice(null);
        }
        return;
      }
      // The page goes away (closed, reloaded): sent at once, and finished by the browser. No
      // page is left to say a refusal; the next opening shows the values kept, as they are.
      if (leaving) {
        void api.setRetention(value, true).catch(() => undefined);
        return;
      }
      queue.current = queue.current.then(async () => {
        try {
          await api.setRetention(value);
          setError(null);
        } catch (e) {
          setError((e as Error).message);
        }
        await load();
        // A change made meanwhile stays shown, to be kept in its turn.
        if (pending.current === null) {
          setDays(null);
          setNotice(null);
        }
      });
    },
    [load],
  );
  useEffect(() => {
    const leave = () => flush(true);
    window.addEventListener("pagehide", leave);
    return () => {
      window.removeEventListener("pagehide", leave);
      flush();
    };
  }, [flush]);
  useEffect(() => {
    if (part !== "seances") flush();
  }, [part, flush]);

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
              <Text color="secondary">
                L'audio d'une séance traitée est supprimé après ce délai, avec
                un préavis ; le texte, les noms et les résumés restent. Une
                séance peut garder son audio depuis son menu « … ».
              </Text>
              <div
                className="cl-settings__steppers"
                onMouseLeave={() => flush()}
                onBlur={(e) => {
                  if (!e.currentTarget.contains(e.relatedTarget as Node | null))
                    flush();
                }}
              >
                <DayStepper
                  label="Garder l'audio"
                  description="Depuis son entrée dans Coulisses."
                  value={shownDays}
                  steps={RETENTION_STEPS}
                  min={Math.max(1, shownNotice)}
                  isDisabled={info === null}
                  onChange={(v) => change({ days: v })}
                />
                <DayStepper
                  label="Prévenir avant"
                  description="Un bandeau et une notification."
                  value={shownNotice}
                  steps={NOTICE_STEPS}
                  max={shownDays}
                  isDisabled={info === null}
                  onChange={(v) => change({ notice: v })}
                />
                {/* Always their lines, so nothing moves once read. */}
                <div className="cl-settings__row">
                  <span className="cl-settings__text">
                    <Text>Bientôt supprimés</Text>
                  </span>
                  <span className="cl-settings__value">
                    {info === null ? (
                      <Skeleton width={60} height={14} radius={1} />
                    ) : (
                      <Text color="secondary">
                        {info.coming.length === 0
                          ? "Aucun"
                          : plural(info.coming.length, "séance", "séances")}
                      </Text>
                    )}
                  </span>
                </div>
                <div className="cl-settings__row">
                  <span className="cl-settings__text">
                    <Text>Déjà supprimés</Text>
                    <Text type="supporting">
                      Chaque suppression et chaque passage en FLAC, avec ses
                      fichiers et leur taille ; jamais le texte d'une séance
                      supprimée.
                    </Text>
                  </span>
                  <span className="cl-settings__value">
                    {info === null ? (
                      <Skeleton width={60} height={14} radius={1} />
                    ) : info.journal.length === 0 ? (
                      <Text color="secondary">Aucun</Text>
                    ) : (
                      <DeletedPanel journal={info.journal} />
                    )}
                  </span>
                </div>
              </div>
              {info && info.coming.length > 0 && (
                <ul className="cl-settings__list">
                  {info.coming.map((c) => (
                    <li key={c.session_id}>
                      <span className="cl-settings__text">
                        <a
                          href={`#/seance/${encodeURIComponent(c.session_id)}`}
                        >
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
              )}
            </section>

            <RemindersSection />

            <ExportFolderSection />
          </>
        )}

        {part === "redaction" && <WritingModels />}

        {part === "transcription" && (
          <>
            <LanguagesSection onError={setError} />
            <ModelsSection onReplace={onReplace} />
            <div className="cl-settings__buttons">
              <Button
                label="Ouvrir le dossier des modèles"
                size="sm"
                variant="ghost"
                onClick={() => void act(() => api.openFolder("modeles"))}
              />
            </div>
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
          </>
        )}
      </main>
    </div>
  );
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
        className="cl-modelpick"
        aria-label={`Déjà supprimés : ${journal.length}. Voir`}
      >
        <span className="cl-modelpick__name">
          {journal.length >= JOURNAL_LIMIT
            ? `${JOURNAL_LIMIT} et plus`
            : journal.length}
        </span>
        <ChevronDown size={16} strokeWidth={1.75} aria-hidden />
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
      <Text color="secondary">
        Coulisses vous demande si la réunion est finie ; il n'arrête jamais
        l'enregistrement de lui-même. La barre des menus montre qu'il
        enregistre.
      </Text>
      {error && (
        <Banner status="error" title={error.title} description={error.text} />
      )}
      {/* Nothing shown before it is read: never values the user did not keep. */}
      {kept === null ? (
        !error && <RowsSkeleton rows={2} />
      ) : (
        <div className="cl-settings__steppers">
          <DayStepper
            label="Prévenir après un silence de"
            description="Personne ne parle, au micro comme dans le son de l'ordinateur."
            value={kept.silence_min}
            steps={SILENCE_STEPS}
            say={minutes}
            onChange={(v) => void change({ ...kept, silence_min: v })}
          />
          <DayStepper
            label="Rappeler toutes les"
            description="Que l'enregistrement tourne toujours."
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
