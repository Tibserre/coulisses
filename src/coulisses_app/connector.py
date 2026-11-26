"""What the assistants' connector may read (ADR 0065, `docs/produit/contrat-connecteur.md`).

The bridge `coulisses-mcp` reads only these answers, in GET, and filters nothing itself: the
rules are applied here, at the source. A connector closed in the settings refuses all; a
space closed to it is in no answer, not even counted; in a space whose names are not passed
on, every name known to the space becomes « Personne A », « Personne B »… everywhere, at
best (whole words, accents and case ignored). Each successful read is written in the
journal of accesses, never purged.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import shlex
import sqlite3
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from coulisses.api import Provenance, RunNotSucceededError, read_provenance
from pydantic import BaseModel, ValidationError

from coulisses_app import actions, corrections, notes, search, sessions, summaries
from coulisses_app.paths import DataDir
from coulisses_app.prompting.generate import PHASES_REF, TITLE_REF
from coulisses_app.prompting.generate import Provenance as GenerationProvenance
from coulisses_app.storage.db import ISO_FORMAT, connect, now_iso

log = logging.getLogger(__name__)

Tool = Literal[
    "lister_espaces", "chercher", "lister_seances", "lire_seance", "lire_resume", "lire_transcript"
]

SECRET_KEY = "connector_view_secret"
OPEN_KEY = "connector_open"
"""Key of `app_setting`: "1" when the user opened the connector; absent or else, closed."""

CLOSED = (
    "Le connecteur de Coulisses est coupé. "
    "Ouvrez-le dans Coulisses › Réglages › Connecteur."  # noqa: RUF001
)
NOT_FOUND = "Séance introuvable, ou dans un espace fermé au connecteur."
CHANGED = (
    "La séance a changé depuis le début de la lecture (corrections, version, chapitres) : "
    "reprenez au début."
)
SEARCH_CHANGED = "La recherche a changé depuis la page précédente : relancez-la."

MAX_TURNS = 500
DEFAULT_TURNS = 200
MAX_HITS = 5
EXCERPT_WORDS = 14


class ConnectorError(Exception):
    """A read refused, with its HTTP code and the French reason."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


# -- open or closed ------------------------------------------------------------------


