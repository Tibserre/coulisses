"""The progress of a running stage, as the engine writes it (its README, « Suivi en direct »):
the phase's rank among the stage's phases since engine v1.13.0, absent before."""

from __future__ import annotations

import json
from pathlib import Path

from coulisses_app.status import ProgressView, _read_progress  # pyright: ignore[reportPrivateUsage]

WRITTEN = {
    "phase": "Empreintes",
    "done": 2.0,
    "total": 5.0,
    "unit": "s",
    "updated_at": "2026-10-27T10:00:00Z",
}


def test_the_rank_of_the_phase_is_given(tmp_path: Path) -> None:
    (tmp_path / "progress.json").write_text(json.dumps(WRITTEN | {"step": 2, "steps": 4}))
    assert _read_progress(tmp_path) == ProgressView(
        phase="Empreintes", done=2.0, total=5.0, unit="s", step=2, steps=4
    )


def test_a_run_before_engine_1_13_has_no_rank(tmp_path: Path) -> None:
    (tmp_path / "progress.json").write_text(json.dumps(WRITTEN))
    progress = _read_progress(tmp_path)
    assert progress is not None and progress.step is None and progress.steps is None
