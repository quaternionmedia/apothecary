"""Shims that level a bed on its solid mounts: the plane through a pair of readings taken
at each screw, the least shims that lift the low corners to the highest, the corners a
layer or the repeatability floor leave without one, what the plane leaves said and
untouched, and the part that draws them."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from apothecary import bed_shims as bs
from apothecary.cli.main import cli
from apothecary.projects.parts.bed_shims import DEFAULT as PART
from apothecary.projects.parts.bed_shims import Params

ROOT = Path(__file__).resolve().parents[1]

CORNERS = (
    bs.Screw("front_left", "FL", 0.0, 0.0),
    bs.Screw("front_right", "FR", 200.0, 0.0),
    bs.Screw("back_right", "BR", 200.0, 200.0),
    bs.Screw("back_left", "BL", 0.0, 200.0),
)
BED = bs.BedScrews(CORNERS, "this test")
AREA = bs.Area(20.0, 20.0, 180.0, 180.0, "this test")


def planted(a: float, b: float, c: float, bow: float = 0.0, n: int = 5):
    """A grid over AREA on the plane a·x + b·y + c, with a bow that is zero on the
    average and on every line through the middle: what no plane takes out."""
    xs = [AREA.x0 + i * (AREA.x1 - AREA.x0) / (n - 1) for i in range(n)]
    ys = [AREA.y0 + j * (AREA.y1 - AREA.y0) / (n - 1) for j in range(n)]
    mid = (n - 1) / 2
    return [
        [a * x + b * y + c + bow * ((i - mid) * (j - mid)) for i, x in enumerate(xs)]
        for j, y in enumerate(ys)
    ]


def nudged(mesh, by: float):
    """``mesh`` with every other point moved by ``by``: a second probe's noise."""
    return [
        [v + (by if (i + j) % 2 else 0.0) for i, v in enumerate(row)] for j, row in enumerate(mesh)
    ]


def by_label(found: bs.Shims, what: str) -> dict:
    return {s.screw.label: getattr(s, what) for s in found.shims}


def test_the_low_corners_are_lifted_to_the_highest_and_it_gets_none():
    found = bs.compute([planted(0.004, -0.0015, 0.2)], BED, AREA)
    assert by_label(found, "height") == pytest.approx(
        {"FL": 0.2, "FR": 1.0, "BR": 0.7, "BL": -0.1}, abs=1e-6
    )
    assert by_label(found, "thickness") == pytest.approx(
        {"FL": 0.8, "FR": 0.0, "BR": 0.3, "BL": 1.1}, abs=1e-6
    )
    assert by_label(found, "printed") == {"FL": 0.8, "FR": None, "BR": 0.3, "BL": 1.1}
    assert by_label(found, "none")["FR"] == bs.NONE_HIGHEST
    level = [s.height + (s.printed or 0) for s in found.shims]
    assert max(level) - min(level) == pytest.approx(0.0, abs=1e-6)
    assert found.residual == pytest.approx((0.0, 0.0, 0.0), abs=1e-6)
    assert found.params() == {"thicknesses": [0.8, 0.3, 1.1], "labels": "FL BR BL"}


def test_a_corner_under_one_layer_gets_none():
    # FL stands 0.15 below FR: no layer prints that.
    found = bs.compute([planted(0.00075, 0.0, 0.0)], BED, AREA)
    assert by_label(found, "none") == {
        "FL": bs.NONE_LAYER, "FR": bs.NONE_HIGHEST, "BR": bs.NONE_HIGHEST, "BL": bs.NONE_LAYER
    }  # fmt: skip
    assert found.params() is None and found.slice_command() is None
    assert found.left == pytest.approx(0.15, abs=1e-6)


def test_the_floor_is_the_most_two_probes_differ_and_a_shim_under_it_is_none():
    first = planted(0.0015, 0.0, 0.0)  # FL 0.3 below the right side
    found = bs.compute([first, nudged(first, 0.35)], BED, AREA)
    assert found.floor == pytest.approx(0.35)
    assert by_label(found, "none")["FL"] == bs.NONE_FLOOR
    single = bs.compute([first], BED, AREA)
    assert single.floor is None and by_label(single, "printed")["FL"] == pytest.approx(0.3)
    assert "not known from one reading" in "\n".join(single.said())


