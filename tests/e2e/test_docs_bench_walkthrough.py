"""The second demonstration: the bench drawn as it is, a camera looking at it, and
what stays on this machine.

Like the first (`test_docs_photo_walkthrough.py`), this module is the page:
`walkthrough/12-the-bench-as-it-is.md` is what it writes, the ordinary test
command runs it, and each step is an assertion the run has to satisfy before
it becomes a sentence. The model half needs no browser; the browser half runs
in a browser launched with Chromium's fake camera, so a camera can be placed
in the world on every machine and no real one is ever opened, against a server
of its own whose picture folder holds only what the page puts there: the
pictures another browser test leaves in the session server's folder never
appear in its screenshots.
"""

from __future__ import annotations

import importlib
import re
import socket
from types import SimpleNamespace

import pytest
from playwright.sync_api import expect
from viewer_ready import OCCLUSION_TESTED, settled

# A lid, one inch by two by half an inch, drawn Y-up as a game or web tool
# would: the kind of file that arrives from elsewhere.
LID = [
    ((0, 0, 0), (1, 0, 0), (1, 2, 0)),
    ((0, 0, 0), (1, 2, 0), (0, 2, 0)),
    ((0, 0, 0.5), (1, 2, 0.5), (1, 0, 0.5)),
    ((0, 0, 0.5), (0, 2, 0.5), (1, 2, 0.5)),
]


def _part_row(page):
    return page.locator("#selected-body .prop-row", has_text="Part")


WEDGES = (
    "() => Object.fromEntries([...document.querySelectorAll('#ring-overlay .wedge')]"
    ".filter((w) => !w.classList.contains('empty'))"
    ".map((w) => [w.dataset.cell, w.getAttribute('aria-label')]))"
)


def _wedges(page) -> dict:
    """The open ring's wedges: cell -> label."""
    return page.evaluate(WEDGES)


def _press(page, label: str) -> None:
    """Press the wedge of the open ring that reads this label."""
    page.wait_for_function(
        "(label) => [...document.querySelectorAll('#ring-overlay .wedge')]"
        ".some((w) => w.getAttribute('aria-label') === label)",
        arg=label,
        timeout=5000,
    )
    page.keyboard.press(next(c for c, got in _wedges(page).items() if got == label))


def _camera_marks_visible(page):
    """Whether each camera's pyramid is drawn (picture_marks.js), camera by camera."""
    return page.evaluate(
        "() => window.apothecaryPictures.cameraState().filter((c) => c.pyramid)"
        ".map((c) => c.pyramid.visible)"
    )


@pytest.fixture
def bench(base_url, start_server, _camera_browser, tmp_path_factory):
    """The page's own server, and a page on it in the fake-camera browser with the
    camera allowed. Its picture folder starts empty and holds only what the test puts
    there, so Pictures lists exactly those whatever else ran on this worker; its pins,
    cameras and views start empty too. ``base_url`` is asked for only so that with no
    server to run against this is skipped, as every browser test is."""
    folder = tmp_path_factory.mktemp("bench_pictures")
    url = start_server({"APOTHECARY_PICTURE_ROOT": str(folder)})
    context = _camera_browser.new_context(viewport={"width": 1280, "height": 800}, base_url=url)
    context.grant_permissions(["camera"], origin=url)
    yield SimpleNamespace(page=context.new_page(), url=url, folder=folder)
    context.close()


