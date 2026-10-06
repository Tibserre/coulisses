"""Summaries and titles: the single assembly, the run that keeps every prompt, the context
window that is never overflowed, and the service around them. The model is a fake."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coulisses_app import jobs
from coulisses_app.api import create_app
from coulisses_app.paths import DataDir
from coulisses_app.processing import Processor
from coulisses_app.prompting import assembly
from coulisses_app.prompting.generate import generate
from coulisses_app.storage.db import connect

from .conftest import FAKE_CHAIN, FakeModel


def run_all(data: DataDir, fake: FakeModel) -> None:
    """Run every queued job, the chain then the generations it queues."""
    processor = Processor(data, FAKE_CHAIN, model_client=fake)
    while True:
        conn = connect(data)
        try:
            job = jobs.claim_next(conn)
        finally:
            conn.close()
        if job is None:
            return
        processor.run_job(job)


@pytest.fixture
def client(data: DataDir, fake_model: FakeModel) -> TestClient:
    app = create_app(
        data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None, model_client=fake_model
    )
    return TestClient(app)


def imported(client: TestClient, recording: Path) -> str:
    with recording.open("rb") as f:
        response = client.post(
            "/api/seances", files={"fichier": ("a.wav", f, "audio/wav")}, data={"non_nommes": "2"}
        )
    assert response.status_code == 201
    return response.json()["id"]


def test_the_assembly_keeps_its_order_and_always_asks_for_french() -> None:
    prompt = assembly.assemble("CONSIGNE DE L'ACTION", "CONTEXTE", "[0:00] Marie : bonjour")
    system = prompt.system
    positions = [
        system.index(assembly.system_frame()[:40]),
        system.index("CONSIGNE DE L'ACTION"),
        system.index(assembly.FALLBACK_RULE[:40]),
        system.index(assembly.FRENCH_INSTRUCTION[:40]),
    ]
    assert positions == sorted(positions)
    assert prompt.user.index("CONTEXTE") < prompt.user.index("[0:00] Marie : bonjour")
    assert [m["role"] for m in prompt.messages()] == ["system", "user"]


def test_both_provided_actions_are_read_with_their_names() -> None:
    names = {a.ref: a.name for a in assembly.provided_actions()}
    assert names == {
        "resume-impro": "Résumé Impro",
        "compte-rendu-reunion": "Compte rendu de réunion",
    }
    for action in assembly.provided_actions():
        # Their own text never repeats what the assembly adds (rules/prompts.md).
        assert assembly.FRENCH_INSTRUCTION not in action.prompt
        assert "Aucun contenu substantiel" not in action.prompt


def test_after_processing_the_title_and_the_space_summaries_are_made(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    session_id = imported(client, recording)
    fake_model.answer = "« Scène du marché. »"
    run_all(data, fake_model)
    session = client.get(f"/api/seances/{session_id}").json()["session"]
    assert session["title"] == "Scène du marché"  # cleaned: no quotes, no final point
    title_options = fake_model.calls[0][2]
    assert title_options["stop"] == ["\n"]  # one line: never cut for going on (P8)
    assert len(fake_model.calls) == 2  # the title, then the space's Résumé Impro
    listed = client.get(f"/api/seances/{session_id}/resumes").json()
    assert [g["action_ref"] for g in listed["generations"]] == ["resume-impro"]
    assert listed["pending"] == []


def test_a_generation_keeps_every_prompt_and_its_provenance(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    first = client.get(f"/api/seances/{session_id}/transcript").json()["speakers"][0]["label"]
    client.post(
        f"/api/seances/{session_id}/corrections",
        json={"kind": "assign_speaker", "speaker": first, "name": "Marie"},
    )
    prov = generate(data, session_id, "resume-impro", "modele-essai", fake_model)
    assert prov.status == "succeeded" and prov.strategy == "unique"
    assert prov.options["num_ctx"] == assembly.settings().num_ctx  # always explicit
    assert prov.edits_applied == 1
    folder = data.run_dir(session_id, prov.run_id)
    sent = (folder / "calls/01-prompt.txt").read_text(encoding="utf-8")
    _model, messages, options = fake_model.calls[-1]
    system, user = messages[0]["content"], messages[1]["content"]
    assert sent == f"=== système ===\n{system}\n\n=== utilisateur ===\n{user}\n"
    assert "] Marie : bonjour" in messages[1]["content"]  # the corrected name, not « Locuteur 1 »
    assert assembly.FRENCH_INSTRUCTION in messages[0]["content"]
    assert (folder / "output.md").read_text(encoding="utf-8").startswith("## Décisions")
    saved = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
    assert saved["model"] == "modele-essai" and saved["model_digest"] == "abc"
    assert options["temperature"] == assembly.settings().temperature


def test_a_long_session_is_summarised_by_parts_then_merged(
    client: TestClient,
    data: DataDir,
    recording: Path,
    fake_model: FakeModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    small = assembly.settings().model_copy(update={"num_ctx": 6000, "response_reserve": 500})
    monkeypatch.setattr(assembly, "settings", lambda: small)
    long_lines = [
        (float(i * 10), f"[{i // 6}:{i % 6}0] Marie : " + "on reprend la scène du marché " * 10)
        for i in range(60)
    ]
    monkeypatch.setattr(assembly, "transcript_lines", lambda _view: long_lines)
    fake_model.prompt_tokens = 100
    calls_before = len(fake_model.calls)
    prov = generate(data, session_id, "resume-impro", "modele-essai", fake_model)
    assert prov.status == "succeeded", prov.error
    assert prov.strategy == "sections"
    kinds = [c.kind for c in prov.calls]
    assert kinds[-1] == "consolidation" and set(kinds[:-1]) == {"section"}
    assert kinds.count("section") >= 2
    for _, messages, options in fake_model.calls[calls_before:]:
        assert assembly.FRENCH_INSTRUCTION in messages[0]["content"]  # every call, P4
        assert options["num_ctx"] == 6000


def test_a_full_context_window_is_a_failure_not_a_cut(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    fake_model.prompt_tokens = assembly.settings().num_ctx  # Ollama filled the window
    prov = generate(data, session_id, "resume-impro", "modele-essai", fake_model)
    assert prov.status == "failed"
    assert prov.error is not None and "fenêtre" in prov.error.message
    folder = data.run_dir(session_id, prov.run_id)
    assert not (folder / "output.md").exists()  # nothing truncated is kept
    assert (folder / "calls/01-response.md").exists()  # but what came back is kept, to see


def test_ollama_down_is_said_plainly(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    fake_model.down = True
    assert (
        client.post(
            f"/api/seances/{session_id}/resumes", json={"action_ref": "compte-rendu-reunion"}
        ).status_code
        == 202
    )
    run_all(data, fake_model)
    pending = client.get(f"/api/seances/{session_id}/resumes").json()["pending"]
    assert pending[-1]["state"] == "failed"
    assert "lancez l'application Ollama" in pending[-1]["error"]
    models = client.get("/api/modeles").json()
    assert models["reachable"] is False and models["error"]


def test_a_summary_goes_stale_when_the_transcript_is_corrected(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    assert (
        client.get(f"/api/seances/{session_id}/resumes").json()["generations"][0]["stale"] is False
    )
    client.post(
        f"/api/seances/{session_id}/corrections",
        json={"kind": "edit_text", "turn": 0, "text": "bonsoir"},
    )
    assert (
        client.get(f"/api/seances/{session_id}/resumes").json()["generations"][0]["stale"] is True
    )


def test_the_user_title_is_never_overwritten(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    session_id = imported(client, recording)
    assert (
        client.patch(f"/api/seances/{session_id}", json={"title": "  Ma   séance "}).json()["title"]
        == "Ma séance"
    )
    fake_model.answer = "Un autre titre"
    run_all(data, fake_model)
    assert client.get(f"/api/seances/{session_id}").json()["session"]["title"] == "Ma séance"
    assert client.patch(f"/api/seances/{session_id}", json={"title": " "}).status_code == 422


def test_the_chosen_model_becomes_the_default(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    assert client.get("/api/modeles").json()["default"] == assembly.settings().default_model
    client.post(
        f"/api/seances/{session_id}/resumes",
        json={"action_ref": "resume-impro", "model": "modele-essai"},
    )
    assert client.get("/api/modeles").json()["default"] == "modele-essai"
    assert (
        client.post(
            f"/api/seances/{session_id}/resumes", json={"action_ref": "inconnue"}
        ).status_code
        == 404
    )


def test_markdown_export_holds_the_summary_and_the_corrected_transcript(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    response = client.get(f"/api/seances/{session_id}/export", params={"contenu": "tout"})
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    text = response.text
    assert "## Résumé Impro" in text and "## Décisions" in text
    assert "## Transcription" in text and "bonjour" in text


def test_a_new_space_starts_from_a_template(client: TestClient) -> None:
    work = client.post(
        "/api/espaces", json={"name": "Équipe produit", "template": "reunion"}
    ).json()
    assert client.get(f"/api/espaces/{work['id']}/actions").json() == [
        {"action_ref": "compte-rendu-reunion", "auto_run": True, "model": None}
    ]
    empty = client.post("/api/espaces", json={"name": "Brouillon"}).json()
    assert client.get(f"/api/espaces/{empty['id']}/actions").json() == []
    changed = client.put(
        f"/api/espaces/{empty['id']}/actions/resume-impro", json={"auto_run": True}
    ).json()
    assert changed[0]["auto_run"] is True
    assert client.post("/api/espaces", json={"name": "X", "template": "?"}).status_code == 422


def test_the_published_provenance_schema_is_up_to_date() -> None:
    from coulisses_app.prompting.generate import Provenance

    published = Path(__file__).parents[1] / "schemas" / "generation-provenance.schema.json"
    assert json.loads(published.read_text(encoding="utf-8")) == Provenance.model_json_schema(), (
        "regenerate schemas/generation-provenance.schema.json"
    )


@pytest.mark.parametrize(
    ("setup", "said"),
    [
        (lambda f: setattr(f, "done_reason", "length"), "coupée"),
        (lambda f: setattr(f, "counted", False), "combien de tokens"),
        (lambda f: setattr(f, "prompt_tokens", 10_000_000), "fenêtre"),
        (lambda f: setattr(f, "answer", "   "), "vide"),
    ],
)
def test_an_answer_that_cannot_be_trusted_is_not_kept(
    client: TestClient,
    data: DataDir,
    recording: Path,
    fake_model: FakeModel,
    setup: object,
    said: str,
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    setup(fake_model)  # type: ignore[operator]
    prov = generate(data, session_id, "resume-impro", "modele-essai", fake_model)
    assert prov.status == "failed" and prov.error is not None and said in prov.error.message
    assert not (data.run_dir(session_id, prov.run_id) / "output.md").exists()


def test_an_estimate_below_the_real_count_is_refused(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    fake_model.prompt_tokens = 30_000  # far more than the estimate of this short prompt
    prov = generate(data, session_id, "resume-impro", "modele-essai", fake_model)
    assert prov.status == "failed" and prov.error is not None
    assert "caracteres_par_token" in prov.error.message


def test_a_line_too_long_for_the_window_is_refused_not_cut(
    client: TestClient,
    data: DataDir,
    recording: Path,
    fake_model: FakeModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    small = assembly.settings().model_copy(update={"num_ctx": 6000, "response_reserve": 500})
    monkeypatch.setattr(assembly, "settings", lambda: small)
    monkeypatch.setattr(
        assembly, "transcript_lines", lambda _view: [(0.0, "[0:00] Marie : " + "mot " * 5000)]
    )
    prov = generate(data, session_id, "resume-impro", "modele-essai", fake_model)
    assert (
        prov.status == "failed" and prov.error is not None and "trop longue" in prov.error.message
    )


def test_a_session_with_no_content_keeps_its_date_as_title(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    session_id = imported(client, recording)
    fake_model.answer = "Séance sans contenu"
    run_all(data, fake_model)
    assert client.get(f"/api/seances/{session_id}").json()["session"]["title"] is None
    fake_model.answer = "« »"
    prov = generate(data, session_id, "titre", "modele-essai", fake_model)
    assert prov.status == "failed" and prov.error is not None and "titre" in prov.error.message


def test_undoing_then_making_another_correction_makes_the_summary_stale(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    base = f"/api/seances/{session_id}"
    first = client.post(
        f"{base}/corrections", json={"kind": "edit_text", "turn": 0, "text": "bonsoir"}
    ).json()["edits"][-1]["id"]
    generate(data, session_id, "resume-impro", "modele-essai", fake_model)
    client.post(f"{base}/corrections/{first}/annuler")
    client.post(f"{base}/corrections", json={"kind": "edit_text", "turn": 0, "text": "salut"})
    # Same number of corrections in force, not the same ones: stale.
    latest = client.get(f"{base}/resumes").json()["generations"][0]
    assert latest["stale"] is True


def test_think_and_the_ollama_version_are_in_the_provenance(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    prov = generate(data, session_id, "resume-impro", "modele-essai", fake_model)
    assert prov.options["think"] is False and prov.ollama_version == "0.0-essai"


def test_a_failed_title_can_be_asked_again_and_the_failure_then_goes(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    session_id = imported(client, recording)
    fake_model.down = True
    run_all(data, fake_model)
    pending = client.get(f"/api/seances/{session_id}/resumes").json()["pending"]
    assert {p["action_ref"] for p in pending} == {"titre", "resume-impro"}
    fake_model.down = False
    fake_model.answer = "Scène du marché"
    assert (
        client.post(f"/api/seances/{session_id}/resumes", json={"action_ref": "titre"}).status_code
        == 202
    )
    run_all(data, fake_model)
    pending = client.get(f"/api/seances/{session_id}/resumes").json()["pending"]
    assert [p["action_ref"] for p in pending] == ["resume-impro"]  # only the one not redone
    assert client.get(f"/api/seances/{session_id}").json()["session"]["title"] == "Scène du marché"


def test_a_summary_with_an_unreadable_provenance_is_listed_with_why(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    listed = client.get(f"/api/seances/{session_id}/resumes").json()["generations"][0]
    (data.run_dir(session_id, listed["run_id"]) / "provenance.json").unlink()
    again = client.get(f"/api/seances/{session_id}/resumes").json()["generations"][0]
    assert again["problem"] and "provenance" in again["problem"]
    assert again["output"]  # the summary itself is still shown


def test_a_title_followed_by_more_is_kept_even_when_the_rest_is_cut(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    fake_model.done_reason = "length"
    fake_model.answer = "Le marché et la fin\n\n## Résumé\nLa séance a commencé par"
    prov = generate(data, session_id, "titre", "modele-essai", fake_model)
    assert prov.status == "succeeded", prov.error
    assert client.get(f"/api/seances/{session_id}").json()["session"]["title"] == (
        "Le marché et la fin"
    )
    fake_model.answer = "Le marché et la f"  # the title itself cut: refused (P8)
    assert generate(data, session_id, "titre", "modele-essai", fake_model).status == "failed"
