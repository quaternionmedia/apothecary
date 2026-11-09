"""The borders docs/boundaries.md states, held against the package: the layer each unit
is in, the imports that reach up a layer, and the one place each package from another
repository or an optional install enters through. The page is the statement; this
reads its tables and checks the code against them."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "boundaries.md"
PACKAGE = ROOT / "apothecary"
TOP_LEVEL = ("apothecary/", "crates/", "docs/", "governance/", "parts/", "templates/")
TOP_LEVEL += ("tests/", "walkthrough/", ".github/")


def _table(heading: str) -> list[list[str]]:
    """The rows of the first table under ``heading``, each cell's backticks dropped."""
    text = PAGE.read_text(encoding="utf-8")
    start = re.search(rf"^#+ {re.escape(heading)}$", text, re.M)
    assert start, f"docs/boundaries.md has no heading {heading!r}"
    assert len(re.findall(rf"^#+ {re.escape(heading)}$", text, re.M)) == 1, f"two {heading!r}"
    rows = []
    for line in text[start.end() :].splitlines():
        if line.startswith("#"):
            break
        if not line.startswith("|"):
            if rows:
                break
            continue
        cells = [c.strip().replace("`", "") for c in line.strip().strip("|").split("|")]
        if not set("".join(cells)) <= set("-: "):
            rows.append(cells)
    assert rows, f"no table under {heading!r}"
    return rows[1:]  # the header row


def _module(path: Path) -> str:
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _is_module(name: str) -> bool:
    path = ROOT.joinpath(*name.split("."))
    return path.with_suffix(".py").is_file() or (path / "__init__.py").is_file()


def _imported(path: Path, at_import: bool = False) -> set[str]:
    """Every module ``path`` imports, at the top or inside a function (``at_import``: at
    the top alone), by a statement, by ``import_module``/``__import__``, by a string that
    names a module of the package, or by an attribute of the name ``apothecary``."""
    module = _module(path)
    package = module.split(".") if path.name == "__init__.py" else module.split(".")[:-1]
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr)}
    functions = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
    later = {id(n) for f in ast.walk(tree) if isinstance(f, functions) for n in ast.walk(f)}
    found = set()
    for node in ast.walk(tree):
        if at_import and id(node) in later:
            continue
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = ".".join(package[: len(package) - node.level + 1] + ([base] if base else []))
            for alias in node.names:
                name = f"{base}.{alias.name}"
                found.add(name if _is_module(name) else base)
        elif isinstance(node, ast.Attribute) and getattr(node.value, "id", "") == "apothecary":
            name = f"apothecary.{node.attr}"
            found.add(name if _is_module(name) else "apothecary")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                for unit in re.findall(r"\bapothecary\.(\w+)", node.value):
                    if _is_module(f"apothecary.{unit}"):
                        found.add(f"apothecary.{unit}")
        elif isinstance(node, ast.Call):
            callee = getattr(node.func, "attr", getattr(node.func, "id", ""))
            if callee not in ("import_module", "__import__"):
                continue
            words = (
                ("name", "package")
                if callee == "import_module"
                else ("name", "", "", "fromlist", "level")
            )
            given = dict(zip(words, node.args, strict=False)) | {
                k.arg: k.value for k in node.keywords
            }
            name = getattr(given.get("name"), "value", None)
            if not isinstance(name, str):
                continue
            level = len(name) - len(name.lstrip(".")) or getattr(given.get("level"), "value", 0)
            if level:
                within = getattr(given.get("package"), "value", None)
                base = within.split(".") if within else package
                name = ".".join(base[: len(base) - level + 1] + [name.lstrip(".")])
            found.add(name)
            for item in getattr(given.get("fromlist"), "elts", []):
                if _is_module(f"{name}.{getattr(item, 'value', '')}"):
                    found.add(f"{name}.{item.value}")
    return found


def _sources() -> list[Path]:
    return sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)


def _unit(module: str) -> str:
    """``apothecary`` for the package's own ``__init__``, else its first name below it."""
    parts = module.split(".")
    return parts[1] if len(parts) > 1 else parts[0]


def _layers() -> dict[str, int]:
    layer = {}
    for number, units, _what in _table("The layers"):
        for unit in units.split(", "):
            assert unit not in layer, f"{unit} is in two layers"
            layer[unit] = int(number)
    return layer


def _edges(at_import: bool = False) -> set[tuple[str, str, str]]:
    edges = set()
    for path in _sources():
        here = _unit(_module(path))
        for name in _imported(path, at_import):
            if name.split(".")[0] == "apothecary" and _unit(name) != here:
                edges.add((here, _unit(name), str(path.relative_to(ROOT))))
    return edges


def test_every_unit_of_the_package_is_in_one_layer():
    units = {_unit(_module(path)) for path in _sources()}
    layer = _layers()
    assert sorted(units - set(layer)) == [], "a unit docs/boundaries.md does not place"
    assert sorted(set(layer) - units) == [], "a unit docs/boundaries.md places that is gone"


def test_an_import_reaches_up_a_layer_only_where_the_page_says():
    layer = _layers()
    upward = {(a, b, where) for a, b, where in _edges() if layer[b] > layer[a]}
    listed = {(row[0], row[1], row[2]) for row in _table("Where an import reaches up")}
    assert sorted(upward - listed) == [], "an import reaching up that the page does not list"
    assert sorted(listed - upward) == [], "a reach the page lists that the code no longer has"


def test_an_import_reaches_up_at_import_time_only_where_the_page_says():
    layer = _layers()
    upward = {(a, b, where) for a, b, where in _edges(at_import=True) if layer[b] > layer[a]}
    rows = _table("Where an import reaches up")
    assert sorted(upward ^ {tuple(r[:3]) for r in rows if r[3] == "at import"}) == []


@pytest.mark.parametrize("package, door", [tuple(row[:2]) for row in _table("Doors")])
def test_a_package_from_elsewhere_enters_through_its_door(package, door):
    importers = {
        str(path.relative_to(ROOT))
        for path in _sources()
        if any(name.split(".")[0] == package for name in _imported(path))
    }
    assert importers, f"nothing imports {package}: its row in the page is stale"
    assert sorted(i for i in importers if not i.startswith(door)) == []


def _exists(named: str) -> bool:
    """A path, a glob, or ``file::test``, the test a function of that file."""
    path, _, test = named.rstrip("/").partition("::")
    found = list(ROOT.glob(path))
    if test:
        tree = (
            ast.parse(found[0].read_text(encoding="utf-8")) if len(found) == 1 else ast.Module([])
        )
        return test in {
            f.name for f in ast.walk(tree) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
    return bool(found)


def test_every_path_the_page_names_exists():
    named = {
        n.removeprefix("./") for n in re.findall(r"`([^`\s]+)`", PAGE.read_text(encoding="utf-8"))
    }
    paths = {
        n for n in named if n.startswith(TOP_LEVEL) or re.fullmatch(r"[\w.-]+\.(md|toml|py)", n)
    }
    assert paths, "the page names no path"
    assert sorted(p for p in paths if not _exists(p)) == []
