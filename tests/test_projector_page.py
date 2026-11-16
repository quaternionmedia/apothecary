"""The projector's page (templates/projector.html.j2, static/projector.js): black, one
canvas and nothing else to press, served for a machine and refused for anything else;
its numbers -- the mapping applied, the grid, the markers, what a change of the stream
is to it -- are the server's, run here under node against apothecary/homography.py.

What it draws on a canvas, how it follows a machine and how a drag keeps a calibration
need a browser: tests/e2e/test_projector_page.py."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apothecary import projector, stays_local
from apothecary.api import app
from apothecary.homography import apply

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "apothecary" / "static"
NODE = shutil.which("node")
client = TestClient(app)


def test_the_page_is_black_and_one_canvas():
    page = client.get("/projector/sites/garage/machines/printer_1")
    assert page.status_code == 200
    assert page.headers["content-security-policy"] == stays_local.CONTENT_SECURITY_POLICY
    html = page.text
    assert re.findall(r"<(canvas|button|input|select|textarea|a|form)\b", html) == ["canvas"]
    assert "background: #000" in html and "from '/static/projector.js'" in html
    assert '"garage"' in html and '"printer_1"' in html
    assert client.get("/static/projector.js").status_code == 200


def test_the_page_is_a_machine_s_and_nothing_else_s():
    assert client.get("/projector/sites/garage/machines/nothing").status_code == 404
    assert client.get("/projector/sites/garage/machines/workbench").status_code == 400
    assert client.get("/projector/sites/nowhere/machines/printer_1").status_code == 404


def _run(tmp_path: Path, body: str) -> dict:
    """``body``, an ES module importing ``/static/...`` as the page does, run under node,
    its last line printed as JSON."""
    hooks = tmp_path / "hooks.mjs"
    hooks.write_text(
        "export async function resolve(specifier, context, next) {\n"
        "  if (specifier.startsWith('/static/'))\n"
        f"    return next(new URL('.' + specifier.slice(7), {json.dumps(STATIC.as_uri() + '/')}).href, context);\n"
        "  return next(specifier, context);\n"
        "}\n",
        encoding="utf-8",
    )
    register = tmp_path / "register.mjs"
    register.write_text(
        "import { register } from 'node:module';\n"
        f"register({json.dumps(hooks.as_uri())});\n",
        encoding="utf-8",
    )
    script = tmp_path / "run.mjs"
    script.write_text(body, encoding="utf-8")
    ran = subprocess.run(
        [NODE, "--import", register.as_uri(), str(script)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=tmp_path,
    )
    assert ran.returncode == 0, ran.stderr
    return json.loads(ran.stdout.strip().splitlines()[-1])


needs_node = pytest.mark.skipif(NODE is None, reason="node runtime required")


@needs_node
def test_the_module_is_javascript_node_accepts():
    ran = subprocess.run([NODE, "--check", str(STATIC / "projector.js")], capture_output=True)
    assert ran.returncode == 0, ran.stderr


@needs_node
def test_the_page_maps_a_point_as_the_server_does(tmp_path):
    bed = projector.starting_points([220.0, 220.0, 250.0])
    lit = [(400.0, 900.0), (1500.0, 880.0), (1400.0, 200.0), (500.0, 220.0)]
    calibration = projector.checked("garage", "printer_1", bed, lit, (1920, 1080), -40.0)
    matrix = [list(row) for row in projector.mapping(calibration)]
    points = [(0.0, 0.0), (110.0, 70.0), (220.0, 220.0), (20.0, -20.0)]
    answer = {"mapping": matrix, "size": [1920, 1080], "moving": {"bed_offset": -40.0}}
    got = _run(
        tmp_path,
        "import * as p from '/static/projector.js';\n"
        f"const a = {json.dumps(answer)};\n"
        f"const points = {json.dumps(points)};\n"
        "console.log(JSON.stringify({\n"
        "  applied: points.map(([x, y]) => p.apply(a.mapping, x, y)),\n"
        "  halved: points.map(([x, y]) => p.toCanvas(a, 960, 540, ...p.onBed(a, x, y))),\n"
        "  known: p.bedKnown(a), unknown: p.bedKnown({ moving: { bed_offset: null } }),\n"
        "}));\n",
    )
    for (x, y), js in zip(points, got["applied"], strict=True):
        assert js == pytest.approx(apply(projector.mapping(calibration), x, y), rel=1e-12)
    # A point of the bed, the bed standing where the poll says, on a canvas half the
    # output's size: the server's bed_to_projector, halved.
    for (x, y), js in zip(points, got["halved"], strict=True):
        u, v = projector.bed_to_projector(calibration, x, y, bed_offset=-40.0)
        assert js == pytest.approx([u / 2, v / 2], rel=1e-12)
    assert got["known"] is True and got["unknown"] is False


@needs_node
def test_the_grid_markers_and_what_a_change_is_to_the_page(tmp_path):
    answer = {
        "picture": {"key": "k1"},
        "calibration": None,
        "starting_points": [[20, 20], [200, 20], [200, 200], [20, 200]],
    }
    kept = {
        **answer,
        "calibration": {"bed": [[1, 2], [3, 4], [5, 6], [7, 9]], "pixels": [[0, 0], [100, 0], [100, 50], [0, 50]], "size": [200, 100]},
    }
    got = _run(
        tmp_path,
        "import * as p from '/static/projector.js';\n"
        f"const a = {json.dumps(answer)}, k = {json.dumps(kept)};\n"
        "const change = (key, picture) => ({ surface: 'projector', key, body: { key: picture, moving: {} } });\n"
        "console.log(JSON.stringify({\n"
        "  grid: p.gridLines([25, 10]),\n"
        "  start: p.startingMarkers(a, 800, 400), scaled: p.startingMarkers(k, 400, 200),\n"
        "  takes: [p.take(a, change('garage/printer_1', 'k1'), 'garage/printer_1'),\n"
        "          p.take(a, change('garage/printer_1', 'k2'), 'garage/printer_1'),\n"
        "          p.take(a, change('garage/cnc_router', 'k2'), 'garage/printer_1'),\n"
        "          p.take(null, change('garage/printer_1', 'k1'), 'garage/printer_1'),\n"
        "          p.take(a, { surface: 'jobs', key: 'garage/printer_1' }, 'garage/printer_1')],\n"
        "  body: p.calibrationBody(a, [[-5, 10], [900, 20], [300.123, 450], [10, 10]], 800, 400),\n"
        "  bodyKept: p.calibrationBody(k, [[1, 1], [2, 2], [3, 3], [4, 4]], 800, 400).bed,\n"
        "}));\n",
    )
    # Every 10 mm of a 25 by 10 floor and its far edges, every fifth line bold.
    assert got["grid"] == [
        [0, 0, 0, 10, True],
        [10, 0, 10, 10, False],
        [20, 0, 20, 10, False],
        [25, 0, 25, 10, False],
        [0, 0, 25, 0, True],
        [0, 10, 25, 10, False],
    ]
    assert got["start"] == [[200, 300], [600, 300], [600, 100], [200, 100]]
    assert got["scaled"] == [[0, 0], [200, 0], [200, 100], [0, 100]]
    assert got["takes"] == ["moved", "again", None, "again", None]
    # The markers kept within the canvas, the bed's points the server's or the kept ones.
    assert got["body"] == {
        "bed": [[20, 20], [200, 20], [200, 200], [20, 200]],
        "pixels": [[0, 10], [800, 20], [300.12, 400], [10, 10]],
        "size": [800, 400],
    }
    assert got["bodyKept"] == [[1, 2], [3, 4], [5, 6], [7, 9]]
