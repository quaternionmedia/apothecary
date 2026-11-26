"""A printer's print area from its plate as kept: where its nozzle stood over the plate's
front-left and back-right corners (Fixes' ⌖ Here, ``bed_shims.keep_position``), the
rectangle between them its slices' OrcaSlicer ``printable_area``. A slice is then arranged
at the middle of the plate the printer has, and kept on it, rather than at the middle of
the area its part's figure names (printer_1's Ender 3 profile says 220 x 220, Creality's
published figure, which printer_1's 300 mm plate is not).

Where either corner is not kept, or the two do not stand a plate apart (the back-right
not behind and right of the front-left by ``SMALLEST`` each way), the profile's own area
is used, as before, and the slice's setting says where it is from.
"""

from __future__ import annotations

import json
from typing import Optional, Tuple

from .. import bed_shims
from .profiles import PrinterProfile

MODULE = "orcaslicer"
# The least a plate is across, each way, mm: corners kept nearer than this are a corner
# kept in the wrong place, not a plate.
SMALLEST = 50.0

Area = Tuple[float, float, float, float]  # x0, y0, x1, y1, the nozzle's coordinates


def area(site: Optional[str], printer: Optional[str]) -> Optional[Area]:
    """The plate kept for ``printer``, front-left to back-right; None where it is not."""
    if not site or not printer:
        return None
    plate = bed_shims.positions(site, printer).get("plate") or {}
    fl, br = plate.get("front_left"), plate.get("back_right")
    if not fl or not br:
        return None
    x0, y0, x1, y1 = (float(fl["x"]), float(fl["y"]), float(br["x"]), float(br["y"]))
    if x1 - x0 < SMALLEST or y1 - y0 < SMALLEST:
        return None
    return x0, y0, x1, y1


def applied(
    profile: PrinterProfile, site: Optional[str], printer: Optional[str], module: str
) -> PrinterProfile:
    """``profile`` with the plate kept for the printer as its slices' ``printable_area``,
    origin ``measured``; the profile as it is where no plate is kept, or the slice is by
    another slicer module."""
    if module != MODULE:
        return profile
    found = area(site, printer)
    if found is None:
        return profile
    x0, y0, x1, y1 = found
    corners = [f"{x0:g}x{y0:g}", f"{x1:g}x{y0:g}", f"{x1:g}x{y1:g}", f"{x0:g}x{y1:g}"]
    section = json.loads(json.dumps(profile.sections.get(MODULE) or {}))
    held = (section.get("set") or {}).get("machine", {}).get("printable_area") or {}
    was = held.get("value")
    section.setdefault("set", {}).setdefault("machine", {})["printable_area"] = {
        "value": corners,
        "source": f"{site}'s {printer}: its plate kept with Here, the nozzle over its "
        f"front-left corner at {x0:g}, {y0:g} and its back-right at {x1:g}, {y1:g} "
        "(bed/positions.json)",
        "origin": "measured",
        "note": f"{x1 - x0:g} x {y1 - y0:g} mm"
        + (f", over the profile's {', '.join(was)}" if isinstance(was, list) else ""),
    }
    return profile.model_copy(update={"sections": {**profile.sections, MODULE: section}})
