import { memo, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Popover } from "@astryxdesign/core/Popover";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowRightLeft, Play, RotateCcw, SpellCheck } from "lucide-react";
import { motion } from "motion/react";
import type { EditRequest, Person, Speaker, Word as WordData } from "../api.ts";
import { formatClock } from "../format.ts";
import { speakerInk } from "../theme/shared.ts";
import type { ReviewModel, Row, TurnRow } from "../transcript.ts";
import { speakerTitle } from "../transcript.ts";
import type { Playback } from "../usePlayback.ts";
import { NamePanel } from "./NamePanel.tsx";

/** Below this confidence a word is underlined, when the engine gives one (spec §7.6). */
const UNSURE_BELOW = 0.5;

/** The art direction's curve: lively start, soft landing, no bounce. */
const GLIDE = { duration: 0.16, ease: [0.22, 1, 0.36, 1] } as const;

/** What the lines need to correct the transcript. */
export interface Editing {
  people: Person[];
  correct: (correction: EditRequest) => Promise<void>;
  addGuest: (name: string) => Promise<Person>;
  resetText: (turn: number) => Promise<void>;
  /** A request to put the cursor in a line's text (E), by its index in the run. */
  editingTurn: number | null;
  setEditingTurn: (turn: number | null) => void;
  /** Line whose voice is being named. */
  namingTurn: number | null;
  setNamingTurn: (turn: number | null) => void;
  selected: ReadonlySet<number>;
  toggleSelected: (turn: number, extend: boolean) => void;
}

export function inkOf(speaker: Speaker): string {
  return speaker.color_slot != null
    ? speakerInk(speaker.color_slot)
    : "var(--coulisses-speaker-unknown-ink)";
}

/** A word as text. Marks (current word, unsure, added, glossary) and their hover tip
 *  are drawn with CSS, so that the line's text, typed into or copied, is exactly its
 *  words (a native title does not show inside an editable line). */
