"""The borders docs/boundaries.md states, held against the package: the layer each unit
is in, the imports that reach up a layer, the one place each package from another
repository or an optional install enters through, and that no module takes an
underscore name from another. The page is the statement; this reads its tables and
checks the code against them."""

from __future__ import annotations

import ast
import functools
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


# Each scan below reads the same files; the package is not written while the suite runs,
# so each file is parsed, and each name looked up, once.
@functools.cache
def _is_module(name: str) -> bool:
    path = ROOT.joinpath(*name.split("."))
    return path.with_suffix(".py").is_file() or (path / "__init__.py").is_file()


@functools.cache
def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _imported(path: Path, at_import: bool = False) -> frozenset[str]:
    """Every module ``path`` imports, at the top or inside a function (``at_import``: at
    the top alone), by a statement, by ``import_module``/``__import__``, by a string that
    names a module of the package, or by an attribute of the name ``apothecary``."""
    return _scanned(path, at_import)


@functools.cache
def _scanned(path: Path, at_import: bool) -> frozenset[str]:
    module = _module(path)
    package = module.split(".") if path.name == "__init__.py" else module.split(".")[:-1]
    nodes = list(ast.walk(_tree(path)))
    docstrings = {id(n.value) for n in nodes if isinstance(n, ast.Expr)}
    functions = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
    later = (
        {id(n) for f in nodes if isinstance(f, functions) for n in ast.walk(f)}
        if at_import
        else set()
    )
    found = set()
    for node in nodes:
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
    return frozenset(found)


@functools.cache
def _sources() -> tuple[Path, ...]:
    return tuple(sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts))


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


@functools.cache
def _edges(at_import: bool = False) -> frozenset[tuple[str, str, str]]:
    edges = set()
    for path in _sources():
        here = _unit(_module(path))
        for name in _imported(path, at_import):
            if name.split(".")[0] == "apothecary" and _unit(name) != here:
                edges.add((here, _unit(name), str(path.relative_to(ROOT))))
    return frozenset(edges)


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


def _is_private(name: str) -> bool:
    """A name its module keeps to itself: a leading underscore, and no dunder."""
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def _dotted(node: ast.AST) -> str:
    """``a.b.c`` for attributes read off a name, else nothing."""
    names = []
    while isinstance(node, ast.Attribute):
        names.append(node.attr)
        node = node.value
    return ".".join([node.id, *reversed(names)]) if isinstance(node, ast.Name) else ""


def _underscore_names_taken(
    text: str, module: str, package: list[str], tree: ast.Module | None = None
) -> set[tuple[str, str]]:
    """Each underscore name the module ``text`` is takes from another module of the
    package, with that module: by a ``from`` import, as an attribute of a name an import
    bound to such a module, by ``getattr`` of one with the name written out, or by
    importing a module whose own name begins with an underscore. A module is followed
    through a function of this module that returns it and a name such a call is
    assigned to, and no further: not through an argument, a container or
    ``sys.modules``. ``tree`` is ``text`` parsed, where the caller has it."""
    nodes = list(ast.walk(tree or ast.parse(text)))
    bound: dict[str, str] = {}  # a name this module reads a module of the package by
    taken = set()
    for node in nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] != "apothecary":
                    continue
                bound[alias.asname or alias.name] = alias.name
                taken.update((alias.name, n) for n in alias.name.split(".") if _is_private(n))
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = ".".join(package[: len(package) - node.level + 1] + ([base] if base else []))
            if base.split(".")[0] != "apothecary":
                continue
            taken.update((base, n) for n in base.split(".") if _is_private(n))
            for alias in node.names:
                if _is_module(f"{base}.{alias.name}"):
                    bound[alias.asname or alias.name] = f"{base}.{alias.name}"
                if _is_private(alias.name):
                    taken.add((base, alias.name))

    def owner(node: ast.AST) -> str:
        """The module of the package ``node`` reads, another than this one; else nothing."""
        if isinstance(node, ast.Call):
            return returned.get(getattr(node.func, "id", ""), "")
        names = _dotted(node).split(".")
        for cut in range(len(names), 0, -1):
            head = bound.get(".".join(names[:cut]))
            if head is not None:
                found = ".".join([head, *names[cut:]])
                return found if found != module and _is_module(found) else ""
        return ""

    returned: dict[str, str] = {}  # a function of this module, and the module it returns
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Return) and inner.value is not None:
                    if owner(inner.value):
                        returned[node.name] = owner(inner.value)
    for node in nodes:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if owner(node.value):
                bound.update({_dotted(target): owner(node.value) for target in node.targets})

    for node in nodes:
        if isinstance(node, ast.Attribute) and _is_private(node.attr) and owner(node.value):
            taken.add((owner(node.value), node.attr))
        elif isinstance(node, ast.Call) and getattr(node.func, "id", "") == "getattr":
            name = getattr(node.args[1], "value", None) if len(node.args) > 1 else None
            if isinstance(name, str) and _is_private(name) and owner(node.args[0]):
                taken.add((owner(node.args[0]), name))
    return taken


@pytest.mark.parametrize(
    "code",
    [
        "from .site_store import _held",
        "from .site_store import _held as held",
        "def f():\n    from .site_store import SiteStore, _held",
        "from . import site_store\nsite_store._held()",
        "from . import site_store as kept\nkept._held()",
        "from .routes import views\nviews._answer",
        "import apothecary.site_store\napothecary.site_store._held",
        "import apothecary.routes as r\nr.views._answer",
        "from . import site_store\ngetattr(site_store, '_held')",
        "def kept():\n    from . import site_store\n\n    return site_store\n\nkept()._held",
        "from . import site_store\ndef kept():\n    return site_store\n\nk = kept()\nk._held",
        "from . import _site_store",
        "from ._site_store import held",
        "import apothecary._site_store",
    ],
)
def test_the_underscore_scan_sees_each_way_of_taking_a_name(code):
    assert _underscore_names_taken(code, "apothecary.sites", ["apothecary"])


@pytest.mark.parametrize(
    "code",
    [
        "from .site_store import SiteStore",
        "from .version import __version__",
        "from . import site_store\nsite_store.SiteStore()._sites",
        "from . import sites\nsites._held",
        "import os\nos._exit",
        "from .stays_local import install_guard as _install_guard\n_install_guard()",
    ],
)
def test_the_underscore_scan_leaves_what_is_no_such_taking(code):
    assert not _underscore_names_taken(code, "apothecary.sites", ["apothecary"])


def test_no_module_takes_an_underscore_name_from_another():
    """A name that begins with an underscore is its module's own (docs/boundaries.md,
    What a module keeps to itself): what two modules of the package share has a
    public name where it is defined."""
    taken = set()
    for path in _sources():
        module = _module(path)
        package = module.split(".") if path.name == "__init__.py" else module.split(".")[:-1]
        text = path.read_text(encoding="utf-8")
        for source, name in _underscore_names_taken(text, module, package, tree=_tree(path)):
            taken.add((str(path.relative_to(ROOT)), source, name))
    assert sorted(taken) == []
