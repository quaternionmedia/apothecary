"""Devices: state records, probe parsing, expected-vs-observed, serial listen/stream, routes."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner
from conftest import fake_cli_calls
from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.cli import cli
from apothecary.firmware import devices
from apothecary.firmware.models import DeviceInfo, FlashRecord
from apothecary.firmware.sketches import find_sketch
from apothecary.firmware.toolchains import Esptool, parse_esptool_probe

ROOT = Path(__file__).resolve().parents[1]

ESPTOOL_OUT = """esptool v5.3.1
Connected to ESP32 on /dev/ttyUSB0:
Chip type:          ESP32-D0WD-V3 (revision v3.1)
Features:           Wi-Fi, BT, Dual Core + LP Core, 240MHz, Vref calibration in eFuse, Coding None
Crystal frequency:  40MHz
MAC:                DE:AD:BE:EF:00:42

Flash Memory Information:
=========================
Manufacturer: c4
Device: 6016
Detected flash size: 4MB
Hard resetting via RTS pin...
"""

OLD_ESPTOOL_OUT = """Chip is ESP32-D0WD (revision 1)
Features: WiFi, BT, Dual Core, 240MHz, VRef calibration in efuse, Coding Scheme None
Crystal is 40MHz
MAC: 24:6f:28:aa:bb:cc
"""


# --- parsing --------------------------------------------------------------------


def test_parse_esptool_probe_v5_and_legacy():
    info = parse_esptool_probe(ESPTOOL_OUT)
    assert info["chip"] == "ESP32-D0WD-V3" and info["revision"] == "v3.1"
    assert info["mac"] == "de:ad:be:ef:00:42" and info["flash_size"] == "4MB"
    assert info["crystal"] == "40MHz" and info["flash_manufacturer"] == "c4"
    assert info["features"][0] == "Wi-Fi" and len(info["features"]) == 6
    legacy = parse_esptool_probe(OLD_ESPTOOL_OUT)
    assert legacy["chip"] == "ESP32-D0WD" and legacy["revision"] == "1"
    assert legacy["mac"] == "24:6f:28:aa:bb:cc" and legacy["crystal"] == "40MHz"


def test_classify_lines_finds_banner_and_chip():
    out = devices.classify_lines(
        ["blink 3", "apothecary esp32_blink: hello", "chip: ESP32 rev 301, 2 core(s)"]
    )
    assert out == {"running_sketch": "esp32_blink", "chip_line": "ESP32 rev 301, 2 core(s)"}
    assert devices.classify_lines(["blink 1"]) == {"running_sketch": None, "chip_line": None}


# --- state -----------------------------------------------------------------------


def _rec(identity, port="/dev/ttyUSB0", mac=None, sketch="esp32_blink", when=None):
    return FlashRecord(
        identity=identity,
        port=port,
        mac=mac,
        sketch=sketch,
        fqbn="esp32:esp32:esp32",
        flashed_at=when or datetime.now(timezone.utc),
    )


def test_state_round_trip_and_last_flash(tmp_path):
    state = devices.FirmwareState(tmp_path / "s.json")
    assert state.flashes() == [] and state.last_flash("x") is None
    old = _rec("aa:bb", mac="aa:bb", sketch="old", when=datetime(2026, 1, 1, tzinfo=timezone.utc))
    new = _rec("aa:bb", mac="aa:bb", sketch="new")
    by_port = _rec("/dev/ttyUSB1", port="/dev/ttyUSB1", sketch="portonly")
    for r in (old, new, by_port):
        state.record_flash(r)
    assert state.last_flash("aa:bb").sketch == "new"
    assert (
        state.last_flash("zz:zz", port="/dev/ttyUSB1").sketch == "portonly"
    )  # never-probed fallback
    assert (
        state.last_flash("zz:zz", port="/dev/ttyUSB0") is None
    )  # MAC-keyed record does not leak to a port match
    assert json.loads((tmp_path / "s.json").read_text())["flashes"][0]["sketch"] == "old"

    dev = DeviceInfo(port="/dev/ttyUSB0", vid="1", pid="2", mac="aa:bb", chip="ESP32")
    state.remember_device(dev)
    assert state.cached_device("/dev/ttyUSB0").mac == "aa:bb"
    assert state.cached_device("/dev/nope") is None


def test_state_survives_corrupt_file(tmp_path):
    f = tmp_path / "s.json"
    f.write_text("{not json")
    state = devices.FirmwareState(f)
    assert state.flashes() == []
    state.record_flash(_rec("p"))
    assert len(state.flashes()) == 1


def test_expected_firmware_detects_drift(fake_arduino_cli, tmp_path, monkeypatch):
    state = devices.get_state()
    sketch = find_sketch("footpedal", ROOT)
    build = tmp_path / "build"
    (build / "footpedal").mkdir(parents=True)
    (build / "footpedal" / "footpedal.ino.hex").write_bytes(b"v1")
    record = devices.make_flash_record(
        "/dev/ttyX", sketch, "arduino:avr:uno", build / "footpedal", state=state
    )
    state.record_flash(record)
    dev = DeviceInfo(port="/dev/ttyX")

    fresh = devices.expected_firmware(dev, build, state)
    assert (
        fresh.record.sketch == "footpedal" and not fresh.source_changed and not fresh.build_changed
    )

    (build / "footpedal" / "footpedal.ino.hex").write_bytes(b"v2")
    assert devices.expected_firmware(dev, build, state).build_changed

    monkeypatch.setattr(devices, "source_sha256", lambda s: "different")
    assert devices.expected_firmware(dev, build, state).source_changed

    state.record_flash(_rec("/dev/ttyY", port="/dev/ttyY", sketch="gone"))
    assert devices.expected_firmware(DeviceInfo(port="/dev/ttyY"), build, state).sketch_missing


def test_make_flash_record_uses_cached_mac(fake_arduino_cli):
    state = devices.get_state()
    state.remember_device(DeviceInfo(port="/dev/ttyFAKE0", vid="0x2341", pid="0x0043", mac="aa:bb"))
    rec = devices.make_flash_record("/dev/ttyFAKE0", None, None, images=["0x0:x.bin"], state=state)
    assert rec.identity == "aa:bb" and rec.mac == "aa:bb" and rec.sketch is None


# --- detected / probed ---------------------------------------------------------------


def test_detected_devices_merge_cached_probe(fake_arduino_cli):
    state = devices.get_state()
    state.remember_device(
        DeviceInfo(
            port="/dev/ttyFAKE1", vid=None, pid=None, mac="aa:bb", chip="ESP32", flash_size="4MB"
        )
    )
    found = {d.port: d for d in devices.detected_devices()}
    assert (
        found["/dev/ttyFAKE0"].board_name == "Arduino Uno" and found["/dev/ttyFAKE0"].chip is None
    )
    assert found["/dev/ttyFAKE1"].chip == "ESP32" and found["/dev/ttyFAKE1"].mac == "aa:bb"
    # A different bridge on the same port name is not the same device.
    state.remember_device(
        DeviceInfo(port="/dev/ttyFAKE1", vid="0x1", pid="0x2", mac="cc:dd", chip="OTHER")
    )
    assert {d.port: d for d in devices.detected_devices()}["/dev/ttyFAKE1"].chip is None


def test_probe_uses_esptool_only_for_unmatched_or_esp(fake_arduino_cli, monkeypatch):
    from apothecary.firmware import toolchains

    fake_esptool = Esptool(argv_prefix=[str(fake_arduino_cli)])
    monkeypatch.setattr(toolchains, "_ESPTOOL", fake_esptool)
    avr = devices.probe_device("/dev/ttyFAKE0")  # matched arduino:avr:uno → esptool skipped
    assert avr.chip is None and avr.board_name == "Arduino Uno"
    esp = devices.probe_device("/dev/ttyFAKE1")
    assert (
        esp.chip == "ESP32-D0WD-V3" and esp.mac == "aa:bb:cc:dd:ee:ff" and esp.probed_at is not None
    )
    assert devices.get_state().cached_device("/dev/ttyFAKE1").mac == "aa:bb:cc:dd:ee:ff"
    calls = [c for c in fake_cli_calls(fake_arduino_cli) if "flash_id" in c]
    assert calls == [["--chip", "auto", "--port", "/dev/ttyFAKE1", "flash_id"]]
    with pytest.raises(Exception, match="no board detected"):
        devices.probe_device("/dev/ttyNOPE")


# --- observed: listen / stream ----------------------------------------------------------


def test_listen_captures_banner_and_releases_port(fake_arduino_cli):
    result = devices.listen("/dev/ttyFAKE0", seconds=0.6)
    assert result.running_sketch == "fake_blink" and result.chip_line.startswith("FAKE-CHIP")
    assert result.lines[0] == "blink 1" and len(result.lines) >= 4
    assert devices.get_streams().open_ports == []


def test_stream_lines_stops_on_event_and_cleans_up(fake_arduino_cli):
    import threading

    stop = threading.Event()
    got = []
    for item in devices.stream_lines("/dev/ttyFAKE0", stop=stop, keepalive=0.2):
        if item is not None:
            got.append(item)
        if len(got) >= 5:
            stop.set()
    assert got[1] == "apothecary fake_blink: hello"
    assert devices.get_streams().open_ports == []


def test_stream_replay_guard_reopens_then_gives_up(fake_arduino_cli, monkeypatch):
    import threading

    monkeypatch.setenv("FAKE_MONITOR", "REPLAY")
    stop = threading.Event()
    items = []
    deadline = time.time() + 8
    for item in devices.stream_lines("/dev/ttyFAKE0", stop=stop, keepalive=0.2, max_reopens=1):
        items.append(item)
        if (item and "giving up" in item) or time.time() > deadline:
            stop.set()
    markers = [i for i in items if i and i.startswith("[apothecary:")]
    assert markers and markers[0] == devices.REPLAY_MARKER
    assert any("giving up" in m for m in markers)
    # Each flood is 3000 lines; two floods happened and almost all of it was dropped.
    assert sum(1 for i in items if i == "junk") < 1500
    assert devices.get_streams().open_ports == []


def test_streams_stop_all_kills_monitors(fake_arduino_cli):
    streams = devices.get_streams()
    proc = streams.open("/dev/ttyFAKE0", 115200)
    assert streams.open_ports == ["/dev/ttyFAKE0"] and proc.poll() is None
    streams.stop_all()
    time.sleep(0.2)
    assert streams.open_ports == [] and proc.poll() is not None


# --- API ---------------------------------------------------------------------------


def test_devices_route_and_upload_records_expected(fake_arduino_cli, fresh_task_runner):
    c = TestClient(app)
    before = c.get("/firmware/devices").json()
    assert [v["device"]["port"] for v in before["devices"]] == ["/dev/ttyFAKE0", "/dev/ttyFAKE1"]
    assert before["devices"][0]["expected"]["record"] is None

    r = c.post(
        "/firmware/sketches/footpedal/upload",
        json={"fqbn": "arduino:avr:uno", "port": "/dev/ttyFAKE0"},
    )
    assert r.status_code == 202
    deadline = time.time() + 5
    while (
        c.get(f"/firmware/tasks/{r.json()['id']}").json()["status"] == "running"
        and time.time() < deadline
    ):
        time.sleep(0.02)
    after = c.get("/firmware/devices").json()["devices"][0]["expected"]
    assert after["record"]["sketch"] == "footpedal" and after["record"]["task_id"] == r.json()["id"]
    assert after["source_changed"] is False


def test_probe_listen_routes(fake_arduino_cli, fresh_task_runner, monkeypatch):
    from apothecary.firmware import toolchains

    monkeypatch.setattr(toolchains, "_ESPTOOL", Esptool(argv_prefix=[str(fake_arduino_cli)]))
    c = TestClient(app)
    assert c.post("/firmware/devices/probe", json={"port": "ttyUSB0"}).status_code == 422
    r = c.post("/firmware/devices/probe", json={"port": "/dev/ttyFAKE1"})
    assert r.status_code == 200 and r.json()["device"]["mac"] == "aa:bb:cc:dd:ee:ff"
    assert c.post("/firmware/devices/probe", json={"port": "/dev/ttyNOPE"}).status_code == 503

    r = c.post("/firmware/devices/listen", json={"port": "/dev/ttyFAKE0", "seconds": 0.6})
    assert r.status_code == 200 and r.json()["running_sketch"] == "fake_blink"
    assert (
        c.post(
            "/firmware/devices/listen", json={"port": "/dev/ttyFAKE0", "seconds": 99}
        ).status_code
        == 422
    )


@pytest.fixture
def live_server(fake_arduino_cli):
    """A real uvicorn on a free port: the SSE route needs genuine client-disconnect semantics."""
    import socket
    import threading

    import uvicorn

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(5)


def test_stream_route_emits_sse_and_releases_port_on_disconnect(live_server, fresh_task_runner):
    import httpx

    assert httpx.get(f"{live_server}/firmware/devices/stream?port=bad").status_code == 422
    seen = []
    with httpx.stream(
        "GET", f"{live_server}/firmware/devices/stream?port=/dev/ttyFAKE0", timeout=10
    ) as resp:
        assert resp.status_code == 200 and resp.headers["content-type"].startswith(
            "text/event-stream"
        )
        for line in resp.iter_lines():
            seen.append(line)
            if "fake_blink: hello" in line:
                break
    assert seen[0] == "event: open" and "data: blink 1" in seen
    deadline = time.time() + 5
    while devices.get_streams().open_ports and time.time() < deadline:
        time.sleep(0.05)
    assert devices.get_streams().open_ports == []


def test_task_start_stops_live_monitors(fake_arduino_cli, fresh_task_runner):
    streams = devices.get_streams()
    streams.open("/dev/ttyFAKE0", 115200)
    assert streams.open_ports == ["/dev/ttyFAKE0"]
    c = TestClient(app)
    r = c.post("/firmware/sketches/footpedal/compile", json={"fqbn": "arduino:avr:uno"})
    assert r.status_code == 202
    assert streams.open_ports == []


def test_busy_task_blocks_probe_and_listen(fake_arduino_cli, fresh_task_runner, tmp_path):
    slow = tmp_path / "slow.sh"
    slow.write_text("#!/bin/sh\n/bin/sleep 2\n")
    slow.chmod(0o755)
    fresh_task_runner.run("x", "slow", [[str(slow)]])
    c = TestClient(app)
    assert c.post("/firmware/devices/probe", json={"port": "/dev/ttyFAKE0"}).status_code == 409
    assert c.post("/firmware/devices/listen", json={"port": "/dev/ttyFAKE0"}).status_code == 409
    assert c.get("/firmware/devices/stream?port=/dev/ttyFAKE0").status_code == 409
    fresh_task_runner.cancel(fresh_task_runner.active.id)


# --- CLI ---------------------------------------------------------------------------


def test_cli_devices_probe_listen(fake_arduino_cli, monkeypatch):
    from apothecary.firmware import toolchains

    monkeypatch.setattr(toolchains, "_ESPTOOL", Esptool(argv_prefix=[str(fake_arduino_cli)]))
    runner = CliRunner()
    r = runner.invoke(cli, ["firmware", "devices"])
    assert r.exit_code == 0, r.output
    assert "/dev/ttyFAKE0" in r.output and "nothing flashed from apothecary yet" in r.output
    r = runner.invoke(cli, ["firmware", "probe", "/dev/ttyFAKE1"])
    assert r.exit_code == 0 and "ESP32-D0WD-V3" in r.output and "aa:bb:cc:dd:ee:ff" in r.output
    r = runner.invoke(cli, ["firmware", "listen", "/dev/ttyFAKE0", "--seconds", "0.6"])
    assert r.exit_code == 0, r.output
    assert "running: fake_blink" in r.output
    r = runner.invoke(cli, ["firmware", "upload", "footpedal", "--port", "/dev/ttyFAKE0"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(cli, ["firmware", "devices", "--json-out"])
    assert json.loads(r.output)[0]["expected"]["record"]["sketch"] == "footpedal"
    assert runner.invoke(cli, ["firmware", "probe", "nope"]).exit_code != 0
