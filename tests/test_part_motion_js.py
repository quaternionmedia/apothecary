"""The page's arithmetic between two rows of a motion's table (apothecary/static/part_motion.js),
run in node and held to apothecary/motion.py, which made the rows.

The page computes nothing of a part: it takes each pose in proportion between the rows
either side, and shows a gap as the nearest row says it. These tests give node the real
tables of the parts that declare a motion and compare what it answers between and at the
samples with what motion.py answers, and the place it gives a piece with gap_geometry's
own placing of the piece's middle, turned into three.js's axes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from apothecary.gap_geometry import Pose
from apothecary.motion import bracket, interpolate, nearest, table
from apothecary.projects.parts import cycloidal_disc, flexure_rotor, rolling_rotor

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "apothecary" / "static" / "part_motion.js"
NODE = shutil.which("node") or str(Path.home() / ".local" / "bin" / "node")

pytestmark = pytest.mark.skipif(not Path(NODE).exists(), reason="node is not installed")

PARTS = {
    "rolling_rotor": rolling_rotor.DEFAULT,
    "flexure_rotor": flexure_rotor.DEFAULT,
    "cycloidal_disc": cycloidal_disc.DEFAULT,
}

SCRIPT = """
import * as m from "%(module)s";
const tables = %(tables)s, values = %(values)s;
const out = {};
for (const [name, t] of Object.entries(tables)) {
    out[name] = {
        bracket: values[name].map((v) => m.bracket(t.samples, v)),
        nearest: values[name].map((v) => m.nearest(t.samples, v)),
        poses: t.pieces.map((p) => values[name].map((v) => m.poseAt(t, p, v))),
        cycled: t.pieces.map((p) => m.poseAt(t, p, t.samples[3], 2)),
        outlines: t.bent.map((b) => values[name].map((v) => m.outlinesAt(t, b, v))),
        gaps: values[name].map((v) => m.gapsAt(t, v).map((g) => [g.sample, g.least, g.marks.length])),
        placed: t.pieces.map((p) => m.placeIn(m.poseAt(t, p, 37.5), [3, -2, 7], [1, 4, 2])),
        steps: [m.stepFrom(t, t.samples[2], 1), m.stepFrom(t, t.samples[2], -1), m.stepFrom(t, t.samples[0], -1),
                m.stepFrom(t, t.samples[t.samples.length - 1], 1), m.stepFrom(t, (t.samples[4] + t.samples[5]) / 2, 1)],
    };
}
const cyc = { range: [0, 360], cyclic: true }, rock = { range: [-8, 8], cyclic: false };
out.advance = {
    round: m.advance(cyc, { value: 350, cycle: 0, way: 1 }, 1, 6),
    back: m.advance(cyc, { value: 10, cycle: 2, way: -1 }, 1, 6),
    bounce: m.advance(rock, { value: 7, cycle: 0, way: 1 }, 1, 8),
    floor: m.advance(rock, { value: -7, cycle: 0, way: -1 }, 1, 8),
};
console.log(JSON.stringify(out));
"""


def _values(t):
    """Each sample, each middle between two, and a few beyond the ends."""
    s = t["samples"]
    mids = [(a + b) / 2 for a, b in zip(s, s[1:], strict=False)]
    quarter = [a + (b - a) / 4 for a, b in zip(s, s[1:], strict=False)][::7]
    return s[::5] + mids[::3] + quarter + [s[0] - 3, s[-1] + 3]


@pytest.fixture(scope="module")
def tables():
    made = {}
    for name, part in PARTS.items():
        values = part.params_model().model_dump()
        made[name] = table(part.motion(values), values)
    return made


@pytest.fixture(scope="module")
def result(tables, tmp_path_factory):
    folder = tmp_path_factory.mktemp("part_motion")
    module = folder / "part_motion.mjs"
    module.write_text(MODULE.read_text(encoding="utf-8"), encoding="utf-8")
    script = folder / "run.mjs"
    values = {name: _values(t) for name, t in tables.items()}
    script.write_text(
        SCRIPT
        % {"module": module.as_uri(), "tables": json.dumps(tables), "values": json.dumps(values)},
        encoding="utf-8",
    )
    done = subprocess.run([NODE, str(script)], capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr
    return values, json.loads(done.stdout)


@pytest.mark.parametrize("name", list(PARTS))
def test_between_two_rows_the_page_takes_what_motion_py_takes(name, tables, result):
    values, out = result
    t = tables[name]
    got = out[name]
    for v, b, n in zip(values[name], got["bracket"], got["nearest"], strict=True):
        i, f = bracket(t["samples"], v)
        assert b[0] == i and b[1] == pytest.approx(f, abs=1e-12)
        assert n == nearest(t["samples"], v)
    for piece, rows in zip(t["pieces"], got["poses"], strict=True):
        for v, row in zip(values[name], rows, strict=True):
            assert row == pytest.approx(interpolate(t["samples"], piece["poses"], v), abs=1e-9)
    for bent, shapes_at in zip(t["bent"], got["outlines"], strict=True):
        for v, shapes in zip(values[name], shapes_at, strict=True):
            i, f = bracket(t["samples"], v)
            j = min(i + 1, len(bent["outlines"]) - 1)
            for s, shape in enumerate(shapes):
                for k, (x, y) in enumerate(shape):
                    a, b = bent["outlines"][i][s][k], bent["outlines"][j][s][k]
                    assert x == pytest.approx(a[0] + f * (b[0] - a[0]), abs=1e-9)
                    assert y == pytest.approx(a[1] + f * (b[1] - a[1]), abs=1e-9)


@pytest.mark.parametrize("name", list(PARTS))
def test_a_gap_shown_is_the_nearest_rows_and_a_cycle_turns_on_by_its_per_cycle(name, tables, result):
    values, out = result
    t = tables[name]
    for v, gaps in zip(values[name], out[name]["gaps"], strict=True):
        i = nearest(t["samples"], v)
        assert [(g[0], g[1], g[2]) for g in gaps] == [(i, gap["least"][i], len(gap["marks"][i])) for gap in t["gaps"]]
    for piece, cycled in zip(t["pieces"], out[name]["cycled"], strict=True):
        row = piece["poses"][3]
        assert cycled == pytest.approx([row[0], row[1], row[2] + 2 * piece["per_cycle"]], abs=1e-9)


@pytest.mark.parametrize("name", list(PARTS))
def test_a_pieces_place_is_its_middle_where_its_pose_puts_it_in_three_js_axes(name, tables, result):
    """placeIn puts a piece drawn centred on [3, -2, 7] (its own frame) where its pose
    puts that point, less the still piece's middle [1, 4, 2], in three.js's axes, and
    turns it about three.js's y by the pose's turn."""
    values, out = result
    t = tables[name]
    for piece, placed in zip(t["pieces"], out[name]["placed"], strict=True):
        x, y, turn = interpolate(t["samples"], piece["poses"], 37.5)
        (px, py), = Pose(x, y, turn).place([(3.0, -2.0)])
        want = (px - 1, 7 - 2, -(py - 4))
        assert placed["position"] == pytest.approx(list(want), abs=1e-9)
        assert placed["angle"] == pytest.approx(turn * 3.141592653589793 / 180, abs=1e-12)


def test_it_steps_sample_by_sample_and_holds_at_the_ends(tables, result):
    _, out = result
    for name, t in tables.items():
        s = t["samples"]
        assert out[name]["steps"] == pytest.approx([s[3], s[1], s[0], s[-1], s[5]])


def test_playing_goes_round_a_cycle_again_and_rocks_anything_else_back_and_forth(result):
    _, out = result
    a = out["advance"]
    # 360 degrees in 6 seconds: a second on from 350 is 50 into the next cycle.
    assert a["round"] == {"value": pytest.approx(50.0), "cycle": 1, "way": 1}
    assert a["back"] == {"value": pytest.approx(310.0), "cycle": 1, "way": -1}
    # 16 degrees in 8 seconds: a second on from 7 is 9, 1 past the end, so back to 7.
    assert a["bounce"] == {"value": pytest.approx(7.0), "cycle": 0, "way": -1}
    assert a["floor"] == {"value": pytest.approx(-7.0), "cycle": 0, "way": 1}
