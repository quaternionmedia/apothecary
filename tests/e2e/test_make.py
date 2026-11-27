"""Make: a part sent to a machine from wherever a person is looking at it.

A printer's Machine opens with its Print window in front, under it, and its makes
lists the site's pieces and then every part of the apothecary. The part selected, or
the part stepped into, has ⚒ Make in the header, naming the first of every site's
machines that make it -- one whose board is connected first, then this site's:
pressed, it opens that machine's Machine -- in another site, that site first --
chooses the part under makes and slices it there. Nothing is armed, started or sent.

Runs against a server of its own with nothing pinned but where a test pins the
simulated printer (idle on ``/dev/ttyFAKE1``) to printer_1's mainboard, and takes it
back; elsewhere printer_1 is opened as the garage plans it, not connected.
No real port is opened. The slicer is the scripted OrcaSlicer of the unit tests
(tests/slicer_helpers.py).
"""

from __future__ import annotations

import re

import httpx
import pytest
import rings
import windows
from boards import BOARD, PRINTER
from garage import open_garage, row, select, to_site
from playwright.sync_api import Page, expect
from slicer_helpers import write_fake_orcaslicer

SLICED_MS = 30000
# A piece drawn about the middle of the world: framed.
IN_THE_MIDDLE = """(key) => {
    const v = window.fractalViewer, node = v.renderNodeByKey[key];
    if (!node || !node.world_bounds) return false;
    const b = node.world_bounds;
    const s = v.sceneAt(...b.min.map((m, i) => (m + b.max[i]) / 2)).project(v.camera);
    return Math.abs(s.x) < 0.35 && Math.abs(s.y) < 0.35;
}"""


@pytest.fixture(scope="module")
def url(base_url, start_server, tmp_path_factory):
    """This module's own server, the scripted OrcaSlicer its slicer. ``base_url`` is
    asked for only so that with no server to run against this is skipped, as every
    browser test is."""
    orca = write_fake_orcaslicer(tmp_path_factory.mktemp("orca"))
    return start_server(
        {"APOTHECARY_ORCASLICER": str(orca), "APOTHECARY_SIMULATED_PRINTER": "idle"}
    )


def _machines_known(page: Page) -> None:
    page.wait_for_function(
        "() => window.fractalViewer.machinesHere.some((m) => m.path === 'printer_1')",
        timeout=15000,
    )


@pytest.mark.e2e
def test_a_printer_opens_with_its_print_window_and_makes_any_part(page: Page, url: str):
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    open_garage(page, url, settle=False)
    _machines_known(page)
    assert page.evaluate("() => window.fractalViewer.openMachine('printer_1')") is True
    expect(page.locator(f"{windows.MACHINE_ROOT}.kind-printer")).to_be_attached(timeout=15000)
    # Its Print, open and in front, in a stack of its own under the Machine, so the
    # Machine's head stays in view beside it.
    page.wait_for_function("() => window.apothecaryPanels.isShown('machine-print')", timeout=10000)
    assert page.evaluate("() => window.apothecaryPanels.isShown('machine')") is True
    # makes: the garage's pieces, then every part of the apothecary by its name.
    groups = windows.in_machine(page, "#print-part optgroup")
    expect(groups).to_have_count(2, timeout=10000)
    assert [groups.nth(i).get_attribute("label") for i in range(2)] == [
        "in garage",
        "every part of the apothecary",
    ]
    here = windows.in_machine(page, "#print-part optgroup[label='in garage'] option")
    every = windows.in_machine(page, "#print-part optgroup[label^='every'] option")
    assert "footpedal" in here.all_inner_texts()
    assert "calibration_cube" in every.all_inner_texts()
    assert "footpedal" not in every.all_inner_texts()
    # Closed, and the Machine opened again: its Print is back.
    windows.close(page, "machine-print")
    assert page.evaluate("() => window.fractalViewer.openMachine('printer_1')") is True
    page.wait_for_function("() => window.apothecaryPanels.isShown('machine-print')", timeout=10000)
    assert errors == []


