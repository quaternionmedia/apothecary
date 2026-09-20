"""Helpers the firmware tests import directly.

Kept out of ``conftest.py`` on purpose: ``from conftest import ...`` resolves
to whichever conftest pytest imported first (``tests/e2e/conftest.py`` in a
full run), so it is not a stable module to import from.
"""

import json
import stat
import sys
import textwrap
from pathlib import Path

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


def _isolate_firmware_state(monkeypatch, tmp_path):
    """Flash records / cached probes go to a per-test file, never ~/.apothecary."""
    from apothecary.firmware import devices

    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(devices, "_STATE", None)
    monkeypatch.setattr(devices, "_STREAMS", None)
    monkeypatch.setattr(devices, "_SCAN", None)  # the 2 s port-scan cache must not span tests
    monkeypatch.setattr(devices, "_LAST_STATUS", {})



def write_fake_arduino_cli(path: Path) -> Path:
    """Materialise the fake as an executable at ``path`` (using this interpreter)."""
    path.write_text(
        FAKE_ARDUINO_CLI.replace("#!/usr/bin/env python3", f"#!{sys.executable}", 1),
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def fake_cli_calls(script) -> list[list[str]]:
    """Every argv the fake arduino-cli script was invoked with, in order."""
    log = script.with_name(script.name + ".calls")
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
