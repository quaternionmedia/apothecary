"""The page as the server now answers it (docs/plans/part-iteration-2026-10-12.md,
part 2's Phase B), through the page's own controls: Apply off up front where this
OpenSCAD cannot build a part, the server's integers, choices and groups drawn, a
saved variant renamed, duplicated, restored from its history, deleted to the trash
and back, and the trash emptied only when asked twice; two variants compared,
overlaid and side by side, with what differs; a render waiting its turn said to be
queued; Download SCAD giving the edit; and Slice and the readiness checklist
following the variant drawn. A part in a submodule, edited as its overlay, is
tests/e2e/test_text_tied.py's.

The server is this module's own: the OpenSCAD every test server runs, a variant
cache of its own, the simulated printer idle and pinned to printer_1's mainboard,
and the scripted OrcaSlicer of the unit tests. What no OpenSCAD here can make --
OpenSCAD's queue holding a render back -- is said to the page by answering its own
requests (Playwright's route): the page draws what it is told.
"""

from __future__ import annotations

import json
import re

import httpx
import pytest
from playwright.sync_api import Page, expect
from slicer_helpers import write_fake_orcaslicer
from viewer_ready import settled

from apothecary.projects.parts.calibration_cube import DEFAULT as CUBE
from apothecary.projects.parts.stl_renderer import params_sidecar_path

PART = "calibration_cube"
PRINTER = "/dev/ttyFAKE1"
BOARD = "printer_1.frame_system.mainboard"
RING_MS = 15000
WEDGES = (
    "() => Object.fromEntries([...document.querySelectorAll('#ring-overlay .wedge')]"
    ".filter((w) => !w.classList.contains('empty'))"
    ".map((w) => [w.getAttribute('aria-label'), w.dataset.cell]))"
)
TALLER = "translate([0, 0, size]) cube(size / 2);"


@pytest.fixture(scope="module")
def url(start_server, every_stl_built, tmp_path_factory):
    real = every_stl_built()["path"]
    if not real:
        pytest.skip("OpenSCAD not installed")
    folder = tmp_path_factory.mktemp("part-answers")
    orca = write_fake_orcaslicer(tmp_path_factory.mktemp("orca"))
    url = start_server(
        {
            "APOTHECARY_OPENSCAD": real,
            "APOTHECARY_CACHE_DIR": str(folder / "cache"),
            "APOTHECARY_SIMULATED_PRINTER": "idle",
            "APOTHECARY_ORCASLICER": str(orca),
            "FAKE_ORCA_LAYERS": "5",
            "FAKE_ORCA_DWELL": "10",
        }
    )
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()
        http.put(
            f"/sites/garage/nodes/{BOARD}/device", json={"identity": PRINTER}
        ).raise_for_status()
    return url


@pytest.fixture
def cube_as_it_was():
    stl = CUBE.get_stl_output_path()
    files = (stl, params_sidecar_path(stl))
    kept = {path: path.read_bytes() for path in files if path.exists()}
    yield
    for path in files:
        if path in kept:
            path.write_bytes(kept[path])
        else:
            path.unlink(missing_ok=True)


def _open(page: Page, url: str, site: str = "parts_library", part: str = PART) -> None:
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{url}/viewer/sites/{site}")
    expect(page.locator("#status")).to_contain_text("Loaded", timeout=20000)
    page.evaluate("() => localStorage.removeItem('apothecary.panels')")
    page.wait_for_function(
        f"() => {{ const m = window.fractalViewer.meshByName['{part}'];"
        " return m && !m.userData.isPlaceholder; }",
        timeout=60000,
    )
    settled(page)


def _press(page: Page, *labels: str) -> None:
    for label in labels:
        page.wait_for_function(
            f"() => [...document.querySelectorAll('#ring-overlay .wedge')]"
            f".some((w) => w.getAttribute('aria-label') === {label!r})",
            timeout=RING_MS,
        )
        page.keyboard.press(page.evaluate(WEDGES)[label])


def _ring(page: Page, part: str, *labels: str) -> None:
    page.locator(f"#contents-list .contents-item[data-path='{part}']").click(
        button="right", modifiers=["Control"]
    )
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=RING_MS)
    _press(page, *labels)


