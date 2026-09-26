"""G-code seam: identify and monitor a 3D-printer controller over serial.

The other half of this package talks to boards Apothecary *programs*
(arduino-cli, esptool). This module talks to boards that already run a
G-code firmware -- Marlin on a Creality mainboard, and by the same protocol
RepRapFirmware, Klipper, Prusa, Smoothie -- to answer what the viewer's
printer nodes need: what is this, is it printing, how hot is it, where is
the head. The wire protocol is the one every host (OctoPrint, Pronterface,
Cura's USB printing) speaks: a line of G-code out, response lines back,
``ok`` to close the exchange. Multiple independent implementations on both
ends, so it passes the replaceability test; the parsers below are written
to Marlin's documented output and note where others differ.

Two things distinguish this from ``devices.SerialStreams``:

* **The link is held open, and reset is explicit.** Creality boards wire
  DTR to reset, like every Arduino. The kernel asserts DTR on open, so
  whether an open reboots the board depends on whether the *previous*
  holder dropped DTR on close (most programs do; this module does not) --
  a running print dies or survives by that accident. So a port is opened
  once and kept by ``PrinterLinks`` until released, polls reuse it, DTR is
  left asserted on close, and the board is only ever rebooted on purpose
  (``Transport.pulse_reset``, behind ``reset=True``). Anything else that
  opens the port (``arduino-cli monitor``, an upload) may reset it, so one
  holder per port is the rule and the API enforces it.
* **It is request/response.** A poll sends ``M105``/``M114``/``M27`` and
  reads until ``ok``; nothing streams unless the firmware autoreports
  (``M155``), and those lines are simply carried in the same reads.

The byte transport is an engine slot (``Transport``), chosen by
``serial_engine()``: **pyserial** when importable (any baud, every platform)
else the stdlib's **termios** (POSIX, standard baud table only -- enough
for a 115200 board with nothing installed). ``APOTHECARY_SERIAL_ENGINE``
pins one, and ``simulated`` selects an in-process pretend Marlin for demos
and browser tests with no hardware. Everything above the slot is
engine-agnostic.
"""

from __future__ import annotations

import os
import re
import select
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Protocol, Tuple

from .models import Heater, PrinterInfo, PrinterStatus
from .toolchains import ToolchainError

# --- parsers: Marlin's documented replies -------------------------------------

# FIRMWARE_NAME:Marlin TH3D UFW 2.94a (Jan 17 2025 11:35:34) SOURCE_CODE_URL:... MACHINE_TYPE:...
# Values run up to the next KEY: -- keys are upper-case identifiers; values may hold spaces
# and colons.
M115_KEY_RE = re.compile(r"([A-Z_]+):")
CAP_RE = re.compile(r"^Cap:([A-Z_0-9]+):([01])$")
# M105: ok T:22.30 /0.00 B:23.59 /0.00 @:0 B@:0     (T0:.. T1:.. with several hotends)
HEATER_RE = re.compile(r"(T\d*|B|C):\s*(-?\d+(?:\.\d+)?)\s*/\s*(-?\d+(?:\.\d+)?)")
POWER_RE = re.compile(r"(B@|@\d*):\s*(-?\d+)")
# M114: X:0.00 Y:0.00 Z:0.00 E:0.00 Count X:0 Y:0 Z:0
M114_RE = re.compile(r"^X:(-?\d+\.?\d*)\s+Y:(-?\d+\.?\d*)\s+Z:(-?\d+\.?\d*)\s+E:(-?\d+\.?\d*)")
# M119: x_min: open / y_min: TRIGGERED / filament: TRIGGERED
ENDSTOP_RE = re.compile(r"^([a-z]\w*):\s+(open|TRIGGERED)$")
# M27: SD printing byte 1234/56789   |   Not SD printing
M27_RE = re.compile(r"SD printing byte (\d+)/(\d+)")
# M31: echo:Print time: 1h 2m 3s
M31_RE = re.compile(r"Print time:\s*(.+)$")
DURATION_RE = re.compile(r"(\d+)\s*([dhms])")


def parse_m115(lines: List[str]) -> dict:
    """The ``KEY:value`` fields plus ``capabilities`` from Marlin's ``Cap:`` lines."""
    fields: dict = {}
    caps: Dict[str, bool] = {}
    for line in lines:
        line = line.strip()
        m = CAP_RE.match(line)
        if m:
            caps[m.group(1)] = m.group(2) == "1"
            continue
        if not line.startswith("FIRMWARE_NAME:"):
            continue
        keys = list(M115_KEY_RE.finditer(line))
        for i, k in enumerate(keys):
            end = keys[i + 1].start() if i + 1 < len(keys) else len(line)
            fields[k.group(1).lower()] = line[k.end() : end].strip()
    if caps:
        fields["capabilities"] = caps
    return fields


def parse_m105(line: str) -> dict:
    """``{"hotends": [Heater...], "bed": Heater|None}`` from a temperature line."""
    hotends: Dict[int, Heater] = {}
    bed = None
    powers = {m.group(1): int(m.group(2)) for m in POWER_RE.finditer(line)}
    for m in HEATER_RE.finditer(line):
        key, actual, target = m.group(1), float(m.group(2)), float(m.group(3))
        if key == "B":
            bed = Heater(actual=actual, target=target, power=powers.get("B@"))
        elif key.startswith("T"):
            idx = int(key[1:] or 0)
            hotends[idx] = Heater(
                actual=actual, target=target, power=powers.get(f"@{key[1:]}", powers.get("@"))
            )
    return {"hotends": [hotends[i] for i in sorted(hotends)], "bed": bed}


def is_temperature_line(line: str) -> bool:
    return bool(HEATER_RE.search(line))


def parse_m114(lines: List[str]) -> Optional[dict]:
    for line in lines:
        m = M114_RE.match(line.strip())
        if m:
            x, y, z, e = (float(v) for v in m.groups())
            return {"x": x, "y": y, "z": z, "e": e}
    return None


def parse_m119(lines: List[str]) -> dict:
    return {m.group(1): m.group(2) for m in (ENDSTOP_RE.match(ln.strip()) for ln in lines) if m}


