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
from typing import Any, Dict, List, Optional, Tuple

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
    # Where it opens when asked for outside its view: beside the system's main
    # window as a tab (None), as a tab beside another window (its id), in a stack of
    # its own in the column beside the world ("column"), or beside the world
    # ("beside") -- panels.js's homes.
    home: Optional[str] = None
    # The ring's verbs that act on it, which open it: an action named, or every
    # action under a prefix that ends with ":".
    verbs: Tuple[str, ...] = ()
    # The kind of subject it is for (a board that is a printer, or a devkit), where it
    # is for one kind only: a subject of another kind has no such window.
    kind: Optional[str] = None
    # Opened when a link to its subject is followed: a link is a request for it.
    on_link: bool = False


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
    # How a person opens its subject: said where its view is asked for without it.
    opened_by: str
    # Registered only while its subject is open (a board's Machine), and left out
    # of the layout a browser remembers.
    transient: bool = False

    def window(self, section: str) -> str:
        """A section's window id."""
        return f"{self.id}-{section}"

    def home(self, section: Section) -> str:
        """Where a section opens when asked for outside the view."""
        return section.home or self.main

    def windows(self) -> List[str]:
        """Every window of the system: the main window, then each section's."""
        return [self.main, *(self.window(s.id) for s in self.sections)]


AIRGAP = System(
    id="airgap",
    title="Airgap",
    group="Airgap",
    main="airgap",
    cell="Airgap view",
    opened_by="Panels › Airgap › Airgap",
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
        Section(
            "sweep",
            "Sweep",
            "a metric mapped over two of the SCAD's names",
            verbs=("airgap:sweep",),
        ),
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
    group="Part",
    # Selected: the piece, its part, what it is drawn from, its envelope and ghost,
    # Download SCAD, and the staged changes' bar (Apply, Revert, Defaults, Undo, Redo).
    main="selected",
    cell="Part view",
    opened_by="a piece's row in Site",
    sections=(
        # In a stack of its own under Selected, so the bar's Apply stays in view.
        Section(
            "parameters",
            "Parameters",
            "the piece's numbers as controls, tied to its text",
            home="column",
            verbs=("part:edit",),
            on_link=True,
        ),
        # Beside the world, as tall as it.
        Section(
            "scad",
            "SCAD",
            "the part's SCAD in the editor: checked as typing stops, rendered, saved as a variant",
            home="beside",
            verbs=("part:scad", "part:save"),
        ),
        Section(
            "variants",
            "Variants",
            "the part's saved variants, each drawn again from its row, and the compare",
            home="part-parameters",
            verbs=("part:variant:",),
        ),
        Section(
            "history",
            "History",
            "this tab's recent applies of the part, each drawn again from the cache",
            home="part-parameters",
        ),
        Section(
            "readiness",
            "Readiness",
            "whether the part is ready to print and check against a real one",
            home="part-parameters",
        ),
    ),  # fmt: skip
    view={
        "row": [
            {"world": True, "size": 44},
            {
                "column": [
                    {"stack": ["selected"], "size": 38},
                    {
                        "stack": [
                            "part-parameters",
                            "part-variants",
                            "part-history",
                            "part-readiness",
                        ],
                        "size": 62,
                        "active": "part-parameters",
                    },
                ],
                "size": 26,
            },
            {
                "column": [
                    {"stack": ["part-scad"], "size": 68},
                    {"stack": ["site", "problems", "scad"], "size": 32},
                ],
                "size": 30,
            },
        ]
    },
)

MACHINE = System(
    id="machine",
    title="Machine",
    group="Machine",
    # The Machine: the board's head -- its link verbs, the control latch, ⏹ E-STOP --
    # what it is and its link, and its state.
    main="machine",
    cell="Machine view",
    opened_by="a board's ring, Device › Open",
    transient=True,
    # In one stack of their own under the Machine, so its head and E-STOP stay in view.
    # A printer's Machine has a printer's sections and a devkit's a devkit's: the page
    # attaches those of the board's kind, again when it is identified as another.
    sections=(
        Section(
            "status",
            "Status",
            "a printer's hotend, bed, position, SD print, endstops and filament",
            home="column",
            verbs=("device:poll",),
            kind="printer",
            on_link=True,
        ),
        Section(
            "temperature",
            "Temperature",
            "a printer's hotend and bed against time, their targets dashed",
            home="column",
            kind="printer",
        ),
        Section(
            "print",
            "Print",
            "a printer's print from here: the files kept, what it makes, Slice, the print",
            home="column",
            verbs=("print:", "slice:"),
            kind="printer",
        ),
        Section(
            "level",
            "Bed level",
            "a printer's bed: probed or read, its mesh, its corners, its records",
            home="column",
            verbs=("level:",),
            kind="printer",
        ),
        Section(
            "sketch",
            "Sketch",
            "a devkit's sketch: what it should run, and what it was heard saying",
            home="column",
            # A hello heard is said here as well as in the log.
            verbs=("device:query", "device:listen"),
            kind="devkit",
            on_link=True,
        ),
        Section(
            "flashing",
            "Flashing",
            "a devkit's sketch built and uploaded to this port, and the task's output",
            home="column",
            verbs=("device:flash",),
            kind="devkit",
        ),
        Section(
            "log",
            "Log",
            "the board's one log: a printer's comms, or a devkit's serial output",
            home="column",
            verbs=("device:listen", "device:query", "device:probe"),
            on_link=True,
        ),
    ),  # fmt: skip
    # Every window of the board's kind in view, none behind another: a printer's
    # Status and Temperature under the Machine, its Print, Bed level and Log beside them;
    # a devkit's Sketch and Flashing under it, its Log beside them. Selected and Site
    # stay, each at a foot, so a board's row and its Device line are there to act on.
    view={
        "row": [
            {"world": True, "size": 34},
            {
                "column": [
                    {"stack": ["machine"], "size": 26},
                    {"stack": ["machine-status", "machine-sketch"], "size": 25},
                    {"stack": ["machine-temperature", "machine-flashing"], "size": 25},
                    {"stack": ["selected"], "size": 24},
                ],
                "size": 33,
            },
            {
                "column": [
                    {"stack": ["machine-print"], "size": 34},
                    {"stack": ["machine-level"], "size": 22},
                    {"stack": ["machine-log"], "size": 22},
                    {"stack": ["site", "jobs", "pinned"], "size": 22, "active": "site"},
                ],
                "size": 33,
            },
        ]
    },
)


# In the order their views are listed: under Panels › Windows, after the
# layout's own two cells, and in ⊞ Windows after Default.
SYSTEMS: Tuple[System, ...] = (PART, MACHINE, AIRGAP)


def by_id(system_id: str) -> System:
    return next(s for s in SYSTEMS if s.id == system_id)


def manifest(systems: Tuple[System, ...] = SYSTEMS) -> List[Dict[str, Any]]:
    """Every system (or those given: a test's own) as the page reads it: plain JSON."""
    return [
        {
            "id": s.id,
            "title": s.title,
            "group": s.group,
            "main": s.main,
            "cell": s.cell,
            "opened_by": s.opened_by,
            "transient": s.transient,
            "sections": [
                {
                    "id": sec.id,
                    "title": sec.title,
                    "holds": sec.holds,
                    "window": s.window(sec.id),
                    "home": s.home(sec),
                    "verbs": list(sec.verbs),
                    "kind": sec.kind,
                    "on_link": sec.on_link,
                }
                for sec in s.sections
            ],
            "view": s.view,
        }
        for s in systems
    ]
