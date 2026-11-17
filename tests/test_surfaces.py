"""The surfaces (apothecary/surfaces.py, routes/surfaces.py): each owner declares what it
keeps, in its own frame; one read, one stream that relays the changes the server already
learns of and asks nothing of any port; and one door for what the family's members
found."""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timedelta, timezone

import pytest
import serial
from fastapi.testclient import TestClient

from apothecary import jobs, projector, sites, surfaces
from apothecary.api import app
from apothecary.family import hub
from apothecary.firmware import devices, gcode
from apothecary.firmware.models import PrinterStatus

PORT = "/dev/ttyFAKE1"  # the scripted arduino-cli's unmatched board
BOARD = "printer_1.frame_system.mainboard"
OWNED = {
    "carlos_holds": ("none", "apothecary.routes.wiring"),
    "contributed": ("none", "apothecary.surfaces"),
    "jobs": ("none", "apothecary.jobs"),
    "lighting": ("none", "apothecary.routes.lighting"),
    "machine_status": ("bed_mm", "apothecary.firmware.devices"),
    "pictures": ("none", "apothecary.routes.pictures"),
    "projector": ("bed_mm", "apothecary.routes.projector"),
    "whiteboard_marks": ("picture_fractions", "apothecary.routes.marks"),
}

client = TestClient(app)


def _events(text: str) -> list:
    """The stream's frames as (event, data), its comments left out."""
    found = []
    for block in text.strip().split("\n\n"):
        lines = [line for line in block.splitlines() if not line.startswith(":")]
        if not lines:
            continue
        said = dict(line.split(": ", 1) for line in lines)
        found.append((said["event"], json.loads(said["data"])))
    return found


def _changes(text: str, surface: str) -> list:
    return [data for event, data in _events(text) if event == "change" and data["surface"] == surface]


@pytest.fixture
def kept(monkeypatch):
    """No poll kept from another test, and the garage as built."""
    monkeypatch.setattr(devices, "_LAST_STATUS", {})
    sites.store.reset("garage")
    yield
    sites.store.reset("garage")


def _poll(port: str = PORT, **fields) -> PrinterStatus:
    return devices.notify_status(
        PrinterStatus(port=port, polled_at=datetime.now(timezone.utc), **fields)
    )


def test_each_surface_is_declared_by_its_owner_in_its_frame():
    listed = client.get("/surfaces").json()
    assert listed["format"] == "apothecary.surfaces/1"
    assert set(listed["frames"]) == {"site_mm", "bed_mm", "picture_fractions", "none"}
    by_name = {s["name"]: s for s in listed["surfaces"]}
    assert {n: (s["frame"], s["owner"]) for n, s in by_name.items()} == OWNED
    assert all(s["tells"] for s in by_name.values())
    assert by_name["projector"]["needs"] == ["site", "path"]
    assert by_name["whiteboard_marks"]["needs"] == ["site", "view"]


def test_a_name_is_one_owner_s_and_a_frame_is_one_of_four():
    taken = surfaces.Surface(name="jobs", frame="none", about="", snapshot=dict, owner="elsewhere")
    with pytest.raises(ValueError, match="already apothecary.jobs's surface"):
        surfaces.register(taken)
    with pytest.raises(ValueError, match="is no frame"):
        surfaces.register(surfaces.Surface(name="x", frame="inches", about="", snapshot=dict))


def test_a_surface_is_read_with_the_words_it_takes(kept):
    assert client.get("/surfaces/machine_status").json() == {
        "surface": "machine_status",
        "frame": "bed_mm",
        "words": {},
        "snapshot": {},
    }
    _poll(state="printing", position={"x": 1.0, "y": 2.0, "z": 3.0})
    read = client.get("/surfaces/machine_status", params={"port": PORT}).json()["snapshot"]
    assert read[PORT]["state"] == "printing" and "raw" not in read[PORT]
    # The projector's surface is its answer, read one way.
    through = client.get("/surfaces/projector", params={"site": "garage", "path": "printer_1"})
    direct = client.get("/sites/garage/machines/printer_1/projector").json()
    assert through.status_code == 200
    got = through.json()["snapshot"]
    assert {k: v for k, v in got.items() if k != "made_at"} == {
        k: v for k, v in direct.items() if k != "made_at"
    }
    unasked = client.get("/surfaces/projector", params={"site": "garage"})
    assert unasked.status_code == 422 and "read for a path" in unasked.json()["detail"]
    strange = client.get("/surfaces/jobs", params={"colour": "red"})
    assert strange.status_code == 422 and "not asked by colour" in strange.json()["detail"]
    assert client.get("/surfaces/weather").status_code == 404
    assert client.get("/surfaces/events", params={"names": "weather"}).status_code == 404


