"""Geometry made elsewhere, in a site and in the world: a mesh file read and
placed, a part described by a sidecar, a machine drawn as it is.

Nothing here fetches anything: the files are written by the tests, as a
person would bring them.
"""

from __future__ import annotations

import json
import shutil
from importlib import import_module

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from apothecary import meshes
from apothecary.api import app
from apothecary.cli.main import cli
from apothecary.example_hierarchy import BENCH_BOARDS, create_example_site, validate_garage_layout
from apothecary.hierarchy import Assembly
from apothecary.models.vectors import Vector3D
from apothecary.primitives import Import
from apothecary.projects.parts import ender3
from apothecary.projects.parts.described import DescribedPart, part_from_sidecar
from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.registry import resolve_wrapper_module, scan_projects

BRICK_OBJ = (
    "v 0 0 0\nv 2 0 0\nv 2 1 0\nv 0 1 0\nv 0 0 3\nv 2 0 3\nv 2 1 3\nv 0 1 3\n"
    "f 1 2 3 4\nf 5 6 7 8\nf 1 2 6 5\nf 2 3 7 6\nf 3 4 8 7\nf 4 1 5 8\n"
)


def test_meshes_read_obj_and_stl_measure_and_write(tmp_path):
    """An OBJ with quads is fanned into triangles; a binary STL written from it
    reads back the same; ASCII STL reads too; bounds are the box; a file in
    inches and Y-up is turned into millimetres and Z-up by a rotation."""
    triangles = meshes.read_obj(BRICK_OBJ)
    assert len(triangles) == 12
    assert meshes.bounds(triangles) == ((0.0, 0.0, 0.0), (2.0, 1.0, 3.0))
    out = tmp_path / "brick.stl"
    meshes.write_stl(triangles, out, name="brick")
    assert out.stat().st_size == 84 + 12 * 50
    assert meshes.read_stl(out.read_bytes()) == triangles
    ascii_stl = "solid a\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid a\n"
    assert meshes.read_stl(ascii_stl.encode()) == [
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    ]
    placed = meshes.transform(triangles, scale=25.4, up="y")
    lo, hi = meshes.bounds(placed)
    assert [round(v, 1) for v in lo] == [0.0, -76.2, 0.0]
    assert [round(v, 1) for v in hi] == [50.8, 0.0, 25.4]
    with pytest.raises(meshes.MeshError, match="STEP"):
        meshes.read_mesh(tmp_path / "thing.step")
    with pytest.raises(meshes.MeshError):
        meshes.read_stl(b"not a mesh at all")


def test_import_renders_its_transforms_and_measures_the_file(tmp_path):
    """`Import` carries scale, rotate and translate as OpenSCAD's own nesting,
    and `bounds()` says where the transformed mesh ends up."""
    stl = tmp_path / "brick.stl"
    meshes.write_stl(meshes.read_obj(BRICK_OBJ), stl)
    plain = Import(file=str(stl))
    assert plain.render() == f'import("{stl.as_posix()}", convexity=10);'
    box = plain.bounds()
    assert (box.min_point.x, box.max_point.x, box.max_point.z) == (0.0, 2.0, 3.0)
    moved = Import(file=str(stl), scale=10, rotate=Vector3D(z=90), translate=Vector3D(x=5))
    assert moved.render() == (
        f'translate([5.0, 0.0, 0.0]) rotate([0.0, 0.0, 90.0]) scale(10.0) import("{stl.as_posix()}", convexity=10);'
    )
    box = moved.bounds()  # 20 x 10 x 30, turned a quarter: -10..0 in x, 0..20 in y, then +5 in x
    assert [
        round(v, 6) for v in (box.min_point.x, box.min_point.y, box.max_point.x, box.max_point.y)
    ] == [-5.0, 0.0, 5.0, 20.0]
    # A node whose part is its body and holds a child renders the import and the child.
    site = Assembly(
        name="s",
        children=[
            Assembly(
                name="box_with_a_thing_in_it",
                base=None,
                part_ref="calibration_cube",
                children=[Assembly(name="thing", base=Import(file=str(stl)))],
            )
        ],
    )
    rendered = site.render()
    # The part's STL is a build artifact: on a fresh clone it is not there yet,
    # and the render says so instead of failing -- the child still renders.
    if (ROOT / "parts" / "calibration_cube" / "calibration_cube.stl").exists():
        assert 'import("parts/calibration_cube/calibration_cube.stl"' in rendered
    else:
        assert "apothecary parts generate-stl calibration_cube" in rendered
    assert f'import("{stl.as_posix()}"' in rendered
    # JSCAD, which cannot import a mesh, stands it in as the box it fits.
    from apothecary.jscad import _render_node

    assert _render_node(plain).startswith("cuboid({size: [2.0, 1.0, 3.0]")