def parse_m27(lines: List[str]) -> dict:
    for line in lines:
        m = M27_RE.search(line)
        if m:
            done, total = int(m.group(1)), int(m.group(2))
            return {"sd_printing": True, "sd_progress": (done / total) if total else None}
    return {"sd_printing": False, "sd_progress": None}


def parse_duration(text: str) -> int:
    unit = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    return sum(int(n) * unit[u] for n, u in DURATION_RE.findall(text))


def parse_m31(lines: List[str]) -> Optional[int]:
    for line in lines:
        m = M31_RE.search(line)
        if m:
            return parse_duration(m.group(1))
    return None


def printer_info_from(lines: List[str], baud: int, boot_lines: List[str] = ()) -> PrinterInfo:
    fields = parse_m115(lines)
    if "firmware_name" not in fields:
        raise ToolchainError("no FIRMWARE_NAME in the M115 reply -- not a G-code firmware?")
    try:
        extruders = int(fields.get("extruder_count", "1"))
    except ValueError:
        extruders = 1
    return PrinterInfo(
        firmware_name=fields["firmware_name"],
        machine_type=fields.get("machine_type"),
        protocol_version=fields.get("protocol_version"),
        source_code_url=fields.get("source_code_url"),
        extruder_count=extruders,
        uuid=fields.get("uuid"),
        capabilities=fields.get("capabilities", {}),
        baud=baud,
        boot_lines=list(boot_lines)[-40:],
        identified_at=datetime.now(timezone.utc),
    )


# --- transport ------------------------------------------------------------------


class Transport(Protocol):
    def write(self, data: bytes) -> None: ...

    def read(self, timeout: float) -> bytes:
        """Whatever is pending within ``timeout`` seconds; ``b""`` on nothing."""
        ...

    def pulse_reset(self) -> None:
        """Drop DTR for a moment: reboots a board whose reset line hangs off it."""
        ...

    def close(self) -> None: ...


RESET_PULSE_S = 0.05


class TermiosTransport:
    """A raw 8N1 serial port via the stdlib; POSIX only."""

    def __init__(self, port: str, baud: int):
        import termios

        flag = getattr(termios, f"B{baud}", None)
        if flag is None:
            raise ToolchainError(
                f"{baud} baud is not in the standard termios table; "
                "115200 is Marlin's usual rate (250000 needs pyserial)"
            )
        try:
            self.fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        except OSError as exc:
            raise ToolchainError(f"cannot open {port}: {exc.strerror}") from exc
        try:
            attr = termios.tcgetattr(self.fd)
            attr[0] = 0  # iflag: no CR/NL mangling, no flow control
            attr[1] = 0  # oflag: raw
            attr[2] = (
                termios.CS8 | termios.CREAD | termios.CLOCAL
            )  # no HUPCL: DTR stays up on close
            attr[3] = 0  # lflag: no echo, no canonical mode
            attr[4] = attr[5] = flag
            termios.tcsetattr(self.fd, termios.TCSANOW, attr)
            termios.tcflush(self.fd, termios.TCIOFLUSH)
        except termios.error as exc:
            os.close(self.fd)
            raise ToolchainError(f"{port} is not a serial port: {exc}") from exc

    def write(self, data: bytes) -> None:
        while data:
            _, w, _ = select.select([], [self.fd], [], 2.0)
            if not w:
                raise ToolchainError("serial write timed out")
            try:
                n = os.write(self.fd, data)
            except OSError as exc:
                raise ToolchainError(f"serial write failed: {exc}") from exc
            data = data[n:]

    def read(self, timeout: float) -> bytes:
        try:
            r, _, _ = select.select([self.fd], [], [], timeout)
            if not r:
                return b""
            return os.read(self.fd, 4096)
        except BlockingIOError:
            return b""
        except OSError as exc:
            raise ToolchainError(f"serial read failed: {exc}") from exc

    def pulse_reset(self) -> None:
        import fcntl
        import struct
        import termios

        dtr = struct.pack("I", termios.TIOCM_DTR)
        fcntl.ioctl(self.fd, termios.TIOCMBIC, dtr)
        time.sleep(RESET_PULSE_S)
        fcntl.ioctl(self.fd, termios.TIOCMBIS, dtr)

    def close(self) -> None:
        try:
            os.close(self.fd)
        except OSError:
            pass


def keep_dtr_on_close(fd: Optional[int]) -> bool:
    """Clear HUPCL on an open tty so closing it leaves DTR asserted.

    The kernel's default is to drop DTR on the last close ("hang up"), and
    a Creality board resets on the next assertion -- so without this, every
    program that closes the port hands the next one a reboot. True when the
    flag was cleared; False on a port that is not a tty (``loop://``) or on
    a platform without termios, where there is nothing to clear.
    """
    if fd is None:
        return False
    try:
        import termios
    except ImportError:  # Windows: pyserial's own close leaves DTR alone
        return False
    try:
        attr = termios.tcgetattr(fd)
        attr[2] &= ~termios.HUPCL
        termios.tcsetattr(fd, termios.TCSANOW, attr)
        return True
    except (OSError, termios.error):
        return False


class PySerialTransport:
    """The pyserial engine: any baud (250000 included), Linux/macOS/Windows.

    ``serial_for_url`` so tests can hand it ``loop://``; a device path is
    passed through unchanged.
    """

    def __init__(self, port: str, baud: int):
        import serial

        try:
            self._s = serial.serial_for_url(port, baudrate=baud, timeout=0.5, write_timeout=2.0)
            self._s.reset_input_buffer()
        except (serial.SerialException, OSError, ValueError) as exc:
            raise ToolchainError(f"cannot open {port}: {exc}") from exc
        keep_dtr_on_close(getattr(self._s, "fd", None))

    def write(self, data: bytes) -> None:
        import serial

        try:
            self._s.write(data)
        except serial.SerialTimeoutException as exc:
            raise ToolchainError("serial write timed out") from exc
        except (serial.SerialException, OSError) as exc:
            raise ToolchainError(f"{self._s.port}: {exc}") from exc

    def read(self, timeout: float) -> bytes:
        import serial

        try:
            self._s.timeout = timeout
            first = self._s.read(1)
            if not first:
                return b""
            return first + self._s.read(self._s.in_waiting)
        except (serial.SerialException, OSError) as exc:
            # Unplugged, or another process is reading the same port.
            raise ToolchainError(f"{self._s.port}: {exc}") from exc

    def pulse_reset(self) -> None:
        import serial

        try:
            self._s.dtr = False
            time.sleep(RESET_PULSE_S)
            self._s.dtr = True
        except (serial.SerialException, OSError) as exc:
            raise ToolchainError(f"{self._s.port}: {exc}") from exc

    def close(self) -> None:
        try:
            self._s.close()
        except Exception:  # noqa: BLE001 -- a vanished USB device raises whatever the OS likes
            pass


