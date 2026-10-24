"""Walking a resolved ring by address: what the tests ask of a ring and the
browser does for itself (static/ring.js)."""

from __future__ import annotations

from typing import Dict, Optional, Sequence, Set

from apothecary.menu import ADDRESS, BACK, NoSuchCell, Option, Ring


def walk(ring: Ring, address: str) -> Option:
    """Follow an address down through nested rings to the option it names.

    Every digit but the last must open a further ring; an address that runs
    into an option that does something, or into an empty cell, is refused
    with the cell that stopped it.
    """
    if not address:
        raise NoSuchCell("an empty address reaches nothing; press at least one cell")
    if not ADDRESS.match(address):
        raise NoSuchCell(f"address {address!r} is not a run of cells: digits 1 to 9, never {BACK}")
    here = ring
    option: Optional[Option] = None
    for depth, digit in enumerate(address):
        if option is not None:
            if not option.children:
                raise NoSuchCell(
                    f"cell {option.cell} ({option.label}) does something rather than "
                    f"opening a ring, so {address[depth:]!r} after it goes nowhere"
                )
            here = Ring(title=option.label, options=option.children)
        option = here.at(int(digit))
    assert option is not None
    return option


def address_of(ring: Ring, option_id: str) -> str:
    """The digits that reach an option, searching in placement order."""

    def search(options: Sequence[Option], so_far: str) -> Optional[str]:
        for option in options:
            path = f"{so_far}{option.cell}"
            if option.id == option_id:
                return path
            if option.children:
                found = search(option.children, path)
                if found is not None:
                    return found
        return None

    found = search(ring.options, "")
    if found is None:
        raise NoSuchCell(
            f"no option called {option_id!r} on {ring.title or 'this ring'} or under it"
        )
    return found


def every_address(ring: Ring) -> Dict[str, str]:
    """Every address that does something, and the action it does. Submenus are
    the way to a leaf, not a thing to do, so they are not listed."""
    found: Dict[str, str] = {}

    def search(options: Sequence[Option], so_far: str) -> None:
        for option in options:
            path = f"{so_far}{option.cell}"
            if option.children:
                search(option.children, path)
            elif option.action:
                found[path] = option.action

    search(ring.options, "")
    return found


def every_action(rings: Sequence[Ring]) -> Dict[str, str]:
    """Every action any of these rings can produce, and the label it wore."""
    found: Dict[str, str] = {}
    seen: Set[int] = set()

    def walk_options(options: Sequence[Option]) -> None:
        for option in options:
            # A ring built by hand can be made to hold itself.
            if id(option) in seen:
                continue
            seen.add(id(option))
            if option.action and option.action not in found:
                found[option.action] = option.label
            if option.children:
                walk_options(option.children)

    for ring in rings:
        walk_options(ring.options)
    return found
