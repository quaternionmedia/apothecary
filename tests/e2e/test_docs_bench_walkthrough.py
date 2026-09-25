"""The second demonstration: the bench drawn as it is, a camera looking at it, and
what stays on this machine.

Like the first (`test_docs_photo_walkthrough.py`), this module is the page:
`walkthrough/12-the-bench-as-it-is.md` is what it writes, the ordinary test
command runs it, and each step is an assertion the run has to satisfy before
it becomes a sentence. The model half needs no browser; the browser half runs
in a browser launched with Chromium's fake camera, so a camera can be placed
in the world on every machine and no real one is ever opened.
"""

from __future__ import annotations

import importlib
import re
import socket

import pytest
from playwright.sync_api import expect

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


def _camera_marks_visible(page):
    return page.evaluate(
        "() => Object.values(window.fractalViewer.cameraMarks).map((l) => l.visible)"
    )


@pytest.mark.e2e
@pytest.mark.walkthrough
def test_the_bench_as_it_is(camera_page, base_url: str, walkthrough, tmp_path):
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

    page = camera_page
    story = walkthrough(
        ordinal="12",
        slug="the-bench-as-it-is",
        title="The bench as it is, and a camera looking at it",
        intro=(
            "A mesh made in another program is brought in measured, not trusted; a "
            "part can be a folder with a sidecar and no Python; the garage's printers "
            "are Ender 3s from published dimensions and its boards are the boards. A "
            "camera placed at a piece is drawn there, at the level where that piece "
            "is, and nowhere else. And nothing here leaves the machine, by "
            "construction rather than by anyone's care."
        ),
        runtime=(
            "The model half runs in this process. The browser half drives a real "
            "browser against a real server; the browser is launched with a fake "
            "camera so there is one to place. It needs no network, and it refuses "
            "one."
        ),
        does_not_show=[
            "**A real camera.** The camera placed here is Chromium's test pattern. "
            "Nothing of anyone's room is in these pictures.",
            "**A printer or board that is connected.** The Ender 3s and the boards "
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
        "The printers are Ender 3s from published dimensions",
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
    for name in ("workbench", "printer_1", "printer_3", "esp32_blink", "raspberry_pi_4"):
        expect(page.locator("#contents-list")).to_contain_text(name)
    page.evaluate("() => localStorage.removeItem('apothecary.panels')")
    page.wait_for_timeout(1500)
    # The root frames the whole building; the bench is what this page is
    # about, so frame the view on it and what stands on it.
    page.evaluate(
        """() => {
            const v = window.fractalViewer;
            const on = new Set(['workbench', 'printer_1', 'printer_2', 'printer_3', 'esp32_blink',
                                'footpedal', 'arduino_uno', 'raspberry_pi_4', 'teensy_40']);
            const level = v.currentRenderNodes(v.currentFocusNode());
            v.frameCameraForChildren(level.filter((n) => on.has(n.name)));
        }"""
    )
    page.wait_for_timeout(600)
    story.shows(
        "The bench at the garage's root: three Ender 3s on it, the boards at its right end",
        "The root shows the whole building; here the view is framed on the bench. "
        "Every machine and board is the part it names, drawn from its own STL, and "
        "the site places each by its footprint.",
    )

    page.locator("#contents-list .contents-item[data-path='printer_1']").click()
    expect(_part_row(page)).to_contain_text("ender3", timeout=5000)
    page.wait_for_timeout(300)
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
    page.wait_for_timeout(1200)
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
    page.wait_for_timeout(1200)
    story.shows(
        "The DevKitC standing on its pins",
        "esp32_blink is a sketch and the board it runs on, drawn as the board: the "
        "described part from the model half of this page, in the world.",
    )

    # A camera, placed at the bench and drawn there.
    page.evaluate("() => window.fractalViewer.zoomOut()")
    page.evaluate("() => window.apothecaryPanels.open('camera')")
    panel = page.locator(".panel[data-panel='camera']")
    expect(panel).to_be_visible(timeout=3000)
    panel.locator("#cam-allow").click()
    page.wait_for_function(
        "() => window.apothecaryCamera && window.apothecaryCamera.live()", timeout=8000
    )
    page.locator("#contents-list .contents-item[data-path='workbench']").click()
    expect(panel.locator("#cam-place")).to_be_enabled(timeout=3000)
    panel.locator("#cam-place").click()
    expect(panel.locator("#cam-place-note")).to_contain_text("placed at workbench", timeout=5000)
    page.evaluate("() => window.fractalViewer.zoomIn('workbench')")
    badge = page.locator(".world-badge.camera-mark")
    expect(badge).to_be_visible(timeout=5000)
    assert _camera_marks_visible(page) == [True]
    # Nothing stands between the camera and the top of the bench, so the badge
    # is not dimmed: the transform gizmo's picking plane, a mesh the size of the
    # scene, is not something in the way.
    page.wait_for_timeout(300)
    expect(badge).not_to_have_class(re.compile(r"\bbehind\b"))
    cameras = page.request.get(f"{base_url}/cameras?site=garage").json()
    assert [c["path"] for c in cameras] == ["workbench"]
    page.wait_for_timeout(600)
    story.shows(
        "A camera placed at the bench is drawn there",
        "Allowed in the Camera panel and placed at the selected piece, the camera "
        "gets a badge above the bench and a small frustum at it, kept on the server "
        "so every browser looking at this site sees it standing there.",
    )

    page.evaluate("() => { const v = window.fractalViewer; v.zoomOut(); v.zoomIn('printer_1'); }")
    expect(badge).to_be_hidden(timeout=5000)
    assert _camera_marks_visible(page) == [False]
    page.wait_for_timeout(600)
    story.shows(
        "Looking into a printer, the camera's mark stays at the bench",
        "A mark is drawn at the level where its piece is. Zoomed into something "
        "else, neither the badge nor the frustum follows; zooming back out brings "
        "both back.",
    )

    page.evaluate("() => window.fractalViewer.zoomOut()")
    expect(badge).to_be_visible(timeout=5000)
    assert _camera_marks_visible(page) == [True]
    panel.locator("#cam-unplace").click()
    expect(badge).to_have_count(0, timeout=5000)
    assert page.request.get(f"{base_url}/cameras?site=garage").json() == []
    story.says(
        "Unplaced, it leaves the world",
        "The placement is a record on this machine and nothing more; taking it "
        "back removes the mark for every browser.",
        shown="GET /cameras?site=garage -> []",
    )

    # ------------------------------------------------------ kept, taken back
    # Two pictures drawn to order, added from the file picker; a board pinned to
    # the DevKitC by a typed identity; both listed on the panel with the button
    # that takes each back.
    from PIL import Image, ImageDraw

    for name in ("shelf.png", "shelf_again.png"):
        drawn = Image.new("L", (320, 240), 245)
        ImageDraw.Draw(drawn).rectangle((30, 30, 200, 120), fill=30)
        drawn.save(tmp_path / name)
    pictures_before = len(page.request.get(f"{base_url}/photos/pictures").json())
    panel.locator("#pic-file").set_input_files(
        [str(tmp_path / "shelf.png"), str(tmp_path / "shelf_again.png")]
    )
    expect(panel.locator("#pic-list .pic")).to_have_count(pictures_before + 2, timeout=8000)
    added = [
        p["path"] for p in page.request.get(f"{base_url}/photos/pictures").json() if p["kept"]
    ]
    assert "uploads/shelf.png" in added and "uploads/shelf_again.png" in added
    pinned = page.request.put(
        f"{base_url}/sites/garage/nodes/esp32_blink/device",
        data={"identity": "aa:bb:cc:dd:ee:ff"},
    )
    assert pinned.ok, pinned.text()
    panel.locator("#pin-refresh").click()
    expect(panel.locator("#pin-list .kept-row")).to_have_count(1, timeout=5000)
    expect(panel.locator("#pin-list .kept-row")).to_contain_text("garage › esp32_blink")
    # Floated free of the rail for the picture, so the whole panel is in view.
    page.evaluate(
        """() => {
            window.apothecaryPanels.float('camera');
            const el = document.querySelector(".panel-free-layer .panel[data-panel='camera']");
            el.style.left = '16px'; el.style.top = '16px';
            el.querySelector('#pic-list').scrollIntoView({ block: 'start' });
        }"""
    )
    page.wait_for_timeout(400)
    story.shows(
        "What the browser put here, it can take back",
        "Pictures added from the file picker are kept as they were named, under "
        "the picture folder's uploads/, each with a button that forgets it; the "
        "cameras placed in the world and the boards pinned to pieces are listed, "
        "every site's, each with the button that takes it back -- a pin whose "
        "site or piece is gone is shown as such, and this is the one place it "
        "can be seen.",
    )

    page.evaluate("() => window.apothecaryPanels.dock('camera', 'right')")
    panel.locator("#pin-list .pin-unpin").click()
    expect(panel.locator("#pin-list")).to_contain_text("none pinned", timeout=5000)
    page.once("dialog", lambda d: d.accept())
    panel.locator("#pic-purge").click()
    expect(panel.locator("#cam-note")).to_contain_text("of the folder's own stay", timeout=8000)
    left = page.request.get(f"{base_url}/photos/pictures").json()
    assert all(not p["kept"] for p in left)
    assert page.request.get(f"{base_url}/firmware/pins").json()["pins"] == []
    story.says(
        "And a purge forgets only what the browser put here",
        "The pictures a person put in the folder by hand are theirs; the tool "
        "never deletes one from a page. What it kept -- a camera's frames, the "
        "pictures added here -- it forgets on request, after asking once.",
        shown=(
            f"{len(added)} added, {len(added)} forgotten; {len(left)} of the folder's own left\n"
            "GET /firmware/pins -> []"
        ),
    )

    # ------------------------------------------------------------ stays local
    with pytest.raises(LeftTheMachine) as refused:
        socket.create_connection(("example.com", 80), timeout=2)
    elsewhere = page.request.get(
        f"{base_url}/cameras?site=garage", headers={"Origin": "http://elsewhere.test"}
    )
    assert elsewhere.status == 403, elsewhere.text()
    story.says(
        "And none of it leaves the machine",
        "The guard is on the process, installed when the package is imported: a "
        "connection past this machine is refused before any name is looked up. The "
        "server answers this machine alone; a page from anywhere else asking it "
        "for the cameras gets a refusal, not the list. Neither is a setting.",
        shown=(
            f"{refused.value}\n\n"
            f"Origin: http://elsewhere.test -> {elsewhere.status} {elsewhere.text()}"
        ),
    )
