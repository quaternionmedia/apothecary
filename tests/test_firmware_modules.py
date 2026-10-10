"""Toolchain modules: one interface, Arduino and Rust for the ESP32 behind it.

The rust-2026-10-08 plan's *Firmware in Rust*: each module says what it builds,
finds its tools (its variable, the tools dir, PATH), reports their status, and
builds and flashes a sketch as steps; the Rust esp32_blink lives with its part
and says what the Arduino one says. Against the scripted cargo and espflash
(tests/firmware_helpers.py); nothing here builds, flashes or fetches for real.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient
from firmware_helpers import fake_cli_calls

from apothecary.api import app
from apothecary.cli import cli
from apothecary.firmware import bindings, devices, service
from apothecary.firmware.modules import Tool, get_module, module_for, modules
from apothecary.firmware.modules.arduino import ArduinoModule
from apothecary.firmware.modules.rust_esp32 import (
    CARGO,
    ESPFLASH,
    RustEsp32Module,
    export_paths,
)
from apothecary.firmware.sketches import discover_sketches, find_sketch
from apothecary.firmware.toolchains import ToolchainError

ROOT = Path(__file__).resolve().parents[1]
RUST = "esp32_blink@rust-esp32"
ARDUINO = "esp32_blink@arduino"
PORT = "/dev/ttyFAKE0"


@pytest.fixture
def builds(tmp_path, monkeypatch):
    """Build output in a folder of the test's own, never the checkout's .cache/."""
    out = tmp_path / "builds"
    monkeypatch.setattr(service, "BUILD_ROOT", out)
    monkeypatch.setattr(bindings, "BUILD_ROOT", out)
    return out


def _wait(client, task_id):
    for _ in range(400):
        data = client.get(f"/firmware/tasks/{task_id}").json()
        if data["status"] != "running":
            return data
        time.sleep(0.02)
    raise AssertionError("task did not finish")


# --- the interface ----------------------------------------------------------------


def test_two_modules_each_saying_what_it_builds():
    """Arduino first, as the seam was; Rust for the ESP32 beside it. A later family or
    language is another entry here, not a change to the callers."""
    found = modules()
    assert [m.id for m in found] == ["arduino", "rust-esp32"]
    arduino, rust = found
    assert arduino.languages == ("arduino",) and "esp32" in arduino.families
    assert arduino.needs_board
    assert rust.languages == ("rust",) and rust.families == ("esp32",)
    assert not rust.needs_board
    assert get_module("rust-esp32") is rust
    with pytest.raises(ToolchainError, match="no toolchain module"):
        get_module("platformio")


def test_a_tool_is_found_by_its_variable_then_the_tools_dir_then_path(tmp_path, monkeypatch):
    tool = Tool("gizmo", env="GIZMO", managed="kit/bin/gizmo", command="gizmo")
    monkeypatch.setenv("APOTHECARY_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    monkeypatch.delenv("GIZMO", raising=False)
    assert tool.find() == (None, None)
    on_path = tmp_path / "bin" / "gizmo"
    on_path.parent.mkdir()
    on_path.write_text("#!/bin/sh\n")
    on_path.chmod(0o755)
    assert tool.find() == (on_path, "PATH")
    managed = tmp_path / "tools" / "kit" / "bin" / "gizmo"
    managed.parent.mkdir(parents=True)
    managed.write_text("#!/bin/sh\n")
    assert tool.find() == (managed, "tools dir")
    named = tmp_path / "mine"
    named.write_text("#!/bin/sh\n")
    monkeypatch.setenv("GIZMO", str(named))
    assert tool.find() == (named, "GIZMO")
    monkeypatch.setenv("GIZMO", "none")  # the suites' servers: none, whatever is installed
    assert tool.find() == (None, None)


# --- the Rust esp32_blink, beside the Arduino one --------------------------------


def test_the_rust_esp32_blink_lives_with_its_part_beside_the_arduino_one():
    """parts/esp32_blink/rust is a Cargo project whose firmware.json names its module;
    it is the sketch esp32_blink, as the Arduino one is, told apart by its id."""
    found = {s.id: s for s in discover_sketches(ROOT)}
    arduino, rust = found[ARDUINO], found[RUST]
    assert arduino.toolchain == "arduino" and arduino.fqbn == "esp32:esp32:esp32"
    assert rust.name == "esp32_blink" and rust.toolchain == "rust-esp32"
    assert rust.path == ROOT / "parts" / "esp32_blink" / "rust"
    assert rust.language == "rust" and rust.target == "esp32" and rust.fqbn is None
    assert rust.part == "esp32_blink" and rust.baud == arduino.baud == 115200
    assert rust.ino is None and rust.to_json()["ino"] is None
    assert json.loads((rust.path / "firmware.json").read_text())["toolchain"] == "rust-esp32"
    assert (rust.path / "Cargo.lock").is_file(), "its crates are vendored from its lockfile"
    # Each is named with its toolchain; the name the two share names neither.
    assert find_sketch(ARDUINO, ROOT).toolchain == "arduino"
    assert find_sketch(RUST, ROOT).toolchain == "rust-esp32"
    with pytest.raises(ValueError, match="esp32_blink@arduino, esp32_blink@rust-esp32"):
        find_sketch("esp32_blink", ROOT)
    assert find_sketch("footpedal", ROOT).id == "footpedal@arduino"  # a name one sketch has
    ids = [s.id for s in discover_sketches(ROOT)]
    assert ids.index(ARDUINO) + 1 == ids.index(RUST)


def test_the_rust_blink_says_what_the_arduino_one_says_at_the_same_baud_and_cadence():
    """The same lines on the wire: the hello, the chip line, a blink count each time
    the LED comes on, every 500 ms, the hello again every ten beats."""
    ino = (ROOT / "parts" / "esp32_blink" / "esp32_blink.ino").read_text()
    rust = (ROOT / "parts" / "esp32_blink" / "rust" / "src" / "main.rs").read_text()
    assert 'Serial.println("apothecary esp32_blink: hello")' in ino
    assert 'println!("apothecary esp32_blink: hello")' in rust
    assert '"chip: %s rev %d, %d core(s), %lu MHz, LED on GPIO %d\\n"' in ino
    assert '"chip: {} rev {}, {} core(s), {} MHz, LED on GPIO {}"' in rust
    assert 'Serial.printf("blink %lu\\n", ++beats)' in ino
    assert 'println!("blink {}", beats)' in rust
    for constant in ("PERIOD_MS", "ANNOUNCE_EVERY"):
        ino_value = ino.split(f"{constant} = ")[1].split(";")[0]
        rust_value = rust.split(f"{constant}: u32 = ")[1].split(";")[0]
        assert ino_value == rust_value, constant
    assert "Serial.begin(115200)" in ino
    assert json.loads((ROOT / "parts/esp32_blink/rust/firmware.json").read_text())["baud"] == 115200
    assert "#![no_std]" in rust and "esp_hal" in rust


def _copy_blink(tmp_path) -> Path:
    shutil.copytree(
        ROOT / "parts" / "esp32_blink",
        tmp_path / "parts" / "esp32_blink",
        ignore=shutil.ignore_patterns("target"),
    )
    return tmp_path


def test_each_implementation_hashes_its_own_sources(tmp_path, monkeypatch):
    """The Rust project sits inside the Arduino sketch's folder, and is not its source:
    an edit to main.rs is a change to the Rust one alone."""
    root = _copy_blink(tmp_path)
    monkeypatch.setattr(devices, "ROOT", root)
    arduino, rust = (find_sketch(i, root) for i in (ARDUINO, RUST))
    files = ArduinoModule().source_files(arduino, [rust.path])
    assert [f.name for f in files] == ["esp32_blink.ino"]
    before = devices.source_sha256(arduino), devices.source_sha256(rust)
    main = rust.path / "src" / "main.rs"
    main.write_text(main.read_text() + "\n// edited\n")
    after = devices.source_sha256(arduino), devices.source_sha256(rust)
    assert after[0] == before[0] and after[1] != before[1]
    (rust.path / "target" / "debug").mkdir(parents=True)
    (rust.path / "target" / "debug" / "junk").write_text("left by a cargo run by hand")
    assert devices.source_sha256(rust) == after[1]
    assert RUST not in {s.id for s in discover_sketches(root) if "target" in s.path.parts}


# --- building and flashing, as steps -----------------------------------------------


def test_a_rust_build_is_offline_in_its_folder_and_flashing_builds_first(fake_rust, builds):
    cargo, espflash = fake_rust
    sketch = find_sketch(RUST, ROOT)
    plan = service.build_plan(sketch, None)
    assert plan.cwd == sketch.path
    argv, check = plan.steps
    assert argv[:3] == [str(cargo), "build", "--release"]
    elf = builds / RUST / "xtensa-esp32-none-elf" / "release" / "esp32_blink"
    # The build's last step: no folder it was built in is in the image.
    assert check[1:4] == ["-m", "apothecary.firmware.image_paths", str(elf)]
    assert str(Path.home()) in check and str(sketch.path) in check
    assert "--offline" in argv
    assert argv[argv.index("--target-dir") + 1] == str(builds / RUST)
    assert plan.env["RUSTUP_AUTO_INSTALL"] == "0"
    flash = service.flash_plan(sketch, None, PORT)
    assert flash.steps[:2] == [argv, check]
    assert flash.steps[2] == [
        str(espflash),
        "flash",
        "--skip-update-check",
        "--non-interactive",
        "--chip",
        "esp32",
        "--port",
        PORT,
        "--baud",
        "460800",
        str(builds / RUST / "xtensa-esp32-none-elf" / "release" / "esp32_blink"),
    ]
    with pytest.raises(ValueError, match="takes no FQBN"):
        service.resolve_board(sketch, "esp32:esp32:esp32")
    assert service.resolve_board(sketch, None) is None
    # Each named with its toolchain, in the task's words too.
    assert service.compile_title(sketch, None) == f"Compile {RUST} (esp32)"
    assert service.upload_title(sketch, PORT) == f"Upload {RUST} → {PORT}"
    arduino = find_sketch(ARDUINO, ROOT)
    assert service.compile_title(arduino, "esp32:esp32:esp32") == (
        f"Compile {ARDUINO} (esp32:esp32:esp32)"
    )
    assert service.upload_title(arduino, PORT) == f"Upload {ARDUINO} → {PORT}"
    assert service.build_dir(arduino).name == ARDUINO


def test_the_tools_dir_cargo_runs_with_its_homes_there_and_the_vendored_crates(
    fake_arduino_cli, tmp_path, monkeypatch
):
    """Installed by apothecary, cargo's homes are the tools dir's, never ~/.cargo or
    ~/.rustup; crates.io is the vendored folder; espup's linker is on PATH."""
    tools = tmp_path / "tools" / "rust-esp32"
    monkeypatch.setenv("CARGO", "")
    managed = CARGO.managed_path()
    managed.parent.mkdir(parents=True)
    managed.write_text("#!/bin/sh\n")
    (tools / "vendor").mkdir()
    (tools / "export-esp.sh").write_text(
        'export LIBCLANG_PATH="/x/lib"\nexport PATH="/x/xtensa-esp-elf/bin:$PATH"\n'
    )
    monkeypatch.setenv("CARGO_REGISTRIES_ELSEWHERE_INDEX", "https://evil.example/index")
    monkeypatch.setenv("RUSTUP_DIST_SERVER", "https://evil.example")
    monkeypatch.setenv("RUSTC_WRAPPER", "sccache")
    monkeypatch.setenv("GITHUB_TOKEN", "a-person-s-token")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:3128")
    module = RustEsp32Module()
    sketch = find_sketch(RUST, ROOT)
    plan = module.build(sketch, None, tmp_path / "out")
    env = plan.env
    assert env["CARGO_HOME"] == str(tools / "cargo")
    assert env["RUSTUP_HOME"] == str(tools / "rustup")
    assert env["PATH"].split(":")[:2] == [str(managed.parent), "/x/xtensa-esp-elf/bin"]
    for gone in (
        "CARGO_REGISTRIES_ELSEWHERE_INDEX",
        "RUSTUP_DIST_SERVER",
        "RUSTC_WRAPPER",
        "GITHUB_TOKEN",
        "HTTPS_PROXY",
    ):
        assert gone not in env, gone
    argv = plan.steps[0]
    assert 'source.crates-io.replace-with="apothecary-vendored"' in argv
    assert f"source.apothecary-vendored.directory='{tools / 'vendor'}'" in argv
    assert export_paths('export PATH="/a:/b:$PATH"\n') == ["/a", "/b"]
    assert export_paths('$Env:PATH = "C:\\a;$Env:PATH"') == ["C:\\a"]


