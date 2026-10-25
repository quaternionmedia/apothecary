"""The tests share helpers through modules made for sharing, and nowhere else.

The browser tests reach the ring through tests/e2e/rings.py; garage, the status line
and a picture pinned there through tests/e2e/garage.py; the boards and ports their
servers simulate through tests/e2e/boards.py; the stated picture the views tests pin
through tests/views_helpers.py, its fixtures in the conftests. A copy kept in a test
file drifts from the others (a shorter wait, a cell read the other way round), and a
change is then made in many places; a test file that imports another's helpers runs
that file's module-level fixtures and setup as well, and breaks when it is renamed.
"""

import ast
from pathlib import Path

TESTS = Path(__file__).resolve().parent
E2E = TESTS / "e2e"

# The ring's helpers and constants, rings.py's alone.
HELPERS = {"_press", "_choose", "_ring_on", "_wedges", "_labels", "_ring_labels"}
CONSTANTS = {"WEDGES", "RING_MS", "PLACEMENT", "CELLS"}
# How the ring's cells are read wholesale.
READ = "querySelectorAll('#ring-overlay .wedge')]"

# What garage.py, boards.py and the browser conftest hold, under the names the test
# files kept their copies by.
SHARED = {
    "garage.py": {
        "_open_garage",
        "_open_viewer",
        "_select",
        "_status",
        "_said",
        "_attached",
        "_found",
        "_make",
        "_kept",
        "_y4m",
        "DRAWING",
        "HANDLE_AT",
    },
    "boards.py": {
        "_ended",
        "PRINTER",
        "BOARD",
        "DEVKIT",
        "NODE",
        "ARDUINO",
        "RUST",
        "LAYERS",
        "DWELL",
    },
    "windows.py": {"BENCH"},
    "conftest.py": {"leaves_garage_as_found", "fixture_picture", "drawing_camera_browser"},
}
# What views_helpers.py and the unit conftest hold.
VIEWS = {"world", "forget_cameras"}


def _defined(tree: ast.Module) -> list:
    """Each name a module defines at its top, with what it is."""
    found = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            found.append((node.name, f"def {node.name}"))
        if isinstance(node, ast.Assign):
            for target in node.targets:
                names = target.elts if isinstance(target, ast.Tuple) else [target]
                found += [(t.id, t.id) for t in names if isinstance(t, ast.Name)]
    return found


def _copies(path: Path) -> list:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = [what for name, what in _defined(tree) if name in HELPERS | CONSTANTS]
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and READ in node.value:
            found.append(f"reads the ring at line {node.lineno}")
    return found


def test_no_browser_test_keeps_a_ring_helper_of_its_own():
    copies = {
        path.name: _copies(path)
        for path in sorted(E2E.glob("*.py"))
        if path.name != "rings.py" and _copies(path)
    }
    assert copies == {}, "use tests/e2e/rings.py"


def test_no_browser_test_keeps_a_garage_or_board_helper_of_its_own():
    copies = {}
    for path in sorted(E2E.glob("test_*.py")):
        defined = _defined(ast.parse(path.read_text(encoding="utf-8")))
        for home, names in SHARED.items():
            kept = [what for name, what in defined if name in names]
            if kept:
                copies[path.name] = copies.get(path.name, []) + [f"{what}: {home}" for what in kept]
    assert copies == {}, "use the module named beside each"


def test_no_unit_test_keeps_the_views_world_of_its_own():
    copies = {
        path.name: kept
        for path in sorted(TESTS.glob("test_*.py"))
        if (
            kept := [
                what
                for name, what in _defined(ast.parse(path.read_text(encoding="utf-8")))
                if name in VIEWS
            ]
        )
    }
    assert copies == {}, "use tests/views_helpers.py and tests/conftest.py's world"


def test_no_test_imports_another_test_module():
    imports = {}
    for path in sorted(TESTS.rglob("test_*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            modules = []
            if isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            elif isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            for module in modules:
                if module.split(".")[-1].startswith("test_"):
                    imports.setdefault(str(path.relative_to(TESTS)), []).append(module)
    assert imports == {}, "share it through a helper module or a conftest instead"