def _edit(page: Page, part: str = PART) -> None:
    _ring(page, part, "Part", "Edit")
    expect(
        page.locator(f".part-editor[data-target='part:{part}'] #part-params .param")
    ).not_to_have_count(0, timeout=15000)


def _status(page: Page):
    return page.locator("#status")


def _save(page: Page, url: str, name: str, scad: str | None = None, params=None) -> None:
    body = {"name": name, "params": params or {}}
    if scad is not None:
        body["scad"] = scad
    answer = page.request.post(f"{url}/parts/{PART}/saved", data=body)
    assert answer.ok, answer.text()


def _row(page: Page, name: str):
    return page.locator(f".scad-saved .saved-row[data-variant='{name}']")


def _manage(page: Page, name: str):
    """The variant's row in the editor's list, its ⋯ unfolded."""
    row = _row(page, name)
    expect(row).to_be_visible(timeout=15000)
    if row.locator(".variant-manage").is_hidden():
        row.locator(".variant-more").click()
    return row


# --- what this OpenSCAD can build, and the server's own fields -----------------------


@pytest.mark.e2e
def test_apply_is_off_up_front_where_this_openscad_cannot_build_the_part(page: Page, url):
    """gridfinity needs a newer OpenSCAD than the one these servers run: its editor says
    so when it opens, and Apply stays off whatever is staged. Its whole numbers step by
    one, its choices are drop-downs, and its hole options are a group of their own
    described fields."""
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _open(page, url)
    _edit(page, "gridfinity")
    note = page.locator("#part-build-note")
    expect(note).to_be_visible()
    expect(note).to_contain_text("Apply is off: needs OpenSCAD")
    gridx = page.locator("#part-params > .param[data-field='gridx']")
    assert gridx.locator(".param-slider").get_attribute("step") == "1"
    gridx.locator(".param-number").fill("4")
    expect(page.locator("#stage-summary")).to_contain_text("1 change staged, valid", timeout=10000)
    expect(page.locator("#apply-btn")).to_be_disabled()
    define = page.locator("#part-params > .param[data-field='gridz_define'] select.param-choice")
    expect(define.locator("option")).to_have_count(4)
    group = page.locator("#part-params > .param[data-field='hole_options']")
    expect(group.locator(".param.sub .caption").first).to_be_visible()
    # Part › Apply says why, rather than a refusal after a render was asked for.
    _ring(page, "gridfinity", "Part", "Apply")
    expect(_status(page)).to_contain_text("gridfinity: needs OpenSCAD", timeout=10000)
    assert errors == []


# --- saved variants, managed -----------------------------------------------------------


