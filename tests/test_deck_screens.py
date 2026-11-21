"""The deck's screens (firmware/deck_screens.py), each a pure function of what it is
given: the swipe read from a touch, the order a swipe walks and where it stops, and what
the Progress and Status screens say of a job and of a machine's last poll. Nothing here
has a deck, a machine or a port."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from apothecary import jobs
from apothecary.firmware import deck
from apothecary.firmware import deck_screens as screens
from apothecary.firmware.models import Heater, PrinterStatus, Spindle

NOW = datetime(2026, 11, 16, 12, 0, 0, tzinfo=timezone.utc)


DECK_JS = Path(__file__).resolve().parents[1] / "apothecary" / "static" / "widgets" / "deck.js"


def test_the_deck_window_sends_a_swipe_where_the_server_reads_one():
    """The Deck window sends a drag along its strip only when it is a swipe, by its own
    SWIPE_PX of a strip of STRIP pixels: the server's figures (SWIPE_MIN_PX, and the
    strip's size), so a drag the window sends is one the server reads as a swipe."""
    js = DECK_JS.read_text(encoding="utf-8")
    swipe = re.search(r"const SWIPE_PX = (\d+);", js)
    strip = re.search(r"STRIP = \[(\d+), (\d+)\]", js)
    assert swipe and strip, "deck.js no longer says SWIPE_PX or STRIP as this test reads them"
    assert int(swipe.group(1)) == screens.SWIPE_MIN_PX
    assert (int(strip.group(1)), int(strip.group(2))) == deck.STRIP_SIZE


def _drag(x, x_out, y=50, y_out=50):
    return {"kind": "drag", "x": x, "y": y, "x_out": x_out, "y_out": y_out}


def _job(progress=0.42, stage="printing", outcome="running", ago=754, part=None, reason=None):
    started = NOW - timedelta(seconds=ago)
    return jobs.Job(
        id="j1",
        kind="print",
        machine=jobs.JobMachine(kind="printer", port="/dev/ttyFAKE1"),
        part=jobs.JobPart(path="p", name=part) if part else None,
        input=jobs.JobInput(name="benchy.gcode"),
        started_at=started,
        finished_at=None if outcome == "running" else NOW,
        outcome=outcome,
        reason=reason,
        progress=progress,
        detail={"stage": stage},
    )


def _status(**kw):
    kw.setdefault("polled_at", NOW)
    return PrinterStatus(port="/dev/ttyFAKE1", **kw)


# --- the swipe, read in one place --------------------------------------------------------


@pytest.mark.parametrize(
    ("touch", "want"),
    [
        (_drag(700, 100), screens.FORWARD),  # a finger moving left turns the page on
        (_drag(100, 700), screens.BACK),
        (_drag(500, 300), screens.FORWARD),  # exactly the threshold
        (_drag(500, 301), 0),  # a pixel short
        (_drag(400, 410), 0),  # a slip
        (_drag(700, 300, y=0, y_out=100), screens.FORWARD),  # a slanting finger still swipes
        ({"kind": "short", "x": 400, "y": 50}, 0),  # a tap is not a swipe
        ({"kind": "long", "x": 400, "y": 50}, 0),
        ({"kind": "drag", "x": 700, "y": 50}, 0),  # no end point: nothing to read
        ("drag", 0),
        (None, 0),
    ],
)
def test_a_swipe_is_a_drag_far_enough_along_the_strip(touch, want):
    assert screens.swipe_of(touch) == want


# --- the order, and its ends ----------------------------------------------------------------


def test_a_swipe_walks_the_screens_in_order_and_stops_at_each_end():
    shown = screens.Screens(screens.screens_for("printer"))
    assert (shown.current, shown.position) == ("knobs", "1/3")
    assert shown.swipe(screens.BACK) is False and shown.current == "knobs"  # nothing before
    assert shown.swipe(screens.FORWARD) and shown.current == "progress"
    assert shown.swipe(screens.FORWARD) and (shown.current, shown.position) == ("status", "3/3")
    assert shown.swipe(screens.FORWARD) is False and shown.current == "status"  # nothing after
    assert shown.swipe(screens.BACK) and shown.current == "progress"