def test_nobody_following_a_surface_builds_nothing_of_a_change():
    made = []
    assert not surfaces.listening("jobs")
    assert surfaces.changed("jobs", key="j", body=lambda: made.append(1)) is None
    assert made == []

    async def follow():
        following = surfaces.subscribe(["jobs"])
        try:
            assert surfaces.listening("jobs") and not surfaces.listening("pictures")
            event = surfaces.changed("jobs", key="j", body=lambda: {"made": made.append(1)})
            assert event["surface"] == "jobs" and event["key"] == "j" and made == [1]
            got, missed = await following.next(1.0)
            assert [e["seq"] for e in got] == [event["seq"]] and missed == 0
        finally:
            following.close()
        assert not surfaces.listening("jobs")

    asyncio.run(follow())


def test_a_reader_that_falls_behind_is_told_how_many_it_missed(monkeypatch):
    monkeypatch.setattr(surfaces, "WAITING_MOST", 3)

    async def follow():
        following = surfaces.subscribe(["pictures"])
        try:
            for n in range(5):
                surfaces.changed("pictures", key=str(n))
            got, missed = await following.next(1.0)
            return [e["key"] for e in got], missed
        finally:
            following.close()

    assert asyncio.run(follow()) == (["2", "3", "4"], 2)


def test_a_stream_dropped_before_or_after_its_first_frame_leaves_nobody_following():
    """A reader that goes before the stream's first frame is never a follower, and one
    that goes after it is let go: no follower is left for whom every change would be
    made."""
    from apothecary.routes.surfaces import surface_events

    class Reader:
        async def is_disconnected(self):
            return False

    async def opened_then_dropped():
        before = len(surfaces._FOLLOWING)
        answer = await surface_events(Reader(), names="projector", seconds=None)
        assert len(surfaces._FOLLOWING) == before and not surfaces.listening("projector")
        frames = answer.body_iterator
        assert "event: surfaces" in await frames.__anext__()
        assert surfaces.listening("projector")
        await frames.aclose()
        assert len(surfaces._FOLLOWING) == before and not surfaces.listening("projector")

    asyncio.run(opened_then_dropped())


@pytest.fixture
def held_link(monkeypatch):
    """A link held open to a simulated printer, every byte written to it counted, and
    every way past it to a port -- a poll, a serial port opened -- counted too: the
    stream could poll this link, and must not."""
    written: list = []

    class Counted(gcode.SimulatedPrinter):
        def write(self, data: bytes) -> None:
            written.append(data)
            super().write(data)

    links = gcode.PrinterLinks(factory=Counted)
    monkeypatch.setattr(gcode, "_LINKS", links)
    links.open(PORT, 115200, settle=False)
    asked: list = []
    monkeypatch.setattr(devices, "printer_status", lambda *a, **k: asked.append(("poll", a)))

    def opened(*args, **kwargs):
        asked.append(("serial", args))
        raise AssertionError("a serial port was opened")

    monkeypatch.setattr(serial, "Serial", opened)
    monkeypatch.setattr(serial, "serial_for_url", opened)
    written.clear()
    yield links, written, asked
    links.stop_all()


# Longer than a page's poll of a machine it follows (the world's and the projector page's,
# every 2 s): a stream that polled on that period would be heard doing it.
LONGER_THAN_A_POLL = 2.6


