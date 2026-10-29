import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { Heading } from "@astryxdesign/core/Heading";
import { NumberInput } from "@astryxdesign/core/NumberInput";
import { Text } from "@astryxdesign/core/Text";
import { FileText, Users } from "lucide-react";
import { api } from "../api.ts";
import type {
  Carryover,
  NotCarried,
  Rerun,
  RerunFacts,
  Versions,
} from "../api.ts";
import { formatClock, formatDateTime, plural } from "../format.ts";
import {
  carriedText,
  rerunMinutes,
  transcribeGain,
  versionOrigin,
} from "../versions.ts";

/** The versions of the session's processing (spec §7.4, §7.6): the one shown, the former
 *  ones (shown again on demand, each with its own corrections), what was not carried over
 *  to the one shown, and « Refaire le traitement… ». `version` and `busy` change when the session's
 *  processing does: the list is read again then. */
export function VersionsSection({
  sessionId,
  version,
  busy,
  carryover,
  duration,
  dev,
  onChanged,
  onSeek,
}: {
  sessionId: string;
  version: string | null;
  busy: boolean;
  carryover: Carryover | null;
  duration: number | null;
  dev: boolean;
  /** The version shown or the processing changed: the page reads the session again. */
  onChanged: () => Promise<void>;
  onSeek: (seconds: number) => void;
}) {
  const [versions, setVersions] = useState<Versions | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);

  const load = useCallback(async () => {
    try {
      setVersions(await api.versions(sessionId));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [sessionId]);
  useEffect(() => {
    void load();
  }, [load, version, busy]);

  const show = async (runId: string) => {
    try {
      setVersions(await api.showVersion(sessionId, runId));
      setError(null);
      await onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  if (!versions)
    return error ? (
      <Banner status="error" title="Versions illisibles" description={error} />
    ) : null;
  const facts = versions.rerun;
  return (
    <section className="cl-versions">
      <Heading level={3}>Versions du traitement</Heading>
      <ol className="cl-versions__list">
        {versions.versions.map((v) => (
          <li key={v.run_id} data-shown={v.shown || undefined}>
            <div className="cl-versions__text">
              <Text weight={v.shown ? "medium" : undefined}>
                Version {v.number}
                <span className="cl-versions__origin">
                  {" "}
                  · {versionOrigin(v)}
                </span>
              </Text>
              <Text type="supporting">
                {v.finished_at
                  ? formatDateTime(v.finished_at)
                  : "date inconnue"}
                {v.corrections > 0 &&
                  ` · ${plural(v.corrections, "correction", "corrections")}`}
              </Text>
              {carriedText(v) && (
                <Text type="supporting">{carriedText(v)}</Text>
              )}
              {dev && (
                <Text type="supporting">
                  <code className="cl-code">{v.run_id}</code>
                  {v.engine_version && ` · moteur ${v.engine_version}`}
                </Text>
              )}
            </div>
            {v.shown ? (
              <Text type="supporting">affichée</Text>
            ) : (
              <Button
                size="sm"
                variant="ghost"
                label="Afficher"
                isDisabled={busy}
                clickAction={() => show(v.run_id)}
              />
            )}
          </li>
        ))}
      </ol>
      {carryover && carryover.not_carried.length > 0 && (
        <NotCarriedList carryover={carryover} onSeek={onSeek} />
      )}
      <div>
        <Button
          size="sm"
          label="Refaire le traitement…"
          isDisabled={!facts.possible}
          clickAction={() => setAsking(true)}
        />
      </div>
      {!facts.possible && facts.why_not && (
        <Text type="supporting">{facts.why_not}</Text>
      )}
      {error && (
        <Text as="p" color="primary" type="supporting">
          {error}
        </Text>
      )}
      <RerunDialog
        isOpen={asking}
        sessionId={sessionId}
        duration={duration}
        onClose={() => setAsking(false)}
        onAsked={async () => {
          setAsking(false);
          await onChanged();
          await load();
        }}
      />
    </section>
  );
}

/** What could not be carried over to the version shown, with why: listed, never dropped
 *  (P8). A click on the time goes to the passage, to correct it again by hand. */
export function NotCarriedList({
  carryover,
  onSeek,
}: {
  carryover: Carryover;
  onSeek: (seconds: number) => void;
}) {
  return (
    <div className="cl-notcarried" id="non-reportees">
      <Text weight="medium">
        {plural(
          carryover.not_carried.length,
          "correction à reprendre",
          "corrections à reprendre",
        )}
      </Text>
      <Text type="supporting">
        Elles restent sur la version précédente. Reprenez-les ici à la main si
        besoin.
      </Text>
      <ol className="cl-notcarried__list">
        {carryover.not_carried.map((c) => (
          <NotCarriedItem key={c.edit_id} item={c} onSeek={onSeek} />
        ))}
      </ol>
    </div>
  );
}

const LONG_TEXT = 220;

function NotCarriedItem({ item, onSeek }: { item: NotCarried; onSeek: (seconds: number) => void }) {
  const [whole, setWhole] = useState(false);
  // « Texte corrigé à 1:16 » next to its time, clickable: the time is said once.
  const what =
    item.at_s != null ? item.description.replace(` à ${formatClock(item.at_s)}`, "") : item.description;
  const long = (item.text?.length ?? 0) > LONG_TEXT;
  return (
    <li>
      <div className="cl-notcarried__head">
        {item.at_s != null && (
          <button
            type="button"
            className="cl-linkbtn cl-notcarried__time"
            onClick={() => onSeek(item.at_s!)}
            title="Aller à ce passage"
          >
            {formatClock(item.at_s)}
          </button>
        )}
        <Text>{what}</Text>
      </div>
      <Text type="supporting">{item.reason.charAt(0).toUpperCase() + item.reason.slice(1)}.</Text>
      {item.text && (
        <p className="cl-notcarried__text" data-clamped={long && !whole ? true : undefined}>
          {item.text}
        </p>
      )}
      {long && (
        <div>
          <button type="button" className="cl-linkbtn cl-notcarried__more" onClick={() => setWhole(!whole)}>
            {whole ? "Replier" : "Tout afficher"}
          </button>
        </div>
      )}
    </li>
  );
}

const CHOICES: {
  value: Rerun;
  label: string;
  icons: ReactNode;
}[] = [
  {
    value: "all",
    label: "Tout",
    icons: (
      <>
        <FileText size={20} strokeWidth={1.75} aria-hidden />
        <Users size={20} strokeWidth={1.75} aria-hidden />
      </>
    ),
  },
  {
    value: "transcribe",
    label: "Le texte",
    icons: <FileText size={20} strokeWidth={1.75} aria-hidden />,
  },
  {
    value: "diarize",
    label: "Les voix",
    icons: <Users size={20} strokeWidth={1.75} aria-hidden />,
  },
];

const ACTION: Record<Rerun, string> = {
  all: "Tout refaire",
  transcribe: "Refaire le texte",
  diarize: "Refaire les voix",
};

/** What a rerun redoes and keeps, in a sentence. */
function rerunSays(stage: Rerun, facts: RerunFacts): string {
  if (stage === "all")
    return "Le texte et les voix sont refaits depuis l'audio, avec le glossaire de l'espace tel qu'il est aujourd'hui.";
  if (stage === "transcribe")
    return `${transcribeGain(facts)} Les voix sont gardées.`;
  return `Le texte est gardé${facts.min_voices ? ` ; la dernière fois, au moins ${plural(facts.min_voices, "voix a été cherchée", "voix ont été cherchées")}` : ""}.`;
}

/** « Refaire le traitement » (spec §7.4): all of it, the text, or the voices, from the
 *  version shown. Its facts are read when it opens. */
export function RerunDialog({
  isOpen,
  sessionId,
  duration,
  onClose,
  onAsked,
  from = "all",
}: {
  isOpen: boolean;
  sessionId: string;
  duration: number | null;
  onClose: () => void;
  onAsked: () => Promise<void>;
  /** The tile chosen on opening: « Tout », unless asked from the people present (the voices). */
  from?: Rerun;
}) {
  const [facts, setFacts] = useState<RerunFacts | null>(null);
  const [stage, setStage] = useState<Rerun>("all");
  const [voices, setVoices] = useState<number | null>(null);
  const [battery, setBattery] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    // Each opening starts afresh, from « Tout » (or the tile it was asked for).
    setStage(from);
    setError(null);
    setVoices(null);
    setFacts(null);
    api.versions(sessionId).then(
      (v) => setFacts(v.rerun),
      (e: Error) => setError(e.message),
    );
    api.power().then(
      (p) => setBattery(p.on_battery),
      () => setBattery(null), // unknown: nothing said, the rerun is the user's call anyway
    );
  }, [isOpen, sessionId, from]);

  const proposed = voices ?? facts?.attendees_now ?? facts?.min_voices ?? 1;
  const time = facts ? rerunMinutes(facts, stage, duration) : null;
  const withVoices = stage !== "transcribe";
  const ask = async () => {
    try {
      await api.rerun(sessionId, stage, withVoices ? proposed : null);
      await onAsked();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <Dialog
      isOpen={isOpen}
      onOpenChange={(open) => !open && onClose()}
      width={520}
    >
      <DialogHeader title="Refaire le traitement" onOpenChange={onClose} />
      <div className="cl-rerun">
        <div
          className="cl-rerun__choices"
          role="radiogroup"
          aria-label="Ce qui est refait"
        >
          {CHOICES.map((c, i) => (
            <button
              key={c.value}
              type="button"
              role="radio"
              aria-checked={stage === c.value}
              // One tile in the tab order, the arrows go from one to the next (radio group).
              tabIndex={stage === c.value ? 0 : -1}
              className="cl-rerun__choice"
              onClick={() => setStage(c.value)}
              onKeyDown={(e) => {
                const step =
                  e.key === "ArrowRight" || e.key === "ArrowDown"
                    ? 1
                    : e.key === "ArrowLeft" || e.key === "ArrowUp"
                      ? -1
                      : 0;
                if (!step) return;
                e.preventDefault();
                const next = (i + step + CHOICES.length) % CHOICES.length;
                setStage(CHOICES[next].value);
                const tiles =
                  e.currentTarget.parentElement?.querySelectorAll("button");
                tiles?.[next]?.focus();
              }}
            >
              <span className="cl-rerun__icons">{c.icons}</span>
              {c.label}
            </button>
          ))}
        </div>
        {facts && (
          <Text as="p" color="secondary">
            {rerunSays(stage, facts)}
          </Text>
        )}
        {withVoices && facts && (
          <div className="cl-rerun__voices">
            <NumberInput
              label="Nombre de présents"
              description="Au moins autant de voix seront cherchées, jamais moins."
              value={proposed}
              onChange={(v) =>
                setVoices(Number.isFinite(v) && v >= 1 ? Math.round(v) : null)
              }
            />
          </div>
        )}
        <Text as="p" type="supporting">
          {time
            ? `Environ ${time.minutes} min${time.measured ? ", comme la dernière fois" : ""}. `
            : ""}
          La séance reste lisible pendant ce temps. À la fin, vos corrections
          sont reportées sur la nouvelle version, et l'ancienne reste dans
          « Versions ».
        </Text>
        {battery && (
          <Banner
            status="warning"
            title="Le Mac est sur batterie"
            description="Mieux vaut le brancher : le calcul est long et sollicite la batterie."
          />
        )}
        {facts && !facts.possible && (
          <Banner
            status="info"
            title="Pas maintenant"
            description={
              facts.why_not ??
              "Le traitement de cette séance ne peut pas être refait pour l'instant."
            }
          />
        )}
        {error && (
          <Banner status="error" title="Relance refusée" description={error} />
        )}
        <div className="cl-rerun__actions">
          <Button variant="ghost" label="Annuler" onClick={onClose} />
          <Button
            variant="primary"
            label={ACTION[stage]}
            isDisabled={!facts?.possible}
            clickAction={ask}
          />
        </div>
      </div>
    </Dialog>
  );
}
