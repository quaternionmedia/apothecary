"""Firmware seam: models, sketch discovery, toolchain wrappers, installer, task runner."""

import hashlib
import io
import json
import tarfile
import time
import zipfile
from pathlib import Path

import pytest
from firmware_fakes import fake_cli_calls

from apothecary.firmware import installer, service
from apothecary.firmware.models import (
    CompileRequest,
    EsptoolFlashRequest,
    UploadRequest,
    validate_core_id,
    validate_fqbn,
    validate_port,
)
from apothecary.firmware.sketches import discover_sketches, find_sketch
from apothecary.firmware.tasks import TaskBusy, TaskRunner, TaskStatus, stream
from apothecary.firmware.toolchains import (
    ADDITIONAL_URLS,
    ArduinoCli,
    Esptool,
    ToolchainError,
    get_arduino_cli,
    tools_dir,
)

ROOT = Path(__file__).resolve().parents[1]


# --- models ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "fqbn", ["arduino:avr:uno", "esp32:esp32:esp32", "arduino:avr:nano:cpu=atmega328old"]
)
def test_valid_fqbn(fqbn):
    assert validate_fqbn(fqbn) == fqbn


@pytest.mark.parametrize("bad", ["uno", "rm -rf /", "arduino:avr", "a:b:c; echo", ""])
def test_invalid_fqbn(bad):
    with pytest.raises(ValueError):
        validate_fqbn(bad)


@pytest.mark.parametrize("port", ["/dev/ttyUSB0", "/dev/cu.usbserial-1420", "COM3"])
def test_valid_port(port):
    assert validate_port(port) == port


@pytest.mark.parametrize("bad", ["ttyUSB0", "/dev/tty USB0", "COM", "/dev/ttyUSB0 && reboot"])
def test_invalid_port(bad):
    with pytest.raises(ValueError):
        validate_port(bad)


def test_core_id_validation():
    assert validate_core_id("esp32:esp32") == "esp32:esp32"
    with pytest.raises(ValueError):
        validate_core_id("esp32")


def test_request_models_reject_bad_input():
    with pytest.raises(ValueError):
        CompileRequest(fqbn="nope")
    with pytest.raises(ValueError):
        UploadRequest(fqbn="arduino:avr:uno", port="not-a-port")
    with pytest.raises(ValueError):
        EsptoolFlashRequest(port="/dev/ttyUSB0", images=[{"offset": "1000", "path": "x.bin"}])
    with pytest.raises(ValueError):
        EsptoolFlashRequest(
            port="/dev/ttyUSB0", chip="esp32; rm", images=[{"offset": "0x0", "path": "x.bin"}]
        )


# --- sketches -------------------------------------------------------------------


def _make_sketch(root: Path, rel: str, sidecar: dict | None = None) -> Path:
    folder = root / "parts" / rel
    folder.mkdir(parents=True)
    (folder / f"{folder.name}.ino").write_text("void setup(){} void loop(){}")
    if sidecar is not None:
        (folder / "firmware.json").write_text(json.dumps(sidecar))
    return folder


def test_discover_sketches_layout_and_sidecar(tmp_path):
    _make_sketch(
        tmp_path, "pedal", {"fqbn": "arduino:avr:uno", "libraries": ["FastLED"], "note": "hi"}
    )
    _make_sketch(tmp_path, "rc/plow/controller")  # nested, no sidecar
    stray = tmp_path / "parts" / "stray"
    stray.mkdir()
    (stray / "other.ino").write_text("")  # name mismatch: not a sketch
    sub = tmp_path / "parts" / "vendored"
    sub.mkdir()
    (sub / ".git").write_text("gitdir: ../../.git/modules/vendored")
    (sub / "vendored.ino").write_text("")  # inside a submodule: skipped

    found = discover_sketches(tmp_path)
    assert [s.name for s in found] == ["controller", "pedal"]
    pedal = next(s for s in found if s.name == "pedal")
    assert pedal.fqbn == "arduino:avr:uno" and pedal.libraries == ["FastLED"] and pedal.note == "hi"
    assert pedal.part == "pedal"
    controller = next(s for s in found if s.name == "controller")
    assert controller.fqbn is None and controller.part == "rc"


def test_find_sketch_by_name_or_path(tmp_path):
    folder = _make_sketch(tmp_path, "pedal")
    assert find_sketch("pedal", tmp_path).path == folder
    assert find_sketch(str(folder), tmp_path).name == "pedal"
    assert find_sketch(str(folder / "pedal.ino"), tmp_path).name == "pedal"
    assert find_sketch("missing", tmp_path) is None
    assert find_sketch(str(tmp_path), tmp_path) is None  # outside parts/


