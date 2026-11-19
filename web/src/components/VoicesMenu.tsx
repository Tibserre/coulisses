import { useRef, useState } from "react";
import { Popover } from "@astryxdesign/core/Popover";
import { Tooltip } from "@astryxdesign/core/Tooltip";
import type { Person, Speaker } from "../api.ts";
import { formatDuration, plural } from "../format.ts";
import { speakerInk, speakerTint } from "../theme/shared.ts";
import { Face } from "./AttendeesSheet.tsx";

/** Named voices shown in the pile; the others go into its « +N ». */
const PILE = 8;

const initial = (name: string) => name.trim().charAt(0).toLocaleUpperCase("fr");

/** A voice's disc: its person's face, else its initial in its colour (a free name, a
 *  character), else an empty place. */
export function VoiceFace({
  voice,
  people,
  size = "md",
}: {
  voice: Speaker;
  people: Person[];
  size?: "sm" | "md" | "lg";
}) {
  const person = people.find((p) => p.id === voice.person_id);
  if (person && !voice.character) return <Face person={person} size={size} />;
  // A character (ADR 0091): who plays it, and its rounded square over it.
  if (voice.character)
    return (
      <span className="cl-double" data-size={size}>
        {person && <Face person={person} size={size} />}
        <span
          className="cl-face"
          data-size={size}
          data-role
          style={{
            background: speakerTint(voice.color_slot ?? 0),
            color: speakerInk(voice.color_slot ?? 0),
          }}
          aria-hidden
        >
          {initial(voice.character)}
        </span>
      </span>
    );
  if (!voice.named) return <Face size={size} />;
  return (
    <span
      className="cl-face"
      data-size={size}
      style={{
        background: speakerTint(voice.color_slot ?? 0),
        color: speakerInk(voice.color_slot ?? 0),
      }}
      aria-hidden
    >
      {initial(voice.name)}
    </span>
  );
}

/** The voices of a session as one button (ADR 0090): the named ones stacked, « +N » in grey
 *  for those left; a click lists them all, those to name first (the one being named at the
 *  top), a rule, then the named ones, each with its speaking time. Two voices of the same
 *  person are offered to be merged there. */
export function VoicesMenu({
  voices,
  toName,
  people,
  current = null,
  twins = [],
  tip,
  onPick,
  onMerge,
}: {
  /** Every voice with a label. */
  voices: Speaker[];
  /** Those without a name, in the order they are named. */
  toName: Speaker[];
  people: Person[];
  /** The voice being named: first, marked, and not counted in « +N ». */
  current?: Speaker | null;
  twins?: [Speaker, Speaker][];
  /** Said on hover (« Nommer les voix »). */
  tip?: string;
  onPick: (voice: Speaker) => void;
  onMerge?: (pair: [Speaker, Speaker]) => void;
}) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const named = voices.filter((v) => v.named);
  const pile = named.slice(0, PILE);
  const left = toName.filter((v) => v !== current);
  const over = named.length - pile.length + left.length;
  const row = (v: Speaker) => (
    <li key={v.label}>
      <button
        type="button"
        className="cl-spacepick__item"
        aria-current={v === current || undefined}
        onClick={() => {
          setOpen(false);
          onPick(v);
        }}
      >
        <VoiceFace voice={v} people={people} size="sm" />
        <span className="cl-spacepick__what">{v.name}</span>
        <span className="cl-who__time">{formatDuration(v.seconds)}</span>
      </button>
    </li>
  );
  const first = current && !current.named ? [current, ...left] : left;
  return (
    <>
      <Popover
        isOpen={open}
        onOpenChange={setOpen}
        label="Les voix de la séance"
        placement="below"
        alignment="start"
        width={280}
        padding={1}
        content={
          <ul className="cl-spacepick" aria-label="Les voix de la séance">
            {first.map(row)}
            {named.length > 0 && first.length > 0 && (
              <li className="cl-who__rule" aria-hidden />
            )}
            {named.map(row)}
            {onMerge &&
              twins.map((pair) => (
                <li key={`${pair[0].label}+${pair[1].label}`}>
                  <button
                    type="button"
                    className="cl-spacepick__item cl-voices__merge"
                    title="Les deux voix n'en font plus qu'une (Cmd-Z pour annuler)"
                    onClick={() => {
                      setOpen(false);
                      onMerge(pair);
                    }}
                  >
                    Réunir les deux {pair[0].name}
                  </button>
                </li>
              ))}
          </ul>
        }
      >
        <button
          ref={button}
          type="button"
          className="cl-who__pile"
          aria-label={`${tip ? `${tip} : ` : ""}${plural(named.length, "voix nommée", "voix nommées")}, ${plural(toName.length, "à nommer", "à nommer")}. Voir les voix`}
        >
          <span className="cl-faces">
            {pile.map((v) => (
              <VoiceFace key={v.label} voice={v} people={people} size="sm" />
            ))}
            {over > 0 && (
              <span className="cl-face" data-over aria-hidden>
                +{over}
              </span>
            )}
          </span>
        </button>
      </Popover>
      {tip && !open && <Tooltip anchorRef={button} content={tip} />}
    </>
  );
}
