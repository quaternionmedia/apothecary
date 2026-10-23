"""Focused systems: one subject each, in windows of its own.

A focused system is a subject the page focuses on -- a rotor/stator pair, a
part, a board -- and how the page holds it: a main window with the subject and
its verbs, and sections, each a window of its own grouped under the system,
closed until asked for (a stack's +, the header's ⊞ Windows, a verb that acts
on it, or the system's view). The view lays the main window, every section and
the world out together.

Each system is one entry here, and everything else reads it: the page
registers its windows and its view from ``manifest()``, given to it as it is
rendered (``static/systems.js``); the canvas ring has a cell for its view under
Panels › Windows (``menu.py``); and the tests hold each widget's sections to its
entry. docs/plans/focused-systems-2026-10-22.md is the plan these follow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

# A view's layout is written in window ids, as panels.js's resolveView reads it:
# "id" is a window (a stack of its own); {"stack": [...ids], "size", "active"} a
# stack of tabs; {"row": [...]} and {"column": [...]} split, each child with an
# optional "size" (per cent); {"world": True, "size"} is the world's window.
Layout = Dict[str, Any]


@dataclass(frozen=True)
class Section:
    """One part of a system, a window of its own: ``<system>-<id>``."""

    id: str
    title: str
    # What it holds, said where the window is listed (its tooltip).
    holds: str


@dataclass(frozen=True)
class System:
    id: str
    title: str
    # Its group in ⊞ Windows and a stack's +.
    group: str
    # The main window's id: the subject and its verbs.
    main: str
    sections: Tuple[Section, ...]
    # The view: the main window, every section and the world laid out together.
    view: Layout
    # Its view's cell under Panels › Windows (a ring label, twelve characters at most).
    cell: str
    # Registered only while its subject is open (a board's Machine), and left out
    # of the layout a browser remembers.
    transient: bool = False

    def window(self, section: str) -> str:
        """A section's window id."""
        return f"{self.id}-{section}"

    def windows(self) -> List[str]:
        """Every window of the system: the main window, then each section's."""
        return [self.main, *(self.window(s.id) for s in self.sections)]


AIRGAP = System(
    id="airgap",
    title="Airgap",
    group="Airgap",
    main="airgap",
    cell="Airgap view",
    sections=(
        Section(
            "metrics",
            "Metrics",
            "the metrics document, grouped: geometry, windings, field, dynamics",
        ),
        Section(
            "field",
            "Winding functions and gap field",
            "each phase's N(θ) and the gap flux density at the rotor angle",
        ),
        Section("gap-map", "Gap map g(θ, φ)", "the gap over stator angle and rotor angle"),
        Section(
            "inductance",
            "Phase inductance and commutation",
            "each phase's L against rotor angle, and the currents applied",
        ),
        Section("torque", "Co-energy and torque", "W′ and T against rotor angle"),
        Section(
            "harmonics",
            "Harmonic overlap",
            "the orders both surfaces carry, and the dominant ripple order",
        ),
        Section("run-up", "Run-up: speed and torque", "the run's speed and torque against time"),
        Section(
            "orbit",
            "Rotor orbit and stator modes",
            "the rotor centre's path, the clearance and touchdown rings, the stator's modes",
        ),
        Section("vibration", "Vibration spectrum", "the run's vibration spectrum"),
        Section("rig", "Rig", "the settings the geometry runs under, one JSON document"),
        Section("sweep", "Sweep", "a metric mapped over two of the SCAD's names"),
    ),  # fmt: skip
    view={
        "row": [
            {
                "column": [
                    {"stack": ["airgap"], "size": 60},
                    {
                        "stack": ["airgap-metrics", "airgap-rig", "airgap-sweep", "selected"],
                        "size": 40,
                        "active": "airgap-metrics",
                    },
                ],
                "size": 34,
            },
            {
                "column": [
                    {"stack": ["airgap-field", "airgap-gap-map"], "size": 50},
                    {
                        "stack": ["airgap-torque", "airgap-inductance", "airgap-harmonics"],
                        "size": 50,
                    },
                ],
                "size": 33,
            },
            {
                "column": [
                    {"world": True, "size": 44},
                    {"stack": ["airgap-run-up", "airgap-orbit", "airgap-vibration"], "size": 56},
                ],
                "size": 33,
            },
        ]
    },
)

PART = System(
    id="part",
    title="Part",
    group="Selected",
    main="selected",
    cell="Part view",
    sections=(),
    view={
        "row": [
            {"world": True, "size": 52},
            {
                "column": [
                    {"stack": ["selected", "scad-editor"], "size": 64, "active": "selected"},
                    {"stack": ["site", "problems", "scad"], "size": 36},
                ],
                "size": 48,
            },
        ]
    },
)

MACHINE = System(
    id="machine",
    title="Machine",
    group="Machine",
    main="machine",
    cell="Machine view",
    transient=True,
    sections=(),
    view={
        "row": [
            {"world": True, "size": 46},
            {
                "column": [
                    {"stack": ["machine", "bench"], "size": 62, "active": "machine"},
                    {"stack": ["site", "jobs", "pinned"], "size": 38},
                ],
                "size": 34,
            },
            {
                "column": [
                    {"stack": ["selected"], "size": 55},
                    {"stack": ["pictures", "settings"], "size": 45},
                ],
                "size": 20,
            },
        ]
    },
)

# In the order their views are listed: under Panels › Windows, after the
# layout's own two cells, and in ⊞ Windows after Default.
SYSTEMS: Tuple[System, ...] = (PART, MACHINE, AIRGAP)


def by_id(system_id: str) -> System:
    return next(s for s in SYSTEMS if s.id == system_id)


def manifest() -> List[Dict[str, Any]]:
    """Every system as the page reads it: plain JSON."""
    return [
        {
            "id": s.id,
            "title": s.title,
            "group": s.group,
            "main": s.main,
            "cell": s.cell,
            "transient": s.transient,
            "sections": [
                {"id": sec.id, "title": sec.title, "holds": sec.holds, "window": s.window(sec.id)}
                for sec in s.sections
            ],
            "view": s.view,
        }
        for s in SYSTEMS
    ]