def test_the_pair_s_mean_is_levelled():
    a = planted(0.004, -0.0015, 0.2)
    found = bs.compute([a, nudged(a, 0.02)], BED, AREA)
    want = [v + (0.01 if (i + j) % 2 else 0) for j, r in enumerate(a) for i, v in enumerate(r)]
    assert [v for row in found.mesh for v in row] == pytest.approx(want)
    assert found.floor == pytest.approx(0.02)
    assert by_label(found, "printed") == {"FL": 0.8, "FR": None, "BR": 0.3, "BL": 1.1}


def test_a_bow_is_said_against_the_bound_and_the_shims_do_not_answer_it():
    flat = bs.compute([planted(0.004, 0, 0)], BED, AREA, bound=0.3)
    bowed = bs.compute([planted(0.004, 0, 0, bow=0.05)], BED, AREA, bound=0.3)
    assert by_label(bowed, "thickness") == pytest.approx(by_label(flat, "thickness"))
    assert bowed.residual[:2] == pytest.approx((-0.2, 0.2))
    assert bowed.bow == pytest.approx(0.4)
    said = "\n".join(bowed.said())
    assert "which shims cannot fix: -0.200..+0.200 mm (a range of 0.400)" in said
    assert "the plane alone leaves 0.400, over it, so no shim brings a reading under it" in said
    assert "under it, once the bed is level" in "\n".join(flat.said())


def test_the_shims_in_place_are_replaced_by_a_whole_set():
    first = bs.compute([planted(0.004, -0.0015, 0.2)], BED, AREA)
    fitted = {s.screw.label: s.printed for s in first.shims if s.printed}
    # Fitted, and probed again: level, so the set in place is the set again.
    again = bs.compute([planted(0, 0, 0.5)], BED, AREA, fitted=fitted)
    assert by_label(again, "printed") == by_label(first, "printed")
    # The left side fitted 0.5 and now 0.6 high: it loses its shims, and the right side's
    # 0.1 is under one layer.
    over = bs.compute([planted(-0.003, 0.0, 0.6)], BED, AREA, fitted={"FL": 0.5, "BL": 0.5})
    assert by_label(over, "none") == {
        "FL": bs.NONE_HIGHEST, "FR": bs.NONE_LAYER, "BR": bs.NONE_LAYER, "BL": bs.NONE_HIGHEST
    }  # fmt: skip
    assert by_label(over, "fitted") == {"FL": 0.5, "FR": 0.0, "BR": 0.0, "BL": 0.5}
    with pytest.raises(bs.ShimError, match="no screw is called XX"):
        bs.compute([planted(0, 0, 0)], BED, AREA, fitted={"XX": 1.0})


def test_each_shim_is_printed_on_a_layer():
    found = bs.compute([planted(0.00523, 0.00377, 0)], BED, AREA)
    for s in found.printed:
        layers = (s.printed - bs.FIRST_LAYER) / bs.STEP
        assert layers == pytest.approx(round(layers)) and s.printed >= bs.FIRST_LAYER
        assert abs(s.printed - s.thickness) <= bs.STEP / 2 + 1e-9


@pytest.mark.parametrize(
    "screws, match",
    [
        (CORNERS[:2], "three screws or more"),
        ((*CORNERS[:3], bs.Screw("back_left", "FL", 0, 200)), "one word of its own"),
    ],
)
def test_screws_a_bed_cannot_have_are_refused(screws, match):
    with pytest.raises(bs.ShimError, match=match):
        bs.BedScrews(screws, "t")


def test_three_screws_level_too():
    three = bs.BedScrews((CORNERS[0], CORNERS[1], bs.Screw("back", "B", 100.0, 200.0)), "t")
    found = bs.compute([planted(0.004, -0.0015, 0.2)], three, AREA)
    level = [s.height + s.thickness for s in found.shims]
    assert max(level) - min(level) == pytest.approx(0.0, abs=1e-6)
    assert Params(**found.params())


