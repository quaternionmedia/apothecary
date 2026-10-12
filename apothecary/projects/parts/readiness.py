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

A page asks about what it draws: ``assess`` takes the variant drawn
(``Drawn``, from the variant cache), whose render, measured bounds and
parameters then answer the geometry questions instead of the part's own STL's,
and a build volume with where it came from (``Volume``: a printer pinned in
the site, or one given).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from apothecary.meshes import MeshError, bounds, read_mesh
from apothecary.projects.parts.stl_renderer import _sources, get_renderer, read_params_sidecar

PASS = "pass"
BLOCKED = "blocked"
UNKNOWN = "unknown"

BOUNDS = "Declared bounds match geometry"

Size = Tuple[float, float, float]


@dataclass(frozen=True)
class Drawn:
    """A variant from the variant cache: what a page drew, which the checklist
    then asks about instead of the part's own STL."""

    key: str
    stl: Path
    params: dict
    # Its bounding box in the frame the bounds are declared in ({"min", "max",
    # "size"}), as the cache measured it; None where it measured none.
    measured: Optional[dict] = None
    # The sha256 of the draft it was rendered from; None: the part's own SCAD.
    draft: Optional[str] = None


@dataclass(frozen=True)
class Volume:
    """A build volume, and where it came from: "printer_1 in garage", "given"."""

    size: Size
    source: str = "given"


# What "Fits the printer" says when no volume is known: the detail, and the fix.
NO_VOLUME = ("no build volume given", "pass --build-volume X,Y,Z to check it")


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


def _sources_newer_than(part, stl_path: Path) -> List[str]:
    """Inputs that changed after the render, if any: the SCAD, what it
    includes, uses or imports, and the wrapper (a Python module, or a
    described part's part.json) -- the same inputs build_stl rebuilds from."""
    rendered = stl_path.stat().st_mtime
    inputs = _sources(part)
    return [f.name for f in inputs if f.exists() and f.stat().st_mtime > rendered]


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
        checks.append(Check(BOUNDS, UNKNOWN, "needs a render"))
        return checks

    if not stl_path.exists():
        can_build, reason = part.can_generate_stl()
        checks.append(
            Check(
                "Geometry renders",
                UNKNOWN,
                "not built yet" if can_build else f"cannot build here: {reason}",
                f"apothecary parts generate-stl {part.name}"
                if can_build
                else f"once it can be built: apothecary parts generate-stl {part.name}",
            )
        )
        checks.append(Check(BOUNDS, UNKNOWN, "needs a render"))
        return checks

    newer = _sources_newer_than(part, stl_path)
    if newer:
        checks.append(
            Check(
                "Geometry renders",
                UNKNOWN,
                f"the render is older than {', '.join(newer)}",
                f"apothecary parts generate-stl {part.name} --force",
            )
        )
        checks.append(Check(BOUNDS, UNKNOWN, "needs a render"))
        return checks

    checks.append(Check("Geometry renders", PASS, f"{stl_path.stat().st_size // 1024} KB"))
    return checks


@dataclass(frozen=True)
class BoundsComparison:
    """Declared against measured extents (x, y, z), in mm."""

    declared: Size
    measured: Size
    tolerance: float

    @property
    def deltas(self) -> Size:
        return tuple(abs(m - d) for d, m in zip(self.declared, self.measured, strict=True))

    @property
    def worst(self) -> float:
        return max(self.deltas)

    @property
    def ok(self) -> bool:
        return self.worst <= self.tolerance


def compare_bounds(
    declared: Sequence[float], measured: Sequence[float], tol: float
) -> BoundsComparison:
    """A part's declared extents against an STL's, each axis allowed ``tol`` mm."""
    return BoundsComparison(tuple(declared), tuple(measured), tol)


@lru_cache(maxsize=256)
def _measured_size(stl_path: Path, mtime_ns: int) -> Size:
    """An STL's extents; keyed on its mtime, so a new render is measured again."""
    lo, hi = bounds(read_mesh(stl_path))
    return (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])


