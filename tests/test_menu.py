"""The ring's options, and the two limits that are easy to break by accident.

These are the checks that only exist because the option builder lives in Python.
In the browser they would be screenshots; here they are arithmetic.

The second half holds the nine-cells rules: where an option is seated, what an
arrow reaches, and the address that reaches an option again. The browser runs
the same rules, and ``tests/conformance/nine_cells.json`` is generated from the
functions here so the two cannot drift apart unnoticed; run this file as a
script to regenerate it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from apothecary.hierarchy import Assembly, Site
from apothecary.menu import (
    BACK,
    CELLS,
    COMPASS,
    DIRECTIONS,
    LONGEST_LABEL,
    MOST_OPTIONS,
    PLACEMENT,
    Context,
    Device,
    Intent,
    NoSuchCell,
    Option,
    Pointing,
    Ring,
    RingTooFull,
    address_of,
    check_ring,
    control_options,
    every_action,
    every_address,
    nearest,
    resolve,
    shorten,
    walk,
)
from apothecary.primitives import Cube

CONFORMANCE = Path(__file__).parent / "conformance" / "nine_cells.json"


def _photo_site() -> Assembly:
    return Site(
        "bench",
        structures=[
            Assembly(name="plate_1", role="word", base=Cube(size=1.0)),
            Assembly(name="disc_2", role="word", base=Cube(size=1.0)),
            Assembly(name="printer_1", role="structure", base=Cube(size=1.0)),
        ],
    )


# ---------------------------------------------------------------- the ceiling


def test_a_ring_holds_eight():
    check_ring([Option(id=str(i), label=str(i), action=f"do{i}") for i in range(MOST_OPTIONS)])


def test_a_ninth_option_is_refused_rather_than_hidden():
    with pytest.raises(RingTooFull, match="Group some of them"):
        check_ring(
            [Option(id=str(i), label=str(i), action=f"do{i}") for i in range(MOST_OPTIONS + 1)]
        )


def test_an_empty_ring_is_refused():
    with pytest.raises(ValueError, match="not a ring"):
        check_ring([])


def test_the_refusal_names_the_options_so_it_can_be_acted_on():
    with pytest.raises(RingTooFull) as raised:
        check_ring([Option(id=f"opt{i}", label=str(i), action=f"do{i}") for i in range(9)])
    assert "opt8" in str(raised.value)


def test_a_ring_checks_itself_when_it_is_built():
    """Built through the model, the refusal arrives wrapped but intact.

    A ring built directly reports the refusal as a validation failure rather
    than as `RingTooFull`, because that is what building a model does with a
    refusal. The message is the same and it is the message that has to be
    actionable.
    """
    with pytest.raises(ValueError, match="Group some of them"):
        Ring(options=[Option(id=str(i), label=str(i), action=f"do{i}") for i in range(9)])


# ---------------------------------------------------------------- the labels


def test_a_label_that_is_too_long_is_refused_at_the_source():
    with pytest.raises(ValueError, match="Shorten it"):
        Option(id="x", label="a" * (LONGEST_LABEL + 1), action="x")


@pytest.mark.parametrize(
    "long_name",
    [
        "printer_1.gantry_system",
        "enclosure.mounting_system.m3_boss_fl",
        "a_very_long_compound_name_indeed",
        "parts_library",
        "supercalifragilistic",
        "the quick brown fox jumps",
    ],
)
def test_every_shortened_label_fits(long_name):
    assert len(shorten(long_name)) <= LONGEST_LABEL


def test_shortening_never_trails_off():
    """An ellipsis says something was removed without saying what."""
    for name in ("printer_1.gantry_system", "a_very_long_compound_name", "x" * 40):
        short = shorten(name)
        assert "…" not in short and not short.endswith("...")


def test_the_last_part_of_a_path_is_what_is_kept():
    """The ring is already standing on the thing the earlier parts name."""
    assert shorten("printer_1.gantry") == "gantry"


def test_a_short_label_is_left_alone():
    """Nothing is taken away from a label that already fits.

    This is the rule, not a nicety. Without it every dot was treated as a path
    separator before the length was checked, and `nozzle_0.4mm` came back as
    `4mm`.
    """
    assert shorten("Fit") == "Fit"
    assert shorten("disc_2") == "disc_2"


@pytest.mark.parametrize(
    "measurement", ["M3.5_bolt", "nozzle_0.4mm", "bench_v1.2", "0.5", "1.6mm", "R0.8"]
)
def test_a_measurement_short_enough_to_fit_is_never_cut(measurement):
    """A 0.4mm nozzle labelled '4mm' is the worst thing this function could do."""
    assert shorten(measurement) == measurement


def test_a_label_is_never_blank():
    """A wedge nobody can read is a wedge nobody can choose on purpose."""
    for nothing_much in ("", "   ", "....", "____", "-" * 30, "gantry_system."):
        assert shorten(nothing_much).strip()


def test_two_things_never_come_out_reading_the_same():
    from apothecary.menu import distinct

    names = ["gantry_system_leftmost", "gantry_system_leftish", "bench.plate_1", "other.plate_1"]
    labels = distinct(names)
    assert len(set(labels)) == len(names)
    assert all(len(label) <= LONGEST_LABEL for label in labels)


def test_a_ring_refuses_two_wedges_that_read_the_same():
    with pytest.raises(ValueError, match="read the same"):
        check_ring(
            [
                Option(id="a", label="Move", action="move-a"),
                Option(id="b", label="Move", action="move-b"),
            ]
        )


def test_a_ring_refuses_two_wedges_that_do_the_same_thing():
    with pytest.raises(ValueError, match="do the same thing"):
        check_ring(
            [Option(id="a", label="A", action="same"), Option(id="b", label="B", action="same")]
        )


def test_a_submenu_is_a_ring_too():
    """Only the outer ring used to be counted, so a submenu could hold twenty."""
    with pytest.raises(ValueError, match="a ring holds"):
        Option(
            id="many",
            label="Many",
            children=[Option(id=str(i), label=str(i), action=f"do{i}") for i in range(9)],
        )


def test_the_rules_still_hold_after_something_is_assigned():
    option = Option(id="a", label="Fine", action="x")
    with pytest.raises(ValueError, match="Shorten it"):
        option.label = "z" * 40


def test_shortening_the_same_name_twice_gives_the_same_answer():
    for name in ("printer_1.gantry_system", "mounting_system", "plate_1"):
        assert shorten(name) == shorten(shorten(name))


def test_a_long_single_word_is_cut_rather_than_left_over_length():
    assert len(shorten("supercalifragilisticexpialidocious")) == LONGEST_LABEL


# ---------------------------------------------------------------- what is offered


def test_the_canvas_ring_offers_the_sites_and_the_groups():
    ring = resolve(
        Context(pointing=Pointing.CANVAS),
        _photo_site(),
        site_names=["bench", "garage"],
        groups=["plate", "disc"],
    )
    assert every_action([ring]).keys() >= {"site:bench", "group:plate", "fit", "reset"}


def test_a_ring_with_nothing_to_group_simply_does_not_offer_it():
    ring = resolve(Context(pointing=Pointing.CANVAS), _photo_site())
    assert "Site" not in [option.id for option in ring.options]
    assert "fit" in [option.id for option in ring.options]


@pytest.mark.parametrize("how_many", [1, 8, 9, 20, 64])
def test_a_long_list_is_grouped_and_nothing_is_lost(how_many):
    """A list of things is not a list of verbs.

    Eight-to-a-ring exists because nine verbs means the menu was designed
    wrong. That argument does not carry over to nine arrangements somebody
    happens to have, so a long list gets lettered groups — one more press,
    nothing hidden.

    An earlier attempt at this keyed the groups on the first letter of each
    name. Every name began with the same letter, so eighteen of twenty things
    silently vanished. Hence counting them here.
    """
    names = [f"site_{i}" for i in range(how_many)]
    ring = resolve(Context(pointing=Pointing.CANVAS), _photo_site(), site_names=names)
    reachable = {a for a in every_action([ring]) if a.startswith("site:")}
    assert reachable == {f"site:{n}" for n in names}


def test_more_things_than_grouping_can_show_is_refused_rather_than_cut():
    with pytest.raises(ValueError, match="needs searching"):
        resolve(
            Context(pointing=Pointing.CANVAS),
            _photo_site(),
            site_names=[f"site_{i}" for i in range(100)],
        )


def test_a_piece_built_from_a_picture_can_be_swapped_for_another_word():
    ring = resolve(
        Context(pointing=Pointing.NODE, targets=["plate_1"]),
        _photo_site(),
        words=["plate", "disc", "post", "slot", "wedge"],
    )
    assert "word:disc" in every_action([ring])


def test_a_piece_that_did_not_come_from_a_picture_is_not_offered_a_word():
    ring = resolve(
        Context(pointing=Pointing.NODE, targets=["printer_1"]),
        _photo_site(),
        words=["plate", "disc"],
    )
    assert not any(action.startswith("word:") for action in every_action([ring]))


def test_an_option_that_does_not_apply_is_absent_rather_than_greyed_out():
    ring = resolve(Context(pointing=Pointing.NODE, targets=["printer_1"]), _photo_site())
    assert all(option.enabled for option in ring.options)


def test_every_ring_can_explain_itself():
    """Where the reasoning behind a piece is reachable, not buried in a comment."""
    site = _photo_site()
    for context in (
        Context(pointing=Pointing.CANVAS),
        Context(pointing=Pointing.NODE, targets=["plate_1"]),
        Context(pointing=Pointing.SELECTION, targets=["plate_1", "disc_2"]),
        Context(pointing=Pointing.EDGE, targets=["a", "b"]),
    ):
        ring = resolve(context, site)
        if context.pointing is not Pointing.CANVAS:
            assert "explain" in every_action([ring])


@pytest.mark.parametrize(
    "pointing", [Pointing.CANVAS, Pointing.NODE, Pointing.SELECTION, Pointing.EDGE]
)
def test_every_kind_of_ring_obeys_both_limits(pointing):
    ring = resolve(
        Context(pointing=pointing, targets=["plate_1"]),
        _photo_site(),
        site_names=["bench", "garage"],
        groups=["plate", "disc"],
        words=["plate", "disc", "post", "slot", "wedge"],
    )
    assert 1 <= len(ring.options) <= MOST_OPTIONS
    for option in ring.options:
        assert len(option.label) <= LONGEST_LABEL
        for child in option.children or []:
            assert len(child.label) <= LONGEST_LABEL


def test_asking_about_a_node_that_is_not_there_still_gives_a_ring():
    ring = resolve(Context(pointing=Pointing.NODE, targets=["nope.nothing"]), _photo_site())
    assert ring.options


# ---------------------------------------------------------------- it changes nothing


def test_working_out_the_options_leaves_the_arrangement_untouched():
    site = _photo_site()
    before = site.model_dump_json()
    for pointing in Pointing:
        resolve(Context(pointing=pointing, targets=["plate_1"]), site, words=["plate", "disc"])
    assert site.model_dump_json() == before


def test_a_choice_is_carried_as_an_intent_and_nothing_else():
    context = Context(pointing=Pointing.NODE, targets=["plate_1"])
    intent = Intent(action="word:disc", context=context, option_id="word:disc")
    assert intent.action == "word:disc"
    assert intent.context.targets == ["plate_1"]


def test_the_things_a_ring_names_are_the_paths_everything_else_uses():
    """No second way of naming things was invented, and none is needed."""
    site = _photo_site()
    ring = resolve(Context(pointing=Pointing.NODE, targets=["plate_1"]), site, words=["disc"])
    assert ring.title == "plate_1"
    assert any(child.name == "plate_1" for child in site.children)


# ---------------------------------------------------------------- shape of an option


def test_an_option_either_does_something_or_opens_another_ring():
    with pytest.raises(ValueError, match="do something or open"):
        Option(id="x", label="X")
    with pytest.raises(ValueError, match="do something or open"):
        Option(id="x", label="X", action="a", children=[Option(id="y", label="Y", action="b")])


# ---------------------------------------------------------------- the nine cells


def _leaves(how_many: int) -> list:
    return [Option(id=f"o{i}", label=f"L{i}", action=f"do{i}") for i in range(how_many)]


PRINTER = Device(port="/dev/ttyUSB0", printer=True, armed=False, bound=True)


def _node_with_printer(device: Device = PRINTER) -> Ring:
    context = Context(pointing=Pointing.NODE, targets=["printer_1"])
    return resolve(context, _photo_site(), device=device)


def _device_ring(device: Device = PRINTER) -> Ring:
    return resolve(Context(pointing=Pointing.DEVICE, targets=[device.port]), device=device)


def _control_ring(device: Device = PRINTER) -> Ring:
    return Ring(title="Control", options=control_options(device))


@pytest.mark.parametrize("how_many", range(1, MOST_OPTIONS + 1))
def test_options_are_seated_cardinals_first(how_many):
    """The i-th option sits in cell PLACEMENT[i]: up, right, down, left, then corners."""
    ring = Ring(options=_leaves(how_many))
    assert [o.cell for o in ring.options] == list(PLACEMENT[:how_many])


def test_a_four_option_ring_sits_at_up_right_down_left():
    assert set(Ring(options=_leaves(4)).cells()) == {8, 6, 2, 4}


def test_the_centre_is_never_seated():
    """Cell 5 backs out. A centre that sometimes chooses cannot be used blind."""
    assert BACK not in PLACEMENT
    assert BACK not in COMPASS
    for how_many in range(1, MOST_OPTIONS + 1):
        assert BACK not in Ring(options=_leaves(how_many)).cells()
    with pytest.raises(NoSuchCell, match="backs out"):
        Ring(options=_leaves(8)).at(BACK)


def test_a_ninth_option_still_has_no_cell_to_sit_in():
    assert len(PLACEMENT) == MOST_OPTIONS
    with pytest.raises(RingTooFull):
        check_ring(_leaves(MOST_OPTIONS + 1))
    with pytest.raises(ValueError, match="a ring holds"):
        Ring(options=_leaves(MOST_OPTIONS + 1))


def test_a_cell_is_given_by_the_ring_and_never_by_hand():
    with pytest.raises(ValueError, match="given by hand"):
        Option(id="x", label="X", action="x", cell=8)
    option = Option(id="x", label="X", action="x")
    assert option.cell is None
    with pytest.raises(ValueError, match="given by hand"):
        option.cell = 8
    Ring(options=[option])
    assert option.cell == 8


def test_reseating_a_ring_moves_its_options():
    """The seat follows the position, so swapping the options re-seats them."""
    first, second = _leaves(2)
    ring = Ring(options=[first, second])
    assert (first.cell, second.cell) == (8, 6)
    ring.options = [second, first]
    assert (second.cell, first.cell) == (8, 6)


def test_a_submenu_seats_its_children_too():
    parent = Option(id="p", label="P", children=_leaves(3))
    assert [c.cell for c in parent.children] == [8, 6, 2]


def test_every_cell_has_one_number_and_one_direction():
    """The keypad and the compass name the same eight cells."""
    assert set(PLACEMENT) == set(COMPASS) == set(CELLS) - {BACK}
    assert len(set(PLACEMENT)) == len(set(COMPASS)) == 8
    assert COMPASS[0] == 8, "up is the first wedge"
    assert CELLS[BACK] == (1, 1), "the centre is the centre"


def test_at_and_cells_agree():
    ring = Ring(options=_leaves(5))
    for cell, option in ring.cells().items():
        assert ring.at(cell) is option
    with pytest.raises(NoSuchCell, match="empty"):
        ring.at(7)
    with pytest.raises(NoSuchCell, match="not a cell"):
        ring.at(0)


# ---------------------------------------------------------------- addresses


def test_walk_and_address_round_trip_through_device_control_jog():
    """Device > Control > Jog > Y+ on a node with a printer pinned to it.

    The address is computed, not assumed: Device is the third option on the
    node ring, Control the eighth on the device ring (Link is the seventh),
    Jog the third on the control ring, and Y+ the first on the jog pad.
    """
    ring = _node_with_printer()
    expected = "".join(str(PLACEMENT[i]) for i in (2, 7, 2, 0))
    address = address_of(ring, "control:jog:Y+")
    assert address == expected == "2728"
    assert walk(ring, address).action == "control:jog:Y+"
    assert BACK not in {int(digit) for digit in address}


def test_every_address_walks_back_to_its_own_action():
    for ring in (_node_with_printer(), _device_ring(), _control_ring()):
        for address, action in every_address(ring).items():
            assert walk(ring, address).action == action
            option = walk(ring, address)
            assert address_of(ring, option.id) == address


def test_the_jog_pad_is_the_keypad():
    """Y+ up, X+ right, Y- down, X- left, Z+ and Z- in the right-hand corners."""
    jog = walk(_control_ring(), str(PLACEMENT[2]))
    assert {c.label: c.cell for c in jog.children} == {
        "Y+": 8,
        "X+": 6,
        "Y-": 2,
        "X-": 4,
        "Z+": 9,
        "Z-": 3,
    }


def test_an_address_through_an_option_that_does_something_goes_nowhere():
    ring = _device_ring()
    with pytest.raises(NoSuchCell, match="does something rather than opening"):
        walk(ring, "88")


def test_an_address_into_an_empty_cell_is_refused():
    with pytest.raises(NoSuchCell, match="empty"):
        walk(Ring(options=_leaves(4)), "7")


@pytest.mark.parametrize("bad", ["", "5", "85", "0", "a", "8 6"])
def test_an_address_is_digits_and_never_five(bad):
    with pytest.raises(NoSuchCell):
        walk(_device_ring(), bad)


def test_an_option_that_is_not_there_has_no_address():
    with pytest.raises(NoSuchCell, match="no option called"):
        address_of(_device_ring(), "nope")


def test_every_address_covers_every_leaf():
    """Every action a ring can produce has exactly one address that reaches it."""
    for ring in (
        _node_with_printer(),
        _device_ring(),
        _control_ring(),
        resolve(
            Context(pointing=Pointing.CANVAS),
            _photo_site(),
            site_names=[f"site_{i}" for i in range(20)],
        ),
    ):
        by_address = every_address(ring)
        assert sorted(by_address.values()) == sorted(every_action([ring]))


def test_an_intent_carries_its_address():
    context = Context(pointing=Pointing.NODE, targets=["printer_1"])
    intent = Intent(
        action="control:jog:Y+", context=context, option_id="control:jog:Y+", address="2728"
    )
    assert intent.address == "2728"
    assert Intent(action="fit", context=context, option_id="fit").address is None
    for bad in ("5", "85", "", "x"):
        with pytest.raises(ValueError, match="run of cells"):
            Intent(action="fit", context=context, option_id="fit", address=bad)


# ---------------------------------------------------------------- nearest in a direction

FOUR = [8, 6, 2, 4]
EIGHT = list(PLACEMENT)

# (occupied, from, direction, expected). The first block is the contract's own
# examples; the rest are the corners of the rule.
NEAREST_VECTORS = [
    (FOUR, 8, "left", 4),
    (FOUR, 8, "right", 6),
    (FOUR, 8, "down", 2),
    (FOUR, 4, "up", 8),
    (EIGHT, None, "up", 8),
    (EIGHT, 8, "up", 8),
    (EIGHT, 9, "left", 8),
    (EIGHT, 7, "down", 4),
    (EIGHT, 1, "right", 2),
    # nothing highlighted: the first arrow starts from the centre
    (FOUR, None, "left", 4),
    (FOUR, None, "down", 2),
    (EIGHT, None, "right", 6),
    ([9, 3], None, "up", 9),
    ([7, 1], None, "down", 1),
    # the corner is reached by walking: Up then Left
    (EIGHT, 8, "left", 7),
    (EIGHT, 4, "up", 7),
    # straight ahead beats nearer-but-aside
    (FOUR, 6, "left", 4),
    ([8, 6, 2, 4, 9], 4, "right", 6),
    ([9, 4, 2], 9, "down", 2),
    # nothing ahead: the highlight stays put
    (FOUR, 2, "down", 2),
    (FOUR, 4, "left", 4),
    ([8], 8, "down", 8),
    # only something aside: it is still ahead, so it is reached
    ([8, 3], 8, "down", 3),
    ([7, 2], 7, "right", 2),
    # a tie in every respect but the number: the lower cell wins
    ([8, 9, 3, 1, 7], 8, "down", 1),
    # the current cell is never a candidate, even from the centre
    ([8, 6, 2, 4], 5, "up", 8),
    ([8, 6, 2, 4, 9, 3, 1, 7], 3, "up", 6),
    ([8, 6, 2, 4, 9, 3, 1, 7], 3, "left", 2),
]


@pytest.mark.parametrize("occupied, from_cell, direction, expected", NEAREST_VECTORS)
def test_an_arrow_reaches_the_nearest_occupied_cell(occupied, from_cell, direction, expected):
    assert nearest(occupied, from_cell, direction) == expected


def test_every_cardinal_of_a_four_option_ring_is_reachable_by_arrows_alone():
    """The defect the record names: walking a row leaves left unreachable from up."""
    reached = {None}
    frontier = [None]
    while frontier:
        here = frontier.pop()
        for direction in DIRECTIONS:
            there = nearest(FOUR, here, direction)
            if there not in reached:
                reached.add(there)
                frontier.append(there)
    assert reached - {None} == set(FOUR)


def test_nearest_refuses_what_is_not_a_cell_or_a_direction():
    with pytest.raises(ValueError, match="not a direction"):
        nearest(FOUR, 8, "north")
    with pytest.raises(ValueError, match="cannot be occupied"):
        nearest([8, 5], 8, "down")
    with pytest.raises(ValueError, match="not cells"):
        nearest([8, 10], 8, "down")


# ---------------------------------------------------------------- the device rings


def test_a_node_with_no_device_has_no_device_option():
    ring = resolve(Context(pointing=Pointing.NODE, targets=["printer_1"]), _photo_site())
    assert "device" not in [o.id for o in ring.options]
    assert not any(a.startswith("device:") for a in every_action([ring]))


def test_a_node_whose_device_is_not_bound_has_no_device_option():
    loose = Device(port="/dev/ttyUSB0", printer=True, bound=False)
    ring = _node_with_printer(loose)
    assert "device" not in [o.id for o in ring.options]


def test_a_bound_device_is_offered_after_move():
    ring = _node_with_printer()
    ids = [o.id for o in ring.options]
    assert ids.index("device") == ids.index("move") + 1
    device = walk(ring, address_of(ring, "device"))
    assert [c.label for c in device.children] == [
        "Watch",
        "Poll",
        "Monitor",
        "Query",
        "Unpin",
        "Rescan",
        "Link",
        "Control",
    ]
    # Link sits before Control on purpose: cell 1 on a devkit and on a printer alike.
    assert device.children[6].cell == 1 and device.children[7].cell == 7
    devkit = walk(_node_with_printer(Device(port="/dev/ttyACM0", bound=True)), "2")
    assert devkit.children[-1].label == "Link" and devkit.children[-1].cell == 1


def test_control_is_absent_when_the_board_is_not_a_printer():
    board = Device(port="/dev/ttyACM0", printer=False, bound=True)
    for ring in (_node_with_printer(board), _device_ring(board)):
        assert "control" not in every_address(ring).values()
        assert not any(a.startswith("control:") for a in every_action([ring]))


def test_pin_or_unpin_depends_on_whether_the_port_is_bound():
    assert "device:pin" in every_action([_device_ring(Device(port="/dev/ttyUSB0"))])
    assert "device:unpin" in every_action([_device_ring(PRINTER)])


def test_arm_or_disarm_depends_on_the_latch():
    disarmed = every_action([_control_ring(PRINTER)])
    assert "control:arm" in disarmed and "control:disarm" not in disarmed
    armed = every_action([_control_ring(Device(port="/dev/ttyUSB0", printer=True, armed=True))])
    assert "control:disarm" in armed and "control:arm" not in armed


def test_the_control_ring_offers_every_allowlisted_verb():
    assert set(every_action([_control_ring()])) == {
        "control:hotend-on",
        "control:hotend-off",
        "control:bed-on",
        "control:bed-off",
        "control:home",
        "control:home-xy",
        "control:home-z",
        "control:jog:Y+",
        "control:jog:X+",
        "control:jog:Y-",
        "control:jog:X-",
        "control:jog:Z+",
        "control:jog:Z-",
        "control:fan-on",
        "control:fan-off",
        "control:sd-resume",
        "control:sd-pause",
        "control:sd-abort",
        "control:motors-off",
        "control:quickstop",
        "control:estop",
        "control:arm",
    }


def test_stop_is_marked_destructive_and_nothing_else_on_the_ring_is():
    ring = _control_ring()
    assert {o.id for o in ring.options if o.destructive} == {"control:estop"}


def test_the_device_ring_stands_on_the_port_s_last_segment():
    assert _device_ring().title == "ttyUSB0"
    long_leaf = _device_ring(Device(port="/dev/serial/by-id/usb-Marlin_Ender-if00")).title
    assert len(long_leaf) <= LONGEST_LABEL and "/" not in long_leaf


def test_a_device_ring_with_nothing_to_stand_on_is_refused():
    with pytest.raises(ValueError, match="stands on a port"):
        resolve(Context(pointing=Pointing.DEVICE))


def test_a_device_ring_is_built_from_the_port_alone_when_nothing_more_is_known():
    ring = resolve(Context(pointing=Pointing.DEVICE, targets=["/dev/ttyACM1"]))
    assert ring.title == "ttyACM1"
    assert "device:pin" in every_action([ring])
    assert "control" not in [o.id for o in ring.options]


def _every_label(options):
    for option in options:
        yield option.label
        if option.children:
            yield from _every_label(option.children)


def test_every_device_and_control_label_fits():
    armed = Device(port="/dev/ttyUSB0", printer=True, armed=True, bound=True)
    for ring in (_node_with_printer(), _device_ring(), _control_ring(), _control_ring(armed)):
        for label in _every_label(ring.options):
            assert len(label) <= LONGEST_LABEL, label


def test_every_ring_the_device_opens_obeys_the_ceiling():
    for ring in (_node_with_printer(), _device_ring(), _control_ring()):
        for address in every_address(ring):
            for depth in range(1, len(address)):
                assert len(walk(ring, address[:depth]).children) <= MOST_OPTIONS


# ---------------------------------------------------------------- conformance

ADDRESS_PATHS = [
    ("control", ["Jog", "Y+"]),
    ("control", ["Jog", "Z-"]),
    ("control", ["Heat", "Bed on"]),
    ("control", ["Home", "All"]),
    ("control", ["Stop"]),
    ("control", ["Arm"]),
    ("device", ["Control", "Jog", "Y+"]),
    ("device", ["Unpin"]),
    ("node", ["Device", "Control", "Jog", "Y+"]),
    ("node", ["Why this"]),
]


def _by_labels(ring: Ring, path: list) -> str:
    """The address of a leaf named by its labels, computed by walking the ring."""
    options = ring.options
    address = ""
    for label in path:
        option = next(o for o in options if o.label == label)
        address += str(option.cell)
        options = option.children or []
    assert walk(ring, address).label == path[-1]
    return address


def nine_cells() -> dict:
    """The conformance vectors, generated from the functions under test.

    Generated rather than written down so the file cannot drift from the
    Python; the browser's implementation is held to this file.
    """
    rings = {"control": _control_ring(), "device": _device_ring(), "node": _node_with_printer()}
    return {
        "version": "0.1.0",
        "notes": (
            "Nine cells numbered as a numeric keypad: 7 8 9 / 4 5 6 / 1 2 3. "
            "Cell 5 (back) holds nothing. placement[i] is the cell of the i-th "
            "option; compass[s] is the cell of compass wedge s, up first and "
            "clockwise, s = angleToIndex(theta, 8) with startDeg -90. nearest: "
            "from the cell (5 when nothing is highlighted), a candidate is any "
            "occupied cell other than the current one whose displacement has a "
            "positive component along the direction; the best has the smallest "
            "offset aside, then the smallest distance along, then the lowest "
            "number; with no candidate the highlight stays where it was (null "
            "when nothing was highlighted). An address is the digits pressed "
            "through nested rings; the rings below are the ones its addresses "
            "are computed on."
        ),
        "placement": list(PLACEMENT),
        "back": BACK,
        "compass": list(COMPASS),
        "cells": {str(cell): list(at) for cell, at in CELLS.items()},
        "directions": {name: list(step) for name, step in DIRECTIONS.items()},
        "nearest": [
            {
                "occupied": list(occupied),
                "from": from_cell,
                "direction": direction,
                "expect": nearest(occupied, from_cell, direction),
            }
            for occupied, from_cell, direction, _ in NEAREST_VECTORS
        ],
        "addresses": [
            {"ring": name, "path": path, "address": _by_labels(rings[name], path)}
            for name, path in ADDRESS_PATHS
        ],
        "every_address": {name: every_address(ring) for name, ring in rings.items()},
        "rings": {name: ring.model_dump(mode="json") for name, ring in rings.items()},
    }


def test_the_conformance_file_is_what_the_functions_say():
    """Regenerate and compare, so an edit to either side is caught.

    To bring the file up to date after a deliberate change:
    ``uv run python tests/test_menu.py --write-conformance``.
    """
    assert CONFORMANCE.exists(), f"{CONFORMANCE} is missing; run this file with --write-conformance"
    on_disk = json.loads(CONFORMANCE.read_text(encoding="utf-8"))
    assert on_disk == nine_cells(), (
        "tests/conformance/nine_cells.json no longer matches the functions in "
        "apothecary/menu.py; regenerate it with "
        "`uv run python tests/test_menu.py --write-conformance` if the change "
        "was meant, and tell whoever holds the browser side."
    )


def test_the_conformance_file_holds_enough_vectors():
    vectors = nine_cells()
    assert len(vectors["nearest"]) >= 20
    assert {v["expect"] for v in vectors["nearest"]} <= set(CELLS) - {BACK}
    assert all(BACK not in [int(d) for d in a["address"]] for a in vectors["addresses"])


if __name__ == "__main__":
    if "--write-conformance" in sys.argv:
        CONFORMANCE.parent.mkdir(parents=True, exist_ok=True)
        CONFORMANCE.write_text(json.dumps(nine_cells(), indent=2) + "\n", encoding="utf-8")
        print(f"wrote {CONFORMANCE}")
    else:
        print(json.dumps(nine_cells(), indent=2))


# --- navigating and choosing pieces from the ring ------------------------------------


def _garage():
    from apothecary.example_hierarchy import create_example_site

    return create_example_site()


def test_the_canvas_ring_lists_the_pieces_at_this_level_and_the_way_up():
    """At the root, Pieces and no Up; zoomed in, Pieces of the focus and Up."""
    from apothecary.menu import carried_by

    root = resolve(Context(pointing=Pointing.CANVAS), _garage())
    labels = [o.label for o in root.options]
    assert labels[0] == "Pieces" and "Up" not in labels
    pieces = root.options[0]
    assert pieces.cell == 8 and pieces.children is not None
    # Thirteen pieces in the garage: two lettered groups, nothing lost.
    names = sorted(c.name for c in _garage().children)
    leaves = [leaf for group in pieces.children for leaf in group.children]
    assert [leaf.action for leaf in leaves] == [f"select:{n}" for n in names]
    assert all(len(leaf.label) <= LONGEST_LABEL for leaf in leaves)
    assert carried_by("select:printer_1").name == "VIEWER"

    zoomed = resolve(Context(pointing=Pointing.CANVAS, targets=["printer_1"]), _garage())
    labels = [o.label for o in zoomed.options]
    assert labels[:2] == ["Pieces", "Up"]
    assert zoomed.options[1].action == "zoom-out" and zoomed.options[1].cell == 6
    inside = zoomed.options[0].children
    assert [o.action for o in inside] == [
        "select:printer_1.frame_system",
        "select:printer_1.gantry_system",
    ]
    assert zoomed.title == shorten("printer_1")


def test_the_node_ring_goes_into_a_piece_and_up_to_its_parent():
    top = resolve(Context(pointing=Pointing.NODE, targets=["printer_1"]), _garage())
    labels = [o.label for o in top.options]
    assert "Into" in labels and "Up" not in labels  # a top-level piece has no parent
    into = next(o for o in top.options if o.label == "Into")
    assert [c.action for c in into.children] == [
        "select:printer_1.frame_system",
        "select:printer_1.gantry_system",
    ]

    board = resolve(
        Context(pointing=Pointing.NODE, targets=["printer_1.frame_system.mainboard"]), _garage()
    )
    labels = [o.label for o in board.options]
    assert "Into" not in labels  # a leaf holds nothing
    up = next(o for o in board.options if o.label == "Up")
    assert up.action == "select:printer_1.frame_system"

    # Every piece is reachable by an address from the root ring, and walks back to itself.
    root = resolve(Context(pointing=Pointing.CANVAS), _garage())
    for address, action in every_address(root).items():
        if action.startswith("select:"):
            assert walk(root, address).action == action


def test_more_than_sixty_four_pieces_is_a_refusal_not_a_bigger_menu():
    from apothecary.hierarchy import Assembly

    crowd = Assembly(
        name="crowd",
        role="site",
        children=[Assembly(name=f"piece_{i:03d}", role="structure") for i in range(65)],
    )
    with pytest.raises(RingTooFull, match="65 pieces"):
        resolve(Context(pointing=Pointing.CANVAS), crowd)
    fits = Assembly(
        name="fits",
        role="site",
        children=[Assembly(name=f"piece_{i:03d}", role="structure") for i in range(64)],
    )
    pieces = resolve(Context(pointing=Pointing.CANVAS), fits).options[0]
    assert len(pieces.children) == 8 and all(len(g.children) == 8 for g in pieces.children)
