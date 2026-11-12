"""The page's journeys: the paths a person takes through its windows.

A journey's windows are laid out together as a view, as each focused system's are
(systems.py): listed in the header's ⊞ Windows › Views and on the ring's Panels ›
Windows after the systems', and defined on the page from this registry by
static/systems.js. docs/plans/journeys-2026-11-11.md plans them.

A view is written as a system's is (systems.py's ``Layout``): window ids, a
``stack`` of tabs, a ``row`` or ``column`` of them, the world's window as
``{"world": True}``. A window the page has not got when the view is laid out --
a board's Machine while none is open -- is left out of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from .systems import Layout


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
        }
        for j in journeys
    ]