function Word({ word, isCurrent }: { word: WordData; isCurrent: boolean }) {
  const unsure = word.confidence != null && word.confidence < UNSURE_BELOW;
  // One tip per word, the most useful first: what to write, then how it was written,
  // then how sure the engine was. Screen readers get the same through aria-label.
  const tip: { kind: string; text?: string; label: string; percent?: number } | null =
    word.suggestion
      ? { kind: "suggestion", text: `→ ${word.suggestion}`, label: `Peut-être « ${word.suggestion} »` }
      : word.added
        ? { kind: "added", text: "ajouté", label: "Ajouté à la main, sans horodatage mesuré" }
        : unsure
          ? {
              kind: "confidence",
              percent: Math.round((word.confidence ?? 0) * 100),
              label: `Mot peu sûr, confiance ${Math.round((word.confidence ?? 0) * 100)} %`,
            }
          : null;
  return (
    <span
      className="cl-word"
      data-unsure={unsure || undefined}
      data-added={word.added || undefined}
      data-suggestion={word.suggestion ? true : undefined}
      data-tip-kind={tip?.kind}
      data-tip={tip?.text}
      aria-description={tip?.label}
      style={tip?.percent != null ? ({ "--cl-conf": tip.percent } as React.CSSProperties) : undefined}
    >
      {isCurrent && (
        <motion.span layoutId="mot-courant" className="cl-word__current" transition={GLIDE} aria-hidden />
      )}
      {word.text}
    </span>
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

/** Give lines to another voice, or to a new one: this is how a voice is split. */
export function GiveToPanel({
  voices,
  except,
  onGive,
}: {
  voices: Speaker[];
  except: string | null;
  onGive: (target: string | null) => void;
}) {
  return (
    <ul className="cl-namepanel__list" aria-label="Donner à">
      <li>
        <button
          type="button"
          className="cl-namepanel__person"
          onClick={() => onGive(null)}
        >
          <span
            className="cl-dot"
            style={{ background: "var(--coulisses-speaker-unknown-ink)" }}
            aria-hidden
          />
          <span>Une nouvelle voix</span>
        </button>
      </li>
      {voices
        .filter((v) => v.label !== null && v.label !== except)
        .map((v) => (
          <li key={v.label}>
            <button
              type="button"
              className="cl-namepanel__person"
              onClick={() => onGive(v.label)}
            >
              <span
                className="cl-dot"
                style={{ background: inkOf(v) }}
                aria-hidden
              />
              <span>{speakerTitle(v)}</span>
            </button>
          </li>
        ))}
    </ul>
  );
}

function placeCaretAtEnd(element: HTMLElement) {
  const range = document.createRange();
  range.selectNodeContents(element);
  range.collapse(false);
  const selection = window.getSelection();
  selection?.removeAllRanges();
  selection?.addRange(range);
}

/** The text of a line, typed into directly. Leaving it (or Enter) saves; Escape gives
 *  back what was there. Cmd-Z undoes typing while in it; outside, it undoes the last
 *  correction (the page handles that). A draft is never lost: refused, it stays on screen
 *  to be fixed; scrolled out of view, it is saved (P8). */
function EditableText({
  turn,
  currentWord,
  editing,
}: {
  turn: TurnRow["turn"];
  currentWord: number | null;
  editing: Editing;
}) {
  const ref = useRef<HTMLParagraphElement>(null);
  const cancel = useRef(false);
  /** What was typed and not saved yet; null when the line shows its saved text. */
  const draft = useRef<string | null>(null);
  // Typing, or saving what was typed: the line is left alone (no current-word mark).
  const [active, setActive] = useState(false);
  // Remounting the paragraph after each edit gives React back a DOM it knows.
  const [version, setVersion] = useState(0);
  const text = turn.words.map((w) => w.text).join(" ");
  const { correct, editingTurn, setEditingTurn } = editing;

  // E (or any request) puts the cursor at the end of this line.
  useLayoutEffect(() => {
    if (editingTurn === turn.index && ref.current) {
      ref.current.focus();
      placeCaretAtEnd(ref.current);
      setEditingTurn(null);
    }
  }, [editingTurn, turn.index, setEditingTurn]);

  // Scrolled out of the virtual list while typed into: save what was typed.
  useEffect(
    () => () => {
      const typed = draft.current?.replace(/\s+/g, " ").trim();
      if (typed && typed !== text) void correct({ kind: "edit_text", turn: turn.index, text: typed }).catch(() => undefined);
    },
    [correct, text, turn.index],
  );

  const finish = async () => {
    const typed = (ref.current?.innerText ?? "").replace(/\s+/g, " ").trim();
    if (cancel.current || typed === text) {
      cancel.current = false;
      draft.current = null;
      setVersion((v) => v + 1);
      setActive(false);
      return;
    }
    try {
      // An empty line is refused by the service, with its reason.
      await correct({ kind: "edit_text", turn: turn.index, text: typed });
      draft.current = null;
      setVersion((v) => v + 1);
      setActive(false);
    } catch {
      // Refused (shown by the page): the draft stays on screen, untouched, to be fixed.
    }
  };

  return (
    <p
      key={`${version}:${text}`}
      ref={ref}
      className="cl-words"
      contentEditable="plaintext-only"
      suppressContentEditableWarning
      spellCheck
      lang="fr"
      role="textbox"
      aria-label="Texte de la réplique, modifiable"
      onFocus={() => setActive(true)}
      onInput={() => {
        draft.current = ref.current?.innerText ?? "";
      }}
      onBlur={() => void finish()}
      onKeyDown={(e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          ref.current?.blur();
        } else if (e.key === "Escape") {
          e.preventDefault();
          cancel.current = true;
          ref.current?.blur();
        }
      }}
    >
      {turn.words.map((w, i) => (
        <span key={i}>
          <Word word={w} isCurrent={!active && currentWord === i} />
          {i < turn.words.length - 1 ? " " : ""}
        </span>
      ))}
    </p>
  );
}

const TurnLine = memo(function TurnLine({
  row,
  currentWord,
  onSeek,
  editing,
  voices,
}: {
  row: TurnRow;
  /** Index of the word being heard in this line; null if it is not being heard. */
  currentWord: number | null;
  onSeek: (t: number) => void;
  editing: Editing;
  voices: Speaker[];
}) {
  const { turn, speaker } = row;
  const isCurrent = currentWord !== null;
  const isSelected = editing.selected.has(turn.index);
  const [giving, setGiving] = useState(false);
  const suggestions = turn.words.filter((w) => w.suggestion);

  const applyGlossary = () => {
    const text = turn.words.map((w) => w.suggestion ?? w.text).join(" ");
    void editing
      .correct({ kind: "edit_text", turn: turn.index, text })
      .catch(() => undefined);
  };

  return (
    <div
      className="cl-turn"
      data-current={isCurrent || undefined}
      data-selected={isSelected || undefined}
    >
      <div className="cl-turn__margin">
        <input
          type="checkbox"
          className="cl-turn__check"
          checked={isSelected}
          aria-label={
            turn.start != null
              ? `Sélectionner la réplique de ${formatClock(turn.start)}`
              : "Sélectionner cette réplique, sans horodatage"
          }
          onChange={() => undefined}
          onClick={(e) => editing.toggleSelected(turn.index, e.shiftKey)}
        />
        <TimeLink t={turn.start} isCurrent={isCurrent} onSeek={onSeek} />
      </div>
      <div className="cl-turn__body">
        <div className="cl-turn__head">
          <Popover
            isOpen={editing.namingTurn === turn.index}
            onOpenChange={(open) =>
              editing.setNamingTurn(open ? turn.index : null)
            }
            label={`Nommer ${speaker.name}`}
            width={320}
            content={
              speaker.label !== null ? (
                <NamePanel
                  speaker={speaker}
                  people={editing.people}
                  voices={voices}
                  onCorrect={async (c) => {
                    await editing.correct(c);
                    editing.setNamingTurn(null);
                  }}
                  onAddGuest={editing.addGuest}
                />
              ) : (
                <p>Cette réplique n'a pas de voix : donnez-la à une voix.</p>
              )
            }
          >
            <button
              type="button"
              className="cl-name"
              data-unnamed={!speaker.named || undefined}
              style={{ color: inkOf(speaker) }}
              title="Nommer cette voix (N)"
            >
              {speaker.name}
              {speaker.played_by && (
                <span className="cl-name__played">
                  {" "}
                  · joué par {speaker.played_by}
                </span>
              )}
            </button>
          </Popover>
          {!speaker.named && speaker.label !== null && (
            <button
              type="button"
              className="cl-turn__nommer"
              onClick={() => editing.setNamingTurn(turn.index)}
            >
              Nommer
            </button>
          )}
          <span className="cl-turn__actions">
            {suggestions.length > 0 && (
              <button
                type="button"
                className="cl-iconbtn"
                aria-label="Appliquer le glossaire"
                title={`Appliquer le glossaire : ${suggestions.map((w) => `${w.text} → ${w.suggestion}`).join(", ")}`}
                onClick={applyGlossary}
              >
                <SpellCheck size={14} strokeWidth={1.75} />
              </button>
            )}
            {turn.edited && (
              <button
                type="button"
                className="cl-iconbtn"
                aria-label="Revenir au texte d'origine"
                title="Revenir au texte d'origine"
                onClick={() =>
                  void editing.resetText(turn.index).catch(() => undefined)
                }
              >
                <RotateCcw size={14} strokeWidth={1.75} />
              </button>
            )}
            <Popover
              isOpen={giving}
              onOpenChange={setGiving}
              label="Donner cette réplique à"
              width={280}
              content={
                <GiveToPanel
                  voices={voices}
                  except={speaker.label}
                  onGive={(target) => {
                    setGiving(false);
                    void editing
                      .correct({
                        kind: "reassign_turns",
                        turns: [turn.index],
                        target,
                      })
                      .catch(() => undefined);
                  }}
                />
              }
            >
              <button
                type="button"
                className="cl-iconbtn"
                aria-label="Donner à une autre voix"
                title="Donner à une autre voix"
              >
                <ArrowRightLeft size={14} strokeWidth={1.75} />
              </button>
            </Popover>
          </span>
        </div>
        <EditableText turn={turn} currentWord={currentWord} editing={editing} />
      </div>
    </div>
  );
});

/** The whole transcript, virtualised: two hours are thousands of lines (rules/web.md). */
export function TranscriptView({
  model,
  pb,
  current,
  editing,
}: {
  model: ReviewModel;
  pb: Playback;
  current: { row: TurnRow; word: number } | null;
  editing: Editing;
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

  // While playing, follow the sound only when the line leaves the screen, and never while
  // a line is being typed into. Never on first display.
  useEffect(() => {
    const typing = document.activeElement?.closest(".cl-words") != null;
    if (!pb.playing || currentIndex < 0 || typing) return;
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
                  currentWord={
                    current?.row.turn.index === row.turn.index
                      ? current.word
                      : null
                  }
                  onSeek={pb.seek}
                  editing={editing}
                  voices={model.speakers}
                />
              ) : (
                <div className="cl-gap">
                  <TimeLink t={row.start} isCurrent={false} onSeek={pb.seek} />
                  <span>
                    Passage non transcrit, {formatClock(row.start)} –{" "}
                    {formatClock(row.end)}. L'audio reste à écouter.
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
