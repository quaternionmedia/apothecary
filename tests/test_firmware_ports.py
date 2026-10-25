"""Each toolchain module brings its own ports: it finds them, listens to a board and
asks the chip itself -- Arduino through arduino-cli and esptool, Rust through
pyserial (apothecary/firmware/serial_monitor.py) and espflash -- so Rust works with
no arduino-cli at all (the owner's decision of 2026-10-10).

Against the scripted tools and the simulated serial engine: no test here lists or
opens a real port.
"""

from __future__ import annotations

import subprocess
import sys
import time

import pytest
from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.firmware import devices, serial_monitor, service
from apothecary.firmware.modules import get_module
from apothecary.firmware.modules.rust_esp32 import parse_board_info
from apothecary.firmware.sketches import find_sketch
from apothecary.firmware.toolchains import ToolchainError

DEVKIT = "/dev/ttyFAKE2"


@pytest.fixture
def rust_only(fake_rust, monkeypatch):
    """Rust for the ESP32 and no arduino-cli anywhere."""
    monkeypatch.setenv("ARDUINO_CLI", "none")
    from apothecary.firmware import toolchains

    toolchains.reset_toolchains()
    yield fake_rust
    toolchains.reset_toolchains()


def test_a_port_two_modules_find_is_the_first_ones(fake_rust):
    """arduino-cli finds the Uno and the printer; the Rust module, its devkit. Each port
    says which module found it, and is listened to by that one."""
    found = {d.port: d.found_by for d in devices.detected_devices(fresh=True)}
    assert found == {"/dev/ttyFAKE0": "arduino", "/dev/ttyFAKE1": "arduino", DEVKIT: "rust-esp32"}
    uno = devices.listener_argv("/dev/ttyFAKE0", 115200)
    assert uno[uno.index("monitor") + 1 : uno.index("monitor") + 3] == ["--port", "/dev/ttyFAKE0"]
    assert devices.listener_argv(DEVKIT, 115200) == [
        sys.executable,
        "-m",
        "apothecary.firmware.serial_monitor",
        DEVKIT,
        "115200",
    ]


def test_rust_alone_finds_ports_listens_and_probes(rust_only):
    devs = devices.detected_devices(fresh=True)
    assert [(d.port, d.found_by, d.vid, d.pid) for d in devs] == [
        (DEVKIT, "rust-esp32", "0x10c4", "0xea60")
    ]
    probed = devices.probe_device(DEVKIT)  # esptool absent: espflash board-info asks
    assert probed.chip == "esp32" and probed.revision == "v3.1"
    assert probed.mac == "24:6f:28:00:00:02" and probed.flash_size == "4MB"
    assert probed.identity == "24:6f:28:00:00:02"


def test_with_nothing_installed_finding_ports_names_both_installs(no_arduino_cli):
    with pytest.raises(ToolchainError, match="arduino-cli is not installed"):
        devices.detected_devices(fresh=True)
    with pytest.raises(ToolchainError, match="--rust-esp32"):
        devices.listener_argv(DEVKIT, 115200)


def test_the_simulated_devkit_says_the_hello_of_what_was_flashed_to_it(rust_only, monkeypatch):
    """Nothing flashed, it boots and says nothing of a sketch; flashed the Rust
    esp32_blink, it says its hello -- the sketch's name, whichever build."""
    quiet = serial_monitor.SimulatedDevkit(DEVKIT, 115200)
    assert b"hello" not in quiet.read(0.1) + quiet.read(0.1)
    sketch = find_sketch("esp32_blink@rust-esp32")
    service.record_upload(DEVKIT, sketch, None)
    board = serial_monitor.SimulatedDevkit(DEVKIT, 115200)
    said = b"".join(board.read(0.05) for _ in range(12)).decode()
    assert "apothecary esp32_blink: hello" in said
    assert "chip: ESP32-D0WD-V3 rev 301, 2 core(s), 240 MHz, LED on GPIO 2" in said
    assert "blink 1\r\n" in said and said.count("hello") >= 2  # again at the tenth blink


def test_the_rust_module_listens_in_a_process_of_its_own(rust_only, tmp_path):
    """The monitor process writes what the board says until it is stopped, as
    arduino-cli's monitor does; the server reads it the same way."""
    service.record_upload(DEVKIT, find_sketch("esp32_blink@rust-esp32"), None)
    proc = subprocess.Popen(
        serial_monitor.monitor_argv(DEVKIT, 115200),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        deadline, out = time.monotonic() + 20, b""
        while b"blink 2" not in out and time.monotonic() < deadline:
            out += proc.stdout.read1(4096)
    finally:
        proc.terminate()
        proc.wait(timeout=5)
    assert b"apothecary esp32_blink: hello" in out


def test_listening_through_the_server_hears_the_hello_with_no_arduino_cli(rust_only):
    service.record_upload(DEVKIT, find_sketch("esp32_blink@rust-esp32"), None)
    heard = devices.listen(DEVKIT, seconds=1.5)
    assert heard.running_sketch == "esp32_blink"
    assert heard.chip_line.startswith("ESP32-D0WD-V3 rev 301")
    client = TestClient(app)
    r = client.post("/firmware/devices/listen", json={"port": DEVKIT, "seconds": 1.0})
    assert r.status_code == 200 and r.json()["running_sketch"] == "esp32_blink"
    seen = client.get("/firmware/devices").json()["devices"]
    assert [d["device"]["found_by"] for d in seen] == ["rust-esp32"]


def test_the_simulated_engine_lists_only_what_it_is_told_to(monkeypatch):
    monkeypatch.setenv("APOTHECARY_SERIAL_ENGINE", "simulated")
    monkeypatch.setenv("APOTHECARY_SIMULATED_DEVKIT", "/dev/ttyFAKE2, /dev/ttyFAKE3")
    assert [b.port for b in serial_monitor.list_ports()] == ["/dev/ttyFAKE2", "/dev/ttyFAKE3"]
    monkeypatch.delenv("APOTHECARY_SIMULATED_DEVKIT")
    assert serial_monitor.list_ports() == []


def test_espflash_board_info_reads_as_an_esptool_probe():
    text = (
        "[INFO ] Serial port: '/dev/ttyUSB0'\n"
        "Chip type:         esp32 (revision v3.1)\n"
        "Crystal frequency: 40 MHz\n"
        "Flash size:        4MB\n"
        "Features:          WiFi, BT, Dual Core, 240MHz, Coding Scheme None\n"
        "MAC address:       24:6F:28:AA:BB:CC\n"
    )
    assert parse_board_info(text) == {
        "chip": "esp32",
        "revision": "v3.1",
        "crystal": "40MHz",
        "flash_size": "4MB",
        "features": ["WiFi", "BT", "Dual Core", "240MHz", "Coding Scheme None"],
        "mac": "24:6f:28:aa:bb:cc",
    }
    argv = get_module("rust-esp32").probe_argv("/dev/ttyUSB0")
    assert argv is None or argv[1:4] == ["board-info", "--skip-update-check", "--non-interactive"]


def test_each_module_says_what_it_can_do(fake_rust):
    status = service.toolchain_status()
    can = {m.id: m.can for m in status.toolchains}
    assert "find ports" in can["arduino"] and "listen" in can["arduino"]
    assert can["rust-esp32"] == ["build", "flash", "find ports", "listen", "probe with espflash"]
