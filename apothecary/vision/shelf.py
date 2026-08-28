"""Arrangements built from pictures, kept where the viewer can find them.

The viewer already knows how to show an arrangement: pick one by name, walk into
it at any depth, filter it by the group each piece belongs to. None of that needs
changing to show something built from a photograph — it needs the arrangement to
be somewhere the viewer looks, and the pieces to carry their group.

So this is a small shelf of arrangements built from pictures, joined into the
same register the viewer already reads. What is known about each piece lives
beside it, joined by the same dotted path everything else uses.

Held in memory only, like everything else that register holds. Nothing is
written anywhere. See ``docs/plans/features/persistence.md`` for when that stops
being good enough, and ``docs/plans/proposals/runs-and-stays-local.md`` for why
it will not become somebody else's disk when it does.

PROTOTYPE — not ratified.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from ..hierarchy import Assembly, LayoutReport
from .album import Album, Built


class Shelf:
    """Every arrangement built from a picture in this session."""

    def __init__(self) -> None:
        self._built: Dict[str, Built] = {}

    def put(self, made: Built) -> str:
        """Shelve one arrangement under its own name, replacing any before it.

        Refuses pieces whose names would make them unreachable. Every part of
        this tool addresses a node by joining names with dots, so a name with a
        dot in it can be stored and never found again, and two pieces sharing a
        name means one of them can never be picked.
        """
        seen = set()
        for piece in made.site.children:
            if "." in piece.name:
                raise ValueError(
                    f"a piece named {piece.name!r} could never be found again: names are "
                    "joined with dots to address them, so a name cannot contain one"
                )
            if piece.name in seen:
                raise ValueError(
                    f"two pieces are both named {piece.name!r}; one of them could never be picked"
                )
            seen.add(piece.name)
        self._built[made.site.name] = made
        return made.site.name

    def forget(self, name: str) -> bool:
        """Take one arrangement off the shelf again."""
        return self._built.pop(name, None) is not None

    def names(self) -> List[str]:
        return sorted(self._built)

    def site(self, name: str) -> Assembly:
        return self._built[name].site

    def album(self, name: str) -> Album:
        return self._built[name].album

    def __contains__(self, name: object) -> bool:
        return name in self._built

    def __len__(self) -> int:
        return len(self._built)

    def factory(self, name: str):
        """A way of fetching this arrangement that the register understands.

        The register asks for something it can call to build an arrangement. A
        picture has already been looked at by this point, so there is nothing to
        rebuild — the answer is the one already on the shelf.
        """

        def fetch() -> Assembly:
            # A copy, not the shelved object. The register's "discard all edits
            # and rebuild" hands back whatever this returns, so returning the
            # live one made resetting a picture-built arrangement do nothing at
            # all while quietly appearing to work.
            return self.site(name).model_copy(deep=True)

        return fetch

    def checker(self, name: str):
        """A way of checking this arrangement that the register understands."""

        def check(site: Assembly) -> LayoutReport:
            return site.validate()

        return check


_shelf: Optional[Shelf] = None


def shelf() -> Shelf:
    """The one shelf this session uses."""
    global _shelf
    if _shelf is None:
        _shelf = Shelf()
    return _shelf


__all__ = ["Shelf", "shelf"]