def test_repo_ships_footpedal_sketch():
    names = {s.name for s in discover_sketches(ROOT)}
    assert "footpedal" in names
    footpedal = find_sketch("footpedal", ROOT)
    assert footpedal.fqbn == "arduino:avr:uno"
    assert "FastLED" in footpedal.libraries


# --- toolchains -----------------------------------------------------------------


def test_tools_dir_override(monkeypatch, tmp_path):
    monkeypatch.setenv("APOTHECARY_TOOLS_DIR", str(tmp_path / "t"))
    assert tools_dir() == tmp_path / "t"
    monkeypatch.delenv("APOTHECARY_TOOLS_DIR")
    assert tools_dir() == Path.home() / ".apothecary" / "tools"


def test_arduino_cli_detect_prefers_env_then_tools_dir_then_path(
    fake_arduino_cli, tmp_path, monkeypatch
):
    assert ArduinoCli.detect() == fake_arduino_cli
    monkeypatch.delenv("ARDUINO_CLI")
    assert ArduinoCli.detect() is None
    managed = tmp_path / "tools" / "arduino-cli" / "arduino-cli"
    managed.parent.mkdir(parents=True)
    managed.write_text("#!/bin/sh\n")
    assert ArduinoCli.detect() == managed


def test_arduino_cli_queries_parse_json(fake_arduino_cli):
    cli = get_arduino_cli()
    assert cli.is_available and cli.version() == "9.9.9"
    boards = cli.board_list()
    assert [b.port for b in boards] == ["/dev/ttyFAKE0", "/dev/ttyFAKE1"]
    assert boards[0].fqbn == "arduino:avr:uno" and boards[0].vid == "0x2341"
    assert boards[1].board_name is None
    assert [b.fqbn for b in cli.board_listall()] == ["arduino:avr:nano", "arduino:avr:uno"]
    cores = cli.core_list()
    assert (
        cores[0].id == "arduino:avr"
        and cores[0].installed == "1.8.8"
        and cores[0].name == "Arduino AVR Boards"
    )


def test_arduino_cli_argv_builders(fake_arduino_cli, tmp_path):
    cli = get_arduino_cli()
    sketch = tmp_path / "s"
    assert cli.compile_argv(sketch, "arduino:avr:uno")[1:] == [
        "compile",
        "--fqbn",
        "arduino:avr:uno",
        "--warnings",
        "default",
        str(sketch),
    ]
    up = cli.upload_argv(sketch, "arduino:avr:uno", "/dev/ttyUSB0", tmp_path / "b")
    assert up[1:] == [
        "upload",
        "--fqbn",
        "arduino:avr:uno",
        "--port",
        "/dev/ttyUSB0",
        "--input-dir",
        str(tmp_path / "b"),
        str(sketch),
    ]
    esp = cli.core_install_argv("esp32:esp32")
    assert esp[1:] == [
        "core",
        "install",
        "esp32:esp32",
        "--additional-urls",
        ADDITIONAL_URLS["esp32"],
    ]
    assert "--additional-urls" not in cli.core_install_argv("arduino:avr")
    assert (
        cli.core_update_index_argv(["esp32:esp32", "esp8266:esp8266"])[-1]
        == f"{ADDITIONAL_URLS['esp32']},{ADDITIONAL_URLS['esp8266']}"
    )
    assert cli.lib_install_argv(["FastLED", "Control Surface"])[1:] == [
        "lib",
        "install",
        "FastLED",
        "Control Surface",
    ]


def test_arduino_cli_missing_raises(no_arduino_cli):
    cli = get_arduino_cli()
    assert not cli.is_available and cli.version() is None
    with pytest.raises(ToolchainError):
        cli.board_list()


def test_esptool_argv_and_missing(tmp_path):
    tool = Esptool(argv_prefix=["/fake/esptool"])
    argv = tool.write_flash_argv(
        "/dev/ttyUSB0",
        [("0x1000", tmp_path / "boot.bin"), ("0x10000", tmp_path / "app.bin")],
        chip="esp32",
        baud=921600,
    )
    assert argv == [
        "/fake/esptool",
        "--chip",
        "esp32",
        "--port",
        "/dev/ttyUSB0",
        "--baud",
        "921600",
        "write_flash",
        "0x1000",
        str(tmp_path / "boot.bin"),
        "0x10000",
        str(tmp_path / "app.bin"),
    ]
    assert tool.erase_argv("/dev/ttyUSB0")[-1] == "erase_flash"
    missing = Esptool(argv_prefix=[])
    assert not missing.is_available
    with pytest.raises(ToolchainError):
        missing.erase_argv("/dev/ttyUSB0")


# --- installer ------------------------------------------------------------------


