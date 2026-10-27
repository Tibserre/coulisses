"""Running a stage again (step 7): a new version, complete or not at all, the corrections
carried over, the former version kept and viewable, with the engine's fake engines."""

from __future__ import annotations

from pathlib import Path

import pytest
from coulisses.api import read_provenance

from coulisses_app import corrections, jobs, sessions, versions
from coulisses_app.api import create_app
from coulisses_app.paths import DataDir
from coulisses_app.processing import Processor
from coulisses_app.spaces import SpaceError
from coulisses_app.status import stage_views
from coulisses_app.storage.db import connect, now_iso

from .conftest import FAKE_CHAIN, local_client
from .test_processing import REFUSED_DIARIZATION, runs


def claim(data: DataDir) -> jobs.Job:
    """The next chain job; the chapters queued after each processing are left aside (they
    would call the model)."""
    conn = connect(data)
    try:
        with conn:
            conn.execute("UPDATE job SET state = 'done' WHERE kind = 'generation'")
        job = jobs.claim_next(conn)
    finally:
        conn.close()
    assert job is not None and job.kind == "chain"
    return job


def processed(data: DataDir, recording: Path, attendees: int = 2) -> str:
    with recording.open("rb") as f:
        session_id = sessions.import_recording(
            data, f, recording.name, unnamed_attendees=attendees, recorded_at=None, profile="essai"
        )
    assert Processor(data, FAKE_CHAIN).run_job(claim(data)).error is None
    return session_id


def shown(data: DataDir, session_id: str) -> dict[str, str]:
    conn = connect(data)
    try:
        return {
            r["stage"]: r["run_id"]
            for r in conn.execute("SELECT * FROM active_run WHERE session_id = ?", (session_id,))
        }
    finally:
        conn.close()


def view(data: DataDir, session_id: str) -> corrections.CorrectedView:
    found = corrections.build_view(data, session_id)
    assert found is not None
    return found


def correct(data: DataDir, session_id: str) -> None:
    """Name the voice and correct the line, as the user would."""
    corrections.add(data, session_id, {"kind": "assign_speaker", "speaker": "S1", "name": "Marie"})
    corrections.add(data, session_id, {"kind": "edit_text", "turn": 0, "text": "bonjour Kathy"})


def test_the_transcription_run_again_gives_a_new_version_with_the_corrections(
    data: DataDir, recording: Path
) -> None:
    session_id = processed(data, recording)
    first = shown(data, session_id)
    correct(data, session_id)

    versions.request_rerun(data, session_id, "transcribe", attendees=None, profile="essai")
    # Queued, then running: the version shown stays the same until the new one is complete.
    assert shown(data, session_id) == first
    assert Processor(data, FAKE_CHAIN).run_job(claim(data)).error is None

    now = shown(data, session_id)
    assert now["diarize"] == first["diarize"]  # reused as it was
    assert now["transcribe"] != first["transcribe"]
    assert now["attribute"] != first["attribute"]
    v = view(data, session_id)
    assert v.run_id == now["attribute"]
    assert v.speakers[0].name == "Marie"
    assert [w.text for w in v.turns[0].words] == ["bonjour", "Kathy"]
    assert v.carryover is not None
    assert (v.carryover.from_run_id, v.carryover.carried) == (first["attribute"], 2)
    assert v.carryover.not_carried == []
    # The copies are corrections of the new version: undone like any other.
    assert [e.kind for e in v.edits] == ["assign_speaker", "edit_text"]

    listed = versions.list_versions(data, session_id).versions
    assert [(x.number, x.origin, x.shown) for x in listed] == [
        (2, "transcribe", True),
        (1, "first", False),
    ]
    assert (listed[0].carried, listed[0].not_carried) == (2, 0)
    # The former version keeps its own corrections, untouched.
    former = corrections.build_view(data, session_id, run_id=first["attribute"])
    assert former is not None and former.speakers[0].name == "Marie"
    assert len(former.edits) == 2


def test_the_voices_run_again_with_another_minimum(data: DataDir, recording: Path) -> None:
    session_id = processed(data, recording, attendees=2)
    first = shown(data, session_id)
    versions.request_rerun(data, session_id, "diarize", attendees=3, profile="essai")
    assert Processor(data, FAKE_CHAIN).run_job(claim(data)).error is None

    now = shown(data, session_id)
    assert (now["transcribe"], now["align"]) == (first["transcribe"], first["align"])
    assert now["diarize"] != first["diarize"]
    prov = read_provenance(data.run_dir(session_id, now["diarize"]))
    assert prov is not None and prov.inputs["min_speakers"] == 3
    listed = versions.list_versions(data, session_id)
    assert [x.min_voices for x in listed.versions] == [3, 2]
    assert listed.rerun.min_voices == 3
    # Who was present is not changed by it.
    session = sessions.get_session(data, session_id)
    assert session is not None and session.unnamed_attendees == 2


