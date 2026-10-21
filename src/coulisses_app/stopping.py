"""« Arrêter » without a confirmation (ADR 0058): the recording is paused at once by the
caller, then stopped after a moment unless taken back. Done by the service, so that it
stops even if the page is closed meanwhile; the page reads how it went.

One condition guards the phase: waiting (the delay runs), stopping (a stop is under way),
idle. A stop asked from elsewhere (the menu bar) while waiting stops at once; while
stopping, it waits for that stop to end (never for a thread, which a web server keeps
alive) and gets that stop's own outcome. A stop's outcome is never lost (P8).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from coulisses_app import capture

log = logging.getLogger(__name__)

Phase = Literal["idle", "waiting", "stopping"]
KEPT_OUTCOMES = 4
"""How many stops' outcomes are kept for whoever waited for them."""
SHUTDOWN_WAIT_S = 60.0
"""At most this long, when the service stops, for a stop under way to close its files."""


class StopOutcome(BaseModel):
    pending: bool
    """A stop asked, its delay or the stop itself still under way: ask again shortly."""
    stopped: capture.StopResult | None
    """The last stop done."""
    error: str | None
    """Why the last stop failed; none once a stop succeeds."""


class DelayedStop:
    def __init__(self, stop: Callable[[], capture.StopResult], delay_s: float) -> None:
        self._stop = stop
        self.delay_s = delay_s
        self._cond = threading.Condition()
        self._phase: Phase = "idle"
        self._timer: threading.Timer | None = None
        self._count = 0
        """Stops started so far: each one's outcome is its own."""
        self._outcomes: dict[int, capture.StopResult | Exception] = {}
        self._last: capture.StopResult | None = None
        self._error: str | None = None

    def schedule(self) -> None:
        """Stop after the delay (the caller has paused the recording)."""
        with self._cond:
            if self._phase == "stopping":
                return
            if self._timer is not None:
                self._timer.cancel()
            self._phase = "waiting"
            self._error = None
            timer = threading.Timer(self.delay_s, lambda: self._due(timer))
            timer.daemon = True
            self._timer = timer
            timer.start()

    def cancel(self) -> bool:
        """Take the stop back: false once it is under way (too late to take back)."""
        with self._cond:
            if self._phase == "stopping":
                return False
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._phase = "idle"
            return True

    def stop_now(self) -> capture.StopResult:
        """Stop at once (the menu bar): a delay running is cut short; a stop under way is
        waited for, and its own outcome returned."""
        with self._cond:
            if self._phase == "stopping":
                waited = self._count
                while self._phase == "stopping":
                    self._cond.wait()
                outcome = self._outcomes.get(waited)
                if isinstance(outcome, capture.StopResult):
                    return outcome
                raise capture.RecordingError(f"L'arrêt n'a pas abouti : {outcome}")
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            number = self._begin()
        outcome = self._run(number)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def _due(self, timer: threading.Timer) -> None:
        with self._cond:
            # Only its own timer, still waiting: never one cancelled then replaced.
            if self._phase != "waiting" or self._timer is not timer:
                return
            self._timer = None
            number = self._begin()
        outcome = self._run(number)
        if isinstance(outcome, Exception):
            log.error("stopping the recording after its delay: %s", outcome)

    def _begin(self) -> int:
        """Under the condition: a stop starts."""
        self._phase = "stopping"
        self._count += 1
        return self._count

    def _run(self, number: int) -> capture.StopResult | Exception:
        try:
            outcome: capture.StopResult | Exception = self._stop()
        except Exception as exc:  # kept for whoever waits, and said to the page
            log.exception("stopping the recording")
            outcome = exc
        with self._cond:
            # The last few kept: whoever waited finds its own, even if another one began.
            self._outcomes[number] = outcome
            for older in [n for n in self._outcomes if n <= number - KEPT_OUTCOMES]:
                del self._outcomes[older]
            if isinstance(outcome, capture.StopResult):
                self._last = outcome
                self._error = None
            elif not isinstance(outcome, capture.NotRecordingError):
                # A stop asked twice finds nothing to stop: not a problem to say.
                self._error = str(outcome)
            self._phase = "idle"
            self._cond.notify_all()
        return outcome

    def outcome(self) -> StopOutcome:
        with self._cond:
            return StopOutcome(pending=self._phase != "idle", stopped=self._last, error=self._error)

    def shutdown(self) -> None:
        """The service stops: a delay running is dropped (the recorder closes the recording
        itself); a stop under way is waited for, so that its files are closed properly."""
        with self._cond:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            if self._phase == "waiting":
                self._phase = "idle"
            if self._phase == "stopping" and not self._cond.wait_for(
                lambda: self._phase != "stopping", SHUTDOWN_WAIT_S
            ):
                # The recording will be found « interrupted » at the next start: the log
                # says why.
                log.warning(
                    "a stop was still under way after %.0f s when the service stopped",
                    SHUTDOWN_WAIT_S,
                )
