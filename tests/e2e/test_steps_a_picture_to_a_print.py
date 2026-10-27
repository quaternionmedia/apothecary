"""A picture to a print, a step at a time, from the bench's ring with no camera: Picture ›
Add with examples/pictures/shapes.png, Find shapes, Size it 300 mm across, Make the disc, Slice it
for printer_1, and Send file to print it.

Each step first checks that the page is where the step before it leaves it, then acts as
a person does and holds what the page says and draws. Under ``--steps`` every step runs in
order, on a server of the test's own (the simulated printer on ``/dev/ttyFAKE1`` pinned
to printer_1's mainboard, the scripted OrcaSlicer) in its own browser, so nothing it adds
outlives it.

Given ``--step N`` and ``--base-url`` naming the demo, only step N runs, on the demo's
walk tab, and the tab is left there (tests/e2e/stepping.py); its picture is
``.cache/walk/picture-to-print-step-N.png``::

    uv run pytest tests/e2e/test_steps_a_picture_to_a_print.py --base-url http://127.0.0.1:6283 --step 1
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import httpx
import pytest
import windows
from boards import BOARD, DWELL, LAYERS, PRINTER
from garage import attached as _attached
from garage import make as _make
from garage import said as _said
from garage import status as _status
from playwright.sync_api import Page, expect
from rings import labels as _labels
from rings import open_on_row as _ring_on
from rings import press as _press
from slicer_helpers import write_fake_orcaslicer
from stepping import ROOT, chosen, where
from viewer_ready import by_hand, settled

SHAPES_PNG = ROOT / "examples" / "pictures" / "shapes.png"
WIDTH_MM = 300  # shapes.png across, as the README's photo example has it


@dataclass
class Walk:
    """The page a step acts on, the server it is on, and whether it is the demo's tab,
    whose panels a person has laid out (left as they are)."""

    page: Page
    base: str
    on_the_demo: bool

    def view(self) -> Optional[dict]:
        """The newest view at the bench, as the server has it."""
        views = [v for v in _attached(self.page, self.base)["views"] if v["host"] == "workbench"]
        return views[-1] if views else None

    def piece(self) -> Optional[str]:
        """The piece made from that view."""
        view = self.view()
        return next(iter(view["made"].values()), None) if view else None


def add(w: Walk) -> None:
    """The bench's ring, Picture › Add, examples/pictures/shapes.png: pinned there as a view, laid
    clear of what rests on the bench, nothing found in it yet; the view brought to the
    bench by hand, to look at it."""
    w.page.goto(f"{w.base}/viewer/sites/garage")
    expect(w.page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    if not w.on_the_demo:
        w.page.evaluate("() => localStorage.removeItem('apothecary.panels')")
    w.page.evaluate("() => window.fractalViewer.waveDone")
    settled(w.page)
    _ring_on(w.page, "workbench")
    _press(w.page, "Picture")
    with w.page.expect_file_chooser() as chosen:
        _press(w.page, "Add")
    chosen.value.set_files(str(SHAPES_PNG))
    _said(w.page, "1 picture(s) pinned at workbench as views")
    w.page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === 'workbench' && e.mat)",
        timeout=20000,
    )
    view = w.view()
    assert view["finder"] is None and view["mat"]["width"] is None, view
    x, half = view["mat"]["centre"][0], view["mat"]["fit_width"] / 2
    roots = {
        s["name"]: s for s in w.page.request.get(f"{w.base}/sites/garage").json()["structures"]
    }
    printer = roots["printer_1"]["world_bounds"]
    assert printer["max"][0] <= x - half, (view["mat"], printer)
    by_hand(w.page, "workbench", distance=2600)


def find(w: Walk) -> None:
    """Picture › Find shapes: shapes.png's three shapes found and outlined, and the status
    line asking for the picture's width before Make."""
    view = w.view()
    where(
        "Find shapes",
        "a picture pinned at the bench, not yet searched",
        bool(view) and view["finder"] is None,
    )
    _ring_on(w.page, "workbench")
    _press(w.page, "Picture", "Find shapes")
    _said(w.page, "3 shapes found at workbench")
    expect(_status(w.page)).to_contain_text("Picture › Size")
    w.page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === 'workbench' && e.outlines.length === 3)",
        timeout=20000,
    )
    assert len(w.view()["shapes"]) == 3


