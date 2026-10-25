"""The slicer over the API: its status, a slice of a part or a made piece for the
pinned printer as a task, its answer, and the slices kept -- against the scripted
OrcaSlicer (tests/slicer_helpers.py). Nothing here renders: a part's or a piece's
STL is a stand-in, and no serial port is opened."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from slicer_helpers import fake_calls

from apothecary import api as api_module
from apothecary.api import _site_store, app
from apothecary.firmware import devices
from apothecary.hierarchy import Structure
from apothecary.slicer import service
from apothecary.vision import views as viewing

client = TestClient(app)

CUBE_STL = b"solid cube\nendsolid cube\n"
BOARD = "printer_1.frame_system.mainboard"


@pytest.fixture(autouse=True)
def garage():
    _site_store.reset("garage")
    yield _site_store.get("garage")
    _site_store.reset("garage")


@pytest.fixture
def parts_built(monkeypatch):
    """A part's STL is a stand-in, built at once: what was asked is recorded."""
    built = []
    real = service.part_target

    def part_target(name, site=None, path=None):
        target = real(name, site=site, path=path)

        def stl(log):
            built.append(name)
            return CUBE_STL

        target.stl = stl
        return target

    monkeypatch.setattr(service, "part_target", part_target)
    return built


def _wait(task: dict, seconds: float = 20.0) -> dict:
    deadline = time.monotonic() + seconds
    while True:
        now = client.get(f"/slicer/tasks/{task['id']}").json()
        if now["status"] != "running" or time.monotonic() > deadline:
            return now
        time.sleep(0.05)


def _slice(body: dict) -> dict:
    r = client.post("/slicer/slice", json=body)
    assert r.status_code == 202, r.text
    started = r.json()
    assert started["slice"] is None and started["kind"] == "slice"
    return _wait(started)


def test_the_status_says_each_slicer_the_one_used_and_the_printers(fake_orcaslicer):
    r = client.get("/slicer/status")
    assert r.status_code == 200
    body = r.json()
    assert body["chosen"] == "orcaslicer" and body["printers"] == ["ender3"]
    (orca,) = body["slicers"]
    assert orca["id"] == "orcaslicer" and orca["chosen"] is True
    assert orca["pinned"] == "2.4.2" and orca["tool"]["version"] == "2.4.2"
    assert (orca["technology"], orca["inputs"], orca["writes"]) == ("FFF", [".stl"], [".gcode"])
    assert orca["problems"] == []
    # What a slice can be composed from: each piece says what it does; the stubs say so.
    pieces = {(p["kind"], p["id"]): p for p in body["pieces"]}
    assert not pieces[("start", "home")]["stub"] and not pieces[("filament", "printer")]["stub"]
    for stub in (
        ("start", "stored-mesh"),
        ("start", "probe-each-print"),
        ("start", "first-layer-offset"),
        ("filament", "choose"),
        ("declared", "word-print-settings"),
    ):
        assert pieces[stub]["stub"] and pieces[stub]["does"], stub
    assert "M420 S1" in pieces[("start", "stored-mesh")]["does"]
    assert "G29" in pieces[("start", "probe-each-print")]["does"]


def test_a_part_is_sliced_for_a_site_printer_and_kept_in_the_print_cards_file_box(
    fake_orcaslicer, parts_built
):
    done = _slice({"part": "calibration_cube", "site": "garage", "printer": "printer_1"})
    assert done["status"] == "succeeded", done["lines"]
    answer = done["slice"]
    assert answer["ok"] is True
    record = answer["record"]
    assert record["made"] == {
        "kind": "part",
        "name": "calibration_cube",
        "site": None,
        "path": None,
        "word": None,
    }
    assert record["printer"] == {
        "part": "ender3",
        "name": "printer_1",
        "site": "garage",
        "path": "printer_1",
        "port": None,
    }
    settings = {s["name"]: s for s in record["settings"]}
    assert settings["layer_height"]["origin"] == "declared"
    assert settings["layer_height"]["source"] == "part calibration_cube"
    assert settings["wall_loops"]["origin"] == "printer"
    assert record["estimate"]["time"] == "1h 2m 3s"
    assert parts_built == ["calibration_cube"]
    # The Print card lists it at once; the slice is read back by its file.
    kept = client.get("/firmware/printers/prints").json()
    assert [f["id"] for f in kept] == [record["file_id"]]
    assert kept[0]["name"] == "calibration_cube.gcode" and kept[0]["problems"] == []
    assert client.get(f"/slicer/slices/{record['file_id']}").json() == record
    assert [r["file_id"] for r in client.get("/slicer/slices").json()] == [record["file_id"]]
    # Forgotten by the Print card, the slice is forgotten too.
    assert client.delete(f"/firmware/printers/prints/{record['file_id']}").is_success
    assert client.get(f"/slicer/slices/{record['file_id']}").status_code == 404


