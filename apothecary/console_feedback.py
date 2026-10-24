"""Live levels from a lighting console, into one state the viewer reads.

``ConsoleState`` takes DMX (``apply_universe``, from an E1.31 packet decoded by
``parse_sacn``) and console levels by channel (``set_levels``: the simulator, a
PUT, later an OSC adapter). ``SacnReceiver`` listens for a console's sACN
(E1.31) and ``OscReceiver`` for its OSC status messages (Eos sends UDP to an address
set in its show-control setup), both on the local network, through
``stays_local.console_listener``: the one socket the stays-local guard lets bind
beyond loopback, receive only. Asking a console for anything (OSC subscribe) would
have to send, which the guard refuses; it is not built.
"""

from __future__ import annotations

import colorsys
import math
import socket
import struct
import threading
import time
from typing import Dict, Iterable, Mapping, Optional, Tuple

from .lighting import LightingRig, decode
from .stays_local import OSC_PORT, SACN_PORT, console_listener

ACN_ID = b"ASC-E1.17\x00\x00\x00"
DMX_HEADER = 126  # ACN root + framing + DMP layers, up to and including the start code
_E131_DATA = 2
_DMP_SET_PROPERTY = 2
_OPT_STREAM_TERMINATED = 0x40


def parse_sacn(packet: bytes) -> Optional[Tuple[int, bytes]]:
    """``(universe, slots)`` from one E1.31 DMX packet; ``None`` for anything else."""
    if len(packet) < DMX_HEADER or packet[4:16] != ACN_ID:
        return None
    if int.from_bytes(packet[40:44], "big") != _E131_DATA or packet[117] != _DMP_SET_PROPERTY:
        return None
    if packet[125] != 0 or packet[112] & _OPT_STREAM_TERMINATED:
        return None  # not DMX, or the source is shutting the stream down
    count = int.from_bytes(packet[123:125], "big") - 1  # property count includes the start code
    if not 0 <= count <= 512 or len(packet) < DMX_HEADER + count:
        return None
    universe = int.from_bytes(packet[113:115], "big")
    return universe, packet[DMX_HEADER : DMX_HEADER + count]


def _osc_string(data: bytes, i: int) -> Tuple[str, int]:
    end = data.index(b"\0", i)
    return data[i:end].decode("utf-8", "replace"), i + ((end - i + 4) // 4) * 4


def parse_osc(packet: bytes) -> list:
    """The ``(address, args)`` messages in an OSC packet, a bundle's flattened; ``[]`` if it is not OSC.

    Arguments of type i, f, s, T, F, N; an argument of another type ends the list.
    """
    try:
        if packet.startswith(b"#bundle\0"):
            messages, i = [], 16
            while i + 4 <= len(packet):
                (size,) = struct.unpack_from("!i", packet, i)
                messages += parse_osc(packet[i + 4 : i + 4 + size])
                i += 4 + size
            return messages
        if not packet.startswith(b"/"):
            return []
        address, i = _osc_string(packet, 0)
        tags = ","
        if i < len(packet):
            tags, i = _osc_string(packet, i)
        args: list = []
        for tag in tags[1:]:
            if tag in "iI":
                args.append(struct.unpack_from("!i", packet, i)[0])
                i += 4
            elif tag == "f":
                args.append(struct.unpack_from("!f", packet, i)[0])
                i += 4
            elif tag == "s":
                text, i = _osc_string(packet, i)
                args.append(text)
            elif tag in "TFN":
                args.append({"T": True, "F": False, "N": None}[tag])
            else:
                break
        return [(address, args)]
    except (ValueError, struct.error, RecursionError):
        return []


MAX_STATUS = 64  # distinct addresses kept; a console sends a few dozen kinds of message


class ConsoleState:
    """The latest level per channel and parameter, for one rig. Thread-safe."""

    def __init__(self, rig: LightingRig):
        self.rig = rig
        self._known = {p.channel for p in rig.patches}
        self._lock = threading.Lock()
        self._levels: Dict[int, Dict[str, float]] = {}
        self._status: Dict[str, list] = {}
        self._seq = 0
        self._last: Optional[float] = None

    def apply_osc(self, messages) -> None:
        """Keep the latest arguments of each ``/eos/out/...`` message: the console's own status."""
        with self._lock:
            for address, args in messages:
                if address.startswith("/eos/out/") and (address in self._status or len(self._status) < MAX_STATUS):
                    self._status[address] = args
                    self._seq += 1
                    self._last = time.monotonic()

    def apply_universe(self, universe: int, slots: bytes) -> None:
        self._merge(decode(self.rig, {universe: slots}))

    def set_levels(self, updates: Mapping[int, Mapping[str, float]]) -> None:
        """Set levels by channel number. Raises ``KeyError`` for an unknown channel, ``ValueError`` for a level outside 0-1."""
        for channel, params in updates.items():
            if channel not in self._known:
                raise KeyError(channel)
            for param, value in params.items():
                if not 0.0 <= value <= 1.0:
                    raise ValueError(f"{channel}.{param} = {value} is outside 0-1")
        self._merge(updates)

    def _merge(self, updates: Mapping[int, Mapping[str, float]]) -> None:
        with self._lock:
            for channel, params in updates.items():
                self._levels.setdefault(channel, {}).update(params)
            self._seq += 1
            self._last = time.monotonic()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "seq": self._seq,
                "age": None if self._last is None else time.monotonic() - self._last,
                "channels": {ch: dict(params) for ch, params in self._levels.items()},
                "status": {address: list(args) for address, args in self._status.items()},
            }