def test_status_says_each_module_and_its_tools(fake_rust, tmp_path):
    status = service.toolchain_status()
    assert status.arduino_cli_ok and status.ok  # the top level is Arduino's, as it was
    arduino, rust = status.toolchains
    assert arduino.id == "arduino" and arduino.ok and arduino.tools[0].name == "arduino-cli"
    assert rust.id == "rust-esp32" and rust.label == "Rust for the ESP32"
    assert rust.ok and [t.name for t in rust.tools] == ["cargo", "espflash"]
    cargo, espflash = rust.tools
    assert cargo.found_by == "CARGO" and cargo.version.startswith("cargo 1.99.0")
    assert espflash.version == "espflash 4.6.0"
    assert rust.install == "apothecary firmware install --rust-esp32"
    assert any(c["argv"] == ["+esp", "--version"] for c in fake_cli_calls(fake_rust[0]))


def test_status_without_rust_names_the_install(fake_arduino_cli):
    rust = service.toolchain_status().toolchains[1]
    assert not rust.ok
    assert "cargo not found (run `apothecary firmware install --rust-esp32`)" in rust.problems
    assert "espflash not found (run `apothecary firmware install --rust-esp32`)" in rust.problems


# --- the routes ------------------------------------------------------------------


def test_a_rust_sketch_compiles_and_uploads_through_the_routes(
    fake_rust, builds, fresh_task_runner
):
    """The Bench's routes, the sketch named by its id: a compile writes the ELF; an
    upload builds, flashes with espflash and records what the board should run --
    esp32_blink, as the Arduino one would be recorded, with its module and chip."""
    cargo, espflash = fake_rust
    client = TestClient(app)
    r = client.post(f"/firmware/sketches/{RUST}/compile", json={})
    assert r.status_code == 202, r.text
    assert r.json()["title"] == f"Compile {RUST} (esp32)"
    done = _wait(client, r.json()["id"])
    assert done["status"] == "succeeded", done
    assert any("Compiling esp32_blink" in line for line in done["lines"])
    elf = builds / RUST / "xtensa-esp32-none-elf" / "release" / "esp32_blink"
    assert elf.is_file()
    assert fake_cli_calls(cargo)[-1]["cwd"] == str(ROOT / "parts" / "esp32_blink" / "rust")

    r = client.post(f"/firmware/sketches/{RUST}/upload", json={"port": PORT})
    assert r.status_code == 202, r.text
    assert r.json()["title"] == f"Upload {RUST} → {PORT}"
    done = _wait(client, r.json()["id"])
    assert done["status"] == "succeeded", done
    assert any("Flashing has completed!" in line for line in done["lines"])
    assert fake_cli_calls(espflash)[-1][:2] == ["flash", "--skip-update-check"]
    record = devices.get_state().last_flash(PORT, PORT)
    assert record.sketch == "esp32_blink" and record.sketch_id == RUST
    assert record.toolchain == "rust-esp32" and record.target == "esp32" and record.fqbn is None
    assert record.build_sha256 == devices.file_sha256(elf)
    device = next(d for d in devices.detected_devices() if d.port == PORT)
    expected = devices.expected_firmware(device, builds)
    assert expected.record.sketch_id == RUST
    assert not (expected.source_changed or expected.build_changed or expected.sketch_missing)


