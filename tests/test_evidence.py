"""The evidence log's pieces, apart from the server: the observation format, a
poll said as observations, what the collector writes, and the view's document."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from apothecary.evidence import log, printers, view
from apothecary.evidence.observation import Observation, Origin, Ref
from apothecary.firmware.models import Heater, PrinterStatus

T0 = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
PIN = printers.Pin("garage", "printer_1.frame_system.mainboard", "printer_1", "A106ZTEU")


def poll(at=T0, state="printing", hotend=210.0, bed=60.0, progress=0.42, z=3.6):
    return PrinterStatus(
        port="/dev/ttyUSB0",
        polled_at=at,
        state=state,
        hotends=[Heater(actual=hotend, target=210.0)],
        bed=Heater(actual=bed, target=60.0),
        position={"x": 110.0, "y": 98.0, "z": z, "e": 412.0},
        endstops={"x_min": "open", "y_min": "TRIGGERED", "filament": "TRIGGERED"},
        filament_present=True,
        sd_progress=progress,
        raw=["ok T:210 /210 B:60 /60"],
    )


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def said(observations):
    return {(o.subject, o.property): o.value for o in observations}


def test_an_observation_is_tightened_never_relaxed():
    base = dict(
        subject="garage:printer_1",
        property="state",
        value="idle",
        origin=Origin(kind="measured", by="a poll"),
        at=T0,
        recorded_at=T0,
    )
    Observation(**base)
    Observation(**{**base, "value": None, "why": "the poll timed out"})
    for bad in (
        {"value": None},  # unread, and no why
        {"why": "and a value too"},
        {"property": "mood"},
        {"subject": "printer_1"},  # no space
        {"at": T0.replace(tzinfo=None)},
        {"origin": {"kind": "rumoured", "by": "someone"}},
        {"colour": "red"},  # a field the format does not have
    ):
        with pytest.raises(ValidationError):
            Observation(**{**base, **bad})


def test_a_poll_is_said_of_its_board_and_the_printer_it_drives():
    out = printers.observations_of(poll(), PIN, "A106ZTEU", now=T0)
    values = said(out)
    assert values[("garage:printer_1.frame_system.mainboard", "present")] is True
    assert values[("garage:printer_1", "state")] == "printing"
    assert values[("garage:printer_1", "progress")] == 0.42
    assert values[("garage:printer_1#heater:hotend0", "temperature")] == 210.0
    assert values[("garage:printer_1#heater:bed", "target")] == 60.0
    assert values[("garage:printer_1#endstop:y_min", "endstop")] == "triggered"
    assert ("garage:printer_1#endstop:filament", "endstop") not in values  # it is ``filament``
    assert values[("garage:printer_1", "filament")] is True
    for each in out:
        assert each.origin.kind == "measured"
        assert Ref(kind="poll", id=printers.poll_id(poll())) in each.evidence
        assert Ref(kind="pin", id="garage:printer_1.frame_system.mainboard") in each.evidence


def test_an_unpinned_port_is_a_sighting_and_an_offline_one_says_only_that():
    out = printers.observations_of(poll(), None, "A106ZTEU", now=T0)
    assert {o.subject.split("#")[0] for o in out} == {"usb:A106ZTEU"}
    gone = printers.observations_of(poll(state="offline"), PIN, "A106ZTEU", now=T0)
    assert said(gone) == {
        ("garage:printer_1.frame_system.mainboard", "present"): False,
        ("garage:printer_1", "state"): "offline",
    }


def test_the_collector_writes_what_changed_and_says_present_once_a_minute(state_dir):
    collector = printers.Collector()

    def lines(kind):
        folder = state_dir / "evidence" / "garage" / kind
        return sum(len(f.read_text().splitlines()) for f in folder.glob("*.jsonl"))

    first = collector.take(poll(), [PIN], "A106ZTEU")
    everything = lines(log.OBSERVATIONS)
    assert lines(log.POLLS) == 1 and everything > 5
    # Under each tolerance: nothing.
    collector.take(poll(T0 + timedelta(seconds=2), hotend=210.6, z=3.62), [PIN], "A106ZTEU")
    assert lines(log.OBSERVATIONS) == everything and lines(log.POLLS) == 1
    # Past one: that one, and its poll.
    collector.take(poll(T0 + timedelta(seconds=4), hotend=212.0), [PIN], "A106ZTEU")
    assert lines(log.OBSERVATIONS) == everything + 1 and lines(log.POLLS) == 2
    # A minute on, nothing moved: the board is said present again, and only that.
    collector.take(poll(T0 + timedelta(seconds=70), hotend=212.0), [PIN], "A106ZTEU")
    assert lines(log.OBSERVATIONS) == everything + 2
    assert first.startswith("20261031T120000.000")


def test_the_view_says_how_each_value_is_known_and_what_changed(state_dir):
    collector = printers.Collector()
    collector.take(poll(), [PIN], "A106ZTEU")
    collector.take(poll(T0 + timedelta(seconds=30), state="idle", progress=None), [PIN], "A106ZTEU")
    seen = log.document("garage", at=T0 + timedelta(seconds=40), since=T0 - timedelta(minutes=5))
    state = next(
        p
        for s in seen["subjects"]
        if s["subject"] == "garage:printer_1"
        for p in s["properties"]
        if p["property"] == "state"
    )
    assert state["value"] == "idle" and state["current"] and state["standing"] == "one kind"
    [moved] = [t for t in seen["transitions"] if t["property"] == "state"]
    assert (moved["from"], moved["to"]) == ("printing", "idle")
    assert moved["before"][0]["id"] != moved["after"][0]["id"]  # each side opens its own poll
    temperatures = seen["series"]["garage:printer_1#heater:hotend0|temperature"]
    assert temperatures[0][1] == 210.0 and temperatures[0][2] == printers.poll_id(poll())
    # Long after, nobody asking: the value is last known, not current.
    later = log.document("garage", at=T0 + timedelta(hours=2))
    state = next(p for s in later["subjects"] for p in s["properties"] if p["property"] == "state")
    assert state["value"] == "idle" and not state["current"]


def test_two_kinds_of_source_agree_or_disagree():
    def obs(kind, value):
        return Observation(
            subject="garage:printer_1",
            property="state",
            value=value,
            origin=Origin(kind=kind, by=kind),
            at=T0,
            recorded_at=T0,
        )

    for values, standing in ((("idle", "idle"), "agreed"), (("idle", "printing"), "disagreed")):
        doc = view.document(
            "garage",
            [obs("measured", values[0]), obs("stated", values[1])],
            [],
            T0,
            T0 - timedelta(hours=1),
        )
        [prop] = doc["subjects"][0]["properties"]
        assert prop["standing"] == standing and len(prop["sources"]) == 2


def test_a_line_that_is_not_json_is_counted_not_read(state_dir):
    printers.Collector().take(poll(), [PIN], "A106ZTEU")
    day = state_dir / "evidence" / "garage" / log.OBSERVATIONS / "2026-10-31.jsonl"
    with day.open("a") as out:
        out.write('{"half a line\n')
    assert log.document("garage", at=T0 + timedelta(seconds=1))["unreadable"] == 1
