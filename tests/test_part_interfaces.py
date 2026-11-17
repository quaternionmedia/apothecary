"""A part says where another meets it, and its render is held to what it says
(BasePart.interfaces, a part.json's interfaces, apothecary/fittings.py's readings,
apothecary parts verify; docs/connections.md)."""

from __future__ import annotations

import json
import math

import pytest

from apothecary.fittings import INTERFACE_TOLERANCE, readings
from apothecary.meshes import section_radii
from apothecary.models.interfaces import Socket, Spigot
from apothecary.projects.parts.base import BasePart
from apothecary.projects.parts.described import part_from_sidecar
from apothecary.projects.parts.stl_renderer import get_renderer, render_part


def tube_mesh(outer, bore, height, n=128, x=0.0):
    """A tube along +Z as triangles: ``outer`` and ``bore`` are (bottom, top) diameters,
    its axis at (x, 0)."""

    def ring(d, z):
        return [
            (x + d / 2 * math.cos(2 * math.pi * k / n), d / 2 * math.sin(2 * math.pi * k / n), z)
            for k in range(n)
        ]

    ob, ot = ring(outer[0], 0.0), ring(outer[1], height)
    ib, it = ring(bore[0], 0.0), ring(bore[1], height)
    tris = []
    for k in range(n):
        j = (k + 1) % n
        for lo, hi in ((ob, ot), (it, ib)):
            tris += [(lo[k], lo[j], hi[j]), (lo[k], hi[j], hi[k])]
        tris += [(ot[k], ot[j], it[j]), (ot[k], it[j], it[k])]
        tris += [(ib[k], ib[j], ob[j]), (ib[k], ob[j], ob[k])]
    return tris


# --- the hook on a part ---------------------------------------------------------------


def test_a_part_nothing_meets_has_no_interfaces(tmp_path):
    part = BasePart(name="plain", source_file=tmp_path / "plain.scad")
    assert (part.interfaces(), part.has_interfaces) == ([], False)
    with pytest.raises(KeyError, match="plain has no interface 'x'; its interfaces: none"):
        part.interface("x")


def _sidecar(tmp_path, interfaces):
    folder = tmp_path / "port"
    folder.mkdir()
    scad = folder / "port.scad"
    scad.write_text(
        "$fn = 128;\ndifference() {\n  cylinder(h = 30, d = 38);\n"
        "  translate([0, 0, -1]) cylinder(h = 32, d = 32);\n}\n",
        encoding="utf-8",
    )
    (folder / "part.json").write_text(
        json.dumps({"name": "port", "tags": ["stub"], "interfaces": interfaces}),
        encoding="utf-8",
    )
    return scad


PORT = {
    "name": "port",
    "type": "socket",
    "position": {"z": 30},
    "normal": {"z": 1},
    "diameter": 32.0,
    "depth": 30.0,
}


def test_a_described_part_reads_its_interfaces_from_its_sidecar(tmp_path):
    part = part_from_sidecar(_sidecar(tmp_path, [PORT]))
    assert part.has_interfaces
    port = part.interface("port")
    assert isinstance(port, Socket)
    assert (port.diameter, port.depth, port.source) == (32.0, 30.0, "stub")


def test_a_sidecar_whose_interfaces_do_not_read_is_no_part_description(tmp_path):
    scad = _sidecar(tmp_path, [{**PORT, "excludes": ["hose"]}])
    with pytest.raises(ValueError, match="does not have"):
        part_from_sidecar(scad)


# --- reading a round interface on a mesh ----------------------------------------------


def test_a_cut_across_a_tube_reads_its_bore_and_its_outside():
    mesh = tube_mesh((39, 41), (35, 35), 40)
    near, far = section_radii(mesh, (0, 0, 20), (0, 0, 1))
    assert far == pytest.approx(20.0, abs=1e-6)  # halfway up a 39-to-41 taper
    assert near == pytest.approx(17.5, abs=0.01)  # a flat of the 128-gon, under 0.01 in
    assert section_radii(mesh, (0, 0, 50), (0, 0, 1)) is None


def test_a_spigot_reads_true_on_the_mesh_that_has_it():
    mesh = tube_mesh((39, 41), (35, 35), 40)
    spigot = Spigot(
        name="hose", position={"z": 40}, normal={"z": -1}, d_base=41, d_tip=39, length=40
    )
    read = readings(spigot, mesh)
    assert [(r.where, r.declared) for r in read] == [("base", 40.975), ("tip", 39.025)]
    assert all(r.holds() for r in read), read


def test_a_socket_drawn_off_its_axis_reads_wrong():
    socket = Socket(name="port", position={"z": 30}, normal={"z": 1}, diameter=32, depth=30)
    assert all(r.holds() for r in readings(socket, tube_mesh((38, 38), (32, 32), 30)))
    moved = readings(socket, tube_mesh((38, 38), (32, 32), 30, x=0.5))
    assert not any(r.holds() for r in moved)
    assert moved[0].measured == pytest.approx(31.0, abs=0.02)


def test_a_bore_drawn_smaller_than_declared_drifts_past_the_tolerance():
    socket = Socket(name="port", position={"z": 30}, normal={"z": 1}, diameter=32, depth=30)
    (mouth, depth) = readings(socket, tube_mesh((38, 38), (31.9, 31.9), 30))
    assert mouth.drift == pytest.approx(0.1, abs=0.01)
    assert mouth.drift > INTERFACE_TOLERANCE
    assert not mouth.holds() and not depth.holds()


def test_an_interface_where_the_mesh_is_not_reads_nothing():
    socket = Socket(name="port", position={"z": 90}, normal={"z": 1}, diameter=32, depth=30)
    read = readings(socket, tube_mesh((38, 38), (32, 32), 30))
    assert [r.measured for r in read] == [None, None]
    assert not any(r.holds() for r in read)


# --- the render -----------------------------------------------------------------------


@pytest.mark.skipif(not get_renderer().is_available, reason="OpenSCAD not installed")
def test_a_described_parts_render_is_held_to_its_interfaces(tmp_path):
    """OpenSCAD's own tube, read about the axis its sidecar declares."""
    from apothecary.meshes import read_mesh

    part = part_from_sidecar(_sidecar(tmp_path, [PORT]))
    stl = tmp_path / "port.stl"
    result = render_part(part, stl, timeout=120)
    assert result.success, result.error_message
    read = readings(part.interface("port"), read_mesh(stl))
    assert [r.where for r in read] == ["mouth", "depth"]
    assert all(r.holds() for r in read), read
