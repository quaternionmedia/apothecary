"""The datum scaffold: a board description becomes an enclosure and a scene.

These tests pin the seam rather than the numbers. The stub envelope will change
when a board is laid out; what must not change is that swapping the provider
changes the geometry and nothing else, and that a scene can still say which of
its parts nobody has measured.
"""

from __future__ import annotations

import pytest

from apothecary.models import BoundingBox3D, Vector3D
from apothecary.models.blackbox import BlackBox, MountPoint, StubProvider
from apothecary.projects.assemblies import build
from apothecary.projects.parts import datum_core as datum_part
from apothecary.shims.kicad import KiCadProvider, t1_core_stub


def test_stub_board_reports_itself_as_a_stub():
    board = t1_core_stub()
    assert board.is_stub, "a hand-entered envelope must not claim to be measured"
    assert board.source == "stub"


def test_enclosure_is_derived_from_the_board_not_hardcoded():
    small = BlackBox(
        name="small",
        envelope=BoundingBox3D(
            min_point=Vector3D(x=0, y=0, z=0), max_point=Vector3D(x=20, y=15, z=1.6)
        ),
    )
    big = BlackBox(
        name="big",
        envelope=BoundingBox3D(
            min_point=Vector3D(x=0, y=0, z=0), max_point=Vector3D(x=80, y=60, z=1.6)
        ),
    )
    a = datum_part.params_for(small)
    b = datum_part.params_for(big)
    assert b.outer_x > a.outer_x and b.outer_y > a.outer_y
    # The enclosure clears the board on every side by wall + tolerance.
    assert a.outer_x == pytest.approx(20 + 2 * a.board_clearance + 2 * a.walls)


def test_mount_inset_is_taken_from_the_board_geometry():
    board = BlackBox(
        name="m",
        envelope=BoundingBox3D(
            min_point=Vector3D(x=0, y=0, z=0), max_point=Vector3D(x=50, y=50, z=1.6)
        ),
        mounts=[MountPoint(name="m1", position=Vector3D(x=5, y=5, z=0), hole_diameter=3.0)],
    )
    params = datum_part.params_for(board)
    assert params.mount_inset == pytest.approx(5.0)
    assert params.screw_d == pytest.approx(3.0)


def test_a_board_with_no_mounts_still_produces_an_enclosure():
    """Defaults must render something coherent with no knowledge of a PCB."""
    bare = BlackBox(
        name="bare",
        envelope=BoundingBox3D(
            min_point=Vector3D(x=0, y=0, z=0), max_point=Vector3D(x=30, y=30, z=1.6)
        ),
    )
    params = datum_part.params_for(bare)
    assert params.outer_x > 0 and params.outer_z > 0


def test_swapping_the_provider_changes_geometry_and_nothing_else():
    other = StubProvider().register(
        BlackBox(
            name="t1-core",
            envelope=BoundingBox3D(
                min_point=Vector3D(x=0, y=0, z=0), max_point=Vector3D(x=64, y=48, z=1.6)
            ),
            source="datasheet",
        )
    )
    _, default_asm = build()
    _, swapped = build(provider=other)
    assert swapped.params.board_x == pytest.approx(64)
    assert swapped.params.board_x != default_asm.params.board_x
    # Same board name, same placements, different numbers: the seam held.
    assert [p.name for p in swapped.placements] == [p.name for p in default_asm.placements]


def test_scene_places_the_enclosure_the_board_and_the_surface():
    scene, assembly = build()
    assert len(scene.objects) == 3
    assert scene.name == "datum-t1-core"
    assert "datum-enclosure" in [p.name for p in assembly.placements]
    scad = scene.render()
    assert "cube" in scad.lower()


def test_report_names_what_is_still_guessed():
    _, assembly = build()
    report = assembly.report()
    stubs = [p for p in assembly.placements if p.stub]
    assert stubs, "the board and the mounting surface are stubs today"
    assert "still stubbed" in report
    for p in stubs:
        assert p.name in report


def test_the_enclosure_itself_is_not_a_stub():
    _, assembly = build()
    enclosure = next(p for p in assembly.placements if p.name == "datum-enclosure")
    assert not enclosure.stub, "geometry apothecary authors is not a guess"


def test_kicad_provider_does_not_claim_to_have_read_a_board():
    provider = KiCadProvider()
    assert provider.can_read_board() is False
    assert provider.unresolved() == ["t1-core"]
    assert provider.get("t1-core").source == "stub"


def test_unknown_black_box_names_what_is_available():
    with pytest.raises(KeyError, match="t1-core"):
        KiCadProvider().get("no-such-board")


def test_part_is_registered_with_print_settings():
    part = datum_part.DEFAULT
    assert part.name == "datum_core"
    assert part.source_file.name == "datum_core.scad"
    assert part.print_settings is not None
    # Derived, not restated: the declared print setting and the parameter
    # default are one house constant, and a test that typed the number again
    # would pass while they drifted apart.
    assert part.print_settings.wall_thickness == pytest.approx(datum_part.Params().walls)


def test_scad_source_exists_and_declares_every_parameter():
    """Every Params field must be settable via -D, or an iteration cannot render."""
    src = datum_part.DEFAULT.source_file
    assert src.exists(), f"{src} missing"
    text = src.read_text(encoding="utf-8")
    for field in datum_part.Params.model_fields:
        assert f"{field} =" in text, f"{field} is not a variable in datum_core.scad"


def test_objects_are_actually_translated_into_place():
    """Cube carries no position of its own.

    An earlier version filled in coordinates that were silently discarded, so
    every object rendered at the origin and the scene looked correct in Python
    while being wrong in OpenSCAD. Assert against the rendered output, which is
    the artifact, rather than against the model that produced it.
    """
    scene, assembly = build()
    scad = scene.render()
    assert scad.count("translate(") == len(scene.objects), "every object is placed"
    # The board sits on its standoffs, not on the floor and not at the origin.
    params = assembly.params
    expected_z = params.floor_t + params.standoff_h
    assert (
        f"translate([{params.walls + params.board_clearance}, "
        f"{params.walls + params.board_clearance}, {expected_z}]" in scad
    )


def test_the_scene_renders_valid_openscad_structure():
    scene, _ = build()
    scad = scene.render()
    assert scad.count("{") == scad.count("}"), "balanced braces"
    assert scad.count("cube(") == 3
