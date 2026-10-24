"""Every registered part, rendered at most once per test session.

``built_stl(part)`` renders a part's SCAD with its defaults and unrotated, as
``apothecary parts verify`` measures it, with the OpenSCAD the part asks for,
into the session's temp directory, never beside the source. A module uses it by
importing ``built_stl_fixture``. pytest makes one fixture per importing module
whatever its scope, so the renders are kept here, not by the fixture.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

from apothecary.projects.parts.base import BasePart
from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.parts.stl_renderer import OpenSCADRenderer, RenderResult, get_renderer
from apothecary.projects.registry import scan_projects

# Parts whose render genuinely takes longer than the default budget.
RENDER_BUDGET = {"gridfinity": 240.0}

_RENDERS: dict[str, RenderResult] = {}


def registered_parts() -> list[tuple[str, BasePart | None]]:
    """(name, part) for every part the registry lists; None where the wrapper
    will not import, so a broken wrapper is a failing case, not a missing one."""
    found = []
    for item in scan_projects(ROOT):
        if item.kind != "part":
            continue
        if not item.wrapper:
            found.append((item.name, BasePart(name=item.name, source_file=item.path)))
            continue
        try:
            found.append((item.name, import_module(item.wrapper).DEFAULT))
        except Exception:
            found.append((item.name, None))
    return sorted(found, key=lambda pair: pair[0])


def _render(part: BasePart, out_dir: Path) -> RenderResult:
    if part.name not in _RENDERS:
        own = part.get_openscad_path()
        renderer = OpenSCADRenderer(str(own)) if own else get_renderer()
        _RENDERS[part.name] = renderer.render_stl(
            part.source_file,
            out_dir / f"{part.name}.stl",
            timeout=RENDER_BUDGET.get(part.name, 60.0),
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
