"""Measures writing models on real sessions, without ever writing to them (plan step 11g,
question M6): which model to advise for each memory tier.

Each model works on its own copy of the sessions given, made outside the real data and
outside this repository: the base copied compact (VACUUM INTO, the real one opened
read-only), then each session's runs (no audio). On it, the model does what the app does
after a session: the chapters, the title (from them), then the summary asked, all through
`prompting.generate` (assembly, provenance, no cut text). Kept, for each: success or error,
duration, tokens, Ollama's loading, reading and writing times, the memory the model holds
once loaded with the app's num_ctx (`ollama ps`), and which chapters the title and the
summary were made from (the model's own, or those copied from the real base when its own
failed: the measure says so).

Then `--fiches` writes, for the models chosen, a blind sheet per session and summary: the
summaries in a random order, named A, B, C…; the key apart.

Usage:
    uv run python scripts/mesurer-modeles.py --seance ID[:ACTION] … --modele M …  [--sortie D]
    uv run python scripts/mesurer-modeles.py --fiches D --modele M …
    uv run python scripts/mesurer-modeles.py --noter D --references R
A session given without an action gets its chapters and title only. `--reglage cle=valeur`
changes a generation setting for the measure (written in `variante.json`), `--reflexion`
lets the model reason before answering. `--noter` scores the chapters against reference
chapters written by hand (`R/reference-<séance>.json`, the answer's format): cuts right
within a minute, kinds right over time, count.
Everything goes to ~/Coulisses/Mesures/<date> by default: it holds copies of the real base
and real transcripts, and is deleted by hand once the choice is made.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import unicodedata
from collections.abc import Callable
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Any, NoReturn

from coulisses_app import corrections
from coulisses_app.paths import DEFAULT_DATA_DIR, DataDir, is_real_data
from coulisses_app.phases import DetectedPhase, PhaseDetection, snap
from coulisses_app.prompting import assembly
from coulisses_app.prompting.generate import (
    PHASES_REF,
    TITLE_REF,
    GenerationFailedError,
    Provenance,
    generate,
)
from coulisses_app.prompting.ollama import ChatAnswer, InstalledModel, OllamaClient

ROOT = Path(__file__).resolve().parents[1]
MEASURES = Path.home() / "Coulisses" / "Mesures"
RESULTS = "resultats.json"
DONE = ".fini"
KEY = "cle.json"
VARIANT = "variante.json"
SCORES = "notes.json"
TOLERANCE_S = 60.0
# The ollama command follows OLLAMA_HOST: kept on this Mac, like OllamaClient (P1).
OLLAMA_ENV = {**os.environ, "OLLAMA_HOST": "127.0.0.1:11434"}


def say(text: str) -> None:
    print(text, flush=True)


def fail(text: str) -> NoReturn:
    print(f"Refusé : {text}", file=sys.stderr)
    raise SystemExit(1)


class OllamaCommandError(RuntimeError):
    pass


class TimedClient:
    """Ollama's client, keeping every answer: its loading, reading and writing times."""

    def __init__(self, inner: OllamaClient, think: bool | None = None) -> None:
        self.inner = inner
        self.answers: list[ChatAnswer] = []
        self.think = think
        """When set, replaces the app's choice: whether the model reasons first."""

    def models(self) -> list[InstalledModel]:
        return self.inner.models()

    def version(self) -> str | None:
        return self.inner.version()

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, object],
        *,
        answer_format: dict[str, object] | None = None,
    ) -> ChatAnswer:
        if self.think is not None:
            options = {**options, "think": self.think}
        answer = self.inner.chat(model, messages, options, answer_format=answer_format)
        self.answers.append(answer)
        return answer


def slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9.-]+", "-", model)


def _comparable(path: Path) -> str:
    # The Mac's disk ignores case and the composition of accents.
    return unicodedata.normalize("NFC", str(path.expanduser().resolve())).casefold()


def in_repository(path: Path) -> bool:
    given, root = _comparable(path), _comparable(ROOT)
    return given == root or given.startswith(root.rstrip(os.sep) + os.sep)


def check_place(path: Path) -> None:
    """Never into the real data, never into this repository (real transcripts)."""
    if is_real_data(path):
        fail(f"{path} est dans les données réelles")
    if in_repository(path):
        fail(f"{path} est dans le dépôt : de vrais transcripts pourraient y être commités")