def test_everything_runs_again_with_the_glossary_and_minimum_of_today(
    data: DataDir, recording: Path
) -> None:
    session_id = processed(data, recording, attendees=2)
    first = shown(data, session_id)
    correct(data, session_id)
    space = sessions.get_session(data, session_id)
    assert space is not None
    conn = connect(data)
    try:
        with conn:
            conn.execute(
                "INSERT INTO glossary_entry (space_id, term, variants, created_at)"
                " VALUES (?, 'Kathy', '[]', ?)",
                (space.space_id, now_iso()),
            )
    finally:
        conn.close()
    client = local_client(
        create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None)
    )
    answer = client.post(
        f"/api/seances/{session_id}/relancer", json={"etape": "all", "presents": 3}
    )
    assert answer.status_code == 202, answer.text
    conn = connect(data)
    try:
        row = conn.execute("SELECT params FROM job ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        conn.close()
    params = jobs.ChainParams.model_validate_json(row["params"])
    assert params.reuse == {}  # nothing kept
    assert params.glossary == ["Kathy"]
    assert Processor(data, FAKE_CHAIN).run_job(claim(data)).error is None

    now = shown(data, session_id)
    assert all(now[stage] != first[stage] for stage in ("transcribe", "align", "diarize"))
    prov = read_provenance(data.run_dir(session_id, now["diarize"]))
    assert prov is not None and prov.inputs["min_speakers"] == 3
    listed = versions.list_versions(data, session_id).versions
    assert [(x.origin, x.min_voices) for x in listed] == [("all", 3), ("first", 2)]
    assert listed[0].carried is not None  # carried over as for the other reruns

    # Without a minimum given, the shown version's.
    client.post(f"/api/seances/{session_id}/relancer", json={"etape": "all"})
    assert Processor(data, FAKE_CHAIN).run_job(claim(data)).error is None
    assert versions.list_versions(data, session_id).versions[0].min_voices == 3


def test_a_rerun_that_stops_halfway_leaves_the_version_shown(
    data: DataDir, recording: Path
) -> None:
    session_id = processed(data, recording, attendees=1)
    first = shown(data, session_id)
    versions.request_rerun(data, session_id, "diarize", attendees=3, profile="essai")
    result = Processor(data, REFUSED_DIARIZATION).run_job(claim(data))
    assert result.error is not None

    assert shown(data, session_id) == first
    stages = {s.stage: s for s in stage_views(data, FAKE_CHAIN, session_id)}
    assert stages["diarize"].state == "failed"
    assert stages["attribute"].state == "succeeded" and stages["attribute"].stale
    assert not stages["transcribe"].stale  # reused, not made again
    assert view(data, session_id).run_id == first["attribute"]


def test_a_rerun_is_refused_while_another_is_under_way(data: DataDir, recording: Path) -> None:
    session_id = processed(data, recording)
    versions.request_rerun(data, session_id, "transcribe", attendees=None, profile="essai")
    with pytest.raises(SpaceError, match="déjà en cours"):
        versions.request_rerun(data, session_id, "diarize", attendees=2, profile="essai")
    assert versions.list_versions(data, session_id).rerun.possible is False


def test_a_session_never_processed_to_the_end_cannot_be_run_again(
    data: DataDir, recording: Path
) -> None:
    with recording.open("rb") as f:
        session_id = sessions.import_recording(
            data, f, recording.name, unnamed_attendees=1, recorded_at=None, profile="essai"
        )
    with pytest.raises(SpaceError, match="pas encore été traitée"):
        versions.request_rerun(data, session_id, "transcribe", attendees=None, profile="essai")


def test_a_former_version_is_shown_again_with_its_own_corrections_and_chapters(
    data: DataDir, recording: Path
) -> None:
    session_id = processed(data, recording)
    first = shown(data, session_id)
    correct(data, session_id)
    # Chapters detected on the first version (the detection itself is tested elsewhere).
    conn = connect(data)
    try:
        with conn:
            conn.execute(
                "INSERT INTO run (id, session_id, stage, status, producer, created_at)"
                " VALUES ('segment_phases-1', ?, 'segment_phases', 'succeeded', 'app', ?)",
                (session_id, now_iso()),
            )
            conn.execute(
                "INSERT INTO run_upstream VALUES ('segment_phases-1', ?)", (first["attribute"],)
            )
    finally:
        conn.close()
    versions.request_rerun(data, session_id, "transcribe", attendees=None, profile="essai")
    assert Processor(data, FAKE_CHAIN).run_job(claim(data)).error is None
    second = shown(data, session_id)
    corrections.add(data, session_id, {"kind": "assign_speaker", "speaker": "S1", "name": "Léa"})

    versions.show(data, session_id, first["attribute"])
    again = shown(data, session_id)
    assert {k: again[k] for k in first} == first
    assert again["segment_phases"] == "segment_phases-1"
    assert view(data, session_id).speakers[0].name == "Marie"
    # Undone then redone on the former version: the copy on the newer one is not a redo.
    marie = view(data, session_id).edits[0].id
    corrections.undo(data, session_id, marie)
    corrections.redo(data, session_id, marie)
    assert view(data, session_id).speakers[0].name == "Marie"

    versions.show(data, session_id, second["attribute"])
    assert view(data, session_id).speakers[0].name == "Léa"


def test_the_version_shown_does_not_change_under_a_rerun(data: DataDir, recording: Path) -> None:
    session_id = processed(data, recording)
    first = shown(data, session_id)["attribute"]
    versions.request_rerun(data, session_id, "transcribe", attendees=None, profile="essai")
    with pytest.raises(SpaceError, match="en cours"):
        versions.show(data, session_id, first)


def test_completing_a_version_again_after_a_crash_changes_nothing(
    data: DataDir, recording: Path
) -> None:
    session_id = processed(data, recording)
    correct(data, session_id)
    job_id = versions.request_rerun(data, session_id, "transcribe", attendees=None, profile="essai")
    assert Processor(data, FAKE_CHAIN).run_job(claim(data)).error is None
    before = view(data, session_id)
    count = len(runs(data, session_id))

    conn = connect(data)
    try:
        jobs.requeue(conn, job_id)  # as after a crash between the end and « done »
    finally:
        conn.close()
    assert Processor(data, FAKE_CHAIN).run_job(claim(data)).error is None
    after = view(data, session_id)
    assert after.run_id == before.run_id
    assert [e.id for e in after.edits] == [e.id for e in before.edits]
    assert after.carryover == before.carryover
    assert len(runs(data, session_id)) == count


def test_the_service_runs_a_stage_again_and_shows_the_versions(
    data: DataDir, recording: Path
) -> None:
    session_id = processed(data, recording)
    client = local_client(
        create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None)
    )
    first = client.get(f"/api/seances/{session_id}").json()["version"]

    answer = client.post(
        f"/api/seances/{session_id}/relancer", json={"etape": "diarize", "presents": 3}
    )
    assert answer.status_code == 202, answer.text
    assert answer.json()["job_state"] == "queued"
    again = client.post(f"/api/seances/{session_id}/relancer", json={"etape": "transcribe"})
    assert again.status_code == 422
    assert again.json()["detail"] == "Un traitement de cette séance est déjà en cours."

    assert Processor(data, FAKE_CHAIN).run_job(claim(data)).error is None
    listed = client.get(f"/api/seances/{session_id}/versions").json()
    assert [v["origin"] for v in listed["versions"]] == ["diarize", "first"]
    assert (
        client.get(f"/api/seances/{session_id}").json()["version"]
        == listed["versions"][0]["run_id"]
    )

    back = client.post(f"/api/seances/{session_id}/versions/{first}/afficher")
    assert back.status_code == 200
    assert [v["shown"] for v in back.json()["versions"]] == [False, True]
    assert client.post(f"/api/seances/{session_id}/versions/inconnue/afficher").status_code == 404