def test_a_reader_with_nobody_polling_causes_no_serial_traffic(kept, held_link):
    """Following every surface for longer than a page's poll period, with a link held and
    nobody polling it: not a byte is written to the port, no poll is made and no port
    opened -- and a poll someone else makes meanwhile is relayed as it is kept. Reading a
    surface, and the projector's answer, asks the port nothing either."""
    links, written, asked = held_link
    assert links.open_ports == [PORT]
    someone = threading.Timer(0.3, lambda: _poll(state="printing"))
    someone.start()
    text = client.get("/surfaces/events", params={"seconds": LONGER_THAN_A_POLL}).text
    someone.join()
    assert written == [] and asked == []
    first = _events(text)[0]
    assert first == ("surfaces", {"following": surfaces.names()})
    relayed = _changes(text, "machine_status")
    assert [(c["key"], c["body"]["state"]) for c in relayed] == [(PORT, "printing")]
    assert relayed[0]["frame"] == "bed_mm" and relayed[0]["format"] == surfaces.EVENT
    # Quiet: only the hello, and nothing more.
    quiet = client.get("/surfaces/events", params={"seconds": LONGER_THAN_A_POLL}).text
    assert _events(quiet) == [first]
    assert written == [] and asked == []
    for read in (
        ("/surfaces/machine_status", {"port": PORT}),
        ("/surfaces/projector", {"site": "garage", "path": "printer_1"}),
        ("/sites/garage/machines/printer_1/projector", {}),
    ):
        assert client.get(read[0], params=read[1]).status_code == 200, read
    assert written == [] and asked == []


def test_a_poll_of_a_machine_s_board_moves_its_projector_and_a_job_is_told(
    fake_arduino_cli, kept, held_link
):
    """The board pinned under printer_1, polled by someone else: the projector's change
    carries what moves and its picture's key, not the toolpath. A job begun and ended on
    it is told as the jobs' changes. Nothing is asked of the port."""
    _, written, asked = held_link
    client.put(f"/sites/garage/nodes/{BOARD}/device", json={"identity": PORT})
    at = datetime.now(timezone.utc)
    job = jobs.Job(
        id=jobs.new_id(at, PORT),
        kind="print",
        machine=jobs.JobMachine(kind="printer", port=PORT, path=BOARD),
        site="garage",
        input=jobs.JobInput(name="cube.gcode", size=40),
        started_at=at,
    )

    def meanwhile():
        _poll(position={"x": 5.0, "y": 70.0, "z": 0.2}, tool_position={"x": 5.0, "y": 70.0, "z": 0.2})
        jobs.begin(job, live=lambda: job)
        jobs.end(job.model_copy(update={"outcome": "done", "finished_at": at + timedelta(seconds=1)}))

    try:
        someone = threading.Timer(0.3, meanwhile)
        someone.start()
        text = client.get(
            "/surfaces/events", params={"names": "projector,jobs", "seconds": 1.2}
        ).text
        someone.join()
    finally:
        client.delete(f"/sites/garage/nodes/{BOARD}/device")
    moved = _changes(text, "projector")
    assert moved and {c["key"] for c in moved} == {"garage/printer_1"}
    body = moved[0]["body"]
    assert set(body) == {"key", "moving"} and moved[0]["frame"] == "bed_mm"
    assert body["moving"]["tool"] == [5.0, 0.0] and body["moving"]["bed_offset"] == -70.0
    told = _changes(text, "jobs")
    assert [(c["key"], c["body"]["outcome"]) for c in told] == [(job.id, "running"), (job.id, "done")]
    assert "log" not in told[0]["body"]
    assert not _changes(text, "machine_status")  # not named, not sent
    assert written == [] and asked == []


@pytest.fixture
def members(tmp_path, monkeypatch):
    """A family whose table names alfred and joe as members a page reads."""
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path))
    (tmp_path / hub.TABLE).write_text(json.dumps({"pull": ["alfred", "joe"]}), encoding="utf-8")
    hub.close()
    yield tmp_path
    hub.close()


