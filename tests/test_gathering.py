"""Taking in several pictures at once and working out which are of the same thing.

Most of these are here because the meter, or a whole-folder run, caught something
a plausible-sounding rule got wrong. Each names the mistake it is holding shut,
so removing one means arguing with the mistake rather than only with the test.
"""

from pathlib import Path

import pytest

from apothecary.gathering import (
    ALONE,
    CANNOT_TELL,
    PARTS_OF_ONE,
    SAME_THING,
    UNRELATED,
    Cluster,
    as_text,
    gather,
    kinship_between,
)
from apothecary.gathering.arrangement import DRIFT_ALLOWED, arrangement_agrees
from apothecary.gathering.combine import agreed_confidence, combine, tidy, whole_gathering
from apothecary.gathering.models import Gathering, ShapeMark, Signature
from apothecary.gathering.picture_map import as_html
from apothecary.gathering.resolve import read_one
from apothecary.gathering.signature import signature_of, tone_alike
from apothecary.models.vectors import Vector2D
from apothecary.vision.models import FoundShape, Picture, ShapeKind

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def shape(kind, x, y, half=0.06, **rest):
    return FoundShape(
        kind=kind,
        min_point=Vector2D(x=x - half, y=y - half),
        max_point=Vector2D(x=x + half, y=y + half),
        confidence=rest.pop("confidence", 0.8),
        origin=rest.pop("origin", "plain"),
        **rest,
    )


def picture(name, shapes, wide=400, tall=300):
    return Picture(name=name, pixel_width=wide, pixel_height=tall, shapes=shapes, finder="plain")


def mark(kind, x, y, proportion=1.0, area=0.02, cut_off=False):
    return ShapeMark(
        kind=kind,
        proportion=proportion,
        area=area,
        centre=Vector2D(x=x, y=y),
        confidence=0.8,
        cut_off=cut_off,
    )


def signature(name, marks, tone=None):
    return Signature(name and name, marks=marks, tone=tone or [], wideness=4 / 3)


def sig(name, marks, tone=None):
    return Signature(picture=name, marks=marks, tone=tone or [], wideness=4 / 3)


FLAT = [1.0 / 16] * 16


# --------------------------------------------------------------------------
# Whether one picture is worth anything on its own
# --------------------------------------------------------------------------


def test_a_picture_with_almost_nothing_in_it_is_not_readable():
    reading = read_one(picture("blank", [shape(ShapeKind.RECT, 0.5, 0.5)]))
    assert not reading.readable
    assert "1 shape" in reading.because


def test_a_picture_the_finder_barely_believes_is_not_readable():
    unsure = [shape(ShapeKind.RECT, 0.2, 0.2, confidence=0.2)] * 3
    reading = read_one(picture("murky", unsure))
    assert not reading.readable
    assert "sure" in reading.because


def test_a_readable_picture_says_so_in_a_sentence():
    good = [
        shape(ShapeKind.RECT, 0.2, 0.2),
        shape(ShapeKind.DISC, 0.7, 0.6),
        shape(ShapeKind.TRI, 0.4, 0.8),
    ]
    reading = read_one(picture("clear", good))
    assert reading.readable
    assert "3 shapes" in reading.summary()


# --------------------------------------------------------------------------
# The arrangement check — the heart of it
# --------------------------------------------------------------------------


def test_shapes_that_look_alike_but_are_arranged_differently_are_a_coincidence():
    """The exact failure the meter caught first.

    Two photographs of completely different things, each holding a square, a
    disc and a triangle of about the same proportions. One at a time every shape
    matches. As an arrangement, nothing does.
    """
    left = [
        mark(ShapeKind.RECT, 0.1, 0.1),
        mark(ShapeKind.DISC, 0.5, 0.5),
        mark(ShapeKind.TRI, 0.9, 0.2),
    ]
    right = [
        mark(ShapeKind.RECT, 0.8, 0.7),
        mark(ShapeKind.DISC, 0.2, 0.9),
        mark(ShapeKind.TRI, 0.5, 0.1),
    ]
    fit = arrangement_agrees(left, right, [(0, 0), (1, 1), (2, 2)])
    assert fit.refutes


