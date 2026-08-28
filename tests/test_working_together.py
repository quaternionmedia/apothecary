"""What a person tells the sorting, and the promises made about their word.

Four promises, and each has tests here because each is the sort of thing that
quietly stops being true:

1. A person's word wins outright.
2. It carries — one answer settles everything that follows from it.
3. It scores the machine, because an answer is a case where the truth is known.
4. Two people who disagree are refused, never averaged.
"""

import pytest

from apothecary.gathering import CANNOT_TELL, PARTS_OF_ONE, SAME_THING, UNRELATED, gather
from apothecary.gathering.judgement import (
    BY_A_PERSON,
    NOT_WORTH_USING,
    WORTH_USING,
    CannotRead,
    Judgement,
    PeopleDisagree,
    read_answers,
    settle,
    unknown_names,
)
from apothecary.gathering.models import ALONE, Gathering
from apothecary.gathering.questions import as_sheet, worth_asking
from apothecary.models.vectors import Vector2D
from apothecary.vision.models import FoundShape, Picture, ShapeKind


def shape(kind, x, y, half=0.05, confidence=0.8):
    return FoundShape(
        kind=kind,
        min_point=Vector2D(x=x - half, y=y - half),
        max_point=Vector2D(x=x + half, y=y + half),
        confidence=confidence,
        origin="plain",
    )


def picture(name, offset=0.0):
    spots = [(0.2, 0.25), (0.45, 0.55), (0.7, 0.3)]
    kinds = [ShapeKind.RECT, ShapeKind.DISC, ShapeKind.TRI]
    return Picture(
        name=name,
        pixel_width=400,
        pixel_height=300,
        finder="plain",
        shapes=[
            shape(kind, x + offset, y + offset) for kind, (x, y) in zip(kinds, spots, strict=True)
        ],
    )


SHARED = [(ShapeKind.RECT, 0.2, 0.2), (ShapeKind.DISC, 0.4, 0.35)]


def half_alike(name, rest):
    """Two shapes in common and the rest different — reliably undecided.

    Built by hand rather than found by trying pictures until one worked, because
    three tests here used to skip themselves when there was nothing undecided,
    and a test that skips itself is how the whole question-ranking mechanism came
    to be deletable with the suite still green.
    """
    return Picture(
        name=name,
        pixel_width=400,
        pixel_height=300,
        finder="plain",
        shapes=[shape(kind, x, y, half=0.04) for kind, x, y in SHARED + rest],
    )


def a_pair_it_cannot_decide():
    return [
        half_alike(
            "left",
            [(ShapeKind.TRI, 0.75, 0.2), (ShapeKind.TRI, 0.85, 0.6), (ShapeKind.RECT, 0.6, 0.85)],
        ),
        half_alike(
            "right",
            [(ShapeKind.DISC, 0.8, 0.25), (ShapeKind.RECT, 0.9, 0.7), (ShapeKind.TRI, 0.55, 0.9)],
        ),
    ]


def nothing_alike(name):
    """A picture the machine confidently calls unrelated to everything else."""
    return Picture(
        name=name,
        pixel_width=400,
        pixel_height=300,
        finder="plain",
        shapes=[
            FoundShape(
                kind=ShapeKind.LINE,
                min_point=Vector2D(x=0.05, y=0.05),
                max_point=Vector2D(x=0.95, y=0.08),
                confidence=0.8,
                origin="plain",
            ),
            FoundShape(
                kind=ShapeKind.POLY,
                min_point=Vector2D(x=0.1, y=0.6),
                max_point=Vector2D(x=0.9, y=0.95),
                confidence=0.8,
                origin="plain",
            ),
            FoundShape(
                kind=ShapeKind.LINE,
                min_point=Vector2D(x=0.4, y=0.2),
                max_point=Vector2D(x=0.44, y=0.5),
                confidence=0.8,
                origin="plain",
            ),
        ],
    )