def test_a_part_described_by_a_sidecar_is_a_part(tmp_path):
    """A folder under parts/ with a SCAD and a part.json, and no Python module,
    is found by the registry, imported by name, and served by the API."""
    folder = ROOT / "parts" / "zz_described_test"
    try:
        folder.mkdir()
        (folder / "zz_described_test.scad").write_text("cube([3, 4, 5]);\n", encoding="utf-8")
        (folder / "part.json").write_text(
            json.dumps(
                {
                    "description": "a test part",
                    "category": "testing",
                    "tags": ["described"],
                    "preview_color": [0.1, 0.2, 0.3],
                    "bounds": {"min": [0, 0, 0], "max": [3, 4, 5]},
                    "source": {"author": "A Person", "license": "CC0-1.0", "units": "mm"},
                }
            ),
            encoding="utf-8",
        )
        found = next(p for p in scan_projects(ROOT) if p.name == "zz_described_test")
        assert found.wrapper == "apothecary.projects.parts.described.zz_described_test"
        module = import_module(resolve_wrapper_module("zz_described_test", ROOT))
        part = module.DEFAULT
        assert isinstance(part, DescribedPart)
        assert part.category == "testing" and part.tags == ["described"]
        assert part.source.license == "CC0-1.0" and part.exists
        assert part.get_bounds().max_point == Vector3D(x=3, y=4, z=5)
        assert part_from_sidecar(folder / "zz_described_test.scad").name == "zz_described_test"
        client = TestClient(app)
        listed = client.get("/parts").json()
        names = {
            p["name"] for p in (listed if isinstance(listed, list) else listed.get("parts", []))
        }
        assert "zz_described_test" in names
        assert client.get("/parts/zz_described_test").status_code == 200
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    with pytest.raises(ModuleNotFoundError):
        import_module("apothecary.projects.parts.described.zz_described_test_gone")


