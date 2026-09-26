"""``/firmware`` API and ``apothecary firmware`` CLI, driven against the fake arduino-cli."""

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


def test_firmware_page_renders(fake_arduino_cli):
    r = TestClient(app).get("/firmware")
    assert r.status_code == 200
    assert "Apothecary Firmware" in r.text and "/firmware/status" in r.text


def test_viewer_links_to_firmware(fake_arduino_cli):
    r = TestClient(app).get("/viewer/sites/garage")
    assert r.status_code == 200 and "/firmware" in r.text


def test_status_and_catalogue(fake_arduino_cli, fresh_task_runner):
    c = TestClient(app)
    status = c.get("/firmware/status").json()
    assert status["ok"] and status["arduino_cli_version"] == "9.9.9"
    assert status["active_task"] is None
    assert any(s["id"] == "esp32:esp32" for s in status["suggested_cores"])
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
    assert not status["ok"]
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


def test_cli_validate_reports_and_exits(fake_arduino_cli):
    result = CliRunner().invoke(cli, ["firmware", "validate"])
    assert result.exit_code == 0, result.output
    assert "arduino-cli 9.9.9" in result.output and "arduino:avr@1.8.8" in result.output


def test_cli_validate_missing_toolchain(no_arduino_cli):
    result = CliRunner().invoke(cli, ["firmware", "validate"])
    assert result.exit_code == 1
    assert "not installed" in result.output
    as_json = CliRunner().invoke(cli, ["firmware", "validate", "--json-out"])
    assert '"arduino_cli_ok": false' in as_json.output


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
    assert "Compiled footpedal for arduino:avr:uno" in r.output
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
    assert "Uploaded footpedal (arduino:avr:nano) to /dev/ttyFAKE0" in r.output
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
