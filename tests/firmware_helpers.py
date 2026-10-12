"""Helpers the firmware tests import directly.

Kept out of ``conftest.py`` on purpose: ``from conftest import ...`` resolves
to whichever conftest pytest imported first (``tests/e2e/conftest.py`` in a
full run), so it is not a stable module to import from.

The scripted arduino-cli, cargo and espflash are the package's
(``apothecary/firmware/scripted.py``), since ``apothecary serve --demo`` runs
them too; they are imported here under the names the tests know them by.
"""

import json

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
    from apothecary.firmware import devices

    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(devices, "_STATE", None)
    monkeypatch.setattr(devices, "_STREAMS", None)
    monkeypatch.setattr(devices, "_SCAN", None)  # the 2 s port-scan cache must not span tests
    monkeypatch.setattr(devices, "_LAST_STATUS", {})
    monkeypatch.setattr(devices, "_LEVELING", {})  # a bed reading's job is per process
    monkeypatch.setattr(devices, "_PRINTS", {})
    monkeypatch.setattr(jobs, "_LIVE", {})  # a running job is read from its thread, per process


def fake_cli_calls(script) -> list[list[str]]:
    """Every argv the fake arduino-cli script was invoked with, in order."""
    log = script.with_name(script.name + ".calls")
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