class SimulatedPrinter:
    """A pretend Marlin behind the transport slot: no port, no hardware.

    Answers the query codes this module sends with plausible, slowly
    moving values. ``APOTHECARY_SIMULATED_PRINTER=printing`` starts it
    mid-way through an SD print that advances about 1 %/s and starts over
    at the end (so a viewer sees ``printing`` and a progress figure
    straight away, however long it looks); the default is a cold, idle
    machine. Any other command gets ``ok``.
    """

    FIRMWARE = "Marlin Apothecary Simulator 1.0 (simulated)"

    def __init__(self, port: str, baud: int):
        import random

        self.port, self.baud = port, baud
        self._rng = random.Random(port)
        self._pending = b""
        self._t0 = time.monotonic()
        self.printing = os.environ.get("APOTHECARY_SIMULATED_PRINTER", "idle").lower() == "printing"
        self.print_len = 60.0  # seconds from 0 to 100 %
        self.paused_at = 0.0
        self.hot_target = 210.0 if self.printing else 0.0
        self.bed_target = 60.0 if self.printing else 0.0
        self.fan = 0
        self.pos = {"X": 0.0, "Y": 0.0, "Z": 0.0}
        self.relative = False
        self.halted = False
        self._heat_t0 = time.monotonic()

    def _progress(self) -> float:
        # A print that goes round: a browser suite that runs longer than one
        # print still finds the machine printing, at whatever percent it is.
        return ((time.monotonic() - self._t0) / self.print_len) % 1.0 if self.printing else 0.0

    def _apply_control(self, cmd: str) -> Optional[List[str]]:
        """Honour the control set so the overlay's effects show up in the next poll."""
        parts = cmd.upper().split()
        code = parts[0]
        args = {p[0]: p[1:] for p in parts[1:] if p}
        if code == "M104":
            self.hot_target = float(args.get("S", 0))
        elif code == "M140":
            self.bed_target = float(args.get("S", 0))
        elif code == "M106":
            self.fan = int(args.get("S", 255))
        elif code == "M107":
            self.fan = 0
        elif code == "G28":
            for axis in "XYZ" if len(parts) == 1 else [a for a in "XYZ" if a in args]:
                self.pos[axis] = 0.0
        elif code == "G91":
            self.relative = True
        elif code == "G90":
            self.relative = False
        elif code in ("G0", "G1"):
            for axis in "XYZ":
                if axis in args:
                    v = float(args[axis])
                    self.pos[axis] = self.pos[axis] + v if self.relative else v
        elif code == "M24":
            self.printing, self._t0 = True, time.monotonic() - self.print_len * self.paused_at
        elif code == "M25":
            self.paused_at, self.printing = self._progress(), False
        elif code == "M524":
            self.printing, self.paused_at = False, 0.0
        elif code == "M112":
            self.halted = True
            return ["Error:Printer halted. kill() called!"]
        elif code in ("M109", "M190"):
            # Heat and wait: a real board says busy until it is there; here it is there.
            target = float(args.get("S", args.get("R", 0)))
            if code == "M109":
                self.hot_target = target
            else:
                self.bed_target = target
            return ["echo:busy: processing", "ok"]
        elif code == "G92":
            for axis in "XYZ":
                if axis in args:
                    self.pos[axis] = float(args[axis])
        elif code == "G4":
            # A dwell takes the time it says (capped), so a streamed file takes
            # time to stream and a pause has something to interrupt.
            ms = float(args.get("P", 0)) or 1000 * float(args.get("S", 0))
            time.sleep(min(2.0, ms / 1000))
        elif code == "G29":
            # A probe takes a while; the busy lines are what Marlin prints while it does.
            return ["echo:busy: processing", "echo:busy: processing", *self._grid_lines(), "ok"]
        elif code == "G30":
            x = float(args.get("X", self.pos["X"]))
            y = float(args.get("Y", self.pos["Y"]))
            return [
                f"Bed X: {x:.2f} Y: {y:.2f} Z: {self._bed_z(x / 220 * 4, y / 220 * 4):.2f}",
                "ok",
            ]
        else:
            return None
        return ["ok"]

    def _bed_z(self, i: float, j: float) -> float:
        """A bed that is slightly tilted and a little bowed, the same every run for a port."""
        tilt = 0.12 * (i - 2) - 0.08 * (j - 2)
        bow = -0.05 * ((i - 2) ** 2 + (j - 2) ** 2) / 4
        return tilt + bow + self._rng.uniform(-0.01, 0.01)

    def _grid_lines(self) -> List[str]:
        lines = ["Bilinear Leveling Grid:", "      0      1      2      3      4"]
        for j in range(5):
            cells = " ".join(f"{self._bed_z(i, j):+.3f}" for i in range(5))
            lines.append(f" {j} {cells}")
        return lines

    def _reply(self, cmd: str) -> List[str]:
        code = cmd.split()[0].upper() if cmd.split() else ""
        wobble = self._rng.uniform(-0.3, 0.3)
        if self.halted and code != "M115":
            return ["Error:Printer halted. kill() called!"]
        controlled = self._apply_control(cmd)
        if controlled is not None:
            return controlled
        if code == "M420" and cmd.upper().split()[-1] == "V":
            return [
                *self._grid_lines(),
                f"echo:Bed Leveling {'ON' if self.printing else 'OFF'}",
                "ok",
            ]
        if code == "M851":
            return ["echo:  M851 X-44.00 Y-10.00 Z-3.15 ; (mm)", "ok"]
        if code == "M115":
            return [
                f"FIRMWARE_NAME:{self.FIRMWARE} SOURCE_CODE_URL:apothecary "
                "PROTOCOL_VERSION:1.0 MACHINE_TYPE:Simulated Ender EXTRUDER_COUNT:1 "
                "UUID:00000000-0000-0000-0000-000000000000",
                "Cap:AUTOREPORT_TEMP:1",
                "ok",
            ]
        if code == "M105":
            # A heater sits within a degree of its target when one is set (a
            # simulator, not a thermal model), at room temperature otherwise.
            hot = self.hot_target if self.hot_target > 0 else 23.0
            bed = self.bed_target if self.bed_target > 0 else 24.0
            hp = 70 if self.hot_target > 0 else 0
            bp = 20 if self.bed_target > 0 else 0
            return [
                f"ok T:{hot + wobble:.2f} /{self.hot_target:.2f} "
                f"B:{bed + wobble:.2f} /{self.bed_target:.2f} @:{hp} B@:{bp}"
            ]
        if code == "M114":
            if self.printing:
                p = self._progress()
                return [
                    f"X:{110 + 60 * p:.2f} Y:95.00 Z:{0.2 + 40 * p:.2f} E:{500 * p:.2f} "
                    "Count X:0 Y:0 Z:0",
                    "ok",
                ]
            x, y, z = self.pos["X"], self.pos["Y"], self.pos["Z"]
            return [f"X:{x:.2f} Y:{y:.2f} Z:{z:.2f} E:0.00 Count X:0 Y:0 Z:0", "ok"]
        if code == "M119":
            return [
                "Reporting endstop status",
                "x_min: open",
                "y_min: TRIGGERED",
                "z_min: open",
                "filament: TRIGGERED",
                "ok",
            ]
        if code == "M27":
            if self.printing:
                return [f"SD printing byte {int(358856 * self._progress())}/358856", "ok"]
            return ["Not SD printing", "ok"]
        if code == "M31":
            secs = int(time.monotonic() - self._t0)
            return [f"echo:Print time: {secs // 60}m {secs % 60}s", "ok"]
        return ["ok"]

    def write(self, data: bytes) -> None:
        for cmd in data.decode("utf-8", "replace").split("\n"):
            if cmd.strip():
                self._pending += "".join(ln + "\n" for ln in self._reply(cmd.strip())).encode()

    def read(self, timeout: float) -> bytes:
        if not self._pending:
            time.sleep(min(timeout, 0.02))
            return b""
        out, self._pending = self._pending, b""
        return out

    def pulse_reset(self) -> None:
        self._t0 = time.monotonic()
        self.halted = False  # a reset is how a halted board comes back
        self._pending += b"start\n External Reset\n" + self.FIRMWARE.encode() + b"\n"

    def close(self) -> None:
        pass


