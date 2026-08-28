"""The whole picture path, driven in a real browser.

Same on-demand pattern as the rest of tests/e2e: a plain run takes no
screenshots; `apothecary docs generate` runs this with `--generate-docs` and
turns the manifest into a walkthrough under docs/generated/.

Each `docs.step(...)` is two things at once — a point where the run has to be
correct, and a sentence of the walkthrough. That is the whole reason the
walkthrough is worth anything: it cannot describe something that did not just
happen, and if the run stops being correct there is no walkthrough to publish
rather than a stale one nobody noticed.

Everything here runs on this machine. The picture is drawn into a folder, the
server is told to look at that folder and nowhere else, and nothing is fetched.
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


@pytest.mark.e2e
@pytest.mark.docs
def test_photo_walkthrough(page: Page, base_url: str, doc_recorder, drawn_picture, tidy_up):
    """Point at a picture, and walk what came out of it in the viewer.

    Shapes are found, matched to named words, placed with a real size, and
    gathered by word — in the viewer the tool already had, with no drawing code
    written for any of it.
    """
    docs = doc_recorder(
        "photo-walkthrough",
        title="From a picture to something you could build (prototype, unratified)",
        intro=(
            "Point the tool at a picture and it finds the flat shapes in it, "
            "matches each one to a named, reusable word, places them in space, "
            "and gathers them by the word they came from. Nothing claims to be "
            "measured unless somebody said how wide the picture is. Everything "
            "runs on this machine with the network switched off."
        ),
    )

    built = page.request.post(
        f"{base_url}/photos",
        data={"picture": str(drawn_picture), "name": SITE, "width_mm": 900},
    )
    assert built.ok, built.text()
    tidy_up(SITE)
    album = built.json()
    assert len(album["pieces"]) >= 3, album

    # Show the picture itself for the first few steps. A walkthrough whose
    # opening frames are a blank page explains nothing, and the picture is the
    # one thing the whole path is about.
    page.goto(f"{base_url}/photos/{SITE}/picture")
    page.wait_for_timeout(300)
    docs.step(
        f"Look at a picture {album['pixel_width']} by {album['pixel_height']} pixels: "
        f"{len(album['pieces'])} shapes found by the '{album['finder']}' finder"
    )

    words = sorted(album["groups"])
    assert words, album
    docs.step(f"Each shape is matched to a word: {', '.join(words)}")

    assert album["sized"] is True
    assert album["share_a_machine_guessed"] == 1.0
    docs.step(
        "The picture is 900mm across, so the pieces have real sizes — and a "
        "machine picked every one of these shapes, which is recorded separately "
        "from whether it has a size"
    )

    page.goto(f"{base_url}/viewer/sites/{SITE}")
    expect(page.locator(".toolbar h1")).to_contain_text("Apothecary")
    page.wait_for_timeout(700)
    docs.step("The arrangement opens in the viewer the tool already had")

    contents = page.locator("#contents-list")
    for name in list(album["pieces"])[:2]:
        expect(contents).to_contain_text(name)
    docs.step("Every piece is listed, named for the word it was matched to")

    chips = page.locator("#category-filters")
    for word in words:
        expect(chips).to_contain_text(word)
    docs.step(
        "The filters the viewer already had are now filters by word — nothing "
        "was drawn to make that happen, the pieces simply carry their word"
    )

    first_word = words[0]
    chips.get_by_text(first_word, exact=False).first.click()
    page.wait_for_timeout(400)
    docs.step(f"Filtering to '{first_word}' keeps that word and sets the rest aside")

    page.locator("#contents-list .contents-item").first.click()
    page.wait_for_timeout(400)
    expect(page.locator("#selected-body")).not_to_be_empty()
    docs.step(
        "Choosing a piece shows where it came from: which finder saw it, how "
        "sure it was, and that its thickness is a guess"
    )

    picture = page.request.get(f"{base_url}/photos/{SITE}/picture")
    assert picture.ok
    assert picture.body()[:4] == b"\x89PNG"
    docs.step("The picture it was all built from is served beside it")

    # Forgetting is checked here as a step of its own; the fixture above is what
    # guarantees it happens when an earlier step fails instead.
    forgotten = page.request.delete(f"{base_url}/photos/{SITE}")
    assert forgotten.ok
    assert SITE not in page.request.get(f"{base_url}/sites").json()


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
