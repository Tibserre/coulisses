import { useEffect, useRef, useState } from "react";
import { Heading } from "@astryxdesign/core/Heading";
import { Text } from "@astryxdesign/core/Text";
import { api } from "../api.ts";
import { clearDraft, readDraft, writeDraft } from "../drafts.ts";
import { formatDateTime } from "../format.ts";

/** The note written after the session (spec §7.8), typed into directly like the rest (no
 *  box). Leaving it saves; it goes into the context of every summary made afterwards. A
 *  draft is never lost (P8): refused, it stays on screen; leaving the page or closing the
 *  window, it is saved; if that fails too, it is kept in this browser and offered back. */
export function NotesSection({ sessionId }: { sessionId: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const saved = useRef<string>("");
  /** What was typed, kept here and not read from the page: on leaving, the element may
   *  already be gone (reading it then would save an empty note). */
  const typed = useRef<string | null>(null);
  const draftKey = `note:${sessionId}`;
  const [loaded, setLoaded] = useState(false);
  const [recovered, setRecovered] = useState(false);
  const [state, setState] = useState<{
    at: string | null;
    error: string | null;
    saving: boolean;
  }>({
    at: null,
    error: null,
    saving: false,
  });

  useEffect(() => {
    api.notes(sessionId).then(
      (note) => {
        saved.current = note?.text ?? "";
        // A draft left unsaved (window closed, save refused) comes back, said so.
        const draft = readDraft<string>(draftKey);
        const shown = draft != null && draft.trim() !== saved.current ? draft : saved.current;
        typed.current = shown === saved.current ? null : shown;
        if (draft != null && shown === saved.current) clearDraft(draftKey);
        if (ref.current) ref.current.innerText = shown;
        setRecovered(typed.current !== null);
        setState((s) => ({ ...s, at: note?.updated_at ?? null }));
        setLoaded(true);
      },
      (e: Error) => setState((s) => ({ ...s, error: e.message })),
    );
  }, [sessionId, draftKey]);

  const save = async () => {
    if (!loaded || typed.current === null) return;
    const text = typed.current.trim();
    if (text === saved.current) {
      typed.current = null;
      clearDraft(draftKey);
      return;
    }
    setState((s) => ({ ...s, saving: true }));
    try {
      const note = await api.setNotes(sessionId, text);
      saved.current = note.text;
      if (typed.current?.trim() === text) {
        typed.current = null;
        clearDraft(draftKey);
      }
      setRecovered(false);
      setState({ at: note.updated_at, error: null, saving: false });
    } catch (e) {
      // Refused: the text stays on screen and in the draft, to be saved again.
      setState((s) => ({ ...s, error: (e as Error).message, saving: false }));
    }
  };

  // Leaving the page (another screen, or the window closed) with something typed: saved.
  const latest = useRef(save);
  latest.current = save;
  useEffect(() => {
    const onHide = () => {
      if (typed.current !== null && typed.current.trim() !== saved.current) {
        void fetch(`/api/seances/${encodeURIComponent(sessionId)}/notes`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: typed.current.trim() }),
          keepalive: true,
        }).catch(() => undefined); // kept as a draft if it does not get through
      }
    };
    window.addEventListener("pagehide", onHide);
    return () => {
      window.removeEventListener("pagehide", onHide);
      void latest.current();
    };
  }, [sessionId]);

  return (
    <section className="cl-notes">
      <Heading level={3}>Notes</Heading>
      <div
        ref={ref}
        className="cl-notes__text"
        contentEditable={loaded ? "plaintext-only" : false}
        suppressContentEditableWarning
        spellCheck
        lang="fr"
        role="textbox"
        aria-multiline="true"
        aria-label="Notes d'après séance, modifiables"
        data-placeholder="Ce que l'enregistrement ne dit pas : une décision prise après, une idée, un absent… Elles sont lues par les résumés."
        onInput={() => {
          typed.current = ref.current?.innerText ?? "";
          writeDraft(draftKey, typed.current);
        }}
        onBlur={() => void save()}
      />
      {recovered && !state.error && (
        <p className="cl-notes__error">
          Brouillon retrouvé, pas encore enregistré : cliquez dans la note puis ailleurs pour
          l'enregistrer.
        </p>
      )}
      {state.error ? (
        <p className="cl-notes__error">{state.error}</p>
      ) : (
        <Text type="supporting" as="p">
          {state.saving
            ? "Enregistrement…"
            : state.at
              ? `Enregistrées le ${formatDateTime(state.at)}. Les résumés faits avant sont signalés périmés.`
              : "Lues par chaque résumé, avec le transcript."}
        </Text>
      )}
    </section>
  );
}
