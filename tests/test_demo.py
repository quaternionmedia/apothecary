"""`apothecary serve --demo`'s folder and seed (apothecary/demo.py).

The demo runs on a state folder of its own, never the person's ``~/.apothecary``
or their pins, and every port it has is the simulated engine's. These hold the
folder -- where it is, what is in it, that it is kept between runs and that
nothing is written outside it -- and the seed, printer_1's mainboard pinned to the
simulated Ender, with every real port refused. tests/e2e/test_the_demo.py goes
round each loop against the demo's own server.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner
from firmware_helpers import _isolate_firmware_state
from slicer_helpers import write_fake_orcaslicer

from apothecary import demo
from apothecary.cli.main import cli
from apothecary.cli.server import DEFAULT_PORT, PORT_ENV
from apothecary.projects.parts.skeleton import ROOT

PATHS = (
    "APOTHECARY_STATE_DIR",
    "APOTHECARY_PICTURE_ROOT",
    "APOTHECARY_TOOLS_DIR",
    "APOTHECARY_CACHE_DIR",
    "APOTHECARY_VARIANTS_REPO",
    "ARDUINO_CLI",
    "CARGO",
    "ESPFLASH",
)


@pytest.fixture
def person(tmp_path, monkeypatch):
    """A person's own folders, which the demo must leave as it found them: their
    state, their tools (with nothing installed) and their render cache."""
    folders = {name: tmp_path / name for name in ("state", "tools", "cache")}
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(folders["state"]))
    monkeypatch.setenv("APOTHECARY_TOOLS_DIR", str(folders["tools"]))
    monkeypatch.setenv("APOTHECARY_CACHE_DIR", str(folders["cache"]))
    monkeypatch.setenv("APOTHECARY_ORCASLICER", "none")
    return folders


def test_the_demo_folder_is_the_checkouts_cache_unless_the_cache_is_elsewhere(monkeypatch):
    monkeypatch.delenv("APOTHECARY_CACHE_DIR", raising=False)
    assert demo.demo_root() == ROOT / ".cache" / "demo"
    assert demo.shown(demo.demo_root()) == ".cache/demo"
    monkeypatch.setenv("APOTHECARY_CACHE_DIR", "/somewhere/else")
    assert demo.demo_root() == Path("/somewhere/else/demo")


def test_the_demo_runs_on_a_folder_of_its_own(person):
    made = demo.prepare()
    root = person["cache"] / "demo"
    assert made.root == root.resolve()
    for name in PATHS:
        where = Path(made.env[name])
        assert where.is_relative_to(made.root), (name, where)
        assert where.exists(), name
    home = Path.home() / ".apothecary"
    assert not any(Path(v).is_relative_to(home) for v in made.env.values() if v.startswith("/"))
    # Every port the simulated engine's; the scripted bench, its devkit on; no esptool.
    assert made.env["APOTHECARY_SERIAL_ENGINE"] == "simulated"
    assert made.env["APOTHECARY_SIMULATED_PRINTER"] == "idle"
    assert made.env["ESPTOOL"] == "none" and made.env["FAKE_DEVKIT"] == "1"
    for tool in ("ARDUINO_CLI", "CARGO", "ESPFLASH"):
        assert os.access(made.env[tool], os.X_OK), tool
    # Pictures beside the state, never inside it: the picture root refuses that.
    assert not Path(made.env["APOTHECARY_PICTURE_ROOT"]).is_relative_to(
        made.env["APOTHECARY_STATE_DIR"]
    )
    # The person's state and tools are as they were: nothing written there.
    assert not person["state"].exists() and not person["tools"].exists()
    assert sorted(p.name for p in person["cache"].iterdir()) == ["demo"]


def test_the_demo_is_kept_between_runs(person):
    first = demo.prepare()
    kept = Path(first.env["APOTHECARY_PICTURE_ROOT"]) / "captures" / "a.png"
    kept.parent.mkdir(parents=True)
    kept.write_bytes(b"a picture taken last time")
    variants = Path(first.env["APOTHECARY_VARIANTS_REPO"])
    saved = subprocess.run(
        ["git", "rev-parse", "--git-dir"], cwd=variants, capture_output=True, text=True
    )
    assert saved.returncode == 0, saved.stderr
    again = demo.prepare()
    assert again.root == first.root and again.env == first.env
    assert kept.read_bytes() == b"a picture taken last time"


def test_the_demo_slices_with_the_persons_orcaslicer_read_where_it_is(
    person, tmp_path, monkeypatch
):
    """Found as their own serve finds it, and named where it is: the demo's tools
    folder is its own, so it is named rather than looked for there."""
    orca = write_fake_orcaslicer(tmp_path / "theirs")
    monkeypatch.setenv("APOTHECARY_ORCASLICER", str(orca))
    made = demo.prepare()
    assert made.orcaslicer == orca and made.env["APOTHECARY_ORCASLICER"] == str(orca)
    monkeypatch.setenv("APOTHECARY_ORCASLICER", "none")
    made = demo.prepare()
    assert made.orcaslicer is None and "APOTHECARY_ORCASLICER" not in made.env


@pytest.mark.parametrize("failure", ["missing", "hung"])
def test_a_git_that_is_missing_or_does_not_answer_leaves_the_demo_without_saves(
    tmp_path, monkeypatch, failure
):
    """The demo's variants repository is made by git, each call given a time: a git that
    is not there, or does not answer in time, leaves the demo running without one."""
    calls = []

    def run(argv, **kwargs):
        calls.append(kwargs.get("timeout"))
        if failure == "missing":
            raise FileNotFoundError("git")
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))

    monkeypatch.setattr(demo.subprocess, "run", run)
    assert demo._variants_repo(tmp_path / "variants.git") is None
    assert calls and all(t == demo.GIT_TIMEOUT_S for t in calls)


def test_the_seed_refuses_outside_the_demo(monkeypatch):
    monkeypatch.delenv(demo.DEMO_ENV, raising=False)
    with pytest.raises(RuntimeError, match="demo's environment only"):
        demo.seed()


def test_the_seed_pins_printer_1s_mainboard_and_touches_no_real_port(person, monkeypatch, tmp_path):
    """printer_1's mainboard pinned to the simulated Ender, identified as a printer;
    pyserial is never asked to open or list a port."""
    import serial
    import serial.tools.list_ports

    from apothecary.firmware import devices, gcode, toolchains

    touched: list = []

    def refuse(*args, **kwargs):
        touched.append(args)
        raise AssertionError("the demo touched a real serial port")

    monkeypatch.setattr(serial.Serial, "open", refuse)
    monkeypatch.setattr(serial.tools.list_ports, "comports", refuse)
    made = demo.prepare()
    for key, value in made.env.items():
        monkeypatch.setenv(key, value)
    _isolate_firmware_state(monkeypatch, tmp_path)
    monkeypatch.setenv("APOTHECARY_STATE_DIR", made.env["APOTHECARY_STATE_DIR"])
    toolchains.reset_toolchains()
    links = gcode.PrinterLinks()
    monkeypatch.setattr(gcode, "_LINKS", links)
    try:
        identity = demo.seed()
        assert identity == "FAKESERIAL1"
        (pin,) = devices.get_state().bindings(demo.SITE)
        assert (pin.path, pin.identity) == (demo.BOARD, "FAKESERIAL1")
        printer = devices.known_device(demo.PRINTER)
        assert printer.printer.machine_type == "Simulated Ender"
        # Every port the demo has is the scripted bench's: the printer and the devkit.
        ports = [d.port for d in devices.detected_devices(fresh=True)]
        assert set(ports) == {"/dev/ttyFAKE0", demo.PRINTER, demo.DEVKIT}, ports
    finally:
        links.stop_all()
        toolchains.reset_toolchains()
    assert touched == []
    assert Path(made.env["APOTHECARY_STATE_DIR"], "firmware-state.json").exists()
    assert not person["state"].exists()


def test_serve_help_describes_the_demo_and_shows_the_defaults():
    said = CliRunner().invoke(cli, ["serve", "--help"], terminal_width=200).output
    assert "--demo" in said and "simulated Ender" in said and ".cache/demo" in said
    assert "Serve without --demo to leave it" in said
    assert "[default: 127.0.0.1]" in said
    assert f"[env var: {PORT_ENV}; default: {DEFAULT_PORT}]" in said