def test_parts_import_brings_a_file_in_as_a_part(tmp_path):
    """`apothecary parts import` turns an OBJ in inches, Y-up, into a part in
    millimetres, Z-up, with its provenance recorded and its bounds measured."""
    source = tmp_path / "brick.obj"
    source.write_text(BRICK_OBJ, encoding="utf-8")
    folder = ROOT / "parts" / "zz_imported_brick"
    try:
        result = CliRunner().invoke(
            cli,
            [
                "parts",
                "import",
                str(source),
                "--name",
                "zz_imported_brick",
                "--units",
                "in",
                "--up",
                "y",
                "--title",
                "A brick",
                "--author",
                "Someone",
                "--license",
                "CC-BY-4.0",
                "--url",
                "https://example.org/brick",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "50.8 x 76.2 x 25.4 mm" in result.output
        assert (folder / "zz_imported_brick.mesh.stl").is_file()
        assert (
            folder / "zz_imported_brick.stl"
        ).is_file()  # the render, for the viewer, without OpenSCAD
        assert (
            'import("zz_imported_brick.mesh.stl"' in (folder / "zz_imported_brick.scad").read_text()
        )
        sidecar = json.loads((folder / "part.json").read_text())
        assert sidecar["source"]["url"] == "https://example.org/brick"
        assert sidecar["source"]["units"] == "in" and sidecar["source"]["up"] == "y"
        assert sidecar["bounds"]["max"] == [50.8, 0.0, 25.4] or sidecar["bounds"]["max"] == [
            50.8,
            -0.0,
            25.4,
        ]
        tag = "SPDX-License-" + "Identifier"  # in halves: REUSE reads a tag anywhere in a file
        assert f"{tag}: CC-BY-4.0" in (folder / "zz_imported_brick.mesh.stl.license").read_text()
        part = import_module(resolve_wrapper_module("zz_imported_brick", ROOT)).DEFAULT
        assert part.source.author == "Someone" and part.category == "imported"
        assert round(part.get_bounds().size.y, 1) == 76.2
        again = CliRunner().invoke(
            cli, ["parts", "import", str(source), "--name", "zz_imported_brick"]
        )
        assert again.exit_code != 0 and "--force" in again.output
        # A node in a site can be that part, and the site renders it.
        site = Assembly(
            name="s",
            children=[Assembly(name="brick", part_ref="zz_imported_brick", position=Vector3D(x=1))],
        )
        assert 'import("parts/zz_imported_brick/zz_imported_brick.stl"' in site.render()
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    refused = CliRunner().invoke(cli, ["parts", "import", str(tmp_path / "x.step")])
    assert refused.exit_code != 0


def test_the_garage_printers_are_ender_3s_drawn_as_they_are():
    """Each printer is the Ender 3 part with its board in the electronics box, its
    build volume where the machine's bed is, its footprint the machine's; the
    boards on the bench are the board models; the layout is still valid."""
    site = create_example_site()
    printers = [s for s in site.children if s.name.startswith("printer_")]
    assert len(printers) == 3
    for printer in printers:
        assert printer.part_ref == "ender3" and printer.base is None
        assert printer.build_volume == Vector3D(x=220, y=220, z=250)
        assert printer.build_origin == ender3.BUILD_ORIGIN == Vector3D(x=90, y=100, z=95)
        assert printer.footprint.min_point == Vector3D(x=-2, y=-41, z=0)
        box = next(c for c in printer.children if c.name == "frame_system")
        board = next(c for c in box.children if c.name == "mainboard")
        assert board.part_ref == "creality_v422" and board.category == "electrical"
        gantry = next(c for c in printer.children if c.name == "gantry_system")
        assert {a.name for a in gantry.additions} == {"left_post", "right_post", "gantry_bar"}
    by_name = {s.name: s for s in site.children}
    assert by_name["esp32_blink"].part_ref == "esp32_devkitc"
    assert by_name["esp32_blink"].sketch_ref == "esp32_blink"
    for name, part, _position, _size in BENCH_BOARDS:
        assert by_name[name].part_ref == part
    assert validate_garage_layout(site).is_valid
    rendered = site.render()
    # STLs are build artifacts; a fresh clone has none yet and the render names
    # what to generate, three times over, instead of importing it.
    for part, path in (
        ("ender3", "parts/ender3/ender3.stl"),
        ("creality_v422", "parts/boards/creality_v422/creality_v422.stl"),
    ):
        if (ROOT / path).exists():
            assert rendered.count(f'import("{path}"') == 3, part
        else:
            assert rendered.count(f"apothecary parts generate-stl {part}") == 3, part
    # The API carries the build origin to the viewers, and the printer is not a board.
    client = TestClient(app)
    tree = client.get("/sites/garage").json()["tree"]
    printer_1 = next(c for c in tree["children"] if c["name"] == "printer_1")
    assert printer_1["part_ref"] == "ender3" and printer_1["build_origin"] == [90.0, 100.0, 95.0]
    # A shape is not a row until a device is pinned to it; the boards that
    # name firmware are rows from the start.
    rows = {r["path"] for r in client.get("/sites/garage/devices").json()["bindings"]}
    assert "esp32_blink" in rows and "footpedal" in rows
    assert not {"printer_1", "arduino_uno", "raspberry_pi_4", "teensy_40"} & rows


def test_the_board_models_are_the_boards_they_say(tmp_path):
    """Every board model's PCB is the published size, at the origin, flat on z = 0
    (or standing on its pins), so a site places it by its corner."""
    expected = {
        "arduino_uno": (68.58, 53.34),
        "raspberry_pi_4": (85.0, 56.0),
        "teensy_40": (35.56, 17.78),
        "esp32_devkitc": (55.0, 28.0),
        "creality_v422": (102.0, 74.0),
    }
    for name, (w, d) in expected.items():
        part = import_module(resolve_wrapper_module(name, ROOT)).DEFAULT
        assert isinstance(part, DescribedPart) and part.category == "electrical"
        text = part.source_file.read_text(encoding="utf-8")
        assert f"size = [{w}, {d}];" in text or f"size = [{int(w)}, {int(d)}];" in text, name
        assert "published" in text.lower()
        stl = part.get_stl_output_path()
        if stl.exists():  # an STL is a build artifact; when it is there, it is the board
            lo, hi = meshes.bounds(meshes.read_mesh(stl))
            assert lo[2] >= -2.0 and hi[0] - lo[0] < w + 20 and hi[1] - lo[1] < d + 10, name
    assert (ROOT / "parts" / "ender3" / "ender3.scad").read_text().count("published") >= 2


def test_the_node_stl_cache_key_follows_the_imported_file(tmp_path, monkeypatch):
    """The same SCAD text over a regenerated mesh is a different render."""
    from apothecary import api

    mesh = ROOT / ".zz_cache_probe.stl"
    try:
        meshes.write_stl(meshes.read_obj(BRICK_OBJ), mesh)
        text = 'import(".zz_cache_probe.stl", convexity=10);'
        first = api._node_stl_cache_paths(text)
        meshes.write_stl(meshes.read_obj(BRICK_OBJ)[:6], mesh)
        second = api._node_stl_cache_paths(text)
        assert first != second
        assert api._node_stl_cache_paths(text) == second
    finally:
        mesh.unlink(missing_ok=True)


FIELD_OF_USE = ("-NC", "-ND", "NonCommercial", "NoDerivatives", "personal")


def test_no_tracked_part_carries_a_licence_the_record_refuses():
    """The open-license record takes OSI-approved or FSF-free licences and no
    field-of-use restriction: a part.json in the repository never names an NC or
    ND licence, and every one that names a licence names it as an SPDX id."""
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", "parts"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    tracked = [rel for rel in tracked if rel.endswith("/part.json")]
    assert tracked, "the boards' sidecars are in the repository"
    for rel in tracked:
        sidecar = json.loads((ROOT / rel).read_text(encoding="utf-8"))
        source = sidecar.get("source") or {}
        licence = source.get("license")
        if licence:
            assert not any(mark.lower() in licence.lower() for mark in FIELD_OF_USE), (rel, licence)
            assert licence.replace(".", "").replace("-", "").replace("+", "").isalnum(), (
                rel,
                licence,
            )
        assert source.get("author") != "Apothecary", (
            "a notice names Quaternion Media, never the tool"
        )