def test_a_part_standing_in_the_site_is_sliced_as_its_part(fake_orcaslicer, parts_built):
    done = _slice({"part": "footpedal", "site": "garage", "printer": "printer_1"})
    assert done["status"] == "succeeded", done["lines"]
    made = done["slice"]["record"]["made"]
    assert made == {
        "kind": "part",
        "name": "footpedal",
        "site": "garage",
        "path": "footpedal",
        "word": None,
    }
    assert parts_built == ["footpedal"]


def test_a_made_piece_is_sliced_from_its_nodes_render_with_the_printers_settings(
    fake_orcaslicer, garage, monkeypatch
):
    """A piece made from a picture declares no print settings, so every value is the
    printer's; its STL is its node's render, as /sites/{name}/nodes/{path}/stl serves it."""
    garage.children.append(Structure(name="bin_1"))  # as a piece made from a picture stands
    rendered = []

    def node_stl(name, path):
        rendered.append((name, path))
        return CUBE_STL, None

    monkeypatch.setattr(api_module, "_node_stl", node_stl)
    with monkeypatch.context() as patched:  # undone before the garage is reset
        patched.setattr(
            viewing,
            "store",
            lambda: SimpleNamespace(
                made_at=lambda site: {"bin_1": SimpleNamespace(word="bin")}
                if site == "garage"
                else {}
            ),
        )
        done = _slice({"part": "bin_1", "site": "garage", "printer": "printer_1"})
    assert done["status"] == "succeeded", done["lines"]
    record = done["slice"]["record"]
    assert record["made"] == {
        "kind": "piece",
        "name": "bin_1",
        "site": "garage",
        "path": "bin_1",
        "word": "bin",
    }
    assert rendered == [("garage", "bin_1")]
    origins = {s["name"]: s["origin"] for s in record["settings"]}
    assert "declared" not in origins.values()
    assert origins["layer_height"] == origins["wall_loops"] == "printer"
    # The word's print settings are a stub, and the answer says so.
    said = next(s for s in record["settings"] if s["name"] == "print settings")
    assert said["source"] == "piece bin_1, made as bin" and "a stub" in said["note"]
    assert devices.print_file(record["file_id"]).name == "bin_1.gcode"


def test_the_printer_of_a_port_is_the_one_its_pin_stands_under(
    fake_orcaslicer, parts_built, garage, monkeypatch
):
    monkeypatch.setattr(
        api_module,
        "_pinned_at",
        lambda port: ("garage", garage, BOARD) if port == "/dev/ttyFAKE1" else None,
    )
    done = _slice({"part": "calibration_cube", "port": "/dev/ttyFAKE1"})
    assert done["status"] == "succeeded", done["lines"]
    printer = done["slice"]["record"]["printer"]
    assert printer == {
        "part": "ender3",
        "name": "printer_1",
        "site": "garage",
        "path": "printer_1",
        "port": "/dev/ttyFAKE1",
    }
    r = client.post("/slicer/slice", json={"part": "calibration_cube", "port": "/dev/ttyFAKE0"})
    assert r.status_code == 422 and "no printer that keeps a slicer profile" in r.json()["detail"]


