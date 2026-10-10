"""The snowplow is built from Python: its parameters drive the STL, and its
tracked SCAD, its declared interfaces and its bounds agree with that code."""

import math
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apothecary import Cylinder, Rotate, Scene, Translate, Vector3D
from apothecary.api import app
from apothecary.meshes import bounds, read_mesh
from apothecary.projects.parts import rc_snowplow, stl_renderer
from apothecary.projects.parts.rc.snowplow import (
    DEFAULT,
    SnowplowPart,
    mount_front_y,
    snowplow_assembly,
)
from apothecary.projects.parts.rc.snowplow.mount import SnowplowMount
from apothecary.projects.parts.stl_renderer import (
    RenderResult,
    geometry_scad,
    get_renderer,
    read_params_sidecar,
)

PACKAGE = Path(snowplow_assembly.__code__.co_filename).parent
needs_openscad = pytest.mark.skipif(
    not get_renderer().is_available, reason="OpenSCAD not installed"
)


def test_snowplow_assembly_renders():
    scene = Scene(name="test_snowplow", objects=[snowplow_assembly()])
    scad = scene.render()
    assert "cube" in scad.lower() and "cylinder" in scad.lower()
    assert "union" in scad.lower() and "difference" in scad.lower()


def test_the_tracked_scad_is_the_code_at_its_defaults():
    """What a reader, the registry and `/parts/rc.snowplow/scad` see is what
    builds the STL. `apothecary parts render rc.snowplow -o
    parts/rc/snowplow/snowplow.scad` rewrites it."""
    assert DEFAULT.source_file.read_text(encoding="utf-8") == geometry_scad(DEFAULT, {})


def test_the_stl_goes_stale_when_the_code_that_builds_it_changes():
    sources = stl_renderer._sources(DEFAULT)
    code = {
        Path(rc_snowplow.__file__),
        *(PACKAGE / f for f in ("__init__.py", "blade.py", "mount.py")),
    }
    assert code | {DEFAULT.source_file} <= set(sources)
    # Each once: the checklist names the ones newer than the render.
    assert len(sources) == len(set(sources)), sources


# --- the mount's bolt holes, against snowplow.yaml --------------------------------


def _bolt_holes() -> list[tuple[float, tuple, tuple]]:
    """(diameter, position, normal) of each bolt_hole interface snowplow.yaml declares."""
    text = (PACKAGE / "snowplow.yaml").read_text(encoding="utf-8")

    def vector(block, key):
        found = re.search(key + r":\s*\{\s*x:\s*(\S+),\s*y:\s*(\S+),\s*z:\s*([^\s}]+)\s*\}", block)
        return tuple(float(v) for v in found.groups())

    return [
        (
            float(re.search(r"diameter:\s*(\S+)", block).group(1)),
            vector(block, "position"),
            vector(block, "normal"),
        )
        for block in text.split("- name:")[1:]
        if "type: bolt_hole" in block
    ]


