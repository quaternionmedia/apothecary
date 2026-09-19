"""The connection a shape finder plugs into.

The connection is the deliverable, not any particular finder. This copies the
pattern already used by ``apothecary/models/blackbox.py``: a checkable
protocol, a plain stand-in, and a field recording where the answer came from.

Two finders ship. That is on purpose — one implementation is an interface with
a single caller wearing a disguise, and it proves nothing about whether the
connection is real.

Every finder must work with the network switched off. See
``docs/plans/proposals/runs-and-stays-local.md``.

PROTOTYPE — not ratified.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Protocol, runtime_checkable

from .models import Picture


@runtime_checkable
class ShapeFinder(Protocol):
    """Anything that can look at a picture file and report flat shapes."""

    def name(self) -> str:
        """Short name, used in reports and to choose this finder."""
        ...

    def look(self, image: Path) -> Picture:
        """Look at one picture file and report what was found."""
        ...


class UnknownFinderError(KeyError):
    """Asked for a finder nobody registered."""


_finders: Dict[str, Callable[[], ShapeFinder]] = {}


def register(name: str, build: Callable[[], ShapeFinder]) -> None:
    """Make a finder available by name. Built when first asked for."""
    _finders[name] = build


def names() -> List[str]:
    """Every registered finder, sorted."""
    return sorted(_finders)


def get(name: str) -> ShapeFinder:
    """Fetch a finder by name."""
    if name not in _finders:
        raise UnknownFinderError(f"no finder named {name!r}; have {names()}")
    finder = _finders[name]()
    if not isinstance(finder, ShapeFinder):
        raise TypeError(f"{name!r} does not satisfy the ShapeFinder protocol")
    return finder


def _register_built_ins() -> None:
    from .plain import PlainFinder
    from .stated import StatedFinder

    register("stated", StatedFinder)
    register("plain", PlainFinder)


_register_built_ins()