def size(w: Walk) -> None:
    """Picture › Size, 300 mm typed in Selected: the picture sized, and nothing of it over
    what rests on the bench."""
    view = w.view()
    where(
        "Size",
        "shapes found in the bench's picture, no width given",
        bool(view) and view["finder"] is not None and view["mat"]["width"] is None,
    )
    _ring_on(w.page, "workbench")
    _press(w.page, "Picture", "Size")
    box = w.page.locator("#selected-body .view-width")
    expect(box).to_be_focused(timeout=3000)
    box.fill(str(WIDTH_MM))
    box.press("Tab")
    _said(w.page, f"{WIDTH_MM} mm across")
    sized = w.view()
    assert sized["mat"]["width"] == WIDTH_MM
    assert [shape["overlaps"] for shape in sized["shapes"]] == [[], [], []], sized["shapes"]


def make(w: Walk) -> None:
    """Picture › Make, the disc: a piece standing on its outline, selected."""
    view = w.view()
    where(
        "Make",
        "the bench's picture sized, nothing made from it",
        bool(view) and view["mat"]["width"] is not None and not view["made"],
    )
    piece = _make(w.page, w.base, "disc")
    _said(w.page, f"made {piece}")


def slice_(w: Walk) -> None:
    """Slice, on the piece's ring: printer_1's Machine slices it, and its G-code is chosen there."""
    piece = w.piece()
    where("Slice", "a piece made from the bench's picture", piece is not None)
    _ring_on(w.page, piece)
    _press(w.page, "Slice")
    _said(w.page, f"Slice: slicing {piece} for printer_1")
    machine = windows.machine(w.page)
    expect(machine.locator("#print-slice-said")).to_contain_text(
        f"{piece} sliced for printer_1 by OrcaSlicer", timeout=300000
    )
    _said(w.page, f"{piece}.gcode kept and chosen")


def print_(w: Walk) -> None:
    """Send file, from printer_1's ring: the piece's G-code printed to its end."""
    piece, machine = w.piece(), windows.machine(w.page)
    chosen = machine.locator("#print-pick option:checked")
    where(
        "Print",
        "the piece's G-code chosen in printer_1's Machine",
        piece is not None and chosen.count() == 1 and f"{piece}.gcode" in chosen.inner_text(),
    )
    _ring_on(w.page, "printer_1")
    _press(w.page, "Device", "Control")
    if "Arm" in _labels(w.page):  # the latch lapses after minutes without a control
        _press(w.page, "Arm")
        expect(w.page.locator("#control")).to_be_visible(timeout=5000)
        _ring_on(w.page, "printer_1")
        _press(w.page, "Device", "Control")
    asked: List[str] = []
    w.page.once("dialog", lambda d: (asked.append(d.message), d.accept()))
    _press(w.page, "Print", "Send file")
    progress = machine.locator("#print-progress")
    expect(progress).to_contain_text(f"{piece}.gcode · printing", timeout=10000)
    assert asked and f"making {piece}" in asked[0], asked
    expect(progress).to_contain_text(f"{piece}.gcode · done", timeout=600000)
    _said(w.page, "ended: done")


STEPS: List[Tuple[str, Callable[[Walk], None]]] = [
    ("Picture › Add", add),
    ("Picture › Find shapes", find),
    ("Picture › Size", size),
    ("Picture › Make", make),
    ("Slice", slice_),
    ("Print", print_),
]


@pytest.fixture
def steps(request, base_url):
    """One step on the demo's walk tab under --step; every step on a server of the
    test's own otherwise (stepping.chosen)."""

    def own():
        return request.getfixturevalue("page"), request.getfixturevalue("own_server")

    yield from chosen(request, base_url, "picture-to-print", STEPS, own)


@pytest.fixture
def own_server(start_server, tmp_path_factory):
    """The test's own server: the simulated printer idle on ``/dev/ttyFAKE1``,
    identified and pinned to printer_1's mainboard, and the scripted OrcaSlicer."""
    orca = write_fake_orcaslicer(tmp_path_factory.mktemp("orca"))
    url = start_server(
        {
            "APOTHECARY_SIMULATED_PRINTER": "idle",
            "APOTHECARY_ORCASLICER": str(orca),
            "FAKE_ORCA_LAYERS": LAYERS,
            "FAKE_ORCA_DWELL": DWELL,
        }
    )
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()
        http.put(
            f"/sites/garage/nodes/{BOARD}/device", json={"identity": PRINTER}
        ).raise_for_status()
    return url


@pytest.mark.e2e
def test_a_picture_to_a_print_a_step_at_a_time(steps):
    page, url, on_the_demo, numbers = steps
    walk = Walk(page, url, on_the_demo)
    for n in numbers:
        STEPS[n - 1][1](walk)