def elsewhere(name):
    return Picture(
        name=name,
        pixel_width=400,
        pixel_height=300,
        finder="plain",
        shapes=[
            shape(ShapeKind.TRI, 0.15, 0.8, half=0.03),
            shape(ShapeKind.RECT, 0.85, 0.15, half=0.09),
            shape(ShapeKind.DISC, 0.6, 0.75, half=0.02),
        ],
    )


# --------------------------------------------------------------------------
# Reading what a person wrote
# --------------------------------------------------------------------------


def test_the_five_sentences_are_understood():
    said = read_answers("""
        # my notes
        bench_left and bench_right are the same thing
        wall_a and wall_b are parts of one thing      # they meet at the door
        shed and kitchen are not related
        my_thumb is not worth using
        very_dark is worth using anyway
        """)
    assert [one.verdict for one in said] == [
        SAME_THING,
        PARTS_OF_ONE,
        UNRELATED,
        NOT_WORTH_USING,
        WORTH_USING,
    ]
    assert said[1].note == "they meet at the door"


def test_notes_and_blank_lines_are_ignored():
    assert read_answers("\n\n# nothing but a note\n\n") == []


def test_a_sentence_it_does_not_understand_says_what_would_have_worked():
    with pytest.raises(CannotRead) as refused:
        read_answers("bench_left ~~ bench_right")
    said = str(refused.value)
    assert "line 1" in said
    assert "are the same thing" in said, "a complaint has to say what to type instead"


def test_a_verdict_about_the_wrong_number_of_pictures_is_refused():
    with pytest.raises(CannotRead, match="about two pictures"):
        read_answers("a and b are not worth using")
    with pytest.raises(CannotRead, match="about one picture"):
        read_answers("a is the same thing")


def test_a_picture_compared_with_itself_is_refused():
    with pytest.raises(ValueError, match="compared with itself"):
        Judgement(left="a", right="a", verdict=SAME_THING)


def test_names_nobody_recognises_are_reported_rather_than_ignored():
    said = read_answers("bench and shedd are the same thing")
    assert unknown_names(said, ["bench", "shed"]) == ["shedd"]


# --------------------------------------------------------------------------
# Two people who disagree
# --------------------------------------------------------------------------


def test_two_answers_that_contradict_each_other_are_refused_not_averaged():
    said = read_answers("a and b are the same thing\n" "b and a are not related\n")
    with pytest.raises(PeopleDisagree) as refused:
        settle(said)
    complaint = str(refused.value)
    assert "line 1" in complaint and "line 2" in complaint
    assert "Nothing was merged" in complaint


def test_the_same_answer_twice_is_not_a_disagreement():
    said = read_answers("a and b are the same thing\nb and a are the same thing\n")
    assert len(settle(said)) == 1


# --------------------------------------------------------------------------
# A person's word wins
# --------------------------------------------------------------------------


def test_a_person_can_join_two_pictures_the_machine_called_unrelated():
    pictures = [picture("bench"), elsewhere("shed")]
    machine = gather(pictures)
    assert machine.between("bench", "shed").verdict != SAME_THING

    told = gather(pictures, answers=read_answers("bench and shed are the same thing"))
    said = told.between("bench", "shed")
    assert said.verdict == SAME_THING
    assert said.said_by == BY_A_PERSON
    assert said.strength == 1.0
    holding = told.cluster_holding("bench")
    assert holding.kind == SAME_THING and sorted(holding.pictures) == ["bench", "shed"]


def test_a_machine_guess_cannot_destroy_a_group_you_built():
    """The way "a person's word wins" failed, on one answer and no odd input.

    The machine had already decided a and b are the same thing, and was sure b
    and far are unrelated. A person says a and far are the same thing. The group
    {a, b, far} then contains a pair the machine calls unrelated — and that guess
    was taken as grounds to throw the whole group away, while the report printed
    "your word was taken as it stands" in the same breath.

    A machine's disagreement is only a quarrel in a group the machine built.
    """
    pictures = [picture("a"), picture("b", 0.02), nothing_alike("far")]
    machine = gather(pictures)
    assert machine.between("a", "b").verdict == SAME_THING
    assert machine.between("b", "far").verdict == UNRELATED

    told = gather(pictures, answers=read_answers("a and far are the same thing"))
    holding = told.cluster_holding("far")
    assert holding is not None and holding.kind == SAME_THING
    assert sorted(holding.pictures) == ["a", "b", "far"]
    assert told.set_aside == {}
    assert told.overruled, "and it says out loud that it stood down"