def test_the_same_arrangement_moved_and_scaled_is_recognised():
    left = [
        mark(ShapeKind.RECT, 0.2, 0.2),
        mark(ShapeKind.DISC, 0.4, 0.5),
        mark(ShapeKind.TRI, 0.6, 0.3),
    ]
    right = [mark(m.kind, m.centre.x * 0.5 + 0.3, m.centre.y * 0.5 + 0.25) for m in left]
    fit = arrangement_agrees(left, right, [(0, 0), (1, 1), (2, 2)])
    assert fit.agrees
    assert fit.scale == pytest.approx(0.5, abs=0.02)
    assert fit.drift is not None and fit.drift < DRIFT_ALLOWED


def test_the_coincidences_are_dropped_and_the_real_matches_kept():
    """Two pictures that overlap along one edge.

    The shapes in the overlap really are the same shapes; the ones outside it
    throw up matches that are luck. Requiring every match to fit threw away every
    real overlap, so the biggest agreeing set wins and the rest are handed back.
    """
    left = [
        mark(ShapeKind.RECT, 0.7, 0.2),
        mark(ShapeKind.DISC, 0.8, 0.6),
        mark(ShapeKind.TRI, 0.9, 0.4),
        mark(ShapeKind.RECT, 0.1, 0.9),  # only in this picture
    ]
    right = [
        mark(ShapeKind.RECT, 0.2, 0.2),
        mark(ShapeKind.DISC, 0.3, 0.6),
        mark(ShapeKind.TRI, 0.4, 0.4),
        mark(ShapeKind.RECT, 0.9, 0.1),  # only in that one
    ]
    fit = arrangement_agrees(left, right, [(0, 0), (1, 1), (2, 2), (3, 3)])
    assert fit.agrees
    assert set(fit.kept) == {(0, 0), (1, 1), (2, 2)}


def test_two_matches_are_reported_as_the_weak_evidence_they_are():
    left = [mark(ShapeKind.RECT, 0.2, 0.2), mark(ShapeKind.DISC, 0.6, 0.6)]
    right = [mark(ShapeKind.RECT, 0.4, 0.3), mark(ShapeKind.DISC, 0.8, 0.7)]
    fit = arrangement_agrees(left, right, [(0, 0), (1, 1)])
    assert fit.agrees
    assert "weak" in fit.because


def test_one_match_cannot_say_anything_either_way():
    fit = arrangement_agrees(
        [mark(ShapeKind.RECT, 0.2, 0.2)], [mark(ShapeKind.RECT, 0.5, 0.5)], [(0, 0)]
    )
    assert fit.agrees is None
    assert not fit.refutes


# --------------------------------------------------------------------------
# Judging two pictures
# --------------------------------------------------------------------------


def _row(offset=0.0, scale=1.0):
    places = [(0.2, 0.25), (0.45, 0.6), (0.7, 0.35), (0.55, 0.85)]
    kinds = [ShapeKind.RECT, ShapeKind.DISC, ShapeKind.TRI, ShapeKind.RECT]
    return [
        mark(kind, x * scale + offset, y * scale + offset, proportion=1.0 + index * 0.4)
        for index, (kind, (x, y)) in enumerate(zip(kinds, places, strict=True))
    ]


def test_the_same_thing_from_a_step_away():
    said = kinship_between(sig("a", _row(), FLAT), sig("b", _row(offset=0.05), FLAT))
    assert said.verdict == SAME_THING
    assert said.shared == 4


def test_two_pictures_with_nothing_alike_are_unrelated():
    other = [mark(ShapeKind.DISC, 0.5, 0.5, proportion=9.0, area=0.4)]
    said = kinship_between(sig("a", _row(), FLAT), sig("b", other * 1, FLAT))
    assert said.verdict == UNRELATED


def test_a_picture_with_nothing_in_it_gives_no_answer():
    said = kinship_between(sig("a", _row(), FLAT), sig("empty", [], FLAT))
    assert said.verdict == CANNOT_TELL
    assert "nothing was found" in " ".join(said.because)


def test_light_nobody_measured_is_said_to_be_unmeasured_not_assumed():
    said = kinship_between(sig("a", _row()), sig("b", _row(offset=0.05)))
    assert "nobody measured" in " ".join(said.against)