def is_open(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT value FROM app_setting WHERE key = ?", (OPEN_KEY,)).fetchone()
    return row is not None and row["value"] == "1"


def set_open(conn: sqlite3.Connection, value: bool) -> None:
    with conn:
        conn.execute(
            "INSERT INTO app_setting (key, value) VALUES (?, ?)"
            " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (OPEN_KEY, "1" if value else "0"),
        )


def check_open(conn: sqlite3.Connection) -> None:
    """Before any other check (contract §1): closed, everything answers 403."""
    if not is_open(conn):
        raise ConnectorError(403, CLOSED)


# -- names -----------------------------------------------------------------------------


def _fold(text: str) -> str:
    """Accents and case removed, one character for one: positions stay those of `text`."""
    out: list[str] = []
    for char in text:
        base = unicodedata.normalize("NFD", char)[0].lower()
        out.append(base if len(base) == 1 else char)
    return "".join(out)


def _forms(name: str) -> list[str]:
    """A name, and each of its words that looks like a name of its own (« Marie Dupont »:
    also « Marie », « Dupont »)."""
    name = name.strip()
    found = [name] if name else []
    words = re.findall(r"\w[\w'-]*", name)
    if len(words) > 1:
        found += [w for w in words if len(w) >= 3 and w[0].isupper()]
    return found


def _letter(rank: int) -> str:
    """A, B, … Z, AA, AB…"""
    letters = ""
    rank += 1
    while rank:
        rank, rest = divmod(rank - 1, 26)
        letters = chr(ord("A") + rest) + letters
    return letters


class Masker:
    """Every form of each group (a person, a term) replaced by its « Personne X », the same
    letter in every session of the space. Groups come in the order the letters are given."""

    def __init__(self, groups: list[list[str]]) -> None:
        self.names: dict[str, str] = {}
        for rank, forms in enumerate(groups):
            label = f"Personne {_letter(rank)}"
            for form in forms:
                self.names.setdefault(_fold(form), label)
        alternatives = sorted(self.names, key=len, reverse=True)
        self._pattern = (
            re.compile(
                r"(?<![\w-])(?:" + "|".join(re.escape(a) for a in alternatives) + r")(?![\w-])"
            )
            if alternatives
            else None
        )

    def spans(self, text: str) -> tuple[str, list[tuple[int, int]]]:
        """The masked text, and where its replacements are in it."""
        if self._pattern is None or not text:
            return text, []
        out: list[str] = []
        spans: list[tuple[int, int]] = []
        last = 0
        length = 0
        for match in self._pattern.finditer(_fold(text)):
            kept = text[last : match.start()]
            out.append(kept)
            length += len(kept)
            label = self.names[match.group(0)]
            out.append(label)
            spans.append((length, length + len(label)))
            length += len(label)
            last = match.end()
        out.append(text[last:])
        return "".join(out), spans

    def mask(self, text: str) -> str:
        return self.spans(text)[0]


def _first_seen(forms: list[str], folded_text: str) -> int | None:
    best: int | None = None
    for form in forms:
        found = re.search(r"(?<![\w-])" + re.escape(_fold(form)) + r"(?![\w-])", folded_text)
        if found and (best is None or found.start() < best):
            best = found.start()
    return best


def _masker(
    conn: sqlite3.Connection, space_id: int, view: corrections.CorrectedView | None
) -> Masker:
    """The names known to the space: its people (archived too), its glossary's proper nouns
    and their variants, in their order of creation, the same letters in every session of
    the space (never the alphabet's order, which would say something of the names). Then
    the voices named freely in this session, the only ones not known to the space, in their
    order of first appearance in its transcript."""
    known: list[tuple[str, int, int, list[str]]] = []
    for row in conn.execute(
        "SELECT id, name, created_at FROM person WHERE space_id = ?", (space_id,)
    ):
        known.append((row["created_at"], 0, row["id"], _forms(row["name"])))
    for row in conn.execute(
        "SELECT id, term, variants, created_at FROM glossary_entry WHERE space_id = ?",
        (space_id,),
    ):
        terms = [row["term"], *_variants(row["variants"])]
        # Proper nouns only: a common word of the trade (« catch ») stays.
        if row["term"][:1].isupper():
            known.append((row["created_at"], 1, row["id"], [f for t in terms for f in _forms(t)]))
    # Times are to the second: a person and a term made in the same second keep the order
    # (people first), which no later addition can change.
    groups = [forms for *_, forms in sorted(known, key=lambda k: k[:3])]
    if view is not None:
        free = [
            _forms(speaker.name)
            for speaker in view.speakers
            if speaker.named and speaker.person_id is None and speaker.character is None
        ]
        text = _fold(" ".join(" ".join(w.text for w in t.words) for t in view.turns))
        groups += sorted(
            free,
            key=lambda forms: (
                (seen := _first_seen(forms, text)) is None,
                seen if seen is not None else 0,
            ),
        )
    return Masker([g for g in groups if g])


def _variants(raw: str) -> list[str]:
    """Known wrong spellings of a term, as `spaces` keeps them (a JSON list of text)."""
    found: list[str] = json.loads(raw)
    return found


# -- a session as the connector sees it ------------------------------------------------


@dataclass
class _Seen:
    session: sessions.Session
    project: str | None
    names_shared: bool
    view: corrections.CorrectedView | None
    masker: Masker | None
    unreadable: str | None = None
    """Why its transcript cannot be read (damaged files, failed processing): said when it is
    read (409), never hidden."""
    listed: Masker | None = None
    """The space's masker without this session's free voices: the names `lister_espaces`
    gives, which the filters accept too."""

    def m(self, text: str) -> str:
        return self.masker.mask(text) if self.masker is not None else text

    def m_opt(self, text: str | None) -> str | None:
        return None if text is None else self.m(text)


def _accessible_ids(conn: sqlite3.Connection) -> list[str]:
    return [
        r["id"]
        for r in conn.execute(
            "SELECT s.id FROM session s JOIN space sp ON sp.id = s.space_id"
            " WHERE sp.connector_access = 1 ORDER BY s.recorded_at DESC, s.id DESC"
        )
    ]


def _seen(data: DataDir, conn: sqlite3.Connection, session_id: str) -> _Seen:
    row = conn.execute(
        "SELECT s.space_id, sp.connector_access, sp.connector_names, p.name AS project"
        " FROM session s JOIN space sp ON sp.id = s.space_id"
        " LEFT JOIN project p ON p.id = s.project_id WHERE s.id = ?",
        (session_id,),
    ).fetchone()
    if row is None or not row["connector_access"]:
        raise ConnectorError(404, NOT_FOUND)
    session = sessions.get_session(data, session_id)
    if session is None:
        raise ConnectorError(404, NOT_FOUND)
    unreadable = None
    try:
        view = corrections.build_view(data, session_id, recognise=False)
    except RunNotSucceededError:
        # Failed, not pending: waiting would not help (P8).
        view = None
        unreadable = "Le traitement de cette séance a échoué : relancez-le dans Coulisses."
    except (OSError, ValueError) as exc:
        # One damaged session must not stop the reading of the others.
        log.warning("connector: %s unreadable: %s", session_id, exc)
        view = None
        unreadable = (
            "Le transcript de cette séance est illisible : ses fichiers sont abîmés ou"
            " ont été déplacés."
        )
    names_shared = bool(row["connector_names"])
    return _Seen(
        session=session,
        project=row["project"],
        names_shared=names_shared,
        view=view,
        masker=None if names_shared else _masker(conn, row["space_id"], view),
        unreadable=unreadable,
        listed=None if names_shared else _masker(conn, row["space_id"], None),
    )


# -- answers -----------------------------------------------------------------------------


class GenerationRef(BaseModel):
    id: int
    action: str
    created_at: str


class SessionItem(BaseModel):
    id: str
    title: str | None
    recorded_at: str
    duration_s: float | None
    space: str
    project: str | None
    names_shared: bool
    transcript_ready: bool
    generations: list[GenerationRef]


class SessionList(BaseModel):
    sessions: list[SessionItem]
    next: str | None


class SearchHit(BaseModel):
    kind: Literal["title", "turn", "timed_note", "note", "generation"]
    ref: str
    at_s: float | None
    excerpt: str


class SearchSession(BaseModel):
    id: str
    title: str | None
    recorded_at: str
    space: str
    names_shared: bool
    hits: list[SearchHit]
    more_hits: bool


class SearchResults(BaseModel):
    query: str
    sessions: list[SearchSession]
    next: str | None
    problems: list[str] = []
    """Sessions of the spaces it may read that could not be searched: said (P8)."""


class SessionProvenance(BaseModel):
    engine_version: str
    profile: str
    models: dict[str, str]
    processed_at: str
    duration_s: float
    corrections: int


class SpeakerItem(BaseModel):
    name: str
    seconds: float
    turns: int


class PhaseItem(BaseModel):
    number: int
    title: str
    start_s: float | None
    end_s: float | None
    first_turn: int
    last_turn: int


class TimedNoteItem(BaseModel):
    id: int
    at_s: float
    text: str


class TranscriptFacts(BaseModel):
    ready: bool
    turns: int
    words: int


class SessionRead(BaseModel):
    id: str
    title: str | None
    recorded_at: str
    duration_s: float | None
    space: str
    project: str | None
    names_shared: bool
    attendees: list[str]
    unnamed_attendees: int | None
    speakers: list[SpeakerItem]
    phases: list[PhaseItem]
    timed_notes: list[TimedNoteItem]
    note: str | None
    transcript: TranscriptFacts
    generations: list[GenerationRef]
    provenance: SessionProvenance | None


class TurnItem(BaseModel):
    index: int
    speaker: str | None
    start_s: float | None
    end_s: float | None
    text: str


class PhaseRef(BaseModel):
    number: int
    title: str


class TranscriptPart(BaseModel):
    session_id: str
    names_shared: bool
    phase: PhaseRef | None
    view: str
    turns: list[TurnItem]
    total_turns: int
    next: int | None
    provenance: SessionProvenance | None


class GenerationProvenanceItem(BaseModel):
    model: str
    created_at: str
    transcript_version: str | None
    engine_version: str | None


class GenerationRead(BaseModel):
    session_id: str
    id: int
    action: str
    names_shared: bool
    markdown: str
    provenance: GenerationProvenanceItem


class JournalEntry(BaseModel):
    id: int
    at: str
    tool: Tool
    session_id: str | None
    session_title: str | None
    session_recorded_at: str | None
    """When it was recorded (« Séance du 29 octobre » for one without a title); None for a
    session deleted since."""
    session_deleted: bool
    names_shared: bool | None
    """None with no session: nothing passed on."""


class Journal(BaseModel):
    entries: list[JournalEntry]
    next: int | None


# -- the journal ---------------------------------------------------------------------------


def _note(conn: sqlite3.Connection, tool: Tool, read: Iterable[tuple[str, bool]]) -> None:
    """One entry per session given (none given: one entry without a session)."""
    at = now_iso()
    rows = [(at, tool, sid, int(shared)) for sid, shared in read] or [(at, tool, None, None)]
    with conn:
        conn.executemany(
            "INSERT INTO connector_access_log (at, tool, session_id, names_shared)"
            " VALUES (?, ?, ?, ?)",
            rows,
        )


def journal(data: DataDir, *, limit: int = 50, before: int | None = None) -> Journal:
    if not 1 <= limit <= 200:
        raise ConnectorError(422, "« limite » va de 1 à 200.")
    conn = connect(data)
    try:
        rows = conn.execute(
            "SELECT l.*, s.id AS still, s.title, s.recorded_at FROM connector_access_log l"
            " LEFT JOIN session s ON s.id = l.session_id"
            " WHERE (? IS NULL OR l.id < ?) ORDER BY l.id DESC LIMIT ?",
            (before, before, limit + 1),
        ).fetchall()
    finally:
        conn.close()
    entries = [
        JournalEntry(
            id=r["id"],
            at=r["at"],
            tool=r["tool"],
            session_id=r["session_id"],
            session_title=r["title"],
            session_recorded_at=r["recorded_at"],
            session_deleted=r["session_id"] is not None and r["still"] is None,
            names_shared=None if r["names_shared"] is None else bool(r["names_shared"]),
        )
        for r in rows[:limit]
    ]
    return Journal(entries=entries, next=entries[-1].id if len(rows) > limit else None)


# -- what is read ------------------------------------------------------------------------


def _provenance(
    data: DataDir, conn: sqlite3.Connection, seen: _Seen, profile: str
) -> SessionProvenance | None:
    """The engine's provenance of the version shown (P7): its runs, as `read_provenance`
    gives them."""
    if seen.view is None:
        return None
    session_id = seen.session.id
    provs: list[Provenance] = []
    for row in conn.execute(
        "SELECT run_id FROM active_run WHERE session_id = ? AND stage IN"
        " ('transcribe', 'align', 'diarize', 'attribute') ORDER BY stage",
        (session_id,),
    ):
        prov = read_provenance(data.run_dir(session_id, row["run_id"]))
        if prov is not None:
            provs.append(prov)
    if not provs:
        return None
    # The version of the « who said what » run shown (the stages of one chain share it; a
    # stage reused from an older chain keeps its own in `models`' runs). Never a comparison
    # of version strings.
    last = next((p for p in provs if p.stage.value == "attribute"), provs[-1])
    return SessionProvenance(
        engine_version=last.coulisses_version,
        # The engine's provenance does not hold it: the profile in force (only one, ADR 0019).
        profile=profile,
        models={p.stage.value: p.model.repo for p in provs if p.model is not None},
        processed_at=max(p.finished_at for p in provs).strftime(ISO_FORMAT),
        duration_s=round(sum(p.duration_s for p in provs), 1),
        corrections=len([e for e in seen.view.edits if not e.reverted]),
    )


def _shown_generations(conn: sqlite3.Connection, seen: _Seen) -> list[int]:
    """The version shown of each summary (its latest, ADR 0060), title and chapters apart."""
    return [
        r["id"]
        for r in conn.execute(
            "SELECT g.id FROM generation g WHERE g.session_id = ? AND g.action_ref NOT IN (?, ?)"
            " AND g.id = (SELECT MAX(id) FROM generation WHERE session_id = g.session_id"
            " AND action_ref = g.action_ref) ORDER BY g.id",
            (seen.session.id, TITLE_REF, PHASES_REF),
        )
    ]


def _generation(
    data: DataDir, conn: sqlite3.Connection, seen: _Seen, generation_id: int
) -> tuple[GenerationProvenance, str] | str:
    """Its provenance and its text, or why it cannot be read (said, P8)."""
    row = conn.execute(
        "SELECT run_id FROM generation WHERE id = ? AND session_id = ?",
        (generation_id, seen.session.id),
    ).fetchone()
    folder = data.run_dir(seen.session.id, row["run_id"])
    if not (folder / "provenance.json").is_file():
        return "Ce résumé n'est pas fini, ou ses fichiers ont été déplacés."
    try:
        prov = GenerationProvenance.model_validate_json(
            (folder / "provenance.json").read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as exc:
        log.warning("generation %s: provenance unreadable: %s", generation_id, exc)
        return f"Ce résumé ne peut pas être lu : sa provenance est abîmée ({type(exc).__name__})."
    if prov.status != "succeeded":
        reason = prov.error.message if prov.error is not None else "raison inconnue"
        return f"La rédaction de ce résumé a échoué : {seen.m(reason)}"
    try:
        text = (folder / "output.md").read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("generation %s: output unreadable: %s", generation_id, exc)
        return f"Ce résumé ne peut pas être lu : son texte manque ou est abîmé ({exc.strerror})."
    return prov, text


def _generation_refs(conn: sqlite3.Connection, seen: _Seen) -> list[GenerationRef]:
    """Every summary shown, readable or not: one that cannot be read says why when it is
    read (409), never left out in silence."""
    names = {a.ref: a.name for a in actions.list_actions(conn)}
    return (
        [
            GenerationRef(
                id=row["id"],
                action=seen.m(summaries.action_name(row["action_ref"], names)),
                created_at=row["created_at"],
            )
            for row in conn.execute(
                f"SELECT id, action_ref, created_at FROM generation WHERE id IN"
                f" ({','.join('?' * len(ids))})"
                " ORDER BY id",
                ids,
            )
        ]
        if (ids := _shown_generations(conn, seen))
        else []
    )


def _item(data: DataDir, conn: sqlite3.Connection, seen: _Seen) -> SessionItem:
    s = seen.session
    return SessionItem(
        id=s.id,
        title=seen.m_opt(s.title),
        recorded_at=s.recorded_at,
        duration_s=s.duration_s,
        space=seen.m(s.space_name),
        project=seen.m_opt(seen.project),
        names_shared=seen.names_shared,
        transcript_ready=seen.view is not None,
        generations=_generation_refs(conn, seen),
    )


def _in_dates(recorded_at: str, since: str | None, until: str | None) -> bool:
    day = recorded_at[:10]
    return (since is None or day >= since) and (until is None or day <= until)


_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _check_dates(since: str | None, until: str | None) -> None:
    for name, value in (("depuis", since), ("jusqu_a", until)):
        if value is not None and not _DATE.match(value):
            raise ConnectorError(422, f"« {name} » s'écrit AAAA-MM-JJ.")


def _same(shown: str | None, asked: str | None) -> bool:
    """A name as the assistant sees it (masked or not) against the one it asks for, accents
    and case ignored; nothing asked: anything goes."""
    if asked is None:
        return True
    return shown is not None and _fold(shown).strip() == _fold(asked).strip()


def _in_space(seen: _Seen, space: str | None, project: str | None = None) -> bool:
    """As named in this session, or as `lister_espaces` names it (without the session's
    free voices)."""

    def named(text: str | None, asked: str | None) -> bool:
        listed = seen.listed.mask(text) if seen.listed is not None and text else text
        return _same(seen.m_opt(text), asked) or _same(listed, asked)

    return named(seen.session.space_name, space) and named(seen.project, project)


def list_sessions(
    data: DataDir,
    *,
    space: str | None = None,
    project: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 30,
    after: str | None = None,
) -> SessionList:
    conn = connect(data)
    try:
        check_open(conn)
        _check_dates(since, until)
        if not 1 <= limit <= 100:
            raise ConnectorError(422, "« limite » va de 1 à 100.")
        cursor: tuple[str, str] | None = None
        if after is not None:
            recorded_at, _, last_id = after.partition("|")
            if not last_id:
                raise ConnectorError(422, "« apres » : passez le « next » d'une réponse.")
            cursor = (recorded_at, last_id)
        # After the last one given, by (date, id): one moved or deleted between two pages is
        # neither skipped nor given twice.
        ids = [
            r["id"]
            for r in conn.execute(
                "SELECT s.id FROM session s JOIN space sp ON sp.id = s.space_id"
                " WHERE sp.connector_access = 1 AND (? IS NULL OR (s.recorded_at, s.id) < (?, ?))"
                " ORDER BY s.recorded_at DESC, s.id DESC",
                (after, *(cursor or (None, None))),
            )
        ]
        found: list[SessionItem] = []
        more = False
        for session_id in ids:
            seen = _seen(data, conn, session_id)
            if not _in_dates(seen.session.recorded_at, since, until) or not _in_space(
                seen, space, project
            ):
                continue
            if len(found) == limit:
                more = True
                break
            found.append(_item(data, conn, seen))
        _note(conn, "lister_seances", [(i.id, i.names_shared) for i in found])
        last = found[-1] if found else None
        return SessionList(
            sessions=found,
            next=f"{last.recorded_at}|{last.id}" if more and last is not None else None,
        )
    finally:
        conn.close()


def read_session(data: DataDir, session_id: str, *, profile: str) -> SessionRead:
    conn = connect(data)
    try:
        check_open(conn)
        seen = _seen(data, conn, session_id)
        s = seen.session
        attendees = [
            seen.m(r["name"])
            for r in conn.execute(
                "SELECT p.name FROM attendee a JOIN person p ON p.id = a.person_id"
                " WHERE a.session_id = ? ORDER BY p.id",
                (session_id,),
            )
        ]
        view = seen.view
        note = notes.after_session(conn, session_id)
        answer = SessionRead(
            id=s.id,
            title=seen.m_opt(s.title),
            recorded_at=s.recorded_at,
            duration_s=s.duration_s,
            space=seen.m(s.space_name),
            project=seen.m_opt(seen.project),
            names_shared=seen.names_shared,
            attendees=attendees,
            unnamed_attendees=s.unnamed_attendees,
            speakers=[
                SpeakerItem(
                    name=_speaker_name(seen, sp), seconds=round(sp.seconds, 1), turns=sp.turns
                )
                for sp in (view.speakers if view else [])
                if sp.turns
            ],
            phases=_phases(seen),
            timed_notes=[
                TimedNoteItem(id=n.id, at_s=n.at_s, text=seen.m(n.text))
                for n in (view.timed_notes if view else [])
            ],
            note=seen.m(note.text) if note is not None and note.text.strip() else None,
            transcript=TranscriptFacts(
                ready=view is not None,
                turns=len(view.turns) if view else 0,
                words=view.word_count if view else 0,
            ),
            generations=_generation_refs(conn, seen),
            provenance=_provenance(data, conn, seen, profile),
        )
        _note(conn, "lire_seance", [(s.id, seen.names_shared)])
        return answer
    finally:
        conn.close()


def _speaker_name(seen: _Seen, speaker: corrections.Speaker) -> str:
    if speaker.character and speaker.played_by:
        return f"{seen.m(speaker.character)} (joué par {seen.m(speaker.played_by)})"
    return seen.m(speaker.name)


def _speaker_names(seen: _Seen, speaker: corrections.Speaker) -> list[str]:
    """What the assistant may call a voice by, as it sees it: its name as given, and for a
    character, the character and who plays it."""
    found = [_speaker_name(seen, speaker), seen.m(speaker.name)]
    if speaker.character and speaker.played_by:
        found += [seen.m(speaker.character), seen.m(speaker.played_by)]
    return found


def _phases(seen: _Seen) -> list[PhaseItem]:
    if seen.view is None:
        return []
    return [
        PhaseItem(
            number=k + 1,
            title=seen.m(p.title),
            start_s=p.start,
            end_s=p.end,
            first_turn=p.turn,
            last_turn=p.end_turn - 1,
        )
        for k, p in enumerate(seen.view.phases)
    ]


def _secret(conn: sqlite3.Connection) -> bytes:
    """A random key of this Mac, made once: the « view » given to the assistant is keyed by
    it, so that the masked names it covers cannot be guessed from it by trying names."""
    row = conn.execute("SELECT value FROM app_setting WHERE key = ?", (SECRET_KEY,)).fetchone()
    if row is not None:
        return bytes.fromhex(row["value"])
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO app_setting (key, value) VALUES (?, ?)",
            (SECRET_KEY, secrets.token_hex(32)),
        )
    row = conn.execute("SELECT value FROM app_setting WHERE key = ?", (SECRET_KEY,)).fetchone()
    return bytes.fromhex(row["value"])


def _view_key(conn: sqlite3.Connection, seen: _Seen) -> str:
    """What a reading in parts reads: the version shown, its corrections, its chapters, and
    the names masked with their letters (a person added: another one may get « B »)."""
    view = seen.view
    assert view is not None
    live = sorted(e.id for e in view.edits if not e.reverted)
    letters = sorted(seen.masker.names.items()) if seen.masker is not None else None
    raw = f"{view.run_id}|{live}|{view.phases_run_id}|{letters}"
    return hmac.new(_secret(conn), raw.encode(), hashlib.sha256).hexdigest()[:16]


def read_transcript(
    data: DataDir,
    session_id: str,
    *,
    profile: str,
    phase: int | None = None,
    since: int | None = None,
    count: int = DEFAULT_TURNS,
    view_key: str | None = None,
    speaker: str | None = None,
) -> TranscriptPart:
    conn = connect(data)
    try:
        check_open(conn)
        if not 1 <= count <= MAX_TURNS:
            raise ConnectorError(422, f"« nombre » va de 1 à {MAX_TURNS}.")
        seen = _seen(data, conn, session_id)
        view = seen.view
        if view is None:
            raise ConnectorError(
                409, seen.unreadable or "Le transcript de cette séance n'est pas encore prêt."
            )
        turns = view.turns
        chosen: PhaseRef | None = None
        if phase is not None:
            if not 1 <= phase <= len(view.phases):
                n = len(view.phases)
                raise ConnectorError(
                    422,
                    f"Cette séance a {n} chapitre(s) : « chapitre » va de 1 à {n}."
                    if n
                    else "Les chapitres de cette séance ne sont pas faits : "
                    "lisez-la sans « chapitre ».",
                )
            p = view.phases[phase - 1]
            chosen = PhaseRef(number=phase, title=seen.m(p.title))
            turns = [t for t in turns if p.turn <= t.index < p.end_turn]
        speakers = {sp.label: sp for sp in view.speakers}
        if speaker is not None:
            wanted = _fold(speaker).strip()
            labels = {
                label
                for label, sp in speakers.items()
                if wanted in (_fold(n).strip() for n in _speaker_names(seen, sp))
            }
            if not labels:
                raise ConnectorError(
                    422,
                    f"Aucune voix « {speaker} » dans cette séance : lire_seance donne ses voix.",
                )
            turns = [t for t in turns if t.speaker in labels]
        # `depuis` alone starts anywhere (an excerpt found by `chercher`); `vue`, once given,
        # makes sure that what follows is read from the same transcript.
        key = _view_key(conn, seen)
        if view_key is not None and view_key != key:
            raise ConnectorError(409, CHANGED)
        rest = [t for t in turns if since is None or t.index >= since]
        part = rest[:count]
        items = [
            TurnItem(
                index=t.index,
                speaker=_speaker_name(seen, speakers[t.speaker])
                if t.speaker is not None and t.speaker in speakers
                else None,
                start_s=t.start,
                end_s=t.end,
                text=seen.m(" ".join(w.text for w in t.words)),
            )
            for t in part
        ]
        answer = TranscriptPart(
            session_id=session_id,
            names_shared=seen.names_shared,
            phase=chosen,
            view=key,
            turns=items,
            total_turns=len(turns),
            next=rest[count].index if len(rest) > count else None,
            provenance=_provenance(data, conn, seen, profile),
        )
        _note(conn, "lire_transcript", [(session_id, seen.names_shared)])
        return answer
    finally:
        conn.close()


def read_generation(data: DataDir, session_id: str, generation_id: int) -> GenerationRead:
    conn = connect(data)
    try:
        check_open(conn)
        seen = _seen(data, conn, session_id)
        if generation_id not in _shown_generations(conn, seen):
            raise ConnectorError(404, "Résumé introuvable.")
        read = _generation(data, conn, seen, generation_id)
        if isinstance(read, str):
            raise ConnectorError(409, read)
        prov, text = read
        engine: str | None = None
        if prov.source_run_id:
            source = read_provenance(data.run_dir(session_id, prov.source_run_id))
            engine = source.coulisses_version if source is not None else None
        answer = GenerationRead(
            session_id=session_id,
            id=generation_id,
            action=seen.m(prov.action_name),
            names_shared=seen.names_shared,
            markdown=seen.m(text),
            provenance=GenerationProvenanceItem(
                model=prov.model,
                created_at=prov.finished_at.strftime(ISO_FORMAT),
                transcript_version=prov.source_run_id,
                engine_version=engine,
            ),
        )
        _note(conn, "lire_resume", [(session_id, seen.names_shared)])
        return answer
    finally:
        conn.close()


# -- search ------------------------------------------------------------------------------


def _query_words(query: str) -> list[str]:
    return [_fold(w) for w in re.findall(r"\w+", query)]


def _visible_words(text: str, masker: Masker | None) -> tuple[str, list[tuple[int, int]]]:
    """The text as the assistant sees it, and the words it may be found by: those of a
    « Personne X » put in its place are not."""
    shown, spans = masker.spans(text) if masker is not None else (text, [])
    words = [
        (m.start(), m.end())
        for m in re.finditer(r"\w+", shown)
        if not any(a <= m.start() < b for a, b in spans)
    ]
    return shown, words


def _found(
    query: list[str], text: str, masker: Masker | None
) -> tuple[str, list[tuple[int, int]]] | None:
    """Whether every word of the query begins a word of the text as seen (as the search of
    Coulisses does, §7.11); the text as seen and where its hits are."""
    shown, words = _visible_words(text, masker)
    folded = _fold(shown)
    for q in query:
        if not any(folded[a:b].startswith(q) for a, b in words):
            return None
    return shown, [(a, b) for a, b in words if any(folded[a:b].startswith(q) for q in query)]


def _excerpt(shown: str, hits: list[tuple[int, int]]) -> str:
    """Around the first hit, `EXCERPT_WORDS` words; the hits between « and »."""
    pieces = [(m.start(), m.end()) for m in re.finditer(r"\S+", shown)]
    if not pieces:
        return shown
    first = hits[0][0] if hits else 0
    centre = next((k for k, (a, b) in enumerate(pieces) if a <= first < b), 0)
    lo = max(0, centre - EXCERPT_WORDS // 2)
    hi = min(len(pieces), lo + EXCERPT_WORDS)
    start, end = pieces[lo][0], pieces[hi - 1][1]
    out: list[str] = []
    cursor = start
    for a, b in hits:
        if a < start or b > end:
            continue
        out.append(shown[cursor:a])
        out.append(f"«{shown[a:b]}»")
        cursor = b
    out.append(shown[cursor:end])
    return ("… " if lo > 0 else "") + "".join(out) + (" …" if hi < len(pieces) else "")


_KIND: dict[str, Callable[[str], tuple[str, str]]] = {
    "title": lambda ref: ("title", ""),
    "turn": lambda ref: ("turn", ref),
    "note": lambda ref: ("note", "") if ref == "apres" else ("timed_note", ref),
    "summary": lambda ref: ("generation", ref),
}


def _page_key(ids: list[str]) -> str:
    return hashlib.sha256("|".join(ids).encode()).hexdigest()[:8]


def find(
    data: DataDir,
    query: str,
    *,
    space: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 10,
    after: str | None = None,
    project: str | None = None,
) -> SearchResults:
    conn = connect(data)
    try:
        check_open(conn)
    finally:
        conn.close()
    if not 1 <= len(query) <= 200:
        raise ConnectorError(422, "« q » fait de 1 à 200 caractères.")
    if not 1 <= limit <= 30:
        raise ConnectorError(422, "« limite » va de 1 à 30.")
    _check_dates(since, until)
    # The index is the service's cache (§7.11): brought up to date as for any search.
    unreadable = search.refresh_sessions(data)
    words = _query_words(query)
    match = search.fts_match(query)
    conn = connect(data)
    try:
        allowed = set(_accessible_ids(conn))
        problems: list[str] = []
        for session_id, _ in unreadable:
            if session_id not in allowed:
                continue
            # Its files are what failed: its title masked without its transcript (the
            # letters in order of creation), never reading it again here.
            row = conn.execute(
                "SELECT s.title, s.recorded_at, s.space_id, sp.connector_names FROM session s"
                " JOIN space sp ON sp.id = s.space_id WHERE s.id = ?",
                (session_id,),
            ).fetchone()
            title = row["title"]
            if title and not row["connector_names"]:
                title = _masker(conn, row["space_id"], None).mask(title)
            name = title or f"la séance du {row['recorded_at'][:10]}"
            problems.append(f"« {name} » n'a pas pu être lue pour la recherche.")
        rows = (
            conn.execute(
                "SELECT session_id, kind, ref, at_s, text FROM search_index"
                " WHERE search_index MATCH ? ORDER BY rank",
                (match,),
            ).fetchall()
            if match is not None and allowed
            else []
        )
        by_session: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            if row["session_id"] in allowed:
                by_session.setdefault(row["session_id"], []).append(row)
        found: list[SearchSession] = []
        for session_id, entries in by_session.items():
            seen = _seen(data, conn, session_id)
            if not _in_dates(seen.session.recorded_at, since, until) or not _in_space(
                seen, space, project
            ):
                continue
            hits: list[SearchHit] = []
            more = False
            for entry in entries:
                result = _found(words, entry["text"], seen.masker)
                if result is None:
                    continue  # found by a name the assistant does not see
                if len(hits) == MAX_HITS:
                    more = True
                    break
                shown, hit_words = result
                kind, ref = _KIND[entry["kind"]](entry["ref"])
                hits.append(
                    SearchHit(
                        kind=kind,  # type: ignore[arg-type]
                        ref=ref,
                        at_s=entry["at_s"] if kind in ("turn", "timed_note") else None,
                        excerpt=_excerpt(shown, hit_words),
                    )
                )
            if hits:
                s = seen.session
                found.append(
                    SearchSession(
                        id=s.id,
                        title=seen.m_opt(s.title),
                        recorded_at=s.recorded_at,
                        space=seen.m(s.space_name),
                        names_shared=seen.names_shared,
                        hits=hits,
                        more_hits=more,
                    )
                )
        key = _page_key([f.id for f in found])
        offset = 0
        if after is not None:
            start, _, given = after.partition(".")
            if given != key or not start.isdigit():
                raise ConnectorError(409, SEARCH_CHANGED)
            offset = int(start)
        page = found[offset : offset + limit]
        nxt = f"{offset + limit}.{key}" if offset + limit < len(found) else None
        _note(conn, "chercher", [(f.id, f.names_shared) for f in page])
        return SearchResults(query=query, sessions=page, next=nxt, problems=problems)
    finally:
        conn.close()


# -- spaces ------------------------------------------------------------------------------


class ProjectItem(BaseModel):
    name: str
    archived: bool
    sessions: int


class SpaceItem(BaseModel):
    name: str
    names_shared: bool
    archived: bool
    sessions: int
    projects: list[ProjectItem]
    """Its projects, those without a session too; its sessions outside any project are the
    rest of `sessions`."""


class SpaceList(BaseModel):
    spaces: list[SpaceItem]


def list_spaces(data: DataDir) -> SpaceList:
    """The spaces open to the connector, their projects and how many sessions each holds,
    names masked as everywhere else. In their order of creation, never the alphabet's (which
    would say something of masked names). In the journal as one entry without a session."""
    conn = connect(data)
    try:
        check_open(conn)
        found: list[SpaceItem] = []
        for space in conn.execute(
            "SELECT sp.id, sp.name, sp.connector_names, sp.archived_at,"
            " (SELECT COUNT(*) FROM session s WHERE s.space_id = sp.id) AS sessions"
            " FROM space sp WHERE sp.connector_access = 1"
            " ORDER BY sp.archived_at IS NOT NULL, sp.id"
        ).fetchall():
            names_shared = bool(space["connector_names"])
            masker = None if names_shared else _masker(conn, space["id"], None)

            def m(text: str, masker: Masker | None = masker) -> str:
                return masker.mask(text) if masker is not None else text

            projects = [
                ProjectItem(
                    name=m(p["name"]), archived=p["archived_at"] is not None, sessions=p["sessions"]
                )
                for p in conn.execute(
                    "SELECT p.name, p.archived_at,"
                    " (SELECT COUNT(*) FROM session s WHERE s.project_id = p.id) AS sessions"
                    " FROM project p WHERE p.space_id = ?"
                    " ORDER BY p.archived_at IS NOT NULL, p.id",
                    (space["id"],),
                )
            ]
            found.append(
                SpaceItem(
                    name=m(space["name"]),
                    names_shared=names_shared,
                    archived=space["archived_at"] is not None,
                    sessions=space["sessions"],
                    projects=projects,
                )
            )
        _note(conn, "lister_espaces", [])
        return SpaceList(spaces=found)
    finally:
        conn.close()


# -- settings ----------------------------------------------------------------------------

CONNECTOR_DIR = Path.home() / "Coulisses" / "Connecteur"
"""Where the app in the Dock writes the fixed launcher (ADR 0065), out of `Données/`."""


class SpaceOptions(BaseModel):
    id: int
    name: str
    connector_access: bool
    connector_names: bool
    archived: bool
    """Archived and still accessible, it is read all the same: its sessions are there."""


class ConnectorSettings(BaseModel):
    open: bool
    launcher: str
    launcher_ready: bool
    """The launcher exists and runs: written by the app in the Dock at its start."""
    launcher_problem: str | None
    """What the service sees when it is not ready, in French; None when it is."""
    claude_code_command: str
    mcpb: str | None
    """The extension for Claude Desktop, None as long as it does not exist."""
    spaces: list[SpaceOptions]


def server_name(dev: bool) -> str:
    return "coulisses-dev" if dev else "coulisses"


def launcher(dev: bool) -> Path:
    return CONNECTOR_DIR / ("coulisses-mcp-dev" if dev else "coulisses-mcp")


def settings_info(data: DataDir, *, dev: bool) -> ConnectorSettings:
    """What the « Connecteur » tab shows (contract §2), the connector open or closed."""
    path = launcher(dev)
    mcpb = CONNECTOR_DIR / ("Coulisses (dév).mcpb" if dev else "Coulisses.mcpb")
    conn = connect(data)
    try:
        spaces = [
            SpaceOptions(
                id=r["id"],
                name=r["name"],
                connector_access=bool(r["connector_access"]),
                connector_names=bool(r["connector_names"]),
                archived=r["archived_at"] is not None,
            )
            for r in conn.execute(
                "SELECT * FROM space ORDER BY archived_at IS NOT NULL, name COLLATE NOCASE"
            )
        ]
        opened = is_open(conn)
    finally:
        conn.close()
    if not path.is_file():
        problem: str | None = (
            "Le lanceur n'a pas encore été écrit : ouvrez Coulisses depuis le Dock."
        )
    elif not os.access(path, os.X_OK):
        problem = "Le lanceur n'est pas exécutable. Rouvrez Coulisses depuis le Dock."
    else:
        problem = None
    return ConnectorSettings(
        open=opened,
        launcher=str(path),
        launcher_ready=problem is None,
        launcher_problem=problem,
        claude_code_command=f"claude mcp add {server_name(dev)} -- {shlex.quote(str(path))}",
        mcpb=str(mcpb) if mcpb.is_file() else None,
        spaces=spaces,
    )
