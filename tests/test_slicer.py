"""The slicer seam: a module finds its program, says what it slices, resolves a
slice's values with where each came from, and a slice keeps its G-code where the
Print card keeps a file -- against a scripted OrcaSlicer (tests/slicer_helpers.py).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from slicer_helpers import fake_calls, write_fake_orcaslicer

from apothecary.cli.main import cli
from apothecary.firmware import devices
from apothecary.models import PrintSettings
from apothecary.slicer import service
from apothecary.slicer.models import Made
from apothecary.slicer.modules import (
    NotInstalled,
    SlicerError,
    chosen_id,
    get_module,
    modules,
)
from apothecary.slicer.modules.orcaslicer import TOOL, read_estimate, seconds_of
from apothecary.slicer.profiles import Declared, load_profile, printers

ROOT = Path(__file__).resolve().parents[1]

# A 10 mm cube, as an STL: what a part's build would hand the slicer.
CUBE_STL = b"solid cube\nendsolid cube\n"


def _target(declared: dict | None = None, name: str = "calibration_cube") -> service.Target:
    settings = PrintSettings(**declared) if declared is not None else None
    return service.Target(
        made=Made(kind="part", name=name),
        declared=Declared.of(settings, f"part {name}"),
        stl=lambda log: CUBE_STL,
    )


def _slice(target, log=None, **kw):
    lines = [] if log is None else log
    printer = service.printer_named("ender3")
    return service.slice_into(target, printer, service.Here(lines.append), **kw), lines


def _by_name(record_or_settings):
    settings = getattr(record_or_settings, "settings", record_or_settings)
    return {s.name: s for s in settings}


# --- the module: what it slices, and where its program is ----------------------------


def test_orcaslicer_is_the_one_module_and_says_what_it_slices(
    fake_orcaslicer, tmp_path, monkeypatch
):
    (module,) = modules()
    assert module.id == "orcaslicer" and module.label == "OrcaSlicer"
    here = tmp_path / "here"
    here.mkdir()
    monkeypatch.chdir(here)
    status = module.status()
    # OrcaSlicer writes a result.json wherever it runs, even for --help: not here.
    assert list(here.iterdir()) == []
    assert (status.technology, status.inputs, status.writes) == ("FFF", [".stl"], [".gcode"])
    assert status.pinned == "2.4.2" and status.install == "apothecary slicer install"
    assert status.ok and status.tool.version == "2.4.2"
    assert status.tool.found_by == "APOTHECARY_ORCASLICER"
    assert status.profiles == str(fake_orcaslicer.parent.parent / "resources" / "profiles")


def test_the_program_is_the_variable_then_the_tools_dir_then_path(tmp_path, monkeypatch):
    from apothecary.slicer import orcaslicer_installer as oi

    tools = tmp_path / "tools"
    monkeypatch.setenv("APOTHECARY_TOOLS_DIR", str(tools))
    on_path = write_fake_orcaslicer(tmp_path / "on-path")
    monkeypatch.setenv("PATH", str(on_path.parent))
    monkeypatch.delenv("APOTHECARY_ORCASLICER", raising=False)
    assert TOOL.find() == (on_path, "PATH")
    # An install in the tools dir: install.json names the program, current the release.
    release = tools / "orcaslicer" / "2.4.2"
    installed = write_fake_orcaslicer(release / "squashfs-root")
    (release / "install.json").write_text(
        json.dumps(
            {
                "executable": "squashfs-root/bin/orca-slicer",
                "resources": "squashfs-root/resources",
                "method": "appimage-extracted",
            }
        )
    )
    (tools / "orcaslicer" / "current").write_text("2.4.2\n")
    assert oi.current_executable() == installed
    assert TOOL.find() == (installed, "tools dir")
    named = write_fake_orcaslicer(tmp_path / "named")
    monkeypatch.setenv("APOTHECARY_ORCASLICER", str(named))
    assert TOOL.find() == (named, "APOTHECARY_ORCASLICER")
    # "none" means none: the browser suites' servers never find a person's own.
    monkeypatch.setenv("APOTHECARY_ORCASLICER", "none")
    assert TOOL.find() == (None, None)
    status = get_module("orcaslicer").status()
    assert not status.ok and status.problems == [
        "OrcaSlicer is not installed: apothecary slicer install"
    ]


def test_an_install_that_names_a_way_out_of_its_folder_names_nothing(tmp_path, monkeypatch):
    from apothecary.slicer import orcaslicer_installer as oi

    monkeypatch.setenv("APOTHECARY_TOOLS_DIR", str(tmp_path / "tools"))
    release = tmp_path / "tools" / "orcaslicer" / "2.4.2"
    release.mkdir(parents=True)
    for bad in ("../../bin/sh", "/bin/sh", "C:/x.exe", "a/../../b"):
        (release / "install.json").write_text(json.dumps({"executable": bad}))
        assert oi.executable_for("2.4.2") is None
    (tmp_path / "tools" / "orcaslicer" / "current").write_text("../../etc\n")
    assert oi.current_version() is None


def test_a_slicer_other_than_the_pinned_one_is_noted_not_refused(
    fake_orcaslicer, tmp_path, monkeypatch
):
    other = tmp_path / "other" / "bin" / "orca-slicer"
    write_fake_orcaslicer(tmp_path / "other")
    other.write_text(other.read_text().replace("OrcaSlicer-2.4.2", "OrcaSlicer-2.3.1"))
    monkeypatch.setenv("APOTHECARY_ORCASLICER", str(other))
    status = get_module("orcaslicer").status()
    assert status.ok and status.tool.version == "2.3.1"
    assert "not the pinned 2.4.2" in status.notes[0]


def test_the_module_used_is_named_then_the_variable_then_the_printers(monkeypatch):
    profile = load_profile("ender3")
    monkeypatch.delenv("APOTHECARY_SLICER", raising=False)
    assert chosen_id(None, profile) == "orcaslicer" == profile.slicer
    monkeypatch.setenv("APOTHECARY_SLICER", "prusaslicer")
    assert chosen_id(None, profile) == "prusaslicer"
    assert chosen_id("cura", profile) == "cura"
    with pytest.raises(SlicerError, match="no slicer 'prusaslicer'"):
        get_module(chosen_id(None, profile))


# --- the printer's profile, kept with its part ------------------------------------------


def test_the_ender3_keeps_its_profile_and_says_where_each_value_came_from():
    assert printers() == ["ender3"]
    profile = load_profile("ender3")
    assert profile.file == "parts/ender3/slicer.json"
    section = profile.section("orcaslicer")
    assert (section["vendor"], section["machine"]) == ("Creality", "Creality Ender-3 0.4 nozzle")
    held = section["set"]["machine"]
    assert held["printable_area"]["value"] == ["0x0", "220x0", "220x220", "0x220"]
    assert held["printable_height"]["value"] == "250"
    assert all(entry["source"] for entry in held.values())
    # The bench's measurements, each with its source and how a slice uses it.
    assert profile.measured["probe_offset"].value == {"x": -44.0, "y": -10.0, "z": -3.15}
    assert "M851" in profile.measured["probe_offset"].source
    assert profile.measured["build_volume"].value == [220, 220, 250]
    assert all(m.source and m.used for m in profile.measured.values())
    # The part's own figures agree with the profile's build volume.
    from apothecary.projects.parts import ender3

    assert [ender3.BUILD.x, ender3.BUILD.y, ender3.BUILD.z] == profile.measured[
        "build_volume"
    ].value


def test_the_probe_offset_is_held_and_not_added_to_the_slicers_z(fake_orcaslicer):
    """The firmware applies M851 when G28 homes Z with the probe; a slicer that added it
    too would drive the nozzle 3.15 mm into the bed."""
    resolved = get_module("orcaslicer").settings(load_profile("ender3"), Declared(by="part x"))
    z = _by_name(resolved)["z_offset"]
    assert z.value == "0" and z.origin == "printer" and "M851 Z-3.15" in z.source
    assert "apply it a second time" in z.note
    assert resolved.configs["machine"]["z_offset"] == "0"


# --- a slice's values, and where each came from -----------------------------------------


def test_a_parts_declared_settings_win_and_the_printer_fills_the_rest(fake_orcaslicer):
    resolved = get_module("orcaslicer").settings(
        load_profile("ender3"),
        Declared.of(
            PrintSettings(nozzle_diameter=0.4, layer_height=0.12, tolerance=0.1), "part cube"
        ),
    )
    shown = _by_name(resolved)
    assert shown["layer_height"].value == "0.12" and shown["layer_height"].origin == "declared"
    assert shown["layer_height"].source == "part cube"
    assert resolved.configs["process"]["layer_height"] == "0.12"
    assert shown["nozzle_diameter"].origin == "declared"
    # wall_thickness was not declared (the model's default is not a declaration).
    assert shown["wall_loops"].origin == "printer" and shown["wall_loops"].value == "2"
    assert "0.20mm Standard @Creality Ender3" in shown["wall_loops"].source
    # The tolerance is the part's geometry's; nothing is passed for it.
    assert shown["tolerance"].origin == "declared"
    assert "not passed to the slicer" in shown["tolerance"].note
    assert "tolerance" not in json.dumps(resolved.configs)
    # Each base profile, flattened along its chain, and named in the answer.
    assert shown["machine profile"].note == (
        "Creality Ender-3 0.4 nozzle < fdm_creality_common < fdm_machine_common"
    )
    assert resolved.configs["machine"]["max_layer_height"] == [
        "0.36"
    ]  # the child's over its parent's
    assert resolved.configs["machine"]["gcode_flavor"] == "marlin"  # the grandparent's


def test_a_declared_wall_thickness_is_as_many_lines_of_the_nozzle_as_reach_it(fake_orcaslicer):
    settings = get_module("orcaslicer").settings
    for thickness, loops in ((1.2, "3"), (3.0, "8"), (0.4, "1"), (1.0, "3")):
        resolved = settings(
            load_profile("ender3"),
            Declared.of(PrintSettings(wall_thickness=thickness), "part tray"),
        )
        wall = _by_name(resolved)["wall_loops"]
        assert (wall.value, wall.origin) == (loops, "declared")
        assert resolved.configs["process"]["wall_loops"] == loops


def test_a_part_asking_for_another_nozzle_or_layers_it_cannot_print_is_refused(fake_orcaslicer):
    settings = get_module("orcaslicer").settings
    with pytest.raises(SlicerError, match="declares a 0.6 mm nozzle.*cannot change a nozzle"):
        settings(load_profile("ender3"), Declared.of(PrintSettings(nozzle_diameter=0.6), "part p"))
    with pytest.raises(SlicerError, match="declares 0.5 mm layers.*prints 0.08 to 0.36 mm"):
        settings(load_profile("ender3"), Declared.of(PrintSettings(layer_height=0.5), "part p"))


def test_the_parts_that_declare_print_settings_declare_only_what_they_set():
    from apothecary.projects.parts import calibration_cube, datum_core

    cube = Declared.of(calibration_cube.DEFAULT.print_settings, "part calibration_cube")
    assert cube.values == {"nozzle_diameter": 0.4, "layer_height": 0.2, "tolerance": 0.1}
    tray = Declared.of(datum_core.DEFAULT.print_settings, "part datum_core")
    assert tray.values["wall_thickness"] == 3.0
    assert Declared.of(None, "piece box").values == {}


def test_a_profile_that_names_no_section_for_the_slicer_or_no_source_is_refused(tmp_path):
    from apothecary.slicer.profiles import read_profile

    path = tmp_path / "slicer.json"
    path.write_text(json.dumps({"slicer": "orcaslicer"}))
    with pytest.raises(SlicerError, match="no 'orcaslicer' section"):
        read_profile("p", path).section("orcaslicer")
    path.write_text("{not json")
    with pytest.raises(SlicerError, match="not a slicer profile"):
        read_profile("p", path)


def test_a_vendor_index_that_points_out_of_its_folder_names_no_profile(tmp_path):
    from slicer_helpers import write_profiles

    from apothecary.slicer.modules.orcaslicer import flatten, vendor_index

    profiles = write_profiles(tmp_path / "resources")
    index = json.loads((profiles / "Creality.json").read_text())
    index["machine_list"].append({"name": "Escape", "sub_path": "../../../etc/passwd"})
    (profiles / "Creality.json").write_text(json.dumps(index))
    found = vendor_index(tmp_path / "resources", "Creality")
    assert "Escape" not in found and "Creality Ender-3 0.4 nozzle" in found
    with pytest.raises(SlicerError, match="no machine profile 'Escape'"):
        flatten(found, "Escape", "machine")
    with pytest.raises(SlicerError, match="not an OrcaSlicer vendor profile name"):
        vendor_index(tmp_path / "resources", "../Creality")


# --- a slice: the G-code kept where the Print card keeps a file --------------------------


def test_a_slice_keeps_its_gcode_in_the_print_cards_file_box_with_its_record(fake_orcaslicer):
    record, lines = _slice(_target({"nozzle_diameter": 0.4, "layer_height": 0.2, "tolerance": 0.1}))
    kept = devices.print_file(record.file_id)
    assert kept is not None and kept.name == "calibration_cube.gcode"
    assert [f.id for f in devices.print_files()] == [record.file_id]
    assert kept.problems == [] and kept.lines == record.lines > 0
    assert record.slicer == "orcaslicer" and record.slicer_version == "2.4.2"
    assert (record.made.kind, record.made.name) == ("part", "calibration_cube")
    assert (record.printer.part, record.printer.name) == ("ender3", "ender3")
    # OrcaSlicer's own estimate, as it wrote it into the G-code.
    e = record.estimate
    assert (e.time, e.seconds, e.first_layer) == ("1h 2m 3s", 3723, "48s")
    assert (e.filament_mm, e.filament_cm3, e.filament_g, e.layers) == (263.81, 0.63, 0.79, 3)
    # Where the extruding moves reach: the square, at the declared layer height.
    assert record.bounds.min == [105.0, 105.0, 0.2] and record.bounds.max == [115.0, 115.0, 0.6]
    assert record.messages == []
    # The record is kept beside the file, and is read back as written.
    assert service.get_record(record.file_id) == record
    assert service.records() == [record]
    # The slicer was handed the three profiles, as user profiles of OrcaSlicer's own.
    (argv,) = [a for a in fake_calls(fake_orcaslicer) if "--slice" in a]
    machine, process = argv[argv.index("--load-settings") + 1].split(";")
    assert argv[argv.index("--arrange") + 1] == "1" and argv[argv.index("--orient") + 1] == "0"
    assert "--ensure-on-bed" in argv and argv[-1].endswith("model.stl")
    assert "Slicing part calibration_cube for ender3" in lines[0]


def test_the_slices_own_folder_is_gone_when_it_ends(fake_orcaslicer):
    _slice(_target())
    work = service.slices_dir() / "work"
    assert work.is_dir() and list(work.iterdir()) == []


def test_a_slice_is_forgotten_with_its_file(fake_orcaslicer):
    record, _ = _slice(_target())
    assert devices.delete_print_file(record.file_id)
    assert service.get_record(record.file_id) is None
    assert not (service.slices_dir() / f"{record.file_id}.json").exists()
    assert service.records() == []
    assert service.get_record("../../etc/passwd") is None


def test_a_failed_slice_says_the_slicers_errors_by_line_and_keeps_nothing(
    fake_orcaslicer, monkeypatch
):
    monkeypatch.setenv("FAKE_ORCA", "outside")
    lines: list = []
    with pytest.raises(service.SliceFailed) as failed:
        _slice(_target(), log=lines)
    exc = failed.value
    assert "OrcaSlicer failed (exit 205)" in str(exc)
    assert "located over the boundary of the heated bed" in str(exc)
    said = [(m.level, m.line, m.text) for m in exc.messages]
    assert ("error", 1, "[error] run found error, return -51, exit...") in said
    assert ("warning", 2, "Warning: the bed is small") in said
    assert (
        "error",
        None,
        "Some objects are located over the boundary of the heated bed. (code -51)",
    ) in said
    assert _by_name(exc.settings)["layer_height"].origin == "printer"
    assert devices.print_files() == []


def test_a_slicer_that_writes_no_gcode_is_a_failure(fake_orcaslicer, monkeypatch):
    monkeypatch.setenv("FAKE_ORCA", "silent")
    with pytest.raises(SlicerError, match="OrcaSlicer wrote no G-code"):
        _slice(_target())
    assert devices.print_files() == []


def test_no_slicer_installed_is_said_before_anything_is_built(fake_orcaslicer, monkeypatch):
    monkeypatch.setenv("APOTHECARY_ORCASLICER", "none")
    built = []
    target = _target()
    target.stl = lambda log: built.append(1) or CUBE_STL
    with pytest.raises(NotInstalled, match="apothecary slicer install"):
        _slice(target)
    assert built == []


def test_a_refused_part_builds_nothing(fake_orcaslicer):
    built = []
    target = _target({"nozzle_diameter": 0.8})
    target.stl = lambda log: built.append(1) or CUBE_STL
    with pytest.raises(SlicerError, match="cannot change a nozzle"):
        _slice(target)
    assert built == [] and fake_calls(fake_orcaslicer) == [["--help"]]


def test_where_the_moves_reach_follows_absolute_and_relative_moves(tmp_path):
    path = tmp_path / "moves.gcode"
    path.write_text(
        "G90\nM82\nG92 E0\nG1 X10 Y10 Z0.2\nG1 X20 E1 ; extrudes\nG1 X30 E1 ; no: E did not grow\n"
        "G91\nG1 Y5 E0.5 ; relative now\nG90\nG1 X200 Y200 ; travel\nG92 E0\nG1 X210 E0.1\n"
    )
    bounds = service.gcode_bounds(path)
    assert bounds.min == [10.0, 10.0, 0.2] and bounds.max == [210.0, 200.0, 0.2]
    path.write_text("G28\nG1 X10 Y10\n")
    assert service.gcode_bounds(path) is None


def test_the_estimate_is_read_from_the_slicers_own_comments(tmp_path):
    path = tmp_path / "e.gcode"
    path.write_text(
        "; HEADER_BLOCK_START\n; total layer number: 50\n; HEADER_BLOCK_END\nG1 X1\n"
        "; filament used [mm] = 263.81, 10.19\n; filament used [g] = 0.79\n"
        "; estimated printing time (normal mode) = 2d 1h 0m 5s\n"
    )
    found = read_estimate(path)
    assert found == {
        "layers": 50,
        "filament_mm": 274.0,
        "filament_g": 0.79,
        "time": "2d 1h 0m 5s",
        "seconds": 176405,
    }
    assert seconds_of("8m 56s") == 536 and seconds_of("") is None


# --- the command line --------------------------------------------------------------------


def test_slicer_status_says_what_each_slicer_slices_and_where_it_is(fake_orcaslicer):
    result = CliRunner().invoke(cli, ["slicer", "status"])
    assert result.exit_code == 0, result.output
    assert "OrcaSlicer (used):" in result.output
    assert "slices .stl into .gcode for FFF printers; pinned 2.4.2" in result.output
    assert f"{fake_orcaslicer} (APOTHECARY_ORCASLICER): 2.4.2" in result.output


def test_slicer_slice_slices_a_part_and_keeps_its_gcode(fake_orcaslicer, monkeypatch):
    monkeypatch.setattr(
        service, "part_target", lambda name, site=None, path=None: _target({"layer_height": 0.12})
    )
    result = CliRunner().invoke(cli, ["slicer", "slice", "calibration_cube", "--json-out"])
    assert result.exit_code == 0, result.output
    record = json.loads(result.output)
    assert devices.print_file(record["file_id"]).name == "calibration_cube.gcode"
    assert {s["name"]: s["origin"] for s in record["settings"]}["layer_height"] == "declared"
    text = CliRunner().invoke(cli, ["slicer", "slice", "calibration_cube"])
    assert text.exit_code == 0, text.output
    assert "orcaslicer estimates 1h 2m 3s, 0.79 g (263.81 mm) of filament, 3 layers" in text.output
    assert "extrudes from (105.0, 105.0, 0.12) to (115.0, 115.0, 0.36)" in text.output


def test_slicer_slice_refuses_a_part_that_is_not_one(fake_orcaslicer):
    result = CliRunner().invoke(cli, ["slicer", "slice", "no_such_part"])
    assert result.exit_code != 0 and "no part named 'no_such_part'" in result.output
    result = CliRunner().invoke(cli, ["slicer", "slice", "calibration_cube", "--printer", "fifel"])
    assert result.exit_code != 0 and "keeps no slicer profile" in result.output


def test_a_part_target_builds_the_parts_own_stl(fake_orcaslicer, monkeypatch, tmp_path):
    from apothecary.projects.parts import stl_renderer
    from apothecary.projects.parts.stl_renderer import RenderResult

    stl = tmp_path / "cube.stl"
    stl.write_bytes(CUBE_STL)
    built = []

    def build_stl(part, params=None, **kw):
        built.append(part.name)
        return RenderResult(success=True, stl_path=stl, skipped="fresh")

    monkeypatch.setattr(stl_renderer, "build_stl", build_stl)
    target = service.part_target("calibration_cube")
    assert target.declared.by == "part calibration_cube"
    assert target.declared.values["layer_height"] == 0.2
    lines: list = []
    assert target.stl(lines.append) == CUBE_STL and built == ["calibration_cube"]
    assert lines == [f"STL: {stl} (up to date)"]