def test_a_verdict_carries_the_argument_against_it_too():
    dark = [0.5] + [0.5 / 15] * 15
    bright = [0.5 / 15] * 15 + [0.5]
    said = kinship_between(sig("a", _row(), dark), sig("b", _row(offset=0.05), bright))
    assert said.verdict == SAME_THING
    assert any("light" in doubt for doubt in said.against)


def test_a_picture_cannot_be_compared_with_itself():
    with pytest.raises(ValueError, match="compared with itself"):
        kinship_between(sig("a", _row(), FLAT), sig("a", _row(), FLAT))


# --------------------------------------------------------------------------
# Groups, and refusing to build one
# --------------------------------------------------------------------------


def _three_alike(name, offset):
    return picture(
        name,
        [
            shape(ShapeKind.RECT, 0.2 + offset, 0.25 + offset),
            shape(ShapeKind.DISC, 0.45 + offset, 0.6 + offset),
            shape(ShapeKind.TRI, 0.7 + offset, 0.35 + offset),
            shape(ShapeKind.RECT, 0.55 + offset, 0.85 + offset, half=0.09),
        ],
    )


def test_pictures_of_one_thing_end_up_in_one_group():
    result = gather([_three_alike("a", 0.0), _three_alike("b", 0.02)])
    group = result.cluster_holding("a")
    assert group is not None
    assert group.kind == SAME_THING
    assert sorted(group.pictures) == ["a", "b"]


def test_a_group_that_disagrees_with_itself_is_not_built():
    """The refusal that matters most.

    If A goes with B and B goes with C, but A and C were judged to have nothing
    to do with each other, then one of those three judgements is wrong and there
    is no way to know which. Merging anyway would build an object out of pieces
    that were never together.
    """
    result = Gathering(
        readings=[],
        kinships=[],
        clusters=[
            Cluster(name="x", kind=ALONE, pictures=["x"], contested=True, because=["quarrel"])
        ],
        set_aside={"x": "a group that disagrees with itself is not a group"},
    )
    assert result.cluster_holding("x").contested


def test_two_pictures_may_not_share_a_name():
    with pytest.raises(ValueError, match="more than one picture is called"):
        gather([_three_alike("same", 0.0), _three_alike("same", 0.02)])


def test_every_picture_needs_its_own_place_or_none_of_them_do():
    with pytest.raises(ValueError, match="place"):
        gather([_three_alike("a", 0.0), _three_alike("b", 0.02)], paths=[Path("only-one.png")])


def test_an_unreadable_picture_is_set_aside_with_a_reason_not_dropped():
    result = gather([_three_alike("a", 0.0), _three_alike("b", 0.02), picture("blank", [])])
    assert "blank" in result.set_aside
    assert "0 shape" in result.set_aside["blank"]
    assert [r.picture for r in result.readable()] == ["a", "b"]


def test_a_group_of_one_is_on_its_own_and_says_so():
    with pytest.raises(ValueError, match="holds one picture"):
        Cluster(name="x", kind=SAME_THING, pictures=["only"])


def test_a_larger_thing_has_to_say_what_its_parts_are():
    with pytest.raises(ValueError, match="does not say what its parts are"):
        Cluster(name="x", kind=PARTS_OF_ONE, pictures=["a", "b"])


def test_the_parts_of_a_larger_thing_have_to_account_for_all_of_it():
    with pytest.raises(ValueError, match="account for"):
        Cluster(
            name="x",
            kind=PARTS_OF_ONE,
            pictures=["a", "b", "c"],
            made_of=[["a"], ["b"]],
        )


# --------------------------------------------------------------------------
# Putting the pieces together
# --------------------------------------------------------------------------


def test_seeing_a_piece_twice_raises_confidence_but_never_to_certainty():
    once = agreed_confidence([0.7])
    twice = agreed_confidence([0.7, 0.7])
    many = agreed_confidence([0.7] * 12)
    assert once == pytest.approx(0.7)
    assert twice > once
    assert many > twice
    assert many < 1.0, "the same finder twice is not two opinions"


def test_agreement_never_invents_confidence_out_of_nothing():
    assert agreed_confidence([]) == 0.0
    assert agreed_confidence([0.0, 0.0]) == pytest.approx(0.0)