def test_the_board_a_route_names_is_each_module_s_own(fake_rust, builds, fresh_task_runner):
    """An Arduino sketch is built for a board, and the request names it, as it always
    did; a Rust sketch builds for its chip and takes none. A name two sketches share
    is refused, naming both."""
    client = TestClient(app)
    r = client.post("/firmware/sketches/esp32_blink/compile", json={})
    assert r.status_code == 422 and "esp32_blink@arduino, esp32_blink@rust-esp32" in r.text
    r = client.post("/firmware/sketches/footpedal/compile", json={})
    assert r.status_code == 422 and "fqbn" in r.json()["detail"]
    r = client.post(f"/firmware/sketches/{RUST}/compile", json={"fqbn": "esp32:esp32:esp32"})
    assert r.status_code == 422 and "takes no FQBN" in r.json()["detail"]
    r = client.post("/firmware/sketches/esp32_blink@nowhere/compile", json={})
    assert r.status_code == 404


def test_the_status_route_and_the_toolchains_route_carry_every_module(fake_rust):
    client = TestClient(app)
    status = client.get("/firmware/status").json()
    assert status["arduino_cli_ok"] and status["ok"]
    assert [t["id"] for t in status["toolchains"]] == ["arduino", "rust-esp32"]
    assert status["toolchains"][1]["ok"]
    listed = client.get("/firmware/toolchains").json()
    assert [t["id"] for t in listed] == ["arduino", "rust-esp32"]
    sketches = client.get("/firmware/sketches").json()
    rust = next(s for s in sketches if s["id"] == RUST)
    assert rust["toolchain"] == "rust-esp32" and rust["name"] == "esp32_blink"
    assert rust["target"] == "esp32" and rust["fqbn"] is None


