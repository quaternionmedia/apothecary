"""Paths a person takes: the bare /viewer address the README and `apothecary serve`
print, and a made piece's Print cell.

The Print cell's server is this module's own: the simulated printer, idle, identified
and pinned to printer_1's mainboard as the bench's real board is, and a picture folder
holding only the stated picture (tests/views_helpers.py), so its piece is made
through the API and no camera is opened. No real serial port is opened.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import httpx
import pytest
import windows
from boards import BOARD, PRINTER
from garage import NAME
from garage import open_garage as _open_garage
from garage import picture as _picture
from garage import pin as _pin
from garage import said as _said
from playwright.sync_api import expect
from rings import labels as _labels
from rings import open_on_row as _ring_on
from rings import press as _press
from views_helpers import HIGH, SHAPES, WIDE

MACHINE = windows.MACHINE


@pytest.mark.e2e
def test_the_bare_viewer_address_opens_the_first_site(page, base_url: str):
    """`/viewer`, as `apothecary serve` prints it: the first site, drawn, and nothing
    thrown on the way."""
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{base_url}/viewer")
    expect(page).to_have_url(re.compile(r"/viewer/sites/[a-z_]+$"))
    expect(page.locator(".toolbar h1")).to_contain_text("Apothecary")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    page.evaluate("() => window.fractalViewer.waveDone")
    site = page.url.rsplit("/", 1)[1]
    assert site in page.request.get(f"{base_url}/sites").json()
    assert errors == []


@pytest.fixture(scope="module")
def bench(base_url, start_server, tmp_path_factory):
    """This module's own server: the idle simulated printer pinned to printer_1's
    mainboard, and the stated picture in its folder. ``base_url`` is asked for only so
    that with no server to run against this is skipped, as every browser test is."""
    import json

    folder = tmp_path_factory.mktemp("print_cell_pictures")
    (folder / f"{NAME}.png").write_bytes(_picture())
    (folder / f"{NAME}.shapes.json").write_text(
        json.dumps({"name": NAME, "pixel_width": WIDE, "pixel_height": HIGH, "shapes": SHAPES}),
        encoding="utf-8",
    )
    url = start_server(
        {"APOTHECARY_SIMULATED_PRINTER": "idle", "APOTHECARY_PICTURE_ROOT": str(folder)}
    )
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()
        http.put(
            f"/sites/garage/nodes/{BOARD}/device", json={"identity": PRINTER}
        ).raise_for_status()
    return SimpleNamespace(url=url, picture=f"{NAME}.png")


@pytest.mark.e2e
def test_a_made_piece_s_print_cell_opens_its_printer_s_machine_with_it_chosen(page, bench):
    """A made piece's ring, Print: printer_1's Machine, a tab beside Pictures, with the
    piece chosen under Print from here's makes, and the status line naming the next step."""
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    view = _pin(page, bench.url, "workbench", bench.picture, mm_across=1800)
    made = page.request.post(f"{bench.url}/sites/garage/views/{view['id']}/make", data={"shape": 1})
    assert made.status == 200, made.text()
    piece = made.json()["made"][0]
    _open_garage(page, bench.url)

    _ring_on(page, piece)
    assert "Print" in _labels(page), _labels(page)
    _press(page, "Print")
    _said(
        page, f"printer_1's Machine makes {piece}: choose its file in Print from here, then ▶ Print"
    )
    machine = windows.machine(page)
    expect(page.locator(MACHINE)).to_be_visible(timeout=5000)
    # Its tab names the printer; its whole title, the tab's tooltip, the port too.
    expect(windows.tab(page, "machine").locator(".lm_title")).to_have_text("printer_1")
    expect(windows.tab(page, "machine")).to_have_attribute("title", f"printer_1 · {PRINTER}")
    expect(machine.locator("#print-part")).to_have_value(piece, timeout=10000)
    assert errors == []