def copy_sessions(source: DataDir, target: DataDir, session_ids: list[str]) -> None:
    """The base and the runs of `session_ids`, from `source` opened read-only."""
    check_place(target.root)
    missing = [s for s in session_ids if not source.runs_dir(s).is_dir()]
    if missing:
        fail(f"sans traitement dans {source.root} : {', '.join(missing)}")
    target.root.mkdir(parents=True)  # never into an existing folder
    conn = sqlite3.connect(f"file:{source.database}?mode=ro", uri=True)
    try:
        conn.execute("VACUUM INTO ?", (str(target.database),))
    finally:
        conn.close()
    for session_id in session_ids:
        # .scratch: what the engine may leave after an incident, audio included.
        shutil.copytree(
            source.runs_dir(session_id),
            target.runs_dir(session_id),
            ignore=shutil.ignore_patterns(".scratch"),
        )


def loaded(table: str) -> dict[str, dict[str, str]]:
    """`ollama ps`, by model: its columns (SIZE, PROCESSOR, CONTEXT…)."""
    lines = [line for line in table.splitlines() if line.strip()]
    if not lines:
        return {}
    header = lines[0]
    starts = [m.start() for m in re.finditer(r"\S+", header)]
    names = header.split()
    out: dict[str, dict[str, str]] = {}
    for line in lines[1:]:
        cells = [
            line[a:b].strip() for a, b in zip(starts, [*starts[1:], len(line) + 1], strict=True)
        ]
        row = dict(zip(names, cells, strict=True))
        out[row["NAME"]] = row
    return out


def ollama_command(*args: str) -> str:
    done = subprocess.run(["ollama", *args], capture_output=True, text=True, env=OLLAMA_ENV)
    if done.returncode != 0:
        raise OllamaCommandError(f"ollama {' '.join(args)} : {done.stderr.strip()}")
    return done.stdout


def ollama_ps() -> dict[str, dict[str, str]]:
    return loaded(ollama_command("ps"))


def unload(model: str) -> None:
    """The model out of memory, so that the next one is measured alone."""
    ollama_command("stop", model)
    if model in ollama_ps():
        say(f"   ATTENTION : {model} reste en mémoire, la mesure suivante en sera faussée")


def answer_record(answer: ChatAnswer) -> dict[str, Any]:
    def per_second(count: int | None, seconds: float | None) -> float | None:
        return count / seconds if count and seconds else None

    return {
        "prompt_tokens": answer.prompt_eval_count,
        "answer_tokens": answer.eval_count,
        "done_reason": answer.done_reason,
        "total_s": answer.total_duration_s,
        "load_s": answer.load_duration_s,
        "reading_s": answer.prompt_eval_duration_s,
        "writing_s": answer.eval_duration_s,
        "reading_tokens_per_s": per_second(answer.prompt_eval_count, answer.prompt_eval_duration_s),
        "writing_tokens_per_s": per_second(answer.eval_count, answer.eval_duration_s),
    }


Generate = Callable[[DataDir, str, str, str, TimedClient], Provenance]