def test_a_module_install_is_a_task_and_an_unknown_module_is_not_found(
    fake_arduino_cli, monkeypatch, fresh_task_runner
):
    seen = []
    monkeypatch.setattr(
        service,
        "install_module",
        lambda module_id, log, force=False: (seen.append((module_id, force)), log("done")),
    )
    client = TestClient(app)
    r = client.post("/firmware/toolchains/rust-esp32/install", json={"force": True})
    assert r.status_code == 202 and r.json()["title"] == "Install Rust for the ESP32"
    assert _wait(client, r.json()["id"])["status"] == "succeeded"
    assert seen == [("rust-esp32", True)]
    assert client.post("/firmware/toolchains/platformio/install", json={}).status_code == 404


def test_a_node_bound_by_its_sketch_finds_the_board_either_implementation_ran_on(fake_rust, builds):
    """The garage's esp32_blink node names the sketch esp32_blink: flashed in Rust, the
    board running it is the node's, as it would be flashed from the Arduino one."""
    sketch = find_sketch(RUST, ROOT)
    service.record_upload(PORT, sketch, None)
    from apothecary.example_hierarchy import create_example_site

    rows = {r.path: r for r in bindings.bindings_for_site("garage", create_example_site())}
    row = rows["esp32_blink"]
    assert row.binding_source == "sketch" and row.device.port == PORT
    assert row.expected.record.sketch_id == RUST


