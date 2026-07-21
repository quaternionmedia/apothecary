"""Worked example for the Site/Structure/Substructure/Feature prototype.

PROTOTYPE — not part of the ratified API. Demonstrates the design proposed in
``governance/qm/adr/DRAFT-site-structure-substructure-feature-hierarchy.md``
against a plausible complex subassembly: one Structure (a control panel)
built from three independent systems (Substructures) — mounting, ventilation,
and cable routing.
"""

from __future__ import annotations

from .hierarchy import Feature, Site, Structure, Substructure
from .models.units import HardwareSizes, PrintSettings
from .models.vectors import Vector3D
from .primitives import Cube

_CORNERS = [(6, 6), (94, 6), (6, 54), (94, 54)]


def create_example_site() -> Site:
    """A control-panel Structure with mounting, ventilation, and cable-routing systems."""

    ps = PrintSettings()

    mounting_system = Substructure(
        name="mounting_system",
        base=Cube(size=Vector3D(x=100, y=60, z=4), comment="Panel plate"),
        additions=[
            Feature.boss(
                f"corner_boss_{i}",
                position=Vector3D(x=x, y=y, z=4),
                diameter=8,
                height=6,
            )
            for i, (x, y) in enumerate(_CORNERS)
        ],
        subtractions=[
            Feature.clearance_hole(
                f"corner_hole_{i}",
                position=Vector3D(x=x, y=y, z=-1),
                nominal_diameter=HardwareSizes.M3,
                depth=12,
                print_settings=ps,
            )
            for i, (x, y) in enumerate(_CORNERS)
        ],
    )

    ventilation_system = Substructure(
        name="ventilation_system",
        position=Vector3D(x=20, y=45, z=0),
        base=Cube(size=Vector3D(x=30, y=10, z=4), comment="Vent boss"),
        subtractions=[
            Feature.clearance_hole(
                f"vent_slot_{col}",
                position=Vector3D(x=3 + col * 4, y=5, z=-1),
                nominal_diameter=2.5,
                depth=6,
                print_settings=ps,
            )
            for col in range(6)
        ],
    )

    cable_routing_system = Substructure(
        name="cable_routing_system",
        position=Vector3D(x=70, y=10, z=0),
        base=Cube(size=Vector3D(x=20, y=20, z=4), comment="Grommet boss"),
        subtractions=[
            Feature.clearance_hole(
                "cable_grommet_hole",
                position=Vector3D(x=10, y=10, z=-1),
                nominal_diameter=12,
                depth=6,
                print_settings=ps,
            )
        ],
    )

    control_panel = Structure(
        name="control_panel",
        material="PETG",
        substructures=[mounting_system, ventilation_system, cable_routing_system],
    )

    return Site(name="Dispensing Cabinet Control Panel", structures=[control_panel])
