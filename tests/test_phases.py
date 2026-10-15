"""Chapters: the model's answer put back on real lines, the user's changes to them, and
their place in the summaries (spec §7.5, ADR 0024). The model is a fake."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coulisses_app import corrections
from coulisses_app.corrections import RemovePhase, SetPhase, _replay
from coulisses_app.marks import Marker, TimedNote
from coulisses_app.paths import DataDir
from coulisses_app.phases import (
    DetectedPhase,
    PhaseAnswerError,
    PhaseDetection,
    drop_before,
    join_parts,
    parse_time,
    snap,
)
from coulisses_app.prompting import assembly
from coulisses_app.prompting.generate import PHASES_REF, _sections, _sections_by_time, generate

from .conftest import FakeModel
from .test_corrections import PEOPLE, TRANSCRIPT, journal
from .test_generation import client, imported, run_all  # noqa: F401  (fixture)

# TRANSCRIPT's lines start at 0:00, 0:02, 0:05 and 0:06.
LINES = [(0, 0.0), (1, 2.0), (2, 5.0), (3, 6.0)]


def answer(*chapters: tuple[str, str, str]) -> str:
    return json.dumps({"chapitres": [{"debut": d, "type": t, "titre": n} for d, t, n in chapters]})


# -- the model's answer -------------------------------------------------------------------


def test_times_are_read_as_written_in_the_transcript() -> None:
    assert parse_time("12:34") == 754
    assert parse_time("1:02:03") == 3723
    assert parse_time("[0:05]") == 5
    assert parse_time("12:75") is None
    assert parse_time("vers la fin") is None


def test_each_chapter_starts_on_the_line_whose_time_it_gives() -> None:
    found = snap([answer(("0:00", "discussion", "Accueil"), ("0:05", "scene", "Le marché"))], LINES)
    assert [(p.turn, p.kind, p.title) for p in found.phases] == [
        (0, "discussion", "Accueil"),
        (2, "scene", "Le marché"),
    ]
    assert found.adjustments == []


def test_a_time_that_is_no_lines_goes_to_the_nearest_line_and_is_said() -> None:
    found = snap([answer(("0:00", "autre", "Début"), ("0:04", "scene", "Jeu"))], LINES)
    assert [p.turn for p in found.phases] == [0, 2]
    assert found.phases[0].kind == "other"
    assert "aucune réplique à 0:04" in found.adjustments[0]


def test_what_cannot_be_used_is_left_out_and_said_never_silently() -> None:
    found = snap(
        [
            answer(
                ("0:02", "discussion", "Retours"),
                ("plus tard", "scene", "Illisible"),
                ("0:02", "scene", "Doublon"),
                ("0:06", "chant", "Inconnu"),
            )
        ],
        LINES,
    )
    # The first chapter is put back on the first line, as the model was asked.
    assert [(p.turn, p.title) for p in found.phases] == [(0, "Retours"), (3, "Inconnu")]
    said = " ".join(found.adjustments)
    assert "illisible" in said and "même réplique" in said and "inconnu" in said
    assert "première réplique" in said


def test_an_answer_with_no_usable_chapter_is_a_failure() -> None:
    with pytest.raises(PhaseAnswerError):
        snap(["pas du JSON"], LINES)
    with pytest.raises(PhaseAnswerError):
        snap([answer()], LINES)


def test_the_answers_of_several_parts_are_put_together() -> None:
    found = snap([answer(("0:00", "scene", "A")), answer(("0:05", "discussion", "B"))], LINES)
    assert [p.turn for p in found.phases] == [0, 2]


# -- the user's changes -------------------------------------------------------------------

DETECTED = PhaseDetection(
    phases=[
        DetectedPhase(turn=0, kind="discussion", title="Accueil"),
        DetectedPhase(turn=2, kind="scene", title="Le marché"),
    ]
)


def phases_of(*requests: object, reverted: tuple[int, ...] = ()) -> list[tuple[object, ...]]:
    v = _replay(
        TRANSCRIPT,
        "attribute-a",
        journal(*requests, reverted=reverted),
        PEOPLE,
        {},
        detection=DETECTED,
        detection_run_id="segment_phases-a",
    )
    return [(p.turn, p.end_turn, p.kind, p.title, p.edited) for p in v.phases]


def test_the_detected_chapters_cover_the_session() -> None:
    v = _replay(TRANSCRIPT, "attribute-a", [], PEOPLE, {}, detection=DETECTED)
    assert [(p.turn, p.end_turn, p.start) for p in v.phases] == [(0, 2, 0.0), (2, 4, 5.0)]
    assert v.phases[1].end == pytest.approx(6.4)  # the measured end of its last line


def test_a_new_chapter_takes_the_kind_of_the_one_it_cuts_and_no_title() -> None:
    assert phases_of(SetPhase(turn=3)) == [
        (0, 2, "discussion", "Accueil", False),
        (2, 3, "scene", "Le marché", False),
        (3, 4, "scene", "", True),
    ]


def test_a_chapter_is_renamed_and_changes_kind() -> None:
    assert phases_of(SetPhase(turn=2, title="Le bowling"), SetPhase(turn=2, phase_kind="other"))[
        1
    ] == (2, 4, "other", "Le bowling", True)


def test_removing_a_cut_joins_the_chapter_before_and_undoing_brings_it_back() -> None:
    assert phases_of(RemovePhase(turn=2)) == [(0, 4, "discussion", "Accueil", False)]
    assert phases_of(RemovePhase(turn=2), reverted=(1,))[1][:4] == (2, 4, "scene", "Le marché")


def test_without_detection_the_user_can_still_cut_chapters() -> None:
    v = _replay(TRANSCRIPT, "attribute-a", journal(SetPhase(turn=1)), PEOPLE, {})
    assert [(p.turn, p.kind) for p in v.phases] == [(1, "discussion")]


def test_chapter_changes_are_described_for_the_history() -> None:
    v = _replay(
        TRANSCRIPT,
        "attribute-a",
        journal(SetPhase(turn=3), SetPhase(turn=2, title="Bowling", phase_kind="scene")),
        PEOPLE,
        {},
        detection=DETECTED,
    )
    assert [e.description for e in v.edits] == [
        "Nouveau chapitre à 0:06",
        "Chapitre à 0:05 : « Bowling », jeu",
    ]
    assert all(e.turn is None for e in v.edits)  # never mistaken for a text correction


# -- in the transcript sent to the model -------------------------------------------------


def test_chapters_head_their_lines_in_the_transcript_sent() -> None:
    v = _replay(TRANSCRIPT, "attribute-a", [], PEOPLE, {}, detection=DETECTED)
    lines = assembly.transcript_lines(v)
    texts = [line.text for line in lines]
    heading = texts.index("[0:05] ── Chapitre « Le marché » (jeu) ──")
    assert texts[heading + 1].startswith("[0:05] ")
    assert [line.phase_heading for line in lines].count(True) == 2
    assert not any(line.phase_heading for line in assembly.transcript_lines(v, with_phases=False))


def test_a_long_session_is_cut_between_chapters_when_they_fit() -> None:
    def line(start: float, chapter: bool = False) -> assembly.Line:
        return assembly.Line(start, "x" * 18, chapter)  # 11 tokens with its line break

    lines = [line(0, True), line(1), line(2, True), line(3), line(4), line(5, True), line(6)]
    sections = _sections(lines, budget_tokens=35, chars_per_token=1.8)
    # Chapters of 2, 3 and 2 lines: the first two do not fit together, the last two do.
    assert [[x.start for x in s] for s in sections] == [[0, 1], [2, 3, 4], [5, 6]]


# -- the service ---------------------------------------------------------------------------


def test_after_processing_the_chapters_are_detected_then_read_by_the_summary(
    client: TestClient,  # noqa: F811
    data: DataDir,
    recording: Path,
    fake_model: FakeModel,
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    client.post(f"/api/seances/{session_id}/resumes", json={"action_ref": "resume-impro"})
    run_all(data, fake_model)
    view = client.get(f"/api/seances/{session_id}/transcript").json()
    assert [(p["turn"], p["kind"], p["title"]) for p in view["phases"]] == [
        (0, "discussion", "Essai")
    ]
    status = client.get(f"/api/seances/{session_id}/chapitres").json()
    assert status["state"] == "done" and status["model"]
    detection_messages = fake_model.calls[0][1]
    assert assembly.FRENCH_INSTRUCTION in detection_messages[0]["content"]  # P4
    assert "── Chapitre" not in detection_messages[1]["content"]
    summary_messages = fake_model.calls[-1][1]
    assert "── Chapitre « Essai » (discussion) ──" in summary_messages[1]["content"]
    folder = data.run_dir(session_id, view["phases_run_id"])
    assert json.loads((folder / "output.json").read_text())["phases"][0]["title"] == "Essai"
    assert (folder / "calls/01-response.json").is_file()


def test_changing_a_chapter_makes_the_summary_stale(
    client: TestClient,  # noqa: F811
    data: DataDir,
    recording: Path,
    fake_model: FakeModel,
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    client.post(f"/api/seances/{session_id}/resumes", json={"action_ref": "resume-impro"})
    run_all(data, fake_model)
    url = f"/api/seances/{session_id}"
    assert not client.get(f"{url}/resumes").json()["generations"][0]["stale"]
    response = client.post(
        f"{url}/corrections", json={"kind": "set_phase", "turn": 0, "phase_kind": "scene"}
    )
    assert response.status_code == 201, response.text
    assert response.json()["phases"][0]["kind"] == "scene"
    assert client.get(f"{url}/resumes").json()["generations"][0]["stale"]


def test_detecting_again_keeps_the_users_changes_and_makes_the_summary_stale(
    client: TestClient,  # noqa: F811
    data: DataDir,
    recording: Path,
    fake_model: FakeModel,
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    client.post(f"/api/seances/{session_id}/resumes", json={"action_ref": "resume-impro"})
    run_all(data, fake_model)
    url = f"/api/seances/{session_id}"
    client.post(f"{url}/corrections", json={"kind": "set_phase", "turn": 0, "title": "Mon titre"})
    fake_model.phases_answer = answer(("0:00", "scene", "Autre détection"))
    assert client.post(f"{url}/chapitres").json()["state"] == "queued"
    run_all(data, fake_model)
    view = client.get(f"{url}/transcript").json()
    assert [(p["kind"], p["title"]) for p in view["phases"]] == [("scene", "Mon titre")]
    assert client.get(f"{url}/resumes").json()["generations"][0]["stale"]


def test_a_detection_that_fails_says_why_and_the_summary_is_made_without_chapters(
    client: TestClient,  # noqa: F811
    data: DataDir,
    recording: Path,
    fake_model: FakeModel,
) -> None:
    fake_model.phases_answer = "pas du JSON"
    session_id = imported(client, recording)
    run_all(data, fake_model)
    client.post(f"/api/seances/{session_id}/resumes", json={"action_ref": "resume-impro"})
    run_all(data, fake_model)
    status = client.get(f"/api/seances/{session_id}/chapitres").json()
    assert status["state"] == "failed"
    assert "chapitres lisibles" in status["error"]
    assert client.get(f"/api/seances/{session_id}/transcript").json()["phases"] == []
    listed = client.get(f"/api/seances/{session_id}/resumes").json()
    assert [g["action_ref"] for g in listed["generations"]] == ["resume-impro"]
    assert listed["pending"] == []  # the chapters' failure is shown with the transcript


@pytest.mark.parametrize(
    ("request_", "said"),
    [
        ({"kind": "set_phase", "turn": 0}, "commence déjà"),
        ({"kind": "set_phase", "turn": 0, "title": "Essai"}, "déjà ainsi"),
        ({"kind": "remove_phase", "turn": 0}, "ouvre la séance"),
        ({"kind": "remove_phase", "turn": 99}, "Aucun chapitre"),
        ({"kind": "set_phase", "turn": 99}, "introuvable"),
    ],
)
def test_a_chapter_change_that_cannot_apply_says_why(
    client: TestClient,  # noqa: F811
    data: DataDir,
    recording: Path,
    fake_model: FakeModel,
    request_: dict[str, object],
    said: str,
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    response = client.post(f"/api/seances/{session_id}/corrections", json=request_)
    assert response.status_code == 422
    assert said in response.json()["detail"]


def test_unreadable_chapters_are_reported_not_hidden(
    client: TestClient,  # noqa: F811
    data: DataDir,
    recording: Path,
    fake_model: FakeModel,
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    view = corrections.build_view(data, session_id)
    assert view is not None and view.phases_run_id is not None
    (data.run_dir(session_id, view.phases_run_id) / "output.json").write_text("abîmé")
    broken = client.get(f"/api/seances/{session_id}/transcript").json()
    assert broken["phases"] == [] and "illisibles" in broken["phases_problem"]


def test_the_detection_is_asked_for_json_with_its_own_reserve(
    client: TestClient,  # noqa: F811
    data: DataDir,
    recording: Path,
    fake_model: FakeModel,
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    prov = generate(data, session_id, PHASES_REF, "modele-essai", fake_model)
    assert prov.status == "succeeded" and prov.stage == "segment_phases"
    assert fake_model.formats[-1] is not None
    assert fake_model.calls[-1][2]["num_predict"] == assembly.settings().phases_reserve


def test_a_title_too_long_is_shortened_and_said() -> None:
    found = snap([answer(("0:00", "scene", "très " * 40))], LINES)
    assert len(found.phases[0].title) == 120
    assert "raccourci" in found.adjustments[0]


def test_a_session_with_nothing_said_gets_one_other_chapter() -> None:
    found = snap([answer(("0:00", "autre", "Essais de micro, rien d'autre"))], LINES)
    assert [(p.turn, p.kind) for p in found.phases] == [(0, "other")]


def test_a_chapter_cut_by_hand_alone_can_be_removed() -> None:
    v = _replay(
        TRANSCRIPT,
        "attribute-a",
        journal(SetPhase(turn=2), RemovePhase(turn=2)),
        PEOPLE,
        {},
    )
    assert v.phases == []


def test_the_chapters_are_read_in_sections_of_the_same_length() -> None:
    # 70 minutes, slices of 25 at most: three of about 23 minutes.
    lines = [assembly.Line(float(m * 60), f"[{m}:00] Marie : oui") for m in range(71)]
    lines.insert(30, assembly.Line(None, "[--:--] Marie : sans heure"))
    slices = _sections_by_time(lines, 25)
    assert len(slices) == 3
    assert [s[0].start for s in slices] == [0.0, 24 * 60.0, 47 * 60.0]
    assert sum(len(s) for s in slices) == len(lines)  # nothing lost
    assert slices[1][6].start is None  # a line without a time stays where it was
    assert len(_sections_by_time(lines[:20], 25)) == 1


def test_the_model_is_told_how_many_chapters_to_aim_at_for_the_length() -> None:
    assert "environ 23 minutes : vise entre 2 et 6 chapitres" in assembly.phases_scale(23, (4, 10))
    assert "environ 1 minute : vise entre 1 et 2 chapitres" in assembly.phases_scale(0.4, (4, 10))
    assert "entre 9 et 23" in assembly.phases_prompt("Découpe.", 92, (4, 10))
    assert "entre 4 et 8" in assembly.phases_scale(15, (2, 4))


def test_a_part_that_goes_on_with_the_previous_chapter_is_joined_to_it() -> None:
    first = answer(("0:00", "discussion", "Accueil"), ("0:05", "scene", "Le marché"))
    goes_on = answer(("0:06", "scene", " le  Marché"), ("0:08", "discussion", "Retours"))
    found, joined = join_parts([first, goes_on])
    assert joined == [True]
    assert [p.title for p in snap(found, LINES).phases] == ["Accueil", "Le marché", "Retours"]
    other = answer(("0:06", "scene", "La gare"))
    assert join_parts([first, other])[1] == [False]
    # A part that is all the previous chapter adds nothing; an unreadable one is passed
    # on as it is, for snap to say why.
    whole = answer(("0:06", "scene", "Le marché"))
    assert json.loads(join_parts([first, whole])[0][1]) == {"chapitres": []}
    assert join_parts([first, "pas du JSON"]) == ([first, "pas du JSON"], [False])
    long_title = "x" * 200
    a, b = answer(("0:00", "scene", long_title)), answer(("0:06", "scene", long_title + "y"))
    assert join_parts([a, b])[1] == [True]  # compared as kept: the first 120 characters


def test_a_long_session_is_detected_in_parts_and_the_cuts_they_force_are_said(
    client: TestClient,  # noqa: F811
    data: DataDir,
    recording: Path,
    fake_model: FakeModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    small = assembly.settings().model_copy(update={"num_ctx": 6000, "phases_reserve": 500})
    monkeypatch.setattr(assembly, "settings", lambda: small)
    long_lines = [
        assembly.Line(float(i * 10), f"[{i // 6}:{i % 6}0] Marie : " + "on reprend " * 30)
        for i in range(60)
    ]
    monkeypatch.setattr(assembly, "transcript_lines", lambda _view, **_: long_lines)
    calls_before = len(fake_model.calls)
    prov = generate(data, session_id, PHASES_REF, "modele-essai", fake_model)
    assert prov.status == "succeeded", prov.error
    assert prov.strategy == "sections"
    assert {c.kind for c in prov.calls} == {"section"}  # no merging call
    assert len(prov.calls) >= 2
    assert all(f is not None for f in fake_model.formats[calls_before:])
    for _, messages, _ in fake_model.calls[calls_before:]:
        assert assembly.FRENCH_INSTRUCTION in messages[0]["content"]  # every part, P4
    folder = data.run_dir(session_id, prov.run_id)
    said = " ".join(json.loads((folder / "output.json").read_text())["adjustments"])
    assert "parties" in said


def test_the_exported_transcript_shows_the_chapters(
    client: TestClient,  # noqa: F811
    data: DataDir,
    recording: Path,
    fake_model: FakeModel,
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    text = client.get(f"/api/seances/{session_id}/export?contenu=transcript").text
    assert "### Chapitre « Essai » (discussion)" in text


def test_chapters_pointing_at_no_line_are_counted_not_hidden() -> None:
    elsewhere = PhaseDetection(
        phases=[*DETECTED.phases, DetectedPhase(turn=99, kind="scene", title="?")]
    )
    v = _replay(TRANSCRIPT, "attribute-a", [], PEOPLE, {}, detection=elsewhere)
    assert len(v.phases) == 2
    assert v.phases_problem is not None and "1 chapitre(s)" in v.phases_problem


# -- markers set while recording (step 6b) -------------------------------------------------


def marker(kind: str, at_s: float, id_: int = 1) -> Marker:
    return Marker(id=id_, kind=kind, at_s=at_s)  # type: ignore[arg-type]


def test_a_marker_takes_the_place_of_the_detected_cut_near_it_and_keeps_its_title() -> None:
    # The detection cut at 0:05 (« Le marché »); the group marked « play » at 0:04.8.
    v = _replay(
        TRANSCRIPT,
        "attribute-a",
        [],
        PEOPLE,
        {},
        detection=DETECTED,
        markers=[marker("scene", 4.8)],
    )
    assert [(p.turn, p.kind, p.title, p.marked) for p in v.phases] == [
        (0, "discussion", "Accueil", False),
        (2, "scene", "Le marché", True),
    ]


def test_a_marker_cuts_where_the_detection_did_not_and_wins_over_its_kind() -> None:
    v = _replay(
        TRANSCRIPT,
        "attribute-a",
        [],
        PEOPLE,
        {},
        detection=DETECTED,
        markers=[marker("scene", 4.8), marker("discussion", 5.9, 2)],
    )
    assert [(p.turn, p.kind, p.marked) for p in v.phases] == [
        (0, "discussion", False),  # the opening chapter is never taken by a marker
        (2, "scene", True),
        (3, "discussion", True),
    ]


def test_key_moments_cut_nothing_and_without_detection_markers_still_cut() -> None:
    v = _replay(
        TRANSCRIPT,
        "attribute-a",
        [],
        PEOPLE,
        {},
        markers=[marker("key_moment", 2.0), marker("scene", 1.9, 2)],
    )
    assert [(p.turn, p.kind, p.title, p.marked) for p in v.phases] == [(1, "scene", "", True)]


def test_the_user_can_still_change_a_chapter_cut_by_a_marker() -> None:
    v = _replay(
        TRANSCRIPT,
        "attribute-a",
        journal(SetPhase(turn=2, title="Le marché")),
        PEOPLE,
        {},
        markers=[marker("scene", 4.8)],
    )
    assert [(p.turn, p.title, p.marked, p.edited) for p in v.phases] == [
        (2, "Le marché", True, True)
    ]


def test_moments_and_notes_are_in_the_transcript_sent_and_markers_for_the_detection() -> None:
    v = _replay(
        TRANSCRIPT,
        "attribute-a",
        [],
        PEOPLE,
        {},
        markers=[marker("key_moment", 2.0), marker("scene", 4.8, 2)],
        timed_notes=[TimedNote(id=1, at_s=5.5, text="Bonne fin de scène")],
    )
    sent = [line.text for line in assembly.transcript_lines(v)]
    assert "[0:02] ★ Moment clé marqué pendant la séance" in sent
    assert "[0:05] ✎ Note prise pendant la séance : Bonne fin de scène" in sent
    assert not any("▸" in line for line in sent)  # the chapter heading says it already
    detection = [line.text for line in assembly.transcript_lines(v, with_phases=False)]
    assert "[0:04] ▸ Marqueur posé pendant la séance : début de jeu" in detection


def test_a_detected_cut_more_than_a_minute_away_from_a_marker_stays() -> None:
    from coulisses_app import corrections

    detected = PhaseDetection(
        phases=[
            DetectedPhase(turn=0, kind="discussion", title="Accueil"),
            DetectedPhase(turn=2, kind="scene", title="Le marché"),
        ]
    )
    far = corrections.MARKER_ABSORBS_S + 1
    v = _replay(
        TRANSCRIPT,
        "attribute-a",
        [],
        PEOPLE,
        {},
        detection=detected,
        markers=[marker("discussion", 5.0 - far)],  # before the session: lands on line 0
    )
    assert [(p.turn, p.title) for p in v.phases] == [(0, "Accueil"), (2, "Le marché")]
    near = _replay(
        TRANSCRIPT,
        "attribute-a",
        [],
        PEOPLE,
        {},
        detection=detected,
        markers=[marker("scene", 4.8)],
    )
    assert near.phases_by_markers == [
        "Marqueur jeu à 0:04 : remplace la coupure détectée à 0:05 (« Le marché »)"
    ]


def test_a_marker_after_the_last_line_cuts_nothing() -> None:
    v = _replay(
        TRANSCRIPT,
        "attribute-a",
        [],
        PEOPLE,
        {},
        detection=DETECTED,
        markers=[marker("scene", 99.0)],
    )
    assert [(p.turn, p.marked) for p in v.phases] == [(0, False), (2, False)]


def test_a_session_longer_than_a_section_is_read_in_parts_that_follow_each_other(
    client: TestClient,  # noqa: F811
    data: DataDir,
    recording: Path,
    fake_model: FakeModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    sliced = assembly.settings().model_copy(update={"phases_section_min": 25})
    monkeypatch.setattr(assembly, "settings", lambda: sliced)
    hour = [assembly.Line(float(m * 60), f"[{m}:00] Marie : on reprend") for m in range(60)]
    monkeypatch.setattr(assembly, "transcript_lines", lambda _view, **_: hour)
    calls_before = len(fake_model.calls)
    prov = generate(data, session_id, PHASES_REF, "modele-essai", fake_model)
    assert prov.status == "succeeded", prov.error
    assert prov.strategy == "sections"  # though the hour fits in the window
    assert len(prov.calls) == 3
    second = fake_model.calls[calls_before + 1][1][0]["content"]
    assert "partie 2" in second and "« Essai » (type `discussion`)" in second
    assert "vise entre" in second
    spec = json.loads((data.run_dir(session_id, prov.run_id) / "spec.json").read_text())
    assert spec["phases_section_min"] == 25  # P7
    folder = data.run_dir(session_id, prov.run_id)
    said = json.loads((folder / "output.json").read_text())["adjustments"]
    # The fake model answers « Essai » each time: each part goes on with it.
    assert sum("continue le chapitre précédent" in a for a in said) == 2


def test_a_chapter_set_in_lines_recalled_from_the_part_before_is_left_out() -> None:
    raw = answer(("19:00", "scene", "Rappelée"), ("20:00", "scene", "B"), ("1:02:03", "x", "C"))
    kept, dropped = drop_before(raw, "20:00")
    assert dropped == 1
    assert [c["titre"] for c in json.loads(kept)["chapitres"]] == ["B", "C"]
    assert drop_before("pas du JSON", "20:00") == ("pas du JSON", 0)
    # A part left with no chapter of its own goes on with the one before.
    assert join_parts([answer(("0:00", "scene", "A")), answer()])[1] == [True]
    # The chapter the part before ended on, set in the recalled lines: the part goes on
    # with it, then cuts where it said.
    before = answer(("0:00", "discussion", "Accueil"), ("15:00", "scene", "Le marché"))
    goes_on = answer(("19:00", "scene", "Le marché"), ("24:00", "discussion", "Retours"))
    kept, _ = drop_before(goes_on, "20:00", ("scene", "Le marché"))
    found, joined = join_parts([before, kept])
    assert joined == [True]
    assert [c["titre"] for c in json.loads(found[1])["chapitres"]] == ["Retours"]


def test_the_chapters_may_have_their_own_window_and_the_summaries_keep_theirs(
    client: TestClient,  # noqa: F811
    data: DataDir,
    recording: Path,
    fake_model: FakeModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    own = assembly.settings().model_copy(update={"phases_num_ctx": 16384})
    monkeypatch.setattr(assembly, "settings", lambda: own)
    calls_before = len(fake_model.calls)
    generate(data, session_id, PHASES_REF, "modele-essai", fake_model)
    generate(data, session_id, "resume-impro", "modele-essai", fake_model)
    windows = [options["num_ctx"] for _, _, options in fake_model.calls[calls_before:]]
    assert windows == [16384, own.num_ctx]


def test_each_part_can_be_sent_after_the_end_of_the_one_before_which_it_does_not_cut(
    client: TestClient,  # noqa: F811
    data: DataDir,
    recording: Path,
    fake_model: FakeModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    recalling = assembly.settings().model_copy(
        update={"phases_section_min": 25, "phases_overlap_min": 3}
    )
    monkeypatch.setattr(assembly, "settings", lambda: recalling)
    hour = [assembly.Line(float(m * 60), f"[{m}:00] Marie : ligne {m}") for m in range(60)]
    monkeypatch.setattr(assembly, "transcript_lines", lambda _view, **_: hour)
    calls_before = len(fake_model.calls)
    prov = generate(data, session_id, PHASES_REF, "modele-essai", fake_model)
    assert prov.status == "succeeded", prov.error
    second = fake_model.calls[calls_before + 1][1]
    sent = second[1]["content"]
    # Parts start at 0, 20 and 40 minutes: the second recalls minutes 17 to 19.
    assert "[17:00] Marie : ligne 17" in sent and "[16:00]" not in sent
    assert (
        sent.index("ligne 19")
        < sent.index("Début de la partie à découper")
        < sent.index("ligne 20")
    )
    assert "rappelées" in second[0]["content"]
    folder = data.run_dir(session_id, prov.run_id)
    said = json.loads((folder / "output.json").read_text())["adjustments"]
    # The fake model sets « Essai » at 0:00 each time: in the recalled lines, left out.
    assert any("2 chapitre(s) placé(s) dans les répliques rappelées" in a for a in said)
    assert json.loads((folder / "spec.json").read_text())["phases_overlap_min"] == 3
