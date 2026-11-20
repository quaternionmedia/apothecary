"""The two facets the page groups by (apothecary/facets.py): a part's Kind and a site's
System, each a ring of eight at most, each word in one value, each colour a token, a kind's
categories shades of its colour, every colour held apart, and a site sent with its own."""

from __future__ import annotations

import itertools
import math
import re

import pytest
from fastapi.testclient import TestClient

from apothecary import api, facets, sites
from apothecary.facets import (
    KIND,
    KINDS,
    MOST_VALUES,
    SYSTEM,
    SYSTEMS,
    category_shade,
    colour,
    facets_of,
    kind_and_system,
    kind_of,
    layer,
    layer_of,
    named,
    shades,
    system_of,
    token,
    token_colour,
)
from apothecary.layer_colours import SHELLS, WORLD
from apothecary.menu import MOST_OPTIONS
from apothecary.projects.parts.skeleton import ROOT

TOKENS = (ROOT / "apothecary" / "static" / "tokens.css").read_text(encoding="utf-8")

client = TestClient(api.app)

# The words a site uses that no System holds, each decided: a site built round one part
# (datum_core's tray and lid, an enclosure, grouped by that word's kind). A part standing
# loose in a site carries no word. A new word is given a System or named loose here.
LOOSE = {"enclosure"}


def _lab(colour: str):
    """CIE L*a*b* (D65) of a #rrggbb colour, worked here rather than taken from the module
    whose colours it measures."""
    rgb = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    return (116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z)))


def _apart(a: str, b: str) -> float:
    """How far apart two colours look (ΔE*76)."""
    return math.dist(_lab(a), _lab(b))


def _contrast(a: str, b: str) -> float:
    """WCAG's contrast ratio between two colours."""

    def luminance(colour: str) -> float:
        rgb = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _token(name: str) -> str:
    return re.search(rf"{name}: (#[0-9a-f]{{6}})", TOKENS).group(1)


def _kinds() -> dict:
    return {name: colour(KIND, name) for name in KINDS}


def _systems() -> dict:
    return {name: colour(SYSTEM, name) for name in SYSTEMS}


def _categories() -> dict:
    return {category: category_shade(category) for words in KINDS.values() for category in words}


def _every_colour() -> dict:
    return {
        **{f"kind {k}": c for k, c in _kinds().items()},
        **{f"system {s}": c for s, c in _systems().items()},
        **{f"category {k}": c for k, c in _categories().items()},
    }


# --- the vocabulary ---------------------------------------------------------------------------


def test_each_facet_is_one_ring():
    assert MOST_VALUES == MOST_OPTIONS
    assert 0 < len(KINDS) <= MOST_VALUES
    assert 0 < len(SYSTEMS) <= MOST_VALUES


@pytest.mark.parametrize("facet", [KINDS, SYSTEMS], ids=["kinds", "systems"])
def test_no_word_is_in_two_values_of_a_facet(facet):
    words = [word for held in facet.values() for word in held]
    assert len(words) == len(set(words))
    assert all(held for held in facet.values())


def test_every_registered_parts_category_is_in_one_kind():
    """A part's kind is its category's, so a category no kind holds is refused here:
    a new one is given its kind in apothecary/facets.py."""
    parts = client.get("/parts").json()
    assert parts
    orphans = {p["name"]: p["category"] for p in parts if kind_of(p["category"]) is None}
    assert orphans == {}


def test_every_word_a_site_uses_is_a_systems_or_named_loose():
    used = set()
    for name in sites.store.names():
        site = sites.store.get(name)
        if facets.facet_of(site) == SYSTEM:
            used |= {word for _, _, word, _ in facets._pieces(site) if word}
    assert used
    assert {w for w in used if system_of(w) is None} == LOOSE


def test_the_garages_words_take_their_systems():
    assert system_of("wall") == "Building"
    assert system_of("fluid") == "Plumbing"
    assert system_of("mechanical") == "Mechanical"
    assert system_of("machine") == "Machines"
    assert system_of("structure") is None
    assert kind_of("coupon") == "Test pieces"
    assert kind_of("building") == "Housings"
    assert kind_of(None) is None and system_of("") is None


# --- tokens ---------------------------------------------------------------------------------