TransportFactory = Callable[[str, int], Transport]
ENGINES: Dict[str, TransportFactory] = {
    "pyserial": PySerialTransport,
    "termios": TermiosTransport,
    "simulated": SimulatedPrinter,
}


def pyserial_available() -> bool:
    try:
        import serial  # noqa: F401
    except ImportError:
        return False
    return True


def serial_engine() -> str:
    """``APOTHECARY_SERIAL_ENGINE`` if set; else pyserial when importable, else termios."""
    wanted = os.environ.get("APOTHECARY_SERIAL_ENGINE", "").strip().lower()
    if wanted:
        if wanted not in ENGINES:
            raise ToolchainError(
                f"APOTHECARY_SERIAL_ENGINE={wanted!r}; known engines: {', '.join(ENGINES)}"
            )
        return wanted
    return "pyserial" if pyserial_available() else "termios"


def open_transport(port: str, baud: int) -> Transport:
    return ENGINES[serial_engine()](port, baud)


# --- comms log: everything said on a port, for the monitor page ------------------------


class CommsLog:
    """A per-port ring of what went over the wire, kept by ``PrinterLinks``.

    Survives a reconnect (the registry owns it, not the link) and a page
    reload (it lives in the server), so the monitor shows polls made by
    other clients too. Entries carry a monotonically increasing index so a
    reader asks for ``since=N`` and gets only what is new.
    """

    def __init__(self, port: str, capacity: int = 4000):
        self.port = port
        self.capacity = capacity
        self._entries: List[dict] = []
        self._base = 0  # index of _entries[0]
        self._lock = threading.Lock()

    def add(self, kind: str, text: str, origin: str = "") -> None:
        with self._lock:
            self._entries.append(
                {
                    "i": self._base + len(self._entries),
                    "t": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                    "kind": kind,  # tx | rx | boot | sys
                    "origin": origin,  # poll | query | identify -- who sent the command
                    "text": text,
                }
            )
            if len(self._entries) > self.capacity:
                drop = self.capacity // 4
                del self._entries[:drop]
                self._base += drop

    def since(self, index: int, limit: int = 1000) -> dict:
        with self._lock:
            start = max(0, index - self._base)
            rows = self._entries[start : start + limit]
            return {"entries": rows, "next": self._base + start + len(rows)}

    @property
    def next_index(self) -> int:
        with self._lock:
            return self._base + len(self._entries)


# --- link: one open port, request/response with a lock ------------------------------

OK_RE = re.compile(r"^ok\b")
ERROR_RE = re.compile(r"^(Error:|!!)")
BUSY_RE = re.compile(r"^echo:busy:")
RESEND_RE = re.compile(r"^Resend:")


