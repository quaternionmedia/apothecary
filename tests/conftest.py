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
        default="8765",
        help="Port for the test server (default: 8765)",
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


# --- firmware toolchain fakes ---------------------------------------------------
#
# A stand-in `arduino-cli` executable that answers the JSON queries the seam
# makes and records every long-running invocation, so firmware tests never
# need (or touch) a real toolchain, ~/.arduino15, or a serial port. The script
# and the helpers that read its log live in firmware_helpers.py; the fixtures
# that wire it in are here.


import pytest  # noqa: E402
import starlette.testclient as _st  # noqa: E402
from firmware_helpers import _isolate_firmware_state, write_fake_arduino_cli  # noqa: E402

import apothecary  # noqa: E402,F401  -- the guard, before any test connects anywhere

# The app answers this machine only (apothecary/stays_local.py). Starlette's
# TestClient presents itself as "testclient" at "testserver", which is
# nowhere; these tests run here, so what it presents is this machine.
_test_client_init = _st.TestClient.__init__


def _from_this_machine(
    self, app, base_url="http://127.0.0.1", *args, client=("127.0.0.1", 50000), **kwargs
):
    _test_client_init(self, app, base_url, *args, client=client, **kwargs)


_st.TestClient.__init__ = _from_this_machine


@pytest.fixture
def fake_arduino_cli(tmp_path, monkeypatch):
    """Point the firmware seam at a scripted arduino-cli; yields the script path."""
    script = write_fake_arduino_cli(tmp_path / "arduino-cli")
    monkeypatch.setenv("ARDUINO_CLI", str(script))
    monkeypatch.setenv("APOTHECARY_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
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
    from apothecary.firmware import toolchains

    monkeypatch.setattr(toolchains.Esptool, "detect", staticmethod(lambda: None))
    toolchains.reset_toolchains()
    _isolate_firmware_state(monkeypatch, tmp_path)
    yield
    toolchains.reset_toolchains()


@pytest.fixture
def fresh_task_runner(monkeypatch):
    from apothecary.firmware import tasks

    runner = tasks.TaskRunner()
    monkeypatch.setattr(tasks, "_RUNNER", runner)
    return runner