def test_your_own_word_can_still_break_a_group():
    """The other half. A person's disagreement is a real quarrel.

    Otherwise "your word wins" would only mean "your word wins when it agrees
    with itself", and a group could be built that contradicts something the same
    person said two lines earlier.
    """
    pictures = [picture("a"), picture("b", 0.02), nothing_alike("far")]
    told = gather(
        pictures,
        answers=read_answers("a and far are the same thing\nb and far are not related"),
    )
    for cluster in told.clusters:
        if cluster.kind != ALONE:
            assert not {"b", "far"} <= set(cluster.pictures)
    assert told.set_aside, "and it says why, rather than quietly dropping one"


def test_a_person_can_separate_two_pictures_the_machine_joined():
    pictures = [picture("a"), picture("b", 0.02)]
    assert gather(pictures).between("a", "b").verdict == SAME_THING

    told = gather(pictures, answers=read_answers("a and b are not related"))
    assert told.between("a", "b").verdict == UNRELATED
    assert told.cluster_holding("a").kind == ALONE


def test_a_person_can_rescue_a_picture_nothing_could_be_read_from():
    blank = Picture(name="dim", pixel_width=400, pixel_height=300, finder="plain")
    machine = gather([picture("a"), picture("b", 0.02), blank])
    assert "dim" in machine.set_aside

    told = gather(
        [picture("a"), picture("b", 0.02), blank],
        answers=read_answers("dim is worth using anyway"),
    )
    assert "dim" not in told.set_aside
    rescued = next(r for r in told.readings if r.picture == "dim")
    assert rescued.readable and rescued.from_a_person


def test_a_person_can_throw_out_a_picture_the_machine_liked():
    told = gather(
        [picture("a"), picture("b", 0.02)],
        answers=read_answers("b is not worth using  # that is my thumb"),
    )
    assert "b" in told.set_aside
    assert "thumb" in told.set_aside["b"]
    assert [r.picture for r in told.readable()] == ["a"]


def test_what_the_machine_thought_is_kept_rather_than_thrown_away():
    told = gather(
        [picture("a"), picture("b", 0.02)],
        answers=read_answers("a and b are not related"),
    )
    said = told.between("a", "b")
    assert said.machine_said == SAME_THING
    assert "the machine had said" in said.summary()


# --------------------------------------------------------------------------
# A person's word carries
# --------------------------------------------------------------------------


def test_one_answer_settles_everything_that_follows_from_it():
    """Saying two are of one thing joins whatever is already joined to either.

    A person should never be asked for something that follows from what they
    already said.
    """
    pictures = [picture("a"), picture("b", 0.02), elsewhere("far")]
    machine = gather(pictures)
    assert machine.cluster_holding("far").kind == ALONE

    told = gather(pictures, answers=read_answers("a and far are the same thing"))
    holding = told.cluster_holding("far")
    assert sorted(holding.pictures) == [
        "a",
        "b",
        "far",
    ], "one answer about a and far should have carried b along with it"


def test_a_person_joining_two_pictures_the_machine_split_still_refuses_a_quarrel():
    """Their word wins, and it cannot make a group that argues with itself.

    If a person joins A to B while the machine is sure B and C are unrelated, and
    C is already with A, the group disagrees with itself and is not built. The
    person is told, rather than the machine picking which of them to believe.
    """
    pictures = [picture("a"), picture("b", 0.02), elsewhere("far")]
    told = gather(
        pictures,
        answers=read_answers("a and far are the same thing\nb and far are not related"),
    )
    for cluster in told.clusters:
        if cluster.kind == ALONE:
            continue
        for one in cluster.pictures:
            for other in cluster.pictures:
                if one < other:
                    said = told.between(one, other)
                    assert said is None or said.verdict != UNRELATED


