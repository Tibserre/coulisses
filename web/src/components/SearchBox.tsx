import { useEffect, useRef, useState } from "react";
import { Search } from "lucide-react";
import { api, type SearchHit, type SearchResults, type Session } from "../api.ts";
import { formatClock } from "../format.ts";
import { sessionHref, sessionName } from "../library.ts";
import { formatDay } from "../retention.ts";

const KIND_LABEL: Record<SearchHit["kind"], string> = {
  title: "titre",
  turn: "transcription",
  note: "note",
  summary: "résumé",
};

function hitHref(sessionId: string, hit: SearchHit): string {
  if (hit.at_s != null) return sessionHref(sessionId, hit.at_s);
  if (hit.kind === "summary") return sessionHref(sessionId, null, "summary");
  return sessionHref(sessionId);
}

/** The search in every session (⌘K): transcripts as corrected, notes, summaries and
 *  titles, accents and case ignored. A result opens its session at the passage. */
export function SearchBox({ sessions }: { sessions: Session[] }) {
  const field = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResults | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  // ⌘K anywhere puts the cursor here.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        field.current?.focus();
        field.current?.select();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Asked a quarter of a second after the last key; an older answer never replaces a newer.
  useEffect(() => {
    const words = query.trim();
    if (!words) {
      setResults(null);
      return;
    }
    let current = true;
    const timer = window.setTimeout(() => {
      api.search(words).then(
        (r) => {
          if (!current) return;
          setResults(r);
          setError(null);
          setActive(0);
        },
        (e: Error) => current && setError(e.message),
      );
    }, 250);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [query]);

  const byId = new Map(sessions.map((s) => [s.id, s]));
  const flat = (results?.sessions ?? []).flatMap((s) => s.hits.map((h) => ({ sessionId: s.session_id, hit: h })));
  const go = (href: string) => {
    setOpen(false);
    field.current?.blur();
    window.location.hash = href;
  };

  let index = -1;
  return (
    <div className="cl-search" onBlur={(e) => !e.currentTarget.contains(e.relatedTarget) && setOpen(false)}>
      <label className="cl-search__field">
        <Search size={15} strokeWidth={1.75} aria-hidden />
        <input
          ref={field}
          type="search"
          role="combobox"
          aria-expanded={open && query.trim() !== ""}
          aria-controls="cl-search-results"
          aria-activedescendant={flat[active] ? `cl-hit-${active}` : undefined}
          aria-autocomplete="list"
          value={query}
          placeholder="Chercher dans les séances"
          aria-label="Chercher dans les séances"
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((a) => Math.min(a + 1, flat.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            } else if (e.key === "Enter" && flat[active]) {
              go(hitHref(flat[active].sessionId, flat[active].hit));
            } else if (e.key === "Escape") {
              setOpen(false);
              field.current?.blur();
            }
          }}
        />
        <kbd>⌘K</kbd>
      </label>
      {open && query.trim() && (
        <div className="cl-search__results" role="listbox" id="cl-search-results" aria-label="Résultats">
          {error && <p className="cl-search__empty">{error}</p>}
          {results && results.sessions.length === 0 && !error && (
            <p className="cl-search__empty">Rien trouvé pour « {results.query} ».</p>
          )}
          {results?.sessions.map((s) => {
            const session = byId.get(s.session_id);
            return (
              <section key={s.session_id}>
                <div className="cl-search__session">
                  <span>{session ? sessionName(session) : "Séance"}</span>
                  {session && <span className="cl-search__meta">{formatDay(session.recorded_at)} · {session.space_name}</span>}
                </div>
                {s.hits.map((h) => {
                  index += 1;
                  const mine = index;
                  return (
                    <a
                      key={`${h.kind}${h.ref}`}
                      role="option"
                      id={`cl-hit-${mine}`}
                      aria-selected={mine === active}
                      className="cl-search__hit"
                      href={hitHref(s.session_id, h)}
                      onMouseEnter={() => setActive(mine)}
                      onClick={(e) => {
                        e.preventDefault();
                        go(hitHref(s.session_id, h));
                      }}
                    >
                      <span className="cl-search__where">{h.at_s != null ? formatClock(h.at_s) : KIND_LABEL[h.kind]}</span>
                      <span className="cl-search__excerpt">
                        {h.excerpt.map((p, k) => (p.hit ? <mark key={k}>{p.text}</mark> : <span key={k}>{p.text}</span>))}
                      </span>
                    </a>
                  );
                })}
              </section>
            );
          })}
          {results?.more && (
            <p className="cl-search__empty">D'autres passages correspondent : précisez la recherche pour les voir.</p>
          )}
          {results && results.problems.length > 0 && (
            <p className="cl-search__empty">{results.problems.join(" ")}</p>
          )}
        </div>
      )}
    </div>
  );
}
