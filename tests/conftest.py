import sys
from pathlib import Path

# Ensure repository root is on sys.path so `import apothecary` works
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# Registered here rather than in tests/e2e/conftest.py, where these options were
# first defined. pytest loads a conftest for the paths named on the command line
# before it parses the arguments, so an option defined one directory further down
# than any named path does not exist yet when the parser meets it: the ordinary
# test command names `tests/` and `walkthrough`, and died on its own
# --start-server with "unrecognized arguments". Options live at the top; the
# fixtures that read them stay where they are used.
def pytest_addoption(parser):
    """Add custom pytest options for E2E tests."""
    parser.addoption(
        "--start-server",
        action="store_true",
        default=False,
        help="Automatically start the test server before E2E tests",
    )
    parser.addoption(
        "--server-port",
        action="store",
        default="8765",
        help="Port for the test server (default: 8765)",
    )
    parser.addoption(
        "--generate-docs",
        action="store_true",
        default=False,
        help=(
            "Enable doc-workflow screenshot/video capture (tests marked 'docs'). "
            "Off by default so a normal test run never writes to docs/generated/. "
            "Driven by `apothecary docs generate`, not meant to be passed by hand "
            "to a full test run."
        ),
    )
# --- firmware toolchain fakes ---------------------------------------------------
#
# A stand-in `arduino-cli` executable that answers the JSON queries the seam
# makes and records every long-running invocation, so firmware tests never
# need (or touch) a real toolchain, ~/.arduino15, or a serial port.

import json  # noqa: E402
import stat  # noqa: E402
import textwrap  # noqa: E402

import pytest  # noqa: E402

FAKE_ARDUINO_CLI = textwrap.dedent(r"""
    #!/usr/bin/env python3
    import json, os, sys
    args = sys.argv[1:]
    if "--config-file" in args:
        i = args.index("--config-file"); del args[i:i + 2]
    with open(__file__ + ".calls", "a") as f:
        f.write(json.dumps(args) + "\n")
    cmd = " ".join(args[:2])
    if cmd == "version --json":
        print(json.dumps({"Application": "arduino-cli", "VersionString": "9.9.9"}))
    elif cmd == "config dump":
        print("{}")
    elif cmd == "board list":
        print(json.dumps({"detected_ports": [
            {"port": {"address": "/dev/ttyFAKE0", "label": "/dev/ttyFAKE0", "protocol": "serial",
                      "properties": {"vid": "0x2341", "pid": "0x0043"}},
             "matching_boards": [{"name": "Arduino Uno", "fqbn": "arduino:avr:uno"}]},
            {"port": {"address": "/dev/ttyFAKE1", "protocol": "serial"}}]}))
    elif cmd == "board listall":
        print(json.dumps({"boards": [{"name": "Arduino Uno", "fqbn": "arduino:avr:uno"},
                                     {"name": "Arduino Nano", "fqbn": "arduino:avr:nano"}]}))
    elif cmd == "core list":
        print(json.dumps({"platforms": [
            {"id": "arduino:avr", "installed_version": "1.8.8", "latest_version": "1.8.8",
             "releases": {"1.8.8": {"name": "Arduino AVR Boards"}}}]}))
    elif "flash_id" in args or "chip_id" in args:  # standing in for esptool
        print("Chip type:          ESP32-D0WD-V3 (revision v3.1)")
        print("Features:           Wi-Fi, BT, Dual Core, 240MHz")
        print("Crystal frequency:  40MHz")
        print("MAC:                aa:bb:cc:dd:ee:ff")
        print("Detected flash size: 4MB")
        print("Manufacturer: c4")
        print("Hard resetting via RTS pin...")
    elif args[0] == "monitor":
        import time
        script = ["blink 1", "apothecary fake_blink: hello", "chip: FAKE-CHIP rev 1, 1 core(s)"]
        if "REPLAY" in os.environ.get("FAKE_MONITOR", ""):
            script = ["junk"] * 3000  # far more than the wire could carry
        for line in script:
            print(line, flush=True)
        n = 1
        while True:  # runs until the caller terminates us, like the real monitor
            time.sleep(0.1); n += 1
            print(f"blink {n}", flush=True)
    elif args[0] in ("compile", "upload", "lib", "core", "config"):
        print("fake " + " ".join(args))
        if "FAIL" in " ".join(args):
            print("Error during build", file=sys.stderr); sys.exit(1)
    else:
        print("unknown: " + " ".join(args), file=sys.stderr); sys.exit(2)
    """).lstrip()


@pytest.fixture
def fake_arduino_cli(tmp_path, monkeypatch):
    """Point the firmware seam at a scripted arduino-cli; yields the script path."""
    script = tmp_path / "arduino-cli"
    script.write_text(
        FAKE_ARDUINO_CLI.replace("#!/usr/bin/env python3", f"#!{sys.executable}", 1),
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
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


def fake_cli_calls(script) -> list[list[str]]:
    log = script.with_name(script.name + ".calls")
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


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