def test_a_screen_is_brought_forward_by_name_and_an_unknown_one_is_refused():
    shown = screens.Screens()
    assert shown.show("status") and shown.current == "status"
    assert shown.show("nothing") is False and shown.current == "status"
    shown.reorder(("knobs", "status"))
    assert shown.current == "status"  # kept when it is still there
    shown.reorder(("knobs",))
    assert shown.current == "knobs"


# --- Progress ----------------------------------------------------------------------------------


def test_progress_of_a_running_print_names_the_file_the_percent_the_stage_and_the_time_so_far():
    strip = screens.progress_strip("printer_1", _job(), None, NOW, "2/3")
    assert strip.text == "benchy.gcode · 42%"
    assert strip.small == "printer_1 · printing · elapsed 12:34 · 2/3"
    assert (strip.bar, strip.colour) == (0.42, "blue")
    assert "remaining" not in strip.small and "left" not in strip.small  # no record carries one


def test_progress_names_the_part_when_the_job_makes_one():
    assert screens.progress_strip("p", _job(part="Bracket"), None, NOW, "2/3").text.startswith(
        "Bracket · "
    )


def test_progress_of_a_job_held_is_amber_and_a_long_name_is_clipped():
    held = screens.progress_strip("p", _job(stage="paused", part="x" * 60), None, NOW, "2/3")
    assert held.colour == "amber" and "paused" in held.small
    assert len(held.text.split(" · ")[0]) == screens.NAME_MAX


@pytest.mark.parametrize(
    ("outcome", "colour", "word", "reason"),
    [
        ("done", "green", "done", None),
        ("cancelled", "amber", "cancelled", "stopped from the page"),
        ("failed", "red", "failed", "the board stopped answering"),
    ],
)
def test_progress_of_an_ended_job_says_how_it_ended_until_a_touch(outcome, colour, word, reason):
    strip = screens.progress_strip("p", _job(0.9, outcome=outcome, reason=reason), None, NOW, "2/3")
    assert strip.colour == colour and f"· {word}" in strip.small
    assert "after 12:34" in strip.small and "tap to clear" in strip.small
    assert strip.bar == 0.9
    assert (reason is None) or reason in strip.small


def test_an_ended_job_s_reason_does_not_say_its_end_twice():
    """A host's cancel is recorded with the word the strip says before it: said once."""
    job = _job(0.3, outcome="cancelled", reason="cancelled; heaters and fan off, motors free")
    strip = screens.progress_strip("p", job, None, NOW, "2/3")
    assert "· cancelled (heaters and fan off, motors free) after" in strip.small, strip.small
    other = screens.progress_strip(
        "p", _job(0.3, outcome="failed", reason="the board stopped"), None, NOW, "2/3"
    )
    assert "· failed (the board stopped) after" in other.small


def test_progress_with_no_job_but_a_card_print_reads_the_card_and_with_neither_says_so():
    card = _status(sd_printing=True, sd_progress=0.5, print_time_s=125)
    strip = screens.progress_strip("printer_1", None, card, NOW, "2/3")
    assert strip.text == "card print · 50%" and "elapsed 2:05" in strip.small and strip.bar == 0.5
    idle = screens.progress_strip("printer_1", None, _status(), NOW, "2/3")
    assert idle.text == "printer_1 · no job" and idle.bar is None and idle.colour == "grey"


def test_a_clock_is_minutes_and_seconds_and_from_the_hour_hours():
    assert [screens.clock(s) for s in (0, 5, 65, 3599, 3600, 7325)] == [
        "0:00",
        "0:05",
        "1:05",
        "59:59",
        "1:00:00",
        "2:02:05",
    ]


# --- Status ------------------------------------------------------------------------------------


