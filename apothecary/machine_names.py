"""A machine renamed: its node's name in its site changed, so its path changed, and every
record the state folder keeps under the old path moved to the new one.

The name is kept as the site's names are (``apothecary/renames.py``), and stood in the
site each time it is built. What moves (``MOVES``), each in its place: the boards pinned
to the node or to anything inside it (``firmware-state.json``), its plan, the filament
loaded on it, its first-layer offset, its tuning documents and a router's cut
correction, its bed's mount and the places kept on it, and the records that name it: the
slices made for it, the jobs it ran and the drawers of the pieces it made. A record that
cannot be moved is said, and the rest are moved all the same.

Refused while anything is at work on the bench (``devices.at_work``: a print or a cut, a
bed reading, a loop's experiment, an armed port), since a job streaming names its machine
by the path it began with; and for a name that is not a node's (letters, digits, ``_``
and ``-``, no dot) or that a node beside it has.
"""

from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from . import renames
from .hierarchy import Assembly, find_node_by_path
from .renames import Refused
from .state_folder import state_dir, write_whole

_LOCK = threading.RLock()


class Busy(Refused):
    """A rename refused while the bench is at work."""


# --- what moves ----------------------------------------------------------


def _moved(value, old: str, new: str) -> Optional[str]:
    """``value``, a node's path, at ``new`` where it is ``old`` or inside it; else None."""
    if not isinstance(value, str):
        return None
    if value == old:
        return new
    if value.startswith(old + "."):
        return new + value[len(old) :]
    return None


def _rewrite(path: Path, change: Callable[[dict], bool]) -> bool:
    """The JSON record at ``path`` changed in place by ``change``, written whole when it
    says it changed something."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict) or not change(data):
        return False
    write_whole(path, json.dumps(data, indent=2, default=str))
    return True


def _at(data: dict, keys: Tuple[str, str], site: str, old: str, new: str) -> bool:
    """``data[site_key] == site`` and ``data[path_key]`` moved from ``old`` to ``new``; its
    ``name``, where it is the old path's own name, the new one's."""
    site_key, path_key = keys
    if data.get(site_key) != site:
        return False
    moved = _moved(data.get(path_key), old, new)
    if moved is None:
        return False
    data[path_key] = moved
    if moved == new and data.get("name") == old.rsplit(".", 1)[-1]:
        data["name"] = new.rsplit(".", 1)[-1]
    return True


def _pins(site: str, old: str, new: str) -> List[str]:
    from .firmware import devices

    moved = devices.get_state().move_bindings(site, old, new)
    return [f"the board pinned to {p}" for p in moved]


def _named_file(folder: str, site: str, old: str, new: str, field: str) -> List[str]:
    """``<folder>/<site>/<old>.json`` to ``<new>.json``, its ``field`` the new name."""
    if "." in old:
        return []
    src = state_dir() / folder / site / f"{old}.json"
    if not src.is_file():
        return []
    dst = src.with_name(f"{new}.json")
    if dst.exists():
        raise Refused(
            f"{folder}/{site}/{new}.json is kept already: nothing of {old}'s is moved over it"
        )
    src.replace(dst)
    _rewrite(dst, lambda d: _at(d, ("site", field), site, old, new))
    return [f"{folder}/{site}/{new}.json"]


def _plan(site, old, new):
    return _named_file("plans", site, old, new, "path")


def _filament(site, old, new):
    return _named_file("filaments", site, old, new, "printer")


def _first_layer(site, old, new):
    return _named_file("first-layer-offset", site, old, new, "printer")


def _cut_correction(site, old, new):
    return _named_file("corrections", site, old, new, "router")


def _tuning(site: str, old: str, new: str) -> List[str]:
    """A printer's tuning documents, ``corrections/<site>/<old>/``, to ``<new>/``, each
    document's printer node the new name."""
    if "." in old:
        return []
    src = state_dir() / "corrections" / site / old
    if not src.is_dir():
        return []
    dst = src.with_name(new)
    if dst.exists():
        raise Refused(
            f"corrections/{site}/{new}/ is kept already: nothing of {old}'s is moved over it"
        )
    shutil.move(str(src), str(dst))

    def node(d: dict) -> bool:
        printer = d.get("printer")
        return isinstance(printer, dict) and _at(printer, ("site", "node"), site, old, new)

    for doc in dst.glob("*.json"):
        _rewrite(doc, node)
    return [f"corrections/{site}/{new}/"]


