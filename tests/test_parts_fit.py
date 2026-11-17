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
    assert "fitting_32: a spigot, drawn" in result.output
    assert "32.6 across at its base to 31.4 at its tip, 25 long" in result.output
    assert "not in use with fitting_25" in result.output


def test_interfaces_follow_the_parameters_given():
    result = run("interfaces", "hose_adapter", "-p", "tip=false", "--json-out")
    assert result.exit_code == 0, result.output
    assert [i["name"] for i in json.loads(result.output)] == ["hose", "fitting_32"]


def test_a_part_with_none_says_so():
    result = run("interfaces", "calibration_cube")
    assert (result.exit_code, result.output) == (0, "calibration_cube declares no interfaces\n")


def test_fit_between_two_named_interfaces():
    result = run("fit", "hose_adapter.hose", "dust_hose_40.end", "--json-out")
    assert result.exit_code == 0, result.output
    (answer,) = json.loads(result.output)
    assert (answer["a"], answer["b"], answer["verdict"], answer["seat"]) == (
        "hose_adapter.hose",
        "dust_hose_40.end",
        "seats",
        40.0,
    )


def test_fit_exits_1_when_nothing_seats():
    result = run("fit", "hose_adapter.fitting_32", "dust_port_25")
    assert result.exit_code == 1
    assert "will not enter" in result.output


def test_fit_names_an_interface_that_is_not_there():
    result = run("fit", "hose_adapter.barb", "dust_port_25")
    assert result.exit_code != 0
    assert "hose_adapter has no interface 'barb'" in result.output


# --- over HTTP ------------------------------------------------------------------------


def test_a_parts_interfaces_over_http():
    r = TestClient(app).get("/parts/dust_port_32/interfaces")
    assert r.status_code == 200
    body = r.json()
    assert body["part"] == "dust_port_32"
    (port,) = body["interfaces"]
    assert (port["name"], port["type"], port["diameter"], port["source"]) == (
        "port",
        "socket",
        32.0,
        "stub",
    )


def test_a_fit_over_http():
    c = TestClient(app)
    r = c.get("/parts/hose_adapter/interfaces/fitting_25/fit", params={"to": "dust_port_25.port"})
    assert r.status_code == 200, r.text
    assert (r.json()["verdict"], r.json()["seat"], r.json()["b"]) == (
        "seats",
        10.0,
        "dust_port_25.port",
    )
    assert c.get("/parts/hose_adapter/interfaces/barb/fit?to=dust_port_25.port").status_code == 404
    assert c.get("/parts/hose_adapter/interfaces/hose/fit?to=dust_port_25").status_code == 422
    assert c.get("/parts/no_such_part/interfaces").status_code == 404
