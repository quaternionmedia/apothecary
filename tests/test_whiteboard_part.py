"""The whiteboard as a part: its writing surface's size is its parameters, the frame
and the tray stand outside it, and the garage hangs it on its south wall clear of
everything else (docs/plans/whiteboard-loop-2026-11-09.md, slice 3)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apothecary.example_hierarchy import (
    BENCH_MOUNTED_STRUCTURES,
    DOOR_WIDTH,
    GARAGE_MAX,
    GARAGE_MIN,
    WALL_THICKNESS,
    WHITEBOARD_POSITION,
    create_example_site,
)
from apothecary.projects.parts import whiteboard
from apothecary.projects.parts.whiteboard import DEFAULT, OVERALL


def test_its_size_is_the_writing_surface_with_the_frame_and_tray_outside_it():
    assert whiteboard.surface().to_list() == [1200.0, 0.0, 900.0]
    assert OVERALL.to_list() == [1230.0, 60.0, 930.0]
    wider = {"width": 1800, "height": 1200, "frame": 20, "tray": 0, "thickness": 25}
    assert whiteboard.surface(wider).to_list() == [1800.0, 0.0, 1200.0]
    assert DEFAULT.get_bounds(wider).max_point.to_list() == [1840.0, 25.0, 1240.0]
    assert DEFAULT.get_bounds().min_point.to_list() == [0.0, 0.0, 0.0]


@pytest.mark.parametrize("params", [{"width": 100}, {"height": 5000}, {"frame": 0}, {"tray": -1}])
def test_a_parameter_outside_its_range_is_refused(params):
    with pytest.raises(ValidationError):
        DEFAULT.get_bounds(params)


def test_it_is_tagged_as_what_a_drawing_is_made_on():
    assert DEFAULT.category == "furniture" and DEFAULT.machine is None
    assert {"whiteboard", "drawing", "wall"} <= set(DEFAULT.tags)
    assert DEFAULT.readme_path is not None and DEFAULT.readme_path.is_file()
    assert DEFAULT.source_file.is_file()


def test_the_garage_hangs_it_on_the_south_wall_clear_of_everything():
    """Its back against the south wall's inner face, between the door's opening and
    the east wall, overlapping no other structure; the site's one overlap stays the
    router's coupon on its table."""
    site = create_example_site()
    hung = next(s for s in site.children if s.name == "whiteboard")
    assert hung.part_ref == "whiteboard" and hung.category == "furniture"
    assert "whiteboard" not in BENCH_MOUNTED_STRUCTURES
    bounds = hung.world_bounds()
    assert bounds.max_point.y == GARAGE_MAX.y - WALL_THICKNESS
    door_ends = GARAGE_MIN.x + (GARAGE_MAX.x - GARAGE_MIN.x + DOOR_WIDTH) / 2
    assert bounds.min_point.x > door_ends, "beside the door's opening, not across it"
    assert bounds.max_point.x < GARAGE_MAX.x - WALL_THICKNESS
    assert bounds.max_point.to_list() == [
        WHITEBOARD_POSITION.x + OVERALL.x,
        WHITEBOARD_POSITION.y + OVERALL.y,
        WHITEBOARD_POSITION.z + OVERALL.z,
    ]
    overlaps = [v.structures for v in site.validate().violations if v.kind == "overlap"]
    assert overlaps == [["cnc_router", "router_coupon"]]
