"""The router's Machine: cnc_router's controller pinned to the simulated GRBL router,
its Machine opened from its badge with a router's cards and words, control armed and
the pad's own verbs sent in GRBL's dialect, the soft reset as the stop, and a cut from
here streamed and followed.

Runs against a server of its own with the simulated router on ``/dev/ttyFAKE3``
(``APOTHECARY_SIMULATED_ROUTER``) and the scripted arduino-cli listing it
(``FAKE_ROUTER``), as ``apothecary serve --demo`` has it. Nothing here opens a real
port.
"""

from __future__ import annotations

import json
import re

import httpx
import pytest
import windows
from boards import wears
from garage import open_garage
from garage import select as _select
from playwright.sync_api import Page, expect

ROUTER = "/dev/ttyFAKE3"
CONTROLLER = "cnc_router.frame_system.controller"
POLL_MS = 2000
WITHIN_A_POLL = 3 * POLL_MS


# A printer's bed reading kept under the port name the router holds, as one was on
# the bench: the Ender's, taken while it had the name. It is there to be drawn, and
# is never the router's.
A_PRINTER_S_READING = {
    "id": "20260920T132512.468-dev_ttyFAKE3",
    "port": ROUTER,
    "at": "2026-09-20T13:25:12.468000Z",
    "method": "read",
    "mesh": [[0.0, 0.4, 0.9], [0.1, 0.5, 1.2], [0.2, 0.7, 1.6]],
    "stats": {"range": 1.6, "mean": 0.62},
    "firmware": "Marlin made up",
}


@pytest.fixture(scope="module")
def url(start_server, tmp_path_factory):
    """The router identified and its controller pinned: cnc_router wears its badge."""
    state = tmp_path_factory.mktemp("router-state")
    (state / "leveling").mkdir()
    (state / "leveling" / f"{A_PRINTER_S_READING['id']}.json").write_text(
        json.dumps(A_PRINTER_S_READING)
    )
    url = start_server(
        env_overrides={
            "APOTHECARY_SIMULATED_ROUTER": ROUTER,
            "APOTHECARY_SIMULATED_SPEED": "0.05",
            "FAKE_ROUTER": "1",
            "APOTHECARY_STATE_DIR": str(state),
        }
    )
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": ROUTER}).raise_for_status()
        http.put(
            f"/sites/garage/nodes/{CONTROLLER}/device", json={"identity": ROUTER}
        ).raise_for_status()
    return url


@pytest.fixture(autouse=True)
def _disarmed(url):
    httpx.post(
        f"{url}/firmware/printers/control", json={"port": ROUTER, "armed": False}, timeout=15.0
    )


def _log(page: Page):
    return windows.in_machine(page, "#log")