class GcodeLink:
    """A held-open serial port speaking line-per-command G-code.

    ``command()`` is serialised by a lock so a poll and a user command never
    interleave their replies. Lines that arrive outside any exchange (an
    autoreport, a boot banner) are kept in ``unsolicited`` for the caller.
    """

    def __init__(self, port: str, baud: int, transport: Transport, log: Optional[CommsLog] = None):
        self.port = port
        self.baud = baud
        self._t = transport
        self._lock = threading.RLock()
        self._buf = b""
        self.unsolicited: List[str] = []
        self.opened_at = datetime.now(timezone.utc)
        self.log = log or CommsLog(port)
        self.engine = type(transport).__name__
        self.log.add("sys", f"opened {port} @ {baud} via {self.engine}")

    def _read_line(self, timeout: float) -> Optional[str]:
        end = time.monotonic() + timeout
        while b"\n" not in self._buf:
            left = end - time.monotonic()
            if left <= 0:
                return None
            chunk = self._t.read(min(left, 0.5))
            if not chunk:
                continue
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return line.decode("utf-8", "replace").rstrip("\r")

    def drain(self, quiet: float = 0.3, limit: float = 5.0) -> List[str]:
        """Read until the board has been silent for ``quiet`` seconds (or ``limit``)."""
        out: List[str] = []
        end = time.monotonic() + limit
        with self._lock:
            while time.monotonic() < end:
                line = self._read_line(quiet)
                if line is None:
                    break
                out.append(line)
        return out

    def settle(self, first: float = 1.5, quiet: float = 0.6, limit: float = 6.0) -> List[str]:
        """Collect whatever the board volunteers after open, until it goes quiet.

        If the open happened to reset the board (the previous holder dropped
        DTR), its banner shows up within ``first`` seconds and is kept in
        ``unsolicited``; if nothing arrives, the board is simply up and we
        carry on -- ``M115`` does not need a banner.
        """
        lines: List[str] = []
        end = time.monotonic() + limit
        with self._lock:
            while time.monotonic() < end:
                line = self._read_line(first if not lines else quiet)
                if line is None:
                    break
                lines.append(line)
                self.log.add("boot", line)
        self.unsolicited.extend(lines)
        return lines

    def reset(self, limit: float = 6.0) -> List[str]:
        """Reboot the board on purpose and return its boot banner."""
        with self._lock:
            self._buf = b""
            self.log.add("sys", "reset: DTR pulse")
            self._t.pulse_reset()
            return self.settle(first=3.0, quiet=0.6, limit=limit)

    def command(
        self,
        cmd: str,
        timeout: float = 5.0,
        origin: str = "poll",
        wait: Optional[float] = None,
        quiet: bool = False,
    ) -> List[str]:
        """Send one line, return every reply line up to and including ``ok``.

        ``origin`` tags the exchange in the comms log so a reader can hide
        the routine polls and keep what a person asked for. ``wait`` bounds
        how long to queue for the link behind another exchange (a print
        streams one line after another); ``LinkBusy`` when it runs out.
        ``quiet`` keeps the exchange out of the log unless the board
        objects: a print is thousands of lines, and the log is for reading.
        """
        cmd = cmd.strip()
        if not cmd or "\n" in cmd:
            raise ValueError("one G-code command per call")
        if not self._lock.acquire(timeout=-1 if wait is None else wait):
            raise LinkBusy(
                f"{self.port}: the link is busy ({self.job['kind'] if self.job else 'an exchange'})"
            )
        try:
            if not quiet:
                self.log.add("tx", cmd, origin)
            self._t.write((cmd + "\n").encode())
            lines: List[str] = []
            end = time.monotonic() + timeout
            while True:
                left = end - time.monotonic()
                if left <= 0:
                    self.log.add("sys", f"timeout: no `ok` for {cmd} within {timeout:.0f}s")
                    raise ToolchainError(
                        f"{self.port}: no `ok` for {cmd} within {timeout:.0f}s "
                        f"({len(lines)} lines received)"
                    )
                line = self._read_line(left)
                if line is None:
                    continue
                lines.append(line)
                objected = ERROR_RE.match(line) or RESEND_RE.match(line)
                if not quiet or objected:
                    if quiet:
                        self.log.add("tx", cmd, origin)  # the line it objected to, for the record
                    self.log.add("rx", line, origin)
                if BUSY_RE.match(line):
                    end = time.monotonic() + timeout  # heating/homing: keep waiting
                elif OK_RE.match(line):
                    return lines
                elif objected:
                    raise ToolchainError(f"{self.port}: {cmd} -> {line}")
        finally:
            self._lock.release()

    def close(self) -> None:
        with self._lock:
            self.log.add("sys", f"closed {self.port}")
            self._t.close()

    # A long exchange (a bed probe takes minutes) is announced here, so a
    # poll can say "busy: probing" instead of queueing behind the lock for
    # as long as the firmware is blocked.
    job: Optional[dict] = None

    def info(self) -> dict:
        return {
            "port": self.port,
            "baud": self.baud,
            "engine": self.engine,
            "opened_at": self.opened_at.isoformat(),
            "log_next": self.log.next_index,
        }


class PrinterLinks:
    """Open links, one per port, released as a group before a task takes a port."""

    def __init__(self, factory: Optional[TransportFactory] = None):
        self._links: Dict[str, GcodeLink] = {}
        self._logs: Dict[str, CommsLog] = {}
        self._lock = threading.RLock()  # open() reaches log_for() while holding it
        self.factory: TransportFactory = factory or open_transport
        self.control = ControlLatch()

    def log_for(self, port: str) -> CommsLog:
        with self._lock:
            if port not in self._logs:
                self._logs[port] = CommsLog(port)
            return self._logs[port]

    def get(self, port: str) -> Optional[GcodeLink]:
        with self._lock:
            return self._links.get(port)

    def open(self, port: str, baud: int) -> GcodeLink:
        """The existing link for ``port`` at that baud, else a fresh one (resets the board)."""
        with self._lock:
            link = self._links.get(port)
            if link is not None and link.baud == baud:
                return link
            if link is not None:
                link.close()
            link = GcodeLink(port, baud, self.factory(port, baud), log=self.log_for(port))
            self._links[port] = link
        link.settle()
        return link

    def close(self, port: str, force: bool = False) -> bool:
        """Drop the link; refused while a print streams over it unless ``force``."""
        with self._lock:
            link = self._links.get(port)
            if link is not None and not force and link.job and link.job.get("kind") == "print":
                raise ToolchainError(f"{port}: a print holds the port -- cancel it first")
            self.control.disarm(port)  # a dropped link never stays armed
            self._links.pop(port, None)
        if link is None:
            return False
        link.close()
        return True

    def stop_all(self) -> None:
        with self._lock:
            links, self._links = list(self._links.values()), {}
        for link in links:
            self.control.disarm(link.port)
            link.close()

    @property
    def open_ports(self) -> List[str]:
        with self._lock:
            return list(self._links)