@pytest.mark.parametrize(
    "body, said",
    [
        ({"part": "no_such_part"}, "no part named 'no_such_part'"),
        ({"part": "calibration_cube", "printer": "fifel"}, "keeps no slicer profile"),
        (
            {"part": "calibration_cube", "site": "garage", "printer": "workbench"},
            "no printer that keeps a slicer profile",
        ),
        (
            {"part": "calibration_cube", "site": "garage", "printer": "esp32_blink"},
            "keeps no slicer profile",
        ),
        ({"part": "calibration_cube", "site": "datum_core"}, "datum_core: no printer"),
    ],
)
def test_what_is_not_a_part_or_a_printer_is_refused_before_a_task_starts(
    fake_orcaslicer, body, said
):
    r = client.post("/slicer/slice", json=body)
    assert r.status_code == 422, r.text
    assert said in r.json()["detail"]
    assert client.get("/slicer/tasks").json() == []


def test_a_name_that_could_be_a_path_elsewhere_is_refused_by_its_shape(fake_orcaslicer):
    for bad in ("../etc/passwd", "a/b", "", ".hidden"):
        assert client.post("/slicer/slice", json={"part": bad}).status_code == 422


def test_no_slicer_installed_is_a_503_before_a_task_starts(
    fake_orcaslicer, parts_built, monkeypatch
):
    monkeypatch.setenv("APOTHECARY_ORCASLICER", "none")
    r = client.post("/slicer/slice", json={"part": "calibration_cube"})
    assert r.status_code == 503 and "apothecary slicer install" in r.json()["detail"]
    assert parts_built == []


def test_a_failed_slice_answers_the_slicers_errors_by_line(
    fake_orcaslicer, parts_built, monkeypatch
):
    monkeypatch.setenv("FAKE_ORCA", "outside")
    done = _slice({"part": "calibration_cube"})
    assert done["status"] == "failed"
    answer = done["slice"]
    assert answer["ok"] is False and "exit 205" in answer["error"]
    assert {"level": "warning", "line": 2, "text": "Warning: the bed is small"} in answer[
        "messages"
    ]
    assert any(
        m["line"] is None and "boundary of the heated bed" in m["text"] for m in answer["messages"]
    )
    assert {s["name"] for s in answer["settings"]} >= {"layer_height", "wall_loops"}
    assert client.get("/firmware/printers/prints").json() == []


def test_a_slice_can_be_cancelled_and_keeps_nothing(fake_orcaslicer, parts_built, monkeypatch):
    monkeypatch.setenv("FAKE_ORCA", "slow")
    r = client.post("/slicer/slice", json={"part": "calibration_cube"})
    task = r.json()
    deadline = time.monotonic() + 20
    while "slicing slowly" not in client.get(f"/slicer/tasks/{task['id']}").json()["lines"]:
        assert time.monotonic() < deadline
        time.sleep(0.05)
    started = time.monotonic()
    cancelled = client.post(f"/slicer/tasks/{task['id']}/cancel").json()
    assert time.monotonic() - started < 15
    done = _wait(cancelled)
    assert done["status"] == "cancelled"
    assert client.get("/firmware/printers/prints").json() == []
    assert client.post(f"/slicer/tasks/{task['id']}/cancel").status_code == 409


def test_one_slice_at_a_time(fake_orcaslicer, parts_built, monkeypatch):
    monkeypatch.setenv("FAKE_ORCA", "slow")
    first = client.post("/slicer/slice", json={"part": "calibration_cube"}).json()
    try:
        r = client.post("/slicer/slice", json={"part": "calibration_cube"})
        assert r.status_code == 409 and "still running" in r.json()["detail"]
    finally:
        client.post(f"/slicer/tasks/{first['id']}/cancel")


def test_the_slicer_install_route_is_a_task(fake_orcaslicer, monkeypatch):
    from apothecary.slicer.modules import orcaslicer

    asked = []
    monkeypatch.setattr(
        orcaslicer.OrcaSlicerModule,
        "install",
        lambda self, log, force=False: asked.append(force) or log("installed (stand-in)"),
    )
    r = client.post("/slicer/install", json={"force": True})
    assert r.status_code == 202 and r.json()["kind"] == "slicer-install"
    done = _wait(r.json())
    assert done["status"] == "succeeded" and "installed (stand-in)" in done["lines"]
    assert asked == [True]


