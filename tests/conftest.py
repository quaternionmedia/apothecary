import sys
from pathlib import Path

# Ensure repository root is on sys.path so `import apothecary` works
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# --- firmware toolchain fakes ---------------------------------------------------
#
# A stand-in `arduino-cli` executable that answers the JSON queries the seam
# makes and records every long-running invocation, so firmware tests never
# need (or touch) a real toolchain, ~/.arduino15, or a serial port.


import pytest  # noqa: E402
from firmware_helpers import write_fake_arduino_cli  # noqa: E402


@pytest.fixture
def fake_arduino_cli(tmp_path, monkeypatch):
    """Point the firmware seam at a scripted arduino-cli; yields the script path."""
    script = write_fake_arduino_cli(tmp_path / "arduino-cli")
    monkeypatch.setenv("ARDUINO_CLI", str(script))
    monkeypatch.setenv("APOTHECARY_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    from apothecary.firmware import toolchains

    # A host with the esp32 core installed has a bundled esptool under
    # ~/.arduino15; tests must not see it.
    monkeypatch.setattr(toolchains.Esptool, "detect", staticmethod(lambda: None))
    toolchains.reset_toolchains()
    _isolate_firmware_state(monkeypatch, tmp_path)
    yield script
    from apothecary.firmware import devices as _devices

    _devices.get_streams().stop_all()
    toolchains.reset_toolchains()


def _isolate_firmware_state(monkeypatch, tmp_path):
    """Flash records / cached probes go to a per-test file, never ~/.apothecary."""
    from apothecary.firmware import devices

    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(devices, "_STATE", None)
    monkeypatch.setattr(devices, "_STREAMS", None)
    monkeypatch.setattr(devices, "_SCAN", None)  # the 2 s port-scan cache must not span tests
    monkeypatch.setattr(devices, "_LAST_STATUS", {})


@pytest.fixture
def no_arduino_cli(tmp_path, monkeypatch):
    """The other environment: nothing installed anywhere."""
    monkeypatch.delenv("ARDUINO_CLI", raising=False)
    monkeypatch.setenv("APOTHECARY_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    from apothecary.firmware import toolchains

    monkeypatch.setattr(toolchains.Esptool, "detect", staticmethod(lambda: None))
    toolchains.reset_toolchains()
    _isolate_firmware_state(monkeypatch, tmp_path)
    yield
    toolchains.reset_toolchains()


@pytest.fixture
def fresh_task_runner(monkeypatch):
    from apothecary.firmware import tasks

    runner = tasks.TaskRunner()
    monkeypatch.setattr(tasks, "_RUNNER", runner)
    return runner
