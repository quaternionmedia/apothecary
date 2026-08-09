"""Worked example: a garage workbench with a fleet of 3D printers, inside its
own building shell, alongside abstract utility fixtures, storage, and a
subtractive-manufacturing stub.

PROTOTYPE — demonstrates apothecary/hierarchy.py's fractal Assembly against a
concrete, spatially verifiable scene rather than an eyeballed one: one Site
("Garage") containing multiple independently-sourced Structures -- the
workbench, a printer per 3D printer sitting on top of it, the garage
building itself (walls with a door and a window cut into them), one
Structure per abstract utility fixture (lighting, HVAC, electrical, fluids),
a storage shelving unit, and a floor-standing CNC router standing in for
subtractive manufacturing. Each is built from one or more named Substructure
systems -- a printer (and the building, and each fixture) is bought/built as
a whole unit, same as the bench, so all are Structures (siblings within the
Site); the *systems within* a Structure (a frame, a gantry, a wall, a
fixture's housing) are Substructures.

The fixtures, storage, and CNC router are deliberately simple stubs -- a
housing plus, where relevant, one named "output" Feature standing in for the
system's actual business end (a lens, a vent grille, a receptacle face, a
spigot, a shelf) -- left for further development, not modeled in functional
detail. The building shell's door and window are openings only, no panel or
pane.

"Verifiable" means more than "it renders": every printer Structure carries a
``footprint`` (see ``Structure.world_bounds()`` in ``hierarchy.py``), so
``tests/test_garage_workbench.py`` checks, in code, that every printer sits
exactly on the bench's top surface, stays within the bench's footprint, and
doesn't overlap its neighbors -- and that the newer additions (the building,
fixtures, storage, CNC router) don't overlap anything either, without being
held to that same bench-specific rule (see ``BENCH_MOUNTED_STRUCTURES`` and
``validate_garage_layout``) -- not just that the generated .scad "looks about
right."

Manufacturing planning, first slice: ``Job``/``JobStore``/``job_fits_printer``
below give each printer Structure a queue -- create a job with the volume it
needs, and assignment is capacity-checked against the printer's
``build_volume`` and rejected if the printer isn't idle. No rotation/packing
optimization, no multi-job scheduling -- one job per printer at a time,
checked on the same three axes the job was specified in. The CNC router
carries no ``build_volume``, so it never participates in this queue yet --
routing jobs across manufacturing types is future work, not modeled here.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel

from .hierarchy import (
    Assembly,
    Feature,
    LayoutReport,
    LayoutViolation,
    Site,
    Structure,
    Substructure,
)
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

# Usable print area (mm) -- smaller than the printer's physical footprint,
# the same way a real desktop FDM printer's chassis is bigger than its bed.
PRINTER_BUILD_VOLUME = Vector3D(x=220.0, y=220.0, z=250.0)

# Every printer Structure.status is one of these; enforced at the API layer
# (see api.py's PRINTER_STATUSES-checking endpoint), not in hierarchy.py --
# a Structure's status is a free-form string there, this is the scenario's
# closed set of meaningful values for *this* example.
PRINTER_STATUSES = ["idle", "printing", "offline", "maintenance"]

# Structures meant to sit on the workbench's top surface in this scenario --
# an explicit role list, not inferred from current position (which is
# exactly what validate_garage_layout's "is it still on the bench" check
# might be catching as wrong). Everything else in the garage (the building
# itself, wall-/ceiling-mounted fixtures, floor-standing tools, shelving) is
# still checked for generic overlap by Site.validate(), just not against
# this bench-specific rule.
BENCH_MOUNTED_STRUCTURES = {"printer_1", "printer_2", "printer_3"}

# --- Garage building shell (mm) -- wraps around the workbench with room to
# walk in front of it; a hollow rectangular shell, not a solid one, so the
# Structure itself carries no footprint (see _build_garage_building's
# docstring for why) -- only its four walls do.
#
# Depth (y) runs well past the workbench/printer/storage cluster (all of
# which sit within y=0..900) -- a single-car garage is normally longer than
# its equipment needs, with open floor between the door and the workbench,
# not a room sized to shrink-wrap its contents. Width (x) is doubled (3000mm
# -> 6000mm) by moving the east wall out, not by moving GARAGE_MIN -- that
# keeps electrical/fluids (positioned near the west wall) untouched, but
# means storage_shelving and cnc_router (positioned flush against the old
# east wall) must shift by the same delta the wall moved, below, or they'd
# end up stranded mid-floor instead of against the new wall.
GARAGE_MIN = Vector3D(x=-500.0, y=-500.0, z=0.0)
GARAGE_MAX = Vector3D(x=5500.0, y=5500.0, z=2600.0)
WALL_THICKNESS = 100.0

DOOR_WIDTH = 2400.0
DOOR_HEIGHT = 2100.0

WINDOW_SIZE = 900.0
WINDOW_SILL_HEIGHT = 900.0

# --- Utility fixtures (mm) -- abstract stubs for systems a real garage
# needs (lighting, HVAC, electrical, fluids/plumbing), each just a housing
# with one "output" Feature standing in for its actual business end (a
# lens, a vent grille, a receptacle face, a spigot) -- left for further
# development, not modeled in any functional detail here.
LIGHTING_POSITION = Vector3D(x=900.0, y=900.0, z=2500.0)
HVAC_POSITION = Vector3D(x=1400.0, y=1000.0, z=2450.0)
ELECTRICAL_POSITION = Vector3D(x=-400.0, y=300.0, z=900.0)
FLUIDS_POSITION = Vector3D(x=-400.0, y=1200.0, z=400.0)

# --- Storage (mm) -- shelving stub against the wall opposite the fixtures.
# x is GARAGE_MAX.x - 600 (100mm clearance + 500mm own width), not a literal
# constant, so it stays flush against the east wall if that wall ever moves
# again -- see GARAGE_MAX's comment on why this needed updating last time.
STORAGE_POSITION = Vector3D(x=GARAGE_MAX.x - 600.0, y=100.0, z=0.0)
STORAGE_SIZE = Vector3D(x=500.0, y=600.0, z=2000.0)
SHELF_THICKNESS = 30.0
SHELF_HEIGHTS = [400.0, 900.0, 1400.0]

# --- Subtractive manufacturing (mm) -- a floor-standing CNC router, next to
# storage: unlike the bench-top additive printers, deliberately not wired
# into the job queue (no build_volume) -- a visual stub for a machine type
# this scenario doesn't yet route jobs to, not a functional gap to hide.
CNC_ROUTER_POSITION = Vector3D(x=GARAGE_MAX.x - 600.0, y=900.0, z=0.0)
CNC_ROUTER_SIZE = Vector3D(x=500.0, y=600.0, z=900.0)


def _leg_corners() -> list[tuple[float, float]]:
    far_x = BENCH_WIDTH - LEG_INSET - LEG_SIZE
    far_y = BENCH_DEPTH - LEG_INSET - LEG_SIZE
    return [
        (LEG_INSET, LEG_INSET),
        (far_x, LEG_INSET),
        (LEG_INSET, far_y),
        (far_x, far_y),
    ]


def _build_workbench() -> Assembly:
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
        category="furniture",
        substructures=[frame_system],
    )


def _build_printer(name: str, *, x: float, y: float, status: str = "idle") -> Assembly:
    frame_system = Substructure(
        name="frame_system",
        base=Cube(
            size=Vector3D(x=PRINTER_WIDTH, y=PRINTER_DEPTH, z=PRINTER_BASE_HEIGHT),
            comment="Printer base / electronics enclosure",
        ),
    )

    post_height = PRINTER_HEIGHT - PRINTER_BASE_HEIGHT - POST_SIZE

    # A Substructure nested inside a Substructure, containing a Feature with
    # its own child Feature: Structure -> Substructure -> Substructure ->
    # Feature -> Feature, one level deeper than the ADR's fixed four -- a
    # shape the old Feature class (a leaf with no children slot at all)
    # could not represent. Demonstrates apothecary/hierarchy.py's Assembly is
    # genuinely unbounded in depth, not just recursive at one level.
    tensioner_boss = Feature.boss(
        "belt_tensioner_boss",
        position=Vector3D(
            x=POST_SIZE + 10, y=PRINTER_DEPTH - POST_SIZE - 10, z=PRINTER_BASE_HEIGHT
        ),
        diameter=10,
        height=8,
    )
    tensioner_boss.children = [
        Feature.boss(
            "belt_tensioner_relief_chamfer",
            position=Vector3D(
                x=POST_SIZE + 10, y=PRINTER_DEPTH - POST_SIZE - 10, z=PRINTER_BASE_HEIGHT + 8
            ),
            diameter=12,
            height=1,
        )
    ]
    belt_tensioner_system = Substructure(
        name="belt_tensioner_system",
        footprint=BoundingBox3D(
            min_point=Vector3D(
                x=POST_SIZE, y=PRINTER_DEPTH - POST_SIZE - 20, z=PRINTER_BASE_HEIGHT
            ),
            max_point=Vector3D(
                x=POST_SIZE + 20, y=PRINTER_DEPTH - POST_SIZE, z=PRINTER_BASE_HEIGHT + 9
            ),
        ),
        additions=[tensioner_boss],
    )

    gantry_system = Substructure(
        name="gantry_system",
        children=[belt_tensioner_system],
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
                        x=PRINTER_WIDTH - POST_SIZE,
                        y=PRINTER_DEPTH - POST_SIZE,
                        z=PRINTER_BASE_HEIGHT,
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
        build_volume=PRINTER_BUILD_VOLUME,
        status=status,
        category="mechanical",
        substructures=[frame_system, gantry_system],
    )


def _wall_substructure(
    name: str, min_point: Vector3D, max_point: Vector3D, *, subtraction: Optional[Assembly] = None
) -> Assembly:
    """One wall as its own Substructure: an accurate footprint (so zooming
    into the garage shows four real walls, not one placeholder box for the
    whole building -- see _build_garage_building), positioned in the
    building's own local frame the same way every other Substructure is.
    """
    size = Vector3D(
        x=max_point.x - min_point.x, y=max_point.y - min_point.y, z=max_point.z - min_point.z
    )
    return Substructure(
        name=name,
        position=min_point,
        footprint=BoundingBox3D(min_point=Vector3D(), max_point=size),
        base=Cube(size=size),
        subtractions=[subtraction] if subtraction else [],
    )


def _build_garage_building() -> Assembly:
    """The garage's own building shell: four walls with a door and a window
    cut into them. North/south walls run the full exterior width; east/west
    walls fit between them -- standard construction practice, and what keeps
    adjacent walls from claiming the same corner volume (they'd otherwise be
    checked against each other as overlapping siblings, since they're both
    children of this Structure).

    The door and window are openings only (subtracted volume) -- no door
    panel or window pane modeled, a deliberate stub left for further
    development rather than an oversight.
    """
    door_opening = Feature(
        name="door_opening",
        geometry=Translate(
            v=Vector3D(x=(GARAGE_MAX.x - GARAGE_MIN.x - DOOR_WIDTH) / 2, y=-1, z=0),
            children=[Cube(size=Vector3D(x=DOOR_WIDTH, y=WALL_THICKNESS + 2, z=DOOR_HEIGHT))],
        ),
    )
    window_opening = Feature(
        name="window_opening",
        geometry=Translate(
            v=Vector3D(
                x=-1,
                y=(GARAGE_MAX.y - GARAGE_MIN.y - 2 * WALL_THICKNESS - WINDOW_SIZE) / 2,
                z=WINDOW_SILL_HEIGHT,
            ),
            children=[Cube(size=Vector3D(x=WALL_THICKNESS + 2, y=WINDOW_SIZE, z=WINDOW_SIZE))],
        ),
    )

    north_wall = _wall_substructure(
        "north_wall",
        GARAGE_MIN,
        Vector3D(x=GARAGE_MAX.x, y=GARAGE_MIN.y + WALL_THICKNESS, z=GARAGE_MAX.z),
    )
    south_wall = _wall_substructure(
        "south_wall",
        Vector3D(x=GARAGE_MIN.x, y=GARAGE_MAX.y - WALL_THICKNESS, z=GARAGE_MIN.z),
        GARAGE_MAX,
        subtraction=door_opening,
    )
    west_wall = _wall_substructure(
        "west_wall",
        Vector3D(x=GARAGE_MIN.x, y=GARAGE_MIN.y + WALL_THICKNESS, z=GARAGE_MIN.z),
        Vector3D(x=GARAGE_MIN.x + WALL_THICKNESS, y=GARAGE_MAX.y - WALL_THICKNESS, z=GARAGE_MAX.z),
        subtraction=window_opening,
    )
    east_wall = _wall_substructure(
        "east_wall",
        Vector3D(x=GARAGE_MAX.x - WALL_THICKNESS, y=GARAGE_MIN.y + WALL_THICKNESS, z=GARAGE_MIN.z),
        Vector3D(x=GARAGE_MAX.x, y=GARAGE_MAX.y - WALL_THICKNESS, z=GARAGE_MAX.z),
    )

    return Structure(
        name="garage_building",
        material="Wood-framed, steel siding",
        # No footprint at this level, deliberately: an AABB spanning the
        # whole exterior envelope would register as "overlapping" the
        # workbench, the printers, and every fixture this building actually
        # contains -- this model has no notion of a hollow shell, only solid
        # bounding boxes. Each wall's own footprint above is accurate and is
        # what the viewer shows once you zoom in.
        category="wall",
        substructures=[north_wall, south_wall, west_wall, east_wall],
    )


def _build_fixture(
    name: str,
    *,
    material: str,
    position: Vector3D,
    housing_size: Vector3D,
    output: Assembly,
    category: str,
) -> Assembly:
    """An abstract utility fixture: a housing plus one "output" Feature
    standing in for its actual business end. Shared shape for lighting,
    HVAC, electrical, and fluids below -- each is a stub left for further
    development, not a functional system.
    """
    fixture = Substructure(
        name="fixture",
        base=Cube(size=housing_size),
        additions=[output],
        footprint=BoundingBox3D(min_point=Vector3D(), max_point=housing_size),
    )
    return Structure(
        name=name,
        material=material,
        position=position,
        footprint=BoundingBox3D(min_point=Vector3D(), max_point=housing_size),
        category=category,
        substructures=[fixture],
    )


def _build_lighting() -> Assembly:
    return _build_fixture(
        "lighting",
        material="Aluminum housing, LED panel",
        position=LIGHTING_POSITION,
        housing_size=Vector3D(x=400.0, y=100.0, z=50.0),
        output=Feature.boss(
            "light_output", position=Vector3D(x=200, y=50, z=-1), diameter=100, height=2
        ),
        # Lighting runs on the same wiring system as the receptacles --
        # standard M/E/P (mechanical/electrical/plumbing) trade grouping.
        category="electrical",
    )


def _build_hvac() -> Assembly:
    return _build_fixture(
        "hvac",
        material="Galvanized steel ductwork",
        position=HVAC_POSITION,
        housing_size=Vector3D(x=300.0, y=300.0, z=100.0),
        output=Feature.boss(
            "vent_output", position=Vector3D(x=150, y=150, z=-1), diameter=200, height=2
        ),
        category="mechanical",
    )


def _build_electrical() -> Assembly:
    return _build_fixture(
        "electrical",
        material="PVC junction box",
        position=ELECTRICAL_POSITION,
        housing_size=Vector3D(x=100.0, y=150.0, z=200.0),
        output=Feature.boss(
            "outlet_output", position=Vector3D(x=50, y=75, z=90), diameter=60, height=15
        ),
        category="electrical",
    )


def _build_fluids() -> Assembly:
    return _build_fixture(
        "fluids",
        material="Copper pipe stub",
        position=FLUIDS_POSITION,
        housing_size=Vector3D(x=100.0, y=100.0, z=300.0),
        output=Feature.boss(
            "spigot_output", position=Vector3D(x=50, y=50, z=280), diameter=30, height=40
        ),
        category="fluid",
    )


def _build_storage() -> Assembly:
    """Shelving stub: a back panel plus a few shelf Features at increasing
    height -- enough nested structure to demonstrate the shape, not a real
    shelving design.
    """

    def _shelf(name: str, height: float) -> Assembly:
        return Feature(
            name=name,
            geometry=Translate(
                v=Vector3D(z=height),
                children=[
                    Cube(size=Vector3D(x=STORAGE_SIZE.x, y=STORAGE_SIZE.y, z=SHELF_THICKNESS))
                ],
            ),
        )

    shelf_unit = Substructure(
        name="shelf_unit",
        base=Cube(
            size=Vector3D(x=STORAGE_SIZE.x, y=SHELF_THICKNESS, z=STORAGE_SIZE.z),
            comment="Back panel",
        ),
        additions=[_shelf(f"shelf_{i + 1}", height) for i, height in enumerate(SHELF_HEIGHTS)],
        footprint=BoundingBox3D(min_point=Vector3D(), max_point=STORAGE_SIZE),
    )
    return Structure(
        name="storage_shelving",
        material="Powder-coated steel",
        position=STORAGE_POSITION,
        footprint=BoundingBox3D(min_point=Vector3D(), max_point=STORAGE_SIZE),
        category="furniture",
        substructures=[shelf_unit],
    )


def _build_cnc_router() -> Assembly:
    """Subtractive manufacturing, as a floor-standing stub next to storage --
    deliberately not given a build_volume (see BENCH_MOUNTED_STRUCTURES and
    the module-level comment on CNC_ROUTER_POSITION): a visual placeholder
    for a machine type this scenario doesn't yet route jobs to.
    """
    frame_system = Substructure(
        name="frame_system",
        base=Cube(size=CNC_ROUTER_SIZE, comment="CNC router body (stub)"),
    )
    return Structure(
        name="cnc_router",
        material="Steel frame, subtractive (CNC router)",
        position=CNC_ROUTER_POSITION,
        footprint=BoundingBox3D(min_point=Vector3D(), max_point=CNC_ROUTER_SIZE),
        status="idle",
        category="mechanical",
        substructures=[frame_system],
    )


def create_example_site() -> Assembly:
    """A garage: a workbench with a fleet of printers on top of it, inside its
    own building shell, alongside abstract utility fixtures, storage, and a
    subtractive-manufacturing stub -- see this module's docstring.
    """

    workbench = _build_workbench()
    printers = [
        _build_printer(f"printer_{i + 1}", x=x, y=PRINTER_Y_POSITION)
        for i, x in enumerate(PRINTER_X_POSITIONS)
    ]

    return Site(
        name="Garage",
        structures=[
            workbench,
            *printers,
            _build_garage_building(),
            _build_lighting(),
            _build_hvac(),
            _build_electrical(),
            _build_fluids(),
            _build_storage(),
            _build_cnc_router(),
        ],
    )


def validate_garage_layout(site: Assembly) -> LayoutReport:
    """Garage-specific layout rules, layered on top of ``Site.validate()``'s generic overlap check.

    Every structure in BENCH_MOUNTED_STRUCTURES must rest exactly on the
    workbench's top surface and stay within its footprint -- a scenario
    rule ("machines sit on the bench"), not a general hierarchy invariant,
    so it lives here rather than in ``hierarchy.py``. Everything else in the
    garage (the building shell, fixtures, storage, the floor-standing CNC
    router) is still checked for generic overlap by ``site.validate()``
    above, just not against this bench-specific rule -- they were never
    meant to be bench-mounted in the first place.
    """
    violations: List[LayoutViolation] = list(site.validate().violations)

    bench = next((s for s in site.children if s.name == "workbench"), None)
    if bench is None:
        return LayoutReport(violations=violations)

    bench_bounds = bench.world_bounds()
    if bench_bounds is None:
        return LayoutReport(violations=violations)

    for structure in site.children:
        if structure.name not in BENCH_MOUNTED_STRUCTURES:
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

        within_x = (
            bench_bounds.min_point.x <= bounds.min_point.x
            and bounds.max_point.x <= bench_bounds.max_point.x
        )
        within_y = (
            bench_bounds.min_point.y <= bounds.min_point.y
            and bounds.max_point.y <= bench_bounds.max_point.y
        )
        if not (within_x and within_y):
            violations.append(
                LayoutViolation(
                    kind="out_of_bounds",
                    message=f"{structure.name} overhangs the bench",
                    structures=[structure.name],
                )
            )

    return LayoutReport(violations=violations)


JOB_STATUSES = ["queued", "assigned", "printing", "done"]


class Job(BaseModel):
    """A print job: a required volume, waiting for (or assigned to) a printer.

    ``assigned_printer`` is kept even after a job is marked ``done`` -- a
    record of which printer produced it, not just current-assignment state.
    """

    name: str
    required_volume: Vector3D
    status: str = "queued"
    assigned_printer: Optional[str] = None


def job_fits_printer(job: Job, printer: Assembly) -> bool:
    """Whether ``printer.build_volume`` is large enough for ``job.required_volume``.

    Axis-aligned, no rotation: the job's X/Y/Z must each fit the printer's
    build volume in that same axis. A printer with no ``build_volume`` set
    (e.g. the workbench) never fits any job.
    """
    build_volume = printer.build_volume
    if build_volume is None:
        return False
    required = job.required_volume
    return (
        required.x <= build_volume.x
        and required.y <= build_volume.y
        and required.z <= build_volume.z
    )


class JobStore:
    """In-memory job queue, one list per site name (prototype -- see
    site_store.py's SiteStore for the same caveats: in-process only, lost on
    restart, not shared across worker processes).
    """

    def __init__(self) -> None:
        self._jobs: Dict[str, List[Job]] = {}

    def list_for_site(self, site_name: str) -> List[Job]:
        return self._jobs.setdefault(site_name, [])

    def add(self, site_name: str, job: Job) -> Job:
        jobs = self.list_for_site(site_name)
        if any(existing.name == job.name for existing in jobs):
            raise ValueError(f"Job {job.name!r} already exists for site {site_name!r}")
        jobs.append(job)
        return job

    def get(self, site_name: str, job_name: str) -> Job:
        for job in self.list_for_site(site_name):
            if job.name == job_name:
                return job
        raise KeyError(job_name)

    def reset(self, site_name: str) -> None:
        """Clear a site's job queue -- called when the site's own layout is
        reset, since a reset re-idles every printer and a job still marked
        "assigned" to one would otherwise be stale.
        """
        self._jobs[site_name] = []
