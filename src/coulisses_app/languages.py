"""The language a session is transcribed in (ADR 0072).

The languages are the engine's (`languages()`): their codes, their names (already in
French), their models. None is written here but « fr », the default (P6). Reading them
never touches the network, and checks the models on disk (a few milliseconds).
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from coulisses.api import LanguageSupport, Provenance
from coulisses.api import languages as engine_languages
from pydantic import BaseModel

from coulisses_app.jobs import DEFAULT_LANGUAGE as DEFAULT
from coulisses_app.jobs import WaitsFor
from coulisses_app.spaces import ConflictError, SpaceError

FIRST_ENGINE_WITH_LANGUAGE = (1, 14, 0)
"""Before this version, the engine transcribed in French only and wrote no language."""


def supported(profile: str, root: Path | None = None) -> list[LanguageSupport]:
    """The languages the chain transcribes, French first, then in the engine's order."""
    return [s for s in engine_languages(profile, root=root).languages if handled(s)]


def handled(support: LanguageSupport) -> bool:
    """Transcribed and aligned by the chain: one that is not would be refused by the engine
    (`language_unsupported`), so it is never offered."""
    return support.transcribed and support.aligned


def _names(found: list[LanguageSupport]) -> str:
    return ", ".join(s.label.lower() for s in found)


def check(profile: str, code: str, root: Path | None = None) -> LanguageSupport:
    """The language, if the engine handles it; else refused before anything is recorded."""
    found = supported(profile, root)
    for support in found:
        if support.language == code and handled(support):
            return support
    raise SpaceError(
        f"Cette langue n'est pas prise en charge. Langues possibles : {_names(found)}."
    )


def waits_for(profile: str, code: str, root: Path | None = None) -> WaitsFor | None:
    """What a processing in this language must wait for: a model missing from this Mac, or
    the language itself, no longer handled by the engine. None: it may start. Nothing is
    downloaded here (P1)."""
    for support in supported(profile, root):
        if support.language != code or not handled(support):
            continue
        if not support.missing_models:
            return None
        return WaitsFor(
            reason="model_missing",
            language=code,
            label=support.label,
            missing_models=list(support.missing_models),
            download_bytes=support.download_bytes,
        )
    return WaitsFor(reason="language_unsupported", language=code)


def of_transcription(prov: Provenance) -> str | None:
    """The language of a transcription, from its provenance (P7): the one the engine was
    given. One made before the engine had languages is French, the only one then. None: a
    later one that does not say it, which is never taken for French."""
    spoken = prov.inputs.get("language")
    if isinstance(spoken, str) and spoken:
        return spoken
    numbers = re.match(r"(\d+)\.(\d+)\.(\d+)", prov.coulisses_version)
    if numbers is not None and tuple(int(n) for n in numbers.groups()) < FIRST_ENGINE_WITH_LANGUAGE:
        return DEFAULT
    return None


def said_failure(prov: Provenance, profile: str, root: Path | None = None) -> str | None:
    """A stage refused for its language, said in French with what to do; None otherwise."""
    error = prov.error
    if error is None or error.code is None:
        return None
    if error.code.value == "language_unsupported":
        found = supported(profile, root)
        return (
            f"La langue « {error.details.get('language', '?')} » n'est pas prise en charge par "
            f"le moteur. Langues possibles : {_names(found)}. Choisissez-en une autre, puis "
            "reprenez."
        )
    if error.code.value == "model_missing":
        return (
            f"Le modèle « {error.details.get('model', '?')} » n'est pas sur ce Mac. "
            "Téléchargez-le dans les réglages, onglet Transcription, puis reprenez."
        )
    return None


def models_of(support: LanguageSupport) -> list[str]:
    """Every model a language needs."""
    return sorted(
        {m for m in (support.transcription_model, support.alignment_model) if m is not None}
    )


def own_models(found: list[LanguageSupport]) -> dict[str, list[str]]:
    """Language → the models only it needs: removing them is removing the language. A model
    every language needs (the transcription's) is never one of them."""
    needs = {s.language: set(models_of(s)) for s in found}
    return {
        code: sorted(m for m in models if sum(m in other for other in needs.values()) == 1)
        for code, models in needs.items()
    }


class SpaceUse(BaseModel):
    id: int
    name: str
    archived: bool


class WaitingSession(BaseModel):
    id: str
    title: str | None
    recorded_at: str


class UsedBy(BaseModel):
    spaces: list[SpaceUse] = []
    """Spaces that have it as their default language (archived ones too)."""
    waiting_sessions: list[WaitingSession] = []
    """Sessions whose processing waits in the queue, in this language."""


def used_by(conn: sqlite3.Connection, code: str) -> UsedBy:
    spaces = [
        SpaceUse(id=r["id"], name=r["name"], archived=r["archived_at"] is not None)
        for r in conn.execute(
            "SELECT id, name, archived_at FROM space WHERE language = ? ORDER BY name", (code,)
        )
    ]
    waiting = [
        WaitingSession(id=r["id"], title=r["title"], recorded_at=r["recorded_at"])
        for r in conn.execute(
            "SELECT DISTINCT s.id, s.title, s.recorded_at FROM job j"
            " JOIN session s ON s.id = j.session_id"
            " WHERE j.kind = 'chain' AND j.state = 'queued'"
            " AND coalesce(json_extract(j.params, '$.language'), ?) = ?"
            " ORDER BY s.recorded_at",
            (DEFAULT, code),
        )
    ]
    return UsedBy(spaces=spaces, waiting_sessions=waiting)


def refuse_removal(conn: sqlite3.Connection, profile: str, key: str, root: Path | None) -> None:
    """A model only a language needs is not removed while that language serves: a space has
    it by default, or a session waits in it. Said with where (409)."""
    found = supported(profile, root)
    # A model every language needs is not one language's; one some need, each of them.
    if all(key in models_of(s) for s in found):
        return
    for support in found:
        if key not in models_of(support):
            continue
        use = used_by(conn, support.language)
        where: list[str] = []
        if use.spaces:
            names = ", ".join(
                f"« {s.name} »{' (archivé)' if s.archived else ''}" for s in use.spaces
            )
            where.append(
                f"c'est la langue de l'espace {names}"
                if len(use.spaces) == 1
                else f"c'est la langue des espaces {names}"
            )
        if use.waiting_sessions:
            titles = ", ".join(
                f"« {s.title} »" if s.title else f"celle du {s.recorded_at[:10]}"
                for s in use.waiting_sessions
            )
            count = len(use.waiting_sessions)
            where.append(
                f"une séance attend ce modèle ({titles})"
                if count == 1
                else f"{count} séances attendent ce modèle ({titles})"
            )
        if where:
            raise ConflictError(
                f"La langue « {support.label} » sert encore : {', et '.join(where)}. "
                "Changez-les d'abord."
            )
