"""Every third-party module apothecary imports comes from a declared dependency."""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from importlib.metadata import packages_distributions
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _normal(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _declared() -> set[str]:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]
    requirements = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        requirements += group
    for group in config.get("dependency-groups", {}).values():
        requirements += [r for r in group if isinstance(r, str)]
    return {_normal(re.split(r"[\s<>=!~;\[]", r, maxsplit=1)[0]) for r in requirements}


def _imported_modules() -> dict[str, str]:
    """Each top-level module imported under apothecary/, with a file that imports it."""
    found: dict[str, str] = {}
    for source in sorted((ROOT / "apothecary").rglob("*.py")):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                found.setdefault(name.split(".")[0], str(source.relative_to(ROOT)))
    return found


def test_every_third_party_import_is_a_declared_dependency():
    declared = _declared()
    owners = packages_distributions()
    undeclared = {}
    for module, where in _imported_modules().items():
        if module == "apothecary" or module in sys.stdlib_module_names:
            continue
        distributions = {_normal(d) for d in owners.get(module, [])}
        if distributions and not distributions & declared:
            undeclared[module] = f"{sorted(distributions)} in {where}"
    assert not undeclared, f"imported, from a distribution pyproject.toml does not declare: {undeclared}"
