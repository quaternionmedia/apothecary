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
