"""The Stream Deck + as a part: the maker's envelope whatever its face's slope, its
parameters refused outside their range, its tags, and its node on the garage's bench
at the right end behind the boards, outside the stretch a pinned picture is laid over
(docs/plans/stream-deck-2026-11-07.md, slice 1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from views_helpers import LAID, SHAPES, TALLNESS

from apothecary.example_hierarchy import (
    BENCH_DEPTH,
    BENCH_MOUNTED_STRUCTURES,
    BENCH_TOP_Z,
    BENCH_WIDTH,
    FOOTPEDAL_POSITION,
    STREAM_DECK_POSITION,
    create_example_site,
)
from apothecary.projects.parts import stream_deck_plus
from apothecary.projects.parts.stream_deck_plus import DEFAULT, KEYS, KNOBS, OVERALL, STRIP
from apothecary.vision import free_space


def test_the_envelope_is_the_makers_whatever_the_face_angle():
    """140 x 138 x 110 mm, the stand included, is what the maker publishes; the angle
    moves the body's thickness inside it, never the envelope."""
    assert OVERALL.to_list() == [140.0, 138.0, 110.0]
    for angle in (30, 36.5, 40, 41):
        bounds = DEFAULT.get_bounds({"face_angle": angle})
        assert bounds.min_point.to_list() == [0.0, 0.0, 0.0]
        assert bounds.max_point.to_list() == OVERALL.to_list()


def test_the_face_carries_what_the_maker_says_it_does():
    assert KEYS == (4, 2) and KNOBS == 4 and STRIP == (108.0, 14.0)


@pytest.mark.parametrize("params", [{"face_angle": 29}, {"face_angle": 42}, {"lit": "maybe"}])
def test_a_parameter_outside_its_range_is_refused(params):
    with pytest.raises(ValidationError):
        DEFAULT.get_bounds(params)


def test_it_is_tagged_as_the_controller_it_is():
    assert DEFAULT.category == "electronics"
    assert {"controller", "streamdeck", "elgato", "usb", "knobs", "touch"} <= set(DEFAULT.tags)
    assert DEFAULT.machine is None  # a controller for the machines, not a machine
    assert DEFAULT.readme_path is not None and DEFAULT.readme_path.is_file()


def test_the_garage_stands_it_at_the_benchs_right_end_behind_the_boards():
    """On the bench's top, at its right end behind the boards, the whole deck inside the
    bench and overlapping nothing that rests on it."""
    site = create_example_site()
    deck = next(s for s in site.children if s.name == "stream_deck")
    assert deck.part_ref == "stream_deck_plus" and deck.category == "electrical"
    assert deck.sketch_ref is None
    assert "stream_deck" in BENCH_MOUNTED_STRUCTURES
    assert deck.position.z == BENCH_TOP_Z
    assert deck.footprint.max_point.to_list() == OVERALL.to_list()
    bounds = deck.world_bounds()
    assert FOOTPEDAL_POSITION.x <= bounds.min_point.x and bounds.max_point.x <= BENCH_WIDTH
    assert bounds.max_point.y <= BENCH_DEPTH
    for other in site.children:
        if other.name in BENCH_MOUNTED_STRUCTURES and other.name != "stream_deck":
            theirs = other.world_bounds()
            apart = (
                theirs.max_point.x <= bounds.min_point.x
                or bounds.max_point.x <= theirs.min_point.x
                or theirs.max_point.y <= bounds.min_point.y
                or bounds.max_point.y <= theirs.min_point.y
            )
            assert apart, other.name


def test_a_picture_pinned_at_the_bench_is_laid_where_it_was():
    """The deck stands outside the bench's clear stretch, so the widest picture laid
    there is centred where it is without the deck (tests/views_helpers.py's LAID)."""
    site = create_example_site()
    bench = next(s for s in site.children if s.name == "workbench")
    standing = [area for _, area in free_space.resting_on(site, "workbench")]
    assert "stream_deck" in {name for name, _ in free_space.resting_on(site, "workbench")}
    laid = free_space.fit(free_space.footprint(bench), standing, TALLNESS)
    assert laid.centre == LAID[:2]


def test_it_stands_clear_of_the_pinned_pictures_shapes():
    """The picture the views tests pin at the bench is laid 1800 mm wide over it,
    centred at LAID; none of its three shapes lands on the deck, so the tests that
    count which structures the shapes lie over read as before."""
    left = LAID[0] - 900.0
    deck_x = (STREAM_DECK_POSITION.x, STREAM_DECK_POSITION.x + stream_deck_plus.OVERALL.x)
    for shape in SHAPES:
        x0, x1 = left + shape["min"][0] * 1800.0, left + shape["max"][0] * 1800.0
        assert x1 < deck_x[0] or x0 > deck_x[1], shape["label"]
