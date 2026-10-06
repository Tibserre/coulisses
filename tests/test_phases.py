"""Chapters: the model's answer put back on real lines, the user's changes to them, and
their place in the summaries (spec §7.5, ADR 0024). The model is a fake."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coulisses_app import corrections
from coulisses_app.corrections import RemovePhase, SetPhase, _replay
from coulisses_app.paths import DataDir
from coulisses_app.phases import (
    DetectedPhase,
    PhaseAnswerError,
    PhaseDetection,
    parse_time,
    snap,
)
from coulisses_app.prompting import assembly
from coulisses_app.prompting.generate import PHASES_REF, _sections, generate

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