@pytest.mark.e2e
def test_make_on_the_part_selected_slices_it_on_this_site_s_printer(page: Page, url: str):
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    open_garage(page, url, settle=False)
    _machines_known(page)
    make = page.locator("#make-here")
    expect(make).to_be_hidden()
    # A board is bought, not made: nothing to make.
    select(page, "esp32_blink")
    expect(make).to_be_hidden()
    # The garage's printer, planned, ahead of the universe's: the router does not cut
    # the footpedal.
    select(page, "footpedal")
    expect(make).to_have_text("⚒ Make footpedal on printer_1", timeout=15000)
    assert page.evaluate("() => window.fractalViewer.makeNow().then((d) => d.said)") == (
        "footpedal goes to printer_1: chosen in its Print window, sliced, then ▶ Print"
        " with control armed"
    )
    page.wait_for_function("() => window.apothecaryPanels.isShown('machine-print')", timeout=10000)
    expect(windows.in_machine(page, "#print-part")).to_have_value("footpedal")
    expect(page.locator("#status")).to_contain_text("kept and chosen", timeout=SLICED_MS)
    expect(windows.in_machine(page, "#print-pick")).to_have_value(re.compile("footpedal"))
    # Nothing armed: ▶ Print is the board's, and there is none.
    expect(windows.in_machine(page, "#print-start")).to_be_disabled()
    # The coupon says how it is cut: the router first.
    select(page, "router_coupon")
    expect(make).to_have_text("⚒ Make router_coupon on cnc_router", timeout=15000)
    assert errors == []


@pytest.mark.e2e
def test_the_file_chosen_follows_the_part_under_makes(page: Page, url: str):
    """calibration_cube sliced in printer_1's Print, then the hose adapter named under
    makes, none of which is kept: the cube's file gives way to none, which says Slice
    makes one, and is not left chosen for a part it does not make. The cube's file
    chosen again by a person stays chosen."""
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    open_garage(page, url, settle=False)
    _machines_known(page)
    assert page.evaluate("() => window.fractalViewer.openMachine('printer_1')") is True
    page.wait_for_function("() => window.apothecaryPanels.isShown('machine-print')", timeout=10000)
    makes, pick = windows.in_machine(page, "#print-part"), windows.in_machine(page, "#print-pick")
    expect(makes.locator("option[value='calibration_cube']")).to_be_attached(timeout=10000)
    makes.select_option("calibration_cube")
    windows.in_machine(page, "#print-slice").click()
    expect(page.locator("#status")).to_contain_text("kept and chosen", timeout=SLICED_MS)
    expect(pick).to_have_value(re.compile("calibration_cube"))
    cube = pick.input_value()

    makes.select_option("hose_adapter")
    expect(pick).to_have_value("")
    expect(pick.locator("option:checked")).to_have_text(
        "— none of hose_adapter kept: Slice makes one —"
    )
    # A person's own choice is theirs.
    pick.select_option(cube)
    page.wait_for_timeout(500)
    expect(pick).to_have_value(cube)
    assert errors == []


@pytest.mark.e2e
def test_make_on_the_part_stepped_into_takes_it_to_the_printer_whose_board_is_connected(
    page: Page, url: str
):
    """In the universe, the calibration cube stepped into: the banner's ⚒ Make names
    garage's printer_1, whose board is connected, ahead of the universe's own printer,
    which is only planned; pressed, it opens the garage, chooses the cube there by its
    name among every part of the apothecary, and slices it for the board's port."""
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()
        http.put(
            f"/sites/garage/nodes/{BOARD}/device", json={"identity": PRINTER}
        ).raise_for_status()
        try:
            open_garage(page, url, settle=False)
            to_site(page, "apothecary")
            make = page.locator("#make-here")
            expect(make).to_be_hidden()
            row(page, "calibration_cube").dblclick()
            page.wait_for_function(
                "() => window.fractalViewer.focusPath.join('.') === 'calibration_cube'"
            )
            expect(make).to_have_text(
                "⚒ Make calibration_cube on printer_1 in garage", timeout=15000
            )
            make.click()
            page.wait_for_function(
                "() => window.fractalViewer.siteName === 'garage'", timeout=15000
            )
            page.wait_for_function(
                "() => window.apothecaryPanels.isShown('machine-print')", timeout=10000
            )
            expect(windows.in_machine(page, "#print-part")).to_have_value("calibration_cube")
            expect(page.locator("#status")).to_contain_text("kept and chosen", timeout=SLICED_MS)
            # Landed in the Machine view: the Machine's head beside its Print, each a
            # stack of its own, nothing the garage opened on the way left -- its
            # Procedure -- and the printer framed in the world.
            page.wait_for_function(
                "() => window.apothecaryPanels.state('machine').stack.length === 1",
                timeout=10000,
            )
            assert windows.state(page, "machine-print")["stack"] == ["machine-print"]
            assert windows.state(page, "machine-print")["shown"] is True
            assert windows.state(page, "procedure")["open"] is False
            page.wait_for_function(IN_THE_MIDDLE, arg="printer_1", timeout=5000)
        finally:
            http.delete(f"/sites/garage/nodes/{BOARD}/device")
    assert errors == []