_LINKS: Optional[PrinterLinks] = None


def get_printer_links() -> PrinterLinks:
    global _LINKS
    if _LINKS is None:
        _LINKS = PrinterLinks()
    return _LINKS


# --- manual queries: report-only codes a user may send by hand ---------------------

# Marlin codes that only *report*: no motion, no heaters, no SD control, no
# EEPROM writes. Each entry is the exact line accepted (parameters included
# where a report form needs them); anything else is refused before it
# reaches the port. Extend here, deliberately, never by relaxing the check.
QUERY_CODES: Dict[str, str] = {
    "M105": "temperatures",
    "M114": "position",
    "M115": "firmware info",
    "M119": "endstop states",
    "M20": "list SD card",
    "M27": "SD print progress",
    "M31": "print time",
    "M78": "print job statistics",
    "M92": "steps per unit",
    "M122": "TMC stepper driver status",
    "M145": "material presets",
    "M201": "max acceleration",
    "M203": "max feedrate",
    "M204": "acceleration",
    "M205": "advanced settings (jerk, min feedrate)",
    "M206": "home offsets",
    "M301": "hotend PID",
    "M304": "bed PID",
    "M420 V": "bed mesh",
    "M503": "all settings",
    "M851": "probe offset",
    "M900": "linear advance",
}


def normalise_query(command: str) -> str:
    """Upper-cased, single-spaced form of ``command``; raises ValueError if it is not a query."""
    cmd = " ".join(command.strip().upper().split())
    if cmd not in QUERY_CODES:
        raise ValueError(f"not a report-only query code: {command!r}")
    return cmd


# --- control: commands that move or heat, only while the port's control latch is armed --

# Each entry: a regex for the whole normalised line and what it does. Values
# are bounded here (a hotend cannot be asked for 400 degC) and the set is
# operator controls only -- no EEPROM writes, no firmware configuration.
# A print streams a whole file past this list (a sliced file is not typed by
# hand); what it may not carry is checked once, before the first line, by
# check_gcode below. Extend deliberately.
HOTEND_MAX_C = 300
BED_MAX_C = 130
JOG_MAX_MM = 300
FEED_MAX = 12000
CONTROL_CODES: List[tuple] = [
    (re.compile(r"^M104 S(\d{1,3})$"), "hotend target"),
    (re.compile(r"^M140 S(\d{1,3})$"), "bed target"),
    (re.compile(r"^M106(?: S(\d{1,3}))?$"), "fan on / speed 0-255"),
    (re.compile(r"^M107$"), "fan off"),
    (re.compile(r"^G28(?: [XYZ](?: [XYZ])*)?$"), "home (all or named axes)"),
    (re.compile(r"^G90$"), "absolute positioning"),
    (re.compile(r"^G91$"), "relative positioning"),
    (re.compile(r"^G[01](?:(?: [XYZ]-?\d{1,3}(?:\.\d{1,2})?){1,3})?(?: F\d{2,5})?$"), "move (jog)"),
    (re.compile(r"^M84$"), "steppers off"),
    (re.compile(r"^M18$"), "steppers off"),
    (re.compile(r"^M23 (?!.*\.\.)([A-Za-z0-9_~./-]{1,64})$"), "select SD file (no ..)"),
    (re.compile(r"^M24$"), "start / resume SD print"),
    (re.compile(r"^M25$"), "pause SD print"),
    (re.compile(r"^M524$"), "abort SD print"),
    (re.compile(r"^M420 S[01]$"), "bed leveling on/off"),
    (re.compile(r"^G29$"), "probe the bed (auto bed leveling)"),
    (
        re.compile(r"^G30(?: X\d{1,3}(?:\.\d{1,2})?)?(?: Y\d{1,3}(?:\.\d{1,2})?)?$"),
        "probe one point",
    ),
    (re.compile(r"^M108$"), "break out of a heat-and-wait"),
    (re.compile(r"^M410$"), "quickstop: abort planned moves"),
]
EMERGENCY_STOP = "M112"  # always accepted, latch or not; halts the board until reset


def normalise_control(command: str) -> str:
    """Upper-cased, single-spaced control line; ValueError if not allowed or out of bounds."""
    cmd = " ".join(command.strip().upper().split())
    if cmd == EMERGENCY_STOP:
        return cmd
    for pattern, _ in CONTROL_CODES:
        m = pattern.match(cmd)
        if not m:
            continue
        if cmd.startswith("M104") and int(m.group(1)) > HOTEND_MAX_C:
            raise ValueError(f"hotend target above {HOTEND_MAX_C} degC: {command!r}")
        if cmd.startswith("M140") and int(m.group(1)) > BED_MAX_C:
            raise ValueError(f"bed target above {BED_MAX_C} degC: {command!r}")
        if cmd.startswith("M106") and m.group(1) and int(m.group(1)) > 255:
            raise ValueError(f"fan speed above 255: {command!r}")
        if cmd[0] == "G" and cmd[1] in "01":
            for axis_val in re.findall(r" [XYZ](-?\d+(?:\.\d+)?)", cmd):
                if abs(float(axis_val)) > JOG_MAX_MM:
                    raise ValueError(f"move beyond {JOG_MAX_MM} mm: {command!r}")
            feed = re.search(r" F(\d+)", cmd)
            if feed and int(feed.group(1)) > FEED_MAX:
                raise ValueError(f"feedrate above {FEED_MAX}: {command!r}")
        return cmd
    raise ValueError(f"not an allowed control code: {command!r}")