@pytest.mark.parametrize(
    "system,machine,expected",
    [
        ("Linux", "x86_64", "arduino-cli_1.5.1_Linux_64bit.tar.gz"),
        ("Linux", "aarch64", "arduino-cli_1.5.1_Linux_ARM64.tar.gz"),
        ("Linux", "armv7l", "arduino-cli_1.5.1_Linux_ARMv7.tar.gz"),
        ("Darwin", "arm64", "arduino-cli_1.5.1_macOS_ARM64.tar.gz"),
        ("Darwin", "x86_64", "arduino-cli_1.5.1_macOS_64bit.tar.gz"),
        ("Windows", "AMD64", "arduino-cli_1.5.1_Windows_64bit.zip"),
    ],
)
def test_asset_name(system, machine, expected):
    assert installer.asset_name("1.5.1", system, machine) == expected


def test_asset_name_unsupported():
    with pytest.raises(ToolchainError):
        installer.asset_name("1.5.1", "Plan9", "mips")


def _targz(name: str, content: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo(name)
        info.size = len(content)
        info.mode = 0o755
        tf.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def test_extract_binary_tar_and_zip(tmp_path):
    out = installer.extract_binary(
        _targz("arduino-cli", b"#!/bin/sh\necho hi\n"), "x.tar.gz", tmp_path / "t"
    )
    assert out.read_bytes().startswith(b"#!/bin/sh") and out.stat().st_mode & 0o111
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("arduino-cli.exe", b"MZ")
        zf.writestr("LICENSE.txt", b"...")
    if (
        installer._exe("arduino-cli") == "arduino-cli"
    ):  # POSIX: expect the posix name, so this zip lacks it
        with pytest.raises(ToolchainError):
            installer.extract_binary(buf.getvalue(), "x.zip", tmp_path / "z")


def test_installer_downloads_verifies_and_smoke_tests(tmp_path, monkeypatch):
    import sys

    from firmware_fakes import FAKE_ARDUINO_CLI

    archive = _targz(
        "arduino-cli",
        FAKE_ARDUINO_CLI.replace("#!/usr/bin/env python3", f"#!{sys.executable}", 1).encode(),
    )
    name = installer.asset_name("1.5.1")
    sha = hashlib.sha256(archive).hexdigest()
    urls = []

    def fetch(url):
        urls.append(url)
        if url.endswith("/releases/latest"):
            return json.dumps({"tag_name": "v1.5.1"}).encode()
        if url.endswith("checksums.txt"):
            return f"{sha}  {name}\nabc  other.deb\n".encode()
        assert url.endswith(name)
        return archive

    log = []
    inst = installer.ArduinoCliInstaller(
        installer.InstallSpec(dest=tmp_path / "dest"), log=log.append, fetch=fetch
    )
    path = inst.install_binary()
    assert path == tmp_path / "dest" / installer._exe("arduino-cli")
    assert ArduinoCli(path).version() == "9.9.9"
    assert any("SHA-256 verified" in line for line in log) and any(
        "9.9.9 OK" in line for line in log
    )
    assert urls[0].endswith("/releases/latest")

    # Second run is a no-op without --force.
    log.clear()
    assert inst.install_binary() == path
    assert any("already installed" in line for line in log)


def test_installer_rejects_bad_checksum(tmp_path):
    archive = _targz("arduino-cli", b"x")
    name = installer.asset_name("1.5.1")

    def fetch(url):
        if url.endswith("checksums.txt"):
            return f"{'0' * 64}  {name}\n".encode()
        return archive

    inst = installer.ArduinoCliInstaller(
        installer.InstallSpec(version="1.5.1", dest=tmp_path / "d"), fetch=fetch
    )
    with pytest.raises(ToolchainError, match="checksum mismatch"):
        inst.install_binary()
    assert not (tmp_path / "d").exists()


def test_resolve_version_pins_or_resolves_latest():
    assert installer.resolve_version("v1.2.3", fetch=lambda _u: b"") == "1.2.3"
    assert (
        installer.resolve_version("latest", fetch=lambda _u: b'{"tag_name": "v2.0.0"}') == "2.0.0"
    )


# --- tasks -----------------------------------------------------------------------


def _wait(task, timeout=5.0):
    deadline = time.time() + timeout
    while task.status == TaskStatus.running and time.time() < deadline:
        time.sleep(0.02)
    return task


def test_stream_feeds_lines_and_returns_exit_code(fake_arduino_cli):
    lines = []
    rc = stream([str(fake_arduino_cli), "compile", "ok"], lines.append)
    assert rc == 0 and lines[0].startswith("$ ") and lines[1] == "fake compile ok"
    assert stream([str(fake_arduino_cli), "compile", "FAIL"], lines.append) == 1
    assert stream(["/nonexistent/binary"], lines.append) == 127


def test_task_runner_runs_steps_and_stops_on_failure(fake_arduino_cli):
    runner = TaskRunner()
    task = _wait(
        runner.run(
            "compile",
            "ok",
            [[str(fake_arduino_cli), "compile", "a"], [str(fake_arduino_cli), "upload", "b"]],
        )
    )
    assert task.status == TaskStatus.succeeded and task.returncode == 0
    assert "fake compile a" in task.lines and "fake upload b" in task.lines
    assert task.snapshot(since=2)["lines"] == task.lines[2:]

    task = _wait(
        runner.run(
            "compile",
            "fail",
            [
                [str(fake_arduino_cli), "compile", "FAIL"],
                [str(fake_arduino_cli), "upload", "never"],
            ],
        )
    )
    assert task.status == TaskStatus.failed and task.returncode == 1
    assert not any("upload never" in line for line in task.lines)
    assert [t.id for t in runner.list()] == [task.id, runner.list()[1].id]


def test_task_runner_refuses_concurrent_tasks(tmp_path):
    slow = tmp_path / "slow.sh"
    slow.write_text("#!/bin/sh\nsleep 2\n")
    slow.chmod(0o755)
    runner = TaskRunner()
    first = runner.run("x", "slow", [[str(slow)]])
    with pytest.raises(TaskBusy):
        runner.run("x", "second", [["true"]])
    assert runner.active is first
    assert runner.cancel(first.id)
    assert first.status == TaskStatus.cancelled and runner.active is None


def test_task_runner_callable_logs_and_reports_errors():
    runner = TaskRunner()
    ok = _wait(runner.run_callable("install", "ok", lambda log: log("hello")))
    assert ok.status == TaskStatus.succeeded and ok.lines == ["hello"]

    def boom(log):
        log("starting")
        raise ToolchainError("nope")

    bad = _wait(runner.run_callable("install", "bad", boom))
    assert bad.status == TaskStatus.failed and bad.lines == ["starting", "ERROR: nope"]


# --- service ---------------------------------------------------------------------


def test_service_status_with_and_without_toolchain(fake_arduino_cli):
    status = service.toolchain_status()
    assert status.ok and status.arduino_cli_version == "9.9.9"
    assert [c.id for c in status.cores] == ["arduino:avr"]
    assert not status.esptool_ok and any("esptool" in p for p in status.problems)


def test_service_status_missing(no_arduino_cli):
    status = service.toolchain_status()
    assert not status.ok and any("firmware install" in p for p in status.problems)


def test_service_resolve_fqbn_and_port(fake_arduino_cli, tmp_path):
    sketch = find_sketch("footpedal", ROOT)
    assert service.resolve_fqbn(sketch, None) == "arduino:avr:uno"
    assert service.resolve_fqbn(sketch, "esp32:esp32:esp32") == "esp32:esp32:esp32"
    with pytest.raises(ToolchainError, match="several boards"):
        service.resolve_port(None)  # the fake reports two ports
    assert service.resolve_port("/dev/ttyUSB9") == "/dev/ttyUSB9"


def test_service_upload_compiles_first(fake_arduino_cli):
    sketch = find_sketch("footpedal", ROOT)
    steps = service.upload_steps(sketch, "arduino:avr:uno", "/dev/ttyUSB0")
    assert steps[0][1] == "compile" and steps[1][1] == "upload"
    assert (
        steps[0][steps[0].index("--build-path") + 1] == steps[1][steps[1].index("--input-dir") + 1]
    )


def test_service_install_runs_cores_and_libraries(fake_arduino_cli, tmp_path, monkeypatch):
    monkeypatch.setattr(
        installer.ArduinoCliInstaller, "install_binary", lambda self: fake_arduino_cli
    )
    monkeypatch.setattr(service, "default_config_exists", lambda: True)
    spec = installer.InstallSpec(cores=["esp32:esp32"], libraries=["FastLED"])
    status = service.install(spec, lambda _line: None)
    assert status.ok
    calls = fake_cli_calls(fake_arduino_cli)
    assert ["core", "update-index", "--additional-urls", ADDITIONAL_URLS["esp32"]] in calls
    assert [
        "core",
        "install",
        "esp32:esp32",
        "--additional-urls",
        ADDITIONAL_URLS["esp32"],
    ] in calls
    assert ["lib", "install", "FastLED"] in calls


def test_resolve_image_path_confined_to_repo(tmp_path):
    (tmp_path / "fw.bin").write_bytes(b"\0")
    assert service.resolve_image_path("fw.bin", tmp_path) == tmp_path / "fw.bin"
    with pytest.raises(ToolchainError, match="inside the repository"):
        service.resolve_image_path("../etc/passwd", tmp_path)
    with pytest.raises(ToolchainError, match="not found"):
        service.resolve_image_path("missing.bin", tmp_path)