def _keyed(file: Path, site: str, old: str, new: str) -> List[str]:
    """A file of records keyed ``site/printer``: ``site/old``'s under ``site/new``."""
    if not file.is_file():
        return []
    moved: List[str] = []

    def change(d: dict) -> bool:
        for key in list(d):
            head, _, tail = key.partition("/")
            if head != site:
                continue
            path = _moved(tail, old, new)
            if path is None:
                continue
            target = f"{site}/{path}"
            if target in d:
                raise Refused(
                    f"{file.name} keeps {target} already: nothing of {old}'s is moved over it"
                )
            d[target] = d.pop(key)
            moved.append(f"{file.parent.name}/{file.name}: {target}")
        return bool(moved)

    _rewrite(file, change)
    return moved


def _bed(site: str, old: str, new: str) -> List[str]:
    from . import bed_shims

    return _keyed(bed_shims.mounts_file(), site, old, new) + _keyed(
        bed_shims.positions_file(), site, old, new
    )


def _records(folder: Path, change: Callable[[dict], bool], what: str) -> List[str]:
    count = 0
    for path in sorted(folder.glob("**/*.json")) if folder.is_dir() else []:
        if _rewrite(path, change):
            count += 1
    return [f"{count} {what}"] if count else []


def _slices(site: str, old: str, new: str) -> List[str]:
    from .slicer import service

    def change(d: dict) -> bool:
        printer = d.get("printer")
        return isinstance(printer, dict) and _at(printer, ("site", "path"), site, old, new)

    return _records(service.slices_dir(), change, "slice records")


def _jobs(site: str, old: str, new: str) -> List[str]:
    from . import jobs

    def change(d: dict) -> bool:
        machine = d.get("machine")
        if d.get("site") != site or not isinstance(machine, dict):
            return False
        moved = _moved(machine.get("path"), old, new)
        if moved is None:
            return False
        machine["path"] = moved
        return True

    return _records(jobs.jobs_dir(), change, "jobs")


def _drawers(site: str, old: str, new: str) -> List[str]:
    from . import cabinet

    def change(d: dict) -> bool:
        machine = d.get("machine")
        return isinstance(machine, dict) and _at(machine, ("site", "path"), site, old, new)

    with cabinet.lock():
        return _records(cabinet.cabinet_dir(), change, "drawers")


# Each kind of record kept under a machine's path, in the order they are moved.
MOVES: Tuple[Tuple[str, Callable[[str, str, str], List[str]]], ...] = (
    ("pins", _pins),
    ("plan", _plan),
    ("filament", _filament),
    ("first-layer offset", _first_layer),
    ("tuning", _tuning),
    ("cut correction", _cut_correction),
    ("bed", _bed),
    ("slices", _slices),
    ("jobs", _jobs),
    ("drawers", _drawers),
)


def rename(site_name: str, site: Assembly, path: str, name: str) -> dict:
    """The node at ``path`` in ``site`` called ``name``, kept so, and every record under
    its old path moved to its new one: what was moved, and what could not be."""
    from .firmware import devices

    name = (name or "").strip()
    if not renames.NAME.match(name):
        raise Refused(
            f"{name!r} is no node's name: letters, digits, _ and -, starting with a letter, "
            "digit or _, at most 64, and no dot"
        )
    node = find_node_by_path(site, path)
    if node is None:
        raise Refused(f"no node {path!r} in {site_name}")
    parent_path, _, old_name = path.rpartition(".")
    if name == old_name:
        return {"path": path, "was": path, "moved": [], "failed": []}
    parent = find_node_by_path(site, parent_path) if parent_path else site
    siblings = [*parent.children, *parent.additions, *parent.subtractions]
    if any(n.name == name for n in siblings):
        raise Refused(f"{site_name} has a {name} beside {old_name} already")
    with _LOCK:
        busy = devices.at_work()
        if busy:
            raise Busy(f"{old_name} is not renamed while the bench is at work: " + "; ".join(busy))
        new = f"{parent_path}.{name}" if parent_path else name
        moved: List[str] = []
        failed: List[str] = []
        for what, move in MOVES:
            try:
                moved += move(site_name, path, new)
            except Refused as exc:
                failed.append(f"{what}: {exc}")
            except OSError as exc:
                failed.append(f"{what}: {exc}")
        renames.keep(site_name, path, name)
        node.name = name
    return {"path": new, "was": path, "moved": moved, "failed": failed}
