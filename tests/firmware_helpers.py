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

# The simulated devkit, when FAKE_DEVKIT is set in the server's environment: an
# ESP32 devkit on /dev/ttyFAKE2 (a CP2102 bridge, which arduino-cli matches to no
# board) that runs what was last flashed to its port -- by the scripted
# arduino-cli's upload or the scripted espflash's flash -- and says that sketch's
# hello, as esp32_blink does, at boot and every ten blinks. Each fake keeps the
# flashes in fake-boards.json beside itself, so the fakes in one folder are one
# bench. Without FAKE_DEVKIT the monitor says fake_blink, whatever was flashed.
FAKE_BOARD = r"""
def _boards_file():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake-boards.json")

def _flashed():
    try:
        with open(_boards_file()) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}

def _flash(port, sketch):
    boards = _flashed()
    boards[port] = sketch
    with open(_boards_file(), "w") as f:
        json.dump(boards, f)
"""

FAKE_ARDUINO_CLI = textwrap.dedent(r"""
    #!/usr/bin/env python3
    import json, os, sys
    """ + textwrap.indent(FAKE_BOARD, "    ") + r"""
    args = sys.argv[1:]
    if "--config-file" in args:
        i = args.index("--config-file"); del args[i:i + 2]
    with open(__file__ + ".calls", "a") as f:
        f.write(json.dumps(args) + "\n")
    cmd = " ".join(args[:2])
    devkit = bool(os.environ.get("FAKE_DEVKIT"))
    port = args[args.index("--port") + 1] if "--port" in args else None
    if cmd == "version --json":
        print(json.dumps({"Application": "arduino-cli", "VersionString": "9.9.9"}))
    elif cmd == "board list":
        ports = [
            {"port": {"address": "/dev/ttyFAKE0", "label": "/dev/ttyFAKE0", "protocol": "serial",
                      "properties": {"vid": "0x2341", "pid": "0x0043"}},
             "matching_boards": [{"name": "Arduino Uno", "fqbn": "arduino:avr:uno"}]},
            {"port": {"address": "/dev/ttyFAKE1", "protocol": "serial",
                      "properties": {"serialNumber": "FAKESERIAL1"}}}]
        if devkit:
            ports.append({"port": {"address": "/dev/ttyFAKE2", "label": "/dev/ttyFAKE2",
                                   "protocol": "serial",
                                   "properties": {"vid": "0x10c4", "pid": "0xea60",
                                                  "serialNumber": "FAKEDEVKIT2"}}})
        print(json.dumps({"detected_ports": ports}))
    elif cmd == "board listall":
        print(json.dumps({"boards": [{"name": "Arduino Uno", "fqbn": "arduino:avr:uno"},
                                     {"name": "Arduino Nano", "fqbn": "arduino:avr:nano"}]}))
    elif cmd == "core list":
        print(json.dumps({"platforms": [
            {"id": "arduino:avr", "installed_version": "1.8.8", "latest_version": "1.8.8",
             "releases": {"1.8.8": {"name": "Arduino AVR Boards"}}}]}))
    elif "flash_id" in args:  # standing in for esptool
        print("Chip type:          ESP32-D0WD-V3 (revision v3.1)")
        print("Features:           Wi-Fi, BT, Dual Core, 240MHz")
        print("Crystal frequency:  40MHz")
        print("MAC:                aa:bb:cc:dd:ee:ff")
        print("Detected flash size: 4MB")
        print("Manufacturer: c4")
        print("Hard resetting via RTS pin...")
    elif args[0] == "monitor":
        import time
        running = _flashed().get(port) if devkit else None
        if running:  # the simulated devkit: it boots into what was flashed and says so
            hello = [f"apothecary {running}: hello",
                     "chip: ESP32-D0WD-V3 rev 301, 2 core(s), 240 MHz, LED on GPIO 2"]
            for line in ["", *hello]:
                print(line, flush=True)
            n = 0
            while True:  # ten times the real cadence: a blink a tenth of a second
                time.sleep(0.1); n += 1
                print(f"blink {n}", flush=True)
                if n % 10 == 0:
                    for line in hello:
                        print(line, flush=True)
        script = ["blink 1", "apothecary fake_blink: hello", "chip: FAKE-CHIP rev 1, 1 core(s)"]
        if "REPLAY" in os.environ.get("FAKE_MONITOR", ""):
            script = ["junk"] * 3000  # far more than the wire could carry
        for line in script:
            print(line, flush=True)
        n = 1
        while True:  # runs until the caller terminates us, like the real monitor
            time.sleep(0.1); n += 1
            print(f"blink {n}", flush=True)
    elif args[0] in ("compile", "upload", "lib", "core"):
        print("fake " + " ".join(args))
        if "FAIL" in " ".join(args):
            print("Error during build", file=sys.stderr); sys.exit(1)
        if args[0] == "upload" and port:
            _flash(port, os.path.basename(args[-1].rstrip("/")))
    else:
        print("unknown: " + " ".join(args), file=sys.stderr); sys.exit(2)
    """).lstrip()


