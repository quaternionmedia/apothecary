"""Helpers the firmware tests import directly.

Kept out of ``conftest.py`` on purpose: ``from conftest import ...`` resolves
to whichever conftest pytest imported first (``tests/e2e/conftest.py`` in a
full run), so it is not a stable module to import from.

The scripted arduino-cli, cargo and espflash are the package's
(``apothecary/firmware/scripted.py``), since ``apothecary serve --simulated`` runs
them too; they are imported here under the names the tests know them by.
"""

import json
import time

from apothecary.firmware.scripted import (  # noqa: F401  -- the tests' names for them
    FAKE_ARDUINO_CLI,
    FAKE_BOARD,
    FAKE_CARGO,
    FAKE_ESPFLASH,
    write_fake_arduino_cli,
    write_fake_cargo,
    write_fake_espflash,
)


def _isolate_firmware_state(monkeypatch, tmp_path):
    """Flash records / cached probes go to a per-test file, never ~/.apothecary."""
    from apothecary import jobs
    from apothecary.evidence import printers as evidence_printers
    from apothecary.firmware import devices

    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(devices, "_STATE", None)
    monkeypatch.setattr(devices, "_STREAMS", None)
    monkeypatch.setattr(devices, "_SCAN", None)  # the 2 s port-scan cache must not span tests
    monkeypatch.setattr(devices, "_PORTS", None)  # the port list's half-second reading
    monkeypatch.setattr(devices, "_HELD_BY", {})  # and what it last found on each port
    monkeypatch.setattr(devices, "_LAST_STATUS", {})
    monkeypatch.setattr(devices, "_LEVELING", {})  # a bed reading's job is per process
    monkeypatch.setattr(devices, "_PRINTS", {})
    monkeypatch.setattr(jobs, "_LIVE", {})  # a running job is read from its thread, per process
    # What the evidence log last wrote is per state folder: a new folder hears it all again.
    monkeypatch.setattr(evidence_printers, "COLLECTOR", evidence_printers.Collector())


def fake_cli_calls(script) -> list[list[str]]:
    """Every argv the fake arduino-cli script was invoked with, in order."""
    log = script.with_name(script.name + ".calls")
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


# A recording of a Creality mainboard running Marlin (TH3D UFW 2.94a), replayed.
BOOT = [
    "start",
    " External Reset",
    "Marlin TH3D UFW 2.94a",
    "echo: Last Updated: 2024-12-05 | Author: TH3D Studio",
    "echo: Compiled: Jan 17 2025",
    "echo: Free Memory: 1289  PlannerBufferBytes: 1200",
    "echo:V88 stored settings retrieved (702 bytes; crc 8322)",
]

REPLIES = {
    "M115": [
        "echo:SD card ok",
        "FIRMWARE_NAME:Marlin TH3D UFW 2.94a (Jan 17 2025 11:35:34) SOURCE_CODE_URL:TH3DStudio.com "
        "PROTOCOL_VERSION:1.0 MACHINE_TYPE:TH3D EZABL EXTRUDER_COUNT:1 "
        "UUID:cede2a2f-41a2-4748-9b12-c55c62f367ff",
        "ok",
    ],
    "M105": ["ok T:22.30 /0.00 B:23.59 /0.00 @:0 B@:0"],
    "M114": ["X:0.00 Y:0.00 Z:0.00 E:0.00 Count X:0 Y:0 Z:0", "ok"],
    "M119": [
        "Reporting endstop status",
        "x_min: open",
        "y_min: TRIGGERED",
        "z_min: open",
        "filament: TRIGGERED",
        "ok",
    ],
    "M27": ["Not SD printing", "ok"],
    "M31": ["echo:Print time: 0s", "ok"],
}

PRINTING = {
    **REPLIES,
    "M105": ["ok T:209.8 /210.00 B:60.02 /60.00 @:78 B@:12"],
    "M114": ["X:110.25 Y:98.40 Z:3.60 E:412.10 Count X:8820 Y:7872 Z:1440", "ok"],
    "M27": ["SD printing byte 152673/358856", "ok"],
    "M31": ["echo:Print time: 1h 2m 3s", "ok"],
}


class ScriptedTransport:
    """Answers each command from a table; prints the boot banner when reset is pulsed.

    ``boot_on_open`` mimics a previous holder having dropped DTR, so the open
    itself reboots the board.
    """

    instances = []

    def __init__(self, port, baud, replies=None, boot=BOOT, boot_on_open=False):
        self.port, self.baud = port, baud
        self.replies = replies or REPLIES
        self.boot = boot
        self.pending = "".join(ln + "\n" for ln in boot).encode() if boot_on_open else b""
        self.sent = []
        self.resets = 0
        self.closed = False
        ScriptedTransport.instances.append(self)

    def pulse_reset(self):
        self.resets += 1
        self.pending += "".join(ln + "\n" for ln in self.boot).encode()

    def write(self, data):
        cmd = data.decode().strip()
        self.sent.append(cmd)
        reply = self.replies.get(cmd)
        if reply is None:
            reply = [f'echo:Unknown command: "{cmd}"', "ok"]
        self.pending += "".join(ln + "\n" for ln in reply).encode()

    def read(self, timeout):
        if not self.pending:
            time.sleep(min(timeout, 0.01))
            return b""
        out, self.pending = self.pending[:64], self.pending[64:]
        return out

    def close(self):
        self.closed = True


def held_until_asked_for(gate, held, longest=5.0):
    """Hold a line on the wire -- a transport's ``write`` that has not returned -- until
    ``gate`` opens, until anything else asks for the link, or ``longest`` seconds at
    most. Asking is an exchange waiting its turn for the link, or anything the comms log
    gains while the line is held: a line written ahead of the exchange (``ahead``, the
    stop) logs itself before it waits to be written. So a route that needs the wire gets
    it as soon as it asks, as it would once the hold ran out, and one that refuses first
    finds the line still held. ``held["link"]`` is the link the line is on, set by whoever
    started what writes it."""
    end, mark = time.monotonic() + longest, None
    while not gate.wait(0.005) and time.monotonic() < end:
        link = held.get("link")
        if link is None:
            continue
        if mark is None:
            mark = link.log.next_index
        if link._turn.locked() or link.waiters or link.log.next_index > mark:
            return
