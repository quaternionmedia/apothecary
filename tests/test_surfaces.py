"""The surfaces (apothecary/surfaces.py, routes/surfaces.py): each owner declares what it
keeps, in its own frame; one read, one stream that relays the changes the server already
learns of and asks nothing of any port; and one door for what the family's members
found."""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import serial
from fastapi.testclient import TestClient

from apothecary import jobs, projector, sites, surfaces
from apothecary.api import app
from apothecary.family import hub, tokens
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
    TOKENS.clear()
    TOKENS.update({name: tokens.make(name) for name in ("alfred", "joe")})
    yield tmp_path
    hub.close()


TOKENS: dict = {}


def _post(body: dict, token="its own", **more):
    """A member's observation posted, with its own token unless another is named."""
    if token == "its own":
        token = TOKENS.get(body.get("by"))
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(
        "/surfaces/contributed", json=body, headers={**headers, **more.pop("headers", {})}, **more
    )


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
            kept = await asyncio.to_thread(_post, _found())
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
    _post(_found(by="joe", surface="jobs", frame="none"))
    every = client.get("/surfaces/contributed").json()["snapshot"]["observations"]
    assert [o["by"] for o in every] == ["joe", "alfred"]
    one = client.get("/surfaces/contributed", params={"surface": "projector"}).json()
    assert [o["body"]["saw"] for o in one["snapshot"]["observations"]] == [
        "the first layer lifting at the front left"
    ]
    on_disk = json.loads((members / "surfaces" / "contributed.json").read_text(encoding="utf-8"))
    assert len(on_disk["observations"]) == 2


def test_a_kept_file_that_does_not_read_is_set_aside_and_said_never_written_over(members):
    """The observations kept, damaged: a read says so and leaves the file; a write keeps
    it aside, as it was, refuses the observation saying where it went, and the next
    write starts a file of its own."""
    folder = members / "surfaces"
    folder.mkdir(exist_ok=True)
    kept = folder / "contributed.json"
    damaged = '{"format": "apothecary.contributed/1", "observations": [{"by": "alfred", '
    kept.write_text(damaged, encoding="utf-8")
    read = client.get("/surfaces/contributed")
    assert read.status_code == 503 and "does not read" in read.json()["detail"], read.text
    assert kept.read_text(encoding="utf-8") == damaged
    refused = _post(_found())
    assert refused.status_code == 503 and "kept aside as" in refused.json()["detail"]
    [aside] = folder.glob("contributed.unreadable-*.json")
    assert aside.name in refused.json()["detail"]
    assert aside.read_text(encoding="utf-8") == damaged and not kept.exists()
    assert _post(_found()).status_code == 201
    every = client.get("/surfaces/contributed").json()["snapshot"]["observations"]
    assert [o["by"] for o in every] == ["alfred"]
    # One row that is no observation does not read either: nothing of it is dropped.
    rows = json.loads(kept.read_text(encoding="utf-8"))
    rows["observations"].append({"by": "joe"})
    kept.write_text(json.dumps(rows), encoding="utf-8")
    assert client.get("/surfaces/contributed").status_code == 503


DOCS = Path(__file__).resolve().parents[1] / "docs" / "surfaces.md"


def test_the_shapes_docs_surfaces_md_shows_have_the_keys_real_ones_have(members, kept):
    """docs/surfaces.md writes a read, a change on the stream and an observation by
    hand: each carries the keys the real one does, so a key renamed turns this red."""
    text = DOCS.read_text(encoding="utf-8")
    read_shown, observation_shown = (
        json.loads(b) for b in re.findall(r"```json\n(.*?)\n```", text, re.S)
    )
    stream = re.search(r"```text\n(.*?)\n```", text, re.S)[1]
    change_shown = json.loads(" ".join(stream.split("event: change\ndata: ", 1)[1].splitlines()))
    read = client.get("/surfaces/projector", params={"site": "garage", "path": "printer_1"})
    assert set(read_shown) == set(read.json())
    assert set(read_shown["words"]) == set(read.json()["words"])

    async def one_change():
        following = surfaces.subscribe(["jobs"])
        try:
            surfaces.changed("jobs", key="j", body={"seen": True})
            got, _ = await following.next(1.0)
            return got[0]
        finally:
            following.close()

    assert set(change_shown) == set(asyncio.run(one_change()))
    kept_answer = _post(observation_shown)
    assert kept_answer.status_code == 201, kept_answer.text
    assert set(kept_answer.json()) == set(observation_shown) | {"format", "recorded_at"}