@pytest.mark.e2e
@pytest.mark.walkthrough
def test_the_bench_as_it_is(bench, walkthrough, tmp_path):
    """Geometry from elsewhere, the bench drawn as the machines it holds, a camera
    placed at a piece and drawn there, and the doors the program keeps shut."""
    from apothecary import meshes
    from apothecary.example_hierarchy import create_example_site
    from apothecary.models.vectors import Vector3D
    from apothecary.primitives import Import
    from apothecary.projects.parts import ender3
    from apothecary.projects.parts.described import part_from_sidecar
    from apothecary.projects.parts.skeleton import ROOT
    from apothecary.projects.registry import scan_projects
    from apothecary.stays_local import LeftTheMachine

    page, base_url, picture_folder = bench.page, bench.url, bench.folder
    story = walkthrough(
        ordinal="12",
        slug="the-bench-as-it-is",
        title="The bench as it is, and a camera looking at it",
        intro=(
            "A mesh made in another program is brought in measured, not trusted; a "
            "part can be a folder with a sidecar and no Python; the garage's printer "
            "is an Ender 3 from published dimensions and its boards are the boards. A "
            "camera placed at a piece is drawn there, at the level where that piece "
            "is, and nowhere else. And nothing here leaves the machine, by "
            "construction rather than by anyone's care."
        ),
        runtime=(
            "The model half runs in this process. The browser half drives a real "
            "browser against a real server of its own, whose picture folder holds "
            "only the pictures this page puts there; the browser is launched with a "
            "fake camera so there is one to place. It needs no network, and it "
            "refuses one."
        ),
        does_not_show=[
            "**A real camera.** The camera placed here is Chromium's test pattern. "
            "Nothing of anyone's room is in these pictures.",
            "**A printer or board that is connected.** The Ender 3 and the boards "
            "are drawn as what they are; none is pinned to a port, and the status "
            "each shows is the site's own.",
            "**The import command writing into the repository.** `apothecary parts "
            "import` is what brings a file in for keeps; this run measures the file "
            "in a temporary folder and leaves `parts/` as it found it.",
            "**The pieces without OpenSCAD.** A part is drawn from an STL that "
            "OpenSCAD renders on first request; on a machine without it the pieces "
            "are their footprint boxes. These pictures were made with it.",
        ],
        page=page,
    )

    # ------------------------------------------------------------------ model
    folder = tmp_path / "elsewhere"
    folder.mkdir()
    lid = folder / "lid.stl"
    meshes.write_stl(LID, lid, name="lid")
    as_drawn = meshes.bounds(meshes.read_mesh(lid))
    placed = meshes.bounds(meshes.transform(meshes.read_mesh(lid), scale=25.4, up="y"))
    assert as_drawn == ((0.0, 0.0, 0.0), (1.0, 2.0, 0.5))
    assert placed[0] == (0.0, -12.7, 0.0)
    assert placed[1][0] == 25.4 and placed[1][2] == 50.8
    story.says(
        "A file made elsewhere is measured, not trusted",
        "The file says nothing about its units or which way is up, so the person "
        "bringing it in says both, and the mesh is turned into millimetres, Z-up, "
        "before anything reads its size. `apothecary parts import` does exactly this "
        "and keeps the answer beside the file, with where it came from.",
        shown=(
            f"in the file: {as_drawn[1][0]} x {as_drawn[1][1]} x {as_drawn[1][2]} (inches, Y up)\n"
            # The quarter turn lands the far edge on -0.0; a zero has no sign worth printing.
            f"kept: x {placed[0][0]}..{placed[1][0]}  y {placed[0][1]}..{placed[1][1] + 0.0:.1f}  "
            f"z {placed[0][2]}..{placed[1][2]} mm, Z up"
        ),
    )

    imported = Import(file=str(lid), scale=25.4, rotate=Vector3D(x=90))
    box = imported.bounds()
    assert imported.render().startswith("rotate([90.0, 0.0, 0.0]) scale(25.4) import(")
    assert (box.min_point.x, box.min_point.y, box.min_point.z) == (0.0, -12.7, 0.0)
    assert round(box.max_point.z, 6) == 50.8
    story.says(
        "Or moved in the model rather than in the file",
        "The same turns as OpenSCAD transforms, so a file that is not in the "
        "scene's frame can be left as it is; `bounds()` reads the file and says "
        "where the transformed mesh ends up, which is the footprint that places it.",
        shown=(
            f"{imported.render().split(' import(')[0]} import(...)\n"
            f"ends up at z {box.min_point.z}..{box.max_point.z:.1f} mm"
        ),
    )

    item = next(p for p in scan_projects(ROOT) if p.kind == "part" and p.name == "esp32_devkitc")
    described = part_from_sidecar(item.path)
    module = importlib.import_module(item.wrapper)
    assert module.DEFAULT.name == described.name == "esp32_devkitc"
    assert described.source is not None and described.source.license == "MIT"
    assert described.default_bounds is not None
    story.says(
        "A part can be a folder with a sidecar and no Python",
        "A `part.json` beside a SCAD says what a wrapper module would have said: "
        "category, colour, bounds, and who made it under what licence. The registry "
        "names such a part's wrapper anyway, and importing that name builds the "
        "part from the sidecar.",
        shown=(
            f"{item.wrapper}\n"
            f"{described.category}; {described.source.author}, {described.source.license}; "
            f"{described.default_bounds.max_point.x:g} x "
            f"{described.default_bounds.max_point.y:g} x "
            f"{described.default_bounds.max_point.z:g} mm"
        ),
    )

    site = create_example_site()
    printer = next(c for c in site.children if c.name == "printer_1")
    frame = next(c for c in printer.children if c.name == "frame_system")
    mainboard = next(c for c in frame.children if c.name == "mainboard")
    assert printer.part_ref == "ender3"
    assert printer.build_origin == ender3.BUILD_ORIGIN
    assert mainboard.part_ref == "creality_v422"
    story.says(
        "The printer is an Ender 3 from published dimensions",
        "A printer node names the part it is, and its children live inside it: the "
        "Creality mainboard in the electronics box, the gantry at the uprights. "
        "`build_origin` puts the bed where it is, so a job's build volume and a "
        "board's marks stand on the real bed rather than on the floor.",
        shown=(
            f"printer_1: part {printer.part_ref}, "
            f"{ender3.OVERALL.x:g} x {ender3.OVERALL.y:g} x {ender3.OVERALL.z:g} mm overall\n"
            f"bed at z = {ender3.BUILD_ORIGIN.z:g}; mainboard: part {mainboard.part_ref}"
        ),
    )

    # ----------------------------------------------------------------- viewer
    page.goto(f"{base_url}/viewer/sites/garage")
    expect(page.locator(".toolbar h1")).to_contain_text("Apothecary")
    contents = page.locator("#contents-list .contents-item")
    expect(contents.first).to_be_visible(timeout=20000)
    for name in ("workbench", "printer_1", "esp32_blink", "raspberry_pi_4"):
        expect(page.locator("#contents-list")).to_contain_text(name)
    page.evaluate("() => localStorage.removeItem('apothecary.panels')")
    # The root frames the whole building; the bench is what this page is
    # about, so frame the view on it and what stands on it.
    page.evaluate(
        """() => {
            const v = window.fractalViewer;
            const on = new Set(['workbench', 'printer_1', 'esp32_blink',
                                'footpedal', 'arduino_uno', 'raspberry_pi_4', 'teensy_40']);
            const level = v.currentRenderNodes(v.currentFocusNode());
            v.frameCameraForChildren(level.filter((n) => on.has(n.name)));
        }"""
    )
    settled(page)
    story.shows(
        "The bench at the garage's root: an Ender 3 at its left end, the boards at its right end",
        "The root shows the whole building; here the view is framed on the bench. "
        "Every machine and board is the part it names, drawn from its own STL, and "
        "the site places each by its footprint.",
    )

    page.locator("#contents-list .contents-item[data-path='printer_1']").click()
    expect(_part_row(page)).to_contain_text("ender3", timeout=5000)
    # Selected's rows run past the rail's lower half: the part row the caption names
    # is scrolled into view.
    _part_row(page).evaluate("(el) => el.scrollIntoView({ block: 'center' })")
    expect(_part_row(page)).to_be_in_viewport(ratio=0.99)  # whole, but for a fraction of a pixel
    settled(page)
    story.shows(
        "A printer is the part it names",
        "Selecting printer_1 shows its rows and, below them, the part its body is. "
        "The power supply stands on the right behind the upright, the spool on its "
        "bracket over the top bar, the electronics box under the bed at the front.",
    )

    page.evaluate("() => window.fractalViewer.zoomIn('printer_1')")
    page.evaluate("() => window.fractalViewer.zoomIn('frame_system')")
    mainboard_row = "#contents-list .contents-item[data-path='printer_1.frame_system.mainboard']"
    page.locator(mainboard_row).click()
    expect(_part_row(page)).to_contain_text("creality_v422", timeout=5000)
    settled(page)
    story.shows(
        "Inside it, the mainboard is the Creality V4.2.2",
        "Zoomed into the printer's frame, its children are drawn and the printer's "
        "body is not: the board in its box, with the pins that would be pinned to a "
        "port. Its outline, holes, headers and jacks are from the maker's drawing.",
    )

    page.evaluate("() => { const v = window.fractalViewer; v.zoomOut(); v.zoomOut(); }")
    page.evaluate("() => window.fractalViewer.zoomIn('esp32_blink')")
    page.locator("#contents-list .contents-item[data-path='esp32_blink']").click()
    expect(_part_row(page)).to_contain_text("esp32_devkitc", timeout=5000)
    settled(page)
    story.shows(
        "The DevKitC standing on its pins",
        "esp32_blink is a sketch and the board it runs on, drawn as the board: the "
        "described part from the model half of this page, in the world.",
    )

    # A camera, added above the bench from the bench's own ring, and told which of
    # this browser's cameras it is from its own.
    page.evaluate("() => window.fractalViewer.zoomOut()")
    page.evaluate("() => window.apothecaryPictureVerbs.ready")
    page.locator("#contents-list .contents-item[data-path='workbench']").click(button="right")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    _press(page, "Camera")
    _press(page, "Add here")
    expect(page.locator("#status")).to_contain_text(
        "added camera_1 above workbench, looking straight down", timeout=5000
    )
    page.wait_for_function("() => window.fractalViewer.selectedName === 'camera_1'")
    page.locator("#contents-list .contents-item[data-path='camera_1']").click(button="right")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    _press(page, "Device")
    _press(page, _wedges(page)["8"])  # this browser's camera, by its name
    expect(page.locator("#status")).to_contain_text(
        "Take picture (P) keeps a frame where it looks", timeout=5000
    )
    # Site's Pinned lists it, every site's cameras and pins listed again as the
    # section unfolds.
    pinned = page.locator(".panel[data-panel='site'] #site-pinned")
    pinned.locator("summary").click()
    placed = pinned.locator(".pin-row.camera")
    expect(placed).to_have_count(1, timeout=5000)
    expect(placed).to_contain_text("garage › camera_1")
    pinned.locator("summary").click()  # folded again, for the pictures below
    badge = page.locator(".world-badge.camera-mark[data-camera='camera_1']")
    expect(badge).to_be_visible(timeout=5000)
    assert _camera_marks_visible(page) == [True]  # selected: its pyramid shows
    # Nothing stands between the camera and the top of the bench, so the badge
    # is not dimmed: the transform gizmo's picking plane, a mesh the size of the
    # scene, is not something in the way.
    settled(page, frames=OCCLUSION_TESTED)
    expect(badge).not_to_have_class(re.compile(r"\bbehind\b"))
    (camera,) = page.request.get(f"{base_url}/sites/garage/attached").json()["cameras"]
    assert camera["name"] == "camera_1" and camera["lands"]["host"] == "workbench"
    story.shows(
        "A camera added above the bench is drawn there",
        "Added from the bench's own ring -- Camera, Add here -- a camera part stands "
        "above the bench looking straight down: its body, its 📷 badge and, while it "
        "is selected, its pyramid from the lens to the bench's top, with a ring to "
        "turn it and an arc to tilt it beside the move arrows. Its own ring's Device "
        "says which of this browser's cameras it is. It is kept on the server, so "
        "every browser looking at this site sees it standing there. The status bar "
        "names the next step, Take picture (P), which keeps a frame where it looks.",
    )

    page.evaluate("() => window.fractalViewer.zoomIn('printer_1')")
    expect(badge).to_be_hidden(timeout=5000)
    assert _camera_marks_visible(page) == [False]
    settled(page)
    story.shows(
        "Looking into a printer, the camera stays in the garage",
        "A camera is a piece of the site, drawn at the level its site is. Zoomed "
        "into something else, neither its badge nor its pyramid follows; zooming "
        "back out brings them back.",
    )

    # Back to the root with nothing selected: zooming out one level would select the
    # printer it left, and its rows and gizmo would stand in the pictures below.
    page.evaluate("() => window.fractalViewer.jumpTo(0)")
    expect(badge).to_be_visible(timeout=5000)
    assert _camera_marks_visible(page) == [False]  # unselected: its body and its badge
    expect(page.locator("#selected-body")).to_contain_text("Click a node to select it")
    # Removed from its row in Site's Pinned.
    pinned.locator("summary").click()
    placed.locator(".pinned-camera-remove").click()
    expect(badge).to_have_count(0, timeout=5000)
    expect(pinned.locator("#pinned-list")).to_contain_text("none pinned")
    assert page.request.get(f"{base_url}/sites/garage/attached").json()["cameras"] == []
    story.says(
        "Removed, it leaves the world",
        "A camera is a piece of the site and a record on this machine, and nothing "
        "more; removing it takes it out of the site for every browser. The pictures "
        "it took stay.",
        shown="GET /sites/garage/attached -> cameras: []",
    )

    # ------------------------------------------------------ kept, taken back
    # Two pictures drawn to order, added from Pictures' file picker; a board pinned
    # to the DevKitC by a typed identity; the pictures listed in Pictures and the
    # board in Site's Pinned, each with the button that takes it back.
    from PIL import Image, ImageDraw

    for name in ("shelf.png", "shelf_again.png"):
        drawn = Image.new("L", (320, 240), 245)
        ImageDraw.Draw(drawn).rectangle((30, 30, 200, 120), fill=30)
        drawn.save(tmp_path / name)
    # One in the picture folder itself, as a person would put it there: what a
    # purge must leave alone.
    theirs = Image.new("L", (320, 240), 245)
    ImageDraw.Draw(theirs).ellipse((40, 40, 220, 200), fill=20)
    theirs.save(picture_folder / "a_person_put_this_here.png")
    listed = page.request.get(f"{base_url}/photos/pictures").json()
    pictures_before = len(listed)
    kept_before = len([p for p in listed if p["kept"]])
    page.evaluate("() => window.apothecaryPanels.open('pictures')")
    pictures = page.locator(".panel[data-panel='pictures']")
    expect(pictures).to_be_visible(timeout=3000)
    rows = pictures.locator(".picture-row")
    expect(rows).to_have_count(pictures_before, timeout=5000)
    pictures.locator("#pic-file").set_input_files(
        [str(tmp_path / "shelf.png"), str(tmp_path / "shelf_again.png")]
    )
    expect(rows).to_have_count(pictures_before + 2, timeout=8000)
    # Kept, and pinned nowhere: the message names the step that pins one.
    expect(page.locator("#status")).to_contain_text(
        "added 2 picture(s) on this machine: choose one, and the ring's Picture › Folder "
        "pins it at a place as a view"
    )
    kept_pictures = pictures.locator(".picture-row:has(.pictures-forget)")
    expect(kept_pictures).to_have_count(kept_before + 2, timeout=5000)
    expect(pictures.locator(".picture-row[data-path='uploads/shelf.png']")).to_contain_text(
        "pinned nowhere"
    )
    expect(
        pictures.locator(".picture-row[data-path='a_person_put_this_here.png'] .pictures-forget")
    ).to_have_count(0)
    added = sorted(
        p["path"] for p in page.request.get(f"{base_url}/photos/pictures").json() if p["kept"]
    )
    assert added == ["uploads/shelf.png", "uploads/shelf_again.png"]
    # The server is this page's own, so the only pin is the one made here.
    assert page.request.get(f"{base_url}/firmware/pins").json()["pins"] == []
    board_pin = page.request.put(
        f"{base_url}/sites/garage/nodes/esp32_blink/device",
        data={"identity": "aa:bb:cc:dd:ee:ff"},
    )
    assert board_pin.ok, board_pin.text()
    # Made outside the page: Pinned lists it when unfolded again.
    pinned.locator("summary").click()
    pinned.locator("summary").click()
    boards = pinned.locator(".pin-row.board")
    expect(boards).to_have_count(1, timeout=5000)
    expect(boards).to_contain_text("garage › esp32_blink")
    # Pictures floated free of the rail beside Site, so both lists are in view.
    page.evaluate(
        """() => {
            window.apothecaryPanels.float('pictures');
            const el = document.querySelector(".panel-free-layer .panel[data-panel='pictures']");
            el.style.left = '16px'; el.style.top = '16px';
        }"""
    )
    # Exactly what this page put in the folder, newest first.
    assert rows.evaluate_all("(rs) => rs.map((r) => r.dataset.path)") == [
        "uploads/shelf_again.png",
        "uploads/shelf.png",
        "a_person_put_this_here.png",
    ]
    # One chosen, for the ring's Picture › Folder to pin.
    pictures.locator(".picture-row[data-path='uploads/shelf.png']").click()
    expect(pictures.locator(".picture-row.chosen")).to_have_attribute(
        "data-path", "uploads/shelf.png"
    )
    expect(page.locator("#status")).to_contain_text(
        "uploads/shelf.png chosen: open the ring on a structure or the floor, and "
        "Picture › Folder pins it there as a view"
    )
    # The thumbnails load lazily: every one in view has arrived.
    page.wait_for_function(
        "() => [...document.querySelectorAll('#pictures-list img')].every((i) => i.complete)"
    )
    settled(page)
    story.shows(
        "What the browser put here, it can take back",
        "Site's Pinned lists what a page pinned -- cameras, views, boards -- every "
        "site's, each row naming its site and carrying the button that takes it back, "
        "from here, without switching to that site; a pin whose site or piece is gone "
        "is shown as such, and this is the one place it can be seen. Pictures lists "
        "every picture in the picture folder, the folder's own and the ones the "
        "browser kept -- those added from its file picker kept as they were named "
        "under uploads/ -- each with where it is pinned as a view, and Forget on a kept "
        "one. A picture kept and pinned nowhere waits to be chosen: a row clicked is "
        "chosen, as shelf.png is here, and the ring's Picture › Folder pins it where "
        "the ring stands -- the seven newest by name, an older one as its last cell -- "
        "as the status bar says.",
    )

    page.evaluate("() => window.apothecaryPanels.dock('pictures', 'right')")
    # Forgotten from its row.
    pictures.locator(".pictures-forget[data-path='uploads/shelf_again.png']").click()
    expect(kept_pictures).to_have_count(kept_before + 1, timeout=5000)
    assert not (picture_folder / "uploads" / "shelf_again.png").exists()
    # A pin whose site is gone is listed as such, and taken back from its row.
    drawn = Image.new("L", (400, 300), 245)
    ImageDraw.Draw(drawn).rectangle((40, 40, 200, 160), fill=30)
    drawn.save(picture_folder / "pins_check.png")
    built = page.request.post(
        f"{base_url}/photos",
        data={"picture": "pins_check.png", "name": "pins_check", "width_mm": 400},
    )
    assert built.ok, built.text()
    piece = next(iter(built.json()["pieces"]))
    stale_pin = page.request.put(
        f"{base_url}/sites/pins_check/nodes/{piece}/device", data={"identity": "/dev/ttyNOWHERE"}
    )
    assert stale_pin.ok, stale_pin.text()
    assert page.request.delete(f"{base_url}/photos/pins_check").ok
    (picture_folder / "pins_check.png").unlink()
    pinned.locator("summary").click()
    pinned.locator("summary").click()
    rows = boards
    expect(rows).to_have_count(2, timeout=5000)
    gone = rows.filter(has_text="pins_check")
    expect(gone).to_have_class(re.compile(r"\bstale\b"))
    expect(gone).to_contain_text("site gone")
    gone.locator(".pinned-board-unpin").click()
    expect(rows).to_have_count(1, timeout=5000)
    # The pin was made outside the viewer, which learns of it when its devices are
    # refreshed. Unpinned from Site's Pinned, the piece's Device section follows at once.
    page.evaluate("() => window.fractalViewer.rescanDevices()")
    page.locator("#contents-list .contents-item[data-path='esp32_blink']").click()
    expect(page.locator("#selected-body .device-section .dev-unpin")).to_be_visible(timeout=8000)
    rows.locator(".pinned-board-unpin").click()
    expect(pinned.locator("#pinned-list")).to_contain_text("none pinned", timeout=5000)
    expect(page.locator("#selected-body .dev-pin-manual")).to_be_visible(timeout=3000)
    expect(page.locator("#selected-body .dev-unpin")).to_have_count(0)
    page.once("dialog", lambda d: d.accept())
    pictures.locator("#pictures-purge").click()
    status = page.locator("#status")
    expect(status).to_contain_text("of the folder's own stay", timeout=8000)
    expect(status).not_to_have_class(re.compile(r"\berror\b"))
    # A second purge has nothing to forget, and says so as a refusal.
    pictures.locator("#pictures-purge").click()
    expect(status).to_contain_text("nothing kept from the browser to forget", timeout=5000)
    expect(status).to_have_class(re.compile(r"\berror\b"))
    left = page.request.get(f"{base_url}/photos/pictures").json()
    assert all(not p["kept"] for p in left)
    assert "a_person_put_this_here.png" in {p["name"] for p in left}
    assert (picture_folder / "a_person_put_this_here.png").is_file()
    assert page.request.get(f"{base_url}/firmware/pins").json()["pins"] == []
    story.says(
        "And a purge forgets only what the browser put here",
        "The pictures a person put in the folder by hand are theirs; the tool "
        "never deletes one from a page. What it kept -- a camera's frames, the "
        "pictures added here -- it forgets on request, after asking once.",
        shown=(
            f"forgotten: {', '.join(sorted(added))}\n"
            "left where it was: a_person_put_this_here.png\n"
            "GET /firmware/pins -> []"
        ),
    )

    # ------------------------------------------------------------ stays local
    with pytest.raises(LeftTheMachine) as refused:
        socket.create_connection(("example.com", 80), timeout=2)
    elsewhere = page.request.get(
        f"{base_url}/sites/garage/attached", headers={"Origin": "http://elsewhere.test"}
    )
    assert elsewhere.status == 403, elsewhere.text()
    story.says(
        "And none of it leaves the machine",
        "The guard is on the process, installed when the package is imported: a "
        "connection past this machine is refused before any name is looked up. The "
        "server answers this machine alone; a page from anywhere else asking it "
        "for a site's cameras and pictures gets a refusal, not the list. Neither is "
        "a setting.",
        shown=(
            f"{refused.value}\n\n"
            f"Origin: http://elsewhere.test -> {elsewhere.status} {elsewhere.text()}"
        ),
    )
