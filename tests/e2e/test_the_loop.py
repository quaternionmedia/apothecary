"""The loop at a place, from the ring alone: a camera pinned at the bench, a picture
taken and pinned as a view, its shapes found as a step of their own, the view
sized, a shape made into a piece standing on its outline, Why this back to it, the
piece dropped, the picture forgotten; and the floor, reached from the canvas
ring's Pictures › Floor.

The browser is Chromium with its fake camera fed a drawn picture
(``--use-file-for-fake-video-capture``): a dark rectangle, disc and triangle on a
light ground, 640 by 480, as tests/e2e/test_camera.py draws them, so the plain
finder has shapes to find in every frame and no real camera is ever opened.

The camera's deviceId is this browser context's: nothing here reloads the page
between pinning a camera and using it, since Chromium may hand a reloaded page
other ids for its fake devices.

Every view, camera, kept picture and made piece a test adds is taken back after
it (tests/e2e/test_picture_in_the_world.py's fixture), and garage is reset.
"""

from __future__ import annotations

import re

import pytest
from PIL import Image, ImageDraw
from playwright.sync_api import expect
from test_picture_in_the_world import leaves_garage_as_found  # noqa: F401 - a fixture
from viewer_ready import settled

WEDGES = (
    "() => Object.fromEntries([...document.querySelectorAll('#ring-overlay .wedge')]"
    ".filter((w) => !w.classList.contains('empty'))"
    ".map((w) => [w.dataset.cell, w.getAttribute('aria-label')]))"
)
STATE = "() => window.apothecaryPictures.state()"
WIDE, HIGH = 640, 480


def _drawing() -> Image.Image:
    img = Image.new("L", (WIDE, HIGH), 245)
    pen = ImageDraw.Draw(img)
    pen.rectangle((40, 40, 260, 160), fill=30)
    pen.ellipse((360, 60, 520, 220), fill=20)
    pen.polygon([(80, 420), (300, 420), (190, 280)], fill=25)
    return img


def _y4m(path) -> None:
    """The drawing as a Y4M stream Chromium's fake camera plays in a loop."""
    ycbcr = _drawing().convert("RGB").convert("YCbCr")
    y, cb, cr = ycbcr.split()
    half = (WIDE // 2, HIGH // 2)
    planes = y.tobytes() + cb.resize(half).tobytes() + cr.resize(half).tobytes()
    with open(path, "wb") as out:
        out.write(f"YUV4MPEG2 W{WIDE} H{HIGH} F10:1 Ip A1:1 C420jpeg\n".encode())
        for _ in range(3):
            out.write(b"FRAME\n" + planes)


@pytest.fixture(scope="module")
def _drawn_camera_browser(browser_type, tmp_path_factory):
    stream = tmp_path_factory.mktemp("fake_camera") / "drawn.y4m"
    _y4m(stream)
    browser = browser_type.launch(
        args=[
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
            f"--use-file-for-fake-video-capture={stream}",
        ]
    )
    yield browser
    browser.close()


@pytest.fixture
def page(_drawn_camera_browser, base_url):
    """A page whose camera sees the drawing, allowed, in a context of its own."""
    context = _drawn_camera_browser.new_context(
        viewport={"width": 1280, "height": 800}, base_url=base_url
    )
    context.grant_permissions(["camera"], origin=base_url)
    yield context.new_page()
    context.close()


def _open_garage(page, base_url: str) -> None:
    page.goto(f"{base_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    page.evaluate("() => localStorage.removeItem('apothecary.panels')")
    settled(page)


def _ring_on(page, path: str) -> None:
    """The node ring on a piece, as a right-click on its row in Contents opens it."""
    page.locator(f"#contents-list .contents-item[data-path='{path}']").click(button="right")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)


def _canvas_ring(page) -> None:
    """The canvas ring, from the key, with nothing selected."""
    page.evaluate(
        "() => { document.activeElement && document.activeElement.blur(); "
        "const v = window.fractalViewer; v.selectedName = null; v.renderSelectedPanel(); }"
    )
    page.keyboard.press("m")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)


def _wedges(page) -> dict:
    return page.evaluate(WEDGES)


def _press(page, *labels: str) -> str:
    """Press the wedges these labels name, ring after ring; the address pressed."""
    address = ""
    for label in labels:
        page.wait_for_function(
            f"() => [...document.querySelectorAll('#ring-overlay .wedge')]"
            f".some((w) => w.getAttribute('aria-label') === {label!r})",
            timeout=5000,
        )
        cell = next(c for c, got in _wedges(page).items() if got == label)
        page.keyboard.press(cell)
        address += cell
    return address