@pytest.mark.e2e
def test_a_saved_variant_is_renamed_duplicated_restored_deleted_and_the_trash_emptied_twice_asked(
    page: Page, url, cube_as_it_was
):
    own = CUBE.source_file.read_text()
    _save(page, url, "first", own.rstrip("\n") + "\n" + TALLER + "\n", {"size": 12})
    _save(page, url, "first", own.rstrip("\n") + "\n" + TALLER + "\n", {"size": 14})
    _open(page, url)
    _edit(page)
    expect(page.locator(".scad-editor .cm-content")).to_be_visible(timeout=20000)

    # Duplicated, then the copy renamed: each under the name typed beside it.
    row = _manage(page, "first")
    row.locator(".variant-to").fill("second")
    row.locator(".variant-duplicate").click()
    expect(_status(page)).to_contain_text("second is a copy of first", timeout=15000)
    row = _manage(page, "second")
    row.locator(".variant-to").fill("third")
    row.locator(".variant-rename").click()
    expect(_status(page)).to_contain_text("second is called third now", timeout=15000)
    expect(_row(page, "second")).to_have_count(0)
    expect(_row(page, "third")).to_be_visible()

    # first's history: its two saves, the older restored -- a new save of it.
    row = _manage(page, "first")
    row.locator(".variant-history").click()
    history = row.locator(".history-row")
    expect(history).to_have_count(2, timeout=15000)
    expect(history.first).to_have_class(re.compile(r"\bcurrent\b"))
    expect(history.nth(1).locator(".saved-numbers")).to_contain_text("size 12")
    history.nth(1).locator(".variant-restore").click()
    expect(_status(page)).to_contain_text("first is as it was at", timeout=15000)
    expect(_manage(page, "first").locator(".history-row")).to_have_count(3)
    saved = page.request.get(f"{url}/parts/{PART}/saved/first").json()
    assert saved["params"] == {"size": 12}

    # Deleted: to the trash, which Deleted lists; restored from there.
    _manage(page, "third").locator(".variant-delete").click()
    expect(_status(page)).to_contain_text("third moved to the trash", timeout=15000)
    trash = page.locator(".scad-saved details.variant-trash")
    expect(trash.locator("summary")).to_have_text("Deleted (1)")
    trash.locator("summary").click()
    trash.locator(".trash-row[data-variant='third'] .trash-restore").click()
    expect(_status(page)).to_contain_text("third is back among the variants", timeout=15000)
    expect(_row(page, "third")).to_be_visible()

    # Deleted for good only when asked twice; and the trash emptied the same way.
    _manage(page, "third").locator(".variant-delete").click()
    expect(_status(page)).to_contain_text("third moved to the trash", timeout=15000)
    trash = page.locator(".scad-saved details.variant-trash")
    forget = trash.locator(".trash-row[data-variant='third'] .trash-forget")
    forget.click()
    expect(_status(page)).to_contain_text("third would be deleted for good, which cannot be undone")
    expect(forget).to_have_text("Press again to confirm")
    assert [v["name"] for v in page.request.get(f"{url}/parts/{PART}/trash").json()] == ["third"]
    forget.click()
    expect(_status(page)).to_contain_text("third is deleted for good", timeout=15000)
    assert page.request.get(f"{url}/parts/{PART}/trash").json() == []
    _manage(page, "first").locator(".variant-delete").click()
    expect(_status(page)).to_contain_text("first moved to the trash", timeout=15000)
    empty = page.locator(".scad-saved details.variant-trash .trash-empty")
    empty.click()
    expect(_status(page)).to_contain_text("every deleted variant would be deleted for good")
    empty.click()
    expect(_status(page)).to_contain_text(
        "the trash is emptied, 1 variant deleted for good", timeout=15000
    )
    expect(page.locator(".scad-saved details.variant-trash summary")).to_have_text("Deleted (0)")