@pytest.mark.e2e
def test_the_router_s_machine_has_a_router_s_cards_and_pad(page: Page, url: str):
    """The badge says the router's state; its Machine is a router's: $I, the controller's
    word, both positions, the spindle, the pins, and no hotend, bed or Slice. Armed, the
    pad has the router's groups; Home sends $H, a jog $J=, the spindle M3 S; E-STOP is the
    soft reset, which answers with the banner; a printer's line typed is refused."""
    open_garage(page, url, settle=False)
    wears(page, "cnc_router")
    badge = page.locator(".world-badge[data-path='cnc_router']")
    expect(badge).to_contain_text("🪚")
    expect(badge).to_contain_text("idle", timeout=WITHIN_A_POLL)
    _select(page, "cnc_router")
    page.locator("#selected-body .device-section .dev-open").click()
    windows.machine_ready(page, "router")
    machine = windows.machine(page)
    expect(machine.locator("#ident")).to_contain_text("Grbl 1.3a")
    expect(machine.locator("#identify")).to_have_text("$I")
    expect(machine.locator("#c-state")).to_have_text("idle", timeout=WITHIN_A_POLL)
    expect(machine.locator("#c-state-s")).to_contain_text("Idle")
    expect(machine.locator("#c-pos")).to_contain_text("X-200.0 Y-300.0 Z-40.00")
    expect(machine.locator("#c-pos-s")).to_contain_text("machine X-200.0")
    expect(machine.locator("#c-spindle")).to_have_text("off")
    expect(machine.locator("#c-pins")).to_contain_text("none")
    expect(machine.locator("#print-title")).to_have_text("Cut from here")
    expect(machine.locator("#print-start")).to_have_text("▶ Cut")
    # The Level card is a router's too, as its Table map (test_router_table_map.py).
    for printers_own in ("#c-hot", "#c-bed", "#level-read", "#chart"):
        expect(machine.locator(printers_own)).to_be_hidden()
    # Where a printer's card has Slice, a router's has Toolpath (docs/cam.md).
    expect(machine.locator("#print-slice")).to_have_text("Toolpath")
    # The queries offered are the dialect's.
    codes = page.evaluate(
        "() => [...document.querySelectorAll('#qcodes option')].map((o) => o.value)"
    )
    assert "$$" in codes and "M503" not in codes

    # Armed: the pad, with the router's groups and none of the printer's.
    machine.locator("#ctl").check()
    pad = page.locator("#control")
    expect(pad).to_be_visible(timeout=5000)
    expect(pad.locator("#ctl-can")).to_have_text("turn and move")
    expect(pad.locator("button[data-cmd='HOME']")).to_be_visible()
    expect(pad.locator("button[data-cmd='$X']")).to_be_visible()
    expect(pad.locator("button[data-cmd='M3 S{r-rpm}']")).to_be_visible()
    expect(pad.locator("button[data-cmd='G38.2 Z-{r-probe} F100']")).to_be_visible()
    expect(pad.locator("button[data-cmd='M104 S{h-hot}']")).to_be_hidden()
    expect(pad.locator("button[data-cmd='M24']")).to_be_hidden()
    pad.locator("button[data-cmd='HOME']").click()
    expect(_log(page)).to_contain_text("> $H", timeout=5000)
    pad.locator("button[data-cmd='M3 S{r-rpm}']").click()
    expect(_log(page)).to_contain_text("> M3 S12000", timeout=5000)
    expect(machine.locator("#c-spindle")).to_have_text("12000 rpm", timeout=WITHIN_A_POLL)
    pad.locator("button[data-jog='X-']").click()
    expect(_log(page)).to_contain_text(re.compile(r"> \$J=G91 G21 X-10 F\d+"), timeout=5000)
    expect(machine.locator("#c-pos")).to_contain_text(
        "X-13.0", timeout=WITHIN_A_POLL
    )  # homed to -3, then 10 back
    pad.locator("button[data-cmd='M5']").click()
    expect(machine.locator("#c-spindle")).to_have_text("off", timeout=WITHIN_A_POLL)

    # A printer's query is refused in the dialect's words; the stop is the soft reset.
    machine.locator("#q").fill("M503")
    machine.locator("#q").press("Enter")
    expect(page.locator("#status")).to_contain_text("M503", timeout=5000)
    expect(page.locator("#status")).to_have_class(re.compile(r"\berror\b"))
    machine.locator("#estop").click()
    expect(_log(page)).to_contain_text("> RESET", timeout=5000)
    expect(_log(page)).to_contain_text("Grbl 1.3a ['$' for help]")
    expect(machine.locator("#c-state")).to_have_text("idle", timeout=WITHIN_A_POLL)