PLACEMENT = "86249317"  # the order a ring seats its options in (apothecary/menu.py)


def _labels(page) -> list:
    """The open ring's labels, in the order its options were given."""
    wedges = _wedges(page)
    return [wedges[cell] for cell in PLACEMENT if cell in wedges]


def _close_ring(page) -> None:
    page.keyboard.press("Escape")
    expect(page.locator("#ring-overlay")).to_be_hidden(timeout=3000)


def _drawn(page, host: str):
    return next((entry for entry in page.evaluate(STATE) if entry["host"] == host), None)


def _status(page):
    return page.locator("#status")


def _said(page, text: str) -> None:
    expect(_status(page)).to_contain_text(text, timeout=20000)
    expect(_status(page)).not_to_have_class(re.compile(r"\berror\b"))


def _pin_the_camera(page, *path: str) -> str:
    """Camera › Pin here › this browser's camera, from a ring already open; its label."""
    _press(page, *path, "Camera", "Pin here")
    label = _labels(page)[0]
    _press(page, label)
    return label


def _attached(page, base_url: str) -> dict:
    return page.request.get(f"{base_url}/sites/garage/attached").json()


@pytest.mark.e2e
def test_take_picture_pins_a_view_and_find_shapes_is_its_own_step(
    page,
    base_url: str,
    leaves_garage_as_found,  # noqa: F811
):
    """The plain pin names Take picture; Take picture keeps a frame and pins it at the
    bench as a view with no shapes, and names Find shapes; Find shapes finds them and
    names Make. The camera's ring holds no Keep."""
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _open_garage(page, base_url)

    _ring_on(page, "workbench")
    label = _pin_the_camera(page)
    _said(page, f"{label} pinned at workbench: Camera › Take picture")

    _ring_on(page, "workbench")
    _press(page, "Camera")
    assert _labels(page) == ["Pin here", "Live", "Take picture", "Unpin"]
    _press(page, "Take picture")
    _said(page, "pinned at workbench as a view: Picture › Find shapes")
    (view,) = _attached(page, base_url)["views"]
    assert view["shapes"] == [] and view["finder"] is None and view["found_at"] is None
    assert view["picture"].startswith("captures/")
    page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === 'workbench' && e.mat)",
        timeout=10000,
    )
    assert _drawn(page, "workbench")["outlines"] == []
    badge = page.locator(".world-badge.place-mark[data-host='workbench']")
    expect(badge).to_contain_text("Find shapes next")

    # No Make before shapes are found; Find shapes is the step that finds them.
    _ring_on(page, "workbench")
    _press(page, "Picture")
    labels = _labels(page)
    assert "Make" not in labels and labels[-1] == "Find shapes", labels
    _press(page, "Find shapes")
    _said(page, "found at workbench")
    expect(_status(page)).to_contain_text("Picture › Make")
    page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === 'workbench' && e.outlines.length)",
        timeout=10000,
    )
    (found,) = _attached(page, base_url)["views"]
    assert found["id"] == view["id"] and found["finder"] == "plain" and found["shapes"]
    expect(badge).to_contain_text(f"view: {len(found['shapes'])} shape")

    # Found by the one finder there is: Find shapes has nothing more to do.
    _ring_on(page, "workbench")
    _press(page, "Picture")
    assert "Find shapes" not in _labels(page)
    _close_ring(page)
    assert errors == []