@pytest.mark.e2e
def test_every_action_on_a_saved_variant_is_a_cell_of_part_variants(
    page: Page, url, cube_as_it_was
):
    """The owner's answer of 2026-10-12: Part › Variants › a name is a ring -- Draw,
    Rename, Duplicate, History, Compare, Delete -- and Part › Variants › Deleted holds
    the trash, each deleted variant Restore and Forget, and Empty; what destroys is
    chosen twice. A name no cell types: Rename and Duplicate put the cursor in the
    variant's box, and Enter does it."""
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    own = CUBE.source_file.read_text()
    _save(page, url, "one", own.rstrip("\n") + "\n" + TALLER + "\n", {"size": 12})
    _open(page, url)
    _edit(page)
    expect(page.locator(".scad-editor .cm-content")).to_be_visible(timeout=20000)

    _ring(page, PART, "Part", "Variants", "one", "Draw")
    expect(_status(page)).to_contain_text("one", timeout=60000)
    expect(_row(page, "one")).to_have_class(re.compile(r"\bchosen\b"), timeout=15000)

    _ring(page, PART, "Part", "Variants", "one", "Duplicate")
    box = _row(page, "one").locator(".variant-to")
    expect(box).to_be_focused(timeout=15000)
    expect(_status(page)).to_contain_text("type the name to copy one to")
    page.keyboard.type("two")
    page.keyboard.press("Enter")
    expect(_status(page)).to_contain_text("two is a copy of one", timeout=15000)

    _ring(page, PART, "Part", "Variants", "two", "Rename")
    expect(_row(page, "two").locator(".variant-to")).to_be_focused(timeout=15000)
    page.keyboard.type("three")
    page.keyboard.press("Enter")
    expect(_status(page)).to_contain_text("two is called three now", timeout=15000)
    expect(_row(page, "three")).to_be_visible()

    _ring(page, PART, "Part", "Variants", "one", "History")
    expect(_status(page)).to_contain_text("one's 1 save", timeout=15000)
    expect(_row(page, "one").locator(".history-row")).to_have_count(1)

    _ring(page, PART, "Part", "Variants", "three", "Delete")
    expect(_status(page)).to_contain_text("three moved to the trash", timeout=15000)
    _ring(page, PART, "Part", "Variants", "Deleted", "three", "Restore")
    expect(_status(page)).to_contain_text("three is back among the variants", timeout=15000)

    # Forget and Empty: the first choice says what it would do, the same cell again does it.
    _ring(page, PART, "Part", "Variants", "three", "Delete")
    expect(_status(page)).to_contain_text("three moved to the trash", timeout=15000)
    _ring(page, PART, "Part", "Variants", "Deleted", "three", "Forget")
    expect(_status(page)).to_contain_text("choose the same cell again to confirm", timeout=15000)
    assert [v["name"] for v in page.request.get(f"{url}/parts/{PART}/trash").json()] == ["three"]
    _ring(page, PART, "Part", "Variants", "Deleted", "three", "Forget")
    expect(_status(page)).to_contain_text("three is deleted for good", timeout=15000)
    _ring(page, PART, "Part", "Variants", "one", "Delete")
    expect(_status(page)).to_contain_text("one moved to the trash", timeout=15000)
    _ring(page, PART, "Part", "Variants", "Deleted", "Empty")
    expect(_status(page)).to_contain_text("every deleted variant would be deleted for good")
    _ring(page, PART, "Part", "Variants", "Deleted", "Empty")
    expect(_status(page)).to_contain_text("the trash is emptied, 1 variant", timeout=15000)
    assert page.request.get(f"{url}/parts/{PART}/trash").json() == []
    assert errors == []


# Each compared mesh as the camera sees it: its bounding box's corners projected, in the
# canvas's pixels.
ON_SCREEN = """() => {
    const v = window.fractalViewer, r = v.canvas.getBoundingClientRect();
    return v.compareMeshes.map((m) => {
        m.geometry.computeBoundingBox();
        const b = m.geometry.boundingBox, xs = [], ys = [];
        for (const x of [b.min.x, b.max.x]) for (const y of [b.min.y, b.max.y]) for (const z of [b.min.z, b.max.z]) {
            const p = m.localToWorld(new m.position.constructor(x, y, z)).project(v.camera);
            xs.push((p.x + 1) / 2 * r.width); ys.push((1 - p.y) / 2 * r.height);
        }
        return { left: Math.min(...xs), right: Math.max(...xs), top: Math.min(...ys), bottom: Math.max(...ys),
                 width: r.width, height: r.height };
    });
}"""


def _both_in_view(page: Page) -> None:
    """Both compared meshes framed: inside the world's view, and each big enough to see."""
    settled(page)
    shown = page.evaluate(ON_SCREEN)
    assert len(shown) == 2, shown
    for box in shown:
        assert box["left"] >= 0 and box["right"] <= box["width"], box
        assert box["top"] >= 0 and box["bottom"] <= box["height"], box
        assert box["right"] - box["left"] > box["width"] / 8, box
        assert box["bottom"] - box["top"] > box["height"] / 8, box