@pytest.mark.e2e
def test_make_opens_the_board_s_machine_though_the_universe_s_boards_answer_late(
    page: Page, url: str
):
    """The universe's scan of its boards still in flight when ⚒ Make opens the garage:
    the garage's boards are asked for themselves, and the universe's answer, coming after
    the garage has loaded, is no answer for it -- printer_1's Machine is its board's,
    not its plan."""
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    held: list = []
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()
        http.put(
            f"/sites/garage/nodes/{BOARD}/device", json={"identity": PRINTER}
        ).raise_for_status()
        try:
            open_garage(page, url, settle=False)
            page.route(
                re.compile(r"/sites/apothecary/devices$"),
                lambda route: held.append(route) if not held else route.continue_(),
            )
            to_site(page, "apothecary")
            page.wait_for_function("() => window.fractalViewer.bindingsInFlight")
            assert len(held) == 1
            row(page, "calibration_cube").dblclick()
            page.wait_for_function(
                "() => window.fractalViewer.focusPath.join('.') === 'calibration_cube'"
            )
            make = page.locator("#make-here")
            expect(make).to_have_text(
                "⚒ Make calibration_cube on printer_1 in garage", timeout=15000
            )
            make.click()
            page.wait_for_function(
                "() => window.fractalViewer.siteName === 'garage'", timeout=15000
            )
            held[0].continue_()
            page.wait_for_function(
                "() => window.apothecaryPanels.isShown('machine-print')", timeout=15000
            )
            opened = page.evaluate(
                "() => { const m = window.fractalViewer.machine;"
                " return m && { port: m.port, plan: !!m.plan }; }"
            )
            assert opened == {"port": PRINTER, "plan": False}
            pinned = page.evaluate(
                "(path) => window.fractalViewer.bindings[path]?.device?.port ?? null", BOARD
            )
            assert pinned == PRINTER
        finally:
            http.delete(f"/sites/garage/nodes/{BOARD}/device")
    assert errors == []


@pytest.mark.e2e
def test_make_takes_the_variant_drawn_to_the_printer_s_site_and_its_slice_again_keeps_it(
    page: Page, url: str
):
    """In the universe, hose_adapter drawn as a variant: ⚒ Make opens the garage, where
    printer_1's board is connected, and slices that variant there. The garage's address
    names the variant, so the Print window's Slice, pressed again, slices the variant
    too, not the part as saved; Back returns to the universe, still drawing it."""
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    params = {"a_d": 36, "a_length": 20, "a_socket": True, "b_d": 33, "b_length": 15,
              "step": False, "step_d": 33}
    with httpx.Client(base_url=url, timeout=120.0) as http:
        rendered = http.post(
            "/parts/hose_adapter/stl/generate?pose=rest", json={"params": params}
        )
        rendered.raise_for_status()
        variant = rendered.json()["variant"]
        assert variant and not rendered.json()["saved"]
        http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()
        http.put(
            f"/sites/garage/nodes/{BOARD}/device", json={"identity": PRINTER}
        ).raise_for_status()
        try:
            page.goto(f"{url}/viewer/sites/apothecary?variant=hose_adapter:{variant}")
            page.wait_for_function(
                "(key) => window.fractalViewer.variantByPart.hose_adapter === key",
                arg=variant,
                timeout=15000,
            )
            row(page, "hose_adapter").dblclick()
            page.wait_for_function(
                "() => window.fractalViewer.focusPath.join('.') === 'hose_adapter'"
            )
            make = page.locator("#make-here")
            expect(make).to_have_text("⚒ Make hose_adapter on printer_1 in garage", timeout=15000)
            make.click()
            page.wait_for_function(
                "() => window.fractalViewer.siteName === 'garage'", timeout=15000
            )
            expect(page.locator("#status")).to_contain_text("kept and chosen", timeout=SLICED_MS)
            said = windows.in_machine(page, "#print-slice-said")
            expect(said).to_contain_text(f"hose_adapter (the variant {variant[:8]}) sliced")
            windows.in_machine(page, "#print-slice").click()
            expect(page.locator("#status")).to_contain_text("slicing hose_adapter", timeout=10000)
            expect(page.locator("#status")).to_contain_text("kept and chosen", timeout=SLICED_MS)
            # The file chosen for ▶ Print is of the variant. (The scripted slicer writes the
            # same G-code for any STL, so both slices are one kept file: its record is the
            # newest slice's.)
            chosen = windows.in_machine(page, "#print-pick").input_value()
            made = http.get(f"/slicer/slices/{chosen}").json()["made"]
            assert (made["name"], made["variant"]) == ("hose_adapter", variant)
            assert made["params"]["b_d"] == pytest.approx(33)
            expect(said).to_contain_text(f"hose_adapter (the variant {variant[:8]}) sliced")
            # The garage drew it from the universe: its address names the variant made.
            assert f"variant=hose_adapter%3A{variant}" in page.url
            page.go_back()
            page.wait_for_function(
                "() => window.fractalViewer.siteName === 'apothecary'", timeout=15000
            )
            page.wait_for_function(
                "(key) => window.fractalViewer.variantByPart.hose_adapter === key",
                arg=variant,
                timeout=15000,
            )
        finally:
            http.delete(f"/sites/garage/nodes/{BOARD}/device")
    assert errors == []