def _found(by="alfred", surface="projector", **more) -> dict:
    return {
        "by": by,
        "at": "2026-11-16T20:15:00+00:00",
        "surface": surface,
        "frame": "bed_mm",
        "key": "garage/printer_1",
        "body": {"saw": "the first layer lifting at the front left", "where": [12.0, 8.5]},
        **more,
    }


def test_a_member_s_observation_is_kept_and_relayed(members):
    async def follow():
        following = surfaces.subscribe(["contributed"])
        try:
            kept = await asyncio.to_thread(client.post, "/surfaces/contributed", json=_found())
            got, _ = await following.next(2.0)
            return kept, got
        finally:
            following.close()

    kept, told = asyncio.run(follow())
    assert kept.status_code == 201, kept.text
    said = kept.json()
    assert said["format"] == "apothecary.contributed/1" and said["recorded_at"]
    assert [(e["surface"], e["key"], e["body"]["by"]) for e in told] == [
        ("contributed", "projector", "alfred")
    ]
    client.post("/surfaces/contributed", json=_found(by="joe", surface="jobs", frame="none"))
    every = client.get("/surfaces/contributed").json()["snapshot"]["observations"]
    assert [o["by"] for o in every] == ["joe", "alfred"]
    one = client.get("/surfaces/contributed", params={"surface": "projector"}).json()
    assert [o["body"]["saw"] for o in one["snapshot"]["observations"]] == [
        "the first layer lifting at the front left"
    ]
    on_disk = json.loads((members / "surfaces" / "contributed.json").read_text(encoding="utf-8"))
    assert len(on_disk["observations"]) == 2


def test_only_a_member_writes_and_only_of_a_surface_in_a_frame(members, monkeypatch):
    stranger = client.post("/surfaces/contributed", json=_found(by="mallory"))
    assert stranger.status_code == 403 and "no member of the family's hub" in stranger.text
    nowhere = client.post("/surfaces/contributed", json=_found(surface="weather"))
    assert nowhere.status_code == 404
    assert client.post("/surfaces/contributed", json=_found(frame="inches")).status_code == 422
    huge = _found(body={"saw": "x" * (surfaces.BODY_MOST + 1)})
    assert client.post("/surfaces/contributed", json=huge).status_code == 422
    # A page of another origin cannot write, as it can write nowhere here.
    foreign = {"origin": "https://evil.example", "sec-fetch-site": "cross-site"}
    assert client.post("/surfaces/contributed", json=_found(), headers=foreign).status_code == 403
    monkeypatch.setattr(surfaces, "KEPT", 2)
    for n in range(3):
        client.post("/surfaces/contributed", json=_found(body={"n": n}))
    kept = client.get("/surfaces/contributed").json()["snapshot"]["observations"]
    assert [o["body"]["n"] for o in kept] == [2, 1]


def test_a_calibration_kept_is_told_as_the_projector_s_change(fake_arduino_cli, kept, held_link):
    client.put(f"/sites/garage/nodes/{BOARD}/device", json={"identity": PORT})
    _poll(position={"x": 0.0, "y": 0.0, "z": 0.0}, tool_position={"x": 0.0, "y": 0.0, "z": 0.0})
    body = {
        "bed": [[20, 20], [200, 20], [200, 200], [20, 200]],
        "pixels": [[400, 900], [1500, 880], [1400, 200], [500, 220]],
        "size": [1920, 1080],
    }
    try:

        async def follow():
            following = surfaces.subscribe(["projector"])
            try:
                was = await asyncio.to_thread(
                    client.get, "/sites/garage/machines/printer_1/projector"
                )
                put = await asyncio.to_thread(
                    client.put, "/sites/garage/machines/printer_1/projector", json=body
                )
                got, _ = await following.next(2.0)
                return was.json(), put.json(), got
            finally:
                following.close()

        was, put, told = asyncio.run(follow())
    finally:
        projector.clear("garage", "printer_1")
        client.delete(f"/sites/garage/nodes/{BOARD}/device")
    assert [e["key"] for e in told] == ["garage/printer_1"]
    assert told[0]["body"]["key"] == put["picture"]["key"] != was["picture"]["key"]