def test_readings_of_other_grids_are_refused():
    with pytest.raises(bs.ShimError, match="grids differ"):
        bs.compute([planted(0, 0, 0), planted(0, 0, 0, n=3)], BED, AREA)
    with pytest.raises(bs.ShimError, match="two by two"):
        bs.grid_points([[0.1, 0.2]], AREA)


def test_the_estimate_is_the_viewer_s():
    """The grid is placed where the Bed mesh layer draws it: the same inset."""
    js = (ROOT / "apothecary" / "static" / "machine_marks.js").read_text(encoding="utf-8")
    inset = float(re.search(r"const MESH_INSET = ([\d.]+);", js).group(1))
    assert inset == bs.MESH_INSET
    area = bs.grid_area_estimate([220, 220, 250], {"x": -44, "y": -10, "z": -3.15})
    assert (area.x0, area.y0, area.x1, area.y1) == (10, 10, 166, 200)
    assert bs.grid_area_estimate([220, 220], {"x": 30, "y": 0}).x0 == 40


def test_a_probe_that_said_its_points_places_the_grid():
    """A printer's reading whose probe said where each point lies (G29 V3) is placed
    there, not by the estimate, and the shims say so."""
    from apothecary.firmware.models import BedReading

    probed = BedReading(
        method="probe",
        mesh=[[0.0, 0.1], [0.2, 0.3]],
        points=[[10.0, 10.0, 0.0], [176.0, 10.0, 0.1], [176.0, 210.0, 0.3], [10.0, 210.0, 0.2]],
        area={"min": {"x": 10.0, "y": 10.0}, "max": {"x": 176.0, "y": 210.0}},
    )
    area = bs.grid_area(None, probed)
    assert (area.x0, area.y0, area.x1, area.y1) == (10.0, 10.0, 176.0, 210.0)
    assert area.source == "the points its probe said it touched"


def test_a_run_says_whether_it_was_heated():
    at = datetime(2026, 9, 26, 21, 8, tzinfo=timezone.utc)
    cold = bs.Run("r1", at, "probe", 15.04)
    hot = bs.Run("r2", at, "probe", 60.2, "heated 60 C, soaked 10 min, 1 of 2")
    assert (cold.heated, hot.heated, bs.Run("r3").heated) == (False, True, None)
    assert cold.said() == "r1 (probe, 2026-09-26 21:08 UTC, bed 15.04 °C, cold)"
    assert hot.said().endswith("heated, 'heated 60 C, soaked 10 min, 1 of 2')")
    found = bs.compute([planted(0.004, 0, 0)], BED, AREA, runs=[cold])
    assert "a cold reading" in "\n".join(found.said())


# --- the part ------------------------------------------------------------------------


def test_the_part_takes_the_shell_s_words_and_gives_the_scad_a_list():
    p = PART.validate_overrides({"thicknesses": "0.8,0.3,1.1", "labels": "FL BR BL"})
    assert p["thicknesses"] == [0.8, 0.3, 1.1]
    assert PART.scad_overrides(p)["labels"] == ["FL", "BR", "BL"]
    # The SCAD's list, as its text in the page reads it, is the same words.
    assert Params(labels=["FL", "BR", "BL"]).labels == "FL BR BL"


@pytest.mark.parametrize(
    "given, match",
    [
        ({"thicknesses": [1.0, 1.2], "labels": "FL FR BL"}, "one label per shim"),
        ({"thicknesses": [1.0, 1.2], "labels": "FL FL"}, "its own"),
        ({"thicknesses": [0.1], "labels": "A"}, "0.2 to 10 mm"),
        ({"thicknesses": [0.5], "labels": 'A"'}, "letters and digits"),
        ({"hole_d": 9, "outer_d": 10}, "under 1 mm of ring"),
        ({"tab_t": 0.7, "label_depth": 0.6}, "a shallower label"),
    ],
)
def test_shims_the_part_cannot_draw_are_refused(given, match):
    with pytest.raises(ValueError, match=match):
        Params(**given)