# --- the CLI ---------------------------------------------------------------------


def test_the_cli_lists_compiles_and_names_the_rust_install(fake_rust, builds):
    runner = CliRunner()
    listed = runner.invoke(cli, ["firmware", "sketches"])
    assert listed.exit_code == 0, listed.output
    assert RUST in listed.output and "toolchain=rust-esp32 target=esp32" in listed.output
    built = runner.invoke(cli, ["firmware", "compile", RUST])
    assert built.exit_code == 0, built.output
    assert f"Compiled {RUST} for esp32" in built.output
    ambiguous = runner.invoke(cli, ["firmware", "compile", "esp32_blink"])
    assert ambiguous.exit_code != 0 and "esp32_blink is 2 sketches" in ambiguous.output
    refused = runner.invoke(cli, ["firmware", "compile", RUST, "--fqbn", "esp32:esp32:esp32"])
    assert refused.exit_code != 0 and "takes no FQBN" in refused.output
    validated = runner.invoke(cli, ["firmware", "validate"])
    assert "Rust for the ESP32 (rust for esp32)" in validated.output
    assert "✓ espflash 4.6.0: " in validated.output
    assert "✓ cargo 1.99.0-nightly (fake 2026-09-30): " in validated.output
    helped = runner.invoke(cli, ["firmware", "install", "--help"])
    assert "--rust-esp32" in helped.output


