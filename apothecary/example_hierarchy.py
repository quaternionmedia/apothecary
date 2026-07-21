"""Worked example: a garage workbench with a fleet of 3D printers.

PROTOTYPE — demonstrates apothecary/hierarchy.py (Site/Structure/Substructure/
Feature) against a concrete, spatially verifiable scene rather than an
eyeballed one: one Site ("Garage") containing **four independently-sourced
Structures** — the workbench itself, plus one Structure per 3D printer
sitting on top of it — each built from one or more named Substructure
systems. This is a richer exercise of the full hierarchy than a single
Structure: a printer is bought as a whole unit, same as the bench, so both
are Structures (siblings within the Site); the *systems within* a Structure
(a frame, a gantry) are Substructures.

"Verifiable" means more than "it renders": every printer Structure carries a
``footprint`` (see ``Structure.world_bounds()`` in ``hierarchy.py``), so
``tests/test_garage_workbench.py`` checks, in code, that every printer sits
exactly on the bench's top surface, stays within the bench's footprint, and
doesn't overlap its neighbors — not just that the generated .scad "looks
about right."

Eventual goal (not attempted here): this bench-of-printers Site is the shape
manufacturing-planning questions ("which printer can take this job," "is
there free capacity") would eventually be asked against — each printer
Structure is already the right unit to eventually attach a build volume,
a queue, or a status to.
"""

from __future__ import annotations

from typing import List

from .hierarchy import Feature, LayoutReport, LayoutViolation, Site, Structure, Substructure
from .models.bounds import BoundingBox3D
from .models.vectors import Vector3D
from .primitives import Cube, Cylinder
from .transforms import Translate

# Bench dimensions (mm)
BENCH_WIDTH = 1800.0
BENCH_DEPTH = 600.0
LEG_HEIGHT = 750.0
TABLETOP_THICKNESS = 30.0
BENCH_TOP_Z = LEG_HEIGHT + TABLETOP_THICKNESS  # world Z of the bench's usable surface

LEG_SIZE = 40.0
LEG_INSET = 50.0

# Printer footprint (mm) -- a simple base + rear gantry-arch silhouette
PRINTER_WIDTH = 300.0
PRINTER_DEPTH = 300.0
PRINTER_HEIGHT = 400.0
PRINTER_BASE_HEIGHT = 50.0
POST_SIZE = 20.0

# Where each printer sits on the bench (world X, world Y), all at BENCH_TOP_Z.
# Chosen with 250mm clearance between printers and margin on every side --
# see tests/test_garage_workbench.py for the checks this satisfies.
PRINTER_X_POSITIONS = [100.0, 650.0, 1200.0]
PRINTER_Y_POSITION = 150.0


def _leg_corners() -> list[tuple[float, float]]:
    far_x = BENCH_WIDTH - LEG_INSET - LEG_SIZE
    far_y = BENCH_DEPTH - LEG_INSET - LEG_SIZE
    return [
        (LEG_INSET, LEG_INSET),
        (far_x, LEG_INSET),
        (LEG_INSET, far_y),
        (far_x, far_y),
    ]


def _build_workbench() -> Structure:
    tabletop = Translate(
        v=Vector3D(z=LEG_HEIGHT),
        children=[Cube(size=Vector3D(x=BENCH_WIDTH, y=BENCH_DEPTH, z=TABLETOP_THICKNESS))],
    )

    legs = [
        Feature(
            name=f"leg_{i}",
            geometry=Translate(
                v=Vector3D(x=x, y=y, z=0),
                children=[Cube(size=Vector3D(x=LEG_SIZE, y=LEG_SIZE, z=LEG_HEIGHT))],
            ),
        )
        for i, (x, y) in enumerate(_leg_corners())
    ]

    cable_pass_through = Feature(
        name="cable_pass_through",
        geometry=Translate(
            v=Vector3D(x=BENCH_WIDTH / 2, y=BENCH_DEPTH - 50, z=LEG_HEIGHT - 1),
            children=[Cylinder(h=TABLETOP_THICKNESS + 2, r=15, center=False)],
        ),
    )

    frame_system = Substructure(
        name="frame_system",
        footprint=BoundingBox3D(
            min_point=Vector3D(),
            max_point=Vector3D(x=BENCH_WIDTH, y=BENCH_DEPTH, z=BENCH_TOP_Z),
        ),
        base=tabletop,
        additions=legs,
        subtractions=[cable_pass_through],
    )

    return Structure(
        name="workbench",
        material="Steel frame, pine top",
        footprint=BoundingBox3D(
            min_point=Vector3D(),
            max_point=Vector3D(x=BENCH_WIDTH, y=BENCH_DEPTH, z=BENCH_TOP_Z),
        ),
        substructures=[frame_system],
    )


