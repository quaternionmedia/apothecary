"""Site garage as a browser test meets it: the viewer opened on it, a row of Site's
tree selected, the status line and what it says, what is attached there, a picture
pinned at a place, the drawing a fake camera plays, and the loop's steps on the
bench's ring (find its shapes, make one a piece, the slice kept of it). Every
browser test reaches these through here, so a change to how the page opens or
speaks is made once; a test file defines none of its own (tests/test_e2e_helpers.py
holds that).

The stated picture is tests/views_helpers.py's, the one the unit tests pin: 1000 by
500 pixels, its three shapes stated. The fixtures that pin it and that take back
what a test added to garage are tests/e2e/conftest.py's."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.sync_api import Page, expect
from rings import labels, on_row, press
from rings import open_on_row as ring_on
from viewer_ready import settled
from views_helpers import png

# How long the page may take to show its rows, or to say something.
SAID_MS = 20000
# The stated picture's name in the picture folder.
NAME = "world_bench"
# Every place's drawn pictures: one entry per host, its views and its mat.
STATE = "() => window.apothecaryPictures.state()"


def open_garage(page: Page, url: str, *, settle: bool = True) -> None:
    """The viewer on site garage, its rows shown; settled, as a picture of it wants,
    unless ``settle`` is false."""
    page.goto(f"{url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=SAID_MS)
    if settle:
        settled(page)


def row(page: Page, path: str):
    """A piece's row in Site's tree."""
    return page.locator(f"#contents-list .contents-item[data-path='{path}']")


def select(page: Page, path: str) -> None:
    """A piece selected by a click on its row, and the page holding it selected."""
    row(page, path).click()
    page.wait_for_function("(p) => window.fractalViewer.selectedName === p", arg=path)


def status(page: Page):
    """The status line."""
    return page.locator("#status")


def said(page: Page, text: str, timeout: int = SAID_MS) -> None:
    """The status line says ``text``, and not as an error."""
    expect(status(page)).to_contain_text(text, timeout=timeout)
    expect(status(page)).not_to_have_class(re.compile(r"\berror\b"))


def attached(page: Page, url: str) -> dict:
    """What is attached to garage: its views, cameras and made pieces."""
    return page.request.get(f"{url}/sites/garage/attached").json()


def drawn(page: Page, host: str):
    """The pictures drawn at a host, as the page holds them; None where none is."""
    return next((entry for entry in page.evaluate(STATE) if entry["host"] == host), None)


def picture(pen_shapes: bool = True) -> bytes:
    """The stated picture as a PNG: its rectangle and triangle drawn, or a blank ground."""
    return png(shapes="rt" if pen_shapes else "")


def pin(page: Page, url: str, host: str, name: str, mm_across: float | None = None) -> dict:
    """A picture pinned as a view at a host, and its shapes found by the stated finder."""
    body = {"host": host, "picture": name}
    if mm_across:
        body["mm_across"] = mm_across
    answer = page.request.post(f"{url}/sites/garage/views", data=body)
    assert answer.status == 201, answer.text()
    found = page.request.post(
        f"{url}/sites/garage/views/{answer.json()['id']}/find", data={"finder": "stated"}
    )
    assert found.status == 200, found.text()
    return found.json()


# The drawing Chromium's fake camera plays: a dark rectangle, disc and triangle on a
# light ground, so the plain finder has shapes to find in every frame.
DRAWING_WIDE, DRAWING_HIGH = 640, 480
# Where the camera reads it (tests/e2e/conftest.py's drawing_camera_browser). Chromium
# names a fake camera by the file it plays, and the page shows that name (the status
# line, the camera's card): a path that is the same on every run keeps a walkthrough
# the same when nothing else changed.
DRAWING = Path(tempfile.gettempdir()) / "apothecary-e2e" / "three-shapes.y4m"


def drawing() -> Image.Image:
    img = Image.new("L", (DRAWING_WIDE, DRAWING_HIGH), 245)
    pen = ImageDraw.Draw(img)
    pen.rectangle((40, 40, 260, 160), fill=30)
    pen.ellipse((360, 60, 520, 220), fill=20)
    pen.polygon([(80, 420), (300, 420), (190, 280)], fill=25)
    return img


def y4m(path) -> None:
    """The drawing as a Y4M stream Chromium's fake camera plays in a loop."""
    ycbcr = drawing().convert("RGB").convert("YCbCr")
    y, cb, cr = ycbcr.split()
    half = (DRAWING_WIDE // 2, DRAWING_HIGH // 2)
    planes = y.tobytes() + cb.resize(half).tobytes() + cr.resize(half).tobytes()
    with open(path, "wb") as out:
        out.write(f"YUV4MPEG2 W{DRAWING_WIDE} H{DRAWING_HIGH} F10:1 Ip A1:1 C420jpeg\n".encode())
        for _ in range(3):
            out.write(b"FRAME\n" + planes)


# Where a point of the selected camera's handles is on the screen: on its turn
# ring where a turn of `deg` puts the picture's top, or on its tilt arc at a tilt
# of `deg` (the handles are drawn about the lens, in the site's frame turned to
# three.js's, y up).
HANDLE_AT = """([kind, deg]) => {
    const v = window.fractalViewer, g = v.cameraHandles;
    const cam = window.apothecaryPictures.camera(g.userData.camera);
    const t = cam.turn * Math.PI / 180, a = deg * Math.PI / 180;
    let x, y, z;
    if (kind === 'turn') { const r = g.userData.turnRadius; x = -Math.sin(a) * r; y = Math.cos(a) * r; z = 0; }
    else { const r = g.userData.tiltRadius; x = -Math.sin(t) * Math.sin(a) * r; y = Math.cos(t) * Math.sin(a) * r; z = -Math.cos(a) * r; }
    const p = g.localToWorld(v.sceneAt(x, y, z)).project(v.camera);
    const box = v.canvas.getBoundingClientRect();
    return [box.left + (p.x + 1) / 2 * box.width, box.top + (1 - p.y) / 2 * box.height];
}"""


def drag_handle(page: Page, kind: str, degrees: list) -> None:
    """The selected camera's turn ring (``kind`` "turn") or tilt arc ("tilt"): pressed
    at the first of ``degrees``, moved through the rest, let go."""
    points = [page.evaluate(HANDLE_AT, [kind, d]) for d in degrees]
    page.mouse.move(*points[0])
    page.mouse.down()
    for point in points[1:]:
        page.mouse.move(*point, steps=3)
    page.mouse.up()


def found(page: Page, host: str = "workbench") -> None:
    """Picture › Find shapes on a place's ring; its outlines drawn."""
    ring_on(page, host)
    press(page, "Picture")
    assert labels(page)[-1] == "Find shapes", labels(page)
    press(page, "Find shapes")
    said(page, f"found at {host}")


def make(page: Page, url: str, word: str) -> str:
    """Picture › Make on the bench's ring, the found shape whose label starts with
    ``word``; the piece it made, as Site lists it."""
    before = set(attached(page, url)["made"])
    on_row(page, "workbench", "Picture", "Make")
    held = labels(page)
    assert held[0] == "Make all", held
    label = next((got for got in held[1:] if got.startswith(word)), held[1])
    press(page, label)
    page.wait_for_function(
        "(n) => Object.keys(window.apothecaryPictures.attached().made || {}).length === n",
        arg=len(before) + 1,
        timeout=10000,
    )
    (piece,) = set(attached(page, url)["made"]) - before
    expect(row(page, piece)).to_be_visible(timeout=10000)
    # Make selects the piece it made, as Add here selects the camera it added.
    page.wait_for_function("(p) => window.fractalViewer.selectedName === p", arg=piece)
    return piece


def kept(page: Page, url: str, piece: str) -> dict:
    """The newest slice of ``piece`` (GET /slicer/slices) and the file it kept, as the
    Print card lists it: its id, its name and the lines a print of it streams."""
    record = next(
        r for r in page.request.get(f"{url}/slicer/slices").json() if r["made"]["name"] == piece
    )
    (file,) = [
        f
        for f in page.request.get(f"{url}/firmware/printers/prints").json()
        if f["id"] == record["file_id"]
    ]
    return {"record": record, **file}
