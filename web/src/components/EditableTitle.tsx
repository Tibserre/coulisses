import { useEffect, useRef, useState } from "react";

/** The session's title, typed into directly like a document (no box): Enter or leaving it
 *  saves, Escape gives back what was there. A refused title stays on screen; a title that
 *  arrives while one types (the generated one) never replaces what is being typed. */
export function EditableTitle({ title, onSave }: { title: string; onSave: (title: string) => Promise<void> }) {
  const ref = useRef<HTMLHeadingElement>(null);
  const cancel = useRef(false);
  const typing = useRef(false);
  const [error, setError] = useState<string | null>(null);

  // The text is set here, not rendered by React: typing changes the DOM, and React must
  // not fight over it.
  useEffect(() => {
    if (!typing.current && ref.current && ref.current.innerText !== title) ref.current.innerText = title;
  }, [title]);

  const finish = async () => {
    typing.current = false;
    const typed = (ref.current?.innerText ?? "").replace(/\s+/g, " ").trim();
    if (cancel.current || typed === title) {
      cancel.current = false;
      if (ref.current) ref.current.innerText = title;
      setError(null);
      return;
    }
    try {
      await onSave(typed);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <>
      <h1
        ref={ref}
        className="cl-title"
        contentEditable="plaintext-only"
        suppressContentEditableWarning
        spellCheck
        lang="fr"
        aria-description="Modifiable : cliquez et tapez, Entrée pour enregistrer"
        onFocus={() => {
          typing.current = true;
        }}
        onBlur={() => void finish()}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            ref.current?.blur();
          } else if (e.key === "Escape") {
            e.preventDefault();
            cancel.current = true;
            ref.current?.blur();
          }
        }}
      />
      {error && <p className="cl-title__error">{error}</p>}
    </>
  );
}