@pytest.mark.e2e
def test_the_loop_at_the_bench_from_the_ring(page, base_url: str, leaves_garage_as_found):  # noqa: F811
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _open_garage(page, base_url)
    url = page.url

    # Pinned at the bench: its badge and a frustum looking down onto it.
    _ring_on(page, "workbench")
    assert _labels(page)[-2:] == ["Camera", "Picture"]  # the bench is no part: no Part
    label = _pin_the_camera(page)
    _said(page, f"{label} pinned at workbench")
    expect(page.locator(".world-badge.place-mark[data-host='workbench'].has-camera")).to_be_visible(
        timeout=5000
    )
    assert _drawn(page, "workbench")["frustum"] is not None
    cameras = page.request.get(f"{base_url}/cameras?site=garage").json()
    assert [c["path"] for c in cameras] == ["workbench"]

    # This browser's camera: Live, Take picture and Unpin beside Pin here.
    _ring_on(page, "workbench")
    _press(page, "Camera")
    assert _labels(page) == ["Pin here", "Live", "Take picture", "Unpin"]
    # Take picture, from Still: the frame is kept with its camera and host and
    # pinned; Find shapes finds what is in it.
    _press(page, "Take picture")
    _said(page, "pinned at workbench as a view")
    _ring_on(page, "workbench")
    _press(page, "Picture", "Find shapes")
    _said(page, "found at workbench")
    page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === 'workbench' && e.outlines.length)",
        timeout=10000,
    )
    first = _attached(page, base_url)["views"]
    assert len(first) == 1 and first[0]["camera"] == cameras[0]["id"]
    assert first[0]["picture"].startswith("captures/") and first[0]["shapes"]

    # Live puts the video on the mat and hides the outlines; Take picture ends it.
    _ring_on(page, "workbench")
    _press(page, "Camera", "Live")
    page.wait_for_function(
        "() => window.apothecaryPictureVerbs.live() === 'workbench'"
        " && window.apothecaryPictures.state().find((e) => e.host === 'workbench').live",
        timeout=8000,
    )
    assert _drawn(page, "workbench")["outlines"] == []
    _ring_on(page, "workbench")
    _press(page, "Camera")
    assert "Still" in _labels(page)
    _press(page, "Take picture")
    page.wait_for_function(
        "(first) => window.apothecaryPictureVerbs.live() === null"
        " && window.apothecaryPictures.state().some((e) => e.host === 'workbench'"
        " && e.view && e.view !== first)",
        arg=first[0]["id"],
        timeout=10000,
    )
    _ring_on(page, "workbench")
    _press(page, "Picture", "Find shapes")
    page.wait_for_function(
        "(first) => window.apothecaryPictures.state().some((e) => e.host === 'workbench'"
        " && e.view !== first && e.outlines.length)",
        arg=first[0]["id"],
        timeout=10000,
    )
    views = _attached(page, base_url)["views"]
    assert len(views) == 2
    view = views[-1]
    assert _drawn(page, "workbench")["view"] == view["id"]

    # Unsized, the host's Picture offers no Make; Selected's width box sizes it.
    _ring_on(page, "workbench")
    _press(page, "Picture")
    assert "Make" not in _labels(page) and {"Views", "Size", "Unpin", "Forget"} <= set(
        _labels(page)
    )
    _press(page, "Size")
    box = page.locator("#selected-body .view-width")
    expect(box).to_be_focused(timeout=3000)
    box.fill("800")
    box.press("Tab")
    _said(page, "800 mm across")
    view = _attached(page, base_url)["views"][-1]
    assert view["mm_across"] == 800

    # Picture › Make › a shape: the piece stands on its outline.
    _ring_on(page, "workbench")
    _press(page, "Picture", "Make")
    shapes = _labels(page)
    assert shapes[0] == "Make all" and len(shapes) >= 2
    _press(page, shapes[1])
    page.wait_for_function(
        "() => Object.keys(window.apothecaryPictures.attached().made || {}).length === 1",
        timeout=10000,
    )
    attached = _attached(page, base_url)
    ((piece, record),) = attached["made"].items()
    _said(page, f"made {piece}")
    shape = next(s for s in attached["views"][-1]["shapes"] if s["index"] == record["shape_index"])
    assert shape["status"] == "made"
    mat = attached["views"][-1]["mat"]
    cx = (shape["min"][0] + shape["max"][0]) / 2
    cy = (shape["min"][1] + shape["max"][1]) / 2
    want = (
        mat["centre"][0] + (cx - 0.5) * mat["width"],
        mat["centre"][1] + (0.5 - cy) * mat["depth"],
    )
    tree = page.evaluate(f"() => window.fractalViewer.nodeByPath({piece!r}).world_bounds")
    got = ((tree["min"][0] + tree["max"][0]) / 2, (tree["min"][1] + tree["max"][1]) / 2)
    assert abs(got[0] - want[0]) < 1 and abs(got[1] - want[1]) < 1, (got, want)
    assert tree["min"][2] == pytest.approx(mat["centre"][2], abs=1)  # on the bench's top
    expect(page.locator(f"#contents-list .contents-item[data-path='{piece}']")).to_be_visible()

    # Why this, from the piece: its view drawn, its outline lit, a thread to it; the
    # selection stays on the piece.
    _ring_on(page, piece)
    labels = _labels(page)
    assert "Camera" not in labels and labels[-2:] == ["Picture", "Part"]
    _press(page, "Why this")
    _said(page, f"made from shape {record['shape_index']}")
    traced = page.evaluate("() => window.apothecaryPictures.traced()")
    assert traced["piece"] == piece and traced["index"] == record["shape_index"]
    assert traced["shown"] is True and traced["visible"] is True
    assert page.evaluate("() => window.fractalViewer.selectedName") == piece

    # Drop, from the piece's Picture: it goes, and its shape reads as found again.
    _ring_on(page, piece)
    _press(page, "Picture")
    assert _labels(page) == ["Word", "Drop"]
    _press(page, "Drop")
    page.wait_for_function(
        "() => Object.keys(window.apothecaryPictures.attached().made || {}).length === 0",
        timeout=10000,
    )
    expect(page.locator(f"#contents-list .contents-item[data-path='{piece}']")).to_have_count(0)
    shapes = _attached(page, base_url)["views"][-1]["shapes"]
    assert all(s["status"] == "found" for s in shapes)

    # Forget: the kept frame goes, its view with it.
    _ring_on(page, "workbench")
    _press(page, "Picture", "Forget")
    _said(page, f"forgot {view['picture']}")
    kept = {p["path"] for p in page.request.get(f"{base_url}/photos/pictures").json()}
    assert view["picture"] not in kept
    assert view["id"] not in {vw["id"] for vw in _attached(page, base_url)["views"]}
    assert page.url == url  # nothing switched the site
    assert errors == []