def test_a_correction_made_while_the_rerun_runs_is_carried_over(
    data: DataDir, recording: Path
) -> None:
    session_id = processed(data, recording)
    versions.request_rerun(data, session_id, "transcribe", attendees=None, profile="essai")
    correct(data, session_id)  # the version shown is still the first one
    assert Processor(data, FAKE_CHAIN).run_job(claim(data)).error is None
    v = view(data, session_id)
    assert v.speakers[0].name == "Marie"
    assert v.carryover is not None and v.carryover.carried == 2


def test_a_correction_meant_for_the_replaced_version_is_refused_not_misplaced(
    data: DataDir, recording: Path
) -> None:
    session_id = processed(data, recording)
    first = shown(data, session_id)["attribute"]
    correct(data, session_id)
    old_edit = view(data, session_id).edits[0].id
    versions.request_rerun(data, session_id, "transcribe", attendees=None, profile="essai")
    assert Processor(data, FAKE_CHAIN).run_job(claim(data)).error is None
    before = len(view(data, session_id).edits)

    with pytest.raises(corrections.VersionChangedError):
        corrections.add(
            data, session_id, {"kind": "edit_text", "turn": 0, "text": "salut"}, version=first
        )
    with pytest.raises(corrections.VersionChangedError):
        corrections.undo(data, session_id, old_edit)  # a correction of the former version
    assert len(view(data, session_id).edits) == before

    client = local_client(
        create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None)
    )
    refused = client.post(
        f"/api/seances/{session_id}/corrections?version={first}",
        json={"kind": "edit_text", "turn": 0, "text": "salut"},
    )
    assert refused.status_code == 409
    assert refused.json()["detail"].startswith("La version affichée vient de changer")