@pytest.mark.e2e
def test_a_cut_from_here_streams_pauses_and_is_a_job(page: Page, url: str):
    """A CAM post's file kept and cut: the controller holds when paused and runs again
    when resumed, the badge says the cut, and the job is listed as a cut of the router."""
    open_garage(page, url, settle=False)
    wears(page, "cnc_router")
    _select(page, "cnc_router")
    page.locator("#selected-body .device-section .dev-open").click()
    windows.machine_ready(page, "router")
    machine = windows.machine(page)
    machine.locator("#ctl").check()
    expect(page.locator("#control")).to_be_visible(timeout=5000)
    # Twenty dwells of two seconds at a fifth of real time: a cut of some ten seconds
    # on the controller, long enough to be seen running, held and resumed.
    text = (
        "G21 G90\nM3 S10000\n"
        + "".join(f"G1 X-{5 * i} Y-{5 * i} F600\nG4 P2\n" for i in range(1, 21))
        + "M5\nM30\n"
    )
    machine.locator("#print-file").set_input_files(
        {"name": "pocket.nc", "mimeType": "text/plain", "buffer": text.encode()}
    )
    expect(machine.locator("#print-pick option").first).to_contain_text("pocket.nc", timeout=5000)
    page.once("dialog", lambda d: d.accept())
    machine.locator("#print-start").click()
    expect(machine.locator("#print-progress")).to_contain_text("pocket.nc · running", timeout=5000)
    # A poll mid-cut lands in the badge: the router's state is the job's word, and the cut.
    page.evaluate(f"() => window.fractalViewer.pollNow('{ROUTER}')")
    expect(page.locator(".world-badge[data-path='cnc_router']")).to_contain_text(
        "cut", timeout=WITHIN_A_POLL
    )
    expect(page.locator(".world-badge[data-path='cnc_router']")).to_contain_text("running")
    machine.locator("#print-pause").click()
    expect(machine.locator("#print-progress")).to_contain_text("paused", timeout=5000)
    expect(machine.locator("#c-state-s")).to_contain_text("Hold", timeout=WITHIN_A_POLL)
    machine.locator("#print-resume").click()
    expect(machine.locator("#print-progress")).to_contain_text(
        re.compile(r"· done ·"), timeout=20000
    )
    expect(machine.locator("#print-history")).to_contain_text("cut · pocket.nc")
    expect(machine.locator("#print-history")).to_contain_text("done")
    jobs = httpx.get(f"{url}/jobs", params={"machine": ROUTER, "kind": "cut"}, timeout=15.0).json()
    assert jobs and jobs[0]["machine"]["kind"] == "router" and jobs[0]["outcome"] == "done"
    expect(machine.locator("#c-state")).to_have_text("idle", timeout=WITHIN_A_POLL)


