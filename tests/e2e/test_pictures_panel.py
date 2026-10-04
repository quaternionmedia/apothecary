"""Pictures: every picture under the picture root, the folder's own and the kept
ones, newest first, each with the places it is pinned at as a view; Forget on a
kept one, Purge kept, and the gathering as a section.

The ring's Picture › Folder holds the seven newest. A row chosen in Pictures is
told to the ring, and Folder's eighth cell pins it when it is older than those:
here one is pinned at the bench that way. Every picture, view and kept picture a
test adds is taken back after it, so a later test finds the server as it would
alone.
"""

from __future__ import annotations

import io
import os
import re

import pytest
from PIL import Image, ImageDraw
from playwright.sync_api import expect

WEDGES = (
    "() => Object.fromEntries([...document.querySelectorAll('#ring-overlay .wedge')]"
    ".filter((w) => !w.classList.contains('empty'))"
    ".map((w) => [w.dataset.cell, w.getAttribute('aria-label')]))"
)
OLD = "oldest.png"
NEWER = [f"a_newer_picture_{i}.png" for i in range(8)]


def _drawn(offset: int) -> Image.Image:
    img = Image.new("L", (400, 300), 245)
    ImageDraw.Draw(img).rectangle((40 + offset, 40, 200 + offset, 160), fill=30)
    return img


def _png(offset: int) -> bytes:
    out = io.BytesIO()
    _drawn(offset).save(out, format="PNG")
    return out.getvalue()


def _press(page, label: str) -> None:
    page.wait_for_function(
        "(label) => [...document.querySelectorAll('#ring-overlay .wedge')]"
        ".some((w) => w.getAttribute('aria-label') === label)",
        arg=label,
        timeout=5000,
    )
    page.keyboard.press(next(c for c, got in page.evaluate(WEDGES).items() if got == label))