# --------------------------------------------------------------------------
# It scores the machine
# --------------------------------------------------------------------------


def test_every_answer_is_also_a_mark_out_of_one_for_the_machine():
    pictures = [picture("a"), picture("b", 0.02), elsewhere("far")]
    told = gather(
        pictures,
        answers=read_answers(
            "a and b are the same thing\n"  # the machine agrees
            "a and far are the same thing\n"  # the machine said otherwise
        ),
    )
    card = told.scorecard()
    assert card["you answered"] == 2
    assert card["agreed"] == 1
    assert card["overruled"] + card["silent"] == 1


def test_the_scorecard_is_empty_when_nobody_has_said_anything():
    card = gather([picture("a"), picture("b", 0.02)]).scorecard()
    assert card == {
        "you answered": 0,
        "about a pair": 0,
        "about one picture": 0,
        "agreed": 0,
        "overruled": 0,
        "silent": 0,
    }


# --------------------------------------------------------------------------
# Asking well
# --------------------------------------------------------------------------


def test_it_only_asks_about_things_it_could_not_decide():
    result = gather([picture("a"), picture("b", 0.02), elsewhere("far")])
    asked = {(q.left, q.right) for q in worth_asking(result)}
    for one, other in asked:
        assert result.between(one, other).verdict == CANNOT_TELL


def test_it_does_not_ask_about_something_a_person_already_answered():
    pictures = a_pair_it_cannot_decide()
    assert worth_asking(gather(pictures)), "there should be a question to begin with"
    told = gather(pictures, answers=read_answers("left and right are not related"))
    assert worth_asking(told) == []


def test_there_is_always_something_to_ask_about_this_pair():
    """The fixture the ranking tests stand on. If this goes, they are lying."""
    result = gather(a_pair_it_cannot_decide())
    assert result.between("left", "right").verdict == CANNOT_TELL
    assert len(worth_asking(result)) == 1


def test_a_question_says_what_answering_it_is_worth():
    asked = worth_asking(gather(a_pair_it_cannot_decide()))
    assert asked[0].settles == 1
    assert "settles" in asked[0].worth()
    assert asked[0].sentence().startswith("Are ")


def _made_up(clusters, kinships, readings=None):
    """A gathering built by hand, so the ranking can be checked exactly.

    worth_asking answers a question about a Gathering, so it is asked one
    directly rather than through whatever a finder happens to produce.
    """
    from apothecary.gathering.models import Cluster, Kinship, Reading

    names = {name for cluster in clusters for name in cluster["pictures"]}
    return Gathering(
        readings=readings
        or [
            Reading(picture=name, shapes_found=3, readable=True, because="made up")
            for name in sorted(names)
        ],
        kinships=[Kinship(**one) for one in kinships],
        clusters=[Cluster(**one) for one in clusters],
    )


def test_a_question_joining_two_groups_is_asked_before_one_joining_two_singles():
    """The whole reason the machine does the arithmetic.

    One answer that settles a dozen pairs is worth a person's minute. One that
    settles a single pair is worth much less, and asking it first is how a
    helpful tool becomes one nobody opens twice.
    """
    # Named so that every ordering except the right one puts the cheap question
    # first: alphabetically "aa" beats "za", and by the other name too. Only
    # ranking by what an answer is worth gets this the right way round.
    made = _made_up(
        clusters=[
            {"name": "big", "kind": SAME_THING, "pictures": ["za1", "za2", "za3"]},
            {"name": "two", "kind": SAME_THING, "pictures": ["zb1", "zb2"]},
            {"name": "aa", "kind": ALONE, "pictures": ["aa"]},
            {"name": "ab", "kind": ALONE, "pictures": ["ab"]},
        ],
        kinships=[
            {"left": "za1", "right": "zb1", "verdict": CANNOT_TELL, "strength": 0.2, "shared": 2},
            {"left": "aa", "right": "ab", "verdict": CANNOT_TELL, "strength": 0.2, "shared": 2},
        ],
    )
    asked = worth_asking(made, most=20)
    assert [(q.left, q.right, q.settles) for q in asked] == [
        ("za1", "zb1", 6),
        ("aa", "ab", 1),
    ], "six beats one, and it has to be asked first whatever the names are"


