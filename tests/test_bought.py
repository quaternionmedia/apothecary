"""What a part needs and does not print (``apothecary/models/bought.py``): counted, sized,
and placed one in each of the interfaces it names."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apothecary.models.bought import INSERT_FIT, Bought
from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.registry import load_part, scan_projects


def test_an_item_is_counted_sized_and_goes_one_in_each_place():
    pin = Bought(name="pin", count=2, diameter=5, length=10, goes_in=["pin_1", "pin_2"])
    assert pin.material is None and pin.bore is None
    with pytest.raises(ValidationError, match="one in each"):
        Bought(name="pin", count=3, diameter=5, goes_in=["pin_1", "pin_2"])
    with pytest.raises(ValidationError, match="twice"):
        Bought(name="pin", count=2, diameter=5, goes_in=["pin_1", "pin_1"])
    with pytest.raises(ValidationError):
        Bought(name="pin", count=0, diameter=5)
    # An item with nowhere drawn for it is still counted.
    assert Bought(name="wire", count=1, diameter=0.5).goes_in == []
    assert INSERT_FIT == pytest.approx(0.2)


def _listed():
    for item in scan_projects(ROOT):
        if item.kind == "part" and item.has_part:
            part = load_part(item)
            if part.params_model is not None and part.bought():
                yield pytest.param(part, id=part.name)


@pytest.mark.parametrize("part", list(_listed()))
def test_each_item_a_part_lists_goes_in_an_interface_it_has_and_fits_it(part):
    """At a part's own values, every place an item goes is one of the part's interfaces,
    and the item is no wider than it, nor longer than a pocket is deep."""
    holes = {i.name: i for i in part.interfaces()}
    for item in part.bought():
        for place in item.goes_in:
            assert place in holes, (part.name, item.name, place)
            assert item.diameter <= holes[place].diameter, (part.name, item.name, place)
            if item.length is not None and getattr(holes[place], "floor", None) == 0.0:
                assert item.length <= holes[place].depth, (part.name, item.name, place)
