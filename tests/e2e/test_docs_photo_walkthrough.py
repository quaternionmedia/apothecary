"""The one demonstration: photographs into pieces, and those pieces in the viewer.

This module is the walkthrough. `walkthrough/11-photographs-into-pieces.md` is
what it writes, and the ordinary test command runs it, so the page is a record
of a run rather than a description standing beside one.

It used to be two demonstrations. A hand-written page of doctests walked the
model half and said, in its own closing section, that the viewer "is driven by
`apothecary docs generate` rather than here, because it needs a server and a
browser". That sentence was the seam: two pages describing one path, one of them
produced by a command somebody had to remember, and the remembered one went
stale. Joining them costs this -- the demonstration now needs a browser and a
server, everywhere, and the page says so.

Each step below is two things at once: an assertion the run has to satisfy, and
a sentence of the page. A step cannot describe something that did not just
happen, and a run that fails half way writes the steps it reached rather than
leaving the last green run's page in place.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

SITE = "walkthrough_bench"


@pytest.fixture
def drawn_picture(picture_folder):
    """A picture with four obvious shapes in it, drawn rather than downloaded.

    Drawn into the one folder the server is allowed to read, because it refuses
    everything else.
    """
    from PIL import Image, ImageDraw

    folder = picture_folder
    picture = Image.new("L", (800, 600), 245)
    pen = ImageDraw.Draw(picture)
    pen.rectangle((60, 60, 320, 220), fill=30)
    pen.ellipse((470, 70, 690, 290), fill=20)
    pen.polygon([(110, 520), (370, 520), (240, 330)], fill=25)
    pen.rectangle((470, 380, 720, 425), fill=35)
    path = folder / "bench.png"
    picture.save(path)
    return path


@pytest.fixture
def tidy_up(page: Page, base_url: str):
    """Forget anything this test shelved, however the test ends.

    The server outlives every test in the run. Tidying up on the last line only
    works when the test reaches its last line, and a test that fails half way
    then poisons every test after it.
    """
    shelved: list[str] = []
    yield shelved.append
    for name in shelved:
        page.request.delete(f"{base_url}/photos/{name}")


CONTRADICTORY_ANSWERS = """
a and b are the same thing
b and a are not related
"""

TOLD = """
parts0_left and parts0_right are parts of one thing
blankset_empty is not worth using
"""


@pytest.mark.e2e
@pytest.mark.walkthrough
def test_photographs_into_pieces(
    page: Page, base_url: str, walkthrough, drawn_picture, tidy_up, tmp_path
):
    """Walk the whole chain, from a photograph to pieces you can walk into."""
    from apothecary import census, workflows
    from apothecary.gathering import bench, gather
    from apothecary.gathering.judgement import PeopleDisagree, read_answers, settle
    from apothecary.gathering.questions import worth_asking
    from apothecary.vision import build
    from apothecary.vision.plain import PlainFinder
    from apothecary.vocabulary import word_for

    story = walkthrough(
        ordinal="11",
        slug="photographs-into-pieces",
        title="Photographs into pieces you could print",
        intro=(
            "Point the tool at a photograph. It finds the flat shapes in it, matches "
            "each one to a named, reusable word, places them in space, sorts a folder "
            "of them into what belongs with what, asks you the questions it cannot "
            "settle, and shows the result in the viewer it already had. Nothing claims "
            "to be measured unless somebody said how wide the picture is."
        ),
        runtime=(
            "It draws its own photographs and reads them back, then walks the same "
            "pieces in a real browser against a real server. It needs no network. It "
            "does need a browser and a running server, which is the price of this "
            "page and the viewer's page being one page."
        ),
        does_not_show=[
            "**A real photograph.** Everything here is drawn to order, which is how "
            "the answers are known. Shadow, texture, blur and clutter are all "
            "absent, so a good showing here means it handles the easy case.",
            "**A printable model.** Turning an arrangement into a solid needs a "
            "program this run does not install. Nothing below the arrangement is "
            "exercised.",
            "**Anything about how long it takes.** No timing is asserted anywhere in " "this run.",
            "**Anything surviving a restart.** Nothing here is stored. The run "
            "builds what it needs and forgets it.",
        ],
    )

    # ------------------------------------------------------------------ model
    folder = tmp_path / "drawn"
    folder.mkdir()
    bench.draw_occasions(folder, each=1, seed=17)
    picture_path = folder / "same0_a.png"
    assert picture_path.exists()

    finder = PlainFinder()
    picture = finder.look(picture_path)
    assert picture.name == "same0_a"
    assert len(picture.shapes) >= 3
    story.says(
        "A photograph becomes shapes",
        "The finder is deliberately plain: it shrinks the picture, splits light from "
        "dark, gathers touching pixels, and guesses each blob from how much of its "
        "box it fills. This one was drawn to order, so the answer is known.",
        shown=f"{len(picture.shapes)} shapes found in {picture.name}",
    )

    first = picture.shapes[0]
    assert 0.0 <= first.min_point.x <= 1.0
    assert 0.0 <= first.max_point.y <= 1.0
    story.says(
        "Nothing there is a measurement",
        "A photograph on its own cannot say how big anything is, so every position "
        "comes back as a fraction of the picture.",
        shown=(
            f"x from {first.min_point.x:.3f} to {first.max_point.x:.3f}, "
            f"y from {first.min_point.y:.3f} to {first.max_point.y:.3f}"
        ),
    )

    choice = word_for(first)
    assert choice.word in {"plate", "disc", "post", "slot", "wedge"}
    assert 0.0 < first.confidence < 1.0
    story.says(
        "Each shape gets a name, and says how sure it is",
        "A word is a recipe that builds an ordinary node, so a named shape is "
        "something the rest of the tool already knows how to handle. The confidence "
        "is never rounded up. It is measurably lower when the finder is wrong, which "
        "is what makes it worth reporting at all.",
        shown=f"{choice.word}, {first.confidence:.2f} sure",
    )

    made = build(picture, picture_path=picture_path)
    assert len(made.site.children) == len(picture.shapes)
    assert made.album.sized is False
    assert all(piece.status == "unsized" for piece in made.site.children)
    about = made.album.provenance[made.site.children[0].name]
    assert about.finder == "plain"
    assert about.thickness_guessed is True
    story.says(
        "Placed, and honest about not being measured",
        "Give it no real-world size and the pieces are still placed, marked as "
        "having no size rather than quietly given one. Every piece carries where it "
        "came from.",
        shown=(
            f"{len(made.site.children)} pieces, sized={made.album.sized}\n"
            f"first piece seen by the '{about.finder}' finder, "
            f"thickness guessed: {about.thickness_guessed}"
        ),
    )

    paths = sorted(folder.glob("*.png"))
    pictures = [finder.look(path) for path in paths]
    found = gather(pictures, paths=paths)
    assert len(found.readings) == len(paths)
    assert "blankset_empty" in found.set_aside
    story.says(
        "Several photographs at once, and which are of the same thing",
        "Some of these are of one thing, some are neighbouring parts of something "
        "bigger, and some are of nothing in particular. A photograph with nothing in "
        "it is set aside with a reason rather than quietly dropped.",
        shown=(
            f"{len(found.readings)} photographs read\n"
            f"blankset_empty set aside: {found.set_aside['blankset_empty']}"
        ),
    )

    groups = [c for c in found.clusters if c.kind != "on its own"]
    assert len(groups) >= 1
    said = found.between("same0_a", "same0_b")
    assert said.verdict == "the same thing"
    assert len(said.because) >= 1
    undecided = found.undecided()
    assert all(k.verdict == "cannot tell" for k in undecided)
    story.says(
        "Every answer says why, and 'cannot tell' is an answer",
        "The sorting is conservative on purpose: it would rather decline a pair than "
        "guess at it. A pair it cannot decide comes back as a real answer with a "
        "reason attached, not as a gap in the output.",
        shown=(
            f"{len(groups)} group(s) built, {len(undecided)} pair(s) declined\n"
            f"same0_a and same0_b: {said.verdict}, because {said.because[0]}"
        ),
    )

    questions = worth_asking(found, most=3)
    assert len(questions) >= 1
    assert "photographs of the same thing" in questions[0].sentence()
    answers = read_answers(TOLD)
    assert [one.verdict for one in answers] == ["parts of one thing", "not worth using"]
    story.says(
        "You are better at this than it is, so it asks",
        "It works out which questions are worth a minute, best first, by how many "
        "other pairs an answer would settle. A person answers in plain sentences, "
        "and the whole language is five of them.",
        shown=questions[0].sentence(),
    )

    told = gather(pictures, paths=paths, answers=answers)
    joined = told.between("parts0_left", "parts0_right")
    assert joined.verdict == "parts of one thing"
    assert joined.said_by == "you"
    assert joined.strength == 1.0
    holding = told.cluster_holding("parts0_left")
    assert sorted(holding.pictures) == ["parts0_left", "parts0_right"]
    card = told.scorecard()
    assert card["you answered"] == 2
    assert card["agreed"] + card["overruled"] + card["silent"] == card["about a pair"]
    story.says(
        "Their word wins, carries, and marks the machine",
        "A person's answer beats the machine's outright, builds the group that "
        "follows from it, and says who decided. It also scores the machine, because "
        "an answered pair is a pair where the answer is known.",
        shown=(
            f"parts0_left and parts0_right: {joined.verdict}, said by {joined.said_by}\n"
            f"the group it makes: {sorted(holding.pictures)}\n"
            f"scorecard: {card}"
        ),
    )

    with pytest.raises(PeopleDisagree) as refused:
        settle(read_answers(CONTRADICTORY_ANSWERS))
    assert str(refused.value).count("line ") >= 2
    story.says(
        "Two answers that contradict each other are refused",
        "Not averaged, and not last-one-wins. The refusal names both lines, because "
        "the person who wrote them is the only one who can settle it.",
        shown=str(refused.value),
    )

    # ----------------------------------------------------------------- viewer
    built = page.request.post(
        f"{base_url}/photos",
        data={"picture": str(drawn_picture), "name": SITE, "width_mm": 900},
    )
    assert built.ok, built.text()
    tidy_up(SITE)
    album = built.json()
    assert len(album["pieces"]) >= 3, album

    page.goto(f"{base_url}/photos/{SITE}/picture")
    page.wait_for_timeout(300)
    story.shows(
        "The same path, now against a real server",
        f"This is the picture the rest of the page is about: {album['pixel_width']} "
        f"by {album['pixel_height']} pixels, {len(album['pieces'])} shapes found by "
        f"the '{album['finder']}' finder. Everything above ran in this process. "
        "Everything below runs through the server and a browser.",
    )

    words = sorted(album["groups"])
    assert words, album
    assert album["sized"] is True
    assert album["share_a_machine_guessed"] == 1.0
    story.says(
        "Told how wide it is, the pieces get real sizes",
        "Nine hundred millimetres across, so the pieces have sizes rather than "
        "fractions. That a machine picked every one of these shapes is recorded "
        "separately from whether they have a size, because they are different "
        "claims.",
        shown=f"words: {', '.join(words)}\nsized: {album['sized']}",
    )

    page.goto(f"{base_url}/viewer/sites/{SITE}")
    expect(page.locator(".toolbar h1")).to_contain_text("Apothecary")
    page.wait_for_timeout(700)
    story.shows(
        "The arrangement opens in the viewer the tool already had",
        "No drawing code was written for any of this. An arrangement built from a "
        "photograph is an ordinary arrangement, so the viewer already knew how to "
        "show it.",
    )

    contents = page.locator("#contents-list")
    for name in list(album["pieces"])[:2]:
        expect(contents).to_contain_text(name)
    story.shows(
        "Every piece is listed, named for the word it was matched to",
        "The names in this list are the words from the top of this page. One "
        "vocabulary runs the whole length of the path.",
    )

    chips = page.locator("#category-filters")
    for word in words:
        expect(chips).to_contain_text(word)
    first_word = words[0]
    chips.get_by_text(first_word, exact=False).first.click()
    page.wait_for_timeout(400)
    story.shows(
        f"Filtering to '{first_word}' keeps that word and sets the rest aside",
        "The filters the viewer already had are filters by word now, because the "
        "pieces simply carry their word.",
    )

    page.locator("#contents-list .contents-item").first.click()
    page.wait_for_timeout(400)
    expect(page.locator("#selected-body")).not_to_be_empty()
    story.shows(
        "Choosing a piece shows where it came from",
        "Which finder saw it, how sure it was, and that its thickness is a guess: "
        "the same provenance the model half printed, in front of a person.",
    )

    picture_response = page.request.get(f"{base_url}/photos/{SITE}/picture")
    assert picture_response.ok
    assert picture_response.body()[:4] == b"\x89PNG"

    forgotten = page.request.delete(f"{base_url}/photos/{SITE}")
    assert forgotten.ok
    assert SITE not in page.request.get(f"{base_url}/sites").json()
    story.says(
        "And it forgets on request",
        "The picture it was all built from is served beside the arrangement while "
        "the arrangement exists, and both go when the arrangement is forgotten.",
    )

    # ------------------------------------------------------------ what it costs
    controls = census.take()
    typed = workflows.take()
    story.says(
        "What the whole thing costs a person",
        "Two meters, because a tool that is pleasant to demonstrate and expensive to "
        "use is neither. The first counts the controls the viewer puts on screen, "
        "and unifying means it reaches nothing rather than a smaller pile. The "
        "second counts what a person types to reach a named job, and every job "
        "carried by nothing but typing is an open item about where the interface "
        "stops.",
        shown=(
            f"{len(controls.controls_of_its_own())} controls of the viewer's own\n"
            f"{typed.typed} typed steps, "
            f"{len(typed.only_typed())} job(s) carried by nothing but typing"
        ),
    )


@pytest.mark.e2e
def test_the_walkthrough_would_notice_if_the_grouping_stopped_working(
    page: Page, base_url: str, drawn_picture, tidy_up
):
    """A walkthrough that cannot fail is a screenshot with a caption.

    The step above claiming the viewer filters by word rests on each piece
    carrying its word. This checks the same thing from the other side: strip the
    words out and the filters have nothing to show.
    """
    built = page.request.post(
        f"{base_url}/photos",
        data={"picture": str(drawn_picture), "name": "grouping_check", "width_mm": 900},
    )
    assert built.ok
    tidy_up("grouping_check")
    words = set(built.json()["groups"])

    tree = page.request.get(f"{base_url}/sites/grouping_check").json()["tree"]
    carried = {child["category"] for child in tree["children"]}
    page.request.delete(f"{base_url}/photos/grouping_check")
    assert carried == words, (
        "the pieces stopped carrying their word, so the viewer's filters would "
        f"show {carried} instead of {words} and the walkthrough step above would "
        "be describing something that no longer happens"
    )
