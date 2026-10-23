import { useEffect, useState } from "react";
import { Pause, Play } from "lucide-react";
import type { Speaker } from "../api.ts";
import { formatClock, formatDuration, plural } from "../format.ts";
import { turnSeconds, type TurnRow } from "../transcript.ts";
import type { Playback } from "../usePlayback.ts";

/** How many of a voice's lines are listed first; the others on demand (none hidden). */
export const FIRST_LINES = 5;
/** An excerpt is heard for this long at most (usePlayback.listen). */
export const EXCERPT_S = 8;

/** The guided naming's card (ADR 0062), over the veiled page: the lines of the voice being
 *  named, and only them. Where it speaks in the session, a mark per line; its longest
 *  lines first (where it is heard best), or in their order; each heard on a click, or the
 *  ones listed one after the other. Lengths and places are the measured ones (P2); what
 *  cannot be heard says why, in the card (P8). The order and the listening are the page's:
 *  the field's keys (← → Space) drive them too. */
export function NamingCard({
  speaker,
  lines,
  sorted,
  order,
  onOrder,
  current,
  duration,
  pb,
  done,
  total,
  audioGone,
  queueing,
  onPick,
  onHear,
  onQueue,
  onStop,
}: {
  speaker: Speaker;
  /** Its lines, in their order (for the strip). */
  lines: TurnRow[];
  /** Its lines in the order chosen. */
  sorted: TurnRow[];
  order: "long" | "time";
  onOrder: (order: "long" | "time") => void;
  /** The line looked at, by its index in the run. */
  current: number | null;
  /** The session's length, for the strip; 0 when unknown (then no strip). */
  duration: number;
  pb: Playback;
  /** Voices named in this round, out of all those there were to name. */
  done: number;
  total: number;
  audioGone: boolean;
  queueing: boolean;
  onPick: (turn: number) => void;
  onHear: (row: TurnRow) => void;
  onQueue: (rows: TurnRow[]) => void;
  onStop: () => void;
}) {
  const [all, setAll] = useState(false);
  // Another voice: its list starts short again.
  useEffect(() => setAll(false), [speaker.label]);
  const shown = all ? sorted : sorted.slice(0, FIRST_LINES);
  // The line looked at is always listed (picked on the strip, for instance).
  const listed =
    current != null && !shown.some((r) => r.turn.index === current)
      ? [...shown, ...sorted.filter((r) => r.turn.index === current)]
      : shown;
  const playable = audioGone ? [] : listed.filter((r) => r.turn.start != null);
  const queueSeconds = playable.reduce(
    (sum, r) => sum + Math.min(turnSeconds(r.turn) ?? EXCERPT_S, EXCERPT_S),
    0,
  );
  const keep = (e: React.MouseEvent) => e.preventDefault();

  return (
    <div
      className="cl-namingcard"
      role="dialog"
      aria-label={`Les répliques de ${speaker.name}`}
    >
      <div className="cl-namingcard__head">
        <span className="cl-name" data-unnamed title={speaker.name}>
          {speaker.name}
        </span>
        <span className="cl-namingcard__meta">
          {plural(lines.length, "réplique", "répliques")}
          {speaker.seconds > 0
            ? ` · ${formatDuration(speaker.seconds)} de parole`
            : ""}
        </span>
        {total > 1 && (
          <span
            className="cl-namingcard__dots"
            aria-label={`${done} ${done > 1 ? "voix nommées" : "voix nommée"} sur ${total}`}
          >
            {Array.from({ length: total }, (_, i) => (
              <i
                key={i}
                data-state={i < done ? "done" : i === done ? "now" : undefined}
              />
            ))}
          </span>
        )}
      </div>

      {/* What cannot be heard, said (P8). */}
      {audioGone && (
        <p className="cl-namingcard__said">
          L'audio de cette séance a été supprimé : les répliques se lisent,
          elles ne s'écoutent plus.
        </p>
      )}
      {pb.error && !audioGone && (
        <p className="cl-namingcard__said" role="alert">
          {pb.error}
        </p>
      )}

      {lines.length > 1 && duration > 0 && (
        <>
          <span className="cl-namingcard__label">
            Où elle parle dans la séance
          </span>
          <div className="cl-namingcard__strip">
            <span className="cl-namingcard__track" aria-hidden />
            {lines.map((r) =>
              r.turn.start == null ? null : (
                <button
                  key={r.turn.index}
                  type="button"
                  className="cl-namingcard__tick"
                  data-current={r.turn.index === current || undefined}
                  style={{
                    left: `${Math.min(100, (r.turn.start / duration) * 100)}%`,
                  }}
                  aria-label={`Réplique à ${formatClock(r.turn.start)}`}
                  title={formatClock(r.turn.start)}
                  onMouseDown={keep}
                  onClick={() => onPick(r.turn.index)}
                />
              ),
            )}
          </div>
        </>
      )}

      {lines.length > FIRST_LINES && (
        <div className="cl-namingcard__order">
          <div
            className="cl-seg"
            role="tablist"
            aria-label="Ordre des répliques"
          >
            {(
              [
                ["long", "Les plus longues"],
                ["time", "Dans l'ordre"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                role="tab"
                aria-selected={order === value}
                onMouseDown={keep}
                onClick={() => onOrder(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <span className="cl-namingcard__meta">
            {order === "long"
              ? "celles où l'on entend le mieux la voix"
              : "de la première à la dernière"}
          </span>
        </div>
      )}

      <ol className="cl-namingcard__lines">
        {listed.map((r) => {
          const seconds = turnSeconds(r.turn);
          const hearing = pb.excerpt != null && pb.excerpt === r.turn.start;
          const silent = audioGone || r.turn.start == null;
          return (
            <li key={r.turn.index}>
              <button
                type="button"
                className="cl-namingcard__line"
                data-current={r.turn.index === current || undefined}
                onMouseDown={keep}
                onClick={() => (silent ? onPick(r.turn.index) : onHear(r))}
                title={
                  audioGone
                    ? undefined
                    : r.turn.start == null
                      ? "Le début de cette réplique n'est pas mesuré : elle ne s'écoute pas seule"
                      : hearing
                        ? "Arrêter l'écoute"
                        : "Écouter cette réplique"
                }
              >
                <span className="cl-namingcard__play" aria-hidden>
                  {silent ? null : hearing ? (
                    <Pause size={13} strokeWidth={1.75} />
                  ) : (
                    <Play size={13} strokeWidth={1.75} />
                  )}
                </span>
                <span className="cl-namingcard__time">
                  {r.turn.start == null ? "" : formatClock(r.turn.start)}
                </span>
                <span className="cl-namingcard__text">
                  {r.turn.words.map((w) => w.text).join(" ")}
                </span>
                <span className="cl-namingcard__len">
                  {seconds == null
                    ? ""
                    : `${Math.max(1, Math.round(seconds))} s`}
                </span>
              </button>
              {!audioGone &&
                r.turn.index === current &&
                r.turn.start == null && (
                  <p className="cl-namingcard__said">
                    Son début n'est pas mesuré : elle ne s'écoute pas seule.
                  </p>
                )}
            </li>
          );
        })}
      </ol>
      {sorted.length > FIRST_LINES && (
        <button
          type="button"
          className="cl-linkbtn cl-linkbtn--quiet cl-namingcard__more"
          onMouseDown={keep}
          onClick={() => setAll(!all)}
        >
          {all
            ? `Ne garder que les ${FIRST_LINES} premières`
            : `Voir les ${sorted.length - FIRST_LINES} autres`}
        </button>
      )}

      {playable.length > 1 && (
        <div className="cl-namingcard__tools">
          <button
            type="button"
            className="cl-linkbtn cl-linkbtn--quiet"
            onMouseDown={keep}
            onClick={() => (queueing ? onStop() : onQueue(playable))}
          >
            {queueing
              ? "Arrêter"
              : playable.length === lines.length
                ? "Écouter ses répliques à la suite"
                : `Écouter ces ${playable.length} à la suite`}
          </button>
          <span className="cl-namingcard__meta">
            environ {formatDuration(Math.round(queueSeconds))}
          </span>
        </div>
      )}
    </div>
  );
}
