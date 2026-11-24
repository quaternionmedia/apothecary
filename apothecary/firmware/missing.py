"""Why a machine's board is not found, read without opening a port.

A machine's board is expected when a board is pinned at the machine's node or beneath
it (``FirmwareState.bindings``) and the port scan names none on any port. What can be
read without touching a port says how far the board got, in the order it gets there:
on USB, given a serial port by the kernel, that port open to this user, and named by
the scan. The first check that is ``off`` is what to do next; those after it are not
reached. Beside them, where the board was last found (the record's ``seen``) and every
serial port plugged in now, with the node a pin names it for.

Read from the kernel's own list of USB devices (``/sys/bus/usb/devices``): each
device's vendor, product and serial number, the socket it is in (``1-1.2``: bus 1,
socket 1, then the hub's socket 2) and the serial ports its driver made. Where that
list is not there (not Linux) the USB checks are ``unread`` and the serial ports alone
are read. The simulated serial engine reads no USB: a simulated server's machines are
its own.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .models import USB_MAKE_RE, BoardInfo, DeviceInfo, usb_make

SYS_USB = Path("/sys/bus/usb/devices")
MAC_RE = re.compile(r"^([0-9a-f]{2}[:-]){5}[0-9a-f]{2}$")

# What a bridge is, by its make, said beside its port; a make not here is its ids.
BRIDGES = {
    "usb:0403:6001": "FTDI FT232R",
    "usb:0403:6015": "FTDI FT231X",
    "usb:1a86:7523": "CH340",
    "usb:1a86:55d4": "CH9102",
    "usb:10c4:ea60": "CP2102",
    "usb:2341:0043": "Arduino Uno",
}


@dataclass
class UsbDevice:
    """One device on USB, as the kernel lists it."""

    place: str  # the kernel's name for its socket: 1-1.2
    make: str  # usb:vvvv:pppp
    serial: Optional[str] = None
    product: Optional[str] = None
    ports: List[str] = field(default_factory=list)  # the serial ports its driver made


@dataclass
class Check:
    id: str
    label: str
    state: str  # ok, off, unread, or after: not reached, an earlier one is off
    says: str = ""


def _read(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip() or None
    except OSError:
        return None


def usb_devices(root: Path = SYS_USB) -> Optional[List[UsbDevice]]:
    """Every device the kernel lists on USB, hubs left out; None where there is no
    such list."""
    from .gcode import serial_engine

    if serial_engine() == "simulated":
        return []
    if not root.is_dir():
        return None
    out = []
    for dev in sorted(root.iterdir()):
        if ":" in dev.name or dev.name.startswith("usb"):
            continue  # an interface, or a bus's own root hub
        vid, pid = _read(dev / "idVendor"), _read(dev / "idProduct")
        if not (vid and pid) or _read(dev / "bDeviceClass") == "09":
            continue  # a hub
        ports = sorted(
            {
                f"/dev/{p.name}"
                for pattern in ("*:*/tty[A-Z]*", "*:*/tty/tty[A-Z]*")
                for p in dev.glob(pattern)
            }
        )
        out.append(
            UsbDevice(
                place=dev.name,
                make=usb_make(vid, pid) or f"usb:{vid}:{pid}",
                serial=_read(dev / "serial"),
                product=_read(dev / "product"),
                ports=ports,
            )
        )
    return out


def bridge(make: Optional[str]) -> str:
    """A make as a person reads it: ``FTDI FT232R (0403:6001)``."""
    if not make:
        return "a USB bridge"
    ids = make.removeprefix("usb:")
    return f"{BRIDGES[make]} ({ids})" if make in BRIDGES else ids


def socket(place: Optional[str]) -> str:
    """A USB place as a person reads it: ``1-1.2`` is the hub's socket 2."""
    if not place:
        return ""
    hops = place.split("-", 1)[-1].split(".")
    return f"USB socket {place}" + (f" (a hub's socket {hops[-1]})" if len(hops) > 1 else "")


def _what_it_is(identity: str, last: Optional[DeviceInfo], seen: Optional[dict]) -> dict:
    """What a pin's identity says of the board on USB: its make, its serial number,
    or neither (a MAC, a port typed by hand) -- then what its last record says."""
    key = identity.strip().lower()
    make = serial = None
    if USB_MAKE_RE.match(key):
        make = key
    elif MAC_RE.match(key) or identity.startswith("/"):
        pass
    else:
        serial = identity.strip()
    for record in (last, seen):
        if record is None:
            continue
        vid = record.vid if isinstance(record, DeviceInfo) else record.get("vid")
        pid = record.pid if isinstance(record, DeviceInfo) else record.get("pid")
        sn = record.serial_number if isinstance(record, DeviceInfo) else record.get("serial_number")
        make = make or usb_make(vid, pid)
        if serial is None and (sn or "").strip() and not USB_MAKE_RE.match(key):
            serial = sn.strip()
    return {"make": make, "serial": serial}


def named(want: dict, identity: str) -> str:
    """The expected board as a person reads it: its bridge and its serial number
    (``FTDI FT232R (0403:6001) A106ZTEU``), the bridge alone for a pin by make, the
    serial number alone where its make was never read, else the pin as typed."""
    if want["make"]:
        return bridge(want["make"]) + (f" {want['serial']}" if want["serial"] else "")
    return want["serial"] or identity


def _is_it(dev: UsbDevice, want: dict) -> bool:
    if want["serial"]:
        return (dev.serial or "").strip().lower() == want["serial"].lower()
    return bool(want["make"]) and dev.make == want["make"]


