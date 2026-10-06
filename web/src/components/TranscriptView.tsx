import { memo, useEffect, useRef, useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { Popover } from "@astryxdesign/core/Popover";
import { Tooltip } from "@astryxdesign/core/Tooltip";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowRightLeft, Pencil, Play } from "lucide-react";
import { motion } from "motion/react";
import type { EditRequest, Person, Speaker, Word as WordData } from "../api.ts";
import { formatClock } from "../format.ts";
import { speakerInk } from "../theme/shared.ts";
import type { ReviewModel, Row, TurnRow } from "../transcript.ts";
import { replaceWord, speakerTitle } from "../transcript.ts";
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
  /** Line whose text is being corrected, by its index in the run. */
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

function Word({
  word,
  isCurrent,
  onAccept,
}: {
  word: WordData;
  isCurrent: boolean;
  /** Replace this word by the glossary's spelling. */
  onAccept?: () => void;
}) {
  const unsure = word.confidence != null && word.confidence < UNSURE_BELOW;
  const inner = (
    <span
      className="cl-word"
      data-unsure={unsure || undefined}
      data-suggestion={word.suggestion ? true : undefined}
    >
      {isCurrent && (
        <motion.span
          layoutId="mot-courant"
          className="cl-word__current"
          transition={GLIDE}
          aria-hidden
        />
      )}
      {word.text}
      {word.added && (
        <sup
          className="cl-word__added"
          aria-label="mot ajouté, sans horodatage mesuré"
        >
          +
        </sup>
      )}
    </span>
  );
  if (word.suggestion && onAccept) {
    return (
      <Tooltip
        content={`Peut-être « ${word.suggestion} » : cliquer pour corriger`}
        hasHoverIndication={false}
      >
        <button type="button" className="cl-word__fix" onClick={onAccept}>
          {inner}
        </button>
      </Tooltip>
    );
  }
  if (unsure) {
    return (
      <Tooltip
        content={`Mot peu sûr, confiance ${Math.round((word.confidence ?? 0) * 100)} %`}
        hasHoverIndication={false}
      >
        {inner}
      </Tooltip>
    );
  }
  if (word.added) {
    return (
      <Tooltip
        content="Ajouté à la main, sans horodatage mesuré"
        hasHoverIndication={false}
      >
        {inner}
      </Tooltip>
    );
  }
  return inner;
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

function TextEditor({
  initial,
  onSave,
  onCancel,
}: {
  initial: string;
  onSave: (text: string) => Promise<void>;
  onCancel: () => void;
}) {
  const [text, setText] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    area.current?.focus();
    area.current?.select();
  }, []);
  const save = async () => {
    try {
      await onSave(text);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <div className="cl-editor">
      <textarea
        ref={area}
        className="cl-editor__area"
        value={text}
        aria-label="Texte de la réplique"
        rows={Math.max(2, Math.ceil(text.length / 70))}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            void save();
          } else if (e.key === "Escape") {
            e.preventDefault();
            onCancel();
          }
        }}
      />
      <div className="cl-editor__bar">
        <span className="cl-editor__hint">
          Entrée pour enregistrer, Échap pour annuler. Un mot corrigé garde son
          horodatage.
        </span>
        <Button size="sm" variant="ghost" label="Annuler" onClick={onCancel} />
        <Button
          size="sm"
          variant="primary"
          label="Enregistrer"
          clickAction={save}
        />
      </div>
      {error && <p className="cl-editor__error">{error}</p>}
    </div>
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
  const isEditing = editing.editingTurn === turn.index;
  const isSelected = editing.selected.has(turn.index);
  const [giving, setGiving] = useState(false);
  const text = turn.words.map((w) => w.text).join(" ");

  const acceptSuggestion = (i: number, by: string) => {
    void editing
      .correct({ kind: "edit_text", turn: turn.index, text: replaceWord(turn.words, i, by) })
      .catch(() => undefined); // the refusal is shown by the page (editError)
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
      <div
        className="cl-turn__body"
        style={{ "--cl-ink": inkOf(speaker) } as React.CSSProperties}
      >
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
            <button
              type="button"
              className="cl-iconbtn"
              aria-label="Corriger le texte (E)"
              title="Corriger le texte (E)"
              onClick={() => editing.setEditingTurn(turn.index)}
            >
              <Pencil size={14} strokeWidth={1.75} />
            </button>
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
                    void editing.correct({
                      kind: "reassign_turns",
                      turns: [turn.index],
                      target,
                    });
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
        {isEditing ? (
          <TextEditor
            initial={text}
            onCancel={() => editing.setEditingTurn(null)}
            onSave={async (value) => {
              if (value.trim() === text) {
                editing.setEditingTurn(null);
                return;
              }
              await editing.correct({
                kind: "edit_text",
                turn: turn.index,
                text: value,
              });
              editing.setEditingTurn(null);
            }}
          />
        ) : (
          <p className="cl-words">
            {turn.words.map((w, i) => (
              <span key={i}>
                <Word
                  word={w}
                  isCurrent={currentWord === i}
                  onAccept={
                    w.suggestion
                      ? () => acceptSuggestion(i, w.suggestion!)
                      : undefined
                  }
                />
                {i < turn.words.length - 1 ? " " : ""}
              </span>
            ))}
          </p>
        )}
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