@pytest.mark.e2e
def test_the_part_made_read_is_a_turn_of_the_printers_tuning(page: Page, url: str):
    """The footpedal made on printer_1, then read in its part's cabinet: its ring's
    Part › View › Feedback brings the Feedback window, where its slice is listed as a piece
    made elsewhere with a row for each size of its box. Keep opens the piece's drawer and files
    the first turn of printer_1's tuning, which says a box's sizes separate no error from
    another, so Take turn is greyed and the next slice takes the profile's own walls; Undo
    turn drops the turn, and its filing says so. The Print window measures nothing."""
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    open_garage(page, url, settle=False)
    _machines_known(page)
    select(page, "footpedal")
    expect(page.locator("#make-here")).to_have_text(re.compile("on printer_1"), timeout=15000)
    page.locator("#make-here").click()
    expect(page.locator("#status")).to_contain_text("kept and chosen", timeout=SLICED_MS)
    assert windows.in_machine(page, "#print-measure-plan").count() == 0
    rings.on_row(page, "footpedal", "Part", "View", "Feedback", "Feedback")
    expect(page.locator("#status")).to_contain_text("footpedal's cabinet in Part › Feedback")
    feedback = windows.panel(page, "part-feedback")
    expect(feedback.locator("#feedback-title")).to_have_text("Feedback · footpedal")
    expect(feedback.locator("#feedback-piece")).to_contain_text("not printed from here")
    said = feedback.locator("#feedback-measure-said")
    expect(said).to_contain_text("of 3 features of its box", timeout=10000)
    # Its ring's other cells act on the piece chosen there: nothing filed, no turn to take;
    # nothing typed, Measure takes a person to the rows.
    rings.on_row(page, "footpedal", "Part", "View", "Feedback", "Take turn")
    expect(page.locator("#status")).to_contain_text("Take turn: nothing is filed of this piece yet")
    rings.on_row(page, "footpedal", "Part", "View", "Feedback", "Measure")
    expect(page.locator("#status")).to_contain_text(
        "read the piece: x, y, z, each in mm in its row; or choose what it shows under seen, "
        "or type a note; then Keep"
    )
    record = next(
        r
        for r in page.request.get(f"{url}/slicer/slices").json()
        if r["made"]["name"] == "footpedal"
    )
    x, y, _ = record["size"]
    rows = '#feedback-measure-plan input[data-feature="{}"]'
    feedback.locator(rows.format("x")).fill(f"{x + 0.2:.3f} {x + 0.22:.3f}")
    feedback.locator(rows.format("y")).fill(f"{y + 0.1:.3f}")
    feedback.locator("#feedback-keep").click()
    expect(page.locator("#status")).to_contain_text(
        "turn-1 filed in footpedal's drawer, for printer_1: footpedal read at 2 features: "
        "no term determined",
        timeout=10000,
    )
    filed = feedback.locator("#feedback-filed li")
    expect(filed).to_have_count(1)
    expect(filed.first).to_contain_text("measured (turn-1)")
    expect(feedback.locator("#feedback-piece-said")).not_to_contain_text("no drawer yet")
    apply = feedback.locator("#feedback-tune-apply")
    expect(apply).to_be_disabled()
    expect(apply).to_have_attribute("title", re.compile("turn-1 proposes no change"))
    expect(feedback.locator("#feedback-tune-history")).to_contain_text(
        "turn-1, footpedal: no term determined; not separated: contour, foot, scale_x, "
        "scale_y; proposed: nothing"
    )
    (drawer,) = page.request.get(f"{url}/cabinet/footpedal").json()["drawers"]
    assert drawer["file"]["file_id"] == record["file_id"] and drawer["job"] is None
    # The next slice for printer_1 takes the profile's own walls: nothing was applied.
    windows.in_machine(page, "#print-slice").click()
    expect(page.locator("#status")).to_contain_text("kept and chosen", timeout=SLICED_MS)
    expect(windows.in_machine(page, "#print-slice-said")).not_to_contain_text(
        "xy_contour_compensation -"
    )
    feedback.locator("#feedback-tune-undo").click()
    expect(page.locator("#status")).to_contain_text("turn-1 undone", timeout=10000)
    expect(filed.first).to_have_class(re.compile("undone"))
    assert errors == []


