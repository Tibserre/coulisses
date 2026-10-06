"""The corrected view, rebuilt from a run and the journal of corrections (pure logic)."""

from __future__ import annotations

from coulisses.api import AttributedTranscript, AttributedWord, Turn, UntranscribedSpan

from coulisses_app.corrections import (
    AssignSpeaker,
    EditText,
    MergeSpeakers,
    ReassignTurns,
    Word,
    _apply_text,
    _Journal,
    _replay,
)
from coulisses_app.spaces import Person


def w(text: str, start: float | None, speaker: str, asr: float | None = None) -> AttributedWord:
    return AttributedWord(
        text=text,
        start=start,
        end=None if start is None else start + 0.4,
        asr_confidence=asr,
        alignment_score=0.05,  # low on most right words: never what the review shows
        speakers=(speaker,),
        speaker=speaker,
    )


TRANSCRIPT = AttributedTranscript(
    reference_source="ref",
    language="fr",
    words=(
        w("Bonjour", 0.0, "7"),
        w("Kathy", 0.5, "7", asr=0.12),
        w("ça", 2.0, "2"),
        w("va", 2.5, "2"),
        w("encore", 5.0, "7"),
        w("moi", 6.0, "4"),
    ),
    turns=(
        Turn(speaker="7", first_word=0, end_word=2, start=0.0, end=0.9),
        Turn(speaker="2", first_word=2, end_word=4, start=2.0, end=2.9),
        Turn(speaker="7", first_word=4, end_word=5, start=5.0, end=5.4),
        Turn(speaker="4", first_word=5, end_word=6, start=6.0, end=6.4),
    ),
    speakers=("2", "4", "7"),
    untranscribed=(UntranscribedSpan(start=3.0, end=4.5, reason="loop"),),
)

MARIE = Person(
    id=1, space_id=1, kind="member", name="Marie", role="coach", color_slot=3, archived=False
)
PEOPLE = {1: MARIE}


def journal(
    *requests: object, reverted: tuple[int, ...] = (), run: str = "attribute-a"
) -> list[_Journal]:
    entries: list[_Journal] = []
    for i, request in enumerate(requests, start=1):
        entries.append(
            _Journal(
                id=i,
                run_id=run,
                kind=request.kind,  # type: ignore[attr-defined]
                payload=request.model_dump_json(),  # type: ignore[attr-defined]
                reverts=None,
                created_at="2026-10-05T10:00:00Z",
            )
        )
    for n, target in enumerate(reverted, start=len(entries) + 1):
        entries.append(
            _Journal(id=n, run_id=run, kind="revert", payload="{}", reverts=target, created_at="x")
        )
    return entries


def view(*requests: object, reverted: tuple[int, ...] = (), variants: dict[str, str] | None = None):
    return _replay(
        TRANSCRIPT, "attribute-a", journal(*requests, reverted=reverted), PEOPLE, variants or {}
    )


def test_without_corrections_voices_are_numbered_by_first_appearance() -> None:
    v = view()
    assert [(s.label, s.name, s.named) for s in v.speakers] == [
        ("7", "Locuteur 1", False),
        ("2", "Locuteur 2", False),
        ("4", "Locuteur 3", False),
    ]
    assert all(s.color_slot is None for s in v.speakers)  # unnamed: grey, never a colour
    assert v.timed_share == 1.0


def test_naming_a_voice_gives_it_the_person_and_her_colour() -> None:
    v = view(AssignSpeaker(speaker="2", person_id=1))
    second = next(s for s in v.speakers if s.label == "2")
    assert (second.name, second.person_id, second.color_slot) == ("Marie", 1, 3)
    # Others keep their number: naming one voice never renumbers the rest.
    assert [s.name for s in v.speakers if s.label != "2"] == ["Locuteur 1", "Locuteur 3"]
    assert v.edits[0].description == "Locuteur 2 : Marie"


def test_a_character_is_played_by_a_person() -> None:
    v = view(AssignSpeaker(speaker="4", person_id=1, character="Le marchand"))
    voice = next(s for s in v.speakers if s.label == "4")
    assert (voice.name, voice.played_by, voice.color_slot) == ("Le marchand", "Marie", 3)


def test_a_free_name_is_named_and_coloured() -> None:
    v = view(AssignSpeaker(speaker="7", name="Le régisseur"))
    voice = v.speakers[0]
    assert voice.named and voice.name == "Le régisseur" and voice.color_slot is not None