@pytest.mark.e2e
def test_two_variants_are_compared_overlaid_and_side_by_side_with_what_differs(
    page: Page, url, cube_as_it_was
):
    own = CUBE.source_file.read_text()
    _save(page, url, "tall-top", own.rstrip("\n") + "\n" + TALLER + "\n", {"size": 16})
    _open(page, url)
    _edit(page)
    expect(page.locator(".scad-editor .cm-content")).to_be_visible(timeout=20000)
    # Compare is the variant's ⋯'s button and its ring cell; the cell here.
    _ring(page, PART, "Part", "Variants", "tall-top", "Compare")
    expect(_status(page)).to_contain_text(
        "tall-top beside the part's own, overlaid: 1 number differs, and its SCAD differs",
        timeout=90000,
    )
    view = page.locator("#part-compare")
    expect(view.locator(".compare-sizes")).to_contain_text(
        "tall-top 16.00 × 16.00 × 24.00 mm · the part's own 10.00 × 10.00 × 10.00 mm"
    )
    expect(view.locator(".compare-params")).to_contain_text("size: 16 → its default")
    # a to b: what the part's own lacks of tall-top's SCAD.
    expect(view.locator(".variant-diff pre")).to_contain_text(f"-{TALLER}")
    meshes = """() => window.fractalViewer.compareMeshes.map((m) => {
        const box = new m.position.constructor(); m.geometry.computeBoundingBox();
        return [m.position.x, m.position.y, m.position.z]; })"""
    page.wait_for_function("() => window.fractalViewer.compareMeshes.length === 2", timeout=30000)
    overlaid = page.evaluate(meshes)
    assert overlaid[0][0] == pytest.approx(overlaid[1][0], abs=4)
    assert not page.evaluate("() => window.fractalViewer.meshByName['calibration_cube'].visible")
    _both_in_view(page)
    view.locator("select.compare-mode").select_option("side by side")
    page.wait_for_function(
        "() => { const [a, b] = window.fractalViewer.compareMeshes;"
        " return a && b && b.position.x - a.position.x > 15; }",
        timeout=30000,
    )
    expect(_status(page)).to_contain_text("drawn side by side")
    _both_in_view(page)
    view.locator(".compare-close").click()
    expect(view).to_be_hidden()
    assert page.evaluate("() => window.fractalViewer.compareMeshes.length") == 0
    assert page.evaluate("() => window.fractalViewer.meshByName['calibration_cube'].visible")


# --- the queue, Download, Slice and the checklist ----------------------------------------


@pytest.mark.e2e
def test_a_render_waiting_its_turn_is_said_to_be_queued_and_the_page_stops_asking(
    page: Page, url, cube_as_it_was
):
    """While a render of this page is in flight the page asks OpenSCAD's queue about its
    own runs (GET /openscad/runs?page=), says it is queued and how far back, and stops
    asking once nothing of its own is waiting or running. The queue's answer is the
    server's shape, made to hold this page's render back."""
    asked = []
    # Held back until the page's render is sent at last.
    state = {"held": True}

    def runs(route):
        page_id = re.search(r"page=([^&]+)", route.request.url).group(1)
        asked.append(route.request.url)
        waiting = (
            [
                {
                    "id": 7,
                    "kind": "render",
                    "part": PART,
                    "page": page_id,
                    "asked": 0,
                    "position": 2,
                    "waited_seconds": 1.5,
                }
            ]
            if state["held"]
            else []
        )
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"limit": 2, "running": [], "waiting": waiting}),
        )

    page.route("**/openscad/runs*", runs)
    _open(page, url)
    _edit(page)
    page.on("request", lambda r: state.update(held=False) if "/draft/render" in r.url else None)
    page.evaluate(
        """() => { const real = window.fetch;
            window.fetch = async (u, init) => {
                if (String(u).includes('/draft/render')) await new Promise((ok) => setTimeout(ok, 2500));
                return real(u, init);
            }; }"""
    )
    page.locator("#part-params > .param[data-field='size'] .param-number").fill("13")
    expect(page.locator("#stage-summary")).to_contain_text("1 change staged, valid", timeout=10000)
    page.locator("#apply-btn").click()
    queue = page.locator("#part-queue")
    expect(queue).to_contain_text(
        "Queued: this render of calibration_cube waits for OpenSCAD -- 1 ahead of it", timeout=10000
    )
    expect(_status(page)).to_contain_text("an applied variant, not saved", timeout=60000)
    expect(queue).to_be_hidden(timeout=10000)
    settled(page)
    page.wait_for_timeout(1500)
    before = len(asked)
    page.wait_for_timeout(2000)
    assert len(asked) == before, "the page went on asking about the queue"


