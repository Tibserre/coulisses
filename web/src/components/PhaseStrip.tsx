import { Button } from "@astryxdesign/core/Button";
import { Text } from "@astryxdesign/core/Text";
import { ListTree, RefreshCw } from "lucide-react";
import type { CorrectedView, PhasesStatus } from "../api.ts";
import { formatClock, plural } from "../format.ts";
import { KIND_LABEL, phaseSpans } from "../transcript.ts";

/** Under the title: one bar per chapter, as long as it lasts, the chapter being heard
 *  named above, and the play head. A click on a bar plays from that chapter. */
export function PhaseStrip({
  view,
  duration,
  time,
  status,
  dev,
  onSeek,
  onDetect,
}: {
  view: CorrectedView;
  duration: number;
  time: number;
  status: PhasesStatus | null;
  dev: boolean;
  onSeek: (t: number) => void;
  onDetect: () => void;
}) {
  const spans = phaseSpans(view, duration);
  // The bars run from the first chapter's start to the last one's end: so does the head.
  const from = spans[0]?.start ?? 0;
  const to = Math.max(from + 1, ...spans.map((s) => s.end));
  const current = [...spans].reverse().find((s) => s.start <= time) ?? spans[0];
  const waiting = status?.state === "queued" || status?.state === "running";

  return (
    <div className="cl-strip">
      <div className="cl-strip__head">
        {current ? (
          <span className="cl-strip__current" data-kind={current.phase.kind}>
            <span className="cl-strip__kind">
              {KIND_LABEL[current.phase.kind]}
            </span>
            {current.phase.title || "Chapitre sans titre"}
          </span>
        ) : (
          !waiting &&
          status?.state !== "failed" && (
            <Text type="supporting">Pas encore de chapitres.</Text>
          )
        )}
        {waiting && (
          // Said, not spun: nothing moves in a loop (art direction).
          <span className="cl-strip__writing" role="status">
            <ListTree size={13} strokeWidth={1.75} aria-hidden />
            Les chapitres s'écrivent · vous pouvez déjà relire
          </span>
        )}
        {status?.state === "failed" && (
          <span className="cl-strip__error">
            Les chapitres n'ont pas pu être détectés :{" "}
            {status.error ?? "erreur inconnue"}
          </span>
        )}
        {view.phases_problem && (
          <span className="cl-strip__error">{view.phases_problem}</span>
        )}
        {dev && view.phases_by_markers.length > 0 && (
          <span
            className="cl-strip__note"
            title={view.phases_by_markers.join("\n")}
          >
            {plural(
              view.phases_by_markers.length,
              "coupure remplacée",
              "coupures remplacées",
            )}{" "}
            par un marqueur
          </span>
        )}
        {dev && status?.state === "done" && status.adjustments.length > 0 && (
          <span
            className="cl-strip__note"
            title={status.adjustments.join("\n")}
          >
            {plural(status.adjustments.length, "ajustement", "ajustements")} de
            la réponse du modèle
          </span>
        )}
        <span className="cl-strip__tools">
          {!waiting &&
            (status?.state === "failed" || spans.length === 0 ? (
              <Button
                size="sm"
                variant="ghost"
                label={
                  status?.state === "failed"
                    ? "Relancer"
                    : "Détecter les chapitres"
                }
                clickAction={onDetect}
              />
            ) : (
              <button
                type="button"
                className="cl-iconbtn"
                aria-label="Détecter les chapitres à nouveau"
                title="Détecter les chapitres à nouveau (vos changements restent)"
                onClick={onDetect}
              >
                <RefreshCw size={14} strokeWidth={1.75} />
              </button>
            ))}
        </span>
      </div>
      {spans.length > 0 && (
        <div className="cl-strip__bars">
          {spans.map((s) => (
            <button
              key={s.phase.turn}
              type="button"
              className="cl-strip__bar"
              data-kind={s.phase.kind}
              data-current={s === current || undefined}
              style={{ flexGrow: Math.max(s.end - s.start, 1) }}
              title={`${s.phase.title || "Chapitre sans titre"} · ${formatClock(s.start)}`}
              aria-label={`Chapitre ${s.number}, ${KIND_LABEL[s.phase.kind].toLowerCase()} : ${s.phase.title || "sans titre"}, à ${formatClock(s.start)}`}
              onClick={(e) => {
                onSeek(s.start);
                e.currentTarget.blur();
              }}
            />
          ))}
          {view.markers
            .filter(
              (m) => m.kind === "key_moment" && m.at_s >= from && m.at_s <= to,
            )
            .map((m) => (
              <button
                key={m.id}
                type="button"
                className="cl-strip__moment"
                style={{ left: `${((m.at_s - from) / (to - from)) * 100}%` }}
                title={`Moment clé à ${formatClock(m.at_s)}`}
                aria-label={`Moment clé à ${formatClock(m.at_s)}`}
                onClick={(e) => {
                  onSeek(m.at_s);
                  e.currentTarget.blur();
                }}
              />
            ))}
          <span
            className="cl-strip__head-mark"
            style={{
              left: `${Math.min(100, Math.max(0, ((time - from) / (to - from)) * 100))}%`,
            }}
            aria-hidden
          />
        </div>
      )}
    </div>
  );
}
