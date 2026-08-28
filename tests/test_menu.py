"""The ring's options, and the two limits that are easy to break by accident.

These are the checks that only exist because the option builder lives in Python.
In the browser they would be screenshots; here they are arithmetic.
"""

from __future__ import annotations

import pytest

from apothecary.hierarchy import Assembly, Site
from apothecary.menu import (
    LONGEST_LABEL,
    MOST_OPTIONS,
    Context,
    Intent,
    Option,
    Pointing,
    Ring,
    RingTooFull,
    check_ring,
    every_action,
    resolve,
    shorten,
)
from apothecary.primitives import Cube


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
