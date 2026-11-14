"""The demo started as a person starts it, for the browser tests that go round it:
``python -m apothecary serve --demo`` as a subprocess, the person's own folders temp
ones, and a guard on every Python process it starts that refuses, and writes down, any
opening of a serial device and any listing of the machine's real ports."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import httpx
import pytest

from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.parts.stl_renderer import get_renderer

# Every Python process the demo starts imports this first. Opening a serial device, by
# any route Python has, or listing the machine's ports is refused and written down.
GUARD = textwrap.dedent(
    r"""
    import builtins, io, os, re

    _LOG = os.environ.get("APOTHECARY_TEST_SERIAL_GUARD")
    _SERIAL = re.compile(r"^/dev/(tty(S|USB|ACM|AMA|FAKE)|cu\.|serial/)")


    def _note(what):
        with _open_file(_LOG, "a") as f:
            f.write(what + "\n")


    if _LOG:
        _open_file, _os_open = builtins.open, os.open

        def _path(path):
            try:
                return os.fsdecode(path)
            except TypeError:
                return ""

        def _guarded_os_open(path, *args, **kwargs):
            if _SERIAL.match(_path(path)):
                _note(f"os.open {_path(path)}")
                raise PermissionError(f"a serial port was opened: {_path(path)}")
            return _os_open(path, *args, **kwargs)

        def _guarded_open(file, *args, **kwargs):
            if not isinstance(file, int) and _SERIAL.match(_path(file)):
                _note(f"open {_path(file)}")
                raise PermissionError(f"a serial port was opened: {_path(file)}")
            return _open_file(file, *args, **kwargs)

        os.open = _guarded_os_open
        builtins.open = io.open = _guarded_open
        try:
            import serial.tools.list_ports as _ports

            def _comports(*args, **kwargs):
                _note("comports")
                raise PermissionError("the machine's serial ports were listed")

            _ports.comports = _comports
        except ImportError:
            pass
    """
)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def guarded_env(folder: Path) -> dict:
    """The environment a person's shell would have, with their folders temp ones and
    the guard on every Python process."""
    guard = folder / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(GUARD, encoding="utf-8")
    env = os.environ.copy()
    for key in [k for k in env if k.startswith(("APOTHECARY_", "FAKE_"))]:
        del env[key]  # nothing of the suite's own servers
    for key in ("ARDUINO_CLI", "ESPTOOL", "CARGO", "ESPFLASH"):
        env.pop(key, None)
    env.update(
        {
            "PYTHONPATH": os.pathsep.join(filter(None, [str(guard), env.get("PYTHONPATH")])),
            "APOTHECARY_TEST_SERIAL_GUARD": str(folder / "serial-touched.log"),
            # The person's own folders: the demo must leave them as they were.
            "APOTHECARY_STATE_DIR": str(folder / "person" / "state"),
            "APOTHECARY_TOOLS_DIR": str(folder / "person" / "tools"),
            "APOTHECARY_CACHE_DIR": str(folder / "person" / "cache"),
        }
    )
    renderer = get_renderer()
    if renderer.is_available:  # the OpenSCAD the person's own serve would use
        env["APOTHECARY_OPENSCAD"] = str(renderer.openscad_path)
    return env


def start_demo(folder: Path, env: dict) -> tuple[str, subprocess.Popen]:
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    log = (folder / "demo.log").open("w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "apothecary", "serve", "--demo", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            pytest.fail(f"the demo exited at start:\n{(folder / 'demo.log').read_text()}")
        try:
            if httpx.get(f"{url}/health", timeout=1.0).status_code == 200:
                return url, proc
        except httpx.TransportError:
            pass
        time.sleep(0.25)
    proc.terminate()
    pytest.fail(f"the demo did not answer within 60 s:\n{(folder / 'demo.log').read_text()}")


def stop(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
