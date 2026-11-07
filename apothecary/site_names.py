"""The names sites go by, for what is kept under one.

A pin, a camera's record, a job, a procedure and a day of evidence are each kept
under the name of the site they belong to. A site that takes another name keeps
what was kept under the one before: whatever reads such a record reads its
site's name through ``current``, so the record is found under the name the site
has now, and is written back under it the next time it is written.

This module imports nothing, so the firmware package and the evidence log can
read it without reaching into the site layer.
"""

from __future__ import annotations

from typing import Dict, List

# The universe: every registered part a leaf of it, and every other site one piece.
UNIVERSE = "apothecary"
# What the page calls it.
UNIVERSE_SHOWN = "Apothecary"

# A name a site had, and the name it has now. The universe was the parts library.
FORMER: Dict[str, str] = {"parts_library": UNIVERSE}


def current(name: str) -> str:
    """The name a site goes by now, whatever name a record was kept under."""
    return FORMER.get(name, name)


def former(name: str) -> List[str]:
    """Every name a site had before the one it has now."""
    return [was for was, now in FORMER.items() if now == name]
