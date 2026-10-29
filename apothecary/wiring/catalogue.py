"""The devices on the bench, as carlos's catalogue names them.

Carlos addresses a device as ``<maker>.<model>`` and describes it in one JSON
file: what it is, its sockets, and which face each socket is on. The entries in
``catalogue/`` are in that format, one file each, named for its id, so a file
can be offered to carlos's catalogue as it is. Apothecary reads from them only
what it writes connections with: the id and the sockets.

A board's faces follow its drawing: the front is its component side seen from
above with +y up, so its edges are left (x min), right (x max), bottom (y min)
and top (y max), and its box is its bounds -- width, height and depth along x,
y and z.

``PARTS`` says which part draws which device. A node made of a part that is
not in it has no type in a patch.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parent / "catalogue"

# The computer apothecary runs on: the far end of every USB lead it observes.
HOST = "apothecary.host"

PARTS: Dict[str, str] = {
    "esp32_devkitc": "espressif.esp32-devkitc",
    "creality_v422": "creality.v422",
    "arduino_uno": "arduino.uno-r3",
    "footpedal": "quaternionmedia.footpedal",
}

# The connectors a USB lead plugs into, as carlos's vocabulary spells them.
USB_CONNECTORS = ("USB-A", "USB-B", "USB-C", "micro-USB")


@lru_cache(maxsize=None)
def entries() -> Dict[str, dict]:
    """Every entry, by id."""
    found: Dict[str, dict] = {}
    for path in sorted(ROOT.glob("*.json")):
        entry = json.loads(path.read_text(encoding="utf-8"))
        found[entry["id"]] = entry
    return found


def device_of(part_ref: Optional[str]) -> Optional[str]:
    """The catalogue id of the device a part draws, or None."""
    return PARTS.get(part_ref) if part_ref else None


def usb_jack(device: str) -> Optional[str]:
    """The name of a device's USB socket, when it has exactly one."""
    sockets = [j["name"] for j in entries()[device]["jacks"] if j["connector"] in USB_CONNECTORS]
    return sockets[0] if len(sockets) == 1 else None