@pytest.mark.e2e
def test_download_scad_gives_the_edit(page: Page, url, cube_as_it_was):
    _open(page, url)
    _edit(page)
    code = page.locator(".scad-editor .cm-content")
    expect(code).to_be_visible(timeout=20000)
    code.click()
    page.keyboard.press("Control+End")
    page.keyboard.insert_text("\n// downloaded as edited")
    with page.expect_download(timeout=20000) as got:
        page.locator(".part-scad-download").click()
    download = got.value
    assert download.suggested_filename == "calibration_cube.scad"
    assert open(download.path(), encoding="utf-8").read().endswith("// downloaded as edited")
    expect(_status(page)).to_contain_text("downloaded, the SCAD as the editor has it")


@pytest.mark.e2e
def test_slice_and_the_checklist_follow_the_variant_drawn(page: Page, url):
    """footpedal, standing in the garage with printer_1's board pinned: its checklist is
    of the variant drawn, against printer_1's build volume, and Slice slices that
    variant, its record naming it."""
    _open(page, url, site="garage", part="footpedal")
    _edit(page, "footpedal")
    checklist = page.locator("#part-checklist .checklist-of")
    expect(checklist).to_contain_text("The saved part, against a build volume of", timeout=15000)
    first = page.locator("#part-params > .param").first
    field = first.get_attribute("data-field")
    box = first.locator(".param-number")
    value = float(box.input_value())
    box.fill(f"{value + 2:g}")
    expect(page.locator("#stage-summary")).to_contain_text("1 change staged, valid", timeout=10000)
    with page.expect_response(lambda r: "/draft/render" in r.url, timeout=90000) as answer:
        page.locator("#apply-btn").click()
    variant = answer.value.json()["variant"]
    assert variant
    expect(checklist).to_contain_text(f"The variant drawn ({variant[:8]})", timeout=30000)
    expect(checklist).to_contain_text("(printer_1")
    _ring(page, "footpedal", "Slice")
    expect(_status(page)).to_contain_text(
        "slicing footpedal, the variant drawn, for printer_1", timeout=20000
    )
    machine = page.locator(".panel[data-panel='machine']")
    expect(machine.locator("#print-slice-said")).to_contain_text(
        f"footpedal (the variant {variant[:8]}) sliced for printer_1", timeout=90000
    )
    record = page.request.get(f"{url}/slicer/slices").json()[0]
    assert record["made"]["variant"] == variant
    assert record["made"]["params"][field] == pytest.approx(value + 2)


# --- Selected's Device section, where a board belongs ------------------------------------


@pytest.mark.e2e
def test_the_device_section_stands_only_where_a_board_belongs(page: Page, url):
    """The owner's word: Selected's Device section is on a board, a printer, a piece that
    names a sketch (footpedal) and anything a board is pinned to already, so its Unpin
    stays in reach; a plain printed part, a bin or a structure has none."""
    section = page.locator("#selected-body .device-section")

    def chosen(path: str) -> None:
        page.locator(f"#contents-list .contents-item[data-path='{path}']").click()
        expect(
            page.locator(f"#contents-list .contents-item.selected[data-path='{path}']")
        ).to_be_visible()

    _open(page, url)
    for plain in (PART, "gridfinity", "v_slot"):
        chosen(plain)
        expect(section).to_have_count(0)
    # A board of the library is one.
    chosen("esp32_devkitc")
    expect(section).to_be_visible()

    _open(page, url, site="garage", part="footpedal")
    chosen("printer_1")  # a printer, its board pinned inside it
    expect(section).to_be_visible()
    expect(section).to_contain_text(PRINTER, timeout=10000)
    chosen("footpedal")  # names a sketch
    expect(section).to_be_visible()
    chosen("workbench")  # a structure: nothing to pin
    expect(section).to_have_count(0)

    # A plain part with a board pinned to it anyway keeps its Device section, its Unpin.
    pinned = page.request.put(
        f"{url}/sites/parts_library/nodes/{PART}/device", data={"identity": "NOTHERE456"}
    )
    assert pinned.ok, pinned.text()
    try:
        _open(page, url)
        page.evaluate("() => window.fractalViewer.boards.scan()")
        page.wait_for_function(f"() => !!window.fractalViewer.bindings['{PART}']", timeout=10000)
        chosen(PART)
        expect(section).to_be_visible()
        expect(section.locator(".dev-unpin")).to_be_visible()
    finally:
        page.request.delete(f"{url}/sites/parts_library/nodes/{PART}/device")
