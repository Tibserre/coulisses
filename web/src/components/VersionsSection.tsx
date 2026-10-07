import { useCallback, useEffect, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { Heading } from "@astryxdesign/core/Heading";
import { NumberInput } from "@astryxdesign/core/NumberInput";
import { RadioList, RadioListItem } from "@astryxdesign/core/RadioList";
import { Text } from "@astryxdesign/core/Text";
import { api } from "../api.ts";
import type { Carryover, NotCarried, Rerun, Versions } from "../api.ts";
import { formatClock, formatDateTime, plural } from "../format.ts";
import {
  carriedText,
  rerunMinutes,
  transcribeGain,
  versionOrigin,
} from "../versions.ts";

/** The versions of the session's processing (spec §7.4, §7.6): the one shown, the former
 *  ones (shown again on demand, each with its own corrections), what was not carried over
 *  to the one shown, and « Relancer… ». `version` and `busy` change when the session's
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
          label="Relancer…"
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
        versions={versions}
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

function RerunDialog({
  isOpen,
  sessionId,
  versions,
  duration,
  onClose,
  onAsked,
}: {
  isOpen: boolean;
  sessionId: string;
  versions: Versions;
  duration: number | null;
  onClose: () => void;
  onAsked: () => Promise<void>;
}) {
  const facts = versions.rerun;
  const [stage, setStage] = useState<Rerun>("transcribe");
  const [voices, setVoices] = useState<number | null>(null);
  const [battery, setBattery] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const proposed = voices ?? facts.attendees_now ?? facts.min_voices ?? 1;

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    api.power().then(
      (p) => setBattery(p.on_battery),
      () => setBattery(null), // unknown: nothing said, the rerun is the user's call anyway
    );
  }, [isOpen]);

  const time = rerunMinutes(facts, stage, duration);
  const ask = async () => {
    try {
      await api.rerun(sessionId, stage, stage === "diarize" ? proposed : null);
      await onAsked();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <Dialog
      isOpen={isOpen}
      onOpenChange={(open) => !open && onClose()}
      width={560}
    >
      <DialogHeader title="Relancer une étape" onOpenChange={onClose} />
      <div className="cl-rerun">
        <RadioList
          label="Étape à refaire"
          isLabelHidden
          value={stage}
          onChange={(v) => setStage(v as Rerun)}
        >
          <RadioListItem
            value="transcribe"
            label="La transcription"
            description={`${transcribeGain(facts)} La séparation des voix est gardée.`}
          />
          <RadioListItem
            value="diarize"
            label="La séparation des voix"
            description={`Avec un autre nombre de présents${facts.min_voices ? ` (la dernière fois : au moins ${facts.min_voices})` : ""}. La transcription est gardée.`}
          />
        </RadioList>
        {stage === "diarize" && (
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
        <Text as="p" color="secondary">
          {time
            ? `Environ ${time.minutes} min de calcul${time.measured ? ", comme la dernière fois" : ""}. `
            : ""}
          La version affichée reste en place jusqu'à la fin ; vos corrections
          sont alors reportées sur la nouvelle, et ce qui ne peut pas l'être est
          listé. L'ancienne version reste consultable.
        </Text>
        {battery && (
          <Banner
            status="warning"
            title="Le Mac est sur batterie"
            description="Mieux vaut le brancher : le calcul est long et sollicite la batterie."
          />
        )}
        {error && (
          <Banner status="error" title="Relance refusée" description={error} />
        )}
        <div className="cl-rerun__actions">
          <Button variant="ghost" label="Annuler" onClick={onClose} />
          <Button
            variant="primary"
            label={
              stage === "transcribe"
                ? "Refaire la transcription"
                : "Refaire la séparation des voix"
            }
            clickAction={ask}
          />
        </div>
      </div>
    </Dialog>
  );
}
