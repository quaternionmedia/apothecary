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
from ring_helpers import address_of, every_action, every_address, walk

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
    check_ring,
    control_options,
    nearest,
    resolve,
    shorten,
)
from apothecary.primitives import Cube

CONFORMANCE = Path(__file__).parent / "conformance" / "nine_cells.json"
VIEWER = Path(__file__).parents[1] / "templates" / "fractal_viewer.html.j2"


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
    """A long list gets groups of at most eight, and every name is still reachable."""
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


def test_an_option_that_does_not_apply_is_absent_rather_than_greyed_out():
    ring = resolve(Context(pointing=Pointing.NODE, targets=["printer_1"]), _photo_site())
    assert all(option.enabled for option in ring.options)


def test_a_node_ring_can_explain_its_piece():
    ring = resolve(Context(pointing=Pointing.NODE, targets=["plate_1"]), _photo_site())
    assert "explain" in every_action([ring])


@pytest.mark.parametrize("pointing", list(Pointing))
def test_every_kind_of_ring_obeys_both_limits(pointing):
    ring = resolve(
        Context(pointing=pointing, targets=["plate_1"]),
        _photo_site(),
        site_names=["bench", "garage"],
        groups=["plate", "disc"],
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
        resolve(Context(pointing=pointing, targets=["plate_1"]), site)
    assert site.model_dump_json() == before


def test_a_choice_is_carried_as_an_intent_and_nothing_else():
    context = Context(pointing=Pointing.NODE, targets=["plate_1"])
    intent = Intent(action="zoom-in", context=context, option_id="zoom")
    assert intent.action == "zoom-in"
    assert intent.context.targets == ["plate_1"]


def test_a_context_ignores_what_a_page_sends_beyond_it():
    """The pages still send where on screen the ring opened; nothing reads it."""
    context = Context.model_validate(
        {"pointing": "canvas", "targets": [], "where": {"x": 3, "y": 4}}
    )
    assert context.model_dump() == {"pointing": Pointing.CANVAS, "targets": []}


def test_the_things_a_ring_names_are_the_paths_everything_else_uses():
    site = _photo_site()
    ring = resolve(Context(pointing=Pointing.NODE, targets=["plate_1"]), site)
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
        "print:start",
        "control:motors-off",
        "control:quickstop",
        "control:break-wait",
        "control:mesh-on",
        "control:mesh-off",
        "control:corner:FL",
        "control:corner:FR",
        "control:corner:BL",
        "control:corner:BR",
        "level:probe",
        "level:read",
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
    with pytest.raises(RingTooFull, match="65 to choose between"):
        resolve(Context(pointing=Pointing.CANVAS), crowd)
    fits = Assembly(
        name="fits",
        role="site",
        children=[Assembly(name=f"piece_{i:03d}", role="structure") for i in range(64)],
    )
    pieces = resolve(Context(pointing=Pointing.CANVAS), fits).options[0]
    assert len(pieces.children) == 8 and all(len(g.children) == 8 for g in pieces.children)


def test_the_level_ring_seats_the_corners_as_they_lie_on_the_bed():
    """Front left at 1, front right at 3, back left at 7, back right at 9: the keypad is the bed."""
    ring = _control_ring()
    level = walk(ring, address_of(ring, "control:level"))
    cells = {c.action: c.cell for c in level.children}
    assert cells["control:corner:FL"] == 1 and cells["control:corner:FR"] == 3
    assert cells["control:corner:BL"] == 7 and cells["control:corner:BR"] == 9
    assert cells["level:probe"] == 8 and cells["level:read"] == 6
    assert address_of(ring, "level:probe") == "48"


def test_the_canvas_ring_opens_and_closes_the_panels_the_page_registers():
    """Panels on the canvas ring: one cell per panel the world's page registers,
    cardinals first, and the two lists -- the resolver's and the template's
    data-panel marks -- are the same, so a panel cannot appear on one side only."""
    import re

    from apothecary.menu import PANELS, carried_by

    root = resolve(
        Context(pointing=Pointing.CANVAS),
        _garage(),
        site_names=["garage", "parts_library"],
        groups=["wall", "furniture"],
    )
    panels = next(o for o in root.options if o.label == "Panels")
    assert panels.cell == 9 and panels.children is not None  # after Pieces, Site, Group, Fit
    # The canvas ring's Camera became Pictures, in the same seat.
    pictures = next(o for o in root.options if o.label == "Pictures")
    assert pictures.cell == 3 and [(c.label, c.action, c.cell) for c in pictures.children] == [
        ("Add", "picture:add:@floor", 8),
        ("Floor", None, 6),  # the floor's Fit, Camera and Picture
        ("Purge", "picture:purge", 2),
        ("Gather", "camera:gather", 4),
    ]
    assert [c.destructive for c in pictures.children] == [False, False, True, False]
    assert carried_by("picture:add:@floor").name == "VIEWER"
    assert carried_by("picture:purge").name == "VIEWER"
    # Site (Contents, its problems, its SCAD, Pinned), Selected, Jobs and Pictures
    # (every picture, and the gathering) each a cell; the machine and its comms
    # log behind one; the rail last.
    assert [(c.label, c.action, c.cell) for c in panels.children] == [
        ("Site", "panel:toggle:site", 8),
        ("Selected", "panel:toggle:selected", 6),
        ("Jobs", "panel:toggle:jobs", 2),
        ("Pictures", "panel:toggle:pictures", 4),
        ("Machine", None, 9),
        ("Rail", "panel:rail:toggle", 3),
    ]
    machine = next(c for c in panels.children if c.label == "Machine")
    assert [(c.action, c.cell) for c in machine.children] == [
        ("panel:toggle:machine", 8),
        ("panel:toggle:log", 6),
    ]
    assert address_of(root, "panel:site") == "98"  # by the option's id
    assert address_of(root, "panel:pictures") == "94"
    assert address_of(root, "panel:machine") == "998"
    assert address_of(root, "panel:rail") == "93"
    for pid in ("site", "pictures"):
        assert carried_by(f"panel:toggle:{pid}").name == "VIEWER"
    # The retired panels are on no ring.
    for gone in ("contents", "validation", "scad", "kept", "camera"):
        assert f"panel:toggle:{gone}" not in set(every_action([root])), gone
    # The page's sections are marked in its markup; Pictures is registered at
    # start and the machine and its log when a printer is opened. Both lists are
    # the resolver's, in order.
    page = VIEWER.read_text(encoding="utf-8")
    marked = re.findall(r'class="panel-section"[^>]*data-panel="([\w-]+)"', page)
    registered = re.findall(r"panels\.register\('([\w-]+)'", page)
    assert marked == [pid for pid, _ in PANELS[: len(marked)]]
    assert sorted(registered) == sorted(pid for pid, _ in PANELS[len(marked) :])
    for gone in ("contents", "validation", "scad", "kept", "camera"):
        assert f'data-panel="{gone}"' not in page and f"register('{gone}'" not in page


# --- pictures and cameras on the ring (pictures plan, Phase 4) -------------------------
#
# A host -- a root structure with a footprint that is not a made piece -- appends
# Camera and Picture to its node ring; the floor's are under the canvas ring's
# Pictures › Floor, since the floor is a selection and not a node (the owner's
# decision of 2026-09-27: no new ring shapes). A shape is made from its host's
# Picture › Make; Word and Drop are under Picture on a made piece.


def _ring_labels(option) -> list:
    return [(c.label, c.cell) for c in option.children]


def _group(ring_or_option, *labels):
    """The option reached by following labels down from a ring or an option."""
    options = (
        ring_or_option.options if isinstance(ring_or_option, Ring) else ring_or_option.children
    )
    here = None
    for label in labels:
        here = next((o for o in options if o.label == label), None)
        assert here is not None, f"no {label!r} among {[o.label for o in options]}"
        options = here.children or []
    return here


def _view(view_id="view_1", *, sized=True, kept=True, shapes=3, picture="bench_top.png"):
    from apothecary.menu import ShapeSeen, ViewSeen

    return ViewSeen(
        id=view_id,
        picture=picture,
        sized=sized,
        kept=kept,
        shapes=[ShapeSeen(index=i, word="disc") for i in range(shapes)],
    )


def _context(**here):
    from apothecary.menu import CameraSeen, PictureContext, Place

    mine = CameraSeen(id="bench_cam", label="bench cam")
    return PictureContext(
        cameras=[mine],
        asked=True,
        pictures=["bench_top.png"],
        here=Place(**{"camera": mine, **here}),
    )


def _depth(options, below=0) -> int:
    return max(
        (_depth(o.children, below + 1) if o.children else below + 1 for o in options),
        default=below,
    )


def test_a_host_appends_camera_and_picture_and_no_existing_cell_moves():
    garage = _garage()
    bare = resolve(Context(pointing=Pointing.NODE, targets=["workbench"]), garage)
    assert [(o.label, o.cell) for o in bare.options] == [
        ("Zoom in", 8),
        ("Move", 6),
        ("Why this", 2),
        ("Into", 4),
        ("Camera", 9),
        ("Picture", 3),
    ]
    # With nothing pinned or allowed: Pin here › Allow, and Picture › Add.
    assert _ring_labels(_group(bare, "Camera")) == [("Pin here", 8)]
    assert _group(bare, "Camera", "Pin here", "Allow").action == "camera:allow"
    assert [c.action for c in _group(bare, "Picture").children] == ["picture:add"]
    # A printer with a board pinned keeps its Device cell where it was.
    printer = resolve(
        Context(pointing=Pointing.NODE, targets=["printer_1"]), garage, device=PRINTER
    )
    assert [(o.label, o.cell) for o in printer.options][:4] == [
        ("Zoom in", 8),
        ("Move", 6),
        ("Device", 2),
        ("Why this", 4),
    ]
    # A printer drawn as a part (ender3) ends with Part: the fullest node ring, eight.
    assert [o.label for o in printer.options][-3:] == ["Camera", "Picture", "Part"]
    assert len(printer.options) == MOST_OPTIONS


def test_camera_and_picture_are_absent_below_the_root_and_where_nothing_can_be_pinned():
    garage = _garage()
    for path in ("printer_1.frame_system", "garage_building"):
        ring = resolve(Context(pointing=Pointing.NODE, targets=[path]), garage)
        labels = [o.label for o in ring.options]
        assert "Camera" not in labels and "Picture" not in labels, (path, labels)


# --- the part editor on the ring (the part-editing spike's decision) --------------------
#
# One editor, in Selected, for a part and for a piece made from a picture: Part ›
# Edit opens it there. Appended after every cell the ring had, so none moves; the
# page carries it, and Apply goes through the part and made routes.


def test_a_part_and_a_made_piece_end_with_part_edit_and_nothing_else_does():
    from apothecary.menu import PictureContext, carried_by

    garage = _garage()
    # A part below the root (the board inside a printer) and a part at the root.
    for path in ("printer_1.frame_system.mainboard", "footpedal", "printer_1"):
        ring = resolve(Context(pointing=Pointing.NODE, targets=[path]), garage)
        part = ring.options[-1]
        assert part.label == "Part" and part.id == "part", (path, [o.label for o in ring.options])
        assert [(c.label, c.action) for c in part.children] == [("Edit", "part:edit")]
        assert len(ring.options) <= MOST_OPTIONS
    # A made piece has Part too, after its Picture.
    site = _garage()
    site.children.append(Assembly(name="disc_1", role="word", base=Cube(size=10.0)))
    told = PictureContext(made=["disc_1"], words=["disc", "plate"])
    made = resolve(Context(pointing=Pointing.NODE, targets=["disc_1"]), site, picture=told)
    assert [o.label for o in made.options][-2:] == ["Picture", "Part"]
    assert _group(made, "Part", "Edit").action == "part:edit"
    # A structure that is neither is left alone: the bench's ring ends as it did.
    bench = resolve(Context(pointing=Pointing.NODE, targets=["workbench"]), garage)
    assert [o.label for o in bench.options][-2:] == ["Camera", "Picture"]
    assert carried_by("part:edit").name == "VIEWER"


def test_a_made_piece_has_picture_with_word_and_drop_and_no_camera():
    from apothecary.menu import PictureContext

    site = _garage()
    site.children.append(Assembly(name="disc_1", role="word", base=Cube(size=10.0)))
    told = PictureContext(made=["disc_1"], words=["disc", "plate", "post"])
    ring = resolve(Context(pointing=Pointing.NODE, targets=["disc_1"]), site, picture=told)
    labels = [o.label for o in ring.options]
    assert "Camera" not in labels and labels[-2:] == ["Picture", "Part"]
    picture = _group(ring, "Picture")
    assert _ring_labels(picture) == [("Word", 8), ("Drop", 6)]
    assert [c.action for c in _group(picture, "Word").children] == [
        "picture:word:disc",
        "picture:word:plate",
        "picture:word:post",
    ]
    assert _group(picture, "Drop").destructive
    # A made piece is not a host: it holds no camera and no view of its own.
    assert "picture:add" not in every_action([ring])


def test_the_floor_is_reached_from_the_canvas_ring_with_nothing_pinned():
    from apothecary.menu import PictureContext

    empty = Assembly(name="empty", role="site")
    bare = resolve(Context(pointing=Pointing.CANVAS), empty)
    assert _ring_labels(_group(bare, "Pictures", "Floor")) == [("Fit", 8), ("Camera", 6)]
    told = PictureContext(pictures=["bench_top.png"])
    ring = resolve(Context(pointing=Pointing.CANVAS), empty, picture=told)
    floor = _group(ring, "Pictures", "Floor")
    assert _ring_labels(floor) == [("Fit", 8), ("Camera", 6), ("Picture", 2)]
    assert _group(floor, "Fit").action == "fit:@floor"
    assert _group(floor, "Camera", "Pin here", "Allow").action == "camera:allow:@floor"
    assert [c.action for c in _group(floor, "Picture").children] == [None]  # Folder
    assert (
        _group(floor, "Picture", "Folder", "bench_top").action == "picture:pin:bench_top.png:@floor"
    )
    # The floor's Add is one ring up, so an action keeps one address.
    assert _group(ring, "Pictures", "Add").action == "picture:add:@floor"
    # Every floor verb says it is the floor's, whoever carries it.
    from apothecary.menu import carried_by

    for action in every_action([ring]):
        carried_by(action)


def test_a_host_whose_camera_is_another_browsers_offers_pin_and_unpin_only():
    from apothecary.menu import CameraSeen, PictureContext, Place

    theirs = CameraSeen(id="another_browsers_camera", label="their cam")
    told = PictureContext(
        cameras=[CameraSeen(id="bench_cam", label="bench cam")],
        asked=True,
        here=Place(camera=theirs),
    )
    ring = resolve(Context(pointing=Pointing.NODE, targets=["workbench"]), _garage(), picture=told)
    camera = _group(ring, "Camera")
    assert _ring_labels(camera) == [("Pin here", 8), ("Unpin", 6)]
    assert [c.action for c in _group(camera, "Pin here").children] == ["camera:pin:bench_cam"]
    # This browser's own: Live (or Still while live), Take picture, then Unpin.
    mine = resolve(
        Context(pointing=Pointing.NODE, targets=["workbench"]), _garage(), picture=_context()
    )
    assert [c.action for c in _group(mine, "Camera").children] == [
        None,
        "camera:live",
        "camera:take-picture",
        "camera:unpin",
    ]
    live = resolve(
        Context(pointing=Pointing.NODE, targets=["workbench"]),
        _garage(),
        picture=_context(live=True),
    )
    assert _group(live, "Camera", "Still").action == "camera:still"


def test_the_picture_group_offers_make_only_on_a_sized_view_and_forget_only_on_a_kept_one():
    ring = resolve(
        Context(pointing=Pointing.NODE, targets=["workbench"]),
        _garage(),
        picture=_context(views=[_view(sized=False, kept=False)], drawn="view_1"),
    )
    picture = _group(ring, "Picture")
    assert [c.label for c in picture.children] == ["Add", "Folder", "Size", "Unpin"]
    sized = resolve(
        Context(pointing=Pointing.NODE, targets=["workbench"]),
        _garage(),
        picture=_context(views=[_view()], drawn="view_1"),
    )
    picture = _group(sized, "Picture")
    assert [(c.label, c.cell) for c in picture.children] == [
        ("Add", 8),
        ("Folder", 6),
        ("Make", 2),
        ("Size", 4),
        ("Unpin", 9),
        ("Forget", 3),
    ]
    # Make › Make all beside each found shape, by index.
    assert [(c.label, c.action) for c in _group(picture, "Make").children] == [
        ("Make all", "picture:make-all:view_1"),
        ("disc 0", "picture:make:view_1:0"),
        ("disc 1", "picture:make:view_1:1"),
        ("disc 2", "picture:make:view_1:2"),
    ]
    assert _group(picture, "Forget").destructive


def test_find_shapes_on_a_searched_view_is_offered_only_where_another_finder_can_read_it():
    one = _context(views=[_view()], drawn="view_1")
    one.finders = ["plain"]
    two = _context(views=[_view()], drawn="view_1")
    two.finders = ["plain", "stated"]
    for told, offered in ((one, False), (two, True)):
        ring = resolve(
            Context(pointing=Pointing.NODE, targets=["workbench"]), _garage(), picture=told
        )
        labels = [c.label for c in _group(ring, "Picture").children]
        assert ("Find shapes" in labels) is offered
    ring = resolve(Context(pointing=Pointing.NODE, targets=["workbench"]), _garage(), picture=two)
    assert [c.action for c in _group(ring, "Picture", "Find shapes").children] == [
        "picture:find:stated"
    ]


def test_find_shapes_is_the_step_after_a_view_is_pinned_and_appended_after_unpin():
    """A view pinned and not yet searched offers Find shapes, the one finder that can
    read it as a leaf or several behind it; once searched, Find shapes offers only the
    other finders, and is absent when there are none. Appended last, so Unpin and
    Forget keep their cells whether it is there or not; and no Make before shapes."""
    unsearched = _context(views=[_view(shapes=0, sized=False)], drawn="view_1")
    unsearched.here.views[0].finder = None
    unsearched.finders = ["plain"]
    ring = resolve(
        Context(pointing=Pointing.NODE, targets=["workbench"]), _garage(), picture=unsearched
    )
    picture = _group(ring, "Picture")
    assert [(c.label, c.cell) for c in picture.children] == [
        ("Add", 8),
        ("Folder", 6),
        ("Size", 2),
        ("Unpin", 4),
        ("Forget", 9),
        ("Find shapes", 3),
    ]
    assert _group(picture, "Find shapes").action == "picture:find:plain"
    # Two finders can read it: Find shapes › each, by name.
    unsearched.finders = ["plain", "stated"]
    ring = resolve(
        Context(pointing=Pointing.NODE, targets=["workbench"]), _garage(), picture=unsearched
    )
    assert [c.action for c in _group(ring, "Picture", "Find shapes").children] == [
        "picture:find:plain",
        "picture:find:stated",
    ]
    # Searched by the only finder there is: nothing more to find.
    searched = _context(views=[_view()], drawn="view_1")
    searched.finders = ["plain"]
    ring = resolve(
        Context(pointing=Pointing.NODE, targets=["workbench"]), _garage(), picture=searched
    )
    labels = [c.label for c in _group(ring, "Picture").children]
    assert "Find shapes" not in labels and labels[-2:] == ["Unpin", "Forget"]
    # At the floor, the same step under Pictures › Floor › Picture.
    floor = resolve(Context(pointing=Pointing.CANVAS), _garage(), picture=unsearched)
    assert [
        c.action for c in _group(floor, "Pictures", "Floor", "Picture", "Find shapes").children
    ] == [
        "picture:find:plain:@floor",
        "picture:find:stated:@floor",
    ]


def test_keep_is_gone_from_every_ring_and_take_picture_is_in_its_place():
    """Camera › Keep went: Take picture always pins a view. A camera of this browser's
    holds Pin here, Live (or Still), Take picture and Unpin, at a host and at the floor."""
    told = _context(views=[_view()], drawn="view_1")
    told.finders = ["plain", "stated"]
    rings = [
        resolve(Context(pointing=Pointing.CANVAS), _garage(), picture=told),
        resolve(Context(pointing=Pointing.NODE, targets=["workbench"]), _garage(), picture=told),
        resolve(
            Context(pointing=Pointing.NODE, targets=["printer_1"]),
            _garage(),
            device=PRINTER,
            picture=told,
        ),
    ]
    actions = set(every_action(rings))
    assert not [a for a in actions if a.startswith("camera:keep")], sorted(actions)
    assert {"camera:take-picture", "camera:take-picture:@floor"} <= actions
    for ring in rings:
        for address in every_address(ring):
            assert walk(ring, address).label != "Keep", address
    camera = _group(rings[1], "Camera")
    assert [(c.label, c.cell) for c in camera.children] == [
        ("Pin here", 8),
        ("Live", 6),
        ("Take picture", 2),
        ("Unpin", 4),
    ]


@pytest.mark.parametrize("how_many", [65, 500])
def test_a_root_with_many_pictures_still_resolves_and_a_chosen_one_fills_the_eighth(how_many):
    told = _context()
    told.pictures = [f"shot_{i:03d}.png" for i in range(how_many)]
    ring = resolve(Context(pointing=Pointing.NODE, targets=["workbench"]), _garage(), picture=told)
    folder = _group(ring, "Picture", "Folder")
    assert len(folder.children) == MOST_OPTIONS
    assert [c.action for c in folder.children][:7] == [
        f"picture:pin:shot_{i:03d}.png" for i in range(7)
    ]
    # More opens the Pictures panel, where every picture is listed with Pin here.
    assert (folder.children[-1].label, folder.children[-1].action) == ("More", "picture:more")
    told.chosen_picture = "shot_042.png"
    ring = resolve(Context(pointing=Pointing.NODE, targets=["workbench"]), _garage(), picture=told)
    last = _group(ring, "Picture", "Folder").children[-1]
    assert last.action == "picture:pin:shot_042.png" and last.cell == 7
    assert last.label == "Pin shot_042" and not last.marked


def _folder(told, floor: bool = False):
    """Picture › Folder's cells, at the bench or (floor) under the canvas ring's Pictures › Floor."""
    if floor:
        ring = resolve(Context(pointing=Pointing.CANVAS, targets=[]), _garage(), picture=told)
        return _group(ring, "Pictures", "Floor", "Picture", "Folder").children
    ring = resolve(Context(pointing=Pointing.NODE, targets=["workbench"]), _garage(), picture=told)
    return _group(ring, "Picture", "Folder").children


@pytest.mark.parametrize("floor", [False, True], ids=["bench", "floor"])
def test_a_picture_chosen_in_pictures_older_than_the_seven_is_folders_eighth_cell(floor):
    """Chosen in Pictures and older than the seven newest, a picture is Folder's eighth
    cell -- "Pin" and as much of its name as fits -- which pins it where the ring stands.
    Unchosen, or chosen and gone from the folder, the eighth is More."""
    told = _context()
    told.pictures = [f"uploads/bench_shot_{i:02d}.png" for i in range(12)]
    tail = ":@floor" if floor else ""
    assert [(o.label, o.action) for o in _folder(told, floor)][-1] == (
        "More",
        f"picture:more{tail}",
    )
    told.chosen_picture = "uploads/bench_shot_09.png"
    cells = _folder(told, floor)
    assert len(cells) == MOST_OPTIONS
    last = cells[-1]
    assert (last.cell, last.action) == (7, f"picture:pin:uploads/bench_shot_09.png{tail}")
    assert last.label.startswith("Pin ") and len(last.label) <= LONGEST_LABEL
    assert last.label == "Pin bench 09"
    assert not any(o.marked for o in cells)
    told.chosen_picture = "uploads/no_longer_there.png"
    assert _folder(told, floor)[-1].label == "More"


def test_a_picture_chosen_among_the_seven_is_marked_in_its_own_cell():
    """Chosen and among the seven newest, a picture's own cell is marked and nothing else
    changes: the eighth is still More, or absent when there are no more."""
    told = _context()
    told.pictures = [f"shot_{i:02d}.png" for i in range(10)]
    unchosen = _folder(told)
    told.chosen_picture = "shot_03.png"
    cells = _folder(told)
    assert [o.marked for o in cells] == [o.action == "picture:pin:shot_03.png" for o in cells]
    assert [(o.label, o.cell, o.action) for o in cells] == [
        (o.label, o.cell, o.action) for o in unchosen
    ]
    assert cells[-1].label == "More"
    told.pictures = told.pictures[:5]
    cells = _folder(told)
    assert len(cells) == 5 and [o.label for o in cells if o.marked] == ["shot_03"]


def test_a_host_with_more_than_eight_views_still_resolves_and_a_chosen_view_fills_the_eighth():
    views = [_view(f"view_{i:02d}", picture=f"shot_{i:02d}.png") for i in range(12)]
    told = _context(views=views, drawn="view_00")
    ring = resolve(Context(pointing=Pointing.NODE, targets=["workbench"]), _garage(), picture=told)
    listed = _group(ring, "Picture", "Views")
    assert [c.action for c in listed.children] == [
        *(f"picture:draw:view_{i:02d}" for i in range(7)),
        "picture:views",
    ]
    told.here.chosen_view = "view_10"
    ring = resolve(Context(pointing=Pointing.NODE, targets=["workbench"]), _garage(), picture=told)
    assert _group(ring, "Picture", "Views").children[-1].action == "picture:draw:view_10"


def test_garage_with_sixty_four_made_pieces_still_resolves_the_canvas_ring():
    from apothecary.menu import PictureContext

    site = _garage()
    made = [f"disc_{i}" for i in range(1, 65)]
    for name in made:
        site.children.append(Assembly(name=name, role="word", base=Cube(size=10.0)))
    ring = resolve(Context(pointing=Pointing.CANVAS), site, picture=PictureContext(made=made))
    pieces = _group(ring, "Pieces")
    assert pieces.cell == 8 and len(pieces.children) <= MOST_OPTIONS
    assert pieces.children[-1].label == "Made"
    reachable = {a for a in every_action([ring]) if a.startswith("select:")}
    assert reachable == {f"select:{c.name}" for c in site.children}
    made_cell = _group(ring, "Pieces", "Made")
    assert {leaf.action for group in made_cell.children for leaf in group.children} == {
        f"select:{m}" for m in made
    }


def test_the_fullest_context_holds_every_ring_to_eight_and_says_how_deep_it_goes():
    """A board, a camera, several views, many shapes, many pictures, several finders:
    every ring and sub-ring holds eight or fewer. The deepest path on a node ring is
    four rings (Picture › Make › group › shape); on the canvas ring the floor is two
    further down (Pictures › Floor › Picture › Make › group › shape), the level deeper
    the owner's decision accepts for the floor having no ring of its own."""
    from apothecary.menu import CameraSeen

    views = [_view(f"view_{i:02d}", shapes=32) for i in range(10)]
    told = _context(views=views, drawn="view_00")
    told.pictures = [f"shot_{i:03d}.png" for i in range(500)]
    told.finders = ["plain", "stated"]
    told.words = ["disc", "plate", "post", "slot", "wedge"]
    told.cameras = [CameraSeen(id=f"cam_{i}", label=f"camera {i}") for i in range(10)]
    node = resolve(
        Context(pointing=Pointing.NODE, targets=["printer_1"]),
        _garage(),
        device=PRINTER,
        picture=told,
    )
    canvas = resolve(
        Context(pointing=Pointing.CANVAS),
        _garage(),
        site_names=["garage", "parts_library", "datum_core"],
        groups=["wall", "furniture"],
        picture=told,
    )
    for ring in (node, canvas):
        assert len(ring.options) <= MOST_OPTIONS
        for address in every_address(ring):
            for depth in range(1, len(address)):
                assert len(walk(ring, address[:depth]).children) <= MOST_OPTIONS
    picture_paths = [a for a, act in every_address(node).items() if act.startswith("picture:")]
    assert max(len(a) for a in picture_paths) == 4
    floor_paths = [a for a, act in every_address(canvas).items() if act.startswith("picture:make:")]
    assert max(len(a) for a in floor_paths) == 6


def test_make_make_all_drop_and_a_made_pieces_word_are_the_servers_and_the_rest_the_viewers():
    from apothecary.menu import carried_by

    for action in (
        "picture:make:view_1:0",
        "picture:make-all:view_1",
        "picture:drop",
        "picture:word:plate",
    ):
        assert carried_by(action).name == "SERVER", action
    for action in (
        "picture:add",
        "picture:add:@floor",
        "picture:pin:bench_top.png",
        "picture:draw:view_1",
        "picture:size",
        "picture:find:plain",
        "picture:find:stated:@floor",
        "picture:unpin",
        "picture:forget",
        "picture:more",
        "picture:views",
        "picture:purge",
        "camera:pin:bench_cam",
        "camera:allow:@floor",
        "camera:live",
        "camera:still",
        "camera:take-picture",
        "camera:unpin",
        "camera:gather",
        "fit:@floor",
    ):
        assert carried_by(action).name == "VIEWER", action
    # A picture whose name reads like a server verb is still only pinned.
    assert carried_by("picture:pin:make:3.png").name == "VIEWER"


def test_the_camera_panels_retired_cells_are_off_every_ring():
    """Allow, Capture, Place, Unplace and Open as one left with the camera panel's
    sections: the camera is pinned and takes pictures from its host's Camera."""
    rings = [
        resolve(Context(pointing=Pointing.CANVAS), _garage(), picture=_context()),
        resolve(
            Context(pointing=Pointing.NODE, targets=["workbench"]), _garage(), picture=_context()
        ),
    ]
    actions = set(every_action(rings))
    for gone in (
        "camera:capture",
        "camera:place",
        "camera:open",
        "camera:unplace",
        "camera:add",
        "camera:purge",
        "camera:allow",
    ):
        assert gone not in actions, gone


# --- carried by the server: the intent route's picture arms --------------------------


from test_views_api import world  # noqa: E402, F401 - the views world, as a fixture here


@pytest.fixture
def carried(world):  # noqa: F811 - the fixture imported above
    """The views world of tests/test_views_api.py, with the bench's view pinned
    and sized: a client, and the view as the page has it."""
    from fastapi.testclient import TestClient
    from test_views_api import _pin

    from apothecary.api import app

    client = TestClient(app)
    view = _pin(client, mm_across=1800)
    return client, view


def _told_about(view: dict):
    from apothecary.menu import PictureContext, Place, ShapeSeen, ViewSeen

    return PictureContext(
        here=Place(
            views=[
                ViewSeen(
                    id=view["id"],
                    picture=view["picture"],
                    finder=view["finder"],
                    sized=bool(view["mat"] and view["mat"]["width"]),
                    shapes=[
                        ShapeSeen(index=s["index"], word=s["word"], status=s["status"])
                        for s in view["shapes"]
                    ],
                )
            ],
            drawn=view["id"],
        )
    )


def _choose(client, ring: dict, address: str, targets, pointing="node") -> dict:
    """Walk a ring's JSON by address, then send the leaf as the page does."""
    options = ring["options"]
    option = None
    for digit in address:
        option = next(o for o in options if o["cell"] == int(digit))
        options = option.get("children") or []
    intent = {
        "action": option["action"],
        "option_id": option["id"],
        "address": address,
        "context": {"pointing": pointing, "targets": list(targets)},
    }
    return client.post("/menu/intent", json={"intent": intent, "site": "garage"})


def _address(ring: dict, action: str) -> str:
    def search(options, so_far):
        for o in options:
            here = f"{so_far}{o['cell']}"
            if o.get("action") == action:
                return here
            found = search(o.get("children") or [], here)
            if found:
                return found
        return None

    found = search(ring["options"], "")
    assert found, f"{action} is on no cell"
    return found


def test_a_shape_is_made_worded_and_dropped_through_the_ring_and_the_intent_route(carried):
    client, view = carried
    told = _told_about(view).model_dump(mode="json")
    ring = client.post(
        "/menu/resolve",
        json={
            "context": {"pointing": "node", "targets": ["workbench"]},
            "site": "garage",
            "picture": told,
        },
    ).json()
    make = _address(ring, f"picture:make:{view['id']}:1")
    assert make.startswith(_address(ring, f"picture:make-all:{view['id']}")[:2])
    answer = _choose(client, ring, make, ["workbench"])
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["carried_by"] == "the server carries it out" and body["address"] == make
    piece = body["did"].split("made ", 1)[1]
    assert piece in {s["name"] for s in body["site"]["structures"]}
    attached = client.get("/sites/garage/attached").json()
    assert attached["made"][piece]["shape_index"] == 1

    # The made piece's own ring: the route says it is made, whatever the page told.
    ring = client.post(
        "/menu/resolve",
        json={"context": {"pointing": "node", "targets": [piece]}, "site": "garage"},
    ).json()
    labels = [o["label"] for o in ring["options"]]
    assert "Camera" not in labels and labels[-2:] == ["Picture", "Part"]
    answer = _choose(client, ring, _address(ring, "picture:word:plate"), [piece])
    assert answer.status_code == 200, answer.text
    assert client.get("/sites/garage/attached").json()["made"][piece]["word"] == "plate"
    answer = _choose(client, ring, _address(ring, "picture:drop"), [piece])
    assert answer.status_code == 200, answer.text
    assert piece not in {s["name"] for s in answer.json()["site"]["structures"]}
    shapes = client.get("/sites/garage/attached").json()["views"][0]["shapes"]
    assert shapes[1]["status"] == "found"

    # Make all, from the same ring once more.
    ring = client.post(
        "/menu/resolve",
        json={
            "context": {"pointing": "node", "targets": ["workbench"]},
            "site": "garage",
            "picture": told,
        },
    ).json()
    answer = _choose(client, ring, _address(ring, f"picture:make-all:{view['id']}"), ["workbench"])
    assert answer.status_code == 200, answer.text
    assert answer.json()["did"].startswith("made 3 piece(s)")


def test_a_carried_picture_intent_is_refused_with_its_reason_and_never_a_500(carried):
    client, view = carried

    def send(action, targets=("workbench",), site="garage"):
        intent = {
            "action": action,
            "option_id": action,
            "context": {"pointing": "node", "targets": list(targets)},
        }
        body = {"intent": intent}
        if site:
            body["site"] = site
        return client.post("/menu/intent", json=body)

    from test_views_api import _pin

    unsized = _pin(client)
    cases = {
        "picture:make": 400,
        "picture:make:": 400,
        f"picture:make:{view['id']}:x": 400,
        f"picture:make:{view['id']}:9": 404,
        "picture:make:view_nowhere:0": 404,
        f"picture:make:{unsized['id']}:0": 409,
        "picture:make-all": 400,
        "picture:make-all:view_nowhere": 404,
        "picture:drop": 404,
        "picture:word": 400,
        "picture:word:no_such_word": 404,
    }
    for action, status in cases.items():
        answer = send(action)
        assert answer.status_code == status, (action, answer.status_code, answer.text)
    made = send(f"picture:make:{view['id']}:0").json()["did"].split("made ", 1)[1]
    assert send(f"picture:make:{view['id']}:0").status_code == 409  # already made
    assert send("picture:word:no_such_word", targets=[made]).status_code == 422
    assert send("picture:drop", site=None).status_code == 400
    assert send("picture:drop", site="no_such_site").status_code == 404
