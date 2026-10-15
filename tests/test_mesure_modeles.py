"""The model measurement script (plan step 11g): it reads the real data, never writes there."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from coulisses_app import paths
from coulisses_app.paths import DataDir
from coulisses_app.phases import DetectedPhase
from coulisses_app.prompting import assembly, ollama
from coulisses_app.prompting.generate import GenerationError, Provenance
from coulisses_app.prompting.ollama import ChatAnswer, InstalledModel, OllamaClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def mesure() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "mesurer_modeles", ROOT / "scripts" / "mesurer-modeles.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def real(monkeypatch, tmp_path: Path) -> Path:
    folder = tmp_path / "Données"
    folder.mkdir()
    monkeypatch.setattr(paths, "DEFAULT_DATA_DIR", folder)
    return folder


PS = """NAME               ID              SIZE     PROCESSOR    CONTEXT    RUNNER    UNTIL
qwen3.8:27b-mlx    5642e97495e1    20 GB    100% GPU     65536      mlx       4 minutes from now
ministral-3:8b     1922accd5827    9.1 GB   100% GPU     65536      llama     Stopping...
"""


def test_ollama_ps_is_read_by_column(mesure) -> None:
    rows = mesure.loaded(PS)
    assert rows["qwen3.8:27b-mlx"]["SIZE"] == "20 GB"
    assert rows["qwen3.8:27b-mlx"]["PROCESSOR"] == "100% GPU"
    assert rows["ministral-3:8b"]["CONTEXT"] == "65536"
    assert rows["ministral-3:8b"]["UNTIL"] == "Stopping..."
    assert mesure.loaded("") == {}


def test_never_into_the_real_data_nor_the_repository(mesure, real: Path, tmp_path: Path) -> None:
    decomposed = Path(unicodedata.normalize("NFD", str(real)).upper()) / "copie"
    for place in (real, real / "sessions" / "x", decomposed, ROOT / "mesures"):
        with pytest.raises(SystemExit):
            mesure.check_place(place)
    mesure.check_place(tmp_path / "Mesures")
    with pytest.raises(SystemExit):
        mesure.copy_sessions(DataDir(tmp_path / "ailleurs"), DataDir(decomposed), [])
    assert not (real / "copie").exists()


def make_source(root: Path, session_ids: list[str]) -> DataDir:
    source = DataDir(root)
    for session_id in session_ids:
        run = source.runs_dir(session_id) / "attribute-1"
        run.mkdir(parents=True)
        (run / "output.json").write_text("{}")
        (source.runs_dir(session_id) / ".scratch").mkdir()
        (source.runs_dir(session_id) / ".scratch" / "audio.wav").write_bytes(b"RIFF")
    conn = sqlite3.connect(source.database)
    conn.execute("CREATE TABLE session (id TEXT)")
    conn.executemany("INSERT INTO session VALUES (?)", [(s,) for s in session_ids])
    conn.commit()
    conn.close()
    return source


def test_the_copy_reads_the_source_only(mesure, real: Path, tmp_path: Path) -> None:
    source = make_source(tmp_path / "source", ["s1"])
    before = source.database.read_bytes()
    target = DataDir(tmp_path / "copie")
    mesure.copy_sessions(source, target, ["s1"])
    copied = sqlite3.connect(target.database)
    assert copied.execute("SELECT id FROM session").fetchall() == [("s1",)]
    copied.close()
    assert (target.runs_dir("s1") / "attribute-1" / "output.json").read_text() == "{}"
    assert not (target.runs_dir("s1") / ".scratch").exists()  # no audio comes along
    assert source.database.read_bytes() == before
    with pytest.raises(FileExistsError):  # never into an existing folder
        mesure.copy_sessions(source, target, ["s1"])
    with pytest.raises(SystemExit):  # a session without processing is said
        mesure.copy_sessions(source, DataDir(tmp_path / "autre"), ["absente"])


class FakeClient:
    def __init__(self) -> None:
        self.answers: list[ChatAnswer] = []

    def models(self) -> list[InstalledModel]:
        return [InstalledModel(name="petit:4b", size_bytes=1, digest="d")]

    def version(self) -> str | None:
        return "0.0"


def fake_run(fail_on: str | None = None, stop_on: str | None = None) -> Any:
    def run(data: DataDir, session_id: str, ref: str, model: str, client: FakeClient):
        if ref == stop_on:
            raise KeyboardInterrupt
        client.answers.append(
            ChatAnswer(
                content="x",
                prompt_eval_count=1000,
                eval_count=100,
                done_reason="stop",
                total_duration_s=3.0,
                load_duration_s=0.0,
                prompt_eval_duration_s=1.0,
                eval_duration_s=2.0,
            )
        )
        failed = ref == fail_on
        run_id = f"{ref}-1"
        now = datetime.now(UTC)
        return Provenance(
            run_id=run_id,
            session_id=session_id,
            stage="segment_phases" if ref == "chapitres" else "summarize",
            app_version="0",
            status="failed" if failed else "succeeded",
            action_ref=ref,
            action_name=ref,
            model=model,
            model_digest=None,
            options={},
            strategy="unique",
            source_run_id="attribute-1",
            edits_applied=0,
            phases_run_id=None if ref == "chapitres" else "segment_phases-réel",
            input_run_id="chapitres-1" if ref == "titre" else None,
            input_kind="chapters" if ref == "titre" else "transcript",
            calls=[],
            started_at=now,
            finished_at=now,
            duration_s=3.0,
            error=GenerationError(type="E", message="vide") if failed else None,
        )

    return run


def test_a_measure_records_speeds_and_whose_chapters_were_used(
    mesure, monkeypatch, real: Path, tmp_path: Path
) -> None:
    source = make_source(tmp_path / "source", ["s1"])
    monkeypatch.setattr(
        mesure, "ollama_command", lambda *a: PS.replace("ministral-3:8b", "petit:4b      ")
    )
    out = tmp_path / "mesures"
    mesure.measure(out, [("s1", "resume-impro")], ["petit:4b"], source, FakeClient(), fake_run())
    results = json.loads((out / "resultats.json").read_text())
    assert [r["task"] for r in results] == ["chapitres", "titre", "resume-impro"]
    assert all(r["status"] == "succeeded" for r in results)
    assert results[0]["calls"][0]["writing_tokens_per_s"] == 50.0
    assert results[0]["calls"][0]["load_s"] == 0.0
    assert results[0]["memory"]["SIZE"] == "9.1 GB"
    assert results[1]["own_chapters"] is True  # the title, from this model's chapters
    # The summary read chapters that are not this model's (the copied real ones): said.
    assert results[2]["own_chapters"] is False


def test_an_interrupted_measure_is_never_taken_as_done(
    mesure, monkeypatch, real: Path, tmp_path: Path
) -> None:
    source = make_source(tmp_path / "source", ["s1"])
    monkeypatch.setattr(mesure, "ollama_command", lambda *a: "")
    out = tmp_path / "mesures"
    with pytest.raises(KeyboardInterrupt):
        mesure.measure(
            out,
            [("s1", "resume-impro")],
            ["petit:4b"],
            source,
            FakeClient(),
            fake_run(stop_on="titre"),
        )
    with pytest.raises(SystemExit):
        mesure.measure(
            out, [("s1", "resume-impro")], ["petit:4b"], source, FakeClient(), fake_run()
        )


def test_ollama_unable_to_say_its_memory_is_recorded(
    mesure, monkeypatch, real: Path, tmp_path: Path
) -> None:
    source = make_source(tmp_path / "source", ["s1"])
    calls: list[tuple[str, ...]] = []

    def command(*args: str) -> str:
        calls.append(args)
        if len(calls) > 1 and args == ("ps",):
            raise mesure.OllamaCommandError("ollama ps : connexion refusée")
        return ""

    monkeypatch.setattr(mesure, "ollama_command", command)
    out = tmp_path / "mesures"
    mesure.measure(out, [("s1", "resume-impro")], ["petit:4b"], source, FakeClient(), fake_run())
    results = json.loads((out / "resultats.json").read_text())
    assert results[0]["memory"] is None
    assert "connexion refusée" in results[0]["memory_error"]


def write_results(tmp_path: Path) -> None:
    results: list[dict[str, Any]] = []
    for model in ("petit:4b", "moyen:12b", "gros:35b"):
        run = tmp_path / model
        run.mkdir()
        (run / "output.md").write_text(f"Résumé écrit par {model}")
        for task in ("resume-impro", "titre"):
            results.append(
                {
                    "model": model,
                    "session": "s1",
                    "task": task,
                    "status": "succeeded",
                    "run": str(run),
                }
            )
    results.append(
        {
            "model": "raté:1b",
            "session": "s1",
            "task": "resume-impro",
            "status": "failed",
            "error": "vide",
        }
    )
    (tmp_path / "resultats.json").write_text(json.dumps(results))


def test_blind_sheets_keep_the_key_apart(mesure, real: Path, tmp_path: Path, capsys) -> None:
    write_results(tmp_path)
    mesure.sheets(tmp_path, ["petit:4b", "moyen:12b", "gros:35b", "raté:1b"], seed=1)
    sheet = (tmp_path / "fiche-s1-resume-impro.md").read_text()
    key = json.loads((tmp_path / "cle.json").read_text())["fiche-s1-resume-impro"]
    assert sorted(key) == ["A", "B", "C"]
    assert sorted(key.values()) == ["gros:35b", "moyen:12b", "petit:4b"]
    for model in key.values():
        assert sheet.count(f"Résumé écrit par {model}") == 1
        assert model not in sheet.replace(f"Résumé écrit par {model}", "")
    assert "raté:1b, s1 · resume-impro (vide)" in capsys.readouterr().out
    with pytest.raises(SystemExit):  # sheets already there are never rewritten
        mesure.sheets(tmp_path, ["petit:4b"])


def test_ollama_gives_its_loading_reading_and_writing_times(monkeypatch) -> None:
    class Answer:
        def __enter__(self) -> Answer:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "message": {"content": "Bonjour"},
                    "prompt_eval_count": 1000,
                    "eval_count": 50,
                    "done_reason": "stop",
                    "total_duration": 3_000_000_000,
                    "load_duration": 0,
                    "prompt_eval_duration": 2_000_000_000,
                    "eval_duration": 500_000_000,
                }
            ).encode()

    monkeypatch.setattr(ollama.urllib.request, "urlopen", lambda *_a, **_k: Answer())
    answer = OllamaClient().chat("m", [], {"num_ctx": 4096})
    assert answer.total_duration_s == 3.0
    assert answer.load_duration_s == 0.0  # already in memory: measured, not unknown
    assert answer.prompt_eval_duration_s == 2.0
    assert answer.eval_duration_s == 0.5


def test_two_summaries_of_one_session_share_its_chapters_and_title(
    mesure, monkeypatch, real: Path, tmp_path: Path
) -> None:
    source = make_source(tmp_path / "source", ["s1"])
    monkeypatch.setattr(mesure, "ollama_command", lambda *a: "")
    out = tmp_path / "mesures"
    asked = [("s1", "resume-impro"), ("s1", "resume-court")]
    mesure.measure(out, asked, ["petit:4b"], source, FakeClient(), fake_run())
    results = json.loads((out / "resultats.json").read_text())
    assert [r["task"] for r in results] == ["chapitres", "titre", "resume-impro", "resume-court"]


def test_a_session_without_an_action_gets_its_chapters_and_title_only(
    mesure, monkeypatch, real: Path, tmp_path: Path
) -> None:
    source = make_source(tmp_path / "source", ["s1"])
    monkeypatch.setattr(mesure, "ollama_command", lambda *a: "")
    out = tmp_path / "mesures"
    mesure.measure(out, [("s1", None)], ["petit:4b"], source, FakeClient(), fake_run())
    results = json.loads((out / "resultats.json").read_text())
    assert [r["task"] for r in results] == ["chapitres", "titre"]


def test_chapters_are_scored_on_cuts_within_a_minute_and_kinds_over_time(mesure) -> None:
    # Ten lines, one a minute; the reference cuts at 3 and 6 minutes.
    turns = [(i, i * 60.0) for i in range(10)]
    reference = [
        DetectedPhase(turn=0, kind="discussion", title="a"),
        DetectedPhase(turn=3, kind="scene", title="b"),
        DetectedPhase(turn=6, kind="discussion", title="c"),
    ]
    # Found: 4 minutes (one off, within the tolerance), 8 minutes (wrong), 6 missed.
    found = [
        DetectedPhase(turn=0, kind="discussion", title="a"),
        DetectedPhase(turn=4, kind="scene", title="b"),
        DetectedPhase(turn=8, kind="scene", title="x"),
    ]
    scores = mesure.score_session(found, reference, turns)
    assert (scores["chapters"], scores["reference_chapters"]) == (3, 3)
    assert scores["precision"] == 0.5 and scores["recall"] == 0.5
    # Kinds wrong over minutes 3, 6, 7 and 8: 5 of the 9 measured minutes right.
    assert scores["kinds"] == pytest.approx(5 / 9)


def test_a_setting_changed_for_a_measure_is_put_in_place_and_an_unknown_one_refused(
    mesure, monkeypatch
) -> None:
    monkeypatch.setattr(assembly, "settings", assembly.settings)  # restored after
    changed = mesure.with_settings(["temperature=0", "phases_section_min=15"])
    assert changed == {"temperature": 0, "phases_section_min": 15}
    assert assembly.settings().phases_section_min == 15
    with pytest.raises(SystemExit):
        mesure.with_settings(["inconnu=1"])
