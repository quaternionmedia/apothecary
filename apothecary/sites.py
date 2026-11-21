"""The sites kept: the one store of them in a process, and the arrangements written
into the program that it holds from the start.

``store`` is what the server, the command line and the family's members ask for a
site by its name; ``apothecary/site_store.py`` says what it keeps, and for how long.
A name it does not hold is ``UnknownSiteError``, which the server answers with a 404
(``apothecary/api.py``). An arrangement built from a picture is added to it while
the program runs, and taken off it again.
"""

from __future__ import annotations

from .datum_core_site import create_datum_core_site, validate_datum_core
from .example_hierarchy import create_example_site, validate_garage_layout
from .site_names import UNIVERSE
from .site_store import SiteStore
from .theatre_site import create_theatre_site, validate_theatre
from .universe import create_universe_site, validate_universe

store = SiteStore(
    {
        # The universe: every registered part a leaf, every other site here one piece.
        UNIVERSE: (lambda: create_universe_site(store.others()), validate_universe),
        "garage": (create_example_site, validate_garage_layout),
        "datum_core": (create_datum_core_site, validate_datum_core),
        # A theatre's shell with sliders: theatre_site.py.
        "theatre": (create_theatre_site, validate_theatre),
    },
    universe=UNIVERSE,
)