# --- bed leveling: reading Marlin's mesh -------------------------------------------------

GRID_HEADER_RE = re.compile(r"^\s*(\d+(?:\s+\d+)+)\s*$")
GRID_ROW_RE = re.compile(r"^\s*(\d+)((?:\s+[-+]?\d+\.\d+)+)\s*$")
G29_POINT_RE = re.compile(r"G29 W I(\d+) J(\d+) Z([-+]?\d+\.\d+)")
PROBE_OFFSET_RE = re.compile(r"M851 X([-+]?\d+\.?\d*) Y([-+]?\d+\.?\d*) Z([-+]?\d+\.?\d*)")
G30_RE = re.compile(r"Bed X:\s*([-+]?\d+\.?\d*)\s*Y:\s*([-+]?\d+\.?\d*)\s*Z:\s*([-+]?\d+\.?\d*)")
LEVELING_STATE_RE = re.compile(r"Bed Leveling (ON|OFF)")


def parse_meshes(lines: List[str]) -> List[List[List[float]]]:
    """Every grid in Marlin's ``M420 V`` / ``G29`` output, in order.

    A grid is a header line of column indices followed by rows that begin
    with a row index: the measured bilinear grid first, then the subdivided
    one when the firmware prints it. Rows are returned top to bottom as
    printed, each a list of floats. ``G29 W I.. J.. Z..`` points (the form
    ``M503`` uses) are gathered into a grid too when no printed grid exists.
    """
    grids: List[List[List[float]]] = []
    current: Optional[List[List[float]]] = None
    for line in lines:
        text = line.strip()
        if GRID_HEADER_RE.match(text):
            current = []
            grids.append(current)
            continue
        m = GRID_ROW_RE.match(text)
        if m and current is not None:
            current.append([float(v) for v in m.group(2).split()])
            continue
        if current is not None and text and not m:
            current = None  # the grid ended
    grids = [g for g in grids if g]
    if grids:
        return grids
    points: Dict[Tuple[int, int], float] = {}
    for line in lines:
        m = G29_POINT_RE.search(line)
        if m:
            points[(int(m.group(2)), int(m.group(1)))] = float(m.group(3))
    if not points:
        return []
    rows = max(j for j, _ in points) + 1
    cols = max(i for _, i in points) + 1
    return [[[points.get((j, i), 0.0) for i in range(cols)] for j in range(rows)]]


def mesh_stats(mesh: List[List[float]]) -> dict:
    """What a person wants to know about a mesh: range, tilt and corners.

    Tilt is a least-squares plane through the points, reported as mm of rise
    across the whole grid in X and in Y; corners are the four corner values
    minus the mean, which is what tramming a bed by its screws changes.
    """
    rows = len(mesh)
    cols = len(mesh[0]) if rows else 0
    flat = [v for row in mesh for v in row]
    if not flat:
        return {"rows": 0, "cols": 0}
    mean = sum(flat) / len(flat)
    lo, hi = min(flat), max(flat)
    # Least squares z = a*x + b*y + c on unit-spaced indices.
    xs = [i for _ in range(rows) for i in range(cols)]
    ys = [j for j in range(rows) for _ in range(cols)]
    n = len(flat)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs) or 1.0
    syy = sum((y - my) ** 2 for y in ys) or 1.0
    a = sum((x - mx) * (z - mean) for x, z in zip(xs, flat, strict=True)) / sxx
    b = sum((y - my) * (z - mean) for y, z in zip(ys, flat, strict=True)) / syy
    return {
        "rows": rows,
        "cols": cols,
        "min": round(lo, 4),
        "max": round(hi, 4),
        "range": round(hi - lo, 4),
        "mean": round(mean, 4),
        "tilt_x": round(a * (cols - 1), 4) if cols > 1 else 0.0,
        "tilt_y": round(b * (rows - 1), 4) if rows > 1 else 0.0,
        "corners": {
            "front_left": round(mesh[0][0] - mean, 4),
            "front_right": round(mesh[0][-1] - mean, 4),
            "back_left": round(mesh[-1][0] - mean, 4),
            "back_right": round(mesh[-1][-1] - mean, 4),
        },
    }


def parse_probe_offset(lines: List[str]) -> Optional[dict]:
    for line in lines:
        m = PROBE_OFFSET_RE.search(line)
        if m:
            return {"x": float(m.group(1)), "y": float(m.group(2)), "z": float(m.group(3))}
    return None


def parse_g30(lines: List[str]) -> Optional[dict]:
    for line in lines:
        m = G30_RE.search(line)
        if m:
            return {"x": float(m.group(1)), "y": float(m.group(2)), "z": float(m.group(3))}
    return None


def parse_leveling_state(lines: List[str]) -> Optional[bool]:
    for line in lines:
        m = LEVELING_STATE_RE.search(line)
        if m:
            return m.group(1) == "ON"
    return None


# --- host printing: what a file may carry, and how long a line may take ----------------

# Codes a print file is refused for, whatever else it says: they write the
# board's settings or take it down, and a slicer never needs them.
PRINT_REFUSED: Dict[str, str] = {
    "M500": "saves settings to EEPROM",
    "M502": "resets settings to the firmware's defaults",
    "M997": "starts a firmware update",
    "M999": "restarts the board after a stop",
    "M112": "kills the board",
    "M0": "stops and waits for a button on the printer",
    "M1": "stops and waits for a button on the printer",
}
TEMP_CODES = {"M104": HOTEND_MAX_C, "M109": HOTEND_MAX_C, "M140": BED_MAX_C, "M190": BED_MAX_C}
COMMENT_RE = re.compile(r";.*$|\([^)]*\)")
TEMP_ARG_RE = re.compile(r"[SR](\d+(?:\.\d+)?)")
# Lines the firmware answers only when it is done: heating, homing, probing, a dwell.
SLOW_CODES = {"M109", "M190", "M191", "G28", "G29", "G4", "M400", "G30"}
PRINT_LINE_TIMEOUT_S = 30.0
PRINT_SLOW_TIMEOUT_S = 900.0