@pytest.mark.e2e
def test_toolpath_writes_the_coupon_s_cut_and_the_cut_names_its_operation(page: Page, url: str):
    """The router's Cut card has Toolpath where a printer's has Slice: the coupon on the
    table, chosen under makes, gets its toolpath written from the cuts it declares --
    kept, chosen and said, the holes bored to the tool -- and the cut, started after the
    work is zeroed where the tool stands, names the operation it is in. The part's ring
    offers the same."""
    from rings import labels as _labels
    from rings import open_on_row as _ring_on

    open_garage(page, url, settle=False)
    wears(page, "cnc_router")
    # On the coupon's ring, Toolpath, since a router is pinned in the garage.
    _ring_on(page, "router_coupon")
    assert "Toolpath" in _labels(page)
    page.keyboard.press("Escape")
    _select(page, "cnc_router")
    page.locator("#selected-body .device-section .dev-open").click()
    windows.machine_ready(page, "router")
    machine = windows.machine(page)
    expect(machine.locator("#print-slice")).to_have_text("Toolpath")
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    machine.locator("#print-part").select_option("router_coupon")
    machine.locator("#print-slice").click()
    page.wait_for_timeout(1500)
    assert errors == [], errors
    expect(page.locator("#status")).to_contain_text("kept and chosen", timeout=5000)
    expect(machine.locator("#print-pick option").first).to_contain_text(
        "router_coupon-cnc_router.nc", timeout=5000
    )
    said = machine.locator("#print-slice-said")
    expect(said).to_contain_text("router_coupon toolpath for cnc_router")
    expect(said).to_contain_text("pocket 40 x 30 at 30,35, 4 deep · 2 passes")
    expect(said).to_contain_text(
        "hole 3 mm at 110,36.667 is smaller than the 6 mm tool: bored to the tool"
    )
    record = httpx.get(f"{url}/cam/cuts", timeout=15.0).json()[0]
    assert record["part"] == "router_coupon" and record["router"]["name"] == "cnc_router"
    # Armed, the work zeroed where the tool stands, then the cut: its progress line
    # names the operation, from the first pass of the pocket.
    machine.locator("#ctl").check()
    expect(page.locator("#control")).to_be_visible(timeout=5000)
    # The tool jogged over where a stock's corner would be touched off, from wherever an
    # earlier test left it: the cut's depth under it and the safe height over it, within
    # the travel. Then the pad's Zero makes it the work zero.
    at = httpx.get(f"{url}/firmware/printers/status", params={"port": ROUTER}, timeout=15.0).json()
    dx, dy, dz = (
        want - at["position"][axis] for axis, want in zip("xyz", (-200, -300, -40), strict=True)
    )
    jogged = httpx.post(
        f"{url}/firmware/printers/command",
        json={"port": ROUTER, "command": f"$J=G91 G21 X{dx:.3f} Y{dy:.3f} Z{dz:.3f} F4000"},
        timeout=15.0,
    )
    assert jogged.status_code == 200 and jogged.json()["lines"] == ["ok"], jogged.text
    expect(machine.locator("#c-pos-s")).to_contain_text(
        "machine X-200.0 Y-300.0 Z-40.00", timeout=4 * WITHIN_A_POLL
    )
    page.locator("#control button[data-cmd='G10 L20 P1 X0 Y0 Z0']").click()
    expect(_log(page)).to_contain_text("> G10 L20 P1 X0 Y0 Z0", timeout=5000)
    expect(machine.locator("#c-pos")).to_contain_text("X0.0 Y0.0 Z0.00", timeout=WITHIN_A_POLL)
    page.once("dialog", lambda d: d.accept())
    machine.locator("#print-start").click()
    # It names the operation it is in, and goes on past every depth to the last of them:
    # the outline, below the stock's top and within the travel. The lines go faster than
    # the polls that show them, so which pass a poll finds is not said here.
    progress = machine.locator("#print-progress")
    expect(progress).to_contain_text(re.compile(r"op \d/4 pass \d/\d: "), timeout=10000)
    expect(progress).to_contain_text(
        re.compile(r"op 4/4 pass \d/6: outline 120 x 80 at 10,10 to z -"), timeout=30000
    )
    machine.locator("#print-cancel").click()  # pressed twice: the first press asks
    expect(page.locator("#status")).to_contain_text("press again to cancel the cut", timeout=5000)
    machine.locator("#print-cancel").click()
    expect(machine.locator("#print-progress")).to_contain_text("cancelled", timeout=20000)
    expect(machine.locator("#c-state")).to_have_text("idle", timeout=WITHIN_A_POLL)


@pytest.mark.e2e
def test_a_part_changed_in_its_editor_gets_its_toolpath_from_the_variant_drawn(
    page: Page, url: str
):
    """One turn of the design loop in the page: the coupon's holes are smaller than the
    tool and the toolpath says so; the hole's size typed in Part › Edit and applied, the
    Cut card's Toolpath writes the variant drawn, and has nothing to say."""
    from part_editing import edit, param

    open_garage(page, url, settle=False)
    wears(page, "cnc_router")
    edit(page, "router_coupon", view=False)
    box = param(page, "hole_diameter").locator(".param-number")
    box.fill("8")
    box.press("Tab")
    apply = page.locator("#apply-btn")
    expect(apply).to_be_enabled(timeout=10000)
    with page.expect_response(lambda r: "/draft/render" in r.url and r.ok, timeout=60000):
        apply.click()
    _select(page, "cnc_router")
    page.locator("#selected-body .device-section .dev-open").click()
    windows.machine_ready(page, "router")
    machine = windows.machine(page)
    machine.locator("#print-part").select_option("router_coupon")
    machine.locator("#print-slice").click()
    said = machine.locator("#print-slice-said")
    expect(said).to_contain_text("(the variant", timeout=10000)
    expect(said).to_contain_text("hole 8 mm at 110,36.667")
    expect(said).not_to_contain_text("bored to the tool")
    record = httpx.get(f"{url}/cam/cuts", timeout=15.0).json()[0]
    assert record["variant"] and record["params"]["hole_diameter"] == 8
    assert record["messages"] == []