@pytest.mark.e2e
def test_the_floor_from_the_canvas_ring(page, base_url: str, leaves_garage_as_found):  # noqa: F811
    """Pictures › Floor on the canvas ring, with nothing pinned there: the fake camera
    pinned at the floor, a picture taken, its shapes found, the floor's mat drawn
    beside the site, sized, and a shape made there."""
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _open_garage(page, base_url)

    _canvas_ring(page)
    _press(page, "Pictures", "Floor")
    assert _labels(page)[:2] == ["Fit", "Camera"]
    _pin_the_camera(page)
    _said(page, "pinned at the floor")
    assert page.evaluate("() => window.fractalViewer.selectedName") == "@floor"
    expect(page.locator(".world-badge.place-mark[data-host=''].has-camera")).to_be_visible(
        timeout=5000
    )

    _canvas_ring(page)
    _press(page, "Pictures", "Floor", "Camera", "Take picture")
    _said(page, "pinned at the floor as a view: Pictures › Floor › Picture › Find shapes")
    _canvas_ring(page)
    _press(page, "Pictures", "Floor", "Picture", "Find shapes")
    _said(page, "found at the floor")
    page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === '' && e.outlines.length)",
        timeout=10000,
    )
    assert page.evaluate("() => window.fractalViewer.selectedName") == "@floor"
    box = page.locator("#selected-body .view-width")
    box.fill("400")
    box.press("Tab")
    _said(page, "400 mm across")

    _canvas_ring(page)
    _press(page, "Pictures", "Floor", "Picture", "Make", "Make all")
    page.wait_for_function(
        "() => Object.keys(window.apothecaryPictures.attached().made || {}).length > 0",
        timeout=10000,
    )
    made = _attached(page, base_url)["made"]
    assert made and all(record["host"] == "" for record in made.values())
    _said(page, "piece(s)")
    assert errors == []


