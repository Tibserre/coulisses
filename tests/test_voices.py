"""Recognising voices from one session to the next (ADR 0057): profiles rebuilt from the
user's namings and the engine's embeddings, proposals only, in the spaces that turned it on.

The engine's fake diarizer keeps no embedding: each test gives the diarization of a
synthetic session the voices it needs, in its temporary folder."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from coulisses.api import VOICE_MODEL_REPO

from coulisses_app import corrections, spaces
from coulisses_app.corrections import AssignSpeaker, MergeSpeakers, RejectVoiceMatch
from coulisses_app.paths import DataDir
from coulisses_app.voices import choices

from .test_corrections import journal
from .test_versions import processed, shown

MODEL = f"{VOICE_MODEL_REPO}@abc123"


def direction(seed: int, near: np.ndarray | None = None) -> np.ndarray:
    """A voice: random, or close to another one (cosine distance well under 0.25)."""
    rng = np.random.default_rng(seed)
    v = rng.normal(size=256)
    if near is not None:
        v = near / np.linalg.norm(near) * 10 + v / np.linalg.norm(v)
    return v / np.linalg.norm(v)


def give_voices(data: DataDir, session_id: str, voices: dict[str, np.ndarray | None]) -> None:
    """The embeddings the engine would have kept with this session's diarization."""
    run_dir = data.run_dir(session_id, shown(data, session_id)["diarize"])
    out = json.loads((run_dir / "output.json").read_text(encoding="utf-8"))
    rows = [voices.get(s) for s in out["speakers"]]
    np.save(
        run_dir / "speaker_embeddings.npy",
        np.array([np.zeros(256) if r is None else r for r in rows]),
    )
    out["speaker_embeddings_file"] = "speaker_embeddings.npy"
    out["speaker_embeddings_model"] = MODEL
    out["speaker_embeddings_speech_s"] = [0.0 if r is None else 30.0 for r in rows]
    (run_dir / "output.json").write_text(json.dumps(out), encoding="utf-8")


@pytest.fixture
def troupe(data: DataDir) -> tuple[int, int]:
    """The default space, recognising voices, and Marie in it."""
    space = spaces.list_spaces(data)[0]
    spaces.update_space(data, space.id, voice_recognition=True)
    marie = spaces.add_person(data, space.id, kind="member", name="Marie")
    return space.id, marie.id


MARIE = direction(1)
JULES = direction(2)


def two_sessions(data: DataDir, recording: Path) -> tuple[str, str]:
    """Marie speaks as S1 in both (the fake chain gives every line to S1)."""
    first, second = processed(data, recording), processed(data, recording)
    give_voices(data, first, {"S1": MARIE, "S2": None})
    give_voices(data, second, {"S1": direction(3, near=MARIE), "S2": JULES})
    return first, second


def proposals(data: DataDir, session_id: str) -> dict[str, str | None]:
    view = corrections.build_view(data, session_id)
    assert view is not None
    return {s.label: s.proposal.name if s.proposal else None for s in view.speakers if s.label}


def test_a_voice_named_in_one_session_is_proposed_in_the_next(
    data: DataDir, recording: Path, troupe: tuple[int, int]
) -> None:
    _, marie = troupe
    first, second = two_sessions(data, recording)
    assert proposals(data, second) == {"S1": None}  # nobody confirmed yet

    corrections.add(data, first, {"kind": "assign_speaker", "speaker": "S1", "person_id": marie})
    assert proposals(data, second) == {"S1": "Marie"}
    view = corrections.build_view(data, second)
    assert view is not None
    s1 = next(s for s in view.speakers if s.label == "S1")
    # Only a proposal: the voice stays unnamed until the user says so (P3).
    assert not s1.named and s1.proposal and 0 <= s1.proposal.distance < 0.25

    # Confirming is naming it: the profile then holds both sessions.
    corrections.add(data, second, {"kind": "assign_speaker", "speaker": "S1", "person_id": marie})
    assert proposals(data, second) == {"S1": None}

    # Another voice is not Marie's: nothing proposed.
    third = processed(data, recording)
    give_voices(data, third, {"S1": JULES})
    assert proposals(data, third) == {"S1": None}


def test_nothing_is_proposed_in_a_space_that_does_not_recognise_voices(
    data: DataDir, recording: Path, troupe: tuple[int, int]
) -> None:
    space, marie = troupe
    first, second = two_sessions(data, recording)
    corrections.add(data, first, {"kind": "assign_speaker", "speaker": "S1", "person_id": marie})
    spaces.update_space(data, space, voice_recognition=False)
    assert proposals(data, second) == {"S1": None}
    # Turned on again: the namings already made count at once (nothing was stored).
    spaces.update_space(data, space, voice_recognition=True)
    assert proposals(data, second)["S1"] == "Marie"


