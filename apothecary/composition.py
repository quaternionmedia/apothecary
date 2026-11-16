"""What each registered part is built from, among the registered parts.

The registry records no part-to-part relation, so it is read from what is there:

- a part's SCAD ``include <...>`` or ``use <...>`` of another registered part's SCAD
  (a path that resolves to no registered part's file adds nothing, however many files
  it passes through: ``boards/board_common.scad`` is shared code, not a part, and
  carries on to whatever it includes);
- a site node of one registered part that holds a node of another (``part_ref``): the
  Ender 3 in the garage holds the board in its electronics box.

A part that says ``parts`` itself (``part.json``, or the wrapper's field) is built from
exactly those, whatever the inference would say. ``apothecary/orbitals.py`` turns the
children into depths.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Set

from .hierarchy import Assembly
from .projects.parts.base import BasePart

_INCLUDE = re.compile(r"^\s*(?:include|use)\s*<([^>]+)>", re.M)

# A SCAD file that includes files that include files is followed this far past the
# part's own, so a circular include (gridfinity's helpers use each other) ends.
MAX_FILES = 400


def _key(path: Path) -> Path:
    return path.resolve()


def scad_uses(source: Path, registered: Mapping[Path, str]) -> Set[str]:
    """The registered parts ``source``'s SCAD includes or uses, directly or through
    files that are no part. ``registered`` maps each registered part's resolved SCAD
    path to its name; ``source`` itself is never its own child."""
    me = _key(source)
    found: Set[str] = set()
    seen: Set[Path] = {me}
    queue: List[Path] = [me]
    while queue and len(seen) < MAX_FILES:
        here = queue.pop()
        try:
            text = here.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for ref in _INCLUDE.findall(text):
            target = _key(here.parent / ref.strip())
            if target in seen:
                continue
            seen.add(target)
            if target in registered:
                found.add(registered[target])
            elif target.is_file():
                queue.append(target)
    return found


def nested_parts(site: Assembly) -> Dict[str, Set[str]]:
    """For each registered part a node of ``site`` is, the other registered parts the
    nodes beneath it are, at any depth."""
    held: Dict[str, Set[str]] = {}

    def below(node: Assembly) -> Set[str]:
        refs: Set[str] = set()
        for child in (*node.children, *node.additions, *node.subtractions):
            if child.part_ref:
                refs.add(child.part_ref)
            refs |= below(child)
        return refs

    def visit(node: Assembly) -> None:
        if node.part_ref:
            held.setdefault(node.part_ref, set()).update(below(node) - {node.part_ref})
        for child in (*node.children, *node.additions, *node.subtractions):
            visit(child)

    visit(site)
    return held


def part_children(
    parts: Mapping[str, BasePart], sites: Optional[Iterable[Assembly]] = None
) -> Dict[str, List[str]]:
    """Each registered part's children, by name: the explicit ``parts`` of one that
    says so, else what its SCAD uses and ``sites`` nest, kept to the registered."""
    registered = {_key(p.source_file): name for name, p in parts.items() if p.source_file}
    nesting: Dict[str, Set[str]] = {}
    for site in sites or ():
        for name, held in nested_parts(site).items():
            nesting.setdefault(name, set()).update(held)
    children: Dict[str, List[str]] = {}
    for name, part in parts.items():
        if part.parts is not None:
            chosen = set(part.parts)
        else:
            chosen = set(nesting.get(name, ()))
            if part.source_file:
                chosen |= scad_uses(part.source_file, registered)
        children[name] = sorted(c for c in chosen if c in parts and c != name)
    return children
