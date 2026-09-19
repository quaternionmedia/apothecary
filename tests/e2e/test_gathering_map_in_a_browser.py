"""The picture of what went with what, opened in a real browser.

Reading the page and believing it renders is exactly the mistake this project has
already made once: the viewer was read, believed, and did not work at all with no
way out to the internet. So the map is driven rather than inspected — loaded with
no network available, in light and in dark, with every console message watched.

Needs no server. The map is one file that fetches nothing, and this test would
fail loudly if that stopped being true.
"""

from pathlib import Path

import pytest
from playwright.sync_api import Page

from apothecary.gathering import gather
from apothecary.gathering.picture_map import as_html
from apothecary.models.vectors import Vector2D
from apothecary.vision.models import FoundShape, Picture, ShapeKind


def _shape(kind, x, y, half=0.06):
    return FoundShape(
        kind=kind,
        min_point=Vector2D(x=x - half, y=y - half),
        max_point=Vector2D(x=x + half, y=y + half),
        confidence=0.8,
        origin="plain",
    )


def _picture(name, offset=0.0, half=0.06):
    spots = [(0.2, 0.25), (0.45, 0.6), (0.7, 0.35), (0.55, 0.8)]
    kinds = [ShapeKind.RECT, ShapeKind.DISC, ShapeKind.TRI, ShapeKind.RECT]
    return Picture(
        name=name,
        pixel_width=400,
        pixel_height=300,
        finder="plain",
        shapes=[
            _shape(kind, x + offset, y + offset, half)
            for kind, (x, y) in zip(kinds, spots, strict=True)
        ],
    )


@pytest.fixture(scope="module")
def drawn_map(tmp_path_factory) -> Path:
    result = gather(
        [
            _picture("bench_from_the_left"),
            _picture("bench_from_the_right", offset=0.02),
            _picture("something_else", offset=0.0, half=0.02),
            Picture(name="a_blank_wall", pixel_width=400, pixel_height=300, finder="plain"),
        ]
    )
    where = tmp_path_factory.mktemp("map") / "went-together.html"
    where.write_text(as_html(result), encoding="utf-8")
    return where


@pytest.mark.e2e
def test_the_map_draws_without_a_word_of_complaint(page: Page, drawn_map: Path):
    trouble = []
    page.on("console", lambda m: trouble.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: trouble.append(str(e)))
    page.on("requestfailed", lambda r: trouble.append(f"asked for {r.url}"))

    page.goto(drawn_map.as_uri())
    page.wait_for_load_state("load")

    assert page.locator("svg").count() == 1
    assert not trouble, trouble


@pytest.mark.e2e
def test_it_asks_the_network_for_nothing(page: Page, drawn_map: Path):
    """The one that would have caught the viewer's own failure.

    Everything the page needs is inside it. If that ever stops being true this
    goes red here rather than on somebody's machine with the network off.
    """
    asked_for = []
    page.on("request", lambda r: asked_for.append(r.url))
    page.goto(drawn_map.as_uri())
    page.wait_for_load_state("load")

    outside = [url for url in asked_for if not url.startswith("file://")]
    assert not outside, outside


@pytest.mark.e2e
def test_every_picture_handed_in_appears_on_it(page: Page, drawn_map: Path):
    page.goto(drawn_map.as_uri())
    # `text_content`, not `inner_text`: drawn text is not laid-out text, and the
    # browser answers `None` for every one of these if you ask the other way.
    labels = page.locator("svg text.label").all_text_contents()
    assert set(labels) == {
        "bench_from_the_left",
        "bench_from_the_right",
        "something_else",
        "a_blank_wall",
    }


@pytest.mark.e2e
def test_the_picture_nothing_could_be_read_from_is_shown_as_such(page: Page, drawn_map: Path):
    """A photograph that quietly vanished would be the worst outcome here."""
    page.goto(drawn_map.as_uri())
    hollow = page.locator("svg circle.dot.unread")
    assert hollow.count() == 1
    beside_it = page.locator("svg g.node").filter(has=page.locator("circle.dot.unread"))
    assert "a_blank_wall" in (beside_it.first.text_content() or "")