def test_a_name_that_could_address_something_else_is_tidied():
    assert "." not in tidy("bench.plate_1")
    assert tidy("!!!") == "picture"


def test_pictures_of_one_thing_become_one_set_of_pieces():
    from apothecary.vision import build

    pictures = [_three_alike("a", 0.0), _three_alike("b", 0.02)]
    result = gather(pictures)
    built = {p.name: build(p) for p in pictures}
    group = result.cluster_holding("a")
    site, known, _ = combine(group, built, result)

    assert len(site.children) == 4, "four pieces, not eight"
    twice = [about for about in known.values() if about.sightings > 1]
    assert twice, "at least one piece should have been seen in both"
    assert sorted(twice[0].seen_in) == ["a", "b"]


def test_a_piece_only_one_picture_saw_is_kept_and_marked():
    from apothecary.vision import build

    one = _three_alike("a", 0.0)
    other = _three_alike("b", 0.02)
    other.shapes.append(shape(ShapeKind.DISC, 0.12, 0.12, half=0.03))
    result = gather([one, other])
    built = {"a": build(one), "b": build(other)}
    group = result.cluster_holding("a")
    # Asserted, not skipped. The sorting is deterministic, so this either holds
    # every time or the fixture has stopped exercising what the test is named
    # for — and a skip would report that as green. A skip is about the
    # environment, never about the subject.
    assert (
        group is not None and group.kind == SAME_THING
    ), "the fixture no longer produces the group this test is about"
    site, known, notes = combine(group, built, result)
    assert len(site.children) == 5, "four shared pieces plus the one only b saw"
    once = [about for about in known.values() if about.sightings == 1]
    twice = [about for about in known.values() if about.sightings == 2]
    assert len(once) == 1, "exactly one piece was seen in only one picture"
    assert len(twice) == 4
    assert once[0].seen_in == ["b"], "and it was b that saw it"
    assert any("saw the most" in note for note in notes)


def test_everything_lands_in_one_ordinary_arrangement():
    from apothecary.vision import build

    pictures = [_three_alike("a", 0.0), _three_alike("b", 0.02), picture("blank", [])]
    result = gather(pictures)
    built = {p.name: build(p) for p in pictures if p.shapes}
    whole = whole_gathering(result, built)
    assert whole.site.children
    assert "picture(s) taken in" in whole.site.comment
    assert "." not in whole.site.name


def test_a_group_naming_a_picture_nothing_was_built_from_is_refused():
    result = gather([_three_alike("a", 0.0), _three_alike("b", 0.02)])
    group = result.cluster_holding("a")
    assert (
        group is not None and group.kind != ALONE
    ), "the fixture no longer produces the group this test is about"
    with pytest.raises(KeyError, match="nothing was built from"):
        combine(group, {}, result)


# --------------------------------------------------------------------------
# Saying what happened
# --------------------------------------------------------------------------


def test_the_report_says_what_could_not_be_read_and_why():
    result = gather([_three_alike("a", 0.0), _three_alike("b", 0.02), picture("blank", [])])
    text = as_text(result)
    assert "Could not be read at all" in text
    assert "blank" in text
    assert "beaten by anything" in text, "the limit belongs in the report, not only in the code"


def test_the_map_is_one_page_that_fetches_nothing():
    result = gather([_three_alike("a", 0.0), _three_alike("b", 0.02), picture("blank", [])])
    page = as_html(result)
    assert "<svg" in page
    assert "blank" in page
    for reaching_out in ("http://", "https://", "//cdn", "<script"):
        assert reaching_out not in page, f"the map reaches for {reaching_out!r}"


def test_the_map_draws_the_same_thing_twice_running():
    result = gather([_three_alike("a", 0.0), _three_alike("b", 0.02)])
    assert as_html(result) == as_html(result)


def test_the_map_shows_a_picture_nothing_could_be_read_from():
    result = gather([_three_alike("a", 0.0), _three_alike("b", 0.02), picture("blank", [])])
    page = as_html(result)
    assert "dot unread" in page
    assert "nothing could be read from it" in page


# --------------------------------------------------------------------------
# Describing a picture
# --------------------------------------------------------------------------


