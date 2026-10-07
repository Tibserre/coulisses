"""Carrying corrections over to a new version, by measured time (pure logic, step 7)."""

from __future__ import annotations

from coulisses.api import AttributedTranscript, AttributedWord, Turn

from coulisses_app.carryover import plan
from coulisses_app.corrections import (
    AnyRequest,
    AssignSpeaker,
    EditText,
    MergeSpeakers,
    ReassignTurns,
    RemovePhase,
    SetPhase,
)

Line = tuple[str, str, float, float]
"""(voice, text, start, end)"""


def transcript(*lines: Line) -> AttributedTranscript:
    words: list[AttributedWord] = []
    turns: list[Turn] = []
    for speaker, text, start, end in lines:
        first = len(words)
        tokens = text.split()
        step = (end - start) / len(tokens)
        for k, token in enumerate(tokens):
            words.append(
                AttributedWord(
                    text=token,
                    start=start + k * step,
                    end=start + (k + 1) * step,
                    speakers=(speaker,),
                    speaker=speaker,
                )
            )
        turns.append(
            Turn(speaker=speaker, first_word=first, end_word=len(words), start=start, end=end)
        )
    return AttributedTranscript(
        reference_source="ref",
        language="fr",
        words=tuple(words),
        turns=tuple(turns),
        speakers=tuple(sorted({line[0] for line in lines})),
    )


SOURCE = transcript(
    ("A", "Bonjour Kathy", 0.0, 2.0),
    ("B", "ça va", 3.0, 5.0),
    ("A", "encore moi", 6.0, 8.0),
    ("C", "salut", 9.0, 10.0),
)
NAMES = {"A": "Locuteur 1", "B": "Paul", "C": "Léa"}


def carry(target: AttributedTranscript, *requests: AnyRequest):
    edits = list(enumerate(requests, start=1))
    return plan(
        SOURCE,
        target,
        edits,
        names=NAMES,
        descriptions={i: f"correction {i}" for i, _ in edits},
    )


# Voices separated again: the same lines, other labels, C now within B's voice.
REVOICED = transcript(
    ("X", "Bonjour Kathy", 0.0, 2.0),
    ("Y", "ça va", 3.0, 5.0),
    ("X", "encore moi", 6.0, 8.0),
    ("Y", "salut", 9.0, 10.0),
)


def test_a_name_goes_to_the_new_voice_holding_its_time() -> None:
    [result] = carry(REVOICED, AssignSpeaker(speaker="A", name="Marie"))
    assert result.applied
    assert result.copy_request == AssignSpeaker(speaker="X", name="Marie")


def test_a_name_is_not_carried_when_no_voice_holds_half_of_its_time() -> None:
    # A spoke 4 s: 1.9 s are now X's, 1.9 s Z's.
    split = transcript(
        ("X", "Bonjour Kathy", 0.0, 1.9),
        ("Y", "ça va", 3.0, 5.0),
        ("Z", "encore moi", 6.0, 7.9),
        ("Y", "salut", 9.0, 10.0),
    )
    [result] = carry(split, AssignSpeaker(speaker="A", name="Marie"))
    assert not result.applied
    assert (
        result.reason is not None and "la moitié du temps de parole de Locuteur 1" in result.reason
    )


def test_two_names_found_in_one_voice_the_longer_keeps_it_the_other_is_listed() -> None:
    paul, lea = carry(
        REVOICED, AssignSpeaker(speaker="B", name="Paul"), AssignSpeaker(speaker="C", name="Léa")
    )
    assert paul.applied and paul.copy_request == AssignSpeaker(speaker="Y", name="Paul")
    assert not lea.applied
    assert lea.reason == "dans la nouvelle version, sa voix est réunie avec celle de Paul"


def test_a_merge_of_voices_already_one_needs_nothing_written() -> None:
    [result] = carry(REVOICED, MergeSpeakers(source="C", target="B"))
    assert result.applied and result.copy_request is None


def test_a_merge_follows_the_voices() -> None:
    [result] = carry(SOURCE, MergeSpeakers(source="C", target="B"))
    assert result.copy_request == MergeSpeakers(source="C", target="B")


def test_a_split_and_the_name_of_the_new_voice_are_carried() -> None:
    split, named = carry(
        REVOICED,
        ReassignTurns(turns=[2], target="coulisses:1"),
        AssignSpeaker(speaker="coulisses:1", name="Léa"),
    )
    assert split.copy_request == ReassignTurns(turns=[2], target="coulisses:1")
    assert split.anchor == (6.0, 8.0)
    assert named.copy_request == AssignSpeaker(speaker="coulisses:1", name="Léa")