def test_every_value_has_its_token_and_no_token_is_left_for_one_gone():
    written = set(re.findall(r"(--(?:kind|system)-[a-z0-9-]+):", TOKENS))
    named = {token(KIND, k) for k in KINDS} | {token(SYSTEM, s) for s in SYSTEMS}
    assert written == named
    assert token(KIND, "Test pieces") == "--kind-test-pieces"
    with pytest.raises(KeyError):
        token(KIND, "Building")


def test_a_system_that_is_a_kinds_same_thing_names_the_kinds_token():
    assert "--system-machines: var(--kind-machines)" in TOKENS
    assert colour(SYSTEM, "Machines") == colour(KIND, "Machines")


def test_a_token_is_followed_to_its_colour_and_a_loop_is_refused():
    sheet = "--a: var(--b); --b: #123456; --c: var(--d); --d: var(--c);"
    assert token_colour("--a", sheet) == "#123456"
    with pytest.raises(LookupError):
        token_colour("--c", sheet)
    with pytest.raises(LookupError):
        token_colour("--nowhere", sheet)


# --- shades ---------------------------------------------------------------------------------


def test_a_kinds_categories_are_shades_stepped_evenly_its_own_colour_in_the_middle():
    for kind, words in KINDS.items():
        own = colour(KIND, kind)
        tints = shades(own, len(words))
        assert [category_shade(w) for w in words] == tints
        lightness = [_lab(t)[0] for t in tints]
        steps = [b - a for a, b in itertools.pairwise(lightness)]
        assert all(s > 0 for s in steps), (kind, lightness)
        if steps:
            assert max(steps) - min(steps) < 1.5, (kind, steps)  # a channel's rounding
        assert lightness[-1] - lightness[0] <= facets.SPAN + 1.5, kind
        if len(words) % 2:
            assert tints[len(words) // 2] == own, kind
    assert shades("#3a9e5c", 1) == ["#3a9e5c"]
    assert category_shade("cup") is None


def test_each_category_is_nearer_its_own_kind_than_any_other():
    kinds = _kinds()
    for category, tint in _categories().items():
        nearest = min(kinds, key=lambda k: _apart(tint, kinds[k]))
        assert nearest == kind_of(category), (category, tint, nearest)


# --- colours held apart ---------------------------------------------------------------------


def test_the_kinds_stand_well_apart():
    """The universe's clusters are told apart by their kind's colour: every two at least
    25 apart (ΔE*76)."""
    for (a, x), (b, y) in itertools.combinations(_kinds().items(), 2):
        assert _apart(x, y) >= 25, (a, b)


def test_the_systems_stand_apart():
    for (a, x), (b, y) in itertools.combinations(_systems().items(), 2):
        assert _apart(x, y) >= 15, (a, b)


def test_categories_are_told_apart_within_a_kind_and_across_kinds():
    for (a, x), (b, y) in itertools.combinations(_categories().items(), 2):
        floor = 7 if kind_of(a) == kind_of(b) else 12
        assert _apart(x, y) >= floor, (a, b)


def test_no_colour_of_a_facet_is_read_as_a_state_a_shell_or_the_worlds_own():
    states = [_token(n) for n in ("--ok", "--warn", "--bad")]
    own = [*SHELLS, WORLD["grid"], WORLD["measure"]]
    for name, col in _every_colour().items():
        for state in states:
            assert _apart(col, state) >= 15, (name, state)
        for other in own:
            assert _apart(col, other) >= 20, (name, other)


def test_every_colour_of_a_facet_stands_out_on_the_pages_ground():
    """3:1 against --bg, the floor for a mark that carries meaning (rad's theme tokens)."""
    ground = _token("--bg")
    for name, col in _every_colour().items():
        assert _contrast(col, ground) >= 3, (name, col)


# --- what a site is sent --------------------------------------------------------------------


@pytest.mark.parametrize("name", ["apothecary", "garage", "theatre", "datum_core"])
def test_a_site_is_sent_with_its_facets(name):
    body = client.get(f"/sites/{name}").json()
    assert body["facets"] == facets.facets_of(sites.store.get(name), api.part_category)


def test_the_universe_is_grouped_by_kind_every_part_in_one():
    sent = client.get("/sites/apothecary").json()
    assert sent["facets"]["by"] == KIND
    assert sent["facets"]["loose"] == []
    names = [v["name"] for v in sent["facets"]["values"]]
    assert names == [k for k in KINDS if k in names]
    categories = {n.get("category") for n in sent["tree"]["children"] if n.get("part_ref")}
    sent_words = {w["word"] for v in sent["facets"]["values"] for w in v["words"]}
    assert categories - {None} == sent_words
    for value in sent["facets"]["values"]:
        assert value["colour"] == colour(KIND, value["name"])
        assert value["token"] == token(KIND, value["name"])
        for word in value["words"]:
            assert word["colour"] == category_shade(word["word"])


def test_a_site_is_grouped_by_system_its_loose_words_named():
    sent = client.get("/sites/garage").json()["facets"]
    assert sent["by"] == SYSTEM
    assert [v["name"] for v in sent["values"]] == [
        "Building",
        "Furniture",
        "Machines",
        "Mechanical",
        "Electrical",
        "Plumbing",
    ]
    assert sent["loose"] == []
    for value in sent["values"]:
        assert all(w["colour"] == value["colour"] for w in value["words"])
    # The parts standing loose, by their kinds: the boards, the Stream Deck and the
    # footpedal on the bench, router_coupon, the whiteboard.
    assert [(v["name"], [w["word"] for w in v["words"]]) for v in sent["kinds"]] == [
        ("Electronics", ["electrical", "electronics"]),
        ("Test pieces", ["coupon"]),
        ("Things", ["furniture"]),
    ]
    for value in sent["kinds"]:
        assert all(w["colour"] == category_shade(w["word"]) for w in value["words"])


def test_a_site_built_round_one_part_is_grouped_by_its_words_kind():
    sent = client.get("/sites/datum_core").json()["facets"]
    assert sent["values"] == [] and sent["loose"] == []
    assert [v["name"] for v in sent["kinds"]] == ["Housings"]
    assert sent["kinds"][0]["words"][0]["layer"] == "category:enclosure"


# --- each piece's kind and System --------------------------------------------------------


def test_a_pieces_kind_and_system_come_from_its_word_and_its_part():
    # The universe: a part's kind, no System, whatever its word.
    assert kind_and_system(KIND, "furniture", "furniture") == ("Things", None)
    assert kind_and_system(KIND, None, None) == (None, None)
    # A site: its word's System; a part's kind beside it.
    assert kind_and_system(SYSTEM, "machine", "machine") == ("Machines", "Machines")
    assert kind_and_system(SYSTEM, "machine", "electrical") == ("Electronics", "Machines")
    assert kind_and_system(SYSTEM, "mechanical", None) == (None, "Mechanical")
    # Loose: a part with no word, by its part's kind; a piece whose word no System holds,
    # by its word's kind; a word nobody wrote down, neither.
    assert kind_and_system(SYSTEM, None, "coupon") == ("Test pieces", None)
    assert kind_and_system(SYSTEM, "enclosure", None) == ("Housings", None)
    assert kind_and_system(SYSTEM, "cup", None) == (None, None)


def _pieces(tree, path=""):
    for child in tree["children"]:
        here = f"{path}.{child['name']}" if path else child["name"]
        yield here, child
        yield from _pieces(child, here)


def test_each_piece_of_the_garage_is_sent_with_its_kind_and_system():
    pieces = dict(_pieces(client.get("/sites/garage").json()["tree"]))
    expected = {
        "printer_1": ("Machines", "Machines"),
        # A piece inside a part is of that part.
        "printer_1.frame_system": ("Machines", "Machines"),
        "printer_1.frame_system.mainboard": ("Electronics", "Machines"),
        "cnc_router.frame_system.controller": ("Electronics", "Machines"),
        "cnc_stand": (None, "Furniture"),
        "hvac": (None, "Mechanical"),
        "garage_building.north_wall": (None, "Building"),
        "fluids": (None, "Plumbing"),
        "router_coupon": ("Test pieces", None),
        "arduino_uno": ("Electronics", None),
        "stream_deck": ("Electronics", None),
        "whiteboard": ("Things", None),
    }
    for path, facet in expected.items():
        assert (pieces[path]["kind"], pieces[path]["system"]) == facet, path


@pytest.mark.parametrize("name", ["garage", "theatre", "datum_core", "apothecary"])
def test_every_piece_is_grouped_by_a_system_or_a_kind(name):
    """No piece falls outside the groups: a site's every piece has a System or a kind, and
    the universe's every piece but a site's has a kind."""
    ungrouped = [
        path
        for path, node in _pieces(client.get(f"/sites/{name}").json()["tree"])
        if node["kind"] is None and node["system"] is None and node["site_ref"] is None
    ]
    assert ungrouped == []


# --- layers ---------------------------------------------------------------------------------


def test_a_value_is_named_as_a_layer_and_read_back():
    assert layer(SYSTEM, "Building") == "system:building"
    assert layer(KIND, "Test pieces") == "kind:test-pieces"
    assert layer(SYSTEM, "Machines") != layer(KIND, "Machines")
    for facet, values in ((KIND, KINDS), (SYSTEM, SYSTEMS)):
        for name in values:
            assert named(layer(facet, name)) == (facet, name)
    assert named("category:coupon") is None and named("system:nowhere") is None
    with pytest.raises(KeyError):
        layer(SYSTEM, "Plumbing and heating")


def test_a_piece_is_on_its_systems_layer_else_its_categorys():
    # A site: its System's, whatever its part; loose, its part's category's, else its word's.
    assert layer_of(SYSTEM, "wall", None) == "system:building"
    assert layer_of(SYSTEM, "machine", "machine") == "system:machines"
    assert layer_of(SYSTEM, None, "coupon") == "category:coupon"
    assert layer_of(SYSTEM, "enclosure", None) == "category:enclosure"
    assert layer_of(SYSTEM, "pegboard", None) == "category:pegboard"
    assert layer_of(SYSTEM, None, None) is None
    # The universe: its category's, the word being its part's.
    assert layer_of(KIND, "furniture", "furniture") == "category:furniture"
    assert layer_of(KIND, None, None) is None


def test_a_systems_word_and_a_part_category_spelt_alike_are_two_layers():
    """The bench's boards are electrical parts and the wiring the Electrical System's; the
    whiteboard a furniture part and the workbench the Furniture System's."""
    pieces = dict(_pieces(client.get("/sites/garage").json()["tree"]))
    assert pieces["arduino_uno"]["layer"] == "category:electrical"
    assert pieces["electrical"]["layer"] == "system:electrical"
    assert pieces["whiteboard"]["layer"] == "category:furniture"
    assert pieces["workbench"]["layer"] == "system:furniture"
    assert pieces["printer_1.frame_system.mainboard"]["layer"] == "system:machines"
    assert pieces["garage_building.north_wall"]["layer"] == "system:building"


@pytest.mark.parametrize("name", ["garage", "theatre", "datum_core", "apothecary"])
def test_every_piece_is_on_a_layer_its_site_sends_a_colour_for(name):
    body = client.get(f"/sites/{name}").json()
    for path, node in _pieces(body["tree"]):
        if node["site_ref"] is None:
            assert node["layer"] in body["layer_colours"], path


def test_a_values_words_carry_their_layers():
    sent = client.get("/sites/garage").json()["facets"]
    for value in sent["values"]:
        assert value["layer"] == layer(SYSTEM, value["name"])
        assert all(w["layer"] == value["layer"] for w in value["words"])
    for kind in sent["kinds"]:
        assert kind["layer"] == layer(KIND, kind["name"])
        assert all(w["layer"] == f"category:{w['word']}" for w in kind["words"])


def test_the_facets_beneath_a_level_are_those_of_what_lies_beneath_it():
    garage = sites.store.get("garage")
    inside = facets_of(garage, api.part_category, "printer_1")
    assert [v["name"] for v in inside["values"]] == ["Machines"]
    assert inside["kinds"] == [] and inside["loose"] == []
    stand = facets_of(garage, api.part_category, "cnc_stand")
    assert [v["name"] for v in stand["values"]] == ["Furniture"] and stand["kinds"] == []
    # A part with nothing inside it has nothing beneath it.
    coupon = facets_of(garage, api.part_category, "router_coupon")
    assert coupon["values"] == [] and coupon["kinds"] == []
    nowhere = facets_of(garage, api.part_category, "no_such_piece")
    assert nowhere["values"] == [] and nowhere["kinds"] == [] and nowhere["loose"] == []
    assert facets_of(garage, api.part_category, "") == facets_of(garage, api.part_category)