def strip_gcode(line: str) -> str:
    """The command on a line of a file: comments dropped, whitespace squeezed, upper-cased."""
    return " ".join(COMMENT_RE.sub("", line).split()).upper()


def line_timeout(cmd: str) -> float:
    code = cmd.split(" ", 1)[0] if cmd else ""
    return PRINT_SLOW_TIMEOUT_S if code in SLOW_CODES else PRINT_LINE_TIMEOUT_S


def check_gcode(text: str) -> Tuple[int, List[str]]:
    """How many lines a file would send, and every reason it may not be sent.

    A reason names its line. Refused codes and temperatures over the seam's
    caps are the two: the same bounds as a typed control, applied once to
    the whole file rather than line by line as it streams.
    """
    total = 0
    problems: List[str] = []
    for n, raw in enumerate(text.splitlines(), 1):
        cmd = strip_gcode(raw)
        if not cmd:
            continue
        total += 1
        code = cmd.split(" ", 1)[0]
        if code in PRINT_REFUSED:
            problems.append(f"line {n}: {code} {PRINT_REFUSED[code]}")
        elif code in TEMP_CODES:
            m = TEMP_ARG_RE.search(cmd[len(code) :])
            if m and float(m.group(1)) > TEMP_CODES[code]:
                problems.append(
                    f"line {n}: {code} asks for {m.group(1)} degC, above {TEMP_CODES[code]}"
                )
        if len(problems) >= 20:
            problems.append("... and the check stopped here")
            break
    return total, problems


CONTROL_TTL_S = 300.0  # a latch that nobody touches for this long disarms itself


class ControlLatch:
    """Per-port arm state: control commands go through only while armed.

    Arming is an explicit act with a lifetime; every accepted command
    renews it, silence lets it lapse. It exists so the monitor's control
    overlay cannot heat or move a machine from a stray click.
    """

    def __init__(self):
        self._until: Dict[str, float] = {}
        self._lock = threading.Lock()

    def arm(self, port: str, ttl: float = CONTROL_TTL_S) -> float:
        with self._lock:
            self._until[port] = time.time() + ttl
            return self._until[port]

    def disarm(self, port: str) -> None:
        with self._lock:
            self._until.pop(port, None)

    def armed(self, port: str) -> bool:
        with self._lock:
            until = self._until.get(port)
            if until is None:
                return False
            if until <= time.time():
                del self._until[port]
                return False
            return True

    def seconds_left(self, port: str) -> float:
        with self._lock:
            until = self._until.get(port)
            return max(0.0, until - time.time()) if until else 0.0

    def renew(self, port: str, ttl: float = CONTROL_TTL_S) -> None:
        if self.armed(port):
            self.arm(port, ttl)


class LinkBusy(ToolchainError):
    """The link is held by a long exchange and the caller would not wait."""


class ControlNotArmed(ToolchainError):
    """A control command arrived while the port's latch was not armed."""


# --- the things the viewer asks ---------------------------------------------------


def identify_printer(link: GcodeLink, reset: bool = False) -> PrinterInfo:
    """``M115`` over an open link; with ``reset`` the board is rebooted first for its banner.

    Raises ``ToolchainError`` if nothing G-code answers.
    """
    if reset:
        link.reset()
    boot = list(link.unsolicited)
    lines = link.command("M115", timeout=8.0, origin="identify")
    try:
        return printer_info_from(lines, link.baud, boot)
    except ToolchainError:
        # A flaky USB link can garble one reply (a transposed `ko`, a lost
        # line); one more try tells a bad link from a non-printer.
        link.drain(quiet=0.3, limit=1.0)
        lines = link.command("M115", timeout=8.0, origin="identify")
        return printer_info_from(lines, link.baud, boot)


def poll_printer(
    link: GcodeLink, endstops: bool = True, wait: Optional[float] = None
) -> PrinterStatus:
    """Temperatures, position, SD progress and (optionally) endstops in one exchange each.

    ``wait`` bounds each exchange's queueing behind a print's stream (see
    ``GcodeLink.command``); a poll between two streamed lines is how a host
    keeps its temperatures fresh mid-print.
    """
    raw: List[str] = []
    temps = link.command("M105", wait=wait)
    raw += temps
    temp_line = next((ln for ln in temps if is_temperature_line(ln)), "")
    parsed = parse_m105(temp_line)
    pos_lines = link.command("M114", wait=wait)
    raw += pos_lines
    sd_lines = link.command("M27", wait=wait)
    raw += sd_lines
    sd = parse_m27(sd_lines)
    stops: dict = {}
    if endstops:
        stop_lines = link.command("M119", wait=wait)
        raw += stop_lines
        stops = parse_m119(stop_lines)
    print_time = None
    if sd["sd_printing"]:
        time_lines = link.command("M31", wait=wait)
        raw += time_lines
        print_time = parse_m31(time_lines)
    filament = stops.get("filament")
    return PrinterStatus(
        port=link.port,
        polled_at=datetime.now(timezone.utc),
        state="printing" if sd["sd_printing"] else "idle",
        hotends=parsed["hotends"],
        bed=parsed["bed"],
        position=parse_m114(pos_lines),
        endstops={k: v for k, v in stops.items() if k != "filament"},
        filament_present=(filament == "TRIGGERED") if filament else None,
        sd_printing=sd["sd_printing"],
        sd_progress=sd["sd_progress"],
        print_time_s=print_time,
        raw=raw,
    )


def control_printer(link: GcodeLink, command: str, timeout: float = 30.0) -> List[str]:
    """Send one allowlisted control line (homing can take a while; ``busy`` extends the wait)."""
    return link.command(normalise_control(command), timeout=timeout, origin="control")


def query_printer(link: GcodeLink, command: str, timeout: float = 15.0) -> List[str]:
    """Send one allowlisted query and return its reply lines (``M503`` can run long)."""
    return link.command(normalise_query(command), timeout=timeout, origin="query")


def offline_status(port: str, reason: str) -> PrinterStatus:
    return PrinterStatus(
        port=port, polled_at=datetime.now(timezone.utc), state="offline", raw=[reason]
    )
