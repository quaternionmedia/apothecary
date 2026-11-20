"""``apothecary tuning``: a printer tuned from the shell, with no browser and no server.

A coupon sliced by the scripted OrcaSlicer, its readings made from planted errors (the
error model's own: this holds the commands, not a printer), kept as a turn, explained,
applied, read again and undone."""

from __future__ import annotations

import json
import time

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from apothecary import print_tuning as pt
from apothecary import sites
from apothecary.api import app
from apothecary.cli import cli
from apothecary.projects.parts.print_coupon import DEFAULT as COUPON
from apothecary.slicer import service
from apothecary.slicer.profiles import load_part

client = TestClient(app)
WHERE = ["--site", "garage", "--printer", "printer_1"]
PLANTED = {"scale_x": 0.004, "scale_y": 0.004, "contour": 0.08, "hole": 0.1, "foot": 0.12}


def _box_stl(x: float, y: float, z: float) -> bytes:
    facets = (((0, 0, 0), (x, 0, 0), (x, y, 0)), ((0, 0, z), (0, y, z), (x, y, z)))
    lines = ["solid box"]
    for facet in facets:
        lines += ["facet normal 0 0 0", "outer loop"]
        lines += [f"vertex {a} {b} {c}" for a, b, c in facet]
        lines += ["endloop", "endfacet"]
    return ("\n".join(lines + ["endsolid box"]) + "\n").encode()


@pytest.fixture(autouse=True)
def garage(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    sites.store.reset("garage")
    real = service.part_target

    def part_target(name, site=None, path=None, variant=None):
        target = real(name, site=site, path=path, variant=variant)
        b = load_part(name).get_bounds().size
        target.stl = lambda log: _box_stl(b.x, b.y, b.z)
        return target

    monkeypatch.setattr(service, "part_target", part_target)
    yield
    sites.store.reset("garage")


def _slice() -> str:
    r = client.post(
        "/slicer/slice", json={"part": "print_coupon", "site": "garage", "printer": "printer_1"}
    )
    task = r.json()
    deadline = time.monotonic() + 20
    while task["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.05)
        task = client.get(f"/slicer/tasks/{task['id']}").json()
    assert task["status"] == "succeeded", task["lines"]
    return task["slice"]["record"]["file_id"]


def _run(*args):
    result = CliRunner().invoke(cli, ["tuning", *args])
    return result


def test_the_plan_says_what_to_read_and_what_it_separates():
    out = _run("plan", "print_coupon")
    assert out.exit_code == 0, out.output
    assert " 1. plate_x" in out.output and "outside jaws" in out.output
    assert "separates: scale_x, scale_y, scale_z, contour, hole, foot, first" in out.output
    box = _run("plan", "calibration_cube")
    assert "names no plan: read by its box" in box.output
    assert "separates: nothing" in box.output


def test_a_turn_is_kept_explained_applied_read_again_and_undone(fake_orcaslicer, tmp_path):
    first = _slice()
    reads = {
        f.name: f.nominal + pt.predicted(f.feature(), PLANTED) for f in COUPON.measures().features
    }
    rows = ["feature,value"] + [
        f"{n},{v + d:.4f}" for n, v in reads.items() for d in (-0.005, 0.005)
    ]
    table = tmp_path / "readings.csv"
    table.write_text("\n".join(rows) + "\n")
    out = _run("turn", first, "--csv", str(table), "--explain")
    assert out.exit_code == 0, out.output
    assert out.output.startswith("turn-1: print_coupon read at 16 features")
    assert "xy_contour_compensation +0.000 mm -> -0.040 mm" in out.output
    assert "Design matrix" in out.output and "| a_pocket_x | 12 | 0 | 0 | 0 | -2 |" in out.output
    assert "z_offset: said, not applied" in out.output

    shown = _run("show", *WHERE, "--format", "json")
    doc = json.loads(shown.output)
    assert doc["schema"] == "print/tuning/1" and doc["settings"] == {}

    applied = _run("apply", *WHERE)
    assert applied.exit_code == 0, applied.output
    assert "xy_contour_compensation: 0 -> -0.04 mm" in applied.output

    second = _slice()
    moved = dict(PLANTED, contour=0.04, hole=0.05, foot=0.06)
    read = [
        (f.name, f.nominal + pt.predicted(f.feature(), moved))
        for f in COUPON.measures().features
        if f.kind != "wall"
    ]
    out = _run(
        "turn",
        second,
        *[f"--read={name}={v - 0.002:.4f},{v + 0.002:.4f}" for name, v in read],
        "--repeatability",
        "0.005",
    )
    assert out.exit_code == 0, out.output
    turn = json.loads(_run("show", *WHERE, "--format", "json").output)["turns"][1]
    assert [len(r["values"]) for r in turn["readings"]] == [2] * 15
    assert turn["instrument"]["repeatability"] == 0.005
    history = _run("history", *WHERE)
    assert (
        "xy_contour_compensation (contour): turn-1 +0.080 mm *, turn-2 +0.040 mm" in history.output
    )
    assert "  shrinking:" in history.output

    undone = _run("undo", *WHERE)
    assert undone.output.startswith(
        "turn-2 undone; the next slices take xy_contour_compensation -0.04"
    )

    kept = tmp_path / "doc.json"
    kept.write_text(_run("show", *WHERE, "--format", "json").output)
    assert _run("validate", str(kept)).output.startswith("OK print/tuning/1 · garage's printer_1")
    broken = json.loads(kept.read_text())
    broken["turns"] = []
    kept.write_text(json.dumps(broken))
    refused = _run("validate", str(kept))
    assert refused.exit_code == 1 and "no turn of this document" in refused.output


def test_a_reading_the_piece_cannot_have_is_refused_and_nothing_kept(fake_orcaslicer):
    file_id = _slice()
    out = _run("turn", file_id, "--read", "a_x=25")
    assert out.exit_code == 1 and "further off than 1 mm" in out.output
    assert _run("show", *WHERE).exit_code == 2  # no document to show
    assert "properties" in json.loads(_run("schema").output)