def test_only_a_member_writes_and_only_of_a_surface_in_a_frame(members, monkeypatch):
    stranger = _post(_found(by="mallory"))
    assert stranger.status_code == 403 and "no member of the family's hub" in stranger.text
    nowhere = _post(_found(surface="weather"))
    assert nowhere.status_code == 404
    assert _post(_found(frame="inches")).status_code == 422
    huge = _found(body={"saw": "x" * (surfaces.BODY_MOST + 1)})
    assert _post(huge).status_code == 422
    # A page of another origin cannot write, as it can write nowhere here.
    foreign = {"origin": "https://evil.example", "sec-fetch-site": "cross-site"}
    assert _post(_found(), headers=foreign).status_code == 403
    monkeypatch.setattr(surfaces, "KEPT", 2)
    for n in range(3):
        _post(_found(body={"n": n}))
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


# --- a job's stages ---------------------------------------------------------------------------


def _stages(told: list) -> list:
    """The stages the jobs' changes carry, each once for as long as it held."""
    stages = [e["body"]["detail"]["stage"] for e in told]
    return [s for n, s in enumerate(stages) if n == 0 or stages[n - 1] != s]


def _a_print_followed(links, lines: int, steer):
    """A print of ``lines`` lines on a scripted board, run while the jobs are followed:
    ``steer(job, gate)`` drives it. The changes the reader heard."""
    from firmware_helpers import ScriptedTransport

    kept = devices.save_print_file("long.gcode", ("G1 X1\n" * lines).encode(), machine="printer")
    gate = threading.Event()
    gate.set()

    class Gated(ScriptedTransport):
        def write(self, data):
            if data.decode().strip() == "G1 X1":
                gate.wait(5)
                time.sleep(0.001)
            super().write(data)

    links.factory = Gated
    links.control.arm(PORT)

    async def follow():
        following = surfaces.subscribe(["jobs"])
        try:
            def run():
                job = devices.start_print(PORT, kept.id, links=links)
                steer(job, gate)
                job.thread.join(10)
                return job

            job = await asyncio.to_thread(run)
            got, missed = await following.next(0.2)
            return job, got, missed
        finally:
            following.close()

    return asyncio.run(follow())


@pytest.fixture
def scripted_links(monkeypatch):
    from firmware_helpers import ScriptedTransport

    ScriptedTransport.instances.clear()
    links = gcode.PrinterLinks(factory=ScriptedTransport)
    monkeypatch.setattr(gcode, "_LINKS", links)
    yield links
    links.stop_all()


