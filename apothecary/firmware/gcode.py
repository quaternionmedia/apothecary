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

* **The link is held open, and reset is explicit.** A port is opened once,
  exclusively, and kept by ``PrinterLinks`` until released; polls reuse it,
  DTR is left asserted on close, and the board is rebooted only on purpose
  (``Transport.pulse_reset``, behind ``reset=True``). One holder per port:
  the API enforces it inside the server. docs/firmware.md ("Reset is
  deliberate, never incidental", "One holder per port") says why.
* **It is request/response.** A poll sends ``M105``/``M114``/``M27`` and
  reads until ``ok``; nothing streams unless the firmware autoreports
  (``M155``), and those lines are simply carried in the same reads.

The byte transport is an engine slot (``Transport``), chosen by
``serial_engine()``: **pyserial** (any baud, every platform) unless
``APOTHECARY_SERIAL_ENGINE=simulated`` selects an in-process pretend Marlin
for ``serve --simulated`` and browser tests, with no hardware. Everything above the slot is
engine-agnostic.
"""

from __future__ import annotations

import errno
import math
import os
import re
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Protocol, Tuple

from .models import MACHINE_OF, MARLIN, BedReading, Heater, PrinterInfo, PrinterStatus
from .toolchains import PortHeld, ToolchainError

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


def hold_exclusively(fd: Optional[int], hold: bool = True) -> bool:
    """Set (or clear) TIOCEXCL: while set, any other open() of the tty fails with EBUSY.

    pyserial's ``exclusive=True`` is an advisory lock that only programs
    taking the same lock respect; a plain open() -- arduino-cli's monitor, a
    terminal -- does not. False on a port that is not a tty (``loop://``) or
    a platform without the ioctl. Root is not stopped by it.
    """
    if fd is None:
        return False
    try:
        import fcntl
        import termios

        fcntl.ioctl(fd, termios.TIOCEXCL if hold else termios.TIOCNXCL)
        return True
    except (ImportError, AttributeError, OSError):
        return False


class PySerialTransport:
    """The pyserial engine: any baud (250000 included), Linux/macOS/Windows.

    ``serial_for_url`` so tests can hand it ``loop://``; a device path is
    passed through unchanged. The port is held exclusively until ``close``.
    """

    def __init__(self, port: str, baud: int):
        import serial

        try:
            self._s = serial.serial_for_url(
                port, baudrate=baud, timeout=0.5, write_timeout=2.0, exclusive=True
            )
            self._s.reset_input_buffer()
        except (serial.SerialException, OSError, ValueError) as exc:
            # EBUSY: another program set TIOCEXCL; EAGAIN: it holds pyserial's lock.
            if getattr(exc, "errno", None) in (errno.EBUSY, errno.EAGAIN):
                raise PortHeld(
                    f"{port} is held by another program (a serial monitor, a slicer, "
                    "another server): close it there first"
                ) from exc
            raise ToolchainError(f"cannot open {port}: {exc}") from exc
        fd = getattr(self._s, "fd", None)
        hold_exclusively(fd)
        keep_dtr_on_close(fd)

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
        hold_exclusively(getattr(self._s, "fd", None), hold=False)
        try:
            self._s.close()
        except Exception:  # noqa: BLE001 -- a vanished USB device raises whatever the OS likes
            pass


class SimulatedHeater:
    """One heater of the simulated board, when its heaters are modelled: a first-order
    plus dead time plant from the heater's power (0 to ``max_power``) to its rise over
    ``ambient``, and the board's PID round it, stepped every ``dt`` simulated seconds.

    The PID is ``control_loops.PIDRunner``'s, its derivative on the reading smoothed by
    ``smoothing`` a step; outside ``functional_range`` degrees of the target the heater is
    full on or off and the PID starts afresh, as Marlin's is documented to do (assumed,
    with Marlin's constants unconfirmed: the range and the smoothing here are the
    simulator's). A reading has Gaussian noise of ``noise`` degrees. Every number is the
    simulator's own and no machine's."""

    def __init__(
        self,
        plant,
        ambient: float,
        gains: Tuple[float, float, float],
        dt: float = 0.1,
        max_power: float = 255.0,
        smoothing: float = 0.95,
        functional_range: float = 10.0,
        noise: float = 0.15,
        seed: str = "",
    ):
        import random

        from .. import control_loops as cl

        self.cl = cl
        self.plant, self.ambient, self.dt = plant, ambient, dt
        self.max_power, self.smoothing, self.functional_range = (
            max_power,
            smoothing,
            functional_range,
        )
        self.noise = noise
        self._rng = random.Random(seed)
        self.runner = cl.PlantRunner(plant, dt)
        self.gains = tuple(float(g) for g in gains)
        self.target = 0.0
        self.power = 0.0
        self.autotune: Optional["SimulatedAutotune"] = None
        self._ctrl = None

    @property
    def temperature(self) -> float:
        return self.ambient + self.runner.output

    def reading(self) -> float:
        return self.temperature + (self._rng.gauss(0.0, self.noise) if self.noise else 0.0)

    def set_gains(self, kp: float, ki: float, kd: float) -> None:
        self.gains = (kp, ki, kd)
        self._ctrl = None

    def settle_at(self, target: float) -> None:
        """At rest at ``target``, its PID holding the power that keeps it there."""
        self.target = target
        u = min(self.max_power, max(0.0, (target - self.ambient) / self.plant.gain))
        self.runner = self.cl.PlantRunner(self.plant, self.dt, start=u)
        self._controller(integral=u)
        self.power = u

    def _controller(self, integral: float = 0.0):
        kp, ki, kd = self.gains
        pid = self.cl.PID(kp, ki, kd, dt=self.dt, filter=self.cl.filter_of(self.smoothing, self.dt))
        self._ctrl = self.cl.PIDRunner(pid, 0.0, self.max_power, integral=integral)
        return self._ctrl

    def step(self) -> None:
        measured = self.reading()
        if self.autotune is not None:
            self.power = self.autotune.power(measured)
        elif self.target <= 0:
            self.power, self._ctrl = 0.0, None
        else:
            error = self.target - measured
            if abs(error) > self.functional_range:
                self.power, self._ctrl = (self.max_power if error > 0 else 0.0), None
            else:
                ctrl = self._ctrl or self._controller()
                self.power = ctrl.update(self.target, measured)
        self.runner.step(self.power)


class SimulatedAutotune:
    """A relay autotune on a simulated heater, in the manner Marlin's ``M303`` is
    documented to work (assumed, not read from its source): the heater full on and off
    about the target by ``bias +/- d``, the bias moved each cycle to even the times up and
    down, the oscillation's swing and period read each cycle, and from the third the
    ultimate gain by the relay's describing function, ``Ku = 4 d / (pi a)``, and the
    classic Ziegler-Nichols gains, ``Kp = 0.6 Ku``, ``Ki = 2 Kp / Tu``, ``Kd = Kp Tu / 8``.
    Its words are the forms ``parse_autotune`` reads. Every choice of when to switch,
    how far to move the bias, and when to give up is the simulator's."""

    REPORT_EVERY_S = 2.0
    HOLD_S = 5.0  # the least time between two switches
    OVERSHOOT_C = 30.0  # past the target by this much, it gives up
    GIVE_UP_S = 20 * 60.0

    def __init__(self, heater: SimulatedHeater, target: float, cycles: int, label: str):
        self.heater, self.target, self.cycles, self.label = heater, target, cycles, label
        top = heater.max_power
        self.bias = self.d = top / 2
        self.heating = True
        self.t = 0.0
        self.switched = 0.0
        self.t_high = self.t_low = 0.0
        self.high, self.low = -1e9, 1e9
        self.cycle = 0
        self.next_report = 0.0
        self.said: List[str] = []
        self.result: Optional[Tuple[float, float, float]] = None
        self.done = False

    def power(self, measured: float) -> float:
        h = self.heater
        dt = h.dt
        self.t += dt
        self.high, self.low = max(self.high, measured), min(self.low, measured)
        if self.t >= self.next_report:
            self.next_report += self.REPORT_EVERY_S
            power = "B@" if self.label == "B" else "@"
            self.said.append(
                f" {self.label}:{measured:.2f} /{self.target:.2f} {power}:{int(self._out())}"
            )
        if measured > self.target + self.OVERSHOOT_C:
            return self._end("PID Autotune failed! Temperature too high")
        if self.t > self.GIVE_UP_S:
            return self._end("PID Autotune failed! timeout")
        since = self.t - self.switched
        if self.heating and measured > self.target and since > self.HOLD_S:
            self.heating = False
            self.t_high = since
            self.switched = self.t
        elif not self.heating and measured < self.target and since > self.HOLD_S:
            self.heating = True
            self.t_low = since
            self.switched = self.t
            self.cycle += 1
            if self.cycle > 1:
                top = h.max_power
                self.bias += self.d * (self.t_high - self.t_low) / (self.t_low + self.t_high)
                self.bias = min(top - 20, max(20.0, self.bias))
                self.d = top - 1 - self.bias if self.bias > top / 2 else self.bias
                self.said.append(
                    f" bias: {int(self.bias)} d: {int(self.d)} min: {self.low:.2f} max: {self.high:.2f}"
                )
                if self.cycle > 2:
                    ku = 4 * self.d / (math.pi * (self.high - self.low) / 2)
                    tu = self.t_low + self.t_high
                    kp = 0.6 * ku
                    ki = 2 * kp / tu
                    kd = kp * tu / 8
                    self.result = (kp, ki, kd)
                    self.said += [
                        f" Ku: {ku:.2f} Tu: {tu:.2f}",
                        " Classic PID ",
                        f" Kp: {kp:.2f} Ki: {ki:.2f} Kd: {kd:.2f}",
                    ]
            self.high, self.low = -1e9, 1e9
            if self.cycle > self.cycles:
                kp, ki, kd = self.result or (0.0, 0.0, 0.0)
                return self._end(
                    "PID Autotune finished! Put the last Kp, Ki and Kd constants from below into Configuration.h",
                    [
                        f"#define DEFAULT_Kp {kp:.2f}",
                        f"#define DEFAULT_Ki {ki:.2f}",
                        f"#define DEFAULT_Kd {kd:.2f}",
                    ],
                )
        return self._out()

    def _out(self) -> float:
        return self.bias + self.d if self.heating else self.bias - self.d

    def _end(self, words: str, more: Tuple[str, ...] = ()) -> float:
        self.said += [words, *more]
        self.done = True
        return 0.0

    def stop(self, words: str) -> None:
        if not self.done:
            self.said.append(words)
            self.done = True


def simulated_heaters(port: str) -> Dict[str, SimulatedHeater]:
    """The simulated board's modelled heaters: a hotend and a bed, each a plant of the
    simulator's own and gains designed for it by IMC-PID with its closed-loop time its dead
    time. No machine's numbers."""
    from .. import control_loops as cl

    hotend = cl.FOPDT(1.0, 90.0, 3.0)
    bed = cl.FOPDT(0.45, 240.0, 8.0)

    def gains(plant):
        pid = cl.design("imc", plant=plant, dt=0.1).pid
        return (round(pid.kp, 2), round(pid.ki, 4), round(pid.kd, 2))

    return {
        "T": SimulatedHeater(hotend, 23.0, gains(hotend), seed=f"{port}:T"),
        "B": SimulatedHeater(bed, 24.0, gains(bed), seed=f"{port}:B"),
    }


def heaters_modelled() -> bool:
    """``APOTHECARY_SIMULATED_HEATERS=model``: the simulated board's heaters follow a
    thermal model; otherwise a heater sits at its target, as it always has."""
    return os.environ.get("APOTHECARY_SIMULATED_HEATERS", "").strip().lower() == "model"


class SimulatedPrinter:
    """A pretend Marlin behind the transport slot: no port, no hardware.

    Answers the query codes this module sends with plausible, slowly
    moving values. ``APOTHECARY_SIMULATED_PRINTER=printing`` starts it
    mid-way through an SD print that advances about 1 %/s and starts over
    at the end (so a viewer sees ``printing`` and a progress figure
    straight away, however long it looks), or holds still at the fraction
    ``APOTHECARY_SIMULATED_PROGRESS`` names, for pictures that are the same
    on every run; the default is a cold, idle machine. Any other command
    gets ``ok``.
    """

    FIRMWARE = "Marlin Apothecary Simulator 1.0 (simulated)"

    def __init__(
        self,
        port: str,
        baud: int,
        heaters: Optional[Dict[str, SimulatedHeater]] = None,
        clock: Optional[Callable[[], float]] = None,
    ):
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
        self.pos = {"X": 0.0, "Y": 0.0, "Z": 0.0}
        self.relative = False
        self.halted = False
        # Multiplies every G4 dwell: 1 is real time, 0 skips them.
        self.dwell_scale = float(os.environ.get("APOTHECARY_SIMULATED_SPEED", "1"))
        held = os.environ.get("APOTHECARY_SIMULATED_PROGRESS", "").strip()
        self.held_at = min(max(float(held), 0.0), 1.0) if held else None
        # The heaters' model, when asked for (``heaters_modelled``, or handed in by a test):
        # its own clock, simulated seconds, which ``APOTHECARY_SIMULATED_HEATER_SPEED``
        # runs faster than real time. Without it a heater sits at its target.
        self._lock = threading.Lock()
        self.heaters = (
            heaters
            if heaters is not None
            else (simulated_heaters(port) if heaters_modelled() else None)
        )
        speed = float(os.environ.get("APOTHECARY_SIMULATED_HEATER_SPEED", "1") or 1)
        self._clock = clock or (lambda: time.monotonic() * speed)
        self._sim_at = self._clock()
        self._waiting: List[str] = []  # lines written while an autotune holds the board
        self._autotune: Optional[str] = None  # the heater's key whose autotune runs
        self.saves = 0  # M500s heard
        # The gains the board answers with when its heaters are not modelled.
        self.gains = {"T": (20.0, 1.0, 100.0), "B": (50.0, 2.0, 500.0)}
        if self.heaters is not None:
            self.gains = {k: h.gains for k, h in self.heaters.items()}
            if self.printing:
                self.heaters["T"].settle_at(self.hot_target)
                self.heaters["B"].settle_at(self.bed_target)

    # -- the modelled heaters ------------------------------------------------------
    CATCH_UP_S = 2 * 3600.0  # the most simulated time one advance steps through

    def _advance(self) -> None:
        """Step the modelled heaters to the clock's now; what an autotune says as it runs
        goes out as it is said, and its end lets the lines written meanwhile be answered."""
        if self.heaters is None:
            return
        now = self._clock()
        span = min(now - self._sim_at, self.CATCH_UP_S)
        self._sim_at = now
        steps = int(span / self.heaters["T"].dt)
        for _ in range(max(0, steps)):
            for heater in self.heaters.values():
                heater.step()
            if self._autotune is not None:
                tune = self.heaters[self._autotune].autotune
                if tune.said:
                    self._emit(tune.said)
                    tune.said = []
                if tune.done:
                    self._end_autotune()

    def _emit(self, lines: List[str]) -> None:
        self._pending += "".join(ln + "\n" for ln in lines).encode()

    def _end_autotune(self) -> None:
        heater = self.heaters[self._autotune]
        tune = heater.autotune
        if tune.said:
            self._emit(tune.said)
        heater.autotune = None
        heater.target = 0.0  # the heater off at the end, as the simulator chooses
        self._autotune = None
        self._emit(["ok"])
        waiting, self._waiting = self._waiting, []
        for cmd in waiting:
            self._emit(self._reply(cmd))

    def _start_autotune(self, cmd: str) -> List[str]:
        if self.heaters is None:
            return [
                "echo:the simulated heaters are not modelled (APOTHECARY_SIMULATED_HEATERS=model): "
                "no autotune",
                "ok",
            ]
        m = AUTOTUNE_RE.match(cmd)
        if not m:
            return [f'echo:Unknown command: "{cmd}"', "ok"]
        key = "B" if m.group(1) == "-1" else "T"
        heater = self.heaters[key]
        heater.autotune = SimulatedAutotune(heater, float(m.group(2)), int(m.group(3)), key)
        self._autotune = key
        return []

    def _progress(self) -> float:
        # A print that goes round: a browser suite that runs longer than one
        # print still finds the machine printing, at whatever percent it is --
        # unless APOTHECARY_SIMULATED_PROGRESS holds it at one (a fraction), so
        # pictures of it are the same on every run.
        if not self.printing:
            return 0.0
        if self.held_at is not None:
            return self.held_at
        return ((time.monotonic() - self._t0) / self.print_len) % 1.0

    def _apply_control(self, cmd: str) -> Optional[List[str]]:
        """Honour the control set so the overlay's effects show up in the next poll."""
        parts = cmd.upper().split()
        code = parts[0]
        args = {p[0]: p[1:] for p in parts[1:] if p}
        if code == "M104":
            self.hot_target = float(args.get("S", 0))
            if self.heaters is not None:
                self.heaters["T"].target = self.hot_target
        elif code == "M140":
            self.bed_target = float(args.get("S", 0))
            if self.heaters is not None:
                self.heaters["B"].target = self.bed_target
        elif code in ("M301", "M304") and {"P", "I", "D"} <= set(args):
            key = "B" if code == "M304" else "T"
            gains = (float(args["P"]), float(args["I"]), float(args["D"]))
            self.gains[key] = gains
            if self.heaters is not None:
                self.heaters[key].set_gains(*gains)
        elif code in ("M301", "M304"):
            kp, ki, kd = self.gains["B" if code == "M304" else "T"]
            return [f"echo: p:{kp:.2f} i:{ki:.2f} d:{kd:.2f}", "ok"]
        elif code == "M503":
            (tp, ti, td), (bp, bi, bd) = self.gains["T"], self.gains["B"]
            return [
                "echo:; PID settings:",
                f"echo:  M301 P{tp:.2f} I{ti:.2f} D{td:.2f}",
                f"echo:  M304 P{bp:.2f} I{bi:.2f} D{bd:.2f}",
                "ok",
            ]
        elif code == "M500":
            self.saves += 1
            return ["echo:Settings Stored (the simulator keeps nothing)", "ok"]
        elif code == "M303":
            return self._start_autotune(" ".join(parts))
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
            self.hot_target = self.bed_target = 0.0
            if self.heaters is not None:
                for heater in self.heaters.values():
                    heater.target, heater.autotune = 0.0, None
                self._autotune, self._waiting = None, []
            return ["Error:Printer halted. kill() called!"]
        elif code in ("M109", "M190"):
            # Heat and wait: a real board says busy until it is there; here it is there.
            target = float(args.get("S", args.get("R", 0)))
            if code == "M109":
                self.hot_target = target
            else:
                self.bed_target = target
            if self.heaters is not None:
                self.heaters["T" if code == "M109" else "B"].target = target
            return ["echo:busy: processing", "ok"]
        elif code == "G92":
            for axis in "XYZ":
                if axis in args:
                    self.pos[axis] = float(args[axis])
        elif code == "G4":
            # A dwell takes the time it says (capped), so a streamed file takes
            # time to stream and a pause has something to interrupt.
            ms = float(args.get("P", 0)) or 1000 * float(args.get("S", 0))
            time.sleep(min(2.0, ms / 1000) * self.dwell_scale)
        elif code == "G29":
            # A probe takes a while; the busy lines are what Marlin prints while it does.
            # At verbosity 3 or more each point probed is said, where the probe stood.
            said = self._probed_lines() if float(args.get("V") or 0) >= 3 else []
            return [
                "echo:busy: processing",
                *said,
                "echo:busy: processing",
                *self._grid_lines(),
                "ok",
            ]
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
        """A bed that is slightly tilted and a little bowed, the same at a place of a
        port's bed however many polls and probes came before: its roughness is seeded by
        the port and the place alone, apart from the temperatures' wobble."""
        import random

        tilt = 0.12 * (i - 2) - 0.08 * (j - 2)
        bow = -0.05 * ((i - 2) ** 2 + (j - 2) ** 2) / 4
        rough = random.Random(f"{self.port}:{i:.4f}:{j:.4f}").uniform(-0.01, 0.01)
        return tilt + bow + rough

    # Where the simulated probe's five by five points lie, in bed coordinates: Marlin's
    # bounds for its 220 mm bed and the probe 44 mm left of the nozzle and 10 mm in
    # front (M851), 10 mm in from the bed's edges and up to where the probe reaches.
    PROBED_X = (10.0, 176.0)
    PROBED_Y = (10.0, 210.0)

    def _probed_lines(self) -> List[str]:
        """``Bed X: .. Y: .. Z: ..`` for each point, column by column and each column
        back and forth along Y, as Marlin's G29 probes and says them at verbosity 3."""
        (x0, x1), (y0, y1) = self.PROBED_X, self.PROBED_Y
        lines = []
        for i in range(5):
            for j in range(5) if i % 2 == 0 else reversed(range(5)):
                x, y = x0 + (x1 - x0) * i / 4, y0 + (y1 - y0) * j / 4
                lines.append(f"Bed X: {x:.2f} Y: {y:.2f} Z: {self._bed_z(i, j):.2f}")
        return lines

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
        if code == "M105" and self.heaters is not None:
            hot, bed = self.heaters["T"], self.heaters["B"]
            return [
                f"ok T:{hot.reading():.2f} /{hot.target:.2f} B:{bed.reading():.2f} /{bed.target:.2f} "
                f"@:{int(round(hot.power))} B@:{int(round(bed.power))}"
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
            held = self.held_at is not None and self.printing
            secs = int(self.held_at * self.print_len if held else time.monotonic() - self._t0)
            return [f"echo:Print time: {secs // 60}m {secs % 60}s", "ok"]
        return ["ok"]

    def write(self, data: bytes) -> None:
        with self._lock:
            self._advance()
            for cmd in data.decode("utf-8", "replace").split("\n"):
                cmd = cmd.strip()
                if not cmd:
                    continue
                if self._autotune is not None:
                    code = cmd.split()[0].upper()
                    if code == "M108":
                        # A break of the wait ends the autotune, as Marlin's is documented
                        # to end on M108 (assumed); the words are the simulator's.
                        self.heaters[self._autotune].autotune.stop("echo:autotune broken by M108")
                        self._end_autotune()
                        self._emit(["ok"])
                        continue
                    if code not in ("M112", "M410"):
                        self._waiting.append(cmd)  # the board's queue waits behind it
                        continue
                self._emit(self._reply(cmd))

    def read(self, timeout: float) -> bytes:
        with self._lock:
            self._advance()
            if self._pending:
                out, self._pending = self._pending, b""
                return out
        time.sleep(min(timeout, 0.02))
        return b""

    def pulse_reset(self) -> None:
        with self._lock:
            self._t0 = time.monotonic()
            self.halted = False  # a reset is how a halted board comes back
            if self.heaters is not None:
                for heater in self.heaters.values():
                    heater.target, heater.autotune = 0.0, None
                self._autotune, self._waiting = None, []
            self._pending += b"start\n External Reset\n" + self.FIRMWARE.encode() + b"\n"

    def close(self) -> None:
        pass


TransportFactory = Callable[[str, int], Transport]
ENGINES: Dict[str, TransportFactory] = {
    "pyserial": PySerialTransport,
    "simulated": SimulatedPrinter,
}


def serial_engine() -> str:
    """``APOTHECARY_SERIAL_ENGINE`` if set, else pyserial."""
    wanted = os.environ.get("APOTHECARY_SERIAL_ENGINE", "").strip().lower() or "pyserial"
    if wanted not in ENGINES:
        raise ToolchainError(
            f"APOTHECARY_SERIAL_ENGINE={wanted!r}; known engines: {', '.join(ENGINES)}"
        )
    return wanted


def open_transport(port: str, baud: int) -> Transport:
    engine = serial_engine()
    if engine == "simulated":
        # A port named in APOTHECARY_SIMULATED_ROUTER answers as a GRBL router, every
        # other as the Marlin printer.
        from . import grbl

        if port in grbl.simulated_ports():
            return grbl.SimulatedRouter(port, baud)
    return ENGINES[engine](port, baud)


# --- comms log: everything said on a port, for a board's Machine ---------------------


class CommsLog:
    """A per-port ring of what went over the wire, kept by ``PrinterLinks``.

    Survives a reconnect (the registry owns it, not the link) and a page
    reload (it lives in the server), so a printer's Machine shows polls made
    by other clients too. Entries carry a monotonically increasing index so a
    reader asks for ``since=N`` and gets only what is new.
    """

    def __init__(self, port: str, capacity: int = 4000):
        self.port = port
        self.capacity = capacity
        self._entries: List[dict] = []
        self._base = 0  # index of _entries[0]
        self._lock = threading.Lock()

    def add(self, kind: str, text: str, origin: str = "", note: Optional[str] = None) -> None:
        with self._lock:
            entry = {
                "i": self._base + len(self._entries),
                "t": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "kind": kind,  # tx | rx | boot | sys
                "origin": origin,  # poll | query | identify -- who sent the command
                "text": text,
            }
            if note:
                entry["note"] = note  # the line in words, where the dialect has them (error:15)
            self._entries.append(entry)
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

SOFT_RESET = b"\x18"  # GRBL's realtime reset, which its banner answers
OK_RE = re.compile(r"^ok\b")
# A board's first line as it boots: Marlin's `start`, Grbl's banner.
BOOT_RE = re.compile(r"^(start$|Grbl \S+ \[)")
RESET_ANSWER_S = 10.0  # a banner this soon after a reset written here answers it
UNSOLICITED_KEPT = 200  # lines said outside any exchange that a link keeps
OWED_WAIT_S = 0.5  # how long an exchange waits for a reply owed to an earlier line
# Marlin objects with `Error:` or `!!`. Every dialect's objection is in OBJECTIONS, each
# dialect adding its own when it is imported (grbl.py: `error:N` and, out of turn,
# `ALARM:N`): the link closes an exchange on any of them, since a board is asked in
# one dialect before it is known to speak another.
ERROR_RE = re.compile(r"^(Error:|!!)")
OBJECTIONS: List["re.Pattern[str]"] = [ERROR_RE]
BUSY_RE = re.compile(r"^echo:busy:")
RESEND_RE = re.compile(r"^Resend:")


class GcodeLink:
    """A held-open serial port speaking line-per-command G-code.

    ``command()`` is serialised by a lock so a poll and a user command never
    interleave their replies. Lines that arrive outside any exchange (an
    autoreport, a boot banner) are kept in ``unsolicited`` for the caller.
    The emergency stop takes no part in that order (``emergency_stop()``): a
    second lock guards only the writing of a line, so M112 waits at most for
    a line being written, never for an exchange in flight.
    """

    def __init__(self, port: str, baud: int, transport: Transport, log: Optional[CommsLog] = None):
        self.port = port
        self.baud = baud
        self._t = transport
        self._lock = threading.RLock()
        self._write_lock = threading.Lock()  # one line on the wire at a time
        # The turnstile: an exchange takes it before the lock and lets it go once it
        # holds the lock, so one that waits with a bound (a poll between two streamed
        # lines) gets the link before the stream's next line, which would otherwise
        # take the lock back the instant it let go. ``waiters`` counts the bounded ones.
        self._turn = threading.Lock()
        self.waiters = 0
        self._holder: Optional[int] = None  # the thread holding the link ``together``
        self._buf = b""
        self.unsolicited: List[str] = []
        # The last `ALARM:N` the board said, whenever it said it: a GRBL status report
        # says a controller is in alarm and not which (grbl.poll_router reads this).
        self.alarm: Optional[str] = None
        # Every byte read from the board since the link opened: unchanged across an
        # exchange, the board said nothing at all to it.
        self.heard = 0
        # Boot banners heard since the link opened: a board that restarts under a
        # job says so here (Marlin's `start`, Grbl's `Grbl 1.1h [`), and nowhere else.
        self.restarts = 0
        # Those of them nothing here asked for: a banner that does not follow a reset
        # this link wrote is a board whose power was cycled, or its button pressed.
        self.unasked_restarts = 0
        self._asked_reset = float("-inf")
        # Replies still to come for lines whose exchange is over: one written ahead
        # of an exchange in flight (``ahead``), one whose `ok` did not come in time.
        # The next exchange reads them off first, so its own reply is its own.
        self._owed = 0
        self.opened_at = datetime.now(timezone.utc)
        self.log = log or CommsLog(port)
        self.engine = type(transport).__name__
        self.log.add("sys", f"opened {port} @ {baud} via {self.engine}")

    # Every wait on the board -- a reply, a quiet line, a boot banner -- is
    # multiplied by this. 1 against hardware; the tests' scripted boards answer
    # at once, so the tests set it near 0 rather than wait out real silences.
    time_scale: float = 1.0

    # The dialect's words for a line the board says, kept beside it in the log
    # (grbl.explain: `error:15` is a jog past the travel); None for a dialect with
    # none. Set once the board is identified.
    annotate: Optional[Callable[[str], Optional[str]]] = None

    def _note(self, line: str) -> Optional[str]:
        return self.annotate(line) if self.annotate is not None else None

    def _acquire(self, wait: Optional[float]) -> bool:
        """The link's lock, waiting ``wait`` seconds at most (forever for None), through
        the turnstile: exchanges take the lock in the order they asked for it. The
        thread that holds the link ``together`` goes straight in: the turnstile may
        be held by one that is waiting for it to let go."""
        if self._holder == threading.get_ident():
            self._lock.acquire()
            return True
        if wait is None:
            with self._turn:
                self._lock.acquire()
            return True
        self.waiters += 1
        try:
            end = time.monotonic() + wait
            if not self._turn.acquire(timeout=wait):
                return False
            try:
                return self._lock.acquire(timeout=max(0.0, end - time.monotonic()))
            finally:
                self._turn.release()
        finally:
            self.waiters -= 1

    def _read_line(self, timeout: float) -> Optional[str]:
        end = time.monotonic() + timeout
        while b"\n" not in self._buf:
            left = end - time.monotonic()
            if left <= 0:
                return None
            chunk = self._t.read(min(left, 0.5))
            if not chunk:
                continue
            self.heard += len(chunk)
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        text = line.decode("utf-8", "replace").rstrip("\r")
        if text.startswith("ALARM:"):
            self.alarm = text
        if BOOT_RE.match(text):
            self.restarts += 1
            if time.monotonic() - self._asked_reset > RESET_ANSWER_S:
                self.unasked_restarts += 1
            self._owed = 0  # a board that restarted owes nothing it was asked before
        return text

    def sweep(self) -> List[str]:
        """What the board has said outside any exchange, read without waiting and
        kept in ``unsolicited``: how a job between two lines learns its board has
        restarted (``restarts``) before it sends the next. Nothing, when an exchange
        is in flight: that exchange is reading."""
        if not self._lock.acquire(blocking=False):
            return []
        try:
            chunk = self._t.read(0.0)
            if chunk:
                self.heard += len(chunk)
                self._buf += chunk
            lines: List[str] = []
            while b"\n" in self._buf:
                line = self._read_line(0.0)
                lines.append(line)
                if OK_RE.match(line) and self._owed > 0:
                    self._owed -= 1  # the late reply of a line whose exchange is over
                self.log.add("rx", line, "unasked", note=self._note(line))
            # A board that reports by itself all through a long job: the newest are kept.
            self.unsolicited = (self.unsolicited + lines)[-UNSOLICITED_KEPT:]
            return lines
        finally:
            self._lock.release()

    def drain(self, quiet: float = 0.3, limit: float = 5.0) -> List[str]:
        """Read until the board has been silent for ``quiet`` seconds (or ``limit``)."""
        out: List[str] = []
        end = time.monotonic() + limit * self.time_scale
        with self._lock:
            while time.monotonic() < end:
                line = self._read_line(quiet * self.time_scale)
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
        end = time.monotonic() + limit * self.time_scale
        with self._lock:
            while time.monotonic() < end:
                line = self._read_line((first if not lines else quiet) * self.time_scale)
                if line is None:
                    break
                lines.append(line)
                self.log.add("boot", line, note=self._note(line))
        self.unsolicited.extend(lines)
        return lines

    def _reset_asked(self) -> None:
        self._asked_reset = time.monotonic()

    def reset(self, limit: float = 6.0) -> List[str]:
        """Reboot the board on purpose and return its boot banner. Refused while a
        job (a print, a bed reading) holds the link: rebooting under it leaves the
        host streaming moves to a cold, unhomed board."""
        if self.job is not None:
            raise PortHeld(f"{self.port}: a {self.job.get('kind')} holds the port -- not resetting")
        with self._lock:
            self._buf = b""
            self.log.add("sys", "reset: DTR pulse")
            self._reset_asked()
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
        if not self._acquire(wait):
            raise LinkBusy(
                f"{self.port}: the link is busy ({self.job['kind'] if self.job else 'an exchange'})"
            )
        try:
            return self._exchange(cmd, timeout, origin, quiet)
        finally:
            self._lock.release()

    def watch(
        self,
        cmd: str,
        each: Callable[[str], None],
        silence: float,
        limit: float,
        origin: str = "control",
    ) -> List[str]:
        """Send one line whose answer is long (an autotune) and read it line by line up to
        its ``ok``, handing each line to ``each`` as it comes: a watcher that raises ends
        the reading there, and so does a board that says nothing for ``silence`` seconds or
        has not finished within ``limit`` (``ToolchainError``). Ended early, the line's
        ``ok`` is owed: the next exchange reads it off first, if it comes."""
        cmd = cmd.strip()
        if not cmd or "\n" in cmd:
            raise ValueError("one G-code command per call")
        self._acquire(None)
        try:
            if self.stopped is not None:
                raise ToolchainError(f"{self.port}: {self.stopped}: {cmd} is not sent")
            self._read_owed()
            self.log.add("tx", cmd, origin)
            with self._write_lock:
                self._t.write((cmd + "\n").encode())
            lines: List[str] = []
            end = time.monotonic() + limit * self.time_scale
            while True:
                left = end - time.monotonic()
                if left <= 0:
                    self._owed += 1
                    raise ToolchainError(f"{self.port}: {cmd} did not finish within {limit:.0f}s")
                line = self._read_line(min(left, silence * self.time_scale))
                if line is None:
                    self._owed += 1
                    if time.monotonic() >= end:
                        raise ToolchainError(
                            f"{self.port}: {cmd} did not finish within {limit:.0f}s"
                        )
                    raise ToolchainError(
                        f"{self.port}: nothing said for {silence:.0f}s during {cmd}"
                    )
                lines.append(line)
                self.log.add("rx", line, origin, note=self._note(line))
                if BOOT_RE.match(line):
                    raise ToolchainError(
                        f"{self.port}: the board restarted before it answered {cmd} ({line})"
                    )
                # An `ok` that carries a temperature report is a report, not the end.
                if OK_RE.match(line) and not is_temperature_line(line):
                    return lines
                if any(p.match(line) for p in OBJECTIONS):
                    raise ToolchainError(f"{self.port}: {cmd} -> {line}")
                try:
                    each(line)
                except BaseException:
                    self._owed += 1
                    raise
        finally:
            self._lock.release()

    def _read_owed(self, wait: float = OWED_WAIT_S) -> List[str]:
        """Read off the replies owed to earlier lines, each up to its ``ok``, so the
        exchange about to begin reads its own; what was read. One that does not come
        within ``wait`` seconds is given up on: the board dropped the line, or is gone."""
        read: List[str] = []
        while self._owed > 0:
            end = time.monotonic() + wait * self.time_scale
            while True:
                left = end - time.monotonic()
                line = self._read_line(left) if left > 0 else None
                if line is None:
                    self._owed = 0
                    return read
                read.append(line)
                self.log.add("rx", line, "late", note=self._note(line))
                if OK_RE.match(line) or any(p.match(line) for p in OBJECTIONS):
                    break
            self._owed = max(0, self._owed - 1)
        return read

    def interrupt(self, cmd: str, wait: float, origin: str = "control") -> List[str]:
        """A line written at once, whatever is in flight (``M108``, the break of a wait),
        and then, once the link is free, the replies owed to it and to the lines before
        it read off, waiting up to ``wait`` seconds for each: what ends a long line that
        was left early (an autotune), so the next exchange's reply is its own. What was
        read; nothing more is waited for once a reply does not come."""
        cmd = cmd.strip()
        if not cmd or "\n" in cmd:
            raise ValueError("one G-code command per call")
        self.log.add("tx", cmd, origin)
        with self._write_lock:
            self._t.write((cmd + "\n").encode())
            self._owed += 1
        self._acquire(None)
        try:
            return self._read_owed(wait)
        finally:
            self._lock.release()

    def _exchange(self, cmd: str, timeout: float, origin: str, quiet: bool) -> List[str]:
        """``command``'s exchange, by a caller that holds the link."""
        if self.stopped is not None:
            raise ToolchainError(f"{self.port}: {self.stopped}: {cmd} is not sent")
        self._read_owed()
        if not quiet:
            self.log.add("tx", cmd, origin)
        with self._write_lock:
            self._t.write((cmd + "\n").encode())
        lines: List[str] = []
        end = time.monotonic() + timeout * self.time_scale
        while True:
            left = end - time.monotonic()
            if left <= 0:
                self.log.add("sys", f"timeout: no `ok` for {cmd} within {timeout:.0f}s")
                self._owed += 1  # if it comes late, it is not the next line's
                raise ToolchainError(
                    f"{self.port}: no `ok` for {cmd} within {timeout:.0f}s "
                    f"({len(lines)} lines received)"
                )
            line = self._read_line(left)
            if line is None:
                continue
            lines.append(line)
            objected = any(p.match(line) for p in OBJECTIONS) or RESEND_RE.match(line)
            booted = BOOT_RE.match(line)
            if not quiet or objected or booted:
                if quiet:
                    self.log.add("tx", cmd, origin)  # the line it objected to, for the record
                self.log.add("rx", line, origin, note=self._note(line))
            asked = time.monotonic() - self._asked_reset <= RESET_ANSWER_S
            if booted and (self.job is not None or asked):
                # A board that boots under a job, or at a reset written here, forgets
                # what it was asked: this line's `ok` is not coming, and waiting its
                # time out only holds the link. A board that boots as its port is
                # first opened is left to answer: its banner is how it is known.
                raise ToolchainError(
                    f"{self.port}: the board restarted before it answered {cmd} ({line})"
                )
            if BUSY_RE.match(line):
                end = time.monotonic() + timeout * self.time_scale  # heating/homing
            elif OK_RE.match(line):
                return lines
            elif objected:
                # A refusal says the dialect's words for it, where it has them, so
                # a typed control and a job that stops both read as more than a code.
                note = self._note(line)
                words = f" ({note})" if note else ""
                raise ToolchainError(f"{self.port}: {cmd} -> {line}{words}")

    def ahead(self, cmd: str, timeout: float = 5.0, origin: str = "control") -> List[str]:
        """A line written at once, ahead of an exchange in flight: Marlin's break of
        a heat-and-wait (``M108``) and its quickstop (``M410``), which are for a
        board that is busy answering something else. With nothing in flight it is
        an exchange like any other. With one in flight the line is written under
        it and nothing is waited for: its ``ok`` comes after that exchange's own,
        and the next exchange reads it off first."""
        cmd = cmd.strip()
        if not cmd or "\n" in cmd:
            raise ValueError("one G-code command per call")
        if self._lock.acquire(blocking=False):
            try:
                return self._exchange(cmd, timeout, origin, quiet=False)
            finally:
                self._lock.release()
        self.log.add("tx", cmd, origin)
        with self._write_lock:
            self._t.write((cmd + "\n").encode())
            self._owed += 1
        return []

    @contextmanager
    def together(self, wait: Optional[float] = None):
        """The link held across several exchanges, so no other caller's line goes
        between them: a jog's ``G91``, its move and its ``G90``. The stop and a line
        written ``ahead`` still go at once. ``LinkBusy`` when ``wait`` runs out."""
        if not self._acquire(wait):
            raise LinkBusy(
                f"{self.port}: the link is busy ({self.job['kind'] if self.job else 'an exchange'})"
            )
        mine = self._holder != threading.get_ident()
        if mine:
            self._holder = threading.get_ident()
        try:
            yield self
        finally:
            if mine:
                self._holder = None
            self._lock.release()

    def realtime(
        self,
        data: bytes,
        until: Optional["re.Pattern[str]"] = None,
        timeout: float = 1.0,
        wait: Optional[float] = None,
        label: Optional[str] = None,
        now: bool = False,
        origin: str = "poll",
    ) -> List[str]:
        """GRBL's realtime characters (``?``, ``!``, ``~``, a reset), written as the
        bytes they are, with no newline and no ``ok`` to wait for; what the board
        says within ``timeout`` is returned, and with ``until`` the read ends at the
        first line matching it (a status report) or raises if none comes. ``now``
        writes ahead of an exchange in flight, as the emergency stop does -- a hold
        is for a machine in motion -- and then reads only if nothing else is;
        otherwise the write waits its turn, ``wait`` bounding the queueing."""
        name = label or data.decode("ascii", "backslashreplace")
        if data == SOFT_RESET:
            self._asked_reset = time.monotonic()
        if now:
            self.log.add("tx", name, origin)
            with self._write_lock:
                self._t.write(data)
            if not self._lock.acquire(blocking=False):
                return []
        else:
            if not self._acquire(wait):
                raise LinkBusy(
                    f"{self.port}: the link is busy ({self.job['kind'] if self.job else 'an exchange'})"
                )
            self.log.add("tx", name, origin)
            with self._write_lock:
                self._t.write(data)
        try:
            lines: List[str] = []
            end = time.monotonic() + timeout * self.time_scale
            while (left := end - time.monotonic()) > 0:
                line = self._read_line(left)
                if line is None:
                    break
                lines.append(line)
                self.log.add("rx", line, origin, note=self._note(line))
                if until is not None and until.match(line.strip()):
                    return lines
            if until is not None:
                self.log.add("sys", f"timeout: no report for {name} within {timeout:.0f}s")
                raise ToolchainError(
                    f"{self.port}: no report for {name} within {timeout:.0f}s "
                    f"({len(lines)} lines received)"
                )
            return lines
        finally:
            self._lock.release()

    def emergency_stop(self, settle: float = 1.0) -> List[str]:
        """M112, written at once: ahead of any exchange in flight, waiting for no
        `ok`, which a halted board never sends. With nothing in flight, what the
        board says within ``settle`` seconds is returned (Marlin's "Printer
        halted"); with an exchange in flight, that exchange reads it, and ends
        with it. The board acts on M112 as it reads it only when its firmware
        parses it early (Marlin's EMERGENCY_PARSER); otherwise after the moves
        it has queued."""
        self.log.add("tx", EMERGENCY_STOP, "control")
        with self._write_lock:
            self._t.write((EMERGENCY_STOP + "\n").encode())
        lines: List[str] = []
        if self._lock.acquire(blocking=False):
            try:
                end = time.monotonic() + settle * self.time_scale
                while (left := end - time.monotonic()) > 0:
                    line = self._read_line(left)
                    if line is None:
                        break
                    lines.append(line)
                    self.log.add("rx", line, "control", note=self._note(line))
            finally:
                self._lock.release()
        return lines

    def close(self) -> None:
        with self._lock:
            self.log.add("sys", f"closed {self.port}")
            self._t.close()

    # A long exchange (a bed probe takes minutes) is announced here, so a
    # poll can say "busy: probing" instead of queueing behind the lock for
    # as long as the firmware is blocked.
    job: Optional[dict] = None

    # Why no line is sent just now, when a job that sends its lines through calls of
    # its own (a bed reading) has been stopped under them: each is refused, said
    # here, until the job has let go. The realtime characters and the stop still go.
    stopped: Optional[str] = None

    def info(self) -> dict:
        return {
            "port": self.port,
            "baud": self.baud,
            "engine": self.engine,
            "opened_at": self.opened_at.isoformat(),
            "log_next": self.log.next_index,
        }


# Read before a port's link or log is handed out: the device layer's reading of the
# port list (``devices.ports_now``), which lets go of what is held for a board that has
# left the port (``PrinterLinks.forget``), so a link or a log is never the last board's.
# None until that layer is imported.
PORT_LIST_READ: Optional[Callable[[], object]] = None


def _read_port_list() -> None:
    if PORT_LIST_READ is not None:
        PORT_LIST_READ()


def job_holds_link(port: str, job: Optional[dict]) -> Optional[str]:
    """Why a link may not be dropped: a job holds it, and only the job lets go."""
    if job is None:
        return None
    from . import can

    return can.holding(port, f"a {job.get('kind')}", job.get("stage"))


class PrinterLinks:
    """Open links, one per port, released as a group before a task takes a port."""

    def __init__(self, factory: Optional[TransportFactory] = None):
        # The last control line each port refused, until one goes (devices.printer_control).
        self.refused: Dict[str, dict] = {}
        self._links: Dict[str, GcodeLink] = {}
        self._logs: Dict[str, CommsLog] = {}
        self._lock = threading.RLock()  # open() reaches log_for() while holding it
        self.factory: TransportFactory = factory or open_transport
        self.control = ControlLatch()

    def log_for(self, port: str) -> CommsLog:
        _read_port_list()
        return self._log_for(port)

    def _log_for(self, port: str) -> CommsLog:
        with self._lock:
            if port not in self._logs:
                self._logs[port] = CommsLog(port)
            return self._logs[port]

    def get(self, port: str) -> Optional[GcodeLink]:
        _read_port_list()
        with self._lock:
            return self._links.get(port)

    def open(self, port: str, baud: int, settle: bool = True) -> GcodeLink:
        """The existing link for ``port`` at that baud, else a fresh one (resets the board).

        A link a job holds is never replaced: reopening at another baud would
        drop the print under its own thread. ``settle`` waits out what the board
        says as it is opened; a stop does not wait for it."""
        _read_port_list()
        with self._lock:
            link = self._links.get(port)
            if link is not None and link.baud == baud:
                return link
            if link is not None:
                if link.job is not None:
                    raise PortHeld(
                        f"{port}: a {link.job.get('kind')} holds the port -- not reopening it"
                    )
                link.close()
            link = GcodeLink(port, baud, self.factory(port, baud), log=self._log_for(port))
            self._links[port] = link
        if settle:
            link.settle()
        return link

    def close(self, port: str) -> bool:
        """Drop the link. Refused while a job holds it, with no way around: only the
        job lets go of its link, after its own safe-off."""
        with self._lock:
            link = self._links.get(port)
            held = job_holds_link(port, link.job if link is not None else None)
            if held:
                raise PortHeld(held)
            self.control.disarm(port)  # a dropped link never stays armed
            self._links.pop(port, None)
        if link is None:
            return False
        link.close()
        return True

    def forget(self, port: str) -> None:
        """Another board is on ``port`` now: the last one's link is closed, its latch
        dropped and its log let go, so nothing of it is shown or armed as the new
        board's. A link a job holds is left to the job, which fails on its own once
        its board has gone."""
        with self._lock:
            link = self._links.get(port)
            if link is not None and link.job is not None:
                return
            self.control.disarm(port)
            self._links.pop(port, None)
            self._logs.pop(port, None)
        if link is not None:
            link.close()

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
EXTRUDE_MAX_MM = 10  # one extrude or retract move, relative: filament, never a whole spool
EXTRUDE_FEED_MAX = 300  # mm/min; a move names its feed, never inheriting a print's
CONTROL_CODES: List[tuple] = [
    (re.compile(r"^M104 S(\d{1,3})$"), "hotend target"),
    (re.compile(r"^M140 S(\d{1,3})$"), "bed target"),
    (re.compile(r"^M106(?: S(\d{1,3}))?$"), "fan on / speed 0-255"),
    (re.compile(r"^M107$"), "fan off"),
    (re.compile(r"^G28(?: [XYZ](?: [XYZ])*)?$"), "home (all or named axes)"),
    (re.compile(r"^G90$"), "absolute positioning"),
    (re.compile(r"^G91$"), "relative positioning"),
    (re.compile(r"^G[01](?:(?: [XYZ]-?\d{1,3}(?:\.\d{1,2})?){1,3})?(?: F\d{2,5})?$"), "move (jog)"),
    (re.compile(r"^M83$"), "extruder relative: E moves are distances, whatever a print left set"),
    (
        re.compile(r"^G1 E-?\d{1,2}(?:\.\d{1,2})? F\d{2,3}$"),
        "extrude or retract (relative E, with its feed)",
    ),
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
    (re.compile(r"^M301(?: E0)? P([\d.]+) I([\d.]+) D([\d.]+)$"), "hotend PID gains, not saved"),
    (re.compile(r"^M304 P([\d.]+) I([\d.]+) D([\d.]+)$"), "bed PID gains, not saved"),
]
# A gain line's bounds: a typo's guard, the seam's own, nothing Marlin says. Each figure
# is a plain decimal of at most four places; none is negative.
GAIN_MAX = {"P": 1000.0, "I": 1000.0, "D": 10000.0}
GAIN_FIGURE = re.compile(r"^\d{1,5}(?:\.\d{1,4})?$")
EMERGENCY_STOP = "M112"  # always accepted, latch or not; halts the board until reset
# Written ahead of an exchange in flight (``GcodeLink.ahead``): the lines Marlin acts
# on as it reads them, where its firmware parses them early (EMERGENCY_PARSER).
AHEAD = ("M108", "M410")
# What only turns something off or stops it, and so goes with the latch down: a
# heater's target to zero, the fan off, a wait broken, the planned moves dropped, the
# card paused. A latch that lapsed never stands between a person and the off switch.
ALWAYS = re.compile(r"^(M104 S0|M140 S0|M107|M108|M410|M25)$")


# This dialect, as a board's ``PrinterInfo`` names it, and the kind of machine it
# drives (apothecary/jobs.py's machine kinds, models.MACHINE_OF).
DIALECT = MARLIN
MACHINE = MACHINE_OF[DIALECT]


class OutOfBounds(ValueError):
    """A control line the dialect knows, asking for more than its bound allows: a
    hotend target, a move, a feed, a spindle speed. Distinct from a line it does not
    know, for a port not yet identified (devices.normalise_control)."""


def normalise_control(command: str) -> str:
    """Upper-cased, single-spaced control line; ValueError if not allowed,
    ``OutOfBounds`` if allowed but over a bound."""
    cmd = " ".join(command.strip().upper().split())
    if cmd == EMERGENCY_STOP:
        return cmd
    for pattern, _ in CONTROL_CODES:
        m = pattern.match(cmd)
        if not m:
            continue
        if cmd.startswith("M104") and int(m.group(1)) > HOTEND_MAX_C:
            raise OutOfBounds(f"hotend target above {HOTEND_MAX_C} degC: {command!r}")
        if cmd.startswith("M140") and int(m.group(1)) > BED_MAX_C:
            raise OutOfBounds(f"bed target above {BED_MAX_C} degC: {command!r}")
        if cmd.startswith("M106") and m.group(1) and int(m.group(1)) > 255:
            raise OutOfBounds(f"fan speed above 255: {command!r}")
        if cmd.startswith(("M301", "M304")):
            for name, figure in zip("PID", m.groups(), strict=True):
                if not GAIN_FIGURE.match(figure):
                    raise ValueError(
                        f"{name} is a plain decimal of four places at most: {command!r}"
                    )
                if float(figure) > GAIN_MAX[name]:
                    raise OutOfBounds(f"{name} above {GAIN_MAX[name]:g}: {command!r}")
            return cmd
        if cmd.startswith("G1 E"):
            if abs(float(re.search(r" E(-?\d+(?:\.\d+)?)", cmd).group(1))) > EXTRUDE_MAX_MM:
                raise OutOfBounds(f"extrusion beyond {EXTRUDE_MAX_MM} mm: {command!r}")
            if int(re.search(r" F(\d+)", cmd).group(1)) > EXTRUDE_FEED_MAX:
                raise OutOfBounds(f"extrusion feedrate above {EXTRUDE_FEED_MAX}: {command!r}")
            return cmd
        if cmd[0] == "G" and cmd[1] in "01":
            for axis_val in re.findall(r" [XYZ](-?\d+(?:\.\d+)?)", cmd):
                if abs(float(axis_val)) > JOG_MAX_MM:
                    raise OutOfBounds(f"move beyond {JOG_MAX_MM} mm: {command!r}")
            feed = re.search(r" F(\d+)", cmd)
            if feed and int(feed.group(1)) > FEED_MAX:
                raise OutOfBounds(f"feedrate above {FEED_MAX}: {command!r}")
        return cmd
    raise ValueError(f"not an allowed control code: {command!r}")


# What a person may still send while a print holds the port: the heaters, the fan
# and the break-wait (a hotend a few degrees off is fixed mid-print); motion and the
# SD card are the print's.
JOB_ALLOWS = re.compile(r"^(M104|M140|M106|M107|M108)\b")


# --- heater loops: the gains a board holds, its autotune, and saving -----------------------
#
# What is established in this tree: M503 is report-only and answers with the board's
# settings as G-code lines, M301 and M304 among them (docs/bench-checklist.md keeps them
# from it), as it prints a mesh as `G29 W` lines; M500 saves settings to the board's
# memory (PRINT_REFUSED). What is ASSUMED, from Marlin's documentation as recalled and not
# from its source or a board, and to be confirmed at the bench by keeping the lines a real
# board says: that M301/M304 take P, I and D with I per second and D in seconds; that
# M303 is `M303 E<n> S<target> C<cycles>` with E-1 for the bed; the words of its result
# (`Kp:`, `Ki:`, `Kd:`, `Ku:`, `Tu:`, `#define DEFAULT_Kp`, `PID Autotune finished`,
# `PID Autotune failed`); that it reports temperatures as it runs; and that M108 ends it.
# The parsers below read any of the forms named and nothing more.

AUTOTUNE_CYCLES = (3, 15)  # the fewest and most cycles the seam asks for
AUTOTUNE_RE = re.compile(r"^M303 E(-1|[0-7]) S(\d{1,3}) C(\d{1,2})$")
SAVE_SETTINGS = "M500"  # the board's memory written: never a control line, asked for by name


def normalise_autotune(command: str) -> str:
    """An autotune line, bounded: ValueError when it is not one, ``OutOfBounds`` for a
    target over the heater's cap or a cycle count outside ``AUTOTUNE_CYCLES``. It is not a
    control line: only the tuning job sends it, and it is watched while it runs."""
    cmd = " ".join(command.strip().upper().split())
    m = AUTOTUNE_RE.match(cmd)
    if not m:
        raise ValueError(f"not an autotune line (M303 E<n> S<target> C<cycles>): {command!r}")
    cap = BED_MAX_C if m.group(1) == "-1" else HOTEND_MAX_C
    if int(m.group(2)) > cap:
        raise OutOfBounds(f"autotune target above {cap} degC: {command!r}")
    lo, hi = AUTOTUNE_CYCLES
    if not lo <= int(m.group(3)) <= hi:
        raise OutOfBounds(f"autotune cycles outside {lo} to {hi}: {command!r}")
    return cmd


# `M301 P22.20 I1.08 D114.00` as M503 prints it (`M301 E0 P..` with several hotends), and
# `p:22.20 i:1.08 d:114.00` as M301 asked with no arguments may answer: both assumed.
GAINS_LINE_RE = re.compile(
    r"\b(M301|M304)(?:\s+E(\d))?\s+P(-?\d+(?:\.\d+)?)\s+I(-?\d+(?:\.\d+)?)\s+D(-?\d+(?:\.\d+)?)"
)
GAINS_REPORT_RE = re.compile(
    r"\bp:\s*(-?\d+(?:\.\d+)?)\s+i:\s*(-?\d+(?:\.\d+)?)\s+d:\s*(-?\d+(?:\.\d+)?)"
)
AUTOTUNE_VALUE_RE = re.compile(
    r"(?:#define\s+DEFAULT_(?:bed)?|\b)(Kp|Ki|Kd|Ku|Tu)\b:?\s*(-?\d+(?:\.\d+)?)"
)
AUTOTUNE_FAILED_RE = re.compile(r"PID Autotune failed!?\s*(.*)$", re.I)
AUTOTUNE_DONE_RE = re.compile(r"PID Autotune finished", re.I)


def parse_gains(lines: List[str]) -> Dict[str, dict]:
    """The PID gains in a board's answer, by loop: ``{"hotend 0": {"kp", "ki", "kd",
    "line"}, "bed": {...}}``. A line that names neither is left alone."""
    found: Dict[str, dict] = {}
    for line in lines:
        m = GAINS_LINE_RE.search(line)
        if not m:
            continue
        name = "bed" if m.group(1) == "M304" else f"hotend {int(m.group(2) or 0)}"
        found[name] = {
            "kp": float(m.group(3)),
            "ki": float(m.group(4)),
            "kd": float(m.group(5)),
            "line": line.strip(),
        }
    return found


def parse_gains_report(lines: List[str]) -> Optional[dict]:
    """The ``p: i: d:`` form one loop's report may take; None when there is none."""
    for line in lines:
        m = GAINS_REPORT_RE.search(line)
        if m:
            return {
                "kp": float(m.group(1)),
                "ki": float(m.group(2)),
                "kd": float(m.group(3)),
                "line": line.strip(),
            }
    return None


def parse_autotune(lines: List[str]) -> dict:
    """What an autotune said: its last ``Kp``, ``Ki``, ``Kd`` (and ``Ku``, ``Tu`` where it
    said them), whether it said it finished, why it failed when it said so, and the
    temperature lines among its words, as ``parse_m105`` reads them."""
    values: Dict[str, float] = {}
    failed: Optional[str] = None
    finished = False
    temperatures: List[dict] = []
    for line in lines:
        f = AUTOTUNE_FAILED_RE.search(line)
        if f:
            failed = f.group(1).strip() or "the firmware said it failed"
            continue
        if AUTOTUNE_DONE_RE.search(line):
            finished = True
        for name, value in AUTOTUNE_VALUE_RE.findall(line):
            values[name.lower()] = float(value)
        if is_temperature_line(line):
            temperatures.append(parse_m105(line))
    return {"values": values, "finished": finished, "failed": failed, "temperatures": temperatures}


# --- bed leveling: reading Marlin's mesh -------------------------------------------------

GRID_HEADER_RE = re.compile(r"^\s*(\d+(?:\s+\d+)+)\s*$")
GRID_ROW_RE = re.compile(r"^\s*(\d+)((?:\s+[-+]?\d+\.\d+)+)\s*$")
G29_POINT_RE = re.compile(r"G29 W I(\d+) J(\d+) Z([-+]?\d+\.\d+)")
PROBE_OFFSET_RE = re.compile(r"M851 X([-+]?\d+\.?\d*) Y([-+]?\d+\.?\d*) Z([-+]?\d+\.?\d*)")
# A point the probe touched, as Marlin says it at G29's verbosity 3 or more (probe.cpp):
# where the probe stood, in bed coordinates, and the height it read.
PROBED_POINT_RE = re.compile(
    r"Bed X:\s*([-+]?\d+(?:\.\d+)?)\s+Y:\s*([-+]?\d+(?:\.\d+)?)\s+Z:\s*([-+]?\d+(?:\.\d+)?)"
)
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


def parse_probed_points(lines: List[str]) -> List[List[float]]:
    """Each point a probe said it touched, in the order said: x and y where the probe
    stood, in bed coordinates, and the height it read."""
    found = (PROBED_POINT_RE.search(line) for line in lines)
    return [[float(m.group(1)), float(m.group(2)), float(m.group(3))] for m in found if m]


def probed_area(points: List[List[float]], mesh: List[List[float]]) -> Optional[dict]:
    """Where ``mesh``'s first and last points lie, from the points its probe said it
    touched: min and max x and y, in the form a router's map keeps (``BedReading.area``).
    None unless the points are the grid's: as many places along X as it has columns and
    along Y as it has rows, each point at one of each."""
    if not points or not mesh or not mesh[0]:
        return None
    xs = sorted({round(p[0], 1) for p in points})
    ys = sorted({round(p[1], 1) for p in points})
    if len(xs) != len(mesh[0]) or len(ys) != len(mesh) or len(points) != len(xs) * len(ys):
        return None
    return {"min": {"x": xs[0], "y": ys[0]}, "max": {"x": xs[-1], "y": ys[-1]}}


def parse_leveling_state(lines: List[str]) -> Optional[bool]:
    for line in lines:
        m = LEVELING_STATE_RE.search(line)
        if m:
            return m.group(1) == "ON"
    return None


# The stored mesh's line: what Read mesh asks for, and what a board without one (a
# GRBL controller) cannot be asked.
STORED_MESH = "M420 V"
# The probe: Marlin's G29 at verbosity 3, which says where each point lies as it probes
# it (`Bed X: .. Y: .. Z: ..`); a plain G29 prints the grid without its positions.
PROBE_BED = "G29 V3"
LEVELING_PROBE_TIMEOUT_S = 900.0  # a five-by-five probe on a slow bed


def read_bed(
    link: GcodeLink,
    *,
    probe: bool = True,
    grid=None,
    stage: Callable[..., None] = lambda word, points=None: None,
) -> BedReading:
    """A printer's bed reading, Marlin's: with ``probe``, home (``G28``) and probe
    (``G29 V3``) first; then the stored mesh (``M420 V``), the probe offset (``M851``)
    and the temperatures (``M105``). ``stage`` is told each step as it starts;
    ``grid`` is a router's and means nothing here, the mesh being the firmware's.
    A probe keeps the points it said it touched, and where they say the grid lies
    (``probed_area``); a read of the stored mesh has neither.
    This dialect's ``Dialect.bed_reading``; the router's is ``grbl.probe_table``."""
    lines: List[str] = []
    probed: List[List[float]] = []
    if probe:
        stage("homing")
        link.command("G28", timeout=120.0, origin="control")
        stage("probing")
        probe_lines = link.command(PROBE_BED, timeout=LEVELING_PROBE_TIMEOUT_S, origin="control")
        probed = parse_probed_points(probe_lines)
        lines += [line for line in probe_lines if not line.startswith("echo:busy")]
    stage("reading")
    mesh_lines = link.command(STORED_MESH, timeout=15.0, origin="query")
    lines += mesh_lines
    offset_lines = link.command("M851", timeout=10.0, origin="query")
    lines += offset_lines
    temp_lines = link.command("M105", timeout=10.0, origin="query")
    lines += temp_lines
    grids = parse_meshes(mesh_lines)
    temps = parse_m105(next((ln for ln in temp_lines if is_temperature_line(ln)), ""))
    mesh = grids[0] if grids else []
    return BedReading(
        method="probe" if probe else "read",
        mesh=mesh,
        subdivided=grids[1] if len(grids) > 1 else None,
        stats=mesh_stats(grids[0]) if grids else {},
        leveling_on=parse_leveling_state(mesh_lines),
        probe_offset=parse_probe_offset(offset_lines),
        hotend_c=temps["hotends"][0].actual if temps["hotends"] else None,
        bed_c=temps["bed"].actual if temps["bed"] else None,
        points=probed or None,
        area=probed_area(probed, mesh),
        lines=lines[-400:],
    )


# --- host printing: what a file may carry, and how long a line may take ----------------

# Codes a streamed file is refused for, whatever else it says: they write the
# board's settings or take it down, or wait for a hand, and neither a slicer nor
# a CAM post needs them. One list for every dialect: a Marlin file carries no
# `$` line and a GRBL file no M500, and refusing each in both costs nothing.
PRINT_REFUSED: Dict[str, str] = {
    "M500": "saves settings to EEPROM",
    "M303": "runs the firmware's autotune: a heater loop's experiment, watched as one (firmware/loops.py)",
    "M502": "resets settings to the firmware's defaults",
    "M997": "starts a firmware update",
    "M999": "restarts the board after a stop",
    "M112": "kills the board",
    "M0": "stops and waits for a button on the machine",
    "M1": "stops and waits for a button on the machine",
    "M6": "is a tool change: the host streams one tool",
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


# What a dialect objects to in a line of a file, beyond what every dialect refuses:
# (the line's number, the command, its code) -> the reasons, each naming its line.
Objections = Callable[[int, str, str], List[str]]


def check_file(text: str, objections: Objections) -> Tuple[int, List[str]]:
    """How many lines a file would send, and every reason it may not be sent: the
    codes no streamed file carries, a controller setting, and what the file's
    dialect objects to (``objections``: Marlin's are ``check_gcode``'s, GRBL's
    ``grbl.check_gcode``'s). A reason names its line. The bounds are a typed
    control's, applied once to the whole file rather than line by line as it
    streams; the check stops after twenty reasons."""
    total = 0
    problems: List[str] = []
    for n, raw in enumerate(text.splitlines(), 1):
        cmd = strip_gcode(raw)
        if not cmd:
            continue
        total += 1
        code = cmd.split(" ", 1)[0]
        if cmd.startswith("$"):
            problems.append(f"line {n}: {cmd[:12]} is a controller setting, not a job's to send")
        elif code in PRINT_REFUSED:
            problems.append(f"line {n}: {code} {PRINT_REFUSED[code]}")
        problems.extend(objections(n, cmd, code))
        if len(problems) >= 20:
            problems.append("... and the check stopped here")
            break
    return total, problems


def _objections(n: int, cmd: str, code: str) -> List[str]:
    """A temperature over the seam's caps, Marlin's one objection to a line."""
    if code in TEMP_CODES:
        m = TEMP_ARG_RE.search(cmd[len(code) :])
        if m and float(m.group(1)) > TEMP_CODES[code]:
            return [f"line {n}: {code} asks for {m.group(1)} degC, above {TEMP_CODES[code]}"]
    return []


def check_gcode(text: str) -> Tuple[int, List[str]]:
    """A printer's file, checked in Marlin's terms (``check_file``): what every
    dialect refuses, and a temperature over the caps."""
    return check_file(text, _objections)


CONTROL_TTL_S = 300.0  # a latch that nobody touches for this long disarms itself


class ControlLatch:
    """Per-port arm state: control commands go through only while armed.

    Arming is an explicit act with a lifetime; every accepted command
    renews it, silence lets it lapse, and a stop disarms it
    (``devices.printer_control``). It exists so the control overlay of a
    printer's Machine cannot heat or move a machine from a stray click.
    Its lifetime runs on the monotonic clock, so a step of the wall clock (NTP,
    a suspend) neither ends an armed window nor lengthens one.
    """

    def __init__(self):
        self._until: Dict[str, float] = {}
        self._lock = threading.Lock()

    # Each asks the port list first (_read_port_list), outside the lock: a port that
    # has changed hands disarms itself there (PrinterLinks.forget).
    def arm(self, port: str, ttl: float = CONTROL_TTL_S) -> float:
        _read_port_list()
        with self._lock:
            self._until[port] = time.monotonic() + ttl
            return self._until[port]

    def disarm(self, port: str) -> None:
        with self._lock:
            self._until.pop(port, None)

    def armed(self, port: str) -> bool:
        _read_port_list()
        with self._lock:
            until = self._until.get(port)
            if until is None:
                return False
            if until <= time.monotonic():
                del self._until[port]
                return False
            return True

    def seconds_left(self, port: str) -> float:
        _read_port_list()
        with self._lock:
            until = self._until.get(port)
            return max(0.0, until - time.monotonic()) if until else 0.0

    def renew(self, port: str, ttl: float = CONTROL_TTL_S) -> None:
        if self.armed(port):
            self.arm(port, ttl)

    def armed_ports(self) -> Dict[str, float]:
        """Every port armed now, and its seconds left; the lapsed ones are let go."""
        _read_port_list()
        with self._lock:
            now = time.monotonic()
            for port in [p for p, until in self._until.items() if until <= now]:
                del self._until[port]
            return {port: round(until - now, 1) for port, until in self._until.items()}


class LinkBusy(PortHeld):
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
    link: GcodeLink,
    endstops: bool = True,
    wait: Optional[float] = None,
    streaming: bool = False,
) -> PrinterStatus:
    """Temperatures, position, SD progress and (optionally) endstops in one exchange each.

    ``wait`` bounds each exchange's queueing behind a print's stream (see
    ``GcodeLink.command``); a poll between two streamed lines is how a host
    keeps its temperatures fresh mid-print. While a job streams (``streaming``) the
    poll does not ask for the card's progress: the host holds the port, so the card
    cannot be printing, and each exchange taken from the stream slows the print. The
    endstops are still asked for, because the runout sensor answers with them and a
    print is when filament runs out.
    """
    raw: List[str] = []
    temps = link.command("M105", wait=wait)
    raw += temps
    temp_line = next((ln for ln in temps if is_temperature_line(ln)), "")
    parsed = parse_m105(temp_line)
    pos_lines = link.command("M114", wait=wait)
    raw += pos_lines
    sd = {"sd_printing": False, "sd_progress": None}
    if not streaming:
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
    """Send one allowlisted control line (homing can take a while; ``busy`` extends the
    wait). The emergency stop is written at once, ahead of the link's queue, and so
    are the break of a heat-and-wait and the quickstop (``AHEAD``): each is for a
    board that is busy with the line before it."""
    cmd = normalise_control(command)
    if cmd == EMERGENCY_STOP:
        return link.emergency_stop()
    if cmd in AHEAD:
        return link.ahead(cmd, timeout=timeout)
    return link.command(cmd, timeout=timeout, origin="control")


def query_printer(link: GcodeLink, command: str, timeout: float = 15.0) -> List[str]:
    """Send one allowlisted query and return its reply lines (``M503`` can run long)."""
    return link.command(normalise_query(command), timeout=timeout, origin="query")


def offline_status(port: str, reason: str) -> PrinterStatus:
    return PrinterStatus(
        port=port, polled_at=datetime.now(timezone.utc), state="offline", raw=[reason]
    )