def test_lines_cut_otherwise_are_found_by_time() -> None:
    recut = transcript(
        ("X", "Bonjour", 0.0, 1.0),
        ("X", "Kathy", 1.0, 2.0),
        ("Y", "ça va", 3.0, 5.0),
        ("X", "encore moi salut", 6.0, 10.5),
    )
    first, last = carry(
        recut,
        ReassignTurns(turns=[0], target="B"),
        ReassignTurns(turns=[2], target="B"),
    )
    assert first.copy_request == ReassignTurns(turns=[0, 1], target="Y")
    # The new line runs from 6 to 10.5: less than half of it is the old line.
    assert not last.applied
    assert last.reason == "ces répliques ne se retrouvent pas dans la nouvelle version"


def test_a_text_correction_needs_the_same_original_text() -> None:
    [kept] = carry(REVOICED, EditText(turn=1, text="ça va bien"))
    assert kept.copy_request == EditText(turn=1, text="ça va bien")
    assert kept.anchor == (3.0, 5.0)

    retranscribed = transcript(
        ("A", "Bonjour Cathy", 0.0, 2.0),
        ("B", "ça va", 3.0, 5.0),
        ("A", "encore moi", 6.0, 8.0),
        ("C", "salut", 9.0, 10.0),
    )
    [changed] = carry(retranscribed, EditText(turn=0, text="Bonjour Kathy !"))
    assert not changed.applied
    assert changed.reason == "cette réplique a changé dans la nouvelle version"
    assert changed.description == "correction 1"


def test_only_the_latest_name_and_text_are_carried() -> None:
    results = carry(
        REVOICED,
        AssignSpeaker(speaker="A", name="Marie"),
        EditText(turn=1, text="ça va ?"),
        AssignSpeaker(speaker="A", name="Maria"),
        EditText(turn=1, text="ça va bien"),
    )
    assert [r.edit_id for r in results] == [3, 4]


def test_a_chapter_cut_goes_to_the_line_starting_within_two_seconds() -> None:
    shifted = transcript(
        ("A", "Bonjour Kathy", 0.0, 2.0),
        ("B", "ça va", 3.0, 5.0),
        ("A", "encore moi", 7.5, 8.0),
        ("C", "salut", 9.0, 10.0),
    )
    cut, removed = carry(shifted, SetPhase(turn=2, title="La scène"), RemovePhase(turn=3))
    assert cut.copy_request == SetPhase(turn=2, title="La scène")
    assert removed.copy_request == RemovePhase(turn=3)

    late = transcript(
        ("A", "Bonjour Kathy", 0.0, 2.0),
        ("B", "ça va encore moi", 3.0, 8.5),
        ("C", "salut", 9.0, 10.0),
    )
    [missed] = carry(late, SetPhase(turn=2))
    assert not missed.applied
    assert missed.reason is not None and "à deux secondes près" in missed.reason


def test_a_voice_fused_into_another_persons_does_not_take_it_over() -> None:
    # Léa's voice (C) was told to be Marie's (A); the new version put it inside Paul's (Y):
    # merging Y into Marie's would move all of Paul's lines.
    [merge] = carry(REVOICED, MergeSpeakers(source="C", target="A"))
    assert not merge.applied
    assert merge.reason == "dans la nouvelle version, sa voix est réunie avec celle de Paul"


def test_voices_the_user_made_one_own_their_new_voice_together() -> None:
    merge, named = carry(
        REVOICED, MergeSpeakers(source="C", target="B"), AssignSpeaker(speaker="B", name="Paul")
    )
    assert merge.applied and merge.copy_request is None
    assert named.copy_request == AssignSpeaker(speaker="Y", name="Paul")


def test_lines_found_only_in_part_are_carried_and_said_to_be() -> None:
    gone = transcript(
        ("X", "Bonjour Kathy", 0.0, 2.0),
        ("Y", "ça va", 3.0, 5.0),
        ("X", "salut", 9.0, 10.0),
    )
    [result] = carry(gone, ReassignTurns(turns=[0, 2], target="B"))
    assert result.applied and result.partial
    assert result.copy_request == ReassignTurns(turns=[0], target="Y")
    assert result.reason == (
        "reportée en partie : 1 réplique sur 2 retrouvée dans la nouvelle version "
        "(manquent celles de 0:06)"
    )
