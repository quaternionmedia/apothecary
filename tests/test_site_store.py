"""Tests for the in-memory SiteStore (prototype)."""

import pytest

from apothecary.hierarchy import LayoutReport, Site
from apothecary.site_store import SiteStore, UnknownSiteError


def _make_registry():
    build_count = {"n": 0}

    def factory():
        build_count["n"] += 1
        return Site(name=f"built-{build_count['n']}")

    def validator(site):
        return LayoutReport()

    return {"widget": (factory, validator)}, build_count


def test_get_builds_lazily_once():
    registry, build_count = _make_registry()
    store = SiteStore(registry)
    assert build_count["n"] == 0

    site_a = store.get("widget")
    assert build_count["n"] == 1
    site_b = store.get("widget")
    assert build_count["n"] == 1  # second get does not rebuild
    assert site_a is site_b


def test_mutations_persist_across_get_calls():
    registry, _ = _make_registry()
    store = SiteStore(registry)
    site = store.get("widget")
    site.name = "renamed"
    assert store.get("widget").name == "renamed"


def test_reset_discards_mutations_and_rebuilds():
    registry, build_count = _make_registry()
    store = SiteStore(registry)
    site = store.get("widget")
    site.name = "renamed"

    reset_site = store.reset("widget")
    assert build_count["n"] == 2
    assert reset_site.name == "built-2"
    assert store.get("widget") is reset_site


def test_unknown_site_raises():
    registry, _ = _make_registry()
    store = SiteStore(registry)
    with pytest.raises(UnknownSiteError):
        store.get("nope")
    with pytest.raises(UnknownSiteError):
        store.reset("nope")
    with pytest.raises(UnknownSiteError):
        store.validator("nope")


def test_names_returns_sorted_registry_keys():
    registry, _ = _make_registry()
    registry["alpha"] = registry["widget"]
    store = SiteStore(registry)
    assert store.names() == ["alpha", "widget"]
