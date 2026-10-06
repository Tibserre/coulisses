import { useMemo, useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import type { EditRequest, Person, Speaker } from "../api.ts";
import { speakerInk } from "../theme/shared.ts";

/** Naming a voice, without leaving the review (art direction): a person of the space,
 *  a new guest, a free name, a character played by someone, or a merge with another
 *  voice. */
export function NamePanel({
  speaker,
  people,
  voices,
  onCorrect,
  onAddGuest,
}: {
  speaker: Speaker;
  people: Person[];
  voices: Speaker[];
  onCorrect: (correction: EditRequest) => Promise<void>;
  onAddGuest: (name: string) => Promise<Person>;
}) {
  const label = speaker.label ?? "";
  const [query, setQuery] = useState("");
  const [character, setCharacter] = useState("");
  const [playedBy, setPlayedBy] = useState<number | null>(speaker.person_id);
  const active = people.filter((p) => !p.archived);
  const q = query.trim().toLowerCase();
  const matches = useMemo(
    () => active.filter((p) => !q || p.name.toLowerCase().includes(q)),
    [active, q],
  );
  const exact = active.some((p) => p.name.toLowerCase() === q);
  const others = voices.filter(
    (v) => v.label !== null && v.label !== speaker.label,
  );

  const [error, setError] = useState<string | null>(null);
  /** Every action reports its refusal here: never an unhandled error (P8). */
  const safely = async (action: () => Promise<unknown>) => {
    try {
      await action();
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const assign = (fields: Partial<Extract<EditRequest, { kind: "assign_speaker" }>>) =>
    safely(() => onCorrect({ kind: "assign_speaker", speaker: label, ...fields }));

  return (
    <div className="cl-namepanel">
      <TextInput
        label="Qui parle ?"
        placeholder="Chercher ou écrire un nom"
        value={query}
        onChange={setQuery}
        onEnter={() => {
          if (matches.length === 1) void assign({ person_id: matches[0].id });
        }}
      />
      <ul className="cl-namepanel__list" aria-label="Personnes de l'espace">
        {matches.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              className="cl-namepanel__person"
              data-current={
                p.id === speaker.person_id && !speaker.character
                  ? true
                  : undefined
              }
              onClick={() => void assign({ person_id: p.id })}
            >
              <span
                className="cl-dot"
                style={{ background: speakerInk(p.color_slot) }}
                aria-hidden
              />
              <span>{p.name}</span>
              <Text type="supporting">
                {p.kind === "guest" ? "invité" : (p.role ?? "membre")}
              </Text>
            </button>
          </li>
        ))}
      </ul>
      {q && !exact && (
        <div className="cl-namepanel__row">
          <Button
            size="sm"
            label={`Ajouter « ${query.trim()} » comme invité`}
            clickAction={() =>
              safely(async () => {
                const guest = await onAddGuest(query.trim());
                await onCorrect({ kind: "assign_speaker", speaker: label, person_id: guest.id });
              })
            }
          />
          <Button
            size="sm"
            variant="ghost"
            label="Nom libre, sans fiche"
            clickAction={() => assign({ name: query.trim() })}
          />
        </div>
      )}

      <details className="cl-namepanel__more">
        <summary>Personnage joué par…</summary>
        <div className="cl-namepanel__character">
          <TextInput
            label="Personnage"
            value={character}
            onChange={setCharacter}
            size="sm"
          />
          <label className="cl-select">
            <span>Joué par</span>
            <select
              value={playedBy ?? ""}
              onChange={(e) =>
                setPlayedBy(e.target.value ? Number(e.target.value) : null)
              }
            >
              <option value="">Choisir…</option>
              {active.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <Button
            size="sm"
            label="Valider"
            isDisabled={!character.trim() || playedBy == null}
            clickAction={() =>
              assign({ person_id: playedBy, character: character.trim() })
            }
          />
        </div>
      </details>

      {others.length > 0 && (
        <details className="cl-namepanel__more">
          <summary>C'est la même personne que…</summary>
          <ul className="cl-namepanel__list">
            {others.map((v) => (
              <li key={v.label}>
                <button
                  type="button"
                  className="cl-namepanel__person"
                  onClick={() =>
                    void safely(() =>
                      onCorrect({
                      kind: "merge_speakers",
                      source: label,
                      target: v.label!,
                    }),
                    )
                  }
                >
                  <span
                    className="cl-dot"
                    style={{
                      background:
                        v.color_slot != null
                          ? speakerInk(v.color_slot)
                          : "var(--coulisses-speaker-unknown-ink)",
                    }}
                    aria-hidden
                  />
                  <span>{v.name}</span>
                  <Text type="supporting">fusionner</Text>
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}

      {speaker.named && (
        <Button
          size="sm"
          variant="ghost"
          label="Retirer le nom"
          clickAction={() =>
            assign({ person_id: null, name: null, character: null })
          }
        />
      )}
      {error && (
        <Text as="p" color="primary" type="supporting">
          {error}
        </Text>
      )}
    </div>
  );
}
