import { useEffect, useState } from "react";
import { Text } from "@astryxdesign/core/Text";
import { FileText, PenLine, Star, Users } from "lucide-react";
import { api, type Preview, type SessionDetail } from "../api.ts";
import { formatClock } from "../format.ts";
import { outlineRows } from "../outline.ts";
import { processingDiscs } from "../processing.ts";
import { KIND_LABEL } from "../transcript.ts";

/** A big disc whose ring fills as the engine says (400 ms to each new share): the disc
 *  never moves, only its ring (animation of the processing, art direction). */
function Disc({
  share,
  icon,
  label,
}: {
  share: number;
  icon: React.ReactNode;
  label: string;
}) {
  const r = 34;
  const length = 2 * Math.PI * r;
  return (
    <div className="cl-disc">
      <span className="cl-disc__face">
        <svg
          className="cl-disc__track"
          width="72"
          height="72"
          viewBox="0 0 72 72"
          aria-hidden
        >
          <circle cx="36" cy="36" r={r} className="cl-disc__ground" />
          <circle
            cx="36"
            cy="36"
            r={r}
            className="cl-disc__ring"
            strokeDasharray={length}
            strokeDashoffset={length * (1 - share)}
          />
        </svg>
        {icon}
      </span>
      <Text type="supporting">{label}</Text>
    </div>
  );
}

/** While the session is processed (ADR 0058): two discs, « Le texte » and « Les voix »,
 *  which the engine makes at the same time, then « Qui a dit quoi »; below, the text once
 *  transcribed, grey, with what was marked during the recording at its time. The names
 *  come with « who said what », then the review opens. Read again every few seconds;
 *  nothing is kept: the review reads the engine's runs. */
export function ProcessingOutline({ detail }: { detail: SessionDetail }) {
  const [outline, setOutline] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const id = detail.session.id;
  const done = detail.stages.filter((s) => s.state === "succeeded").length;
  useEffect(() => {
    let gone = false;
    const read = () =>
      api.preview(id).then(
        (next) => {
          if (!gone) {
            setOutline(next);
            setError(null);
          }
        },
        (e: Error) => !gone && setError(e.message),
      );
    void read();
    const timer = window.setInterval(() => void read(), 4000);
    return () => {
      gone = true;
      window.clearInterval(timer);
    };
  }, [id, done]);

  const discs = processingDiscs(
    detail.stages,
    detail.source?.duration_s ?? null,
  );
  const queued = detail.session.job_state === "queued";

  const lines = outline?.lines ?? [];
  const marks = [
    ...(outline?.markers ?? []).map((m) => ({
      key: `m${m.id}`,
      at: m.at_s,
      kind: m.kind,
      text: m.kind === "key_moment" ? "Moment clé" : KIND_LABEL[m.kind],
    })),
    ...(outline?.notes ?? []).map((n) => ({
      key: `n${n.id}`,
      at: n.at_s,
      kind: "note",
      text: n.text,
    })),
  ];
  const rows = outlineRows(
    lines.map((l, i) => ({
      key: `l${i}`,
      at: l.start,
      kind: "line",
      text: l.text,
    })),
    marks,
  );

  return (
    <section
      className="cl-outline"
      aria-label="La séance en cours de traitement"
    >
      <div className="cl-outline__discs" role="status">
        <div className="cl-outline__pair">
          <Disc
            share={discs.text}
            label="Le texte"
            icon={<FileText size={30} strokeWidth={1.5} aria-hidden />}
          />
          <Disc
            share={discs.voices}
            label={
              discs.voices >= 1 && !discs.joining
                ? "Les voix · prêtes"
                : "Les voix"
            }
            icon={<Users size={30} strokeWidth={1.5} aria-hidden />}
          />
        </div>
        <Text type="supporting">
          {queued
            ? "En file : un autre traitement passe d'abord."
            : discs.stalled
              ? "Une étape ne donne plus de nouvelles depuis un moment : elle s'est peut-être arrêtée. Le détail des étapes est ci-dessous."
              : discs.joining
                ? "Qui a dit quoi · quelques secondes"
                : `${discs.minutesLeft !== null ? `environ ${discs.minutesLeft} min · ` : ""}vous pouvez fermer Coulisses`}
        </Text>
      </div>
      {error && (
        <Text type="supporting">L'aperçu n'a pas pu être lu : {error}</Text>
      )}
      {outline !== null && lines.length === 0 && (
        <Text color="secondary">
          Le texte arrive dès que la transcription est faite.
        </Text>
      )}
      <ol className="cl-outline__lines">
        {rows.map((r) => (
          <li key={r.key} className="cl-outline__line" data-kind={r.kind}>
            <span className="cl-rec__at">
              {r.at === null ? "" : formatClock(r.at)}
            </span>
            <span className="cl-outline__text">
              {r.kind === "note" && (
                <PenLine size={13} strokeWidth={1.75} aria-hidden />
              )}
              {r.kind === "key_moment" && (
                <Star size={13} strokeWidth={1.75} aria-hidden />
              )}{" "}
              {r.text}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
