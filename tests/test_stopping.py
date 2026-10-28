"""« Arrêter » without a confirmation (ADR 0058): a stop after a delay, taken back, cut short,
raced; its outcome never lost."""

from __future__ import annotations

import threading
import time

import pytest

from coulisses_app import capture
from coulisses_app.stopping import DelayedStop


class FakeStop:
    def __init__(self, *, fails: bool = False, slow: threading.Event | None = None) -> None:
        self.calls = 0
        self.fails = fails
        self.slow = slow
        self.started = threading.Event()

    def __call__(self) -> capture.StopResult:
        self.calls += 1
        self.started.set()
        if self.slow is not None:
            self.slow.wait(5)
        if self.fails:
            raise capture.RecordingError("Le disque est plein.")
        return capture.StopResult(
            session_id="s1", duration_s=12.0, processing=True, on_battery=False
        )


def settle(delayed: DelayedStop) -> None:
    deadline = time.monotonic() + 5
    while delayed.outcome().pending:
        assert time.monotonic() < deadline, "the stop never settled"
        time.sleep(0.01)


def test_stopped_after_its_delay_with_its_outcome() -> None:
    stop = FakeStop()
    delayed = DelayedStop(stop, 0.05)
    delayed.schedule()
    assert delayed.outcome().pending
    settle(delayed)
    outcome = delayed.outcome()
    assert stop.calls == 1 and outcome.error is None
    assert outcome.stopped is not None and outcome.stopped.session_id == "s1"


def test_taken_back_within_its_delay_nothing_stops() -> None:
    stop = FakeStop()
    delayed = DelayedStop(stop, 0.1)
    delayed.schedule()
    assert delayed.cancel()
    time.sleep(0.2)
    assert stop.calls == 0 and not delayed.outcome().pending


def test_the_menu_bar_stops_at_once_during_the_delay_and_nothing_is_left_pending() -> None:
    stop = FakeStop()
    delayed = DelayedStop(stop, 0.2)
    delayed.schedule()
    assert delayed.stop_now().session_id == "s1"
    time.sleep(0.3)  # the delay passes: no second stop
    outcome = delayed.outcome()
    assert stop.calls == 1 and not outcome.pending and outcome.stopped is not None


def test_a_stop_under_way_cannot_be_taken_back_and_is_waited_for_not_raced() -> None:
    release = threading.Event()
    stop = FakeStop(slow=release)
    delayed = DelayedStop(stop, 0.01)
    delayed.schedule()
    assert stop.started.wait(5)
    assert not delayed.cancel()  # too late: the page is told, never a silent resume
    result: list[capture.StopResult] = []
    menu_bar = threading.Thread(target=lambda: result.append(delayed.stop_now()))
    menu_bar.start()
    release.set()
    menu_bar.join(5)
    assert stop.calls == 1 and result[0].session_id == "s1"
    settle(delayed)


def test_a_failed_stop_is_said_until_one_succeeds() -> None:
    delayed = DelayedStop(FakeStop(fails=True), 0.01)
    delayed.schedule()
    settle(delayed)
    assert delayed.outcome().error == "Le disque est plein."
    delayed._stop = FakeStop()  # type: ignore[assignment]  # the disk freed, stopped again
    delayed.stop_now()
    assert delayed.outcome().error is None


def test_the_service_stopping_waits_for_a_stop_under_way() -> None:
    release = threading.Event()
    stop = FakeStop(slow=release)
    delayed = DelayedStop(stop, 0.01)
    delayed.schedule()
    assert stop.started.wait(5)
    threading.Timer(0.1, release.set).start()
    delayed.shutdown()  # returns once the files are closed
    assert not delayed.outcome().pending


def test_a_delay_still_running_is_dropped_when_the_service_stops() -> None:
    stop = FakeStop()
    delayed = DelayedStop(stop, 0.1)
    delayed.schedule()
    delayed.shutdown()
    time.sleep(0.2)
    assert stop.calls == 0  # the recorder closes the recording itself


def test_two_stops_from_threads_that_stay_alive_wait_for_the_stop_not_for_a_thread() -> None:
    # A web server keeps its threads: waiting for one to end would never return.
    release = threading.Event()
    stay = threading.Event()
    stop = FakeStop(slow=release)
    delayed = DelayedStop(stop, 10)
    results: list[capture.StopResult] = []

    def menu_bar() -> None:
        results.append(delayed.stop_now())
        stay.wait(5)  # the pool's thread lives on

    first = threading.Thread(target=menu_bar, daemon=True)
    first.start()
    assert stop.started.wait(5)
    second = threading.Thread(target=menu_bar, daemon=True)
    second.start()
    time.sleep(0.05)
    release.set()
    deadline = time.monotonic() + 2
    while len(results) < 2:
        assert time.monotonic() < deadline, "the second stop waited for a thread"
        time.sleep(0.01)
    assert stop.calls == 1 and [r.session_id for r in results] == ["s1", "s1"]
    stay.set()


def test_a_stop_that_failed_is_said_to_whoever_waited_never_an_older_one() -> None:
    delayed = DelayedStop(FakeStop(), 10)
    delayed.stop_now()  # an older session's stop, done
    release = threading.Event()
    delayed._stop = FakeStop(fails=True, slow=release)  # type: ignore[assignment]
    failures: list[str] = []

    def stop_and_catch() -> None:
        try:
            delayed.stop_now()
        except capture.RecordingError as exc:
            failures.append(str(exc))

    first = threading.Thread(target=stop_and_catch)
    first.start()
    time.sleep(0.05)
    second = threading.Thread(target=stop_and_catch)
    second.start()
    time.sleep(0.05)
    release.set()
    first.join(5)
    second.join(5)
    assert len(failures) == 2 and all("plein" in f for f in failures)
    assert delayed.outcome().error is not None


def test_a_stop_asked_twice_finds_nothing_to_stop_and_says_no_problem() -> None:
    delayed = DelayedStop(FakeStop(), 10)
    delayed.stop_now()

    def nothing() -> capture.StopResult:
        raise capture.NotRecordingError("Aucun enregistrement en cours.")

    delayed._stop = nothing  # type: ignore[assignment]
    with pytest.raises(capture.NotRecordingError):
        delayed.stop_now()  # the menu bar is told, as before
    outcome = delayed.outcome()
    assert outcome.error is None and outcome.stopped is not None
