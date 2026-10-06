"""The actions one can modify or write, and the note after the session (spec §7.8, §7.9).
The model is a fake."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from coulisses_app.paths import DataDir
from coulisses_app.prompting import assembly
from coulisses_app.prompting.generate import generate

from .conftest import FakeModel
from .test_generation import client, imported, run_all  # noqa: F401  (fixture)

ORIGINAL = assembly.action("resume-impro").prompt


def by_ref(client: TestClient) -> dict[str, dict[str, object]]:  # noqa: F811
    return {a["ref"]: a for a in client.get("/api/actions").json()}


def test_the_provided_actions_are_listed_unmodified(client: TestClient) -> None:  # noqa: F811
    listed = by_ref(client)
    assert len(listed) == 6
    assert listed["resume-impro"]["provided"] and not listed["resume-impro"]["modified"]
    assert listed["resume-impro"]["prompt"] == ORIGINAL


def test_modifying_a_provided_action_keeps_the_original_restorable(
    client: TestClient,  # noqa: F811
    data: DataDir,
    recording: Path,
    fake_model: FakeModel,
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    response = client.put(
        "/api/actions/resume-impro",
        json={"name": "Résumé Impro", "description": "Le mien.", "prompt": "MA CONSIGNE"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["modified"]
    prov = generate(data, session_id, "resume-impro", "modele-essai", fake_model)
    sent = fake_model.calls[-1][1][0]["content"]
    assert "MA CONSIGNE" in sent and ORIGINAL not in sent
    assert assembly.FRENCH_INSTRUCTION in sent  # the assembly still adds it (P4)
    spec = json.loads((data.run_dir(session_id, prov.run_id) / "spec.json").read_text())
    assert spec["action_prompt"] == "MA CONSIGNE"  # what made it, kept for good (P5)

    restored = client.post("/api/actions/resume-impro/restaurer").json()
    assert not restored["modified"] and restored["prompt"] == ORIGINAL
    assert spec == json.loads((data.run_dir(session_id, prov.run_id) / "spec.json").read_text())


def test_an_action_of_ones_own_is_created_used_duplicated_then_archived(
    client: TestClient,  # noqa: F811
    data: DataDir,
    recording: Path,
    fake_model: FakeModel,
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    created = client.post(
        "/api/actions",
        json={"name": "Citations", "description": "Les phrases à garder.", "prompt": "RELÈVE"},
    )
    assert created.status_code == 201, created.text
    ref = created.json()["ref"]
    assert ref.startswith("perso-") and not created.json()["provided"]
    asked = client.post(f"/api/seances/{session_id}/resumes", json={"action_ref": ref})
    assert asked.status_code == 202
    run_all(data, fake_model)
    listed = client.get(f"/api/seances/{session_id}/resumes").json()["generations"]
    assert listed[0]["action_name"] == "Citations"

    copy = client.post(f"/api/actions/{ref}/dupliquer").json()
    assert copy["name"] == "Copie de Citations" and copy["prompt"] == "RELÈVE"

    assert client.post(f"/api/actions/{ref}/archiver").status_code == 204
    assert ref not in by_ref(client)
    # Its summary stays, with its name.
    listed = client.get(f"/api/seances/{session_id}/resumes").json()["generations"]
    assert listed[0]["action_name"] == "Citations" and listed[0]["output"]


def test_a_provided_action_is_never_archived(client: TestClient) -> None:  # noqa: F811
    response = client.post("/api/actions/resume-impro/archiver")
    assert response.status_code == 422
    assert "restaurez" in response.json()["detail"]


def test_an_action_needs_a_name_and_a_prompt(client: TestClient) -> None:  # noqa: F811
    for body, said in [
        ({"name": " ", "prompt": "x"}, "nom"),
        ({"name": "A", "prompt": "  "}, "prompt"),
        ({"name": "A" * 81, "prompt": "x"}, "80"),
    ]:
        response = client.post("/api/actions", json=body)
        assert response.status_code == 422 and said in response.json()["detail"]
    assert client.put("/api/actions/perso-99", json={"name": "A", "prompt": "x"}).status_code == 404


# -- the note after the session ----------------------------------------------------------


def test_the_note_goes_into_the_context_and_changing_it_makes_the_summary_stale(
    client: TestClient,  # noqa: F811
    data: DataDir,
    recording: Path,
    fake_model: FakeModel,
) -> None:
    session_id = imported(client, recording)
    url = f"/api/seances/{session_id}"
    assert client.get(f"{url}/notes").json() is None
    written = client.put(f"{url}/notes", json={"text": "  Marie absente la prochaine fois.  "})
    assert (
        written.status_code == 200 and written.json()["text"] == "Marie absente la prochaine fois."
    )
    run_all(data, fake_model)
    client.post(f"/api/seances/{session_id}/resumes", json={"action_ref": "resume-impro"})
    run_all(data, fake_model)
    sent = fake_model.calls[-1][1][1]["content"]
    assert "## Notes prises après la séance\nMarie absente la prochaine fois." in sent
    assert not client.get(f"{url}/resumes").json()["generations"][0]["stale"]

    client.put(f"{url}/notes", json={"text": "Marie revient finalement."})
    assert client.get(f"{url}/resumes").json()["generations"][0]["stale"]


def test_an_emptied_note_is_kept_empty_and_leaves_the_context(
    client: TestClient,  # noqa: F811
    data: DataDir,
    recording: Path,
    fake_model: FakeModel,
) -> None:
    session_id = imported(client, recording)
    url = f"/api/seances/{session_id}"
    client.put(f"{url}/notes", json={"text": "Une idée."})
    assert client.put(f"{url}/notes", json={"text": ""}).json()["text"] == ""
    run_all(data, fake_model)
    assert "Notes prises" not in fake_model.calls[-1][1][1]["content"]
    assert client.put("/api/seances/inconnue/notes", json={"text": "x"}).status_code == 404


def test_a_modified_action_is_modified_again_then_restored_then_modified_anew(
    client: TestClient,  # noqa: F811
) -> None:
    def put(prompt: str) -> dict[str, object]:
        return client.put(
            "/api/actions/resume-impro", json={"name": "Résumé Impro", "prompt": prompt}
        ).json()

    assert put("V1")["prompt"] == "V1"
    assert put("V2")["prompt"] == "V2"  # the version in force is updated, not doubled
    assert client.post("/api/actions/resume-impro/restaurer").json()["prompt"] == ORIGINAL
    assert put("V3")["modified"]  # a new modified version, the archived ones kept


def test_a_summary_asked_for_an_action_archived_since_fails_visibly(
    client: TestClient,  # noqa: F811
    data: DataDir,
    recording: Path,
    fake_model: FakeModel,
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    own = client.post("/api/actions", json={"name": "Citations", "prompt": "RELÈVE"}).json()
    client.post(f"/api/seances/{session_id}/resumes", json={"action_ref": own["ref"]})
    client.post(f"/api/actions/{own['ref']}/archiver")
    run_all(data, fake_model)
    pending = client.get(f"/api/seances/{session_id}/resumes").json()["pending"]
    assert [(p["state"], p["error"]) for p in pending] == [("failed", "Action introuvable.")]


def test_a_space_offers_one_summary_first_and_its_other_settings_stay(
    client: TestClient,  # noqa: F811
) -> None:
    space = client.get("/api/espaces").json()[0]["id"]
    client.put(f"/api/espaces/{space}/actions/idees-scenes", json={"auto_run": True, "model": "m"})
    offered = client.put(
        f"/api/espaces/{space}/resume-propose", json={"action_ref": "resume-court"}
    ).json()
    assert {(a["action_ref"], a["auto_run"], a["model"]) for a in offered} == {
        ("resume-impro", False, None),
        ("idees-scenes", False, "m"),
        ("resume-court", True, None),
    }
    assert (
        client.put(f"/api/espaces/{space}/resume-propose", json={"action_ref": "x"}).status_code
        == 404
    )


def test_a_long_name_is_not_cut_when_duplicated(client: TestClient) -> None:  # noqa: F811
    own = client.post("/api/actions", json={"name": "N" * 80, "prompt": "P"}).json()
    assert client.post(f"/api/actions/{own['ref']}/dupliquer").json()["name"] == "N" * 80
