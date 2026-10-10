"""Finding ports and listening to a board, for a toolchain module that does so itself.

The Rust module needs no arduino-cli (the owner's decision of 2026-10-10): it
finds ports and listens to a devkit through **pyserial**, the transport the
G-code seam already uses, behind the same engine slot
(``gcode.serial_engine()``):

- **Finding** is pyserial's ``list_ports``: the operating system's own list of
  serial devices, with each one's USB VID, PID and serial number. Nothing is
  opened to make it.
- **Listening** is this module run as a process of its own
  (``python -m apothecary.firmware.serial_monitor PORT BAUD``), as
  arduino-cli's monitor is: it opens the port once, exclusively, and writes
  what the board says to its standard output until it is stopped -- so the
  server reads it, paces it and stops it exactly as it does arduino-cli's
  monitor, and one holder per port stays the rule. DTR and RTS are held
  de-asserted before the port is opened, so on an ESP32 devkit, whose
  auto-reset hangs off them, listening does not reset the board.

Why pyserial and not espflash's monitor: it is already a dependency and the
transport the seam holds ports with; it lists ports without opening any;
it opens one without pulling the board into reset, where espflash's monitor
resets the board when it starts and draws a terminal to be parsed; and it is
the same on every platform the server runs on. espflash still identifies a
chip (``espflash board-info``, the Rust module's Probe): only a flasher speaks
the ROM bootloader.

With ``APOTHECARY_SERIAL_ENGINE=simulated`` (demos and the browser suites) no
port is touched: the ports listed are the ones ``APOTHECARY_SIMULATED_DEVKIT``
names, each a pretend ESP32 devkit on a CP2102 bridge, and listening to one
hears the hello of the sketch Apothecary last flashed to it (its flash
record), as esp32_blink says it, ten times faster.
"""

from __future__ import annotations

import os
import sys
import time
from typing import List, Optional

from .models import BoardInfo

SIMULATED_DEVKIT_ENV = "APOTHECARY_SIMULATED_DEVKIT"
SIMULATED_VID, SIMULATED_PID = "0x10c4", "0xea60"  # a CP2102, as the bench's devkit has


def _engine() -> str:
    from .gcode import serial_engine

    return serial_engine()


def simulated_ports() -> List[str]:
    raw = os.environ.get(SIMULATED_DEVKIT_ENV, "")
    return [p.strip() for p in raw.split(",") if p.strip()]


def list_ports() -> List[BoardInfo]:
    """The serial ports the engine sees, none of them opened."""
    if _engine() == "simulated":
        return [
            BoardInfo(
                port=port,
                label=port,
                vid=SIMULATED_VID,
                pid=SIMULATED_PID,
                serial_number=f"SIMDEVKIT{i}",
            )
            for i, port in enumerate(simulated_ports())
        ]
    from serial.tools import list_ports as pyserial_ports

    found = []
    for p in pyserial_ports.comports():
        if p.vid is None and p.pid is None and not p.serial_number:
            continue  # a motherboard's own UART, nobody's board
        found.append(
            BoardInfo(
                port=p.device,
                label=p.device,
                vid=f"0x{p.vid:04x}" if p.vid is not None else None,
                pid=f"0x{p.pid:04x}" if p.pid is not None else None,
                serial_number=p.serial_number or None,
            )
        )
    return sorted(found, key=lambda b: b.port)


class SimulatedDevkit:
    """A pretend ESP32 devkit: it runs what Apothecary last flashed to its port."""

    def __init__(self, port: str, baud: int):
        self.port, self.baud = port, baud
        self.sketch = self._flashed()
        self.started = time.monotonic()
        self.beats = 0
        self.pending = b"\r\n" + (self.hello() if self.sketch else b"ets Jun  8 2016 00:22:57\r\n")

    def _flashed(self) -> Optional[str]:
        from .devices import get_state

        record = get_state().last_flash(self.port, self.port)
        return record.sketch if record else None

    def hello(self) -> bytes:
        return (
            f"apothecary {self.sketch}: hello\r\n"
            "chip: ESP32-D0WD-V3 rev 301, 2 core(s), 240 MHz, LED on GPIO 2\r\n"
        ).encode()

    def read(self, timeout: float) -> bytes:
        if self.pending:
            out, self.pending = self.pending, b""
            return out
        time.sleep(min(timeout, 0.1))  # a blink each tenth of a second
        if not self.sketch:
            return b""
        self.beats += 1
        out = f"blink {self.beats}\r\n".encode()
        if self.beats % 10 == 0:
            out += self.hello()
        return out

    def close(self) -> None:
        pass


class PySerialDevkit:
    """A devkit's port, opened once and exclusively, DTR and RTS held de-asserted."""

    def __init__(self, port: str, baud: int):
        import serial

        from .gcode import hold_exclusively, keep_dtr_on_close
        from .toolchains import PortHeld, ToolchainError

        s = serial.Serial()
        s.port, s.baudrate, s.timeout, s.exclusive = port, baud, 0.5, True
        s.dtr = False  # set before open: an ESP32's auto-reset is not pulled
        s.rts = False
        try:
            s.open()
        except (serial.SerialException, OSError) as exc:
            if "busy" in str(exc).lower() or "lock" in str(exc).lower():
                raise PortHeld(f"{port} is held by another program") from exc
            raise ToolchainError(f"cannot open {port}: {exc}") from exc
        hold_exclusively(getattr(s, "fd", None))
        keep_dtr_on_close(getattr(s, "fd", None))
        self._s = s

    def read(self, timeout: float) -> bytes:
        self._s.timeout = timeout
        first = self._s.read(1)
        if not first:
            return b""
        return first + self._s.read(self._s.in_waiting)

    def close(self) -> None:
        try:
            self._s.close()
        except Exception:  # noqa: BLE001 -- a vanished USB device raises whatever the OS likes
            pass


def open_devkit(port: str, baud: int):
    return SimulatedDevkit(port, baud) if _engine() == "simulated" else PySerialDevkit(port, baud)


def monitor_argv(port: str, baud: int) -> List[str]:
    """This module as a process of its own, listening to ``port``."""
    return [sys.executable, "-m", "apothecary.firmware.serial_monitor", port, str(baud)]


def main(argv: Optional[List[str]] = None) -> int:
    """Write what the board on PORT says to standard output until stopped."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: python -m apothecary.firmware.serial_monitor PORT BAUD", file=sys.stderr)
        return 2
    from .models import validate_port

    port, baud = validate_port(args[0]), int(args[1])
    try:
        link = open_devkit(port, baud)
    except Exception as exc:  # noqa: BLE001 -- said, then the monitor ends as arduino-cli's would
        print(f"[apothecary: {exc}]", flush=True)
        return 1
    out = sys.stdout.buffer
    try:
        while True:
            data = link.read(0.5)
            if data:
                out.write(data)
                out.flush()
    except (KeyboardInterrupt, BrokenPipeError):
        return 0
    except Exception as exc:  # noqa: BLE001 -- the port went (unplugged): say so and end
        print(f"[apothecary: {exc}]", flush=True)
        return 1
    finally:
        link.close()


if __name__ == "__main__":  # pragma: no cover - the listening process
    sys.exit(main())
