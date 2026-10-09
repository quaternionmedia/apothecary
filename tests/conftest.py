import sys
from pathlib import Path

# Ensure repository root is on sys.path so `import apothecary` works
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# Registered here rather than in tests/e2e/conftest.py, where these options were
# first defined. pytest loads a conftest for the paths named on the command line
# before it parses the arguments, so an option defined one directory further down
# than any named path does not exist yet when the parser meets it: the ordinary
# test command names `tests/` and `walkthrough`, and died on its own
# --start-server with "unrecognized arguments". Options live at the top; the
# fixtures that read them stay where they are used.
def pytest_addoption(parser):
    """Add custom pytest options for E2E tests."""
    parser.addoption(
        "--start-server",
        action="store_true",
        default=False,
        help="Automatically start the test server before E2E tests",
    )
    parser.addoption(
        "--server-port",
        action="store",
        default=None,
        help="Port for --start-server's server (default: a free one) or for yours (8765)",
    )
    parser.addoption(
        "--shard",
        action="store",
        default=None,
        metavar="K/N",
        help="Browser tests only: run the K-th of N shards, whole files balanced by "
        "tests/e2e/durations.json. CI runs the three shards on three runners.",
    )
    parser.addoption(
        "--slow",
        action="store_true",
        default=False,
        help="Also run tests marked slow: full CGAL renders, accuracy benches. CI passes it.",
    )
    parser.addoption(
        "--generate-docs",
        action="store_true",
        default=False,
        help=(
            "Enable doc-workflow screenshot/video capture (tests marked 'docs'). "
            "Off by default so a normal test run never writes to docs/generated/. "
            "Driven by `apothecary docs generate`, not meant to be passed by hand "
            "to a full test run."
        ),
    )


# `slow` marks what --slow's help names: full CGAL renders, accuracy benches. A
# test that renders a primitive of its own with the real OpenSCAD -- a cube,
# turned or cut -- is not one of those and stays unmarked: it is as quick as
# the tests around it, and it is the default run's check that OpenSCAD takes
# what the renderer writes.
def pytest_collection_modifyitems(config, items):
    if config.getoption("--slow"):
        return
    skip = pytest.mark.skip(reason="slow: run with --slow")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)


# --- firmware toolchain fakes ---------------------------------------------------
#
# A stand-in `arduino-cli` executable that answers the JSON queries the seam
# makes and records every long-running invocation, so firmware tests never
# need (or touch) a real toolchain, ~/.arduino15, or a serial port. The script
# and the helpers that read its log live in firmware_helpers.py; the fixtures
# that wire it in are here.


import pytest  # noqa: E402
from firmware_helpers import (  # noqa: E402
    _isolate_firmware_state,
    write_fake_arduino_cli,
    write_fake_cargo,
    write_fake_espflash,
)


@pytest.fixture(autouse=True)
def _no_background_renders(monkeypatch):
    """The app builds missing STLs in the background when it starts. A test that
    starts it (a TestClient used as a context manager, a live uvicorn) would
    render into the checkout from a worker thread that outlives the test and runs
    under the next test's environment. Off for every test; the one test of
    startup generation deletes the variable for itself. The browser suite's
    servers are started before any test and keep their own environment."""
    monkeypatch.setenv("APOTHECARY_SKIP_STL_GENERATION", "1")


@pytest.fixture(autouse=True, scope="session")
def _cache_outside_the_checkout(tmp_path_factory):
    """Node renders go to a cache of the run's own, never the checkout's."""
    import os

    previous = os.environ.get("APOTHECARY_CACHE_DIR")
    os.environ["APOTHECARY_CACHE_DIR"] = str(tmp_path_factory.mktemp("cache"))
    yield
    if previous is None:
        os.environ.pop("APOTHECARY_CACHE_DIR", None)
    else:
        os.environ["APOTHECARY_CACHE_DIR"] = previous


@pytest.fixture(autouse=True)
def _scripted_boards_answer_at_once(monkeypatch):
    """Every board in the unit suite is scripted and answers at once; waiting out
    a real board's silences (1.5 s settles, 5 s timeouts) was a minute of the run."""
    from apothecary.firmware import gcode

    monkeypatch.setattr(gcode.GcodeLink, "time_scale", 0.02)


# The guard on the process and the TestClient that says it is this machine are
# the repository's root conftest.py, so the walkthrough's doctests get them too.


@pytest.fixture
def fake_arduino_cli(tmp_path, monkeypatch):
    """Point the firmware seam at a scripted arduino-cli; yields the script path."""
    script = write_fake_arduino_cli(tmp_path / "arduino-cli")
    monkeypatch.setenv("ARDUINO_CLI", str(script))
    monkeypatch.setenv("APOTHECARY_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    # A person's own cargo or espflash, named in their environment, is not the test's.
    monkeypatch.setenv("CARGO", "none")
    monkeypatch.setenv("ESPFLASH", "none")
    from apothecary.firmware import toolchains

    # A host with the esp32 core installed has a bundled esptool under
    # ~/.arduino15; tests must not see it.
    monkeypatch.setattr(toolchains.Esptool, "detect", staticmethod(lambda: None))
    toolchains.reset_toolchains()
    _isolate_firmware_state(monkeypatch, tmp_path)
    yield script
    from apothecary.firmware import devices as _devices

    _devices.get_streams().stop_all()
    toolchains.reset_toolchains()


@pytest.fixture
def no_arduino_cli(tmp_path, monkeypatch):
    """The other environment: nothing installed anywhere."""
    monkeypatch.delenv("ARDUINO_CLI", raising=False)
    monkeypatch.setenv("APOTHECARY_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    monkeypatch.setenv("CARGO", "none")
    monkeypatch.setenv("ESPFLASH", "none")
    from apothecary.firmware import toolchains

    monkeypatch.setattr(toolchains.Esptool, "detect", staticmethod(lambda: None))
    toolchains.reset_toolchains()
    _isolate_firmware_state(monkeypatch, tmp_path)
    yield
    toolchains.reset_toolchains()


@pytest.fixture
def fake_rust(fake_arduino_cli, tmp_path, monkeypatch):
    """The scripted cargo and espflash beside the scripted arduino-cli, one simulated
    bench (its flashes in fake-boards.json there); yields (cargo, espflash)."""
    cargo = write_fake_cargo(tmp_path / "cargo")
    espflash = write_fake_espflash(tmp_path / "espflash")
    monkeypatch.setenv("CARGO", str(cargo))
    monkeypatch.setenv("ESPFLASH", str(espflash))
    yield cargo, espflash


@pytest.fixture
def fresh_task_runner(monkeypatch):
    from apothecary.firmware import tasks

    runner = tasks.TaskRunner()
    monkeypatch.setattr(tasks, "_RUNNER", runner)
    return runner
