"""Who is on a port now: the one answer a board's records are kept and read by.

A port's name is the socket's turn in a queue, not the board (``devices``: a record
counts only for the board the port list finds on its port). What is kept of a board
is kept under the board's own key and read for the board on the port now, so it
follows the board from port to port and never reaches another board. A bed reading
is the first record kept this way (docs/plans/machine-identity-2026-11-07.md).

``on_port(port)`` is the board a port holds: its key, the kind of machine it drives
and its firmware, from the record ``FirmwareState.cached_device`` has read against
the port list; a board nothing has identified is there with its key and no kind.
None when the port holds nothing and no record says what was last there.

A board's key is its MAC, else its USB bridge's serial number -- the identity a pin
stores -- else, for a bridge with no serial number (the router's CH340), its maker's
and product's ids. Those follow the board from port to port, and are the same for
two bridges of one make: while two such are on the machine, the key is shared, and
nothing kept under it is either's.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import devices


@dataclass(frozen=True)
class Occupant:
    port: str
    key: Optional[str]
    # "printer" or "router" (jobs.py's machine kinds); None: not identified as either.
    kind: Optional[str]
    firmware: Optional[str]  # the name its firmware gave, when it was identified
    shared: bool = False  # another board on the machine now has the same key

    def owns(self, key: Optional[str]) -> bool:
        """Whether what is kept under ``key`` is this board's."""
        if not key or not self.key or self.shared:
            return False
        return key.lower() == self.key.lower()


def key_of(board) -> Optional[str]:
    """A board's own key, from its record (``DeviceInfo``) or the port list's word
    (``BoardInfo``): its MAC, its bridge's serial number, or ``usb:vid:pid``."""
    mac = (getattr(board, "mac", None) or "").strip()
    if mac:
        return mac
    serial_number = (board.serial_number or "").strip()
    if serial_number:
        return serial_number
    vid, pid = devices._usb_id(board.vid), devices._usb_id(board.pid)
    if isinstance(vid, int) and isinstance(pid, int):
        return f"usb:{vid:04x}:{pid:04x}"
    return None


def on_port(port: str, state: Optional[devices.FirmwareState] = None) -> Optional[Occupant]:
    """The board on ``port`` now, or None when the port holds nothing known."""
    state = state or devices.get_state()
    record = state.cached_device(port)
    board = record or devices.board_on(port)
    if board is None:
        return None
    key = key_of(board)
    shared = (
        bool(key)
        and key.startswith("usb:")
        and any(
            other != port and key_of(seen) == key for other, seen in devices.ports_now().items()
        )
    )
    printer = record.printer if record is not None else None
    return Occupant(
        port=port,
        key=key,
        kind=devices.machine_kind(record),
        firmware=printer.firmware_name if printer is not None else None,
        shared=shared,
    )
