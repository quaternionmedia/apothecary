"""A part's interfaces, how two fit, and the adapter between two ends, at the command
line and over HTTP (apothecary parts interfaces, fit and adapter;
apothecary/routes/interfaces.py)."""

from __future__ import annotations

import json

from click.testing import CliRunner
from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.cli.main import cli


def run(*args):
    return CliRunner().invoke(cli, ["parts", *args])


# --- the command line -----------------------------------------------------------------


def test_interfaces_lists_each_with_its_sizes_and_what_it_excludes():
    result = run("interfaces", "hose_adapter")
    assert result.exit_code == 0, result.output
    assert "step: a spigot, drawn" in result.output
    assert "32.6 across at its base to 31.4 at its tip, 25 long" in result.output
    assert "not in use with b" in result.output


def test_interfaces_follow_the_parameters_given():
    result = run("interfaces", "hose_adapter", "-p", "step=false", "--json-out")
    assert result.exit_code == 0, result.output
    assert [i["name"] for i in json.loads(result.output)] == ["a", "b"]


def test_interfaces_at_a_preset_and_a_number_over_it():
    result = run("interfaces", "dust_port@hose_40", "-p", "diameter=41.5", "--json-out")
    assert result.exit_code == 0, result.output
    (end,) = json.loads(result.output)
    assert (end["type"], end["diameter"], end["stretch"], end["depth"]) == ("socket", 41.5, 0.05, 100.0)


def test_a_part_with_none_says_so():
    result = run("interfaces", "calibration_cube")
    assert (result.exit_code, result.output) == (0, "calibration_cube declares no interfaces\n")


def test_fit_between_two_named_interfaces():
    result = run("fit", "hose_adapter.a", "dust_port@hose_40.end", "--json-out")
    assert result.exit_code == 0, result.output
    (answer,) = json.loads(result.output)
    assert (answer["a"], answer["b"], answer["verdict"], answer["seat"]) == (
        "hose_adapter.a",
        "dust_port@hose_40.end",
        "seats",
        40.0,
    )


def test_fit_exits_1_when_nothing_seats():
    result = run("fit", "hose_adapter.step", "dust_port@port_25")
    assert result.exit_code == 1
    assert "will not enter" in result.output


def test_fit_names_an_interface_or_a_preset_that_is_not_there():
    result = run("fit", "hose_adapter.barb", "dust_port@port_25")
    assert result.exit_code != 0
    assert "hose_adapter has no interface 'barb'" in result.output
    result = run("fit", "hose_adapter.a", "dust_port@port_99")
    assert result.exit_code != 0
    assert "dust_port has no preset 'port_99'; its presets: hose_40, port_32" in result.output


def test_the_adapter_between_two_presets_says_each_fit_and_its_parameters():
    result = run("adapter", "dust_port@hose_40", "dust_port@port_32")
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[:4] == [
        "hose_adapter between dust_port@hose_40.end and dust_port@port_32.end",
        "  a ↔ dust_port@hose_40.end: seats, 40 in (it goes 40.0 in and stops: its shoulder "
        "reaches the mouth)",
        "  b ↔ dust_port@port_32.end: seats, 12.5 in (it goes 12.5 in and stops: its diameter "
        "reaches the bore's 32)",
        "  stub numbers: dust_port@hose_40.end, dust_port@port_32.end",
    ]
    assert "-p a_d=40 " in lines[4] and "-p b_d=32 " in lines[4] and "-p step=false" in lines[4]
    assert lines[5].startswith("  the rule: a spigot end straddles the bore it meets")
    assert lines[6].startswith("  slice it: apothecary slicer slice hose_adapter -p ")


def test_a_measured_end_goes_over_its_preset_and_is_no_stub():
    result = run(
        "adapter",
        "dust_port@hose_40",
        "dust_port@port_32",
        "-b",
        "diameter=31.6",
        "-b",
        "measured=true",
        "--json-out",
    )
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["params"]["b_d"] == 31.6
    assert body["b"]["label"] == "dust_port@port_32.end (diameter=31.6, measured=true)"
    assert body["b"]["interface"]["source"] == "measured"
    assert [c["name"] for c in body["placed"]] == ["end_a", "adapter", "end_b"]


