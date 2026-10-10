"""Comparing a geometry kernel with the reference, by numbers.

Three layers, cheapest first.

1. The measures and the corpus are checked on their own, with no kernel and no
   OpenSCAD: a box has the volume a box has, an open mesh is not watertight,
   every scene in the corpus renders and survives a round trip through JSON.
2. The reference (OpenSCAD with the Manifold backend) is checked against
   volumes that can be worked out by hand. Skipped when this machine has no
   OpenSCAD with Manifold.
3. A kernel is compared with the reference, case by case. Skipped until an
   adapter is registered in ``apothecary.kernel_compare.KERNELS``.

``apothecary kernel-reference`` prints the reference's numbers; this file
states none of them.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from click.testing import CliRunner

from apothecary import kernel_compare as kc
from apothecary import meshes
from apothecary.cli.main import cli
from apothecary.scene import Scene

BOX = kc._box()  # 5 x 3 x 2, outward-wound
OCTAHEDRON = kc._octahedron()  # radius 4


# ---------------------------------------------------------------- the measures


def test_a_box_measures_as_a_box():
    m = kc.measure(BOX)
    assert m.triangles == 12
    assert m.volume == pytest.approx(5 * 3 * 2)
    assert m.area == pytest.approx(2 * (15 + 10 + 6))
    assert m.bbox_min == (0, 0, 0) and m.bbox_max == (5, 3, 2)
    assert m.watertight and m.manifold and m.degenerate == 0


def test_an_octahedron_measures_as_one():
    m = kc.measure(OCTAHEDRON)
    assert m.volume == pytest.approx(4 * 4**3 / 3)  # 4/3 r^3
    assert m.area == pytest.approx(8 * math.sqrt(3) / 4 * (4 * math.sqrt(2)) ** 2)
    assert m.manifold


def test_an_inside_out_mesh_has_negative_volume():
    flipped = [(a, c, b) for a, b, c in BOX]
    assert kc.signed_volume(flipped) == pytest.approx(-30)
    # Still closed, and still consistent with itself: only its sign says it is wrong.
    assert kc.measure(flipped).manifold


def test_a_missing_triangle_is_not_watertight():
    m = kc.measure(BOX[1:])
    assert not m.watertight and not m.manifold


def test_one_flipped_triangle_is_watertight_but_not_manifold():
    a, b, c = BOX[0]
    m = kc.measure([(a, c, b)] + BOX[1:])
    assert m.watertight and not m.manifold


def test_a_collapsed_triangle_is_counted_and_left_out():
    point = (1.0, 1.0, 1.0)
    m = kc.measure(BOX + [(point, point, (2.0, 2.0, 2.0))])
    assert m.degenerate == 1 and m.watertight


def test_relative_error():
    assert kc.relative_error(101, 100) == pytest.approx(0.01)
    assert kc.relative_error(0.5, 0) == 0.5


def test_a_point_is_as_far_from_a_triangle_as_geometry_says():
    tri = ((0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (0.0, 4.0, 0.0))
    d = kc.closest_distance_to_triangle
    assert d((1.0, 1.0, 3.0), tri) == pytest.approx(3)  # over the face
    assert d((-3.0, 0.0, 4.0), tri) == pytest.approx(5)  # off a corner
    assert d((2.0, -2.0, 0.0), tri) == pytest.approx(2)  # off an edge
    assert d((3.0, 3.0, 0.0), tri) == pytest.approx(math.sqrt(2))  # off the long edge
    assert d((1.0, 1.0, 0.0), tri) == 0


def test_the_index_finds_what_a_search_of_every_triangle_finds():
    points = kc.sample_surface(OCTAHEDRON, 40, seed=3) + [(9.0, 9.0, 9.0), (0.0, 0.0, 0.0)]
    index = kc.SurfaceIndex(BOX)
    for p in points:
        brute = min(kc.closest_distance_to_triangle(p, t) for t in BOX)
        assert index.distance(p) == pytest.approx(brute)


def test_sampling_is_the_same_every_run_and_stays_on_the_surface():
    first = kc.sample_surface(BOX, 50, seed=1)
    assert first == kc.sample_surface(BOX, 50, seed=1)
    assert first != kc.sample_surface(BOX, 50, seed=2)
    index = kc.SurfaceIndex(BOX)
    assert max(index.distance(p) for p in first) < 1e-9


def test_a_surface_is_no_distance_from_itself_and_a_shift_from_a_shifted_copy():
    assert kc.surface_distance(BOX, BOX, samples=200).worst < 1e-9
    moved = [tuple((x + 0.25, y, z) for x, y, z in tri) for tri in BOX]
    d = kc.surface_distance(BOX, moved, samples=400)  # type: ignore[arg-type]
    assert 0 < d.mean <= 0.25 + 1e-9
    assert d.worst <= 0.25 + 1e-9


def test_a_missing_piece_shows_in_the_distance_even_one_way():
    with_arm = BOX + [
        tuple((x + 20, y, z) for x, y, z in tri) for tri in BOX  # type: ignore[misc]
    ]
    assert kc.surface_distance(BOX, with_arm, samples=200).worst > 10


def test_compare_of_a_mesh_with_itself_is_clean():
    ref = kc.measure(BOX)
    c = kc.compare(BOX, BOX, candidate_seconds=1.0, reference_seconds=2.0, samples=100)
    assert c.volume_error == 0 and c.area_error == 0 and c.bbox_error == 0
    assert c.triangle_ratio == 1 and c.seconds_ratio == 0.5
    assert kc.violations(c, ref) == []


def test_violations_name_what_is_outside():
    ref = kc.measure(BOX)
    shrunk = [tuple((x * 0.9, y * 0.9, z * 0.9) for x, y, z in tri) for tri in BOX]
    found = kc.violations(kc.compare(shrunk, BOX, samples=100), ref)  # type: ignore[arg-type]
    assert any("volume" in line for line in found)
    assert any("bounding box" in line for line in found)


# ------------------------------------------------------------------ the corpus


def test_the_corpus_has_every_kind_of_scene_the_plan_names():
    groups = {case.group for case in kc.CASES}
    assert groups == {"primitive", "boolean", "nested", "hull", "transform", "import", "library"}
    assert len(set(kc.CASE_NAMES)) == len(kc.CASE_NAMES)


@pytest.mark.parametrize("name", kc.CASE_NAMES)
def test_a_case_is_a_scene_that_renders_and_survives_json(name, tmp_path):
    """The JSON round trip is what a command-line kernel is handed."""
    scene = kc.case_named(name).scene(tmp_path)
    assert scene.objects
    if kc.case_named(name).group == "import":
        assert "import(" in scene.render()
    again = Scene.model_validate_json(scene.model_dump_json())
    assert again.render() == scene.render()


def test_import_cases_name_files_that_exist_and_are_closed(tmp_path):
    for case in kc.CASES:
        if case.group != "import":
            continue
        case.scene(tmp_path)
        files = list(tmp_path.glob(f"{case.name}.stl"))
        assert files, case.name
        assert kc.measure(meshes.read_stl(files[0].read_bytes())).manifold


def test_an_unknown_case_is_named_with_the_ones_there_are():
    with pytest.raises(KeyError, match="cube"):
        kc.case_named("no such case")


# --------------------------------------------------------------- the reference


@pytest.fixture(scope="module")
def reference_openscad() -> Path:
    try:
        return kc.reference_openscad()
    except kc.ReferenceUnavailable as why:
        pytest.skip(str(why))


# Volumes worked out by hand, not read off the reference.
BY_HAND = {
    "cube": 10**3,
    "cube_centered": 10 * 6 * 4,
    "union": 2 * 10**3 - 5**3,
    "union_touching": 2 * 10**3,
    "difference_flush": 10**3 - 6 * 6 * 5,
    "import_box": 5 * 3 * 2,
}


@pytest.mark.parametrize("name", sorted(BY_HAND))
def test_the_reference_agrees_with_arithmetic(name, reference_openscad, tmp_path):
    ref = kc.run_reference([kc.case_named(name)], tmp_path, reference_openscad)[0]
    m = kc.measure(ref.triangles)
    assert m.volume == pytest.approx(BY_HAND[name], rel=1e-5)
    assert m.manifold, f"{name}: the reference's own mesh is not manifold"


def test_the_reference_table_has_a_row_per_case(reference_openscad, tmp_path):
    cases = [kc.case_named("cube"), kc.case_named("hull_rounded_box")]
    refs = kc.run_reference(cases, tmp_path, reference_openscad)
    table = kc.reference_table(refs)
    assert [line.split()[0] for line in table.splitlines()[2:]] == ["cube", "hull_rounded_box"]
    assert kc.reference_table(refs, as_json=True).count("\n") == 1


class OpenSCADAsKernel:
    """The reference wearing the adapter protocol: what a kernel must look like,
    and a kernel that must score perfectly against itself."""

    name = "openscad-again"

    def __init__(self, openscad: Path):
        self.openscad = openscad

    def available(self):
        return True, ""

    def render(self, scene, out):
        return kc.render_reference(scene, out, self.openscad)[0]


def test_the_harness_scores_the_reference_perfectly_against_itself(reference_openscad, tmp_path):
    """Proves the adapter path end to end, with no kernel in the registry."""
    adapter = OpenSCADAsKernel(reference_openscad)
    assert isinstance(adapter, kc.KernelAdapter)
    case = kc.case_named("difference")
    ref = kc.run_reference([case], tmp_path, reference_openscad)[0]
    triangles, seconds = kc.timed(adapter, case.scene(tmp_path), tmp_path / "again.stl")
    comparison = kc.compare(triangles, ref.triangles, seconds, ref.seconds, samples=300)
    assert kc.violations(comparison, kc.measure(ref.triangles)) == []
    assert comparison.triangle_ratio == 1
    assert kc.KERNELS == {}, "the corpus test only skips while no adapter is registered"


# ------------------------------------------------------------------ the command


def test_the_reference_command_lists_the_corpus():
    result = CliRunner().invoke(cli, ["kernel-reference", "--list"])
    assert result.exit_code == 0
    assert all(name in result.output for name in kc.CASE_NAMES)


def test_the_reference_command_says_why_when_it_has_no_manifold(tmp_path):
    result = CliRunner().invoke(cli, ["kernel-reference", "--openscad", str(tmp_path / "none")])
    assert result.exit_code == 1
    assert "not an OpenSCAD with Manifold" in result.output


def test_the_reference_command_names_an_unknown_case():
    result = CliRunner().invoke(cli, ["kernel-reference", "--case", "nope"])
    assert result.exit_code == 1


# ------------------------------------------------------------------- a kernel

KERNEL_CASES = [(k, c) for k in sorted(kc.KERNELS) for c in kc.CASE_NAMES] or [(None, None)]
_REFERENCES: dict = {}


@pytest.mark.parametrize(
    "kernel_name,case_name", KERNEL_CASES, ids=[f"{k}-{c}" for k, c in KERNEL_CASES]
)
def test_a_kernel_renders_the_case_as_the_reference_does(
    kernel_name, case_name, tmp_path_factory, request
):
    if kernel_name is None:
        pytest.skip(
            "no kernel adapter is registered (apothecary.kernel_compare.KERNELS is empty); "
            "register a KernelAdapter to compare a kernel with the reference"
        )
    adapter = kc.KERNELS[kernel_name]
    ok, why = adapter.available()
    if not ok:
        pytest.skip(f"{kernel_name} is not available here: {why}")
    openscad = request.getfixturevalue("reference_openscad")
    case = kc.case_named(case_name)
    work = tmp_path_factory.mktemp(case.name)
    if case_name not in _REFERENCES:
        _REFERENCES[case_name] = kc.run_reference([case], work, openscad)[0]
    ref = _REFERENCES[case_name]
    scene = case.scene(work)
    triangles, seconds = kc.timed(adapter, scene, work / f"{kernel_name}.stl")
    comparison = kc.compare(triangles, ref.triangles, seconds, ref.seconds)
    problems = kc.violations(comparison, kc.measure(ref.triangles))
    if case.openscad_facets and problems:
        pytest.xfail(f"{case.name} leaves the facet count to OpenSCAD's rule: {problems}")
    assert not problems, f"{kernel_name} on {case.name}: " + "; ".join(problems)