def _build_printer(name: str, *, x: float, y: float) -> Structure:
    frame_system = Substructure(
        name="frame_system",
        base=Cube(
            size=Vector3D(x=PRINTER_WIDTH, y=PRINTER_DEPTH, z=PRINTER_BASE_HEIGHT),
            comment="Printer base / electronics enclosure",
        ),
    )

    post_height = PRINTER_HEIGHT - PRINTER_BASE_HEIGHT - POST_SIZE
    gantry_system = Substructure(
        name="gantry_system",
        additions=[
            Feature(
                name="left_post",
                geometry=Translate(
                    v=Vector3D(x=0, y=PRINTER_DEPTH - POST_SIZE, z=PRINTER_BASE_HEIGHT),
                    children=[Cube(size=Vector3D(x=POST_SIZE, y=POST_SIZE, z=post_height))],
                ),
            ),
            Feature(
                name="right_post",
                geometry=Translate(
                    v=Vector3D(
                        x=PRINTER_WIDTH - POST_SIZE, y=PRINTER_DEPTH - POST_SIZE, z=PRINTER_BASE_HEIGHT
                    ),
                    children=[Cube(size=Vector3D(x=POST_SIZE, y=POST_SIZE, z=post_height))],
                ),
            ),
            Feature(
                name="gantry_bar",
                geometry=Translate(
                    v=Vector3D(
                        x=0,
                        y=PRINTER_DEPTH - POST_SIZE,
                        z=PRINTER_HEIGHT - POST_SIZE,
                    ),
                    children=[Cube(size=Vector3D(x=PRINTER_WIDTH, y=POST_SIZE, z=POST_SIZE))],
                ),
            ),
        ],
    )

    return Structure(
        name=name,
        material="Aluminum extrusion + PETG",
        position=Vector3D(x=x, y=y, z=BENCH_TOP_Z),
        footprint=BoundingBox3D(
            min_point=Vector3D(),
            max_point=Vector3D(x=PRINTER_WIDTH, y=PRINTER_DEPTH, z=PRINTER_HEIGHT),
        ),
        substructures=[frame_system, gantry_system],
    )


def create_example_site() -> Site:
    """A garage: one workbench Structure plus a fleet of printer Structures on top of it."""

    workbench = _build_workbench()
    printers = [
        _build_printer(f"printer_{i + 1}", x=x, y=PRINTER_Y_POSITION)
        for i, x in enumerate(PRINTER_X_POSITIONS)
    ]

    return Site(name="Garage", structures=[workbench, *printers])


def validate_garage_layout(site: Site) -> LayoutReport:
    """Garage-specific layout rules, layered on top of ``Site.validate()``'s generic overlap check.

    Every Structure other than the workbench must rest exactly on the
    workbench's top surface and stay within its footprint -- a scenario
    rule ("things sit on the bench"), not a general hierarchy invariant, so
    it lives here rather than in ``hierarchy.py``.
    """
    violations: List[LayoutViolation] = list(site.validate().violations)

    bench = next((s for s in site.structures if s.name == "workbench"), None)
    if bench is None:
        return LayoutReport(violations=violations)

    bench_bounds = bench.world_bounds()
    if bench_bounds is None:
        return LayoutReport(violations=violations)

    for structure in site.structures:
        if structure is bench:
            continue
        bounds = structure.world_bounds()
        if bounds is None:
            continue

        if bounds.min_point.z != bench_bounds.max_point.z:
            violations.append(
                LayoutViolation(
                    kind="not_on_bench",
                    message=(
                        f"{structure.name} is not resting on the bench surface "
                        f"(z={bounds.min_point.z}, bench top={bench_bounds.max_point.z})"
                    ),
                    structures=[structure.name],
                )
            )
            continue

        within_x = bench_bounds.min_point.x <= bounds.min_point.x and bounds.max_point.x <= bench_bounds.max_point.x
        within_y = bench_bounds.min_point.y <= bounds.min_point.y and bounds.max_point.y <= bench_bounds.max_point.y
        if not (within_x and within_y):
            violations.append(
                LayoutViolation(
                    kind="out_of_bounds",
                    message=f"{structure.name} overhangs the bench",
                    structures=[structure.name],
                )
            )

    return LayoutReport(violations=violations)
