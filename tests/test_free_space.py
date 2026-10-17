"""The free space on a structure's top (apothecary/vision/free_space.py): what rests on
it, where a picture fits clear of it, and what a footprint laid there overlaps."""

from __future__ import annotations

import pytest

from apothecary.example_hierarchy import create_example_site
from apothecary.vision.free_space import Area, fit, footprint, overlapping, resting_on

BENCH = Area(0, 0, 1800, 600)
PRINTER = Area(98, 109, 568, 563)
BOARDS = Area(1600, 20, 1800, 400)


def test_a_picture_fits_where_nothing_stands_widest_and_centred_there():
    """Between a printer at one end and boards at the other, a picture three deep for
    four across is as wide as the bench's depth allows, in the clear stretch between."""
    laid = fit(BENCH, [PRINTER, BOARDS], tallness=0.75)
    assert laid.width == pytest.approx(800)
    x, y = laid.centre
    assert PRINTER.x1 <= x - 400 and x + 400 <= BOARDS.x0
    assert y == pytest.approx(300)
    assert overlapping(Area(x - 400, y - 300, x + 400, y + 300), [("printer_1", PRINTER)]) == []


def test_on_a_clear_top_a_picture_lies_on_its_middle():
    laid = fit(BENCH, [], tallness=0.75)
    assert laid.centre == (900, 300) and laid.width == pytest.approx(800)


def test_a_narrow_gap_gives_a_narrower_picture_than_a_wide_one():
    """The widest picture wins, not the largest clear area: a long thin strip loses to
    a squarer space a picture fills better."""
    strip_and_square = [Area(0, 100, 1500, 600)]  # leaves a 1500 x 100 strip and a 300 x 600 end
    laid = fit(BENCH, strip_and_square, tallness=1.0)
    assert laid.width == pytest.approx(300)
    assert laid.centre == (1650, 300)


def test_with_nothing_clear_it_is_the_tops_middle_and_width():
    laid = fit(BENCH, [BENCH], tallness=0.75)
    assert laid.centre == (900, 300) and laid.width == pytest.approx(800)


def test_edges_that_touch_are_no_overlap():
    assert overlapping(Area(568, 0, 700, 100), [("printer_1", PRINTER)]) == []
    assert overlapping(Area(560, 0, 700, 200), [("printer_1", PRINTER)]) == ["printer_1"]


def test_what_rests_on_the_garage_bench_is_what_stands_on_its_top():
    """printer_1, the boards and the footpedal rest on the workbench's top; the
    building, the CNC router and anything not on the top do not."""
    site = create_example_site()
    names = {name for name, _ in resting_on(site, "workbench")}
    assert "printer_1" in names and "footpedal" in names and "arduino_uno" in names
    assert "garage_building" not in names and "workbench" not in names
    bench = footprint(next(c for c in site.children if c.name == "workbench"))
    assert all(area.overlaps(bench) for _, area in resting_on(site, "workbench"))
    assert resting_on(site, "no_such_structure") == []
