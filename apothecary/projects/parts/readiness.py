"""Is this part ready to be printed and checked against a real one?

The question a build-and-verify pass starts from, answered from what the
repository already knows rather than from a document somebody maintains by
hand. Every check here reads a model that exists: the part's wrapper, its
declared bounds against real geometry, its print settings, the values its
sources disagree about, and the black boxes it is fitted around.

Three states, and the middle one is the point:

``pass``      the check ran and the part satisfies it.
``blocked``   the check ran and the part does not. Fix before printing.
``unknown``   the check could not run — no OpenSCAD, no build volume given.
              Never counted as a pass. A checklist that reports a question it
              could not ask as a tick is worse than no checklist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

PASS = "pass"
BLOCKED = "blocked"
UNKNOWN = "unknown"


@dataclass
class Check:
    """One question, its answer, and what to do when the answer is no."""

    name: str
    state: str
    detail: str = ""
    fix: str = ""

    @property
    def ok(self) -> bool:
        return self.state == PASS


@dataclass
class Readiness:
    part: str
    checks: List[Check] = field(default_factory=list)

    @property
    def blocked(self) -> List[Check]:
        return [c for c in self.checks if c.state == BLOCKED]

    @property
    def unknown(self) -> List[Check]:
        return [c for c in self.checks if c.state == UNKNOWN]

    @property
    def ready(self) -> bool:
        """Ready only if nothing is blocked *and* nothing is unanswered.

        An unanswered question is not a pass. Printing on the strength of a
        check that never ran is how a spool gets spent on a part nobody
        measured.
        """
        return not self.blocked and not self.unknown


def _geometry_checks(part, renderer, stl_path: Path) -> List[Check]:
    checks = []

    if not part.source_file.exists():
        return [
            Check(
                "Source geometry exists",
                BLOCKED,
                f"{part.source_file} is missing",
                "the part folder must hold a SCAD file named after it",
            )
        ]
    checks.append(Check("Source geometry exists", PASS, str(part.source_file.name)))

    if renderer is None or not renderer.is_available:
        checks.append(
            Check(
                "Geometry renders",
                UNKNOWN,
                "OpenSCAD not installed",
                "install OpenSCAD, then `apothecary parts generate-stl <part>`",
            )
        )
        checks.append(Check("Declared bounds match geometry", UNKNOWN, "needs a render"))
        return checks

    if not stl_path.exists():
        checks.append(
            Check(
                "Geometry renders",
                UNKNOWN,
                "not built yet",
                f"apothecary parts generate-stl {part.name}",
            )
        )
        checks.append(Check("Declared bounds match geometry", UNKNOWN, "needs a render"))
        return checks

    checks.append(Check("Geometry renders", PASS, f"{stl_path.stat().st_size // 1024} KB"))
    return checks


def _bounds_check(part, stl_path: Path, tolerance: float) -> Check:
    from apothecary.cli.utils import _get_stl_bounding_box

    declared = part.get_bounds()
    if declared is None:
        return Check(
            "Declared bounds match geometry",
            BLOCKED,
            "the part declares no bounds",
            "give the wrapper a get_bounds or default_bounds",
        )

    box = _get_stl_bounding_box(stl_path)
    if box is None:
        return Check("Declared bounds match geometry", UNKNOWN, "could not measure the STL")

    measured = (box[1] - box[0], box[3] - box[2], box[5] - box[4])
    want = (declared.size.x, declared.size.y, declared.size.z)
    worst = max(abs(a - w) for a, w in zip(measured, want, strict=False))
    if worst > tolerance:
        return Check(
            "Declared bounds match geometry",
            BLOCKED,
            f"off by {worst:.2f} mm — declared "
            f"{want[0]:.1f} x {want[1]:.1f} x {want[2]:.1f}, measured "
            f"{measured[0]:.1f} x {measured[1]:.1f} x {measured[2]:.1f}",
            "reconcile the wrapper with the SCAD; anything sizing around this part is wrong",
        )
    return Check(
        "Declared bounds match geometry",
        PASS,
        f"{want[0]:.1f} x {want[1]:.1f} x {want[2]:.1f} mm, within {tolerance} mm",
    )


def _print_settings_check(part) -> Check:
    settings = getattr(part, "print_settings", None)
    if settings is None:
        return Check(
            "Print settings declared",
            UNKNOWN,
            "the part names no nozzle, layer height or tolerance",
            "set print_settings on the wrapper so a slicer profile is not guesswork",
        )
    return Check(
        "Print settings declared",
        PASS,
        f"nozzle {settings.nozzle_diameter} mm, layer {settings.layer_height} mm, "
        f"wall {settings.wall_thickness} mm, tolerance {settings.tolerance} mm",
    )


def _contested_check(part) -> Check:
    contested = getattr(part, "contested", {}) or {}
    if not contested:
        return Check("No disputed dimensions", PASS, "nothing recorded as contested")
    names = ", ".join(sorted(contested))
    return Check(
        "No disputed dimensions",
        BLOCKED,
        f"{len(contested)} unresolved: {names}",
        "settle them in the viewer — the panel lists each candidate and its source",
    )


def _build_volume_check(part, build_volume) -> Check:
    if build_volume is None:
        return Check(
            "Fits the printer",
            UNKNOWN,
            "no build volume given",
            "pass --build-volume X,Y,Z to check it",
        )
    declared = part.get_bounds()
    if declared is None:
        return Check("Fits the printer", UNKNOWN, "the part declares no bounds")

    size = (declared.size.x, declared.size.y, declared.size.z)
    over = [
        f"{axis} {have:.1f} > {limit:.1f}"
        for axis, have, limit in zip("XYZ", size, build_volume, strict=False)
        if have > limit
    ]
    if over:
        return Check(
            "Fits the printer",
            BLOCKED,
            "; ".join(over),
            "split the part, or print it on a larger machine",
        )
    return Check(
        "Fits the printer",
        PASS,
        f"{size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm inside "
        f"{build_volume[0]:.0f} x {build_volume[1]:.0f} x {build_volume[2]:.0f}",
    )


def _stub_check(part) -> Check:
    """Black boxes this part is fitted around that nobody has measured.

    `models/blackbox.py` carries `source` precisely so a reader can tell a
    measured envelope from a guessed one, and an assembly reports its stubs.
    A part fitted only to guesses can be printed — it just should not be
    called verified against hardware afterwards.
    """
    try:
        from apothecary.projects.assemblies import build
    except Exception:
        return Check("Fitted to measured artifacts", UNKNOWN, "no assembly drives this part")

    try:
        # build() returns (Scene, Assembly). Reading it as one object made this
        # check report "no stubs remain" for an assembly it had never looked
        # at -- the false pass this module's own docstring warns about.
        _scene, assembly = build()
    except Exception as exc:  # pragma: no cover - defensive
        return Check("Fitted to measured artifacts", UNKNOWN, f"assembly did not build: {exc}")

    placements = getattr(assembly, "placements", None)
    if placements is None:
        return Check(
            "Fitted to measured artifacts", UNKNOWN, "the assembly reports no placements"
        )

    # Only for a part the assembly actually places. This used to report the
    # bench's stubs for every part in the library, so `calibration_cube` was
    # told it was fitted to a board it has never heard of.
    source = part.source_file.name
    placed = any(source in (getattr(p, "note", "") or "") for p in placements)
    if not placed:
        return Check(
            "Fitted to measured artifacts",
            PASS,
            "not fitted to a black box — nothing external to measure",
        )

    stubs = [p for p in placements if getattr(p, "stub", False)]
    if not stubs:
        return Check(
            "Fitted to measured artifacts", PASS, f"{len(placements)} placed, none stubbed"
        )
    return Check(
        "Fitted to measured artifacts",
        UNKNOWN,
        f"{len(stubs)} envelope(s) still guessed: " + ", ".join(p.name for p in stubs),
        "replace a StubProvider with a measured source (KiCadProvider, a datasheet)",
    )


def assess(part, build_volume: Optional[tuple] = None, tolerance: float = 0.5) -> Readiness:
    """Everything the repository can answer about printing this part."""
    from apothecary.projects.parts.stl_renderer import get_renderer

    renderer = get_renderer()
    # The part decides where its STL lives. gridfinity's SCAD is inside a
    # third-party submodule and its wrapper overrides this precisely so the
    # render does not land in somebody else's checkout; assuming
    # source_file.with_suffix looked in the wrong place for it.
    stl_path = part.get_stl_output_path()

    checks = _geometry_checks(part, renderer, stl_path)
    if any(c.name == "Geometry renders" and c.ok for c in checks):
        checks.append(_bounds_check(part, stl_path, tolerance))

    checks.append(_print_settings_check(part))
    checks.append(_contested_check(part))
    checks.append(_build_volume_check(part, build_volume))
    checks.append(_stub_check(part))

    return Readiness(part=part.name, checks=checks)
