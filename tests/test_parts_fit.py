"""A part's interfaces and how two fit, at the command line and over HTTP
(apothecary parts interfaces, apothecary parts fit, apothecary/routes/interfaces.py)."""

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