def test_the_worth_of_a_question_counts_the_group_it_would_actually_merge():
    """Not the composite it happens to be drawn inside.

    A larger thing is several separate groups placed side by side. Answering
    "these two are the same thing" merges the *groups*, not the composite —
    reading the composite size reported a question worth four as worth one and
    sorted it last, and one worth two as worth four and sorted it first.
    """
    made = _made_up(
        clusters=[
            {
                "name": "larger",
                "kind": PARTS_OF_ONE,
                "pictures": ["p1", "p2", "q1", "q2"],
                "made_of": [["p1", "p2"], ["q1", "q2"]],
            },
            {"name": "z", "kind": ALONE, "pictures": ["z"]},
        ],
        kinships=[
            {"left": "p1", "right": "q1", "verdict": CANNOT_TELL, "strength": 0.2, "shared": 2},
            {"left": "p1", "right": "z", "verdict": CANNOT_TELL, "strength": 0.2, "shared": 2},
        ],
    )
    worth = {(q.left, q.right): q.settles for q in worth_asking(made, most=20)}
    assert worth[("p1", "q1")] == 4
    assert worth[("p1", "z")] == 2


def test_it_never_asks_something_that_follows_from_what_is_already_settled():
    """Two pictures already known to be the same thing are not a question."""
    made = _made_up(
        clusters=[{"name": "one", "kind": SAME_THING, "pictures": ["p1", "p2", "p3"]}],
        kinships=[
            {"left": "p1", "right": "p3", "verdict": CANNOT_TELL, "strength": 0.2, "shared": 2}
        ],
    )
    assert worth_asking(made) == []


def test_it_does_not_ask_about_a_pair_with_nothing_to_look_at():
    made = _made_up(
        clusters=[
            {"name": "z", "kind": ALONE, "pictures": ["z"]},
            {"name": "y", "kind": ALONE, "pictures": ["y"]},
        ],
        kinships=[
            {"left": "y", "right": "z", "verdict": CANNOT_TELL, "strength": 0.1, "shared": 0}
        ],
    )
    assert worth_asking(made) == [], "an easy no is not a hard question"


def test_asking_for_no_questions_at_all_is_refused():
    made = _made_up(
        clusters=[{"name": "z", "kind": ALONE, "pictures": ["z"]}],
        kinships=[],
    )
    with pytest.raises(ValueError, match="fewest"):
        worth_asking(made, most=0)


def test_how_many_there_are_is_countable_so_holding_some_back_can_be_admitted():
    from apothecary.gathering.questions import how_many_worth_asking

    made = _made_up(
        clusters=[
            {"name": name, "kind": ALONE, "pictures": [name]} for name in ("a", "b", "c", "d")
        ],
        kinships=[
            {"left": one, "right": other, "verdict": CANNOT_TELL, "strength": 0.2, "shared": 2}
            for one, other in [("a", "b"), ("c", "d"), ("a", "c"), ("b", "d")]
        ],
    )
    assert how_many_worth_asking(made) == 4
    assert len(worth_asking(made, most=2)) == 2


def test_the_sheet_is_something_a_person_can_answer_in_place():
    result = gather([picture("a"), picture("b", 0.02), elsewhere("far")])
    sheet = as_sheet(result, worth_asking(result))
    assert "are the same thing" in sheet
    assert "Delete the hash" in sheet
    for line in sheet.splitlines():
        assert not line.strip() or line.lstrip().startswith(
            "#"
        ), "every line has to start out commented, or the sheet answers itself"


def test_the_sheet_never_rewrites_what_somebody_already_said():
    """A tool that tidied a person's own words would be the last time they
    trusted it with them."""
    mine = "# my own notes, exactly as I typed them\na and b are the same thing\n"
    result = gather([picture("a"), picture("b", 0.02), elsewhere("far")])
    sheet = as_sheet(result, worth_asking(result), already=mine)
    assert sheet.startswith(mine.rstrip())


