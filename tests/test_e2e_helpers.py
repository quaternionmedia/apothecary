"""The browser tests reach the ring through tests/e2e/rings.py alone: a copy of how it
opens, reads or presses kept in a test file drifts from the others (a shorter wait, a
cell read the other way round), and a change to the ring is then made in many places.
"""

import ast
from pathlib import Path

E2E = Path(__file__).resolve().parent / "e2e"

# The ring's helpers and constants, rings.py's alone.
HELPERS = {"_press", "_choose", "_ring_on", "_wedges", "_labels", "_ring_labels"}
CONSTANTS = {"WEDGES", "RING_MS", "PLACEMENT", "CELLS"}
# How the ring's cells are read wholesale.
READ = "querySelectorAll('#ring-overlay .wedge')]"


def _copies(path: Path) -> list:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in HELPERS:
            found.append(f"def {node.name}")
        if isinstance(node, ast.Assign):
            found += [t.id for t in node.targets if isinstance(t, ast.Name) and t.id in CONSTANTS]
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
