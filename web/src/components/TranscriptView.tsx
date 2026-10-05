import { memo, useEffect, useRef } from "react";
import { Tooltip } from "@astryxdesign/core/Tooltip";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Play } from "lucide-react";
import { motion } from "motion/react";
import type { AttributedWord } from "../api.ts";
import { formatClock } from "../format.ts";
import type { ReviewModel, Row, TurnRow } from "../transcript.ts";
import type { Playback } from "../usePlayback.ts";

/** Below this confidence a word is underlined, when the engine gives one (spec §7.6). */
const UNSURE_BELOW = 0.5;

/** The art direction's curve: lively start, soft landing, no bounce. */
const GLIDE = { duration: 0.16, ease: [0.22, 1, 0.36, 1] } as const;

function Word({
  word,
  isCurrent,
}: {
  word: AttributedWord;
  isCurrent: boolean;
}) {
  const unsure = word.confidence != null && word.confidence < UNSURE_BELOW;
  const inner = (
    <span className="cl-word" data-unsure={unsure || undefined}>
      {isCurrent && (
        <motion.span
          layoutId="mot-courant"
          className="cl-word__current"
          transition={GLIDE}
          aria-hidden
        />
      )}
      {word.text}
    </span>
  );
  if (!unsure) return inner;
  return (
    <Tooltip
      content={`Mot peu sûr, confiance ${Math.round((word.confidence ?? 0) * 100)} %`}
      hasHoverIndication={false}
    >
      {inner}
    </Tooltip>
  );
}

function TimeLink({
  t,
  isCurrent,
  onSeek,
}: {
  t: number | null;
  isCurrent: boolean;
  onSeek: (t: number) => void;
}) {
  if (t == null) {
    return (
      <span className="cl-time" title="Début non mesuré">
        —
      </span>
    );
  }
  return (
    <button
      type="button"
      className="cl-time"
      data-current={isCurrent || undefined}
      onClick={(e) => {
        onSeek(t);
        // Hand the keyboard back to the player: Space plays or pauses again.
        e.currentTarget.blur();
      }}
      aria-label={`Lire à partir de ${formatClock(t)}`}
    >
      <span className="cl-time__label">{formatClock(t)}</span>
      <span className="cl-time__play" aria-hidden>
        <Play size={14} strokeWidth={2} fill="currentColor" />
      </span>
    </button>
  );
}

const TurnLine = memo(function TurnLine({
  row,
  currentWord,
  onSeek,
}: {
  row: TurnRow;
  /** Index of the word being heard in this turn; -1 if this turn is not being heard. */
  currentWord: number | null;
  onSeek: (t: number) => void;
}) {
  const isCurrent = currentWord !== null;
  return (
    <div className="cl-turn" data-current={isCurrent || undefined}>
      <TimeLink t={row.start} isCurrent={isCurrent} onSeek={onSeek} />
      <div className="cl-turn__body">
        <span className="cl-name" data-unnamed>
          {row.speaker.name}
        </span>
        <p className="cl-words">
          {row.words.map((w, i) => (
            <span key={i}>
              <Word word={w} isCurrent={currentWord === i} />
              {i < row.words.length - 1 ? " " : ""}
            </span>
          ))}
        </p>
      </div>
    </div>
  );
});

/** The whole transcript, virtualised: two hours are thousands of turns (rules/web.md). */
export function TranscriptView({
  model,
  pb,
  current,
}: {
  model: ReviewModel;
  pb: Playback;
  current: { row: TurnRow; word: number } | null;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: model.rows.length,
    getScrollElement: () => scroller.current,
    estimateSize: () => 96,
    overscan: 8,
    getItemKey: (i) => model.rows[i].key,
  });

  const currentIndex = current ? model.rows.indexOf(current.row) : -1;

  // An explicit move (click on a time, previous / next) brings the line to the centre.
  const lastMoves = useRef(pb.moves);
  useEffect(() => {
    if (pb.moves !== lastMoves.current && currentIndex >= 0) {
      lastMoves.current = pb.moves;
      virtualizer.scrollToIndex(currentIndex, { align: "center" });
    }
  }, [pb.moves, currentIndex, virtualizer]);

  // While playing, follow the sound only when the line leaves the screen: the page stays
  // calm. Never on first display.
  useEffect(() => {
    if (!pb.playing || currentIndex < 0) return;
    const visible = virtualizer.getVirtualItems();
    const first = visible.find(
      (v) => v.start >= (virtualizer.scrollOffset ?? 0),
    );
    const last = visible[visible.length - 1];
    if (
      !first ||
      !last ||
      currentIndex < first.index ||
      currentIndex >= last.index
    ) {
      virtualizer.scrollToIndex(currentIndex, { align: "start" });
    }
  }, [currentIndex, pb.playing, virtualizer]);

  return (
    <div ref={scroller} className="cl-transcript" aria-label="Transcription">
      <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
        {virtualizer.getVirtualItems().map((item) => {
          const row: Row = model.rows[item.index];
          return (
            <div
              key={item.key}
              data-index={item.index}
              ref={virtualizer.measureElement}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                right: 0,
                transform: `translateY(${item.start}px)`,
              }}
            >
              {row.kind === "turn" ? (
                <TurnLine
                  row={row}
                  currentWord={current?.row === row ? current.word : null}
                  onSeek={pb.seek}
                />
              ) : (
                <div className="cl-gap">
                  <TimeLink t={row.start} isCurrent={false} onSeek={pb.seek} />
                  <span>
                    Passage non transcrit, {formatClock(row.start)} – {formatClock(row.end)}. L'audio
                    reste à écouter.
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