def _turn(axis, degrees):
    """The matrix turning by ``degrees`` about ``axis``, right-handed as in OpenSCAD."""
    x, y, z = (c / math.hypot(*axis) for c in axis)
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    t = 1 - c
    return [
        [t * x * x + c, t * x * y - s * z, t * x * z + s * y],
        [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
        [t * x * z - s * y, t * y * z + s * x, t * z * z + c],
    ]


def _apply(m, v):
    return tuple(sum(m[i][j] * v[j] for j in range(3)) for i in range(3))


def _compose(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _cylinders(obj, turn=None, at=(0.0, 0.0, 0.0)):
    """(centre, axis, radius, length) of every cylinder under ``obj``, in its frame."""
    turn = turn or _turn((0, 0, 1), 0)
    if isinstance(obj, Cylinder):
        axis = _apply(turn, (0, 0, 1))
        centre = (
            at if obj.center else tuple(p + a * obj.h / 2 for p, a in zip(at, axis, strict=True))
        )
        return [(centre, axis, obj.radii()[0], obj.h)]
    if isinstance(obj, Translate):
        at = tuple(
            p + d for p, d in zip(at, _apply(turn, (obj.v.x, obj.v.y, obj.v.z)), strict=True)
        )
    elif isinstance(obj, Rotate):
        if isinstance(obj.a, Vector3D):  # about X, then Y, then Z
            a = obj.a
            local = _compose(
                _turn((0, 0, 1), a.z), _compose(_turn((0, 1, 0), a.y), _turn((1, 0, 0), a.x))
            )
        else:
            v = obj.v or Vector3D(x=0, y=0, z=1)
            local = _turn((v.x, v.y, v.z), obj.a)
        turn = _compose(turn, local)
    return [c for child in getattr(obj, "children", []) for c in _cylinders(child, turn, at)]


def _assert_holes(cylinders, origin, thickness):
    """Each bolt_hole of snowplow.yaml, its position taken from ``origin``, is
    one cylinder: bolt_diameter across, through the plate along the normal."""
    holes = _bolt_holes()
    assert len(holes) == 2 and len(cylinders) == len(holes)
    for diameter, position, normal in holes:
        centre = tuple(o + p for o, p in zip(origin, position, strict=True))
        at = [c for c in cylinders if math.dist(c[0], centre) < 1e-6]
        assert len(at) == 1, f"no hole centred at {centre}: {cylinders}"
        _, axis, radius, length = at[0]
        assert radius == pytest.approx(diameter / 2)
        assert abs(sum(a * n for a, n in zip(axis, normal, strict=True))) == pytest.approx(1), axis
        assert length > thickness


def test_the_bolt_holes_are_the_interfaces_snowplow_yaml_declares():
    """snowplow.yaml gives the holes in the mount plate's own frame."""
    mount = SnowplowMount()
    _assert_holes(_cylinders(mount.geometry()), (0.0, 0.0, 0.0), mount.thickness)


def test_the_parts_stl_has_the_holes_where_the_assembly_puts_the_mount():
    """What build_stl, the viewer and `parts verify` render: the plate's
    origin mount_thickness / 2 behind its front face, mount_height / 2 up,
    as snowplow.yaml says."""
    p = rc_snowplow.Params()
    front = mount_front_y(p.blade_height, p.blade_thickness, p.blade_angle, p.mount_height)
    origin = (0.0, front - p.mount_thickness / 2, p.mount_height / 2)
    _assert_holes(_cylinders(DEFAULT.geometry({})), origin, p.mount_thickness)


def test_the_holes_follow_bolt_diameter_and_mount_thickness():
    mount = SnowplowMount(bolt_diameter=5, thickness=9)
    assert {(round(r, 6), h) for _, _, r, h in _cylinders(mount.geometry())} == {(2.5, 11)}


# --- the slider path: POST /parts/{name}/stl/generate with params ----------------


class _StandIn:
    """OpenSCAD's stand-in: keeps the SCAD and definitions it is handed."""

    is_available = True

    def __init__(self):
        self.handed = []

    def render_stl(self, scad_path, stl_path=None, timeout=120.0, params=None):
        self.handed.append((Path(scad_path).read_text(encoding="utf-8"), params))
        stl_path.write_text("solid fake\nendsolid fake\n")
        return RenderResult(success=True, stl_path=stl_path)


@pytest.fixture
def snowplow_stl(tmp_path, monkeypatch):
    """Where the snowplow builds to in these tests, never parts/; the variant
    cache is the test's own."""
    stl = tmp_path / "snowplow.stl"
    monkeypatch.setattr(SnowplowPart, "get_stl_output_path", lambda self: stl)
    monkeypatch.setenv("APOTHECARY_CACHE_DIR", str(tmp_path / "cache"))
    return stl


def test_a_slider_changes_the_scad_openscad_is_handed(snowplow_stl, monkeypatch):
    stand_in = _StandIn()
    monkeypatch.setattr(stl_renderer, "_renderer", stand_in)
    r = TestClient(app).post(
        "/parts/rc.snowplow/stl/generate", json={"params": {"blade_width": 80}}
    )
    assert r.status_code == 200, r.text
    [(scad, definitions)] = stand_in.handed
    assert "cube([80.0, 3.0, 45.0], center=true);" in scad
    assert not definitions
    # A variant is the cache's: the snowplow's own STL stays the default one.
    assert r.json()["params"] == {"blade_width": 80.0}
    assert r.json()["stl_url"] == f"/parts/rc.snowplow/variants/{r.json()['variant']}/stl"
    assert not snowplow_stl.exists() and read_params_sidecar(snowplow_stl) is None


@pytest.mark.slow
@needs_openscad
def test_a_slider_changes_the_stl(snowplow_stl, tmp_path):
    client = TestClient(app)
    r = client.post("/parts/rc.snowplow/stl/generate", json={"params": {"blade_width": 80}})
    assert r.status_code == 200, r.text
    variant = tmp_path / "variant.stl"
    variant.write_bytes(client.get(r.json()["stl_url"]).content)
    lo, hi = bounds(read_mesh(variant))
    size = [hi[axis] - lo[axis] for axis in range(3)]
    assert size[0] == pytest.approx(80, abs=0.01)
    declared = DEFAULT.get_bounds({"blade_width": 80}).size
    assert size == pytest.approx([declared.x, declared.y, declared.z], abs=0.5)


# --- one solid: the mount plate is joined to the blade -----------------------------

# The blade raked back over the plate, upright, and leaning forward; thin and
# thick; and raked so far that its base is off the bed.
SHAPES = [
    pytest.param({}, id="defaults"),
    pytest.param({"blade_angle": 25}, id="raked-back"),
    pytest.param({"blade_angle": 60}, id="raked-off-the-bed"),
    pytest.param({"blade_angle": 0}, id="upright"),
    pytest.param({"blade_angle": -15}, id="leaning-forward"),
    pytest.param({"blade_thickness": 1.5}, id="thin"),
    pytest.param({"blade_thickness": 8, "blade_angle": 0}, id="thick-upright"),
    pytest.param({"blade_thickness": 6, "blade_angle": -20}, id="thick-leaning-forward"),
]


def _bodies(triangles) -> int:
    """How many separate pieces a mesh is: triangles sharing a corner are one."""
    parent: dict = {}

    def root(corner):
        while parent.setdefault(corner, corner) != corner:
            corner = parent[corner]
        return corner

    for first, *others in triangles:
        for corner in others:
            parent[root(corner)] = root(first)
    return len({root(corner) for corner in list(parent)})


@pytest.fixture
def rendered(tmp_path):
    """The snowplow's STL for ``params``, rendered by OpenSCAD."""

    def render(params):
        stl = tmp_path / "snowplow.stl"
        result = stl_renderer.render_part(DEFAULT, stl, DEFAULT.validate_overrides(params))
        assert result.success, result.error_message
        return read_mesh(stl)

    return render


@pytest.mark.slow
@needs_openscad
@pytest.mark.parametrize("params", SHAPES)
def test_the_plate_and_the_blade_are_one_body(rendered, params):
    """A part other parts are built onto is one solid: the plate the bolt
    holes are in holds the blade."""
    assert _bodies(rendered(params)) == 1


@pytest.mark.slow
@needs_openscad
@pytest.mark.parametrize("params", SHAPES)
def test_it_renders_to_the_bounds_it_declares(rendered, params):
    lo, hi = bounds(rendered(params))
    declared = DEFAULT.get_bounds(params)
    assert list(lo) == pytest.approx(declared.min_point.to_list(), abs=0.01)
    assert list(hi) == pytest.approx(declared.max_point.to_list(), abs=0.01)