def test_the_bounds_are_the_column_of_shims():
    box = PART.get_bounds({"thicknesses": [0.3, 2.5, 0.8], "labels": "A B C", "slot": False})
    assert (box.max_point.x, box.max_point.y, box.max_point.z) == (14 + 12, 3 * 12 + 2 * 10, 2.5)
    assert PART.get_bounds({"thicknesses": [0.3], "labels": "A"}).max_point.z == 1.2


def test_the_part_prints_on_tenth_millimetre_layers():
    assert PART.print_settings.layer_height == bs.STEP


# --- printer_1, read from a state folder of the test's own ------------------------------


def _bench(state: Path, readings, board="A106ZTEU", path="printer_1.frame_system.mainboard"):
    state.mkdir(parents=True, exist_ok=True)
    (state / "firmware-state.json").write_text(
        json.dumps(
            {
                "bindings": [
                    {"site": "garage", "path": path, "identity": board,
                     "bound_at": "2026-11-16T02:03:41Z", "kind": "printer"}
                ]
            }
        ),
        encoding="utf-8",
    )  # fmt: skip
    folder = state / "leveling"
    folder.mkdir()
    for rid, when, bed_c, rows in readings:
        (folder / f"{rid}.json").write_text(
            json.dumps(
                {"id": rid, "port": "/dev/ttyUSB1", "board": board, "machine": "printer",
                 "at": when, "method": "probe", "mesh": rows, "bed_c": bed_c,
                 "probe_offset": {"x": -44.0, "y": -10.0, "z": -3.15}}
            ),
            encoding="utf-8",
        )  # fmt: skip


def _run(command, *args):
    return CliRunner().invoke(
        cli, ["bed", command, "--site", "garage", "--printer", "printer_1", *args]
    )


TILTED = [[0.0, 0.3, 0.6], [0.0, 0.3, 0.6], [0.0, 0.3, 0.6]]
LEVEL = [[0.0] * 3 for _ in range(3)]


def test_printer_1_s_profile_holds_four_screws():
    from apothecary.slicer.profiles import load_profile

    profile = load_profile("ender3")
    assert [s.label for s in bs.bed_screws(profile).screws] == ["FL", "FR", "BR", "BL"]
    assert bs.range_bound(profile) == 0.3


def test_shims_come_from_the_newest_heated_pair(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    _bench(
        tmp_path / "state",
        [
            ("20260920T100000.000-cold", "2026-09-20T10:00:00Z", 15.0, LEVEL),
            ("20260921T100000.000-hot-1", "2026-09-21T10:00:00Z", 60.1, TILTED),
            ("20260921T100500.000-hot-2", "2026-09-21T10:05:00Z", 60.3, nudged(TILTED, 0.02)),
        ],
    )
    result = _run("shims")
    assert result.exit_code == 0, result.output
    assert (
        "reading 20260921T100500.000-hot-2 (probe, 2026-09-21 10:05 UTC, bed 60.3 °C, heated)"
        in result.output
    )
    assert "reading 20260921T100000.000-hot-1" in result.output
    assert "repeatability floor: 0.020 mm" in result.output
    assert "slice them: uv run apothecary slicer slice bed_shims -p thicknesses=" in result.output
    cold = json.loads(_run("shims", "--reading", "20260920T100000.000-cold", "--json-out").output)
    assert [r["heated"] for r in cold["runs"]] == [False]
    assert cold["params"] is None and cold["slice"] is None
    runs = _run("runs").output.splitlines()
    assert [line.split(" ")[0] for line in runs] == [
        "20260921T100500.000-hot-2", "20260921T100000.000-hot-1", "20260920T100000.000-cold"
    ]  # fmt: skip
    compared = _run(
        "compare", "--before", "20260921T100000.000-hot-1", "--after", "20260920T100000.000-cold"
    ).output
    assert "after less before: -0.600..+0.000 mm at any point" in compared


def test_a_single_newest_probe_when_the_pair_is_not_heated(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    _bench(
        tmp_path / "state",
        [
            ("20260921T100000.000-a", "2026-09-21T10:00:00Z", 15.0, LEVEL),
            ("20260921T100500.000-b", "2026-09-21T10:05:00Z", 15.2, TILTED),
            ("20260921T101000.000-c", "2026-09-21T10:10:00Z", 15.2, LEVEL),
        ],
    )
    stored = tmp_path / "state" / "leveling" / "20260921T101000.000-c.json"
    record = json.loads(stored.read_text(encoding="utf-8"))
    stored.write_text(json.dumps({**record, "method": "read"}), encoding="utf-8")
    found = json.loads(_run("shims", "--json-out").output)
    assert [r["id"] for r in found["runs"]] == ["20260921T100500.000-b"]
    assert found["floor"] is None


def test_the_command_says_what_it_lacks(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "state").mkdir()
    result = _run("shims")
    assert result.exit_code != 0 and "no board is pinned at printer_1 in garage" in result.output
    _bench(tmp_path / "other", [], board="OTHER")
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "other"))
    result = _run("shims")
    assert result.exit_code != 0
    assert "OTHER, pinned at printer_1 in garage, has no probe of its bed" in result.output
    assert "--fitted is LABEL=MM" in _run("shims", "--fitted", "FL").output
    assert "has no reading nope" in _run("shims", "--reading", "nope").output