def test_merging_moves_every_line_and_drops_the_merged_voice() -> None:
    v = view(MergeSpeakers(source="4", target="7"))
    assert [t.speaker for t in v.turns] == ["7", "2", "7", "7"]
    assert {s.label for s in v.speakers} == {"7", "2"}
    assert next(s for s in v.speakers if s.label == "7").turns == 3


def test_splitting_gives_lines_to_a_new_voice() -> None:
    v = view(ReassignTurns(turns=[2], target="coulisses:1"))
    assert v.turns[2].speaker == "coulisses:1"
    new = next(s for s in v.speakers if s.label == "coulisses:1")
    assert new.name == "Nouvelle voix 1" and not new.named


def test_words_carry_the_transcription_models_doubt_not_the_alignment_score() -> None:
    words = view().turns[0].words
    assert [x.asr_confidence for x in words] == [None, 0.12]


def test_an_output_from_before_engine_1_4_reads_with_no_doubt_shown() -> None:
    old = TRANSCRIPT.model_dump(mode="json", exclude={"words"})
    old["words"] = [  # engine v1.3.0: only the alignment score, under its former name
        {
            "text": "Bonjour",
            "start": 0.0,
            "end": 0.4,
            "confidence": 0.02,
            "speakers": ["7"],
            "speaker": "7",
        },
        {
            "text": "Kathy",
            "start": 0.5,
            "end": 0.9,
            "confidence": 0.01,
            "speakers": ["7"],
            "speaker": "7",
        },
        *old_tail(),
    ]
    transcript = AttributedTranscript.model_validate(old)
    v = _replay(transcript, "attribute-a", [], PEOPLE, {})
    assert all(x.asr_confidence is None for t in v.turns for x in t.words)


def old_tail() -> list[dict[str, object]]:
    return [
        x.model_dump(mode="json", exclude={"asr_confidence", "alignment_score"})
        for x in TRANSCRIPT.words[2:]
    ]


def test_a_corrected_word_keeps_its_measured_time() -> None:
    v = view(EditText(turn=0, text="Bonjour Cathy"))
    words = v.turns[0].words
    assert [x.text for x in words] == ["Bonjour", "Cathy"]
    assert (words[1].start, words[1].corrected, words[1].added) == (0.5, True, False)
    assert words[1].asr_confidence is None  # checked by hand: the model's doubt is gone
    assert words[0].corrected is False


def test_added_words_have_no_time_of_their_own() -> None:
    words = view(EditText(turn=1, text="ça va très bien")).turns[1].words
    assert [(x.text, x.start, x.added) for x in words] == [
        ("ça", 2.0, False),
        ("va", 2.5, False),
        ("très", None, True),
        ("bien", None, True),
    ]
    assert view(EditText(turn=1, text="ça va très bien")).timed_share < 1.0


def test_a_shorter_stretch_keeps_its_measured_end() -> None:
    original = [
        Word(text="a", start=1.0, end=1.2, asr_confidence=None, uncertain=False),
        Word(text="b", start=1.3, end=1.5, asr_confidence=None, uncertain=False),
        Word(text="c", start=1.6, end=2.0, asr_confidence=None, uncertain=False),
    ]
    out = _apply_text(original, "x")
    assert [(x.text, x.start, x.end) for x in out] == [("x", 1.0, 2.0)]


def test_an_undone_correction_no_longer_applies_but_stays_listed() -> None:
    v = view(AssignSpeaker(speaker="2", person_id=1), reverted=(1,))
    assert next(s for s in v.speakers if s.label == "2").name == "Locuteur 2"
    assert [(e.id, e.reverted) for e in v.edits] == [(1, True)]


def test_the_latest_naming_of_a_voice_wins() -> None:
    v = view(AssignSpeaker(speaker="2", person_id=1), AssignSpeaker(speaker="2", name="Paul"))
    assert next(s for s in v.speakers if s.label == "2").name == "Paul"


def test_corrections_of_another_run_are_counted_not_applied() -> None:
    entries = journal(AssignSpeaker(speaker="2", person_id=1), run="attribute-old")
    v = _replay(TRANSCRIPT, "attribute-a", entries, PEOPLE, {})
    assert v.other_run_edits == 1
    assert next(s for s in v.speakers if s.label == "2").name == "Locuteur 2"


def test_a_known_wrong_spelling_suggests_the_glossary_term() -> None:
    v = view(variants={"kathy": "Cathy"})
    assert v.turns[0].words[1].suggestion == "Cathy"
    assert v.turns[0].words[0].suggestion is None


def test_untranscribed_stretches_are_kept() -> None:
    assert [(u.start, u.end) for u in view().untranscribed] == [(3.0, 4.5)]
