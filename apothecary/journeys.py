"""The page's journeys: the paths a person takes through its windows.

A journey's windows are laid out together as a view, as each focused system's are
(systems.py): listed in the header's ⊞ Windows › Views and on the ring's Panels ›
Windows after the systems', and defined on the page from this registry by
static/systems.js. docs/plans/journeys-2026-11-11.md plans them.

A view is written as a system's is (systems.py's ``Layout``): window ids, a
``stack`` of tabs, a ``row`` or ``column`` of them, the world's window as
``{"world": True}``. A window the page has not got when the view is laid out --
a board's Machine while none is open -- is left out of it.

A journey's steps are numbered on a rail in the header while it is entered, the step
a person is on filled and Next naming the one after (codecartographer's step rail,
after alfred's stage rail). A step brings its windows forward, the one it is about
first; choosing a window it owns -- its tab, ⊞ Windows or a stack's + -- says a
person is on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from .systems import Layout


@dataclass(frozen=True)
class Step:
    id: str
    # Its name on the rail, after its number.
    label: str
    # The rail's tooltip, and what Next says is coming.
    hint: str
    # The windows entering it brings forward, the one it is about first: that one is
    # in front where two share a stack. A closed one is opened again.
    forward: Tuple[str, ...]
    # The windows that say a person is on it, when chosen. Each window is one step's.
    owns: Tuple[str, ...] = ()
    # Whether entering it draws the path of the file the machine has chosen, as the
    # Machine view does.
    draws: bool = False


@dataclass(frozen=True)
class Journey:
    id: str
    title: str
    # Its cell under the ring's Panels › Windows, as a system's view's is, wearing the
    # colour of the group of windows it is mostly in.
    cell: str
    group: str
    # The window its view needs open first, the page's own for a subject, and how
    # that subject is opened: until it is, the view is greyed and says so.
    requires: str
    opened_by: str
    view: Layout
    # What the rail and ⊞ Windows › Journeys call it.
    name: str = ""
    steps: Tuple[Step, ...] = ()
    # What the tour puts it on, on the demo: the machine whose window it opens and the
    # piece it chooses (widgets/tour_popover.js). Empty where the tour cannot stage it.
    staged_on: Tuple[Tuple[str, str], ...] = ()


# Make a thing on a machine: a part chosen in Site, its numbers in Parameters, the
# machine's Print window to slice it and draw its path, the job in Jobs. The machine's
# window and its Print window share a stack at the column's foot, Print in front.
MAKE = Journey(
    id="make",
    title="Make",
    cell="Make view",
    group="Machine",
    requires="machine",
    opened_by="a machine's badge or its row in Site, or Slice on a part's ring",
    view={
        "row": [
            {"world": True, "size": 62},
            {
                "column": [
                    {
                        "stack": ["site", "problems", "pinned", "jobs", "scad"],
                        "size": 22,
                        "active": "site",
                    },
                    {"stack": ["selected"], "size": 26},
                    {"stack": ["part-parameters"], "size": 22},
                    {
                        "stack": ["machine", "machine-print", "pictures", "bench", "settings"],
                        "size": 30,
                        "active": "machine-print",
                    },
                ],
                "size": 38,
            },
        ]
    },
    name="Make a thing",
    staged_on=(("machine", "printer_1"), ("part", "footpedal")),
    steps=(
        Step(
            "choose",
            "Choose",
            "the part, among the site's pieces",
            forward=("site", "selected"),
            owns=("site", "problems", "pinned", "scad"),
        ),
        Step(
            "shape",
            "Shape",
            "its numbers, in Parameters",
            forward=("part-parameters", "selected"),
            owns=("selected", "part-parameters"),
        ),
        Step(
            "slice",
            "Slice",
            "the machine's Print window: the part under makes, then Slice",
            forward=("machine-print",),
            owns=("machine-print",),
        ),
        Step(
            "see",
            "See",
            "the chosen file's path, drawn on the machine",
            forward=("machine-print",),
            draws=True,
        ),
        Step(
            "print",
            "Print",
            "control armed in the Machine, ▶ Print, the job in Jobs",
            forward=("machine", "jobs"),
            owns=("machine", "jobs"),
        ),
    ),
)


# In the order their views are listed, after the systems'.
JOURNEYS: Tuple[Journey, ...] = (MAKE,)


def by_id(journey_id: str) -> Journey:
    return next(j for j in JOURNEYS if j.id == journey_id)


def manifest(journeys: Tuple[Journey, ...] = JOURNEYS) -> List[Dict[str, Any]]:
    """Every journey (or those given: a test's own) as the page reads it: plain JSON."""
    return [
        {
            "id": j.id,
            "title": j.title,
            "cell": j.cell,
            "group": j.group,
            "requires": j.requires,
            "opened_by": j.opened_by,
            "view": j.view,
            "name": j.name,
            "staged_on": dict(j.staged_on),
            "steps": [
                {
                    "id": s.id,
                    "label": s.label,
                    "hint": s.hint,
                    "forward": list(s.forward),
                    "owns": list(s.owns),
                    "draws": s.draws,
                }
                for s in j.steps
            ],
        }
        for j in journeys
    ]