def measure(
    out: Path,
    sessions_asked: list[tuple[str, str | None]],
    models: list[str],
    source: DataDir,
    client: TimedClient,
    run: Generate = generate,
) -> None:
    check_place(out)
    installed = {m.name for m in client.models()}
    missing = [m for m in models if m not in installed]
    if missing:
        fail(f"pas installé dans Ollama : {', '.join(missing)}")
    results_file = out / RESULTS
    results: list[dict[str, Any]] = (
        json.loads(results_file.read_text("utf-8")) if results_file.is_file() else []
    )
    for model in models:
        folder = out / "donnees" / slug(model)
        if (folder / DONE).exists():
            continue
        if folder.exists() or any(r["model"] == model for r in results):
            # Its partial records stay in resultats.json: measuring again here would mix them.
            fail(
                f"la mesure de {model} dans {out} s'est arrêtée en cours : "
                "refaites-la dans une autre --sortie"
            )
    try:
        others = set(ollama_ps()) - set(models)
    except OllamaCommandError as exc:
        fail(f"Ollama ne dit pas ce qu'il a en mémoire : {exc}")
    if others:
        say(f"   (déjà en mémoire dans Ollama : {', '.join(sorted(others))})")
    out.mkdir(parents=True, exist_ok=True)
    # A session asked with several summaries: its chapters and title made once.
    by_session: dict[str, list[str]] = {}
    for session_id, action_ref in sessions_asked:
        refs = by_session.setdefault(session_id, [])
        if action_ref is not None:
            refs.append(action_ref)
    for model in models:
        data = DataDir(out / "donnees" / slug(model))
        if (data.root / DONE).exists():
            say(f"{model} : déjà mesuré entièrement dans {data.root}, passé")
            continue
        say(f"{model} : copie des séances…")
        copy_sessions(source, data, list(by_session))
        for session_id, action_refs in by_session.items():
            own_phases: str | None = None
            for ref in (PHASES_REF, TITLE_REF, *action_refs):
                say(f"   {session_id} · {ref}…")
                client.answers = []
                record: dict[str, Any] = {"model": model, "session": session_id, "task": ref}
                if getattr(client, "think", None) is not None:
                    # What the run's spec.json cannot say: the measure changed it.
                    record["think"] = client.think
                try:
                    prov = run(data, session_id, ref, model, client)
                    record |= {
                        "status": prov.status,
                        "error": prov.error.message if prov.error else None,
                        "duration_s": prov.duration_s,
                        "strategy": prov.strategy,
                        "run": str(data.run_dir(session_id, prov.run_id)),
                        "phases_run_id": prov.phases_run_id,
                        "input_kind": prov.input_kind,
                        "input_run_id": prov.input_run_id,
                    }
                    if ref == PHASES_REF and prov.status == "succeeded":
                        own_phases = prov.run_id
                    # Made from the chapters of another model (those copied from the real
                    # base) when this one's failed. A title read from the transcript or a
                    # summary used no chapters.
                    if ref == TITLE_REF and prov.input_kind == "chapters":
                        record["own_chapters"] = prov.input_run_id == own_phases
                    elif ref not in (PHASES_REF, TITLE_REF) and prov.phases_run_id is not None:
                        record["own_chapters"] = prov.phases_run_id == own_phases
                except GenerationFailedError as exc:
                    record |= {"status": "failed", "error": str(exc)}
                record["calls"] = [answer_record(a) for a in client.answers]
                try:
                    record["memory"] = ollama_ps().get(model)
                except OllamaCommandError as exc:
                    record["memory"] = None
                    record["memory_error"] = str(exc)
                    say(f"      mémoire inconnue : {exc}")
                results.append(record)
                results_file.write_text(
                    json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                state = "réussi" if record["status"] == "succeeded" else record["error"]
                if record.get("own_chapters") is False:
                    state += " (sans ses propres chapitres : mesure faussée)"
                say(f"      {state} ({record.get('duration_s') or 0:.0f} s)")
        (data.root / DONE).write_text(datetime.now().isoformat() + "\n", encoding="utf-8")
        try:
            unload(model)
        except OllamaCommandError as exc:
            say(f"   ATTENTION : {exc} ; la mesure suivante peut en être faussée")
    say(f"Mesures dans {results_file}")


def sheets(out: Path, models: list[str], seed: int | None = None) -> None:
    """For each session and summary, those of `models` in a random order (A, B, C…)."""
    check_place(out)
    if (out / KEY).exists() or any(out.glob("fiche-*.md")):
        fail(f"des fiches existent déjà dans {out} : elles ne sont jamais réécrites")
    results = json.loads((out / RESULTS).read_text("utf-8"))
    rng = random.Random(seed)
    asked = [r for r in results if r["task"] not in (PHASES_REF, TITLE_REF)]
    for model in models:
        for session_id, task in dict.fromkeys((r["session"], r["task"]) for r in asked):
            mine = [
                r
                for r in asked
                if (r["model"], r["session"], r["task"]) == (model, session_id, task)
            ]
            if not any(r["status"] == "succeeded" for r in mine):
                why = mine[-1]["error"] if mine else "pas mesuré"
                say(f"   absent des fiches : {model}, {session_id} · {task} ({why})")
    summaries = [r for r in asked if r["model"] in models and r["status"] == "succeeded"]
    key: dict[str, dict[str, str]] = {}
    for session_id, task in dict.fromkeys((r["session"], r["task"]) for r in summaries):
        found = [r for r in summaries if (r["session"], r["task"]) == (session_id, task)]
        rng.shuffle(found)
        letters = [chr(ord("A") + i) for i in range(len(found))]
        name = f"fiche-{session_id}-{task}"
        key[name] = {letter: r["model"] for letter, r in zip(letters, found, strict=True)}
        parts = [f"# {task}, séance {session_id} : {len(found)} résumés à l'aveugle\n"]
        for letter, r in zip(letters, found, strict=True):
            text = (Path(r["run"]) / "output.md").read_text("utf-8").strip()
            parts.append(f"\n\n---\n\n## Résumé {letter}\n\n{text}\n")
        (out / f"{name}.md").write_text("".join(parts), encoding="utf-8")
    (out / KEY).write_text(json.dumps(key, ensure_ascii=False, indent=2), "utf-8")
    say(f"Fiches dans {out} ; la clé, à n'ouvrir qu'après avoir jugé : {out / KEY}")


# -- scoring the chapters against references -----------------------------------------------


def _cuts(phases: list[DetectedPhase], start_of: dict[int, float | None]) -> list[float]:
    """Where each chapter after the first starts, in seconds."""
    return [t for p in phases[1:] if (t := start_of.get(p.turn)) is not None]


def _matched(found: list[float], wanted: list[float], tolerance_s: float) -> int:
    """Cuts found within the tolerance of a wanted one, each used once, closest first."""
    pairs = sorted(
        (abs(f - w), i, j)
        for i, f in enumerate(found)
        for j, w in enumerate(wanted)
        if abs(f - w) <= tolerance_s
    )
    used_f: set[int] = set()
    used_w: set[int] = set()
    for _, i, j in pairs:
        if i not in used_f and j not in used_w:
            used_f.add(i)
            used_w.add(j)
    return len(used_f)


def _kinds_agree(
    found: list[DetectedPhase],
    wanted: list[DetectedPhase],
    turns: list[tuple[int, float | None]],
) -> float:
    """The share of the session's time where the kind found is the kind wanted: played or
    not, « autre » counted as discussion (the detection no longer proposes it, ADR 0045)."""

    def played(kind: str) -> str:
        return "scene" if kind == "scene" else "discussion"

    def kind_at(phases: list[DetectedPhase]) -> dict[int, str]:
        starts = {p.turn: played(p.kind) for p in phases}
        out: dict[int, str] = {}
        current = played(phases[0].kind)
        for index, _ in turns:
            current = starts.get(index, current)
            out[index] = current
        return out

    mine, ref = kind_at(found), kind_at(wanted)
    timed = [(i, t) for i, t in turns if t is not None]
    total = agree = 0.0
    for (index, start), (_, following) in pairwise(timed):
        length = following - start
        total += length
        if mine[index] == ref[index]:
            agree += length
    return agree / total if total else 0.0


def score_session(
    found: list[DetectedPhase],
    reference: list[DetectedPhase],
    turns: list[tuple[int, float | None]],
    tolerance_s: float = TOLERANCE_S,
) -> dict[str, Any]:
    start_of = dict(turns)
    cuts, wanted = _cuts(found, start_of), _cuts(reference, start_of)
    hits = _matched(cuts, wanted, tolerance_s)
    precision = hits / len(cuts) if cuts else 1.0
    recall = hits / len(wanted) if wanted else 1.0
    return {
        "chapters": len(found),
        "reference_chapters": len(reference),
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "kinds": _kinds_agree(found, reference, turns),
    }


def score(out: Path, references: Path, tolerance_s: float = TOLERANCE_S) -> None:
    results = json.loads((out / RESULTS).read_text("utf-8"))
    rows: list[dict[str, Any]] = []
    for r in results:
        if r["task"] != PHASES_REF:
            continue
        ref_file = references / f"reference-{r['session']}.json"
        if not ref_file.is_file():
            say(f"   pas de référence pour {r['session']} : non noté")
            continue
        row: dict[str, Any] = {"model": r["model"], "session": r["session"]}
        if r["status"] != "succeeded":
            rows.append(row | {"error": r["error"]})
            continue
        data = DataDir(out / "donnees" / slug(r["model"]))
        view = corrections.build_view(data, r["session"])
        if view is None:
            fail(f"pas de transcript copié pour {r['session']} dans {data.root}")
        turns = [(t.index, t.start) for t in view.turns]
        reference = snap([ref_file.read_text("utf-8")], turns)
        found = PhaseDetection.model_validate_json(
            (Path(r["run"]) / "output.json").read_text("utf-8")
        )
        row |= score_session(found.phases, reference.phases, turns, tolerance_s)
        row["duration_s"] = r.get("duration_s")
        row["memory"] = (r.get("memory") or {}).get("SIZE")
        rows.append(row)
    (out / SCORES).write_text(json.dumps(rows, ensure_ascii=False, indent=2), "utf-8")
    variant = out / VARIANT
    said = f" ({variant.read_text('utf-8').strip()})" if variant.exists() else ""
    say(f"Notes de {out.name}{said}")
    say(
        f"{'modèle':22}{'séance':10}{'chap.':>11}{'préc.':>7}{'rappel':>7}{'F1':>6}"
        f"{'types':>7}{'durée':>7}  mémoire"
    )
    for row in rows:
        if "error" in row:
            say(f"{row['model']:22}{row['session'][:8]:10}  échec : {row['error']}")
            continue
        say(
            f"{row['model']:22}{row['session'][:8]:10}"
            f"{row['chapters']:>5} / {row['reference_chapters']:<3}"
            f"{row['precision']:>7.2f}{row['recall']:>7.2f}{row['f1']:>6.2f}{row['kinds']:>7.0%}"
            f"{row['duration_s'] or 0:>6.0f}s  {row['memory'] or '?'}"
        )
    for model in dict.fromkeys(r["model"] for r in rows):
        mine = [r for r in rows if r["model"] == model and "error" not in r]
        failed = sum(1 for r in rows if r["model"] == model and "error" in r)
        if mine:
            say(
                f"{model:22}{'moyenne':10}{'':11}"
                f"{sum(r['precision'] for r in mine) / len(mine):>7.2f}"
                f"{sum(r['recall'] for r in mine) / len(mine):>7.2f}"
                f"{sum(r['f1'] for r in mine) / len(mine):>6.2f}"
                f"{sum(r['kinds'] for r in mine) / len(mine):>7.0%}"
                f"{sum(r['duration_s'] or 0 for r in mine):>6.0f}s"
                + (f"  ({failed} échec(s))" if failed else "")
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Mesure des modèles de rédaction.")
    parser.add_argument("--seance", action="append", default=[], help="ID[:ACTION]")
    parser.add_argument("--modele", action="append", default=[])
    parser.add_argument("--sortie", type=Path)
    parser.add_argument("--fiches", type=Path, help="dossier de mesures à mettre en fiches")
    parser.add_argument("--noter", type=Path, help="dossier de mesures dont noter les chapitres")
    parser.add_argument("--references", type=Path, help="dossier des chapitres de référence")
    parser.add_argument(
        "--tolerance", type=float, default=TOLERANCE_S, help="écart admis pour une coupure, en s"
    )
    parser.add_argument("--reglage", action="append", default=[], help="cle=valeur")
    parser.add_argument("--reflexion", action="store_true", help="le modèle réfléchit d'abord")
    args = parser.parse_args()
    if args.noter:
        if not args.references:
            fail("--noter attend --references")
        score(args.noter, args.references, args.tolerance)
        return
    if not args.modele:
        fail("au moins un --modele")
    if args.fiches:
        sheets(args.fiches, args.modele)
        return
    if not args.seance:
        fail("au moins une --seance ID[:ACTION]")
    asked: list[tuple[str, str | None]] = []
    for given in args.seance:
        session_id, colon, action_ref = given.partition(":")
        if not session_id or (colon and not action_ref):
            fail("--seance attend ID[:ACTION], par exemple 20261006-160856-4bdx:resume-impro")
        asked.append((session_id, action_ref or None))
    out = args.sortie or MEASURES / datetime.now().strftime("%Y%m%d-%H%M%S")
    variant = with_settings(args.reglage)
    if args.reflexion:
        variant["reflexion"] = True
    if variant:
        check_place(out)
        out.mkdir(parents=True, exist_ok=True)
        (out / VARIANT).write_text(json.dumps(variant, ensure_ascii=False), "utf-8")
    measure(
        out,
        asked,
        args.modele,
        DataDir(DEFAULT_DATA_DIR),
        TimedClient(OllamaClient(), think=True if args.reflexion else None),
    )


def with_settings(given: list[str]) -> dict[str, Any]:
    """The generation settings changed for this measure (`cle=valeur`, by the names of
    `assembly.Settings`), put in place of the app's."""
    changes: dict[str, Any] = {}
    for item in given:
        name, _, raw = item.partition("=")
        if name not in assembly.Settings.model_fields or not raw:
            fail(f"--reglage attend cle=valeur parmi {', '.join(assembly.Settings.model_fields)}")
        try:
            changes[name] = json.loads(raw)
        except json.JSONDecodeError:
            changes[name] = raw
    if changes:
        try:
            changed = assembly.Settings.model_validate(assembly.settings().model_dump() | changes)
        except ValueError as exc:
            fail(f"--reglage : {exc}")
        assembly.settings = lambda: changed  # type: ignore[assignment]
    return changes


if __name__ == "__main__":
    main()
