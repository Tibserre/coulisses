import { useEffect, useState } from "react";
import { Text } from "@astryxdesign/core/Text";
import { Check, PenLine, Star } from "lucide-react";
import { api, type Preview, type SessionDetail } from "../api.ts";
import { formatClock } from "../format.ts";
import { outlineRows } from "../outline.ts";
import { KIND_LABEL } from "../transcript.ts";

/** While the session is processed (ADR 0058): the review building itself. A thin line says
 *  where it is; below, the text once transcribed, grey, with what was marked during the
 *  recording at its time; the names come with « who said what », then the review opens.
 *  Read again every few seconds; nothing is kept: the review reads the engine's runs. */
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

  const stages = detail.stages;
  const current = stages.find(
    (s) => s.state === "running" || s.state === "stalled",
  );
  const share = current?.progress?.total
    ? current.progress.done / current.progress.total
    : 0;
  const fraction = stages.length ? (done + share) / stages.length : 0;
  // About ten minutes of computing per hour of audio (spec §7.4): said as « environ ».
  const hours = (detail.source?.duration_s ?? 0) / 3600;
  const left = Math.max(1, Math.round(hours * 10 * (1 - fraction)));
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
  const stalled = stages.some((s) => s.state === "stalled");

  return (
    <section
      className="cl-outline"
      aria-label="La séance en cours de traitement"
    >
      <div className="cl-outline__progress" role="status">
        <div className="cl-outline__track" aria-hidden>
          <i style={{ width: `${Math.round(fraction * 100)}%` }} />
        </div>
        <Text type="supporting">
          {queued
            ? "En file : un autre traitement passe d'abord."
            : stalled
              ? "Une étape ne donne plus de nouvelles depuis un moment : elle s'est peut-être arrêtée. Le détail des étapes est ci-dessous."
              : current
                ? `${current.label}${hours > 0 ? ` · environ ${left} min` : ""}`
                : "Traitement en cours"}
        </Text>
        <ol className="cl-outline__steps">
          {stages.map((s) => (
            <li
              key={s.stage}
              data-state={s.state}
              data-stale={s.stale || undefined}
            >
              {s.state === "succeeded" && (
                <Check size={12} strokeWidth={2} aria-hidden />
              )}
              {s.label}
              {s.stale && " (à refaire)"}
            </li>
          ))}
        </ol>
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
      <Text type="supporting">
        Vous pouvez fermer Coulisses : le traitement reprendra où il en était à
        la prochaine ouverture.
      </Text>
    </section>
  );
}