def _turned(size: Size, rotation: Sequence[float]) -> Optional[Size]:
    """``size`` after OpenSCAD's ``rotate(rotation)`` (about x, then y, then z), or
    None when an angle is not a quarter turn, as the render's extents are then not the box's."""
    x, y, z = size
    for axis, angle in zip("xyz", rotation, strict=True):
        if angle % 90:
            return None
        if (angle // 90) % 2:
            if axis == "x":
                y, z = z, y
            elif axis == "y":
                x, z = z, x
            else:
                x, y = y, x
    return (x, y, z)


def _bounds_check(part, stl_path: Path, tolerance: float) -> Check:
    declared = part.get_bounds()
    if declared is None:
        return Check(
            BOUNDS,
            BLOCKED,
            "the part declares no bounds",
            "give the wrapper a get_bounds or default_bounds",
        )

    # Declared bounds are for the default parameters, so an override render says nothing.
    overrides = (read_params_sidecar(stl_path) or {}).get("params")
    if overrides:
        return Check(
            BOUNDS,
            UNKNOWN,
            f"the STL was rendered with {', '.join(sorted(overrides))} overridden",
            f"apothecary parts generate-stl {part.name}",
        )

    size = (declared.size.x, declared.size.y, declared.size.z)
    want = _turned(size, part.display_rotation.to_list())
    if want is None:
        return Check(
            BOUNDS,
            UNKNOWN,
            "the STL is turned by display_rotation, by other than quarter turns",
            f"apothecary parts verify {part.name}",
        )

    try:
        measured = _measured_size(stl_path, stl_path.stat().st_mtime_ns)
    except (OSError, MeshError) as exc:
        return Check(
            BOUNDS,
            UNKNOWN,
            f"could not measure the STL: {exc}",
            f"apothecary parts generate-stl {part.name} --force",
        )

    result = compare_bounds(want, measured, tolerance)
    if not result.ok:
        return Check(
            BOUNDS,
            BLOCKED,
            f"off by {result.worst:.2f} mm — declared "
            f"{want[0]:.1f} x {want[1]:.1f} x {want[2]:.1f}, measured "
            f"{measured[0]:.1f} x {measured[1]:.1f} x {measured[2]:.1f}",
            "reconcile the wrapper with the SCAD; anything sizing around this part is wrong",
        )
    return Check(
        BOUNDS,
        PASS,
        f"{want[0]:.1f} x {want[1]:.1f} x {want[2]:.1f} mm, within {tolerance} mm",
    )


def _drawn_checks(part, drawn: Drawn, tolerance: float) -> List[Check]:
    """The geometry questions, asked of a variant drawn from the cache: it is
    there only because it rendered, so it renders; its measured size is held to
    the bounds the part declares for its parameters."""
    if not part.source_file.exists():
        return _geometry_checks(part, None, Path(drawn.stl))
    checks = [Check("Source geometry exists", PASS, str(part.source_file.name))]
    try:
        size_kb = Path(drawn.stl).stat().st_size // 1024
    except OSError:
        size_kb = None
    from_draft = " from an edit of its SCAD" if drawn.draft else ""
    checks.append(
        Check(
            "Geometry renders",
            PASS,
            f"variant {drawn.key}{from_draft}" + (f", {size_kb} KB" if size_kb is not None else ""),
        )
    )
    checks.append(_drawn_bounds_check(part, drawn, tolerance))
    return checks


def _speaks_for_params(part) -> bool:
    """Whether the part's declared bounds follow its parameters: its own
    get_bounds, not BasePart's, which answers its defaults whatever is asked."""
    from apothecary.projects.parts.base import BasePart

    return type(part).get_bounds is not BasePart.get_bounds


def _drawn_bounds_check(part, drawn: Drawn, tolerance: float) -> Check:
    if drawn.params and not _speaks_for_params(part):
        return Check(
            BOUNDS,
            UNKNOWN,
            f"the part declares bounds for its defaults only, and the variant sets "
            f"{', '.join(sorted(drawn.params))}",
            "give the wrapper a get_bounds that follows its parameters",
        )
    try:
        declared = part.get_bounds(dict(drawn.params) or None)
    except Exception as exc:  # a wrapper that cannot size itself for these
        return Check(BOUNDS, UNKNOWN, f"the part could not size itself for them: {exc}")
    if declared is None:
        return Check(
            BOUNDS,
            BLOCKED,
            "the part declares no bounds",
            "give the wrapper a get_bounds or default_bounds",
        )
    if not drawn.measured:
        return Check(BOUNDS, UNKNOWN, "the variant was not measured")
    want = (declared.size.x, declared.size.y, declared.size.z)
    measured = tuple(float(v) for v in drawn.measured["size"])
    result = compare_bounds(want, measured, tolerance)
    if not result.ok:
        return Check(
            BOUNDS,
            BLOCKED,
            f"off by {result.worst:.2f} mm — declared "
            f"{want[0]:.1f} x {want[1]:.1f} x {want[2]:.1f} for these parameters, measured "
            f"{measured[0]:.1f} x {measured[1]:.1f} x {measured[2]:.1f}",
            "reconcile the wrapper with the SCAD; anything sizing around this part is wrong",
        )
    return Check(
        BOUNDS,
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


def _build_volume_check(
    part,
    build_volume,
    drawn: Optional[Drawn] = None,
    source: str = "given",
    none: Tuple[str, str] = NO_VOLUME,
) -> Check:
    """Whether the part fits ``build_volume``: the variant drawn by the size it
    measured, else the part by the size it declares. ``source`` says where the
    volume came from; ``none`` is what to say, and to do, when there is none."""
    if build_volume is None:
        return Check("Fits the printer", UNKNOWN, none[0], none[1])
    if drawn is not None and drawn.measured:
        size = tuple(float(v) for v in drawn.measured["size"])
        what = "measured"
    else:
        params = (dict(drawn.params) or None) if drawn is not None else None
        declared = part.get_bounds(params)
        if declared is None:
            return Check("Fits the printer", UNKNOWN, "the part declares no bounds")
        size = (declared.size.x, declared.size.y, declared.size.z)
        what = "declared"
    inside = "" if source == "given" else f" ({source})"
    over = [
        f"{axis} {have:.1f} > {limit:.1f}"
        for axis, have, limit in zip("XYZ", size, build_volume, strict=False)
        if have > limit
    ]
    if over:
        return Check(
            "Fits the printer",
            BLOCKED,
            "; ".join(over) + inside,
            "split the part, or print it on a larger machine",
        )
    return Check(
        "Fits the printer",
        PASS,
        f"{size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm {what}, inside "
        f"{build_volume[0]:.0f} x {build_volume[1]:.0f} x {build_volume[2]:.0f}{inside}",
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
        return Check("Fitted to measured artifacts", UNKNOWN, "the assembly reports no placements")

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


def assess(
    part,
    build_volume: Optional[tuple] = None,
    tolerance: float = 0.5,
    drawn: Optional[Drawn] = None,
    volume_from: str = "given",
    no_volume: Tuple[str, str] = NO_VOLUME,
) -> Readiness:
    """Everything the repository can answer about printing this part: the part
    as its own STL is, or the variant ``drawn``. ``volume_from`` says where
    ``build_volume`` came from, and ``no_volume`` what to say without one."""
    if drawn is not None:
        checks = _drawn_checks(part, drawn, tolerance)
    else:
        renderer = get_renderer()
        # The part decides where its STL lives (gridfinity's is outside its submodule).
        stl_path = part.get_stl_output_path()
        checks = _geometry_checks(part, renderer, stl_path)
        if any(c.name == "Geometry renders" and c.ok for c in checks):
            checks.append(_bounds_check(part, stl_path, tolerance))

    checks.append(_print_settings_check(part))
    checks.append(_contested_check(part))
    checks.append(_build_volume_check(part, build_volume, drawn, volume_from, no_volume))
    checks.append(_stub_check(part))

    return Readiness(part=part.name, checks=checks)