def test_the_openapi_shows_the_slicer_routes():
    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/slicer/status",
        "/slicer/install",
        "/slicer/slice",
        "/slicer/tasks/{task_id}",
        "/slicer/tasks/{task_id}/cancel",
        "/slicer/slices",
        "/slicer/slices/{file_id}",
    ):
        assert path in paths, path


def test_a_slice_writes_files_only(fake_orcaslicer, parts_built):
    """No serial port: the slicer is handed files, and its argv names no port."""
    _slice({"part": "calibration_cube"})
    for argv in fake_calls(fake_orcaslicer):
        assert not [a for a in argv if a.startswith("/dev/")]


def test_a_site_named_alone_slices_for_its_one_printer(fake_orcaslicer, parts_built):
    done = _slice({"part": "calibration_cube", "site": "garage"})
    assert done["status"] == "succeeded", done["lines"]
    assert done["slice"]["record"]["printer"]["path"] == "printer_1"


def _piece_in(garage, monkeypatch):
    """bin_1, standing in the garage as a piece made from a picture stands; its STL a
    stand-in. Returns the patch to hold the view store with while it is used."""
    garage.children.append(Structure(name="bin_1"))
    monkeypatch.setattr(api_module, "_node_stl", lambda name, path: (CUBE_STL, None))
    return lambda patched: patched.setattr(
        viewing,
        "store",
        lambda: SimpleNamespace(
            made_at=lambda site: {"bin_1": SimpleNamespace(word="bin")} if site == "garage" else {}
        ),
    )


def test_slicer_slice_reaches_a_made_piece_through_the_running_server(
    fake_orcaslicer, garage, monkeypatch
):
    """`apothecary slicer slice SITE/PATH` asks the server on this machine, as the page
    will: a made piece lives in its memory. Its log arrives as the task runs."""
    import click
    from click.testing import CliRunner

    from apothecary.cli import slicer as cli_slicer
    from apothecary.cli.main import cli

    hold = _piece_in(garage, monkeypatch)
    asked = []

    def call(base, method, path, body=None):
        asked.append((base, method, path.split("?")[0]))
        r = client.request(method, path, json=body)
        if r.status_code >= 400:
            raise click.ClickException(f"{r.json()['detail']} ({r.status_code})")
        return r.json()

    monkeypatch.setattr(cli_slicer, "_call", call)
    with monkeypatch.context() as patched:
        hold(patched)
        result = CliRunner().invoke(cli, ["slicer", "slice", "garage/bin_1"])
    assert result.exit_code == 0, result.output
    assert "Slicing piece bin_1 for printer_1" in result.output
    assert "bin_1.gcode: kept as" in result.output
    assert asked[:2] == [
        ("http://127.0.0.1:8000", "GET", "/health"),
        ("http://127.0.0.1:8000", "POST", "/slicer/slice"),
    ]
    assert {a[2] for a in asked[2:]} == {asked[2][2]} and asked[2][2].startswith("/slicer/tasks/")
    assert [f["name"] for f in client.get("/firmware/printers/prints").json()] == ["bin_1.gcode"]
    with monkeypatch.context() as patched:
        hold(patched)
        refused = CliRunner().invoke(cli, ["slicer", "slice", "garage/no_such_piece"])
    assert (
        refused.exit_code != 0
        and "'no_such_piece' is no part or piece of garage, and no part's name (422)"
        in refused.output
    )


def test_slicer_slice_says_when_no_server_is_running_and_listens_nowhere_else():
    import socket

    from click.testing import CliRunner

    from apothecary.cli.main import cli

    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        free = held.getsockname()[1]
    result = CliRunner().invoke(cli, ["slicer", "slice", "garage/bin_1", "--port", str(free)])
    assert result.exit_code != 0
    assert f"no apothecary server at http://127.0.0.1:{free}" in result.output
    assert "apothecary serve" in result.output
    elsewhere = CliRunner().invoke(cli, ["slicer", "slice", "garage/bin_1", "--host", "10.0.0.7"])
    assert elsewhere.exit_code != 0 and "this machine only" in elsewhere.output
    bad = CliRunner().invoke(cli, ["slicer", "slice", "garage/../etc"])
    assert bad.exit_code != 0 and "want SITE/PATH" in bad.output
