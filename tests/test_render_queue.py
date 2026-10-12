"""A bounded queue of OpenSCAD runs (docs/plans/part-iteration-2026-10-12.md,
item 7): at most ``runs_limit()`` at once, the rest waiting their turn and shown
as waiting to the page that asked (``GET /openscad/runs``), and a request
cancelled while it waits leaving the line without running, as one cancelled
while it runs is stopped.

The OpenSCAD is scripted (tests/scripted_openscad.py): a SCAD holding ``SLEEP``
takes half a minute to render, so a run can be seen running and others waiting.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from scripted_openscad import renders, scripted_openscad

from apothecary import api
from apothecary.api import app
from apothecary.projects.parts import stl_renderer
from apothecary.projects.parts.base import BasePart
from apothecary.projects.parts.stl_renderer import (
    OPENSCAD_RUNS,
    Cancellation,
    RunQueue,
    runs_for,
    runs_limit,
)

SCAD = "width = 34; // [10:100]\ncube([width, 20, 3]);\n"


class TestTheLimit:
    def test_two_unless_the_environment_says_otherwise(self, monkeypatch):
        monkeypatch.delenv("APOTHECARY_OPENSCAD_RUNS", raising=False)
        monkeypatch.setattr(stl_renderer.os, "cpu_count", lambda: 4)
        assert runs_limit() == OPENSCAD_RUNS == 2
        monkeypatch.setattr(stl_renderer.os, "cpu_count", lambda: 1)
        assert runs_limit() == 1
        monkeypatch.setenv("APOTHECARY_OPENSCAD_RUNS", "3")
        assert runs_limit() == 3
        for odd in ("0", "-2", "many"):
            monkeypatch.setenv("APOTHECARY_OPENSCAD_RUNS", odd)
            assert runs_limit() in (1, 2)


def _waiting_for(queue: RunQueue, count: int, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        now = queue.snapshot()
        if len(now["waiting"]) == count:
            return now
        time.sleep(0.01)
    raise AssertionError(f"never {count} waiting: {queue.snapshot()}")


class TestTheQueue:
    def test_beyond_the_limit_a_run_waits_its_turn_in_order(self, monkeypatch):
        monkeypatch.setenv("APOTHECARY_OPENSCAD_RUNS", "1")
        queue, order = RunQueue(), []
        first = queue.acquire("render")

        def wait(name):
            with runs_for("block", name), queue.place("param") as run:
                order.append((name, run is not None))

        second = threading.Thread(target=wait, args=("page-2",))
        second.start()
        _waiting_for(queue, 1)
        third = threading.Thread(target=wait, args=("page-3",))
        third.start()
        now = _waiting_for(queue, 2)
        assert [(r["page"], r["position"], r["kind"]) for r in now["waiting"]] == [
            ("page-2", 1, "param"),
            ("page-3", 2, "param"),
        ]
        assert [r["kind"] for r in now["running"]] == ["render"] and now["limit"] == 1
        assert queue.snapshot("page-3")["waiting"][0]["position"] == 2
        queue.release(first)
        second.join(5)
        third.join(5)
        assert order == [("page-2", True), ("page-3", True)]
        assert queue.snapshot() == {"limit": 1, "running": [], "waiting": []}

    def test_a_run_cancelled_while_it_waits_leaves_without_running(self, monkeypatch):
        monkeypatch.setenv("APOTHECARY_OPENSCAD_RUNS", "1")
        queue, cancel, got = RunQueue(), Cancellation(), []
        held = queue.acquire("render")
        waiter = threading.Thread(target=lambda: got.append(queue.acquire("render", cancel)))
        waiter.start()
        _waiting_for(queue, 1)
        cancel.cancel()
        waiter.join(5)
        assert got == [None] and queue.snapshot()["waiting"] == []
        queue.release(held)


@pytest.fixture
def block(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_CACHE_DIR", str(tmp_path / "cache"))
    exe = scripted_openscad(tmp_path / "bin" / "openscad")
    monkeypatch.setenv("APOTHECARY_OPENSCAD", str(exe))
    monkeypatch.setattr(stl_renderer, "_renderer", None)
    monkeypatch.setattr(stl_renderer, "RUNS", RunQueue())
    monkeypatch.setattr(api, "RUNS", stl_renderer.RUNS)
    scad = tmp_path / "parts" / "block" / "block.scad"
    scad.parent.mkdir(parents=True)
    scad.write_text(SCAD)
    part = BasePart(name="block", source_file=scad)
    monkeypatch.setattr(BasePart, "get_stl_output_path", lambda self: tmp_path / "block.stl")
    real = api._load_part_wrapper
    monkeypatch.setattr(
        api, "_load_part_wrapper", lambda name: part if name == "block" else real(name)
    )
    return exe


def _render_in_thread(client, scad: str, page: str, out: dict, name: str) -> threading.Thread:
    def go():
        out[name] = client.post(
            "/parts/block/draft/render", params={"page": page}, json={"scad": scad, "params": {}}
        )

    thread = threading.Thread(target=go)
    thread.start()
    return thread


def _until(client, test, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        now = client.get("/openscad/runs").json()
        if test(now):
            return now
        time.sleep(0.02)
    raise AssertionError(client.get("/openscad/runs").json())


class TestThroughTheRoutes:
    def test_a_waiting_render_is_shown_to_its_page_and_cancels_as_a_running_one_does(
        self, block, monkeypatch
    ):
        monkeypatch.setenv("APOTHECARY_OPENSCAD_RUNS", "1")
        client, out = TestClient(app), {}
        slow = _render_in_thread(client, SCAD + "// SLEEP\n", "page-a", out, "slow")
        _until(client, lambda now: [r["kind"] for r in now["running"]] == ["render"])
        waiting = _render_in_thread(client, SCAD + "// b one\n", "page-b", out, "waiting")
        _until(client, lambda now: len(now["waiting"]) == 1)
        mine = client.get("/openscad/runs", params={"page": "page-b"}).json()
        assert mine["running"] == [] and mine["limit"] == 1
        # Its first run waits: listing what the draft declares, before its render.
        assert [(r["part"], r["kind"], r["position"]) for r in mine["waiting"]] == [
            ("block", "param", 1)
        ]
        # A newer request from page-b takes the waiting one's place: it leaves the line.
        newer = _render_in_thread(client, SCAD + "// b two\n", "page-b", out, "newer")
        waiting.join(10)
        assert out["waiting"].status_code == 409, out["waiting"].text
        assert out["waiting"].json()["detail"]["superseded"] is True
        # A newer request from page-a stops the one running; the line moves on.
        quick = _render_in_thread(client, SCAD + "// a quick\n", "page-a", out, "quick")
        for thread in (slow, newer, quick):
            thread.join(20)
        assert out["slow"].status_code == 409
        assert out["newer"].status_code == 200 and out["quick"].status_code == 200
        assert out["newer"].json()["queued_seconds"] > 0
        # The SLEEP render started and was stopped; "b one" never ran.
        texts = [r["text"] for r in renders(block)]
        assert not any("b one" in t for t in texts) and any("SLEEP" in t for t in texts)
        assert client.get("/openscad/runs").json() == {"limit": 1, "running": [], "waiting": []}

    def test_a_check_waits_for_a_place_too(self, block, monkeypatch):
        monkeypatch.setenv("APOTHECARY_OPENSCAD_RUNS", "1")
        client, out = TestClient(app), {}
        slow = _render_in_thread(client, SCAD + "// SLEEP\n", "page-a", out, "slow")
        _until(client, lambda now: [r["kind"] for r in now["running"]] == ["render"])
        checked = {}
        check = threading.Thread(
            target=lambda: checked.update(
                r=client.post(
                    "/parts/block/draft/check",
                    params={"page": "page-c"},
                    json={"scad": SCAD, "params": {}},
                )
            )
        )
        check.start()
        now = _until(client, lambda now: len(now["waiting"]) == 1)
        assert now["waiting"][0]["kind"] in ("param", "csg")
        assert now["waiting"][0]["page"] == "page-c"
        client.post(
            "/parts/block/draft/render",
            params={"page": "page-a"},
            json={"scad": SCAD + "// a quick\n", "params": {}},
        )
        slow.join(20)
        check.join(20)
        assert checked["r"].status_code == 200 and checked["r"].json()["valid"]


def test_the_queue_is_the_one_the_route_reads():
    assert api.RUNS is stl_renderer.RUNS
    assert Path(stl_renderer.__file__).name == "stl_renderer.py"