@pytest.mark.e2e
def test_the_filament_loaded_and_a_fault_seen_tune_the_printers_next_slices(page: Page, url: str):
    """printer_1's Print window says the filament loaded on it, the profile's own until
    one is chosen; another chosen is what its next slice is made with. The footpedal
    made, then looked at in its part's cabinet, Part › Feedback: stringing seen clear is
    filed as the first look of printer_1's tuning, which steps the retraction; Take turn
    takes it, and Undo turn drops it.
    The filaments' first ask fails and is asked again; the drop-down is not drawn again
    while a person has it, nor when nothing it holds changed."""
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    asked: list = []

    def fail_once(route):
        asked.append(route.request.url)
        if len(asked) == 1:
            route.fulfill(status=503, json={"detail": "the server was away"})
        else:
            route.continue_()

    page.route(re.compile(r"/slicer/filaments\?"), fail_once)
    open_garage(page, url, settle=False)
    _machines_known(page)
    select(page, "footpedal")
    expect(page.locator("#make-here")).to_have_text(re.compile("on printer_1"), timeout=15000)
    page.locator("#make-here").click()
    expect(page.locator("#status")).to_contain_text("kept and chosen", timeout=SLICED_MS)
    filament = windows.in_machine(page, "#print-filament")
    expect(filament).to_have_value("Creality Generic PLA", timeout=10000)
    assert len(asked) >= 2  # the first ask failed, and was asked again
    expect(windows.in_machine(page, "#print-filament-said")).to_have_text(
        "the profile's own: choose what is loaded"
    )
    # A person with the drop-down: the Print window drawn again (a file chosen) leaves
    # what they have on it, and the options it drew are the same ones after they leave.
    first = filament.evaluate_handle("(sel) => sel.options[0]")
    filament.evaluate("(sel) => { sel.focus(); sel.value = 'Creality Generic PETG'; }")
    windows.in_machine(page, "#print-pick").dispatch_event("change")
    assert filament.evaluate("(sel, first) => [sel.value, sel.options[0] === first]", first) == [
        "Creality Generic PETG",
        True,
    ]
    filament.evaluate("(sel) => sel.blur()")
    assert filament.evaluate("(sel, first) => [sel.value, sel.options[0] === first]", first) == [
        "Creality Generic PLA",
        True,
    ]
    filament.select_option("Creality Generic PETG")
    expect(page.locator("#status")).to_contain_text(
        "Creality Generic PETG loaded on printer_1", timeout=10000
    )
    windows.in_machine(page, "#print-slice").click()
    expect(page.locator("#status")).to_contain_text("kept and chosen", timeout=SLICED_MS)
    expect(windows.in_machine(page, "#print-slice-said")).to_contain_text("Creality Generic PETG")
    filament.select_option("Creality Generic PLA")
    expect(page.locator("#status")).to_contain_text("Creality Generic PLA loaded", timeout=10000)
    windows.in_machine(page, "#print-slice").click()
    expect(page.locator("#status")).to_contain_text("kept and chosen", timeout=SLICED_MS)

    rings.on_row(page, "footpedal", "Part", "View", "Feedback", "Feedback")
    feedback = windows.panel(page, "part-feedback")
    seen = feedback.locator('#feedback-seen-faults select[data-fault="stringing"]')
    expect(seen).to_be_visible(timeout=10000)
    seen.select_option("2")
    feedback.locator("#feedback-keep").click()
    expect(page.locator("#status")).to_contain_text(
        "look-1 filed in footpedal's drawer, for printer_1: footpedal looked at: stringing "
        "clear; proposed: filament_retraction_length 4 mm -> 4.5 mm",
        timeout=10000,
    )
    expect(seen).to_have_value("0")
    history = feedback.locator("#feedback-tune-history")
    expect(history).to_contain_text("look-1, footpedal, seen: stringing clear")
    feedback.locator("#feedback-tune-apply").click()
    expect(page.locator("#status")).to_contain_text(
        "Taken for printer_1's next slices: filament_retraction_length", timeout=10000
    )
    expect(history).to_contain_text(
        "stringing: clear at look-1 (then filament_retraction_length 4.5)"
    )
    feedback.locator("#feedback-tune-undo").click()
    expect(page.locator("#status")).to_contain_text("look-1 undone", timeout=10000)
    assert errors == []