def test_an_adapter_adjusted_is_checked_again_and_exits_1_when_an_end_does_not_seat():
    result = run("adapter", "dust_port@hose_40", "dust_port@outlet_35", "-p", "b_d=36")
    assert result.exit_code == 1
    assert "b ↔ dust_port@outlet_35.end: loose (it is 35 across at its widest and the bore is 36" in (
        result.output
    )


def test_the_adapter_refused_says_why():
    result = run("adapter", "dust_port@outlet_35", "dust_port", "-b", "diameter=35")
    assert result.exit_code == 1
    assert "meet without an adapter" in result.output
    result = run("adapter", "hose_adapter", "dust_port")
    assert "hose_adapter has 3 round interfaces (a, step, b): name the one meant" in result.output
    result = run("adapter", "dust_port@hose_40", "dust_port@port_32", "-p", "transition_length=2")
    assert result.exit_code == 1
    assert "transition: its bore closes in past 45 degrees" in result.output


# --- over HTTP ------------------------------------------------------------------------


def test_a_parts_interfaces_over_http_at_a_preset():
    c = TestClient(app)
    body = c.get("/parts/dust_port/interfaces", params={"preset": "port_25"}).json()
    assert (body["part"], body["preset"]) == ("dust_port", "port_25")
    (port,) = body["interfaces"]
    assert (port["name"], port["type"], port["diameter"], port["source"]) == (
        "end",
        "socket",
        25.0,
        "stub",
    )
    assert c.get("/parts/dust_port/interfaces", params={"preset": "nope"}).status_code == 404


def test_a_fit_over_http():
    c = TestClient(app)
    r = c.get("/parts/hose_adapter/interfaces/b/fit", params={"to": "dust_port@port_25.end"})
    assert r.status_code == 200, r.text
    assert (r.json()["verdict"], r.json()["seat"], r.json()["b"]) == (
        "seats",
        10.0,
        "dust_port@port_25.end",
    )
    assert c.get("/parts/hose_adapter/interfaces/barb/fit?to=dust_port.end").status_code == 404
    assert c.get("/parts/hose_adapter/interfaces/a/fit?to=dust_port").status_code == 422
    assert c.get("/parts/no_such_part/interfaces").status_code == 404


HOSE = {"part": "dust_port", "preset": "hose_40"}
PORT = {"part": "dust_port", "preset": "port_32"}


def test_the_adapter_between_two_ends_over_http():
    c = TestClient(app)
    r = c.post("/parts/hose_adapter/between", json={"a": HOSE, "b": {**PORT, "params": {"diameter": 31.6}}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["part"], body["derived"], body["seats"]) == ("hose_adapter", True, True)
    assert (body["params"]["a_d"], body["params"]["b_d"]) == (40.0, 31.6)
    assert [f["verdict"] for f in body["fits"]] == ["seats", "seats"]
    assert body["b"]["label"] == "dust_port@port_32.end (diameter=31.6)"
    assert [(p["name"], p["position"]) for p in body["placed"]] == [
        ("end_a", [0.0, 0.0, 0.0]),
        ("adapter", [0.0, 0.0, 60.0]),
        ("end_b", [0.0, 0.0, 155.5]),
    ]
    assert body["placed_ok"] is True


def test_its_own_parameters_are_checked_against_the_ends_over_http():
    c = TestClient(app)
    made = c.post("/parts/hose_adapter/between", json={"a": HOSE, "b": PORT}).json()
    r = c.post(
        "/parts/hose_adapter/between",
        json={"a": HOSE, "b": PORT, "params": {**made["params"], "b_d": 33.0}},
    )
    assert r.status_code == 200, r.text
    assert (r.json()["derived"], r.json()["seats"]) == (False, False)
    assert r.json()["fits"][1]["verdict"] == "will not enter"


def test_no_adapter_is_a_422_with_why_and_an_unknown_end_a_404():
    c = TestClient(app)
    r = c.post(
        "/parts/hose_adapter/between",
        json={"a": {"part": "dust_port", "preset": "outlet_35"}, "b": {"part": "dust_port", "params": {"diameter": 35}}},
    )
    assert r.status_code == 422
    assert "meet without an adapter" in r.json()["detail"]
    r = c.post("/parts/hose_adapter/between", json={"a": {"part": "dust_port", "preset": "nope"}, "b": PORT})
    assert r.status_code == 404
    r = c.post("/parts/dust_port/between", json={"a": HOSE, "b": PORT})
    assert (r.status_code, r.json()["detail"]) == (
        404,
        "dust_port is not generated between two ends; hose_adapter is",
    )
