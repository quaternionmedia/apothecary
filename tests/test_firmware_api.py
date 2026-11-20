"""``/firmware`` API and ``apothecary firmware`` CLI, driven against the fake arduino-cli."""

import json
import re
import threading
import time
from pathlib import Path

from click.testing import CliRunner
from fastapi.testclient import TestClient
from firmware_helpers import fake_cli_calls

from apothecary.api import app
from apothecary.cli import cli

ROOT = Path(__file__).resolve().parents[1]


def _wait_for(client, task_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/firmware/tasks/{task_id}").json()
        if data["status"] != "running":
            return data
        time.sleep(0.02)
    raise AssertionError("task did not finish")


# --- API ------------------------------------------------------------------------


def test_the_firmware_page_is_the_bench_in_the_viewer(fake_arduino_cli):
    """/firmware leads to the viewer with the Bench open."""
    r = TestClient(app).get("/firmware", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/viewer/sites/garage?panel=bench"
    page = TestClient(app).get("/firmware")
    assert page.status_code == 200 and "/static/widgets/toolchain.js" in page.text


def test_the_viewer_links_to_no_page_of_its_own(fake_arduino_cli):
    """The toolbar links to no page of its own: Panels › Tools › Bench and a board's Machine
    are the ways in."""
    r = TestClient(app).get("/viewer/sites/garage")
    assert r.status_code == 200
    assert not re.search(r'href="[^"]*/firmware(/monitor)?(\?[^"]*)?"', r.text)
    assert "firmware-link" not in r.text and "monitor-link" not in r.text


def test_status_and_catalogue(fake_arduino_cli, fresh_task_runner):
    c = TestClient(app)
    status = c.get("/firmware/status").json()
    # Where the tools live, each module's own status, and the task running now:
    # nothing of one module's is beside them.
    assert set(status) == {"tools_dir", "toolchains", "active_task"}
    arduino = status["toolchains"][0]
    assert arduino["id"] == "arduino" and arduino["ok"]
    assert [(t["name"], t["version"], t["ok"]) for t in arduino["tools"]] == [
        ("arduino-cli", "9.9.9", True),
        ("esptool", None, False),
    ]
    assert arduino["config_file"] == f"{status['tools_dir']}/arduino-cli.yaml"
    assert [(c["id"], c["installed"]) for c in arduino["cores"]] == [("arduino:avr", "1.8.8")]
    assert status["active_task"] is None
    assert {"id": "esp32:esp32", "label": "Espressif ESP32 (all variants)"} in (
        arduino["suggested_cores"]
    )
    assert [b["port"] for b in c.get("/firmware/boards").json()] == [
        "/dev/ttyFAKE0",
        "/dev/ttyFAKE1",
    ]
    assert {b["fqbn"] for b in c.get("/firmware/boards/all").json()} == {
        "arduino:avr:uno",
        "arduino:avr:nano",
    }
    assert c.get("/firmware/cores").json()[0]["id"] == "arduino:avr"
    assert any(s["name"] == "footpedal" for s in c.get("/firmware/sketches").json())


def test_status_without_toolchain_is_honest(no_arduino_cli, fresh_task_runner):
    c = TestClient(app)
    status = c.get("/firmware/status").json()
    arduino = status["toolchains"][0]
    assert arduino["id"] == "arduino" and not arduino["ok"]
    assert arduino["config_file"] is None and arduino["cores"] == []
    assert "arduino-cli not found (run `apothecary firmware install`)" in arduino["problems"]
    assert c.get("/firmware/boards").status_code == 503
    assert (
        c.post("/firmware/sketches/footpedal/compile", json={"fqbn": "arduino:avr:uno"}).status_code
        == 503
    )


def test_compile_task_lifecycle(fake_arduino_cli, fresh_task_runner):
    c = TestClient(app)
    r = c.post("/firmware/sketches/footpedal/compile", json={"fqbn": "arduino:avr:uno"})
    assert r.status_code == 202
    task = r.json()
    assert task["kind"] == "compile" and "footpedal" in task["title"]
    done = _wait_for(c, task["id"])
    assert done["status"] == "succeeded"
    assert done["lines"][0].startswith("$ ") and "fake compile" in done["lines"][1]
    # Incremental polling only returns new lines.
    tail = c.get(f"/firmware/tasks/{task['id']}?since={done['next']}").json()
    assert tail["lines"] == [] and tail["next"] == done["next"]
    assert c.get("/firmware/tasks").json()[0]["id"] == task["id"]
    assert c.get("/firmware/tasks/nope").status_code == 404
    assert c.post(f"/firmware/tasks/{task['id']}/cancel").status_code == 409


def test_upload_compiles_then_uploads(fake_arduino_cli, fresh_task_runner):
    c = TestClient(app)
    r = c.post(
        "/firmware/sketches/footpedal/upload",
        json={"fqbn": "arduino:avr:uno", "port": "/dev/ttyFAKE0"},
    )
    assert r.status_code == 202
    done = _wait_for(c, r.json()["id"])
    assert done["status"] == "succeeded"
    calls = [call for call in fake_cli_calls(fake_arduino_cli) if call[0] in ("compile", "upload")]
    assert [call[0] for call in calls] == ["compile", "upload"]
    assert calls[1][calls[1].index("--port") + 1] == "/dev/ttyFAKE0"


def test_failed_build_is_reported(fake_arduino_cli, fresh_task_runner):
    c = TestClient(app)
    r = c.post("/firmware/sketches/footpedal/compile", json={"fqbn": "arduino:avr:FAIL"})
    done = _wait_for(c, r.json()["id"])
    assert done["status"] == "failed" and done["returncode"] == 1
    assert "exit 1" in done["lines"][-1]


def test_input_validation(fake_arduino_cli, fresh_task_runner):
    c = TestClient(app)
    assert (
        c.post("/firmware/sketches/footpedal/compile", json={"fqbn": "rm -rf /"}).status_code == 422
    )
    assert (
        c.post(
            "/firmware/sketches/footpedal/upload",
            json={"fqbn": "arduino:avr:uno", "port": "ttyUSB0"},
        ).status_code
        == 422
    )
    assert (
        c.post("/firmware/sketches/missing/compile", json={"fqbn": "arduino:avr:uno"}).status_code
        == 404
    )
    assert c.post("/firmware/cores/install", json={"id": "esp32"}).status_code == 422
    assert c.post("/firmware/libraries/install", json={"names": []}).status_code == 422
    assert c.post("/firmware/libraries/install", json={"names": ["--evil"]}).status_code == 422


def test_esptool_flash_requires_tool_and_confines_paths(
    fake_arduino_cli, fresh_task_runner, monkeypatch
):
    c = TestClient(app)
    body = {"port": "/dev/ttyUSB0", "images": [{"offset": "0x0", "path": "README.md"}]}
    assert c.post("/firmware/esptool/flash", json=body).status_code == 503  # no esptool

    from apothecary.firmware import toolchains

    monkeypatch.setattr(
        toolchains, "_ESPTOOL", toolchains.Esptool(argv_prefix=[str(fake_arduino_cli), "compile"])
    )
    evil = {"port": "/dev/ttyUSB0", "images": [{"offset": "0x0", "path": "../../etc/passwd"}]}
    assert c.post("/firmware/esptool/flash", json=evil).status_code == 503
    r = c.post("/firmware/esptool/flash", json={**body, "erase": True, "chip": "esp32"})
    assert r.status_code == 202
    done = _wait_for(c, r.json()["id"])
    assert done["status"] == "succeeded"
    steps = [call for call in fake_cli_calls(fake_arduino_cli) if call[0] == "compile"]
    assert steps[0][1:] == ["--chip", "esp32", "--port", "/dev/ttyUSB0", "erase_flash"]
    assert steps[1][1:7] == ["--chip", "esp32", "--port", "/dev/ttyUSB0", "--baud", "460800"]
    assert steps[1][7:9] == ["write_flash", "0x0"] and steps[1][9].endswith("README.md")


def test_busy_runner_returns_409(fake_arduino_cli, fresh_task_runner, tmp_path):
    slow = tmp_path / "slow.sh"
    slow.write_text("#!/bin/sh\n/bin/sleep 2\n")
    slow.chmod(0o755)
    fresh_task_runner.run("x", "slow", [[str(slow)]])
    c = TestClient(app)
    assert (
        c.post("/firmware/sketches/footpedal/compile", json={"fqbn": "arduino:avr:uno"}).status_code
        == 409
    )
    assert c.get("/firmware/status").json()["active_task"]["title"] == "slow"
    active = fresh_task_runner.active
    assert c.post(f"/firmware/tasks/{active.id}/cancel").json()["status"] == "cancelled"


def test_install_task_runs_installer(fake_arduino_cli, fresh_task_runner, monkeypatch):
    from apothecary.firmware import installer

    monkeypatch.setattr(
        installer.ArduinoCliInstaller, "install_binary", lambda self: fake_arduino_cli
    )
    c = TestClient(app)
    r = c.post("/firmware/install", json={"cores": ["arduino:avr"]})
    assert r.status_code == 202
    done = _wait_for(c, r.json()["id"])
    assert done["status"] == "succeeded"
    assert ["core", "install", "arduino:avr"] in fake_cli_calls(fake_arduino_cli)
    assert c.post("/firmware/install", json={"cores": ["bad"]}).status_code == 422


# --- CLI -------------------------------------------------------------------------


# What validate says of esptool when there is none.
NO_ESPTOOL = (
    "  • esptool: not found (optional: raw binary flashing needs it; "
    "arduino-cli uploads to an ESP32 without it)"
)


def test_cli_validate_reports_and_exits(fake_arduino_cli):
    result = CliRunner().invoke(cli, ["firmware", "validate"])
    assert result.exit_code == 0, result.output
    assert "arduino-cli 9.9.9" in result.output and "arduino:avr@1.8.8" in result.output
    # Arduino's lines, word for word and in order, up to the next module's heading:
    # the tools dir, arduino-cli as found, its config and its cores, and esptool.
    tools = fake_arduino_cli.parent / "tools"
    assert result.output.splitlines()[:7] == [
        "Firmware toolchain",
        f"  tools dir: {tools}",
        f"  ✓ arduino-cli 9.9.9: {fake_arduino_cli}",
        f"    config: {tools / 'arduino-cli.yaml'}",
        "    cores: arduino:avr@1.8.8",
        NO_ESPTOOL,
        "Rust for the ESP32 (rust for esp32)",
    ]


def test_cli_validate_missing_toolchain(no_arduino_cli, tmp_path):
    result = CliRunner().invoke(cli, ["firmware", "validate"])
    assert result.exit_code == 1
    assert "not installed" in result.output
    # A tool its own line says is missing is not said again as a problem.
    assert result.output.splitlines()[:5] == [
        "Firmware toolchain",
        f"  tools dir: {tmp_path / 'tools'}",
        "  ✗ arduino-cli: not installed (apothecary firmware install)",
        NO_ESPTOOL,
        "Rust for the ESP32 (rust for esp32)",
    ]
    as_json = CliRunner().invoke(cli, ["firmware", "validate", "--json-out"])
    assert as_json.exit_code == 1
    said = json.loads(as_json.output)
    assert set(said) == {"tools_dir", "toolchains"}
    arduino = said["toolchains"][0]
    assert arduino["id"] == "arduino" and not arduino["ok"]
    assert [(t["name"], t["ok"]) for t in arduino["tools"]] == [
        ("arduino-cli", False),
        ("esptool", False),
    ]


def test_cli_lists(fake_arduino_cli):
    runner = CliRunner()
    boards = runner.invoke(cli, ["firmware", "boards"])
    assert (
        boards.exit_code == 0
        and "/dev/ttyFAKE0" in boards.output
        and "Arduino Uno" in boards.output
    )
    all_boards = runner.invoke(cli, ["firmware", "boards", "--all"])
    assert "arduino:avr:nano" in all_boards.output
    cores = runner.invoke(cli, ["firmware", "cores"])
    assert "arduino:avr" in cores.output and "1.8.8" in cores.output
    sketches = runner.invoke(cli, ["firmware", "sketches", "--json-out"])
    assert '"name": "footpedal"' in sketches.output


def test_cli_compile_and_upload(fake_arduino_cli):
    runner = CliRunner()
    r = runner.invoke(cli, ["firmware", "compile", "footpedal"])
    assert r.exit_code == 0, r.output
    assert "Compiled footpedal@arduino for arduino:avr:uno" in r.output
    r = runner.invoke(
        cli,
        [
            "firmware",
            "upload",
            "footpedal",
            "--port",
            "/dev/ttyFAKE0",
            "--fqbn",
            "arduino:avr:nano",
        ],
    )
    assert r.exit_code == 0, r.output
    assert "Uploaded footpedal@arduino (arduino:avr:nano) to /dev/ttyFAKE0" in r.output
    calls = [c[0] for c in fake_cli_calls(fake_arduino_cli) if c[0] in ("compile", "upload")]
    assert calls == ["compile", "compile", "upload"]


def test_cli_upload_refuses_to_guess_between_ports(fake_arduino_cli):
    r = CliRunner().invoke(cli, ["firmware", "upload", "footpedal"])
    assert r.exit_code != 0 and "several boards detected" in r.output


def test_cli_rejects_unknown_sketch_and_bad_fqbn(fake_arduino_cli):
    runner = CliRunner()
    r = runner.invoke(cli, ["firmware", "compile", "nope"])
    assert r.exit_code != 0 and "unknown sketch" in r.output
    r = runner.invoke(cli, ["firmware", "compile", "footpedal", "--fqbn", "bad"])
    assert r.exit_code != 0 and "not a valid FQBN" in r.output


def test_cli_cores_install_and_libraries(fake_arduino_cli):
    runner = CliRunner()
    r = runner.invoke(cli, ["firmware", "cores", "--install", "esp32:esp32"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(cli, ["firmware", "libraries", "--install", "FastLED"])
    assert r.exit_code == 0, r.output
    calls = fake_cli_calls(fake_arduino_cli)
    assert [
        "core",
        "install",
        "esp32:esp32",
        "--additional-urls",
        "https://espressif.github.io/arduino-esp32/package_esp32_index.json",
    ] in calls
    assert ["lib", "install", "FastLED"] in calls
    assert runner.invoke(cli, ["firmware", "libraries"]).exit_code != 0


def test_cli_flash_bin_argument_parsing(fake_arduino_cli, tmp_path, monkeypatch):
    from apothecary.firmware import toolchains

    monkeypatch.setattr(
        toolchains, "_ESPTOOL", toolchains.Esptool(argv_prefix=[str(fake_arduino_cli), "compile"])
    )
    img = tmp_path / "app.bin"
    img.write_bytes(b"\0")
    runner = CliRunner()
    r = runner.invoke(
        cli,
        ["firmware", "flash-bin", "/dev/ttyUSB0", f"0x10000:{img}", "--chip", "esp32", "--erase"],
    )
    assert r.exit_code == 0, r.output
    assert "Flashed 1 image(s)" in r.output
    r = runner.invoke(cli, ["firmware", "flash-bin", "/dev/ttyUSB0", "noколон"])
    assert r.exit_code != 0
    r = runner.invoke(cli, ["firmware", "flash-bin", "bad-port", f"0x0:{img}"])
    assert r.exit_code != 0 and "serial port" in r.output


def test_a_flash_of_a_machines_controller_is_asked_for_by_name(
    fake_arduino_cli, fresh_task_runner, monkeypatch
):
    """A port whose board answered as a router is not flashed by a sketch's upload, by
    raw images or from the command line, unless replacing its firmware is asked for."""
    from apothecary.firmware import devices, gcode, grbl, toolchains

    port, sketch = "/dev/ttyFAKE1", "esp32_blink@arduino"
    monkeypatch.setenv("APOTHECARY_SIMULATED_SPEED", "0")
    links = gcode.PrinterLinks(factory=grbl.SimulatedRouter)
    monkeypatch.setattr(gcode, "_LINKS", links)
    devices.identify_printer(port)
    links.stop_all()
    c = TestClient(app)
    asked = {"fqbn": "esp32:esp32:esp32", "port": port}
    r = c.post(f"/firmware/sketches/{sketch}/upload", json=asked)
    assert r.status_code == 422 and "holds a router's controller (Grbl 1.3a)" in r.json()["detail"]
    monkeypatch.setattr(
        toolchains, "_ESPTOOL", toolchains.Esptool(argv_prefix=[str(fake_arduino_cli), "compile"])
    )
    raw = {"port": port, "images": [{"offset": "0x0", "path": "README.md"}]}
    assert c.post("/firmware/esptool/flash", json=raw).status_code == 422
    assert fresh_task_runner.active is None
    assert not [c for c in fake_cli_calls(fake_arduino_cli) if c[0] in ("upload", "compile")]
    said = CliRunner().invoke(cli, ["firmware", "upload", sketch, "--port", port])
    assert said.exit_code != 0 and "holds a router's controller" in said.output
    said = CliRunner().invoke(cli, ["firmware", "flash-bin", port, "0x0:README.md"])
    assert said.exit_code != 0 and "holds a router's controller" in said.output
    r = c.post(
        f"/firmware/sketches/{sketch}/upload", json={**asked, "replace_machine_firmware": True}
    )
    assert r.status_code == 202
    assert _wait_for(c, r.json()["id"])["status"] == "succeeded"


def test_the_server_says_what_a_restart_would_cut_into(
    fake_arduino_cli, fresh_task_runner, monkeypatch
):
    """Idle is said, never assumed: a table map under way with its latch lapsed, a
    running task and an armed port are each a reason not to restart."""
    from apothecary.firmware import devices, gcode, grbl

    port = "/dev/ttyFAKE1"
    monkeypatch.setenv("APOTHECARY_SIMULATED_SPEED", "0")
    gate = threading.Event()

    class SlowProbe(grbl.SimulatedRouter):
        def write(self, data):
            if b"G38.2" in data:
                gate.wait(10)
            super().write(data)

    links = gcode.PrinterLinks(factory=SlowProbe)
    monkeypatch.setattr(gcode, "_LINKS", links)
    c = TestClient(app)
    assert c.get("/firmware/busy").json() == {"busy": []}
    links.control.arm(port)
    assert c.get("/firmware/busy").json() == {"busy": [f"{port}: control is armed"]}
    job = devices.start_leveling(port, probe=True)
    for _ in range(500):
        if job.stage == "probing":
            break
        time.sleep(0.01)
    links.control.disarm(port)  # as five minutes of probing lets the latch lapse
    assert c.get("/firmware/busy").json() == {"busy": [f"{port}: a table map is probing"]}
    assert c.get("/firmware/printers/armed").json() == {"armed": {}}
    assert not [j for j in c.get("/jobs").json() if j.get("outcome") == "running"]
    gate.set()
    job.thread.join(10)
    assert c.get("/firmware/busy").json() == {"busy": []}
    task = fresh_task_runner.run("upload", "a flash", [["/bin/sleep", "2"]], port="/dev/ttyUSB0")
    assert c.get("/firmware/busy").json() == {"busy": [f"task {task.id} (a flash) is running"]}
    fresh_task_runner.cancel(task.id)
    links.stop_all()