# --- what a shim fits: the bed screw and the mount, kept per machine ---------------------


def test_until_a_mount_is_kept_the_part_s_defaults_stand_and_are_said_to(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    held = bs.mount("garage", "printer_1")
    assert (held.hole_d, held.outer_d, held.hole_kept, held.outer_kept) == (4.6, 12.0, False, False)
    assert held.params() == {}
    assert held.said().startswith("screw hole 4.6 mm (a default), ring 12 mm across (a default)")
    found = bs.compute([planted(0.004, 0, 0)], BED, AREA, mount=held)
    assert "hole_d" not in found.params() and "-p hole_d" not in found.slice_command()
    assert any(
        line.startswith("each shim fits a screw hole 4.6 mm (a default)") for line in found.said()
    )


def test_a_mount_kept_is_the_machine_s_across_a_restart_and_the_slice_takes_it(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    bs.keep_mount("garage", "printer_1", screw="M3")
    half = bs.mount("garage", "printer_1")
    assert (half.hole_d, half.screw, half.hole_kept, half.outer_kept) == (3.4, "M3", True, False)
    assert "ring 12 mm across (a default)" in half.said()
    bs.keep_mount("garage", "printer_1", outer_d=11.8)
    # Read again from the state folder, as a restarted server reads it.
    kept = json.loads((tmp_path / "state" / "bed" / "mounts.json").read_text(encoding="utf-8"))
    assert kept["garage/printer_1"]["hole_d"] == 3.4 and kept["garage/printer_1"]["outer_d"] == 11.8
    whole = bs.mount("garage", "printer_1")
    assert whole.said().startswith("screw hole 3.4 mm (M3), ring 11.8 mm across: kept ")
    found = bs.compute([planted(0.004, 0, 0)], BED, AREA, mount=whole)
    assert found.params()["hole_d"] == 3.4 and found.params()["outer_d"] == 11.8
    assert found.slice_command().endswith(" -p hole_d=3.4 -p outer_d=11.8")
    assert Params(**found.params())
    # A hole typed over the screw's is no longer that screw's preset.
    assert bs.keep_mount("garage", "printer_1", hole_d=3.6).screw is None
    # Another machine keeps its own, and has none yet.
    assert not bs.mount("garage", "cnc_router").hole_kept


@pytest.mark.parametrize(
    "given, match",
    [
        ({"screw": "M5"}, "M3 or M4"),
        ({}, "nothing to keep"),
        ({"outer_d": 5.0}, "not a mount a shim fits"),
        ({"hole_d": 10.0}, "not a mount a shim fits"),
    ],
)
def test_a_mount_no_shim_fits_is_refused_and_nothing_kept(tmp_path, monkeypatch, given, match):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    with pytest.raises(bs.ShimError, match=match):
        bs.keep_mount("garage", "printer_1", **given)
    assert not (tmp_path / "state" / "bed" / "mounts.json").exists()
    with pytest.raises(bs.ShimError, match="has no printer at nowhere"):
        bs.keep_mount("garage", "nowhere", screw="M4")


def test_the_screw_sets_the_hole_and_a_hole_typed_goes_over_it_in_python_and_in_scad():
    from apothecary.projects.parts.bed_shims import SCREW_HOLES

    assert (Params().hole, Params(screw="M3").hole, Params(screw="M3", hole_d=3.6).hole) == (
        4.6,
        3.4,
        3.6,
    )
    scad = (ROOT / "parts" / "bed_shims" / "bed_shims.scad").read_text(encoding="utf-8")
    line = re.search(
        r"^hole = hole_d > 0 \? hole_d : \(screw == \"M3\" \? ([\d.]+) : ([\d.]+)\);", scad, re.M
    )
    assert line and (float(line.group(1)), float(line.group(2))) == (
        SCREW_HOLES["M3"],
        SCREW_HOLES["M4"],
    )
    with pytest.raises(ValueError, match="2 mm or more"):
        Params(hole_d=1.0)
    assert PART.scad_overrides(PART.validate_overrides({"screw": "M3"})) == {"screw": "M3"}


def test_the_command_says_and_keeps_the_mount(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    said = _run("mount").output
    assert said.startswith("printer_1's shims fit a screw hole 4.6 mm (a default)")
    kept = json.loads(_run("mount", "--screw", "M4", "--outer", "13", "--json-out").output)
    assert (kept["hole_d"], kept["outer_d"], kept["hole_kept"], kept["outer_kept"]) == (
        4.6,
        13.0,
        True,
        True,
    )
    assert "M5" in _run("mount", "--screw", "M5").output  # click names the choice refused


# --- what the page draws: GET /bed/{site}/{printer}, PUT .../mount ---------------------


def _four(state: Path):
    """Two heated pairs, the first tilted and the second level after shims, and a cold
    probe before both: what the page's windows draw."""
    _bench(
        state,
        [
            ("20260920T100000.000-cold", "2026-09-20T10:00:00Z", 15.0, TILTED),
            ("20260921T100000.000-before-1", "2026-09-21T10:00:00Z", 60.1, TILTED),
            ("20260921T100500.000-before-2", "2026-09-21T10:05:00Z", 60.3, nudged(TILTED, 0.02)),
            ("20260922T100000.000-after-1", "2026-09-22T10:00:00Z", 60.2, LEVEL),
            ("20260922T100500.000-after-2", "2026-09-22T10:05:00Z", 60.0, nudged(LEVEL, 0.01)),
        ],
    )


def test_the_story_is_the_runs_their_pairs_their_differences_and_the_shims(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    _four(tmp_path / "state")
    told = bs.story("garage", "printer_1")
    assert [r["id"].split("-", 1)[1] for r in told["runs"]] == [
        "after-2", "after-1", "before-2", "before-1", "cold"
    ]  # fmt: skip
    assert [r["heated"] for r in told["runs"]] == [True, True, True, True, False]
    assert told["pairs"] == [
        ["20260922T100000.000-after-1", "20260922T100500.000-after-2"],
        ["20260921T100000.000-before-1", "20260921T100500.000-before-2"],
    ]
    rep = told["differences"]["repeatability"]
    assert rep["of"] == told["pairs"][0] and rep["floor"] == pytest.approx(0.01)
    after = told["differences"]["after"]
    assert (after["before"], after["after"]) == (told["pairs"][1], told["pairs"][0])
    assert min(v for row in after["mesh"] for v in row) < -0.5  # the tilt taken out
    assert told["differences"]["bow"]["bound"] == 0.3
    assert [r["id"] for r in told["shims"]["runs"]] == [
        "20260922T100500.000-after-2", "20260922T100000.000-after-1"
    ]  # fmt: skip
    assert told["mount"]["hole_kept"] is False and told["volume"] == [220, 220]
    assert [s["label"] for s in told["screws"]] == ["FL", "FR", "BR", "BL"]


def test_a_pair_needs_two_heated_probes_one_after_the_other():
    def rec(rid, method, bed_c):
        return type(
            "R",
            (),
            {"id": rid, "method": method, "bed_c": bed_c, "mesh": LEVEL, "at": None, "note": None},
        )()

    found = [
        rec("e", "probe", 60),
        rec("d", "probe", 15),
        rec("c", "probe", 60),
        rec("b", "probe", 60),
        rec("a", "read", 60),
    ]
    assert [[r.id for r in p] for p in bs.heated_pairs(found)] == [["c", "b"]]


def test_the_routes_answer_the_story_and_keep_a_mount(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from apothecary.api import app

    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    _four(tmp_path / "state")
    client = TestClient(app)
    told = client.get("/bed/garage/printer_1").json()
    assert told["shims"]["mount"]["hole_kept"] is False
    kept = client.put("/bed/garage/printer_1/mount", json={"screw": "M3", "outer_d": 11.8})
    assert kept.status_code == 200 and kept.json()["said"].startswith("screw hole 3.4 mm (M3)")
    told = client.get("/bed/garage/printer_1").json()
    assert (told["mount"]["hole_d"], told["mount"]["outer_d"]) == (3.4, 11.8)
    refused = client.put("/bed/garage/printer_1/mount", json={"outer_d": 5})
    assert refused.status_code == 422 and "not a mount a shim fits" in refused.json()["detail"]
    assert client.get("/bed/garage/nowhere").status_code == 404
    assert client.put("/bed/garage/printer_1/mount", json={"screw": "M5"}).status_code == 422


# ---- what a person reads of the shims printed -------------------------------------------

MADE = {"thicknesses": [0.3, 0.8], "labels": "FL BR", "screw": "M3", "outer_d": 11.8}


def test_each_shim_s_thickness_is_read_across_its_ring_and_named_for_its_corner():
    """A height for each shim, in the order of the labels, its nominal the shim's
    thickness, its line through the ring between the hole and the rim, clear of the slot;
    two labels that would give one name are named by their place instead."""
    import math

    from apothecary.projects.parts.bed_shims import centre

    p = Params(**MADE)
    drawn = PART.measures(MADE)
    assert [(f.name, f.kind, f.axis, f.jaw, f.nominal) for f in drawn.features] == [
        ("shim_fl", "height", "z", "outside", 0.3),
        ("shim_br", "height", "z", "outside", 0.8),
    ]
    for i, f in enumerate(drawn.features):
        cx, cy = centre(p, i)
        out = math.hypot(f.at[0] - cx, f.at[1] - cy)
        assert p.hole / 2 < out < p.outer_d / 2, f.name
        # The slot runs from the hole toward +X, as wide as the hole.
        assert f.at[0] < cx or abs(f.at[1] - cy) > p.hole / 2, f.name
    assert drawn.check() == {"scale_z": True, "first": True}
    assert [f.name for f in PART.measures({"labels": "FL fl BL"}).features] == [
        "shim_1",
        "shim_2",
        "shim_3",
    ]
    assert [f.name for f in PART.measures({"labels": "Ä FL BL"}).features] == [
        "shim_1",
        "shim_2",
        "shim_3",
    ]


def test_the_render_has_each_shim_s_faces_where_the_plan_draws_them(tmp_path):
    from apothecary.meshes import read_mesh
    from apothecary.models.measures import MEASURE_TOLERANCE
    from apothecary.projects.parts.stl_renderer import get_renderer, render_part

    if not get_renderer().is_available:
        pytest.skip("OpenSCAD not installed")
    result = render_part(PART, tmp_path / "bed_shims.stl", params=MADE, timeout=180)
    assert result.success, result.stderr
    triangles = read_mesh(result.stl_path)
    for feature in PART.measures(MADE).features:
        found = feature.read_on(triangles)
        assert found is not None, feature.name
        assert found == pytest.approx(feature.faces, abs=MEASURE_TOLERANCE), feature.name
    # Drawn for other thicknesses than the render's, both are found off.
    other = PART.measures({**MADE, "thicknesses": [0.5, 0.6]})
    assert all(
        f.read_on(triangles) != pytest.approx(f.faces, abs=MEASURE_TOLERANCE)
        for f in other.features
    )