def test_a_failed_carrying_over_leaves_the_version_shown_and_is_tried_again(
    data: DataDir, recording: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = processed(data, recording)
    first = shown(data, session_id)
    correct(data, session_id)
    job_id = versions.request_rerun(data, session_id, "transcribe", attendees=None, profile="essai")

    def broken(*_: object) -> None:
        raise KeyError("x")

    with monkeypatch.context() as patched:
        patched.setattr("coulisses_app.carryover.carry", broken)
        result = Processor(data, FAKE_CHAIN).run_job(claim(data))
    assert result.error is not None and "KeyError" not in result.error
    assert "La version affichée n'a pas changé" in result.error
    assert shown(data, session_id) == first

    conn = connect(data)
    try:
        jobs.requeue(conn, job_id)
    finally:
        conn.close()
    assert Processor(data, FAKE_CHAIN).run_job(claim(data)).error is None
    assert view(data, session_id).speakers[0].name == "Marie"


def test_a_rerun_whose_kept_stage_has_gone_stops_instead_of_redoing_it(
    data: DataDir, recording: Path
) -> None:
    session_id = processed(data, recording)
    first = shown(data, session_id)
    versions.request_rerun(data, session_id, "diarize", attendees=3, profile="essai")
    data.run_dir(session_id, first["transcribe"]).rename(
        data.run_dir(session_id, "deplace-dans-le-finder")
    )
    result = Processor(data, FAKE_CHAIN).run_job(claim(data))
    assert result.error is not None and "« Transcription »" in result.error
    assert shown(data, session_id) == first
    assert not [
        r
        for r in runs(data, session_id)
        if r["stage"] == "transcribe" and r["id"] != first["transcribe"]
    ]


def test_the_stages_listed_are_those_of_the_version_shown(data: DataDir, recording: Path) -> None:
    session_id = processed(data, recording)
    first = shown(data, session_id)
    versions.request_rerun(data, session_id, "transcribe", attendees=None, profile="essai")
    assert Processor(data, FAKE_CHAIN).run_job(claim(data)).error is None
    versions.show(data, session_id, first["attribute"])
    listed = {s.stage: s.run_id for s in stage_views(data, FAKE_CHAIN, session_id)}
    assert listed == {k: first[k] for k in listed}


def test_redo_and_back_to_the_original_text_are_guarded_too(data: DataDir, recording: Path) -> None:
    session_id = processed(data, recording)
    first = shown(data, session_id)["attribute"]
    correct(data, session_id)
    name = view(data, session_id).edits[0].id
    corrections.undo(data, session_id, name)
    versions.request_rerun(data, session_id, "transcribe", attendees=None, profile="essai")
    assert Processor(data, FAKE_CHAIN).run_job(claim(data)).error is None
    with pytest.raises(corrections.VersionChangedError):
        corrections.redo(data, session_id, name)  # undone on the former version
    with pytest.raises(corrections.VersionChangedError):
        corrections.reset_text(data, session_id, 0, version=first)


def test_the_rerun_says_which_glossary_terms_are_new(data: DataDir, recording: Path) -> None:
    session_id = processed(data, recording)
    space = sessions.get_session(data, session_id)
    assert space is not None
    conn = connect(data)
    try:
        with conn:
            conn.execute(
                "INSERT INTO glossary_entry (space_id, term, variants, created_at)"
                " VALUES (?, 'Kathy', '[]', ?)",
                (space.space_id, now_iso()),
            )
    finally:
        conn.close()
    facts = versions.list_versions(data, session_id).rerun
    assert facts.glossary_added == ["Kathy"]
    assert facts.engine_updated is False
