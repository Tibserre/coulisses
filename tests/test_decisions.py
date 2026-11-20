"""Each ADR number is taken once (Pilotage/organisation.md, rule 8). Run on the result of a
merge, before it is pushed to main: two branches that took the same number fail here."""

import re
from collections import Counter
from pathlib import Path

DECISIONS = Path(__file__).resolve().parents[1] / "docs" / "decisions"


def test_no_two_decisions_share_a_number() -> None:
    numbered = {
        p.name: int(m[0]) for p in DECISIONS.glob("*.md") if (m := re.match(r"\d+", p.name))
    }
    assert numbered, f"no ADR found in {DECISIONS}"
    counts = Counter(numbered.values())
    assert not sorted(name for name, n in numbered.items() if counts[n] > 1)
