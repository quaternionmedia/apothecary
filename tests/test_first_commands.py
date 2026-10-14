"""The README's first commands, run as a person runs them: the paths a newcomer takes
first -- `serve` for real, the startup STL build, the example scene, one part's STL,
`problems` and `parts checklist`."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from apothecary.cli import cli
from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.parts.stl_renderer import get_renderer

needs_openscad = pytest.mark.skipif(
    not get_renderer().is_available, reason="OpenSCAD is not installed here"
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _own_state(tmp_path: Path) -> dict:
    """A server's environment with every folder its own and every tool scripted or
    absent: nothing of the person's is read or written, and no serial port is opened."""
    (tmp_path / "pictures").mkdir()
    return {
        **os.environ,
        "APOTHECARY_STATE_DIR": str(tmp_path / "state"),
        "APOTHECARY_CACHE_DIR": str(tmp_path / "cache"),
        "APOTHECARY_TOOLS_DIR": str(tmp_path / "tools"),
        "APOTHECARY_PICTURE_ROOT": str(tmp_path / "pictures"),
        "APOTHECARY_SKIP_STL_GENERATION": "1",
        "APOTHECARY_SERIAL_ENGINE": "simulated",
        "APOTHECARY_ORCASLICER": "none",
        "ARDUINO_CLI": "none",
        "ESPTOOL": "none",
        "CARGO": "none",
        "ESPFLASH": "none",
    }


def test_serve_runs_for_real_and_answers_the_viewer(tmp_path):
    """`apothecary serve --port N` as a process of its own, as the README starts it: it
    says where the viewer is, and /viewer answers there."""
    port = _free_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "apothecary", "serve", "--port", str(port)],
        cwd=ROOT,
        env=_own_state(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 30
        while True:
            assert server.poll() is None, server.stdout.read()
            try:
                if httpx.get(f"{url}/health", timeout=1.0).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            assert time.monotonic() < deadline, "serve did not answer within 30 s"
            time.sleep(0.2)
        viewer = httpx.get(f"{url}/viewer", timeout=10.0, follow_redirects=True)
        assert viewer.status_code == 200
        assert "<title>" in viewer.text and "Apothecary" in viewer.text
    finally:
        server.terminate()
        said, _ = server.communicate(timeout=10)
    assert f"Viewer: http://127.0.0.1:{port}/viewer" in said


@needs_openscad
def test_the_server_builds_a_missing_stl_when_it_starts(monkeypatch, tmp_path):
    """Started with no STL for a part, the app builds it in the background, while
    /health answers."""
    from apothecary import api
    from apothecary.projects.parts.calibration_cube import DEFAULT as CUBE
    from apothecary.projects.registry import scan_projects

    built = tmp_path / "calibration_cube.stl"
    (cube,) = [p for p in scan_projects(ROOT) if p.kind == "part" and p.name == CUBE.name]
    monkeypatch.setattr(api, "scan_projects", lambda root: [cube])
    monkeypatch.setattr(type(CUBE), "get_stl_output_path", lambda self: built)
    monkeypatch.delenv("APOTHECARY_SKIP_STL_GENERATION", raising=False)
    with TestClient(api.app) as client:
        assert client.get("/health").status_code == 200
        deadline = time.monotonic() + 120
        while not api.app.state.stl_generation_task.done():
            assert time.monotonic() < deadline, "the startup build did not finish in 120 s"
            time.sleep(0.2)
    assert built.read_text(encoding="utf-8", errors="replace").startswith("solid")


def test_the_example_scene_renders_through_the_cli(tmp_path):
    """README: `apothecary render --scene-file examples/scene.json -o scene.scad`."""
    out = tmp_path / "scene.scad"
    done = subprocess.run(
        [sys.executable, "-m", "apothecary", "render", "--scene-file", "examples/scene.json"]
        + ["-o", str(out)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    scad = out.read_text(encoding="utf-8")
    assert "cube([10.0, 10.0, 5.0]" in scad
    assert "A JSON cube" in scad


@needs_openscad
def test_one_parts_stl_is_generated_through_the_cli(monkeypatch, tmp_path):
    """README: `apothecary parts generate-stl datum_core`, into a folder of the test's own
    rather than the checkout's."""
    from apothecary.projects.parts.datum_core import DEFAULT as CORE

    built = tmp_path / "datum_core.stl"
    monkeypatch.setattr(type(CORE), "get_stl_output_path", lambda self: built)
    result = CliRunner().invoke(cli, ["parts", "generate-stl", "datum_core", "--force"])
    assert result.exit_code == 0, result.output
    assert "datum_core: datum_core.stl in " in result.output
    assert built.read_text(encoding="utf-8", errors="replace").startswith("solid")


def test_problems_says_what_is_open_and_who_can_close_it():
    """README: `apothecary problems`, and narrowed to one owner."""
    from apothecary.spaces import problems

    found = problems()
    result = CliRunner().invoke(cli, ["problems"])
    assert result.exit_code == 0, result.output
    if not found:
        assert "nothing open matches that" in result.output
        return
    owners = sorted({p.owner for p in found})
    for owner in owners:
        assert f"{owner} can close these" in result.output
    assert f"{len(found)} open: " in result.output
    narrowed = CliRunner().invoke(cli, ["problems", "--owner", owners[0], "--detail"])
    assert narrowed.exit_code == 0, narrowed.output
    assert f"{owners[0]} can close these" in narrowed.output
    for other in owners[1:]:
        assert f"{other} can close these" not in narrowed.output


@needs_openscad
def test_parts_checklist_says_whether_a_part_is_ready():
    """`apothecary parts checklist calibration_cube`: its checks under its name and a
    verdict; it exits non-zero when, and only when, something blocks."""
    result = CliRunner().invoke(cli, ["parts", "checklist", "calibration_cube"])
    assert result.exit_code in (0, 1), result.output
    assert "calibration_cube" in result.output
    assert "ready to build" in result.output or "not ready: " in result.output
    assert ("blocking" in result.output) == (result.exit_code == 1), result.output
    refused = CliRunner().invoke(cli, ["parts", "checklist"])
    assert refused.exit_code != 0
    assert "Specify a part name or use --all" in refused.output