def test_status_of_a_printer_is_its_state_its_temperatures_and_what_it_asks_for():
    status = _status(
        state="printing",
        hotends=[Heater(actual=204.6, target=210)],
        bed=Heater(actual=60, target=60),
    )
    strip = screens.status_strip("printer_1", "printer", status, NOW, "3/3")
    assert strip.text == "printer_1 · printing" and strip.colour == "green"
    assert strip.small == "hotend 205/210 · bed 60/60 · 3/3"
    cold = screens.status_strip(
        "printer_1",
        "printer",
        _status(hotends=[Heater(actual=21, target=0)], bed=None, todo=["load the filament"]),
        NOW,
        "3/3",
    )
    assert (
        cold.small == "hotend 21 off · bed - · load the filament · 3/3" and cold.colour == "amber"
    )


def test_status_of_a_router_is_its_spindle_and_feed_and_its_alarm_first_thing_to_do():
    status = _status(
        state="alarm",
        dialect="grbl",
        spindle=Spindle(rpm=8000, target=8000, on=True),
        feed=800,
        alarm=1,
        alarm_text="Hard limit",
        todo=["Unlock it ($X), then home"],
    )
    strip = screens.status_strip("cnc_router", "router", status, NOW, "3/3")
    assert strip.text == "cnc_router · alarm" and strip.colour == "red"
    assert strip.small == "spindle 8000 rpm · feed 800 · Unlock it ($X), then home · 3/3"
    only_alarm = _status(state="alarm", alarm=9, alarm_text="Homing required", dialect="grbl")
    assert "Homing required" in screens.status_strip("r", "router", only_alarm, NOW, "3/3").small


def test_status_says_how_old_a_reading_is_and_when_there_is_none():
    old = _status(polled_at=NOW - timedelta(seconds=95), hotends=[Heater(actual=30)])
    assert "read 1:35 ago" in screens.status_strip("p", "printer", old, NOW, "3/3").small
    fresh = _status(polled_at=NOW - timedelta(seconds=3))
    assert "ago" not in screens.status_strip("p", "printer", fresh, NOW, "3/3").small
    none = screens.status_strip("printer_1", "printer", None, NOW, "3/3")
    assert none.text == "printer_1 · no reading" and none.colour == "grey"


def test_the_knobs_of_a_machine_a_job_holds_say_jogs_are_refused_in_the_servers_words():
    words = "/dev/ttyFAKE1: a print holds the port (printing)"
    printer = screens.held_strip("printer_1", "printer", words, "1/3")
    assert printer.colour == "amber" and printer.small.startswith(words)
    assert "jogs refused" in printer.small and "no knob moves it" in printer.small
    assert "knob 4 still turns the spindle" in screens.held_strip("r", "router", words, "1/3").small


def test_status_says_the_jobs_stage_where_a_job_holds_the_port():
    """A poll made while the host streams a job carries the job and says the busy word
    over the card's idle state, whatever the job's stage: Status says the stage -- a
    print paused is paused, amber as Progress draws it -- and a poll with no job still
    says the machine's own state."""
    paused = _status(
        state="printing",
        hotends=[Heater(actual=200, target=200)],
        job={"kind": "print", "port": "/dev/ttyFAKE1", "stage": "paused"},
    )
    strip = screens.status_strip("printer_1", "printer", paused, NOW, "3/3")
    assert strip.text == "printer_1 · paused" and strip.colour == "amber"
    streaming = paused.model_copy(update={"job": {"kind": "print", "stage": "printing"}})
    assert screens.status_strip("p", "printer", streaming, NOW, "3/3").colour == "green"
    cut = _status(state="running", dialect="grbl", job={"kind": "cut", "stage": "running"})
    assert screens.status_strip("r", "router", cut, NOW, "3/3").text == "r · running"


def test_the_knobs_words_while_held_are_one_line_the_strip_and_the_window_both_say():
    words = "/dev/ttyFAKE1: a print holds the port (paused)"
    assert screens.held_strip("p", "printer", words, "1/3").small == screens.held_words(
        "printer", words
    )
    assert screens.held_words("printer", words) == f"{words} · jogs refused, no knob moves it"