def test_the_sheet_offers_to_rescue_a_picture_nothing_could_be_read_from():
    blank = Picture(name="dim", pixel_width=400, pixel_height=300, finder="plain")
    result = gather([picture("a"), picture("b", 0.02), blank])
    sheet = as_sheet(result, worth_asking(result))
    assert "dim is worth using anyway" in sheet


# --------------------------------------------------------------------------
# What the person did is visible afterwards
# --------------------------------------------------------------------------


def test_the_report_says_which_ones_you_decided():
    from apothecary.gathering import as_text

    told = gather(
        [picture("a"), picture("b", 0.02), elsewhere("far")],
        answers=read_answers("a and far are the same thing"),
    )
    text = as_text(told)
    assert "What you told it" in text
    assert "you answered" in text
    assert "you said so" in text


def test_the_map_draws_a_join_you_made_differently_from_one_it_guessed():
    from apothecary.gathering.picture_map import as_html

    told = gather(
        [picture("a"), picture("b", 0.02), elsewhere("far")],
        answers=read_answers("a and far are the same thing"),
    )
    page = as_html(told)
    assert 'class="edge same told"' in page or 'class="edge parts told"' in page
    assert "you said so, not the machine" in page


def test_the_report_asks_for_what_would_help_most():
    from apothecary.gathering import as_text

    text = as_text(gather(a_pair_it_cannot_decide()))
    assert "What would help most" in text
    assert "worth your minute" in text


# --------------------------------------------------------------------------
# It is arithmetic, and that is on purpose
#
# The half of this the machine does is counting, comparing and sorting. There is
# no model in it, nothing is asked of anything over a network, and the same
# input gives the same output every time. That is a deliberate choice and not an
# accident of what was to hand, so it is checked rather than claimed.
# --------------------------------------------------------------------------

WOULD_NOT_BE_ARITHMETIC = (
    "openai",
    "anthropic",
    "transformers",
    "torch",
    "onnx",
    "tensorflow",
    "llama",
    "langchain",
    "requests",
    "httpx",
    "urllib",
    "socket",
)