# A scripted cargo, standing in for the Xtensa toolchain's: a build must be
# --offline, or it refuses as a build that would reach a host; it writes an ELF
# into --target-dir whose bytes follow the sketch's sources, so an edit is a new
# build. `vendor` makes the folder it is given; `--version`, with or without
# +esp, says what it is. Every argv, with the folder it ran in, is kept in
# <script>.calls.
FAKE_CARGO = textwrap.dedent(r"""
    #!/usr/bin/env python3
    import hashlib, json, os, sys, tomllib
    args = sys.argv[1:]
    with open(__file__ + ".calls", "a") as f:
        f.write(json.dumps({"argv": args, "cwd": os.getcwd()}) + "\n")
    if args and args[0].startswith("+"):
        args = args[1:]
    if args[:1] in (["--version"], ["-V"]):
        print("cargo 1.99.0-nightly (fake 2026-09-30)")
    elif args[:1] == ["build"]:
        if "--offline" not in args:
            print("error: fake cargo: a build must be --offline", file=sys.stderr); sys.exit(101)
        with open("Cargo.toml", "rb") as f:
            name = tomllib.load(f)["package"]["name"]
        print(f"   Compiling {name} v0.1.0 ({os.getcwd()})", flush=True)
        if "FAIL" in open(os.path.join("src", "main.rs")).read():
            print("error: could not compile `" + name + "`", file=sys.stderr); sys.exit(101)
        h = hashlib.sha256()
        for root, _, files in sorted(os.walk("src")):
            for name_ in sorted(files):
                with open(os.path.join(root, name_), "rb") as f:
                    h.update(f.read())
        out = args[args.index("--target-dir") + 1] if "--target-dir" in args else "target"
        folder = os.path.join(out, "xtensa-esp32-none-elf", "release")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, name), "wb") as f:
            f.write(b"\x7fELF fake " + h.hexdigest().encode())
        print("    Finished `release` profile [optimized + debuginfo] target(s) in 0.01s")
    elif args[:1] == ["vendor"]:
        out = args[-1]
        os.makedirs(os.path.join(out, "esp-hal-1.2.2"), exist_ok=True)
        print("   Vendoring esp-hal v1.2.2 to " + out)
    else:
        print("fake cargo: unknown " + " ".join(args), file=sys.stderr); sys.exit(2)
    """).lstrip()

# A scripted espflash: `flash` writes the ELF it is given to the port's simulated
# board (fake-boards.json, shared with the scripted arduino-cli), saying what the
# real one says when it is done.
FAKE_ESPFLASH = textwrap.dedent(r"""
    #!/usr/bin/env python3
    import json, os, sys
    """ + textwrap.indent(FAKE_BOARD, "    ") + r"""
    args = sys.argv[1:]
    with open(__file__ + ".calls", "a") as f:
        f.write(json.dumps(args) + "\n")
    if args[:1] in (["--version"], ["-V"]):
        print("espflash 4.6.0")
    elif args[:1] == ["board-info"]:
        port = args[args.index("--port") + 1]
        print(f"[INFO ] Serial port: '{port}'")
        print("[INFO ] Connecting...")
        print("Chip type:         esp32 (revision v3.1)")
        print("Crystal frequency: 40 MHz")
        print("Flash size:        4MB")
        print("Features:          WiFi, BT, Dual Core, 240MHz, Coding Scheme None")
        print("MAC address:       24:6f:28:00:00:02")
    elif args[:1] == ["flash"]:
        port = args[args.index("--port") + 1]
        elf = args[-1]
        if not os.path.isfile(elf):
            print(f"Error: no ELF at {elf}", file=sys.stderr); sys.exit(1)
        if "FAIL" in " ".join(args):
            print("Error: espflash::connection_failed", file=sys.stderr); sys.exit(1)
        print(f"[INFO ] Serial port: '{port}'")
        print("[INFO ] Connecting...")
        print("Chip type:         esp32 (revision v3.1)")
        print("App/part. size:    61,232/4,128,768 bytes, 1.48%")
        print("[INFO ] Flashing has completed!")
        _flash(port, os.path.basename(elf))
    else:
        print("fake espflash: unknown " + " ".join(args), file=sys.stderr); sys.exit(2)
    """).lstrip()


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



def _write_script(path: Path, text: str) -> Path:
    path.write_text(text.replace("#!/usr/bin/env python3", f"#!{sys.executable}", 1), "utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def write_fake_arduino_cli(path: Path) -> Path:
    """Materialise the fake as an executable at ``path`` (using this interpreter)."""
    return _write_script(path, FAKE_ARDUINO_CLI)


def write_fake_cargo(path: Path) -> Path:
    """The scripted cargo, an executable at ``path``."""
    return _write_script(path, FAKE_CARGO)


def write_fake_espflash(path: Path) -> Path:
    """The scripted espflash, an executable at ``path``; beside a scripted
    arduino-cli, the two flash one simulated bench."""
    return _write_script(path, FAKE_ESPFLASH)


def fake_cli_calls(script) -> list[list[str]]:
    """Every argv the fake arduino-cli script was invoked with, in order."""
    log = script.with_name(script.name + ".calls")
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