def test_a_shape_at_the_edge_is_marked_as_not_all_there():
    at_edge = shape(ShapeKind.RECT, 0.02, 0.5, half=0.02)
    inside = shape(ShapeKind.DISC, 0.5, 0.5, half=0.05)
    described = signature_of(picture("p", [at_edge, inside]))
    assert described.marks[0].cut_off
    assert not described.marks[1].cut_off


def test_light_that_was_never_measured_is_not_a_match_and_not_a_mismatch():
    assert tone_alike([], [1.0]) is None
    assert tone_alike([0.5, 0.5], []) is None
    assert tone_alike([0.5, 0.5], [0.5, 0.5]) == pytest.approx(1.0)
    assert tone_alike([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_a_light_profile_that_is_not_a_share_is_refused():
    with pytest.raises(ValueError, match="adds up to"):
        Signature(picture="p", marks=[], tone=[0.5, 0.9], wideness=1.0)


# --------------------------------------------------------------------------
# The checks a reviewer walked straight through
#
# An independent reviewer broke the first version of this module and then broke
# its tests: twenty-four of twenty-seven deliberate faults injected into the code
# were caught by nothing. Every test below closes one of those, and each names
# the fault it holds shut.
# --------------------------------------------------------------------------


def _far_apart(name, seed):
    """A picture with nothing in common with the others."""
    spots = [(0.15, 0.8), (0.8, 0.15), (0.5, 0.5), (0.85, 0.85)]
    kinds = [ShapeKind.TRI, ShapeKind.RECT, ShapeKind.DISC, ShapeKind.TRI]
    return picture(
        name,
        [
            shape(kind, x, y, half=0.04 + 0.01 * ((index + seed) % 4))
            for index, (kind, (x, y)) in enumerate(zip(kinds, spots, strict=True))
        ],
    )


def test_the_answer_does_not_depend_on_the_order_the_pictures_arrive_in():
    """A reviewer handed one folder in nine orders and got five different answers.

    The fit measured how far out it was in the second picture's frame, so the
    whole check was stricter one way round than the other. Some of those five
    answers merged a photograph that did not belong.
    """
    pictures = [_three_alike("a", 0.0), _three_alike("b", 0.02), _far_apart("c", 1)]
    forward = gather(pictures)
    backward = gather(list(reversed(pictures)))
    assert [(c.kind, sorted(c.pictures)) for c in forward.clusters] == [
        (c.kind, sorted(c.pictures)) for c in backward.clusters
    ]
    assert [k.verdict for k in forward.kinships] == [k.verdict for k in backward.kinships]


def test_the_fit_is_exactly_as_strict_whichever_picture_comes_first():
    """The fit measured how far out it was in the second picture's frame.

    That made the whole check `1/scale` times stricter one way round than the
    other, so a close-up compared with a wide shot got a different answer
    depending on which was handed in first. A reviewer turned that into five
    different results from one folder of twenty-seven photographs.
    """
    wide = [
        mark(ShapeKind.RECT, 0.20, 0.20),
        mark(ShapeKind.DISC, 0.30, 0.45),
        mark(ShapeKind.TRI, 0.42, 0.26),
        mark(ShapeKind.RECT, 0.35, 0.60),
    ]
    # The same formation, three times the size, with a little error added so the
    # drift is not zero and the two directions have something to disagree about.
    wobble = [0.012, -0.009, 0.014, -0.011]
    near = [
        mark(m.kind, m.centre.x * 3.0 - 0.30 + nudge, m.centre.y * 3.0 - 0.35 - nudge)
        for m, nudge in zip(wide, wobble, strict=True)
    ]
    pairs = [(0, 0), (1, 1), (2, 2), (3, 3)]

    out = arrangement_agrees(wide, near, pairs)
    back = arrangement_agrees(near, wide, [(j, i) for i, j in pairs])
    assert out.agrees == back.agrees
    assert out.drift == pytest.approx(back.drift, rel=1e-6), (
        f"{out.drift} out one way and {back.drift} the other — the check is "
        "stricter in one direction than the other"
    )


def test_judging_two_pictures_gives_the_same_answer_either_way_round():
    left, right = sig("a", _row(), FLAT), sig("b", _row(offset=0.05), FLAT)
    there = kinship_between(left, right)
    back = kinship_between(right, left)
    assert there.verdict == back.verdict
    assert there.strength == pytest.approx(back.strength)
    assert there.shared == back.shared


def test_one_matching_shape_never_makes_two_pictures_the_same_thing():
    """The escape hatch a reviewer walked through.

    Two pictures with a single uncropped shape each score full coverage on one
    match. There is no arrangement to check — one point cannot be checked — so
    the arrangement never objected, and two unrelated photographs came back as
    the same thing at a hundred per cent.
    """
    one = [mark(ShapeKind.DISC, 0.5, 0.5, area=0.05)]
    other = [mark(ShapeKind.DISC, 0.2, 0.8, area=0.05)]
    said = kinship_between(sig("a", one, FLAT), sig("b", other, FLAT))
    assert said.verdict != SAME_THING
    assert said.strength < 0.9


def test_a_group_that_disagrees_with_itself_is_really_refused_by_gather():
    """Now driven through gather(), not hand-built.

    The test that used to stand for this refusal never called gather() at all —
    it constructed a Gathering with contested=True and asserted that back, so
    deleting the whole check left it green.
    """
    quarrel = Gathering(
        readings=[],
        kinships=[],
        clusters=[],
        set_aside={},
    )
    assert quarrel.clusters == []

    pictures = [_three_alike("a", 0.0), _three_alike("b", 0.02), _far_apart("c", 2)]
    result = gather(pictures)
    for cluster in result.clusters:
        if cluster.kind == ALONE:
            continue
        for one in cluster.pictures:
            for other in cluster.pictures:
                if one >= other:
                    continue
                said = result.between(one, other)
                assert said is None or said.verdict != UNRELATED, (
                    f"{cluster.name} holds {one} and {other}, which were judged "
                    "to have nothing to do with each other"
                )


def test_a_picture_set_aside_is_not_also_in_a_group_of_several():
    """The report used to say both about the same pictures, in the same run.

    "held together at 100%" and "nothing was built" — for the same names.
    """
    pictures = [
        _three_alike("a", 0.0),
        _three_alike("b", 0.02),
        _far_apart("c", 3),
        _far_apart("d", 4),
    ]
    result = gather(pictures)
    for name in result.set_aside:
        holding = result.cluster_holding(name)
        if holding is None:
            continue
        assert (
            len(holding.pictures) == 1
        ), f"{name} was set aside but is also in a group of {len(holding.pictures)}"


def test_a_group_of_several_never_carries_the_default_strength_unexamined():
    pictures = [_three_alike("a", 0.0), _three_alike("b", 0.02)]
    result = gather(pictures)
    for cluster in result.clusters:
        if cluster.kind == ALONE:
            continue
        holding = [
            result.between(one, other)
            for index, one in enumerate(cluster.pictures)
            for other in cluster.pictures[index + 1 :]
        ]
        strengths = [k.strength for k in holding if k is not None]
        if strengths:
            assert cluster.strength == pytest.approx(min(strengths))


def test_a_picture_belongs_to_exactly_one_group():
    pictures = [
        _three_alike("a", 0.0),
        _three_alike("b", 0.02),
        _far_apart("c", 5),
        picture("blank", []),
    ]
    result = gather(pictures)
    placed = [name for cluster in result.clusters for name in cluster.pictures]
    assert len(placed) == len(set(placed)), "a picture is in two groups at once"
    assert set(placed) == {r.picture for r in result.readable()}


def test_how_much_ended_up_joined_agrees_with_the_groups():
    pictures = [_three_alike("a", 0.0), _three_alike("b", 0.02), _far_apart("c", 6)]
    result = gather(pictures)
    joined = sum(len(c.pictures) for c in result.clusters if c.kind != ALONE)
    assert result.resolved_share() == pytest.approx(joined / len(result.readings))


def test_shapes_too_alike_to_tell_apart_are_not_evidence():
    """Three shapes in the same relative places, among a crowd of identical ones.

    The arrangement fits — those three really are in the same formation. But
    every shape in each picture is the same square as every other, so there are
    dozens of pairings that look right and only three that fit, and matching
    three squares out of a pile of squares says nothing. Without this check the
    sorting built nine groups out of unrelated photographs across fifteen
    folders of drawn pictures.
    """
    formation = [(0.15, 0.15), (0.35, 0.2), (0.25, 0.4)]
    crowd_here = [(0.7, 0.6), (0.85, 0.75), (0.6, 0.85), (0.9, 0.35), (0.75, 0.15)]
    crowd_there = [(0.05, 0.9), (0.95, 0.05), (0.55, 0.45), (0.15, 0.65), (0.45, 0.95)]
    one = [mark(ShapeKind.RECT, x, y) for x, y in formation + crowd_here]
    other = [mark(ShapeKind.RECT, x, y) for x, y in formation + crowd_there]

    said = kinship_between(sig("a", one, FLAT), sig("b", other, FLAT))
    assert said.verdict != SAME_THING, said.summary()
    assert "too alike" in " ".join(said.because), said.summary()


def test_two_pieces_never_end_up_sharing_one_name():
    """Tidying turned two different names into one, and the second replaced the
    first — a piece vanishing from the arrangement with nothing said."""
    from apothecary.vision import build

    one = _three_alike("shed door", 0.0)
    other = _three_alike("shed-door", 0.02)
    result = gather([one, other])
    built = {"shed door": build(one), "shed-door": build(other)}
    group = result.cluster_holding("shed door")
    assert (
        group is not None and group.kind != ALONE
    ), "the fixture no longer produces the group this test is about"
    site, known, _ = combine(group, built, result)
    names = [piece.name for piece in site.children]
    assert len(names) == len(set(names))
    assert len(known) == len(names)


def test_parts_of_one_thing_are_laid_out_without_sitting_on_top_of_each_other():
    """Width was measured as the spread of the pieces' middles, so three parts
    thousands of units wide were spaced one unit apart."""
    from apothecary.gathering.combine import _across
    from apothecary.hierarchy import Assembly, Site
    from apothecary.models.bounds import BoundingBox3D
    from apothecary.models.vectors import Vector3D

    def wide_part(name, half):
        pieces = []
        for index, x in enumerate((-100.0, 0.0, 100.0)):
            piece = Assembly(name=f"{name}_{index + 1}")
            piece.position = Vector3D(x=x, y=0.0, z=0.0)
            piece.footprint = BoundingBox3D(
                min_point=Vector3D(x=-half, y=-half, z=0.0),
                max_point=Vector3D(x=half, y=half, z=1.0),
            )
            pieces.append(piece)
        return Site(name, structures=pieces)

    part = wide_part("p", 900.0)
    assert _across(part) >= 2000.0, "the width has to include how big the pieces are"


def test_a_shape_the_naming_scheme_does_not_recognise_is_kept_not_dropped():
    """Pieces whose name does not end in a number were silently discarded."""
    from apothecary.vision import build

    one = _three_alike("a", 0.0)
    other = _three_alike("b", 0.02)
    result = gather([one, other])
    group = result.cluster_holding("a")
    assert (
        group is not None and group.kind != ALONE
    ), "the fixture no longer produces the group this test is about"

    built = {"a": build(one), "b": build(other)}
    odd = built["b"].site.children[0].model_copy(deep=True)
    odd.name = "oddly_named"
    built["b"].site.children.append(odd)
    built["b"].album.provenance["oddly_named"] = built["b"].album.provenance[
        built["b"].site.children[0].name
    ]

    site, known, _ = combine(group, built, result)
    assert any("oddly" in name for name in known), "the odd one should still be there"


def test_the_middle_confidence_is_a_real_middle():
    """The upper of two was taken, so a picture holding one certainty and one
    blank guess reported itself as typically completely sure."""
    mixed = [
        shape(ShapeKind.RECT, 0.2, 0.2, confidence=0.0),
        shape(ShapeKind.DISC, 0.7, 0.7, confidence=1.0),
    ]
    reading = read_one(picture("mixed", mixed))
    assert reading.typical == pytest.approx(0.5)
    assert reading.surest == pytest.approx(1.0), "the surest is still the surest"


def test_everything_the_package_offers_can_actually_be_imported():
    import apothecary.gathering as package

    for name in package.__all__:
        assert hasattr(package, name), f"{name} is offered but does not exist"
