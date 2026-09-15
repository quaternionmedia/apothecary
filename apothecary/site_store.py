"""In-memory, single-process store for Site instances (prototype).

Sites carry no real persistence layer yet -- this is a process-lifetime
singleton, not a database. It exists so that edits (position moves, and in
later phases printer status and job assignments) survive across requests
instead of being rebuilt fresh each time, unlike /render's stateless Scene
handling, which fits because a Scene has no state to keep between calls.

Known limitations, stated rather than hidden: state is lost on server
restart, and is not shared across multiple worker processes (each Uvicorn
worker would get its own store). Fine for a single-process dev server, not
for anything beyond this prototype -- a real deployment would swap this for
an actual persistence layer without changing the call sites below.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Tuple

from .hierarchy import Assembly, LayoutReport

SiteFactory = Callable[[], Assembly]
SiteValidator = Callable[[Assembly], LayoutReport]


class UnknownSiteError(KeyError):
    """Raised when a site name isn't registered."""


class SiteStore:
    """Holds one live Site per registered name, built lazily on first access."""

    def __init__(self, registry: Dict[str, Tuple[SiteFactory, SiteValidator]]):
        self._registry = registry
        self._sites: Dict[str, Assembly] = {}

    def _entry(self, name: str) -> Tuple[SiteFactory, SiteValidator]:
        entry = self._registry.get(name)
        if entry is None:
            raise UnknownSiteError(name)
        return entry

    def names(self) -> List[str]:
        return sorted(self._registry.keys())

    def get(self, name: str) -> Assembly:
        """Return the persisted Site, building it from its factory on first access."""
        factory, _validator = self._entry(name)
        if name not in self._sites:
            self._sites[name] = factory()
        return self._sites[name]

    def validator(self, name: str) -> SiteValidator:
        _factory, validator = self._entry(name)
        return validator

    def reset(self, name: str) -> Assembly:
        """Discard all edits and rebuild the site fresh from its factory."""
        factory, _validator = self._entry(name)
        self._sites[name] = factory()
        return self._sites[name]
