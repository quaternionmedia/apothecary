"""Every registered part, rendered at most once per test session.

``built_stl(part)`` renders a part with its defaults and unrotated, as
``apothecary parts verify`` measures it (``render_part``: its Python geometry
if it has some, else its SCAD), with the OpenSCAD the part asks for, into the
session's temp directory, never beside the source. A module uses it by
importing ``built_stl_fixture``. pytest makes one fixture per importing module
whatever its scope, so the renders are kept here, not by the fixture.

``face_up(stl)``: how far the largest flat face of a render that faces up leans
from straight up, which says which way up it was drawn.
"""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path

import pytest

from apothecary.meshes import read_mesh
from apothecary.projects.parts.base import BasePart
from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.parts.stl_renderer import RenderResult, get_renderer, render_part
from apothecary.projects.registry import PartLoadError, load_part, scan_projects

# Parts whose render genuinely takes longer than the default budget.
RENDER_BUDGET = {"gridfinity": 240.0}

_RENDERS: dict[str, RenderResult] = {}


def registered_parts() -> list[tuple[str, BasePart | None]]:
    """(name, part) for every part the registry lists; None where the wrapper
    will not load, so a broken part is a failing case, not a missing one."""
    found = []
    for item in scan_projects(ROOT):
        if item.kind != "part":
            continue
        if not item.has_part:
            found.append((item.name, BasePart(name=item.name, source_file=item.path)))
            continue
        try:
            found.append((item.name, load_part(item)))
        except PartLoadError:
            found.append((item.name, None))
    return sorted(found, key=lambda pair: pair[0])


def _render(part: BasePart, out_dir: Path) -> RenderResult:
    if part.name not in _RENDERS:
        _RENDERS[part.name] = render_part(
            part, out_dir / f"{part.name}.stl", timeout=RENDER_BUDGET.get(part.name, 60.0)
        )
    return _RENDERS[part.name]


@pytest.fixture(scope="session", name="built_stl")
def built_stl_fixture(tmp_path_factory):
    """``built_stl(part) -> Path``: the part's STL, rendered once this session.

    Skips when OpenSCAD is missing or the part says it cannot be built here;
    fails, with OpenSCAD's output, when the render fails.
    """
    out_dir = tmp_path_factory.getbasetemp() / "rendered_parts"
    out_dir.mkdir(exist_ok=True)

    def build(part: BasePart) -> Path:
        if not get_renderer().is_available:
            pytest.skip("OpenSCAD not installed")
        if not part.source_file.exists():
            pytest.fail(f"{part.name}: source missing: {part.source_file}")
        can_build, reason = part.can_generate_stl()
        if not can_build:
            pytest.skip(f"{part.name} cannot be built here: {reason}")
        result = _render(part, out_dir)
        if not result.success:
            pytest.fail(
                f"{part.name}: {result.error_message}\n"
                f"OpenSCAD stderr:\n{(result.stderr or '')[-2000:]}"
            )
        return result.stl_path

    return build


def face_up(stl: Path) -> float:
    """The degrees from +z of the largest flat face of ``stl`` that faces up: its
    triangles grouped by plane (normal and offset, rounded), their areas summed."""
    planes: dict = defaultdict(float)
    for a, b, c in read_mesh(Path(stl)):
        u, v = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
        n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
        twice = math.sqrt(sum(x * x for x in n))
        if twice == 0:
            continue
        n = [x / twice for x in n]
        offset = sum(n[i] * a[i] for i in range(3))
        planes[(tuple(round(x, 3) + 0.0 for x in n), round(offset, 1))] += twice / 2
    up = [(area, normal) for (normal, _), area in planes.items() if normal[2] > 0]
    _, normal = max(up)
    return math.degrees(math.acos(min(1.0, normal[2])))
