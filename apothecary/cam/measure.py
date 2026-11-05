"""As cut: what the tool did, measured against what the design asked.

The simulated router keeps every block it ran (``SimulatedRouter.trace``: where
each began and ended in work coordinates, at what feed, and whether it was a
rapid). A cutting move at or below a depth, widened by the tool's radius, is
material gone; its extent is what a caliper would find on the piece.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

from .models import Bounds

Trace = Iterable[dict]  # each: start, end (work coordinates), feed, rapid

Window = Tuple[float, float, float, float]  # x0, y0, x1, y1


def extent(
    trace: Trace, z: float, tool_diameter: float, within: Optional[Window] = None
) -> Optional[Bounds]:
    """The XY extent of material the tool took at depth ``z`` or below -- every
    cutting move whose both ends are at or under ``z``, widened by the tool's radius --
    inside ``within`` when a window is given; None when no such move ran."""
    r = tool_diameter / 2
    low: Optional[List[float]] = None
    high: Optional[List[float]] = None
    for block in trace:
        if block["rapid"]:
            continue
        a, b = block["start"], block["end"]
        if a["z"] > z + 1e-6 or b["z"] > z + 1e-6:
            continue
        for p in (a, b):
            if within is not None and not (
                within[0] <= p["x"] <= within[2] and within[1] <= p["y"] <= within[3]
            ):
                continue
            lo = [p["x"] - r, p["y"] - r, min(a["z"], b["z"])]
            hi = [p["x"] + r, p["y"] + r, max(a["z"], b["z"])]
            low = lo if low is None else [min(u, v) for u, v in zip(low, lo, strict=True)]
            high = hi if high is None else [max(u, v) for u, v in zip(high, hi, strict=True)]
    if low is None or high is None:
        return None
    return Bounds(min=[round(v, 3) for v in low], max=[round(v, 3) for v in high])


def size(bounds: Optional[Bounds]) -> Optional[Tuple[float, float]]:
    """A width and a height, from an extent."""
    if bounds is None:
        return None
    return (round(bounds.max[0] - bounds.min[0], 3), round(bounds.max[1] - bounds.min[1], 3))