def _the_whole_path():
    """Every file between a photograph and a group of photographs.

    Both packages, not just the sorting. The claim made is about the whole path,
    and a reviewer pointed out the guard only covered half of it — which is the
    sort of gap that is invisible until somebody adds an import to the other
    half.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "apothecary"
    return sorted(
        source
        for folder in ("gathering", "vision", "vocabulary")
        for source in (root / folder).glob("*.py")
    )


def test_the_cooperation_layer_is_arithmetic_and_nothing_else():
    """No model, no service, nothing over a network. Read from the source.

    A tool that asked something else what two photographs were of would be
    unrepeatable, unexplainable, and would put the person's photographs somewhere
    they did not choose. Every one of those is disqualifying on its own.
    """
    import ast

    for source in _the_whole_path():
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        reached_for = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                reached_for.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                reached_for.add(node.module.split(".")[0])
        for banned in WOULD_NOT_BE_ARITHMETIC:
            assert banned not in reached_for, (
                f"{source.name} reaches for {banned!r}. The machine's half of this "
                "is counting, comparing and sorting; anything that answers "
                "differently on two Tuesdays does not belong in it."
            )


def test_nothing_here_is_left_to_chance():
    """Not even a seeded shuffle. There is no randomness in the deciding path."""
    import ast

    for source in _the_whole_path():
        if source.name == "bench.py":
            continue  # the meters draw pictures; they decide nothing
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(a.name.split(".")[0] != "random" for a in node.names), source.name
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] != "random", source.name


def test_the_same_answers_give_the_same_result_twice_running():
    said = read_answers("a and far are the same thing\nb is not worth using\n")
    pictures = [picture("a"), picture("b", 0.02), elsewhere("far")]
    once = gather(pictures, answers=said)
    again = gather(pictures, answers=said)
    assert once.model_dump_json() == again.model_dump_json()


def test_the_order_the_answers_were_written_in_does_not_matter():
    pictures = [picture("a"), picture("b", 0.02), elsewhere("far")]
    forward = read_answers("a and far are the same thing\nb is not worth using\n")
    backward = read_answers("b is not worth using\na and far are the same thing\n")
    assert (
        gather(pictures, answers=forward).model_dump_json()
        == gather(pictures, answers=backward).model_dump_json()
    )


def test_the_questions_come_out_in_the_same_order_every_time():
    result = gather([picture("a"), picture("b", 0.02), elsewhere("far")])

    def shape_of(questions):
        return [(q.left, q.right, q.settles, q.shared) for q in questions]

    once = shape_of(worth_asking(result, most=20))
    again = shape_of(worth_asking(result, most=20))
    assert once == again

    # And the order is fully determined by the rule it says it uses, so no two
    # questions are left to whichever happened to come out of a set first.
    by_the_rule = sorted(once, key=lambda q: (-(q[3] > 0), -q[2], -q[3], q[0], q[1]))
    assert once == by_the_rule
    assert len({(left, right) for left, right, _, _ in once}) == len(once)


# --------------------------------------------------------------------------
# The command itself
#
# None of this was covered at all, which is how a mutation that made the command
# ignore --answers entirely survived the whole suite, and how --ask came to
# overwrite a person's notes without anybody noticing.
# --------------------------------------------------------------------------


@pytest.fixture
def a_folder(tmp_path):
    """Three drawn pictures: two of one thing and one of something else."""
    from apothecary.gathering import bench

    where = tmp_path / "pics"
    scene = bench._scene(__import__("random").Random(4), spread=bench.WINDOW_WIDE, count=4)
    window = (0.0, 0.0, bench.WINDOW_WIDE, bench.WINDOW_TALL)
    bench._photograph(scene, window, _made(where, "bench_left"), light=0)
    bench._photograph(scene, window, _made(where, "bench_right"), light=10)
    other = bench._scene(__import__("random").Random(99), spread=bench.WINDOW_WIDE, count=4)
    bench._photograph(other, window, _made(where, "shed"), light=6)
    bench._photograph([], window, _made(where, "blank_wall"), light=0)
    return where


def _made(where, name):
    where.mkdir(parents=True, exist_ok=True)
    return where / f"{name}.png"


def _run(*args):
    from click.testing import CliRunner

    from apothecary.cli.photo import photo

    return CliRunner().invoke(photo, ["gather", *[str(a) for a in args]])


def test_the_command_uses_what_you_told_it(a_folder, tmp_path):
    plain = _run(a_folder)
    assert plain.exit_code == 0
    assert "bench_left" in plain.output

    answers = tmp_path / "mine.txt"
    answers.write_text("bench_left and shed are the same thing\n", encoding="utf-8")
    told = _run(a_folder, "--answers", answers)
    assert told.exit_code == 0
    assert "What you told it" in told.output
    assert "you said so" in told.output


def test_the_command_refuses_a_name_that_is_not_there(a_folder, tmp_path):
    answers = tmp_path / "mine.txt"
    answers.write_text("bench_left and shedd are the same thing\n", encoding="utf-8")
    said = _run(a_folder, "--answers", answers)
    assert said.exit_code != 0
    assert "shedd" in said.output


def test_the_command_refuses_two_answers_that_disagree_without_a_traceback(a_folder, tmp_path):
    """The flagship refusal came out as thirty lines of internal detail."""
    answers = tmp_path / "mine.txt"
    answers.write_text(
        "bench_left and shed are the same thing\nshed and bench_left are not related\n",
        encoding="utf-8",
    )
    said = _run(a_folder, "--answers", answers)
    assert said.exit_code != 0
    assert "Traceback" not in said.output
    assert "picking one would mean a machine deciding" in said.output


def test_the_command_says_when_your_answer_could_not_be_used(a_folder, tmp_path):
    answers = tmp_path / "mine.txt"
    answers.write_text("bench_left and blank_wall are the same thing\n", encoding="utf-8")
    said = _run(a_folder, "--answers", answers)
    assert said.exit_code == 0
    assert "could not be used" in said.output
    assert "worth using anyway" in said.output, "and it says what to type instead"


def test_asking_never_destroys_what_you_wrote(a_folder, tmp_path):
    """It replaced the file outright whenever --answers was not the same path."""
    mine = tmp_path / "mine.txt"
    mine.write_text(
        "# my careful notes\nbench_left and bench_right are the same thing\n", encoding="utf-8"
    )
    said = _run(a_folder, "--ask", mine)
    assert said.exit_code == 0
    kept = mine.read_text(encoding="utf-8")
    assert "my careful notes" in kept
    assert "bench_left and bench_right are the same thing" in kept


def test_asking_twice_does_not_pile_the_questions_up(a_folder, tmp_path):
    """Answering two copies of one question differently was reported as two
    people disagreeing."""
    sheet = tmp_path / "q.txt"
    _run(a_folder, "--ask", sheet)
    once = sheet.read_text(encoding="utf-8")
    _run(a_folder, "--answers", sheet, "--ask", sheet)
    twice = sheet.read_text(encoding="utf-8")
    assert twice.count("What the machine could not work out") == 1
    assert len(twice.splitlines()) <= len(once.splitlines()) + 2


def test_the_sheet_it_writes_can_be_answered_and_handed_back(a_folder, tmp_path):
    sheet = tmp_path / "q.txt"
    _run(a_folder, "--ask", sheet)
    written = sheet.read_text(encoding="utf-8")

    here = {p.stem for p in a_folder.glob("*.png")}
    answered = []
    took = False
    for line in written.splitlines():
        naked = line[2:] if line.startswith("# ") else ""
        # Only a line about pictures that are actually here. The instructions at
        # the top are written with the gaps marked so they cannot be mistaken for
        # answers, and this is the check that they cannot.
        if not took and " are not related" in naked and naked.split(" ")[0] in here:
            answered.append(naked)
            took = True
        else:
            answered.append(line)
    sheet.write_text("\n".join(answered), encoding="utf-8")

    back = _run(a_folder, "--answers", sheet)
    assert back.exit_code == 0, back.output
    if took:
        assert "What you told it" in back.output


def test_the_sheets_own_instructions_cannot_be_mistaken_for_answers(a_folder, tmp_path):
    """Uncommenting the whole sheet by accident used to feed it its own examples.

    They are refused now — and refused by name, saying which line — rather than
    read as pictures called 'one' and 'another'.
    """
    from apothecary.gathering.judgement import CannotRead, read_answers

    sheet = tmp_path / "q.txt"
    _run(a_folder, "--ask", sheet)
    everything_uncommented = "\n".join(
        line[2:] if line.startswith("# ") else line
        for line in sheet.read_text(encoding="utf-8").splitlines()
    )
    with pytest.raises(CannotRead) as refused:
        read_answers(everything_uncommented)
    assert "line " in str(refused.value)


def test_asking_for_no_questions_is_refused_by_the_command(a_folder, tmp_path):
    said = _run(a_folder, "--ask", tmp_path / "q.txt", "--most", "0")
    assert said.exit_code != 0
    assert "fewest" in said.output


def test_holding_questions_back_is_admitted_rather_than_hidden(a_folder, tmp_path):
    sheet = tmp_path / "q.txt"
    said = _run(a_folder, "--ask", sheet, "--most", "1")
    assert said.exit_code == 0
    written = sheet.read_text(encoding="utf-8")
    if "held back" in said.output:
        assert "not written here" in written


def test_a_file_saved_by_an_ordinary_editor_is_read(a_folder, tmp_path):
    """Three invisible bytes at the front made the first name unrecognisable."""
    answers = tmp_path / "mine.txt"
    answers.write_bytes("﻿bench_left and shed are the same thing\n".encode("utf-8"))
    said = _run(a_folder, "--answers", answers)
    assert said.exit_code == 0, said.output
    assert "What you told it" in said.output