@pytest.mark.e2e
def test_the_page_says_a_router_in_a_router_s_words(page: Page, url: str):
    """What a printer's words would get wrong, on a router: its row and its badge say its
    state once, its facts call its volume its working area, a negative position never
    breaks inside a number, and its hour in the Working space names the states it was in
    and the spindle, with no printer's words among them."""
    open_garage(page, url, settle=False)
    wears(page, "cnc_router")
    row = page.locator("#contents-list .contents-item[data-path='cnc_router']")
    expect(row).to_contain_text("🪚 idle", timeout=WITHIN_A_POLL)
    expect(row).not_to_contain_text("(structure)")
    badge = page.locator(".world-badge[data-path='cnc_router']")
    assert "idle · idle" not in badge.evaluate("(b) => b.textContent")
    _select(page, "cnc_router")
    facts = page.locator("#selected-body .prop-readonly:not(.picture-facts)")
    expect(facts).to_contain_text("Working area: 400 × 600 × 80 mm")
    expect(facts).not_to_contain_text("Build volume")
    page.locator("#selected-body .device-section .dev-open").click()
    windows.machine_ready(page, "router")
    machine = windows.machine(page)
    windows.from_the_windows_menu(page, "machine-print")
    expect(windows.tab(page, "machine-print")).to_contain_text("Cut")
    windows.from_the_windows_menu(page, "machine-status")
    expect(machine.locator("#c-pos .nb")).to_have_count(3, timeout=WITHIN_A_POLL)
    windows.from_the_windows_menu(page, "working")
    space = page.locator(".working-space")
    hour = space.locator(".ws-hour[data-path='cnc_router']")
    expect(hour).to_be_visible(timeout=WITHIN_A_POLL)
    hour.click()
    legend = space.locator(".ws-legend")
    expect(legend).to_contain_text("idle", timeout=2 * WITHIN_A_POLL)
    expect(legend).to_contain_text("spindle")
    for printers_own in ("printing", "hotend", "bed"):
        expect(legend).not_to_contain_text(printers_own)


@pytest.mark.e2e
def test_a_printer_s_reading_under_the_router_s_port_is_never_laid_over_its_table(
    page: Page, url: str
):
    """The server lists the router no reading of a printer's; and the page, asking for
    the router's own maps and told a printer's reading anyway (the request answered as
    a server that listed readings by port name alone would), lays none over the
    router's table: a reading is laid over the kind of machine that took it."""
    every = httpx.get(f"{url}/firmware/printers/leveling", timeout=15.0).json()
    assert [r["id"] for r in every if r["port"] == ROUTER] == [A_PRINTER_S_READING["id"]]
    mine = httpx.get(f"{url}/firmware/printers/leveling", params={"port": ROUTER}, timeout=15.0)
    assert mine.json() == []
    asked = []

    def by_port_name(route):
        asked.append(route.request.url)
        route.fulfill(json=[A_PRINTER_S_READING])

    page.route(re.compile(r".*/firmware/printers/leveling\?port=.*ttyFAKE3.*"), by_port_name)
    open_garage(page, url)
    page.wait_for_function(
        "() => { const m = window.fractalViewer.marks['cnc_router']; return m && m.marks; }",
        timeout=15000,
    )
    page.evaluate(
        "() => { const v = window.fractalViewer; v.marks['cnc_router'].readingAt = 0;"
        " v.refreshReading('cnc_router');"
        " window.dispatchEvent(new CustomEvent('apothecary:mesh',"
        f" {{ detail: {json.dumps(A_PRINTER_S_READING)} }})); }}"
    )
    page.wait_for_timeout(1000)
    assert page.evaluate("() => window.fractalViewer.marks['cnc_router'].kind") == "router"
    assert page.evaluate("() => window.fractalViewer.marks['cnc_router'].marks.mesh()") is None
    # A router's marks ask, for the router's own table maps (test_router_table_map.py);
    # what they are answered here is a printer's, and is not theirs.
    assert asked and all("ttyFAKE3" in url for url in asked)
