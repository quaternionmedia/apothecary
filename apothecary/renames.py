"""The names a person gave a site's nodes, over the names the program builds them with.

A site is built from the program's words (``apothecary/sites.py``), which name each node,
and a node's path is its names from the site down. A node renamed
(``apothecary/machine_names.py``) is kept in the state folder, ``renames/<site>.json``,
as the name the node the program builds at its own path has now, and stood in the site
each time it is built (``stand``), as a camera a person added is. What the program names
by its own words -- a journey's machine, the deck's machine keys, the simulated printer's
pinned board -- is read through ``current``, so it follows the node to whatever it is
called; ``written`` reads a path back to the program's.

Nothing here but the state folder: the journeys and the sites read it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .state_folder import state_dir, write_whole

NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-]{0,63}$")
SITE_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,199}$")


class Refused(ValueError):
    """A rename that is not made, and why."""


# --- what is kept: the program's path of each node renamed, and its name now -------------


def _file(site: str) -> Path:
    if not SITE_NAME.match(site or ""):
        raise Refused(f"no renames are kept for a site called {site!r}")
    return state_dir() / "renames" / f"{site}.json"


def names(site: str) -> Dict[str, str]:
    """Each node renamed in ``site``, by the path the program builds it at: its name now."""
    try:
        held = json.loads(_file(site).read_text(encoding="utf-8"))
    except (OSError, ValueError, Refused):
        return {}
    found = held.get("names") if isinstance(held, dict) else None
    return {str(k): str(v) for k, v in found.items()} if isinstance(found, dict) else {}


def current(site: str, path: str) -> str:
    """``path`` as the program writes it, at the names its nodes have now."""
    renamed = names(site)
    if not renamed or not path:
        return path
    written = path.split(".")
    now = list(written)
    for i in range(len(written)):
        name = renamed.get(".".join(written[: i + 1]))
        if name is not None:
            now[i] = name
    return ".".join(now)


def written(site: str, path: str) -> str:
    """``path`` as it is now, at the names the program builds its nodes with."""
    renamed = names(site)
    if not renamed or not path:
        return path
    back = {current(site, original): original.rsplit(".", 1)[-1] for original in renamed}
    now = path.split(".")
    out = list(now)
    for i in range(len(now)):
        name = back.get(".".join(now[: i + 1]))
        if name is not None:
            out[i] = name
    return ".".join(out)


def _child(node: Any, name: str) -> Optional[Any]:
    """The node under ``node`` called ``name``, its children, additions and subtractions
    walked as one, as a site's paths walk them (``hierarchy.find_node_by_path``)."""
    for each in [*node.children, *node.additions, *node.subtractions]:
        if each.name == name:
            return each
    return None


def _at(site: Any, path: str) -> Optional[Any]:
    node = site
    for name in path.split("."):
        node = _child(node, name)
        if node is None:
            return None
    return node


def keep(site: str, path: str, name: str) -> Dict[str, str]:
    """The node at ``path`` now called ``name``, kept: by the path the program builds it
    at, and nothing kept where ``name`` is the program's own."""
    original = written(site, path)
    renamed = names(site)
    renamed[original] = name
    if name == original.rsplit(".", 1)[-1]:
        del renamed[original]
    write_whole(_file(site), json.dumps({"names": renamed}, indent=2))
    return renamed


def stand(site_name: str, site: Any) -> List[str]:
    """Each node renamed in ``site_name`` given its name now, in the site as the program
    built it; the paths renamed. A path the program no longer builds is passed over."""
    renamed = names(site_name)
    found = []
    # The shallower first: a node is found at its parent's name now and its own.
    for original in sorted(renamed, key=lambda p: p.count(".")):
        parent, _, own = original.rpartition(".")
        node = _at(site, f"{current(site_name, parent)}.{own}" if parent else own)
        if node is not None:
            node.name = renamed[original]
            found.append(original)
    return found
