"""French formatting shared by the service (history of corrections, prompts later)."""

from __future__ import annotations


def clock(seconds: float) -> str:
    """`m:ss`, or `h:mm:ss` past an hour, like the review screen."""
    s = max(0, int(seconds))
    h, rest = divmod(s, 3600)
    m, sec = divmod(rest, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"
