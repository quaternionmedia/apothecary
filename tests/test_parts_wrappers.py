from pathlib import Path

from apothecary.projects.registry import scan_projects


def test_all_known_parts_have_wrappers():
    root = Path(__file__).resolve().parents[1]
    projects = scan_projects(root)
    parts = [p for p in projects if p.kind == "part"]
    # Ensure at least some parts exist
    assert len(parts) >= 5
    # All scanned parts in this repo should have a wrapper module present
    missing = [p.name for p in parts if not p.wrapper]
    assert not missing, f"Missing wrappers for: {missing}"