def _wait_for(test, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not test():
        time.sleep(0.005)
    assert test()


def test_a_print_s_stages_arrive_in_order_on_a_follower(fake_arduino_cli, scripted_links):
    """A print begun, paused, resumed and run to its end, heard by a follower of the jobs:
    each stage as it held, in order, the same job's id on each, and the last the record."""

    def steer(job, gate):
        gate.clear()  # a line held at the board
        _wait_for(lambda: job.stage == "printing")
        job.pause()
        gate.set()
        time.sleep(0.1)
        job.resume()

    job, told, missed = _a_print_followed(scripted_links, 60, steer)
    assert job.record.outcome == "done" and missed == 0
    assert {e["key"] for e in told} == {job.record.id} and all(e["surface"] == "jobs" for e in told)
    assert _stages(told) == ["starting", "printing", "paused", "printing", "done"]
    assert [e["body"]["outcome"] for e in told][0] == "running"
    assert told[-1]["body"]["outcome"] == "done" and told[-1]["body"]["progress"] == 1.0
    progress = [e["body"]["progress"] for e in told]
    assert progress == sorted(progress)


def test_a_cancel_is_told_as_cancelling_and_then_cancelled(fake_arduino_cli, scripted_links):
    def steer(job, gate):
        _wait_for(lambda: job.sent >= 2)
        job.cancel()

    job, told, _ = _a_print_followed(scripted_links, 300, steer)
    assert job.record.outcome == "cancelled"
    assert _stages(told)[-2:] == ["cancelling", "cancelled"]
    assert _stages(told)[:2] == ["starting", "printing"]


def test_progress_is_told_at_each_whole_percent_and_no_oftener(fake_arduino_cli, scripted_links, monkeypatch):
    monkeypatch.setattr(devices, "PRINT_PROGRESS_EVERY", 1)  # the job speaks at every line
    job, told, _ = _a_print_followed(scripted_links, 400, lambda job, gate: None)
    percents = [int(e["body"]["progress"] * 100) for e in told]
    assert len(percents) == len(set(zip(percents, (e["body"]["detail"]["stage"] for e in told))))
    assert len(told) <= 100 + 5 and percents[0] == 0 and percents[-1] == 100
    assert len(told) > 5  # the progress between is told, at some rate


def test_nobody_following_a_job_means_nothing_of_it_is_made(fake_arduino_cli, scripted_links):
    """``moved`` asks the job for its state only while a reader follows the jobs."""
    asked = []
    at = datetime.now(timezone.utc)
    job = jobs.Job(
        id=jobs.new_id(at, "/dev/ttyQUIET"),
        kind="print",
        machine=jobs.JobMachine(kind="printer", port="/dev/ttyQUIET"),
        input=jobs.JobInput(name="q.gcode"),
        started_at=at,
        detail={"stage": "starting"},
    )

    def now():
        asked.append(1)
        return job.model_copy(update={"detail": {"stage": "printing"}})

    jobs.begin(job, live=now)
    try:
        assert not surfaces.listening("jobs") and jobs.moved(job.id, now) is None
        assert asked == []

        async def follow():
            following = surfaces.subscribe(["jobs"])
            try:
                return jobs.moved(job.id, now), jobs.moved(job.id, now), jobs.moved("gone", now)
            finally:
                following.close()

        first, again, unknown = asyncio.run(follow())
        assert first["body"]["detail"]["stage"] == "printing"
        assert again is None and unknown is None  # told once for as long as it held
    finally:
        jobs.end(job.model_copy(update={"outcome": "done", "finished_at": at}))
    assert jobs._TOLD.get(job.id) is None


def test_the_job_change_docs_surfaces_md_shows_has_the_keys_a_real_one_has(
    fake_arduino_cli, scripted_links
):
    """The stage event written by hand in docs/surfaces.md carries keys a real one has."""
    text = DOCS.read_text(encoding="utf-8")
    shown = re.findall(r"```text\n(.*?)\n```", text, re.S)[1]
    written = json.loads(" ".join(shown.split("event: change\ndata: ", 1)[1].splitlines()))
    job, told, _ = _a_print_followed(scripted_links, 30, lambda job, gate: None)
    real = told[0]
    assert set(written) == set(real) and written["surface"] == "jobs"
    assert set(written["body"]) <= set(real["body"])
    assert set(written["body"]["detail"]) <= set(real["body"]["detail"])
    assert jobs.JOB_ID_RE.match(written["key"]) and "log" not in real["body"]


def test_a_member_writes_only_with_its_own_token(members, caplog):
    """The name in ``by`` is a claim: without the member's token, with another's, with a
    wrong one or in another scheme it is 401 and nothing is kept, and no token is in
    what is answered or logged."""
    caplog.set_level("DEBUG")
    missing = _post(_found(), token=None)
    assert missing.status_code == 401 and missing.headers["www-authenticate"] == "Bearer"
    others = _post(_found(by="alfred"), token=TOKENS["joe"])  # joe's token, alfred's name
    wrong = _post(_found(), token="not-a-token")
    scheme = _post(_found(), token=None, headers={"Authorization": f"Basic {TOKENS['alfred']}"})
    bare = _post(_found(), token=None, headers={"Authorization": TOKENS["alfred"]})
    for refused in (others, wrong, scheme, bare):
        assert refused.status_code == 401, refused.text
    assert client.get("/surfaces/contributed").json()["snapshot"]["observations"] == []
    assert _post(_found()).status_code == 201
    for text in [r.text for r in (missing, others, wrong, scheme, bare)] + [caplog.text]:
        assert not any(token in text for token in TOKENS.values())


def test_a_member_with_no_token_made_is_refused_and_told_how_to_make_one(members):
    """A name in the table with no token is not let write as itself, as it was: the
    owner makes it one (``apothecary family token NAME``)."""
    tokens.revoke("joe")
    refused = _post(_found(by="joe", surface="jobs", frame="none"), token=TOKENS["joe"])
    assert refused.status_code == 401
    assert "apothecary family token joe" in refused.json()["detail"]
    assert TOKENS["joe"] not in refused.text
    assert not (members / "surfaces" / "contributed.json").exists()


def test_a_token_is_kept_only_as_its_hash_in_a_file_for_this_account_alone(members):
    text = (members / tokens.FILE).read_text(encoding="utf-8")
    assert not any(token in text for token in TOKENS.values())
    assert (members / tokens.FILE).stat().st_mode & 0o077 == 0
    assert tokens.named() == ["alfred", "joe"]
    again = tokens.make("alfred")  # a new token replaces the old
    assert not tokens.check("alfred", TOKENS["alfred"]) and tokens.check("alfred", again)
    assert not tokens.check("alfred", "") and not tokens.check("nobody", again)
    (members / tokens.FILE).write_text("{", encoding="utf-8")  # unreadable: fails closed
    assert not tokens.check("alfred", again)