def test_check_says_each_module(fake_rust):
    """`apothecary check` names Rust for the ESP32 beside arduino-cli, installed or not."""
    shown = CliRunner().invoke(cli, ["check"])
    assert "✓ arduino-cli 9.9.9" in shown.output
    assert "✓ Rust for the ESP32 (cargo 1.99.0-nightly" in shown.output
    assert "Rust for the ESP32 can build, flash, find ports, listen, probe with espflash" in (
        shown.output
    )
    assert "Arduino can build, upload, find ports, listen, probe with esptool" in shown.output


def test_check_names_the_rust_install_when_it_is_missing(fake_arduino_cli):
    shown = CliRunner().invoke(cli, ["check"])
    assert (
        "Rust for the ESP32 not installed (optional: apothecary firmware install --rust-esp32)"
        in shown.output
    )
    assert "it would build, flash, find ports, listen" in shown.output


def test_install_rust_alone_leaves_arduino_cli_be(fake_arduino_cli, monkeypatch):
    calls = []
    monkeypatch.setattr(service, "install", lambda spec, log: calls.append("arduino"))
    monkeypatch.setattr(
        service, "install_module", lambda module_id, log, force=False: calls.append(module_id)
    )
    runner = CliRunner()
    assert runner.invoke(cli, ["firmware", "install", "--rust-esp32"]).exit_code == 0
    assert calls == ["rust-esp32"]
    calls.clear()
    assert runner.invoke(cli, ["firmware", "install", "--rust-esp32", "--esp32"]).exit_code == 0
    assert calls == ["arduino", "rust-esp32"]
    calls.clear()
    assert runner.invoke(cli, ["firmware", "install"]).exit_code == 0
    assert calls == ["arduino"]


def test_module_for_a_sketch_is_its_toolchain():
    assert module_for(find_sketch(RUST, ROOT)).id == "rust-esp32"
    assert module_for(find_sketch("footpedal", ROOT)).id == "arduino"
    assert ESPFLASH.env == "ESPFLASH" and CARGO.env == "CARGO"


def test_an_image_that_names_where_it_was_built_is_refused(tmp_path, capsys):
    """The Rust build's last step: no folder it was built in -- and so no user name --
    may be in the image, by either slash."""
    from apothecary.firmware import image_paths

    home = str(Path.home())
    clean = tmp_path / "clean.elf"
    clean.write_bytes(b"\x7fELF /sketch/esp32_blink/src/main.rs /rustup/lib/rustlib/src")
    assert image_paths.main([str(clean), "--refuse", home, "--refuse", str(ROOT)]) == 0
    assert "no build path in the image" in capsys.readouterr().out
    named = tmp_path / "named.elf"
    named.write_bytes(b"\x7fELF " + f"{home}/.cargo/registry/src/x.rs".encode())
    assert image_paths.main([str(named), "--refuse", home]) == 1
    assert f"build path in the image: {home}" in capsys.readouterr().out
    windows = tmp_path / "windows.elf"
    windows.write_bytes(b"\x7fELF C:/Users/pk/x.rs")
    assert image_paths.found_in(windows.read_bytes(), ["C:\\Users\\pk"]) == {
        "C:\\Users\\pk": [5]
    }
    assert image_paths.main([str(tmp_path / "missing.elf"), "--refuse", home]) == 2