def explain(
    identity: str,
    kind: Optional[str],
    *,
    usb: Optional[List[UsbDevice]],
    listed: Dict[str, BoardInfo],
    last_port: Optional[str] = None,
    last: Optional[DeviceInfo] = None,
    seen: Optional[dict] = None,
    can_open=None,
) -> dict:
    """The checks for one expected board, in the order a board gets through them."""
    can_open = can_open or (lambda port: os.access(port, os.R_OK | os.W_OK))
    want = _what_it_is(identity, last, seen)
    machine = kind or "machine"
    board = named(want, identity)
    made = bridge(want["make"])
    where_last = ""
    if last_port or (seen or {}).get("location"):
        where_last = "It was last found" + (f" on {last_port}" if last_port else "")
        place = (seen or {}).get("location")
        where_last += (f", in {socket(place)}" if place else "") + "."

    on_usb = [d for d in usb or [] if _is_it(d, want)]
    by_port = [
        p
        for p, b in listed.items()
        if (want["serial"] and (b.serial_number or "").strip().lower() == want["serial"].lower())
        or (not want["serial"] and want["make"] and usb_make(b.vid, b.pid) == want["make"])
        or (identity.startswith("/") and os.path.realpath(identity) == os.path.realpath(p))
    ]
    checks: List[Check] = []
    todo = ""

    # 1. On USB.
    if usb is None or not (want["serial"] or want["make"]):
        found = bool(by_port)
        checks.append(
            Check(
                "usb",
                "On USB",
                "ok" if found else "unread",
                f"its port {by_port[0]} is listed" if found else "USB is not read here",
            )
        )
    elif on_usb:
        d = on_usb[0]
        checks.append(Check("usb", "On USB", "ok", f"{board} is in {socket(d.place)}"))
    else:
        checks.append(Check("usb", "On USB", "off", f"nothing on USB is {board}"))
        todo = (
            f"Switch the {machine} on and seat its USB cable at both ends: a cable made only "
            "to charge carries no data. Plugged in through a hub, try a socket on the "
            f"computer itself. {where_last}"
        ).strip()
        # Another of its make, with another serial number: a board swapped for this one.
        if want["serial"] and want["make"]:
            for d in usb or []:
                if d.make == want["make"] and d.serial and d.ports:
                    todo += (
                        f" {made} {d.serial} is on {d.ports[0]}: if that is this {machine}'s "
                        "board now, pin it here."
                    )

    # 2. A serial port.
    ports = sorted({*(p for d in on_usb for p in d.ports), *by_port})
    if todo:
        checks.append(Check("port", "A serial port", "after"))
    elif ports:
        checks.append(Check("port", "A serial port", "ok", f"the kernel made {', '.join(ports)}"))
    else:
        checks.append(
            Check("port", "A serial port", "off", "on USB, with no serial port: no driver took it")
        )
        todo = "Unplug it and plug it in again."
        if want["make"] == "usb:1a86:7523":
            todo += (
                " If it stays without one, brltty (a braille display service) takes CH340 "
                "bridges on some Linux systems: removing it frees the bridge."
            )
        else:
            todo += " If it stays without one, its driver is not loaded on this computer."

    # 3. Open to this user.
    port = ports[0] if ports else None
    if todo:
        checks.append(Check("open", "Open to this user", "after"))
    elif port and not can_open(port):
        checks.append(
            Check(
                "open",
                "Open to this user",
                "off",
                f"{port} is not readable and writable by this user",
            )
        )
        todo = "Add this user to the port's group (dialout on most Linux systems: sudo usermod -aG dialout $USER), then log in again."
    else:
        checks.append(Check("open", "Open to this user", "ok", f"{port} is readable and writable"))

    # 4. Named by the scan.
    if todo:
        checks.append(Check("scan", "Found by the scan", "after"))
    else:
        other = last.printer.machine if last is not None and last.printer is not None else None
        if other and kind and other != kind:
            says = f"its board last answered as a {other}, and this machine is a {kind}"
            todo = (
                f"Pin the board that answers as a {kind} here, or this board on the {other} it is."
            )
        else:
            says = "the last scan did not name it"
            todo = (
                "It is scanned for afresh by itself: a board that has only just come up "
                "answers. If it stays unnamed, unplug it and plug it in again."
            )
        checks.append(Check("scan", "Found by the scan", "off", says))

    return {
        "identity": identity,
        "board": board,
        "make": want["make"],
        "bridge": made,
        "serial": want["serial"],
        "last_port": last_port,
        "last_place": (seen or {}).get("location"),
        "last_said": where_last,
        "checks": [asdict(c) for c in checks],
        "todo": todo,
    }


def plugged(
    usb: Optional[List[UsbDevice]], listed: Dict[str, BoardInfo], claims: Dict[str, str]
) -> List[dict]:
    """Every serial port plugged in now: its port, make, serial number, socket, and
    the node a pin names it for."""
    out = {}
    for d in usb or []:
        for p in d.ports:
            out[p] = {
                "port": p,
                "make": d.make,
                "bridge": bridge(d.make),
                "serial": d.serial,
                "place": d.place,
                "product": d.product,
            }
    for p, b in listed.items():
        make = usb_make(b.vid, b.pid)
        out.setdefault(
            p,
            {
                "port": p,
                "make": make,
                "bridge": bridge(make),
                "serial": b.serial_number,
                "place": b.location,
                "product": None,
            },
        )
    for row in out.values():
        row["for"] = claims.get(row["port"])
    return [out[p] for p in sorted(out)]
