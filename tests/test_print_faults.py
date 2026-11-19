"""What a look at a printed piece changes (apothecary/print_faults.py): one setting for
the worst fault seen, kept stepping while the fault shrinks, put back and the next
lever tried when it does not, and nothing while the piece read was sliced before the
last change."""

from __future__ import annotations

import pytest

from apothecary import print_faults as pf

# What a slice of Creality Generic PLA on the Ender-3 0.4 nozzle used, as its record says.
USED = {
    "filament_retraction_length": None,  # nil: the machine's retraction_length stands
    "retraction_length": 4.0,
    "nozzle_temperature": 220.0,
    "nozzle_temperature_initial_layer": 220.0,
    "nozzle_temperature_range_low": 190.0,
    "nozzle_temperature_range_high": 230.0,
    "cool_plate_temp": 60.0,
    "cool_plate_temp_initial_layer": 60.0,
    "travel_speed": 150.0,
    "brim_width": 0.0,
    "close_fan_the_first_x_layers": 1.0,
    "filament_flow_ratio": 0.98,
    "filament_max_volumetric_speed": 12.0,
    "slow_down_layer_time": 8.0,
    "fan_max_speed": 100.0,
    "outer_wall_speed": 40.0,
}


def _stepped(look, fault, key, before, after, severity, back=False):
    return pf.Stepped(look, fault, key, before, after, severity, back)


def test_every_fault_says_what_it_looks_like_and_what_else_to_look_at():
    assert [f.id for f in pf.FAULTS][:3] == ["stringing", "first_layer", "warping"]
    for f in pf.FAULTS:
        assert f.name and f.looks_like and f.otherwise
        for lv in f.levers:
            assert lv.least < lv.most and lv.step and lv.why
            assert lv.kind in ("filament", "process", "machine")
    # Every setting a lever moves or reads is one a slice records.
    assert "retraction_length" in pf.READ_KEYS and "nozzle_temperature_range_high" in pf.READ_KEYS


def test_a_fault_never_stepped_takes_its_first_lever_one_step():
    d = pf.next_step({"stringing": 2}, USED, [])
    (move,) = d.moves
    # The filament's retraction says nil: it stands at the machine's 4 mm.
    assert (move.key, move.used, move.new, move.back) == (
        "filament_retraction_length",
        4.0,
        4.5,
        False,
    )
    assert move.why.startswith("Stringing (clear): more filament drawn back")


def test_the_worst_fault_is_changed_and_only_one():
    d = pf.next_step({"stringing": 1, "warping": 3, "ringing": 3}, USED, [])
    assert [m.key for m in d.moves] == ["cool_plate_temp"]  # warping: worst, and listed first


def test_nothing_seen_changes_nothing():
    d = pf.next_step({"stringing": 0}, USED, [])
    assert d.moves == [] and d.said == ["nothing seen: no change"]


def test_a_fault_that_shrank_after_a_step_takes_the_same_lever_again():
    past = [
        pf.Past(
            "look-1",
            {"stringing": 2},
            [_stepped("look-1", "stringing", "filament_retraction_length", 4.0, 4.5, 2)],
        )
    ]
    d = pf.next_step({"stringing": 1}, {**USED, "filament_retraction_length": 4.5}, past)
    (move,) = d.moves
    assert (move.key, move.used, move.new) == ("filament_retraction_length", 4.5, 5.0)
    assert "it governs it" in d.said[0]


def test_a_fault_that_did_not_move_puts_its_lever_back_and_tries_the_next():
    past = [
        pf.Past(
            "look-1",
            {"stringing": 2},
            [_stepped("look-1", "stringing", "filament_retraction_length", 4.0, 4.5, 2)],
        )
    ]
    d = pf.next_step({"stringing": 2}, {**USED, "filament_retraction_length": 4.5}, past)
    back, nxt = d.moves
    assert (back.key, back.new, back.back) == ("filament_retraction_length", 4.0, True)
    assert "does not govern it here" in back.why
    assert (nxt.key, nxt.used, nxt.new, nxt.back) == ("nozzle_temperature", 220.0, 215.0, False)


def test_a_lever_put_back_is_not_tried_again():
    past = [
        pf.Past(
            "look-1",
            {"stringing": 2},
            [_stepped("look-1", "stringing", "filament_retraction_length", 4.0, 4.5, 2)],
        ),
        pf.Past(
            "look-2",
            {"stringing": 2},
            [
                _stepped(
                    "look-2", "stringing", "filament_retraction_length", 4.5, 4.0, 2, back=True
                ),
                _stepped("look-2", "stringing", "nozzle_temperature", 220.0, 215.0, 2),
            ],
        ),
    ]
    used = {**USED, "filament_retraction_length": 4.0, "nozzle_temperature": 215.0}
    d = pf.next_step({"stringing": 2}, used, past)
    back, nxt = d.moves
    assert (back.key, back.new) == ("nozzle_temperature", 220.0)
    assert nxt.key == "travel_speed" and nxt.new == 170.0


def test_a_piece_sliced_before_the_last_change_changes_nothing():
    past = [
        pf.Past(
            "look-1",
            {"stringing": 2},
            [_stepped("look-1", "stringing", "filament_retraction_length", 4.0, 4.5, 2)],
        )
    ]
    d = pf.next_step({"stringing": 2, "warping": 3}, USED, past)
    assert d.moves == []
    assert d.said == [
        "this piece was sliced with filament_retraction_length 4 mm, not 4.5 mm as look-1 "
        "set it: print one sliced since, to see what that change did"
    ]


def test_a_temperature_stays_inside_the_filaments_own_range():
    hot = {**USED, "nozzle_temperature": 230.0}
    past = [
        pf.Past(
            "look-1",
            {"under_extrusion": 2},
            [_stepped("look-1", "under_extrusion", "filament_flow_ratio", 0.98, 1.0, 2)],
        )
    ]
    d = pf.next_step({"under_extrusion": 2}, {**hot, "filament_flow_ratio": 1.0}, past)
    # The flow did not govern it: put back; the temperature is at the range's top, so the
    # third lever is stepped.
    assert [(m.key, m.new) for m in d.moves] == [
        ("filament_flow_ratio", 0.98),
        ("filament_max_volumetric_speed", 10.0),
    ]
    assert "nozzle_temperature is at its limit, 230 °C" in " ".join(d.said)


def test_a_fault_with_every_lever_spent_says_what_to_look_at():
    past = [
        pf.Past(
            "look-1",
            {"ringing": 2},
            [_stepped("look-1", "ringing", "outer_wall_speed", 40.0, 30.0, 2)],
        )
    ]
    d = pf.next_step({"ringing": 3}, {**USED, "outer_wall_speed": 30.0}, past)
    (back,) = d.moves
    assert back.back and back.new == 40.0
    assert "no lever left" in d.said[-1] and "a loose belt or wheel" in d.said[-1]


@pytest.mark.parametrize("fault_id", [f.id for f in pf.FAULTS])
def test_each_fault_seen_bad_on_a_fresh_slice_steps_its_first_lever(fault_id):
    d = pf.next_step({fault_id: 3}, USED, [])
    first = pf.fault(fault_id).levers[0]
    assert [m.key for m in d.moves] == [first.key]
    (m,) = d.moves
    assert m.new == pytest.approx(first.clamp(pf.value_of(first, USED) + first.step, USED))