@pytest.mark.e2e
def test_it_reads_in_the_dark_as_well_as_the_light(page: Page, drawn_map: Path):
    """Both sets of colours were chosen and checked, not flipped automatically."""
    page.goto(drawn_map.as_uri())
    root = page.locator(".viz-root")

    page.emulate_media(color_scheme="light")
    light = root.evaluate("el => getComputedStyle(el).backgroundColor")
    light_ink = root.evaluate("el => getComputedStyle(el).color")

    page.emulate_media(color_scheme="dark")
    dark = root.evaluate("el => getComputedStyle(el).backgroundColor")
    dark_ink = root.evaluate("el => getComputedStyle(el).color")

    assert light != dark, "the two modes look identical"
    assert light_ink != dark_ink


@pytest.mark.e2e
def test_the_same_thing_is_also_said_in_a_table(page: Page, drawn_map: Path):
    """Whoever the drawing does not serve gets the same information in words."""
    page.goto(drawn_map.as_uri())
    rows = page.locator("table").first.locator("tbody tr")
    assert rows.count() == 4
    assert "a_blank_wall" in page.locator("table").first.inner_text()


# --------------------------------------------------------------------------
# The picture people are shown
#
# It comes out of the same run as the assertions above, against the real page,
# not from a separate harness wearing a demonstration hat. A picture produced by
# a second code path is a second copy of the behaviour, and the two drift.
#
# The artifact is recorded, never compared. A test that diffs images fails on a
# font and gets switched off; a test that asserts what the code did cannot be
# switched off without losing the test. The protection is in the assertions; the
# picture is output.
# --------------------------------------------------------------------------

SHOWN = Path(__file__).resolve().parents[2] / "docs" / "generated" / "gathering"


@pytest.fixture(scope="module")
def a_real_gathering(tmp_path_factory):
    """Photographs drawn to order, sorted, with two things a person said.

    Drawn rather than fetched so the same run gives the same picture, and so
    nothing here depends on somebody's holiday photographs being present.
    """
    from apothecary.gathering import bench, gather
    from apothecary.gathering.judgement import read_answers
    from apothecary.vision.plain import PlainFinder

    folder = tmp_path_factory.mktemp("shown")
    bench.draw_occasions(folder, each=2, seed=17)
    paths = sorted(folder.glob("*.png"))
    finder = PlainFinder()
    pictures = [finder.look(path) for path in paths]
    said = read_answers(
        "parts0_left and parts0_right are parts of one thing\n"
        "parts1_left and parts1_right are parts of one thing\n"
        "close0_near and close0_whole are the same thing\n"
        "blankset_empty is not worth using   # a blank wall\n"
    )
    return paths, gather(pictures, paths=paths, answers=said)


@pytest.mark.e2e
def test_the_picture_shown_to_people_comes_out_of_a_real_run(
    page: Page, a_real_gathering, tmp_path
):
    """One test. It asserts what the code did, and the picture is what it saw."""
    from apothecary.gathering.picture_map import as_html

    paths, found = a_real_gathering
    where = tmp_path / "went-together.html"
    where.write_text(as_html(found), encoding="utf-8")

    trouble = []
    page.on("console", lambda m: trouble.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: trouble.append(str(e)))
    page.set_viewport_size({"width": 1180, "height": 900})
    page.goto(where.as_uri())
    page.wait_for_load_state("load")

    # --- the assertions. These are the regression protection. --------------
    assert not trouble, trouble

    joined = [c for c in found.clusters if c.kind != "on its own"]
    assert len(joined) >= 4, "the picture is supposed to show several groups"

    told = found.told()
    assert len(told) == 3, "three of those groups a person decided"

    # Every group a person made is drawn heavier than one the machine worked out.
    theirs = page.locator("svg line.edge.told")
    assert theirs.count() == len(
        told
    ), "a join somebody made must be visibly different from one it guessed"
    assert (
        page.locator("svg circle.dot.unread").count() == 1
    ), "the photograph nothing could be read from has to still be on the page"
    assert "you decided" in page.locator(".headline").inner_text()

    # --- and only now, the picture ----------------------------------------
    SHOWN.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOWN / "which-pictures-went-together.png"), full_page=False)
    page.emulate_media(color_scheme="dark")
    page.wait_for_timeout(120)
    page.screenshot(path=str(SHOWN / "which-pictures-went-together-dark.png"))

    # The generator asserts its own artifacts exist. Fifteen lines turns
    # "somebody forgot" into a red build.
    for name in (
        "which-pictures-went-together.png",
        "which-pictures-went-together-dark.png",
    ):
        made = SHOWN / name
        assert (
            made.exists() and made.stat().st_size > 5_000
        ), f"{name} was not written, or is too small to be a picture of anything"