def _open(page, base_url: str) -> None:
    page.goto(f"{base_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    page.evaluate("() => localStorage.removeItem('apothecary.panels')")


def _views(page, base_url: str) -> list:
    return page.request.get(f"{base_url}/sites/garage/attached").json()["views"]


@pytest.fixture
def leaves_as_found(page, base_url: str, picture_folder):
    """The folder's pictures, the views and the kept pictures as they were before."""
    api = page.request
    views = {vw["id"] for vw in api.get(f"{base_url}/placed").json()["views"]}
    pictures = {p["path"] for p in api.get(f"{base_url}/photos/pictures").json()}
    yield
    for view in api.get(f"{base_url}/placed").json()["views"]:
        if view["id"] not in views:
            api.delete(f"{base_url}/sites/{view['site']}/views/{view['id']}")
    for picture in api.get(f"{base_url}/photos/pictures").json():
        if picture["path"] in pictures:
            continue
        if picture["kept"]:
            api.delete(f"{base_url}/photos/pictures/{picture['path']}")
        else:
            (picture_folder / picture["path"]).unlink(missing_ok=True)


def _folder_on_the_bench(page) -> dict:
    """The bench's ring, entered to Picture › Folder: its wedges, cell -> label."""
    page.locator("#contents-list .contents-item[data-path='workbench']").click(button="right")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    _press(page, "Picture")
    _press(page, "Folder")
    return page.evaluate(WEDGES)


def _marked(page) -> list:
    return page.evaluate(
        "() => [...document.querySelectorAll('#ring-overlay .wedge.marked')]"
        ".map((w) => [w.dataset.cell, w.getAttribute('aria-label'), w.getAttribute('aria-current')])"
    )


@pytest.mark.e2e
def test_a_chosen_picture_older_than_the_seventh_is_pinned_at_the_bench_from_the_ring(
    page, base_url: str, picture_folder, leaves_as_found
):
    """A picture put in the folder before eight others is not one of Folder's seven;
    Folder's More opens Pictures. Its row, clicked, is chosen -- one at a time, let go
    by a click again or by Escape -- and the bench's Folder then ends in "Pin oldest",
    which pins it at the bench as a view. Chosen among the seven, a picture's own cell
    is marked and the eighth is More. Pictures has no Pin here of its own."""
    _drawn(0).save(picture_folder / OLD)
    os.utime(picture_folder / OLD, (1_000_000_000, 1_000_000_000))  # 2001: older than any
    for i, name in enumerate(NEWER):
        _drawn(10 + i * 5).save(picture_folder / name)
    listed = [p["path"] for p in page.request.get(f"{base_url}/photos/pictures").json()]
    assert listed.index(OLD) >= 7  # past the seven newest the ring's Folder holds
    newest = listed[0]

    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _open(page, base_url)
    status = page.locator("#status")

    # The bench's ring: Folder holds the seven newest and More, and not this picture.
    labels = list(_folder_on_the_bench(page).values())
    assert "More" in labels and "oldest" not in labels and not _marked(page)
    _press(page, "More")
    panel = page.locator(".panel[data-panel='pictures']")
    expect(panel).to_be_visible(timeout=3000)
    expect(status).to_contain_text(
        "every picture is in Pictures: choose one there, and Folder's last cell pins it at "
        "workbench as a view"
    )
    expect(panel.locator(".pictures-pin")).to_have_count(0)
    row = panel.locator(f".picture-row[data-path='{OLD}']")
    expect(row).to_be_visible(timeout=5000)
    expect(row.locator(".picture-views")).to_contain_text("pinned nowhere")
    chosen = panel.locator(".picture-row.chosen")
    expect(chosen).to_have_count(0)

    # Chosen by a click, one at a time; a click again lets go, and so does Escape.
    row.click()
    expect(row).to_have_class(re.compile(r"\bchosen\b"))
    expect(row).to_have_attribute("aria-selected", "true")
    expect(status).to_contain_text(
        f"{OLD} chosen: open the ring on a structure or the floor, and Picture › Folder "
        "pins it there as a view"
    )
    expect(panel.locator("#pictures-where")).to_contain_text(f"{OLD} chosen")
    other = panel.locator(f".picture-row[data-path='{newest}']")
    other.click()
    expect(chosen).to_have_count(1)
    expect(other).to_have_class(re.compile(r"\bchosen\b"))
    other.click()
    expect(chosen).to_have_count(0)
    row.click()
    page.locator("#viewer-canvas").focus()
    page.keyboard.press("Escape")
    expect(chosen).to_have_count(0)
    assert page.evaluate("() => window.apothecaryPictureVerbs.chosen()") is None

    # Chosen, it is Folder's eighth cell on the bench's ring: pressed, pinned there.
    row.click()
    expect(row).to_have_class(re.compile(r"\bchosen\b"))
    wedges = _folder_on_the_bench(page)
    assert wedges["7"] == "Pin oldest" and "More" not in wedges.values()
    assert not _marked(page)
    _press(page, "Pin oldest")
    expect(status).to_contain_text(
        f"{OLD} pinned at workbench as a view: Picture › Find shapes finds what is in it",
        timeout=5000,
    )
    expect(status).not_to_have_class(re.compile(r"\berror\b"))
    views = [vw for vw in _views(page, base_url) if vw["picture"] == OLD]
    assert [vw["host"] for vw in views] == ["workbench"]
    expect(row.locator(".picture-view.here")).to_have_text("workbench", timeout=5000)
    page.wait_for_function(
        "(p) => { const d = window.apothecaryPictures.drawnAt('workbench'); return d && d.picture === p; }",
        arg=OLD,
        timeout=5000,
    )
    expect(row).to_have_class(re.compile(r"\bchosen\b"))  # still chosen, to pin again elsewhere

    # Chosen among the seven: its own cell marked, and the eighth is More.
    other.click()
    wedges = _folder_on_the_bench(page)
    assert wedges["7"] == "More"
    marked = _marked(page)
    assert len(marked) == 1 and marked[0][2] == "true"
    expect(page.locator(f"#ring-cell-{marked[0][0]}")).to_have_attribute(
        "aria-label", wedges[marked[0][0]]
    )
    page.keyboard.press("Escape")  # the ring closes; the choice stays
    expect(page.locator("#ring-overlay")).to_have_count(0)
    expect(other).to_have_class(re.compile(r"\bchosen\b"))

    # A view's place, clicked: selected, and that view drawn there.
    page.evaluate("() => { const v = window.fractalViewer; v.jumpTo(0); v.selectFloor(); }")
    row.locator(f".picture-view.here[data-view='{views[0]['id']}']").click()
    assert page.evaluate("() => window.fractalViewer.selectedName") == "workbench"
    assert (
        page.evaluate("() => window.apothecaryPictures.drawnAt('workbench').id") == views[0]["id"]
    )
    expect(status).to_contain_text(f"drawing {OLD} at workbench")
    expect(other).to_have_class(re.compile(r"\bchosen\b"))  # a place clicked chooses nothing
    assert errors == []


@pytest.mark.e2e
def test_folder_more_opens_pictures(page, base_url: str):
    """The eighth leaf of Picture › Folder, More, opens Pictures."""
    _open(page, base_url)
    carried = page.evaluate(
        "() => window.apothecaryPictureVerbs.carry({ action: 'picture:more',"
        " context: { pointing: 'node', targets: ['workbench'] } })"
    )
    assert carried is True
    expect(page.locator(".panel[data-panel='pictures']")).to_be_visible(timeout=3000)
    expect(page.locator("#status")).to_contain_text("Pictures")


@pytest.mark.e2e
def test_forget_and_purge_from_pictures(page, base_url: str, picture_folder, leaves_as_found):
    """A kept picture pinned at the bench, forgotten from its row: its view is unpinned
    and its mat goes. Purge kept asks once and forgets every kept picture, the folder's
    own staying; asked again, it has nothing to forget and says so as a refusal."""
    pinned = page.request.post(
        f"{base_url}/photos/pictures?name=forget_from_pictures.png&kept=upload&site=garage&host=workbench",
        data=_png(0),
        headers={"Content-Type": "image/png"},
    )
    assert pinned.status == 201, pinned.text()
    pinned = pinned.json()
    loose = page.request.post(
        f"{base_url}/photos/pictures?name=purge_from_pictures.png&kept=upload",
        data=_png(40),
        headers={"Content-Type": "image/png"},
    )
    assert loose.status == 201, loose.text()
    loose = loose.json()
    _drawn(70).save(picture_folder / "the_folders_own.png")

    _open(page, base_url)
    page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === 'workbench' && e.mat)",
        timeout=5000,
    )
    page.evaluate("() => window.apothecaryPanels.open('pictures')")
    panel = page.locator(".panel[data-panel='pictures']")
    kept = panel.locator(f".picture-row[data-path='{pinned['path']}']")
    expect(kept).to_contain_text("· added", timeout=5000)
    expect(kept.locator(".picture-view")).to_have_text("workbench")
    own = panel.locator(".picture-row[data-path='the_folders_own.png']")
    expect(own).to_be_visible()
    expect(own.locator(".pictures-forget")).to_have_count(0)  # a person's: only a person removes it

    kept.locator(".pictures-forget").click()
    expect(kept).to_have_count(0, timeout=5000)
    page.wait_for_function(
        "() => !window.apothecaryPictures.state().some((e) => e.host === 'workbench')",
        timeout=5000,
    )
    assert not [vw for vw in _views(page, base_url) if vw["picture"] == pinned["path"]]
    expect(page.locator("#status")).to_contain_text(f"forgot {pinned['path']}")

    page.once("dialog", lambda d: d.accept())
    panel.locator("#pictures-purge").click()
    status = page.locator("#status")
    expect(status).to_contain_text("of the folder's own stay", timeout=8000)
    expect(status).not_to_have_class(re.compile(r"\berror\b"))
    expect(panel.locator(f".picture-row[data-path='{loose['path']}']")).to_have_count(
        0, timeout=5000
    )
    expect(own).to_be_visible()
    left = page.request.get(f"{base_url}/photos/pictures").json()
    assert all(not p["kept"] for p in left)
    assert (picture_folder / "the_folders_own.png").is_file()
    panel.locator("#pictures-purge").click()
    expect(status).to_contain_text("nothing kept from the browser to forget", timeout=5000)
    expect(status).to_have_class(re.compile(r"\berror\b"))
