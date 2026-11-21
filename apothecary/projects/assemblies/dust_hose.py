"""A dust hose on a port, through the stepped adapter, placed by its connections.

Three registered parts side by side: the hose's end and the port, two nodes of the
one ``dust_port`` part at two of its presets, and the adapter at its defaults. None
is built from another; two connections say how they meet, and ``connections.place``
stands each where its interfaces meet. The hose stays where it is, its end up; the
adapter stands on it, pushed all the way in; the port is turned over and put on the
adapter's step, or its end ``b``, as far as it goes.

``build(port)`` takes ``"32"`` or ``"25"``: the adapter's step in ``dust_port@port_32``,
or its end ``b`` in ``dust_port@port_25``. ``report()`` says how each connection fits
and which numbers are still a stub's.
"""

from __future__ import annotations

from typing import List, Tuple

from apothecary.connections import ConnectionReport, place
from apothecary.hierarchy import Assembly, Connection
from apothecary.projects.parts.dust_port import PRESETS

PORTS = {"32": ("port_32", "step"), "25": ("port_25", "b")}


def unplaced(port: str = "32") -> Assembly:
    """The assembly as written: its parts, where none has been put yet, and how they meet."""
    preset, end = PORTS[port]
    return Assembly(
        name=f"dust_hose_{port}",
        role="assembly",
        children=[
            Assembly(
                name="hose", role="part", part_ref="dust_port", params=PRESETS["hose_40"].params
            ),
            Assembly(name="adapter", role="part", part_ref="hose_adapter"),
            Assembly(name="port", role="part", part_ref="dust_port", params=PRESETS[preset].params),
        ],
        connections=[
            Connection(a="hose.end", b="adapter.a"),
            Connection(a=f"adapter.{end}", b="port.end"),
        ],
    )


def build(port: str = "32") -> Tuple[Assembly, ConnectionReport]:
    """The assembly placed by its connections, and what ``check`` says of it."""
    return place(unplaced(port))


def report(port: str = "32") -> List[str]:
    return build(port)[1].lines()


__all__ = ["PORTS", "build", "report", "unplaced"]