@pytest.mark.e2e
def test_a_dropped_file_is_pinned_where_it_lands(
    page,
    base_url: str,
    tmp_path,
    leaves_garage_as_found,  # noqa: F811
):
    """Dropped on a child while zoomed in, one file is pinned at its root and the view
    steps out; two dropped at once are two views, the last drawn; on empty canvas, the
    floor; a view's row in the pins list unpins it."""
    _drawing().save(tmp_path / "bench_drop.png")
    data = (tmp_path / "bench_drop.png").read_bytes()
    _open_garage(page, base_url)

    drop = """async ([x, y, names, bytes]) => {
        const dt = new DataTransfer();
        const raw = Uint8Array.from(atob(bytes), (c) => c.charCodeAt(0));
        for (const name of names) dt.items.add(new File([raw], name, { type: 'image/png' }));
        const canvas = window.fractalViewer.canvas;
        canvas.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, clientX: x, clientY: y, bubbles: true, cancelable: true }));
    }"""
    import base64

    encoded = base64.b64encode(data).decode()

    # Zoomed into the bench, onto one of its children: pinned at the bench, stepped out.
    page.evaluate("() => window.fractalViewer.zoomIn('workbench')")
    settled(page)
    child = page.evaluate(
        """() => {
            const v = window.fractalViewer;
            const r = v.canvas.getBoundingClientRect();
            // A frame is mostly air: look for a point that lands on one of its bars.
            for (let fy = 0.1; fy < 0.95; fy += 0.04) for (let fx = 0.1; fx < 0.95; fx += 0.04) {
                const at = { clientX: r.left + fx * r.width, clientY: r.top + fy * r.height };
                const hit = v.raycastPick(at);
                if (hit && hit.key) return { x: at.clientX, y: at.clientY, key: hit.key };
            }
            return null;
        }"""
    )
    assert child and child["key"].startswith("workbench."), child
    assert page.evaluate("() => window.fractalViewer.focusPath.length") == 1
    page.evaluate(drop, [child["x"], child["y"], ["bench_drop.png"], encoded])
    _said(page, "1 picture(s) pinned at workbench")
    assert page.evaluate("() => window.fractalViewer.focusPath.length") == 0
    views = _attached(page, base_url)["views"]
    assert [vw["host"] for vw in views] == ["workbench"]
    assert views[0]["picture"].startswith("uploads/bench_drop")

    # Two at once, on the bench's mat: two views, the last one drawn. The first
    # drop stepped the view out of the bench; measure only once it has stopped.
    page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === 'workbench' && e.mat)"
    )
    settled(page)
    # Measured and dropped in one call, so no mesh can arrive between the two.
    dropped = page.evaluate(
        """([names, bytes]) => {
            const v = window.fractalViewer;
            const view = window.apothecaryPictures.drawnAt('workbench');
            const r = v.canvas.getBoundingClientRect();
            // A point of the mat the page itself picks as the bench: whichever
            // corner is clear of the printers standing on it at this viewport.
            let at = null;
            for (let fy = 0.025; fy < 1 && !at; fy += 0.05) for (let fx = 0.025; fx < 1 && !at; fx += 0.05) {
                const p = window.apothecaryPictures.scenePoint(view.id, fx, fy);
                p.project(v.camera);
                // Whole pixels, as the page's drop event carries them, and clear of
                // the bench's edges: the pixels beside it must be the bench too.
                const x = Math.round(r.left + (p.x + 1) / 2 * r.width);
                const y = Math.round(r.top + (1 - p.y) / 2 * r.height);
                const bench = (dx, dy) => {
                    const hit = v.raycastPick({ clientX: x + dx, clientY: y + dy });
                    return (hit && (hit.pick ? hit.pick.host : hit.key)) === 'workbench';
                };
                if ([[0, 0], [-1, 0], [1, 0], [0, -1], [0, 1]].every(([dx, dy]) => bench(dx, dy))) at = { clientX: x, clientY: y };
            }
            if (!at) return false;
            const dt = new DataTransfer();
            const raw = Uint8Array.from(atob(bytes), (c) => c.charCodeAt(0));
            for (const name of names) dt.items.add(new File([raw], name, { type: 'image/png' }));
            v.canvas.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, clientX: at.clientX, clientY: at.clientY, bubbles: true, cancelable: true }));
            return true;
        }""",
        [["one.png", "two.png"], encoded],
    )
    assert dropped, "no point of the bench's mat is picked as the bench"
    _said(page, "2 picture(s) pinned at workbench")
    views = [vw for vw in _attached(page, base_url)["views"] if vw["host"] == "workbench"]
    assert len(views) == 3
    assert _drawn(page, "workbench")["view"] == views[-1]["id"]
    assert views[-1]["picture"].startswith("uploads/two")

    # On empty canvas, where nothing is under the pointer: the floor.
    empty = page.evaluate(
        """() => {
            const v = window.fractalViewer;
            const r = v.canvas.getBoundingClientRect();
            for (let fy = 0.05; fy < 1; fy += 0.1) for (let fx = 0.02; fx < 1; fx += 0.08) {
                const at = { clientX: r.left + fx * r.width, clientY: r.top + fy * r.height };
                if (!v.raycastPick(at)) return { x: at.clientX, y: at.clientY };
            }
            return null;
        }"""
    )
    assert empty, "nowhere on the canvas is empty"
    page.evaluate(drop, [empty["x"], empty["y"], ["floor.png"], encoded])
    _said(page, "1 picture(s) pinned at the floor")
    assert [vw["host"] for vw in _attached(page, base_url)["views"]].count("") == 1

    # A view's row in Kept unpins it.
    page.evaluate("() => window.apothecaryPanels.open('kept')")
    panel = page.locator(".panel[data-panel='kept']")
    row = panel.locator(f".kept-row.view:has(.kept-view-unpin[data-id='{views[0]['id']}'])")
    expect(row).to_be_visible(timeout=5000)
    row.locator(".kept-view-unpin").click()
    expect(row).to_have_count(0, timeout=5000)
    assert views[0]["id"] not in {vw["id"] for vw in _attached(page, base_url)["views"]}