def test_undoing_the_naming_takes_the_voice_out_of_the_profile(
    data: DataDir, recording: Path, troupe: tuple[int, int]
) -> None:
    _, marie = troupe
    first, second = two_sessions(data, recording)
    view = corrections.add(
        data, first, {"kind": "assign_speaker", "speaker": "S1", "person_id": marie}
    )
    corrections.undo(data, first, view.edits[-1].id)
    assert proposals(data, second)["S1"] is None


def test_no_is_remembered_for_that_voice_and_undone_like_any_correction(
    data: DataDir, recording: Path, troupe: tuple[int, int]
) -> None:
    _, marie = troupe
    first, second = two_sessions(data, recording)
    corrections.add(data, first, {"kind": "assign_speaker", "speaker": "S1", "person_id": marie})
    view = corrections.add(
        data, second, {"kind": "reject_voice_match", "speaker": "S1", "person_id": marie}
    )
    assert view.edits[-1].description == "Locuteur 1 : pas Marie"
    assert proposals(data, second)["S1"] is None
    corrections.undo(data, second, view.edits[-1].id)
    assert proposals(data, second)["S1"] == "Marie"


def test_a_character_or_a_free_name_feeds_no_profile(
    data: DataDir, recording: Path, troupe: tuple[int, int]
) -> None:
    _, marie = troupe
    first, second = two_sessions(data, recording)
    corrections.add(
        data,
        first,
        {"kind": "assign_speaker", "speaker": "S1", "person_id": marie, "character": "Le roi"},
    )
    assert proposals(data, second)["S1"] is None
    corrections.add(data, first, {"kind": "assign_speaker", "speaker": "S1", "name": "Marie"})
    assert proposals(data, second)["S1"] is None


def test_an_unreadable_voice_file_is_said_not_hidden(
    data: DataDir, recording: Path, troupe: tuple[int, int]
) -> None:
    _, marie = troupe
    first, second = two_sessions(data, recording)
    corrections.add(data, first, {"kind": "assign_speaker", "speaker": "S1", "person_id": marie})
    run_dir = data.run_dir(first, shown(data, first)["diarize"])
    (run_dir / "output.json").write_text("{", encoding="utf-8")  # damaged in the Finder
    from coulisses_app import voices

    voices._EMBEDDINGS.clear()  # pyright: ignore[reportPrivateUsage]
    view = corrections.build_view(data, second)
    assert view is not None
    assert view.voices_problem and "la séance du" in view.voices_problem
    assert first not in view.voices_problem  # no technical detail outside the log
    assert all(s.proposal is None for s in view.speakers)


def test_a_voice_from_before_the_engine_kept_voices_is_never_proposed(
    data: DataDir, recording: Path, troupe: tuple[int, int]
) -> None:
    _, marie = troupe
    first, second = processed(data, recording), processed(data, recording)
    give_voices(data, first, {"S1": MARIE})
    corrections.add(data, first, {"kind": "assign_speaker", "speaker": "S1", "person_id": marie})
    assert proposals(data, second) == {"S1": None}  # no embeddings: nothing


# -- which voices are confirmed (pure logic) ----------------------------------------------


def test_a_voice_merged_into_a_named_voice_is_confirmed_too() -> None:
    confirmed, _ = choices(
        journal(AssignSpeaker(speaker="7", person_id=1), MergeSpeakers(source="4", target="7")),
        "attribute-a",
    )
    assert confirmed == {"7": 1, "4": 1}


def test_merging_then_naming_confirms_both() -> None:
    confirmed, _ = choices(
        journal(MergeSpeakers(source="4", target="7"), AssignSpeaker(speaker="7", person_id=1)),
        "attribute-a",
    )
    assert confirmed == {"7": 1, "4": 1}


def test_an_undone_naming_or_another_versions_confirms_nothing() -> None:
    assert (
        choices(journal(AssignSpeaker(speaker="7", person_id=1), reverted=(1,)), "attribute-a")[0]
        == {}
    )
    assert choices(journal(AssignSpeaker(speaker="7", person_id=1)), "attribute-b")[0] == {}


def test_the_latest_name_of_a_voice_is_the_one_confirmed() -> None:
    confirmed, rejected = choices(
        journal(
            AssignSpeaker(speaker="7", person_id=1),
            AssignSpeaker(speaker="7", person_id=2),
            RejectVoiceMatch(speaker="2", person_id=1),
        ),
        "attribute-a",
    )
    assert confirmed == {"7": 2} and rejected == {("2", 1)}


def test_an_archived_person_is_never_proposed(
    data: DataDir, recording: Path, troupe: tuple[int, int]
) -> None:
    _, marie = troupe
    first, second = two_sessions(data, recording)
    corrections.add(data, first, {"kind": "assign_speaker", "speaker": "S1", "person_id": marie})
    spaces.update_person(data, marie, archived=True)
    assert proposals(data, second)["S1"] is None
