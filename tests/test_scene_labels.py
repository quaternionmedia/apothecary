"""Rebuilding a shape from a saved description honours the label.

`docs/scene-json.md` promises a saved shape may say which family it belongs to,
and that the label is used. It was not: the test for "is this a ball" asked
whether a radius was present, and a tube has a radius too, so a tube labelled a
tube came back a ball.

These tests were written against the fault and watched failing before it was
fixed. The two marked as the documented looseness are a separate question and
are not fixed here — see
``docs/plans/features/scene-document-validation.md``.
"""

from __future__ import annotations

import pytest

from apothecary.api import _rehydrate
from apothecary.primitives import Cube, Cylinder, Sphere

# ------------------------------------------------- the label must be believed


@pytest.mark.parametrize(
    "saved, expected",
    [
        ({"type": "cylinder", "h": 10, "r": 5}, Cylinder),
        ({"type": "cylinder", "h": 10, "r1": 3, "r2": 5}, Cylinder),
        ({"type": "cylinder", "h": 2, "r": 0.5, "center": True}, Cylinder),
        ({"type": "sphere", "r": 5}, Sphere),
        ({"type": "sphere", "r": 5, "fn": 64}, Sphere),
        ({"type": "cube", "size": {"x": 1, "y": 2, "z": 3}}, Cube),
    ],
)
def test_a_labelled_shape_comes_back_as_that_shape(saved, expected):
    assert isinstance(_rehydrate(saved), expected)


def test_a_labelled_tube_keeps_its_measurements():
    tube = _rehydrate({"type": "cylinder", "h": 10, "r": 5})
    assert tube.h == 10 and tube.r == 5
    assert "cylinder" in tube.render()


def test_the_label_wins_even_when_the_measurements_suit_another_shape():
    """A radius alone used to be taken as proof of a ball."""
    assert isinstance(_rehydrate({"type": "cylinder", "r": 5, "h": 1}), Cylinder)
    assert isinstance(_rehydrate({"type": "sphere", "r": 5, "h": 1}), Sphere)


def test_a_labelled_shape_with_a_size_that_suits_a_cube_still_obeys_the_label():
    assert isinstance(
        _rehydrate({"type": "sphere", "size": {"x": 1, "y": 1, "z": 1}, "r": 2}), Sphere
    )


# ------------------------------------------------- unlabelled stays as it was


def test_without_a_label_a_radius_alone_is_still_read_as_a_ball():
    """The documented looseness, unchanged. Tightening it is a separate decision."""
    assert isinstance(_rehydrate({"r": 5}), Sphere)


def test_without_a_label_a_height_and_radius_is_still_read_as_a_ball():
    """Wrong, and knowingly left alone: changing it changes a written promise."""
    assert isinstance(_rehydrate({"h": 10, "r": 5}), Sphere)
