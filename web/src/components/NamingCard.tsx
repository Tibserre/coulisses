import { useEffect, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";
import type { Speaker } from "../api.ts";
import { formatClock, formatDuration, plural } from "../format.ts";
import {
  namingLines,
  nearestLine,
  tickWidth,
  turnSeconds,
  type TurnRow,
} from "../transcript.ts";
import type { Playback } from "../usePlayback.ts";

/** How many of the longest lines « à la suite » hears. */
export const FIRST_LINES = 5;
/** An excerpt is heard for this long at most (usePlayback.listen). */
export const EXCERPT_S = 8;

/** The guided naming's card (ADR 0062), over the veiled page: the voice being named, and
 *  only its lines. The line looked at keeps its own place, large, with ▶ (nothing is added
 *  to a list, nothing jumps). Under it, where the voice speaks in the session: a strip
 *  that is run over rather than aimed at, the line nearest the pointer lit and shown, a
 *  click anywhere taking it. Its lines in a list only on demand. Times and lengths are the
 *  measured ones (P2); what cannot be heard says why (P8). The listening is the page's: the
 *  field's keys (← → Space) drive it too. */
export function NamingCard({
  speaker,
  lines,
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
  /** Its lines, in their order. */
  lines: TurnRow[];
  /** The line looked at. */
  current: TurnRow;
  /** The session's length, for the strip; 0 when unknown (then the list instead). */
  duration: number;
  pb: Playback;
  /** Voices named in this round, out of all those there were to name. */
  done: number;
  total: number;
  audioGone: boolean;
  queueing: boolean;
  /** A line looked at (and heard, if it can be). */
  onHear: (row: TurnRow) => void;
  onPick: (row: TurnRow) => void;
  onQueue: (rows: TurnRow[]) => void;
  onStop: () => void;
}) {
  const [listing, setListing] = useState(false);
  // Another voice: back to the strip.
  useEffect(() => setListing(false), [speaker.label]);
  const strip = useRef<HTMLDivElement>(null);
  const [near, setNear] = useState<TurnRow | null>(null);
  const timed = lines.filter((r) => r.turn.start != null);
  const showStrip = duration > 0 && timed.length > 1;
  const keep = (e: React.MouseEvent) => e.preventDefault();

  /** The line whose start is nearest the pointer, on the strip. */
  const nearest = (clientX: number): TurnRow | null => {
    const box = strip.current?.getBoundingClientRect();
    if (!box) return null;
    return nearestLine(timed, ((clientX - box.left) / box.width) * duration);
  };
  const place = (t: number) =>
    `${Math.min(100, Math.max(0, (t / duration) * 100))}%`;

  const longest = namingLines(lines, "long")
    .filter((r) => r.turn.start != null)
    .slice(0, FIRST_LINES);
  const queueSeconds = longest.reduce(
    (sum, r) => sum + Math.min(turnSeconds(r.turn) ?? EXCERPT_S, EXCERPT_S),
    0,
  );
  const seconds = turnSeconds(current.turn);
  const hearing = pb.excerpt != null && pb.excerpt === current.turn.start;
  const silent = audioGone || current.turn.start == null;
  const position = lines.indexOf(current) + 1;

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

      {/* The line looked at: its own place, large; nothing around it moves. */}
      <div className="cl-namingcard__focus">
        <button
          type="button"
          className="cl-namingcard__hear"
          onMouseDown={keep}
          onClick={() => (hearing ? onStop() : onHear(current))}
          disabled={silent}
          aria-label={
            audioGone
              ? "L'audio de cette séance a été supprimé"
              : current.turn.start == null
                ? "Le début de cette réplique n'est pas mesuré : elle ne s'écoute pas seule"
                : hearing
                  ? "Arrêter l'écoute (Espace)"
                  : "Écouter cette réplique (Espace)"
          }
          title={
            current.turn.start == null && !audioGone
              ? "Le début de cette réplique n'est pas mesuré : elle ne s'écoute pas seule"
              : undefined
          }
        >
          {hearing ? (
            <Pause size={14} strokeWidth={1.75} />
          ) : (
            <Play size={14} strokeWidth={1.75} />
          )}
        </button>
        <div className="cl-namingcard__said-line" key={current.turn.index}>
          <span className="cl-namingcard__meta" aria-live="polite">
            {current.turn.start == null
              ? "heure non mesurée"
              : formatClock(current.turn.start)}
            {seconds == null ? "" : ` · ${Math.max(1, Math.round(seconds))} s`}
            {lines.length > 1
              ? ` · réplique ${position} sur ${lines.length}`
              : ""}
          </span>
          <span className="cl-namingcard__text">
            {current.turn.words.map((w) => w.text).join(" ")}
          </span>
        </div>
      </div>

      {showStrip && !listing && (
        <>
          <div
            ref={strip}
            className="cl-namingcard__strip"
            // Run over with the pointer; its equivalent for the keyboard and the screen
            // readers: the field's ← → and the list (« Voir ses … répliques »).
            aria-hidden
            onMouseDown={keep}
            onPointerMove={(e) => setNear(nearest(e.clientX))}
            onPointerLeave={() => setNear(null)}
            onClick={(e) => {
              const row = nearest(e.clientX);
              if (!row) return;
              setNear(null);
              if (audioGone) onPick(row);
              else onHear(row);
            }}
          >
            <span className="cl-namingcard__track" aria-hidden />
            {timed.map((r) => (
              <i
                key={r.turn.index}
                className="cl-namingcard__tick"
                data-state={
                  r === current ? "current" : r === near ? "near" : undefined
                }
                style={{
                  left: place(r.turn.start!),
                  width: `${tickWidth(r.turn)}px`,
                }}
                aria-hidden
              />
            ))}
            {near && near !== current && (
              <span
                className="cl-namingcard__peek"
                // Held inside the card near its edges.
                style={{
                  left: `clamp(7.5rem, ${place(near.turn.start!)}, calc(100% - 7.5rem))`,
                }}
                aria-hidden
              >
                <span className="cl-namingcard__meta">
                  {formatClock(near.turn.start!)}
                  {turnSeconds(near.turn) != null
                    ? ` · ${Math.max(1, Math.round(turnSeconds(near.turn)!))} s`
                    : ""}
                </span>
                {near.turn.words.map((w) => w.text).join(" ")}
              </span>
            )}
          </div>
          <div className="cl-namingcard__ends" aria-hidden>
            <span>0:00</span>
            <span>
              Où elle parle dans la séance
              {timed.length < lines.length
                ? ` · dont ${lines.length - timed.length} sans heure mesurée, dans la liste`
                : ""}
            </span>
            <span>{formatClock(duration)}</span>
          </div>
        </>
      )}

      {(listing || !showStrip) && lines.length > 1 && (
        <ol className="cl-namingcard__lines">
          {lines.map((r) => {
            const s = turnSeconds(r.turn);
            return (
              <li key={r.turn.index}>
                <button
                  type="button"
                  className="cl-namingcard__line"
                  data-current={r === current || undefined}
                  onMouseDown={keep}
                  onClick={() =>
                    audioGone || r.turn.start == null ? onPick(r) : onHear(r)
                  }
                >
                  <span className="cl-namingcard__time">
                    {r.turn.start == null ? "" : formatClock(r.turn.start)}
                  </span>
                  <span className="cl-namingcard__text">
                    {r.turn.words.map((w) => w.text).join(" ")}
                  </span>
                  <span className="cl-namingcard__time">
                    {s == null ? "" : `${Math.max(1, Math.round(s))} s`}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      )}

      {lines.length > 1 && (
        <div className="cl-namingcard__tools">
          {showStrip && (
            <button
              type="button"
              className="cl-linkbtn cl-linkbtn--quiet"
              onMouseDown={keep}
              onClick={() => setListing(!listing)}
            >
              {listing
                ? "Revenir à la frise"
                : `Voir ses ${lines.length} répliques en liste`}
            </button>
          )}
          {!audioGone && longest.length > 1 && (
            <button
              type="button"
              className="cl-linkbtn cl-linkbtn--quiet"
              onMouseDown={keep}
              onClick={() => (queueing ? onStop() : onQueue(longest))}
            >
              {queueing
                ? "Arrêter"
                : `Écouter ${longest.length === lines.length ? "ses répliques" : `les ${longest.length} plus longues`} à la suite · environ ${formatDuration(Math.round(queueSeconds))}`}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