class _Receiver:
    """A thread that reads one console UDP port and hands each packet to ``handle``."""

    port = 0

    def __init__(self, state: ConsoleState):
        self.state = state
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def _join(self, sock: socket.socket) -> None:
        """Hook: what a receiver does to the socket before it reads."""

    def handle(self, packet: bytes) -> None:
        raise NotImplementedError

    def start(self) -> None:
        sock = console_listener(self.port)
        sock.settimeout(0.25)
        self._join(sock)
        self._sock = sock
        self._thread = threading.Thread(target=self._run, name=type(self).__name__, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._sock:
            self._sock.close()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                packet, _ = self._sock.recvfrom(8192)
            except socket.timeout:
                continue
            except OSError:
                return
            self.handle(packet)


class SacnReceiver(_Receiver):
    """Feeds a ``ConsoleState`` from the sACN universes a console sends.

    One socket for all universes: it joins each universe's multicast group
    (239.255.hi.lo), so a console sending multicast reaches it, and a console sending
    unicast to this machine reaches it as well. A universe not in ``universes`` is
    ignored. ``failed`` lists universes whose group could not be joined (no multicast
    route); unicast still arrives for them.
    """

    port = SACN_PORT

    def __init__(self, state: ConsoleState, universes: Iterable[int]):
        super().__init__(state)
        self.universes = frozenset(universes)
        self.failed: list = []

    def _join(self, sock: socket.socket) -> None:
        for universe in sorted(self.universes):
            group = socket.inet_aton(f"239.255.{universe >> 8}.{universe & 0xFF}")
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, group + struct.pack("!I", 0))
            except OSError:
                self.failed.append(universe)

    def handle(self, packet: bytes) -> None:
        parsed = parse_sacn(packet)
        if parsed and parsed[0] in self.universes:
            self.state.apply_universe(*parsed)


class OscReceiver(_Receiver):
    """Feeds a ``ConsoleState``'s status from the OSC an Eos console sends (UDP, to this machine)."""

    port = OSC_PORT

    def handle(self, packet: bytes) -> None:
        self.state.apply_osc(parse_osc(packet))


def simulate_levels(rig: LightingRig, t: float) -> Dict[int, Dict[str, float]]:
    """Levels for every parameter the rig's fixtures have, at time ``t`` seconds.

    A sweep for demoing without a console: intensity pulses, colour cycles, and
    moving heads pan and tilt. Each fixture is offset so the room does not move in step.
    """
    out: Dict[int, Dict[str, float]] = {}
    for p in rig.patches:
        params = rig.types[p.fixture_type].params if p.fixture_type in rig.types else []
        phase = p.channel * 0.37
        levels: Dict[str, float] = {}
        if "Intens" in params:
            levels["Intens"] = 0.5 + 0.5 * math.sin(t + phase)
        if any(c in params for c in ("Red", "Green", "Blue")):
            rgb = colorsys.hsv_to_rgb((t / 8 + p.channel / 20) % 1, 1, 1)
            levels.update(zip(("Red", "Green", "Blue"), rgb, strict=True))
        if "Pan" in params:
            levels["Pan"] = 0.5 + 0.5 * math.sin(t / 3 + phase)
        if "Tilt" in params:
            levels["Tilt"] = 0.5 + 0.5 * math.cos(t / 4 + phase)
        if levels:
            out[p.channel] = levels
    return out
