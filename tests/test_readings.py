"""The last half hour of each machine's polls (firmware/readings.py): what a graph on the
deck is drawn from. Each poll that lands in ``devices.notify_status`` is kept, at most two
a second; a poll of nothing (offline) is not; a board's port forgotten forgets them."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from apothecary.firmware import devices, readings
from apothecary.firmware.models import Heater, PrinterStatus, Spindle

NOW = datetime(2026, 11, 25, 12, 0, 0, tzinfo=timezone.utc)
PORT = "/dev/ttyFAKE9"


@pytest.fixture(autouse=True)
def _fresh():
    readings.reset()
    yield
    readings.reset()


def _poll(ago, port=PORT, **kw):
    kw.setdefault("hotends", [Heater(actual=200 - ago, target=215)])
    kw.setdefault("bed", Heater(actual=60, target=60))
    return PrinterStatus(port=port, polled_at=NOW - timedelta(seconds=ago), **kw)


def test_a_poll_is_kept_as_the_numbers_a_graph_draws():
    readings.record(_poll(10))
    kept = readings.history(PORT, now=NOW.timestamp())
    assert len(kept) == 1
    one = kept[0]
    assert (one.hotend, one.bed, one.spindle_rpm) == ((190.0, 215.0), (60.0, 60.0), None)
    assert one.at == pytest.approx((NOW - timedelta(seconds=10)).timestamp())
    router = PrinterStatus(
        port="/dev/ttyR",
        polled_at=NOW,
        dialect="grbl",
        spindle=Spindle(rpm=9000, on=True),
        feed=600,
    )
    readings.record(router)
    (cut,) = readings.history("/dev/ttyR", now=NOW.timestamp())
    assert (cut.spindle_rpm, cut.feed, cut.hotend) == (9000.0, 600, None)
    readings.record(
        router.model_copy(
            update={"polled_at": NOW + timedelta(seconds=1), "spindle": Spindle(rpm=9000, on=False)}
        )
    )
    assert readings.history("/dev/ttyR", now=NOW.timestamp() + 1)[-1].spindle_rpm == 0.0


def test_two_polls_within_half_a_second_keep_one_and_an_older_one_none():
    """Two pages polling at once keep one reading; a held reading handed on again, or one
    older than the newest, is kept once."""
    readings.record(_poll(10))
    readings.record(_poll(9.8))  # 0.2 s after: the first stands
    readings.record(_poll(10))  # the same again
    readings.record(_poll(20))  # older than the newest
    readings.record(_poll(9))
    kept = readings.history(PORT, now=NOW.timestamp())
    assert [round(NOW.timestamp() - r.at, 1) for r in kept] == [10.0, 9.0]


def test_a_poll_of_nothing_is_not_kept_and_a_window_takes_the_newest():
    readings.record(_poll(5, state="offline"))
    assert readings.history(PORT, now=NOW.timestamp()) == []
    for ago in (900, 500, 100, 1):
        readings.record(_poll(ago))
    assert len(readings.history(PORT, now=NOW.timestamp())) == 4
    assert [
        round(NOW.timestamp() - r.at) for r in readings.history(PORT, 600, now=NOW.timestamp())
    ] == [500, 100, 1]
    assert readings.history(None) == [] and readings.history("/dev/nothing") == []


def test_what_is_older_than_half_an_hour_is_let_go():
    readings.record(_poll(readings.KEPT_S + 60))
    readings.record(_poll(30))
    kept = readings.history(PORT, window_s=10 * readings.KEPT_S, now=NOW.timestamp())
    assert [round(NOW.timestamp() - r.at) for r in kept] == [30]


def test_every_poll_that_lands_is_kept_and_a_port_forgotten_forgets_them():
    """``devices.notify_status`` is where every poll lands, whoever made it; a port
    forgotten (its board unplugged, another in its place) has no history."""
    devices.notify_status(_poll(4))
    devices.notify_status(_poll(2))
    assert len(readings.history(PORT, now=NOW.timestamp())) == 2
    devices.forget_port(PORT)
    assert readings.history(PORT, now=NOW.timestamp()) == []
