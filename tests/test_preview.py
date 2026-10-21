"""The text shown while a session is processed (ADR 0058): lines at their measured time, or
none, in the order of the text; never a time made up (P2)."""

from __future__ import annotations

from coulisses.api import Transcript

from coulisses_app.preview import _lines


def transcript(
    words: list[tuple[str, float | None, float | None]], *, measured: bool = True
) -> Transcript:
    return Transcript.model_validate(
        {
            "reference_source": "ref",
            "language": "fr",
            "words": [{"text": t, "start": s, "end": e} for t, s, e in words],
            "measured_word_timestamps": measured,
            "chunks": [],
            "untranscribed": [],
        }
    )


def test_lines_end_at_a_sentence_or_a_long_gap_and_keep_the_measured_time() -> None:
    lines = _lines(
        transcript(
            [
                ("On", 1.0, 1.2),
                ("garde", 1.2, 1.5),
                ("le 14.", 1.5, 2.0),
                ("Les", 2.1, 2.3),
                ("maquettes", 2.3, 2.9),
                ("sont", 6.0, 6.2),  # three seconds later: a new line
                ("prêtes", 6.2, 6.8),
            ]
        )
    )
    assert [(line.start, line.text) for line in lines] == [
        (1.0, "On garde le 14."),
        (2.1, "Les maquettes"),
        (6.0, "sont prêtes"),
    ]


def test_a_line_whose_first_word_has_no_time_gets_none_never_a_made_up_one() -> None:
    lines = _lines(transcript([("Euh", None, None), ("bon.", 3.0, 3.2), ("Donc", 4.0, 4.1)]))
    assert [(line.start, line.text) for line in lines] == [(None, "Euh bon."), (4.0, "Donc")]
