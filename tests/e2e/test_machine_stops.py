"""What stops a machine from the page, and what the page says of a machine it cannot
hear: a jog is one request, the verbs that interrupt go at once and are never greyed,
the Machine view keeps the Machine's head and its stop in view at any size the page is
laid out for, the popped-out pad has a stop of its own, a Disarm that failed is never drawn as
disarmed, an open Machine hears the latch armed from elsewhere, a status gone old says
its age, and a Machine follows its board to the port it is found on.

Runs against a server of its own with the simulated printer on ``/dev/ttyFAKE1`` and
the simulated router on ``/dev/ttyFAKE3``, each identified and pinned. Every test
starts with both disarmed and both links released: the simulators start over. A
request is held back, refused or answered for the server by the browser
(``page.route``), so what the page does while the server is slow, silent or wrong is
seen without a server that is any of them. Nothing here opens a real port.
"""

from __future__ import annotations

import re

import httpx
import pytest
import windows
from boards import BOARD, PRINTER
from playwright.sync_api import Page, expect

ROUTER = "/dev/ttyFAKE3"
CONTROLLER = "cnc_router.frame_system.controller"
POLL_MS = 2000  # the Machine's default interval
WITHIN_A_POLL = POLL_MS + 3000
ARMED_MS = 2000  # how often the page asks which ports are armed (boards.js)


@pytest.fixture(scope="module")
def url(start_server):
    url = start_server(
        env_overrides={
            "APOTHECARY_SIMULATED_ROUTER": ROUTER,
            "APOTHECARY_SIMULATED_SPEED": "0.05",
            "FAKE_ROUTER": "1",
        }
    )
    with httpx.Client(base_url=url, timeout=15.0) as http:
        for port, node in ((PRINTER, BOARD), (ROUTER, CONTROLLER)):
            http.post("/firmware/devices/identify", json={"port": port}).raise_for_status()
            http.put(
                f"/sites/garage/nodes/{node}/device", json={"identity": port}
            ).raise_for_status()
    return url


@pytest.fixture(autouse=True)
def _as_it_starts(url):
    """Both disarmed and both links released, before and after: a simulator stopped
    by one test starts over for the next."""

    def start_over():
        with httpx.Client(base_url=url, timeout=15.0) as http:
            for port in (PRINTER, ROUTER):
                http.post("/firmware/printers/control", json={"port": port, "armed": False})
                http.post("/firmware/printers/release", json={"port": port}).raise_for_status()
                http.post("/firmware/devices/identify", json={"port": port}).raise_for_status()

    start_over()
    yield
    start_over()


def _machine(page: Page, url: str, port: str = PRINTER):
    """The board's Machine open and polled once; returns its control pad."""
    page.goto(f"{url}/firmware/monitor?port={port}")
    windows.machine_ready(page, "router" if port == ROUTER else "printer")
    expect(windows.in_machine(page, "#c-state")).not_to_have_text("—", timeout=10000)
    return page.locator("#control")


def _arm(page: Page):
    page.locator("#ctl").check()
    expect(page.locator("#control")).to_be_visible(timeout=5000)


def _armed(url: str, port: str = PRINTER) -> bool:
    r = httpx.get(f"{url}/firmware/printers/control", params={"port": port}, timeout=15.0)
    return r.json()["armed"]


def _posts(page: Page) -> list:
    """Every request the page posts to a machine from here on: the route's last part
    and its body."""
    sent = []

    def note(request):
        if request.method == "POST" and "/firmware/printers/" in request.url:
            sent.append((request.url.rsplit("/", 1)[1], request.post_data_json))

    page.on("request", note)
    return sent


def _lines(sent: list) -> list:
    return [body["command"] for route, body in sent if route == "command"]


def _held(page: Page, line: str) -> list:
    """The page's request for this line kept from the server, as a line that takes a
    minute is in flight for a minute: the route to let go is the list's one item."""
    held = []

    def hold(route):
        if (route.request.post_data_json or {}).get("command") == line and not held:
            held.append(route)
        else:
            route.continue_()

    page.route("**/firmware/printers/command", hold)
    return held


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("port", "feed", "lines"),
    [
        (PRINTER, 3000, ("G91", "G1 Y10 F3000", "G90")),
        (ROUTER, 1000, ("$J=G91 G21 Y10 F1000",)),
    ],
    ids=["printer", "router"],
)
def test_a_jog_is_one_request(page: Page, url: str, port: str, feed: int, lines: tuple):
    """A jog from the pad is one POST /firmware/printers/jog for a printer as for a
    router: the relative move, and absolute positioning put back, are the server's to
    send, and the page sends none of their lines itself."""
    pad = _machine(page, url, port)
    _arm(page)
    if port == PRINTER:  # mid-print as it starts: paused, so it takes a move
        pad.locator("button[data-cmd='M25']").click()
        expect(windows.in_machine(page, "#c-state")).to_contain_text("idle", timeout=WITHIN_A_POLL)
    sent = _posts(page)
    pad.locator("button[data-step='10']").click()
    pad.locator("button[data-jog='Y+']").click()
    log = windows.in_machine(page, "#log")
    for line in lines:
        expect(log.locator(".tx.control", has_text=line).last).to_be_visible(timeout=8000)
    expect(pad.locator("#ctl-sent")).to_have_text(f"> jog Y10 F{feed}")
    assert [s for s in sent if s[0] in ("jog", "command")] == [
        ("jog", {"port": port, "axis": "Y", "mm": 10, "feed": feed})
    ], sent
    # The pad is the chain's again once the jog has answered.
    expect(pad.locator("button[data-jog='Y+']")).to_be_enabled(timeout=WITHIN_A_POLL)


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("port", "slow", "home", "interrupts"),
    [
        (PRINTER, "G28", "HOME", ("M410", "M108")),
        (ROUTER, "$H", "HOME", ("JOG-CANCEL", "HOLD", "RESUME")),
    ],
    ids=["printer", "router"],
)
def test_a_verb_that_interrupts_goes_at_once_with_a_line_in_flight(
    page: Page, url: str, port: str, slow: str, home: str, interrupts: tuple
):
    """With a home in flight the pad is greyed, and Quickstop and Break wait (a
    router's Stop jog, Hold and Resume) are not: each is sent the moment it is
    pressed, ahead of the home's answer, never queued behind it."""
    pad = _machine(page, url, port)
    _arm(page)
    held = _held(page, slow)
    sent = _posts(page)
    pad.locator(f"button[data-cmd='{home}']").click()
    page.wait_for_function("() => true")  # a turn of the page
    expect(pad.locator("button[data-jog='Y+']")).to_be_disabled(timeout=5000)
    assert _lines(sent) == [slow], sent
    for line in interrupts:
        button = pad.locator(f"button[data-cmd='{line}']")
        expect(button).to_be_enabled()
        with page.expect_response(
            lambda r, line=line: r.url.endswith("/firmware/printers/command")
            and r.request.post_data_json["command"] == line,
            timeout=8000,
        ):
            button.click()
        # Still in flight, and the pad still greyed around the verbs that interrupt.
        expect(pad.locator("button[data-jog='Y+']")).to_be_disabled()
    assert _lines(sent)[: 1 + len(interrupts)] == [slow, *interrupts], sent
    assert len(held) == 1
    held[0].continue_()
    page.unroute("**/firmware/printers/command")
    expect(pad.locator("button[data-jog='Y+']")).to_be_enabled(timeout=15000)


@pytest.mark.e2e
def test_the_popped_out_pad_has_a_stop_of_its_own(page: Page, url: str):
    """Armed, the pad stands in a window of its own, which the Machine's head may not
    be beside: it has an E-STOP of its own there, never greyed, that sends what the
    Machine's sends. Put back in the Machine, the Machine's is the one."""
    pad = _machine(page, url)
    _arm(page)
    window = windows.panel(page, "control")
    stop = window.locator("#pad-estop")
    expect(stop).to_be_visible(timeout=5000)
    expect(stop).to_have_text("⏹ E-STOP")
    expect(stop).to_have_attribute("title", re.compile(r"^M112: emergency stop"))
    pad.locator("#ctl-pop").click()  # ⇥ Put back
    expect(page.locator(f"{windows.MACHINE} #control")).to_be_visible()
    expect(page.locator("#pad-estop")).to_be_hidden()
    expect(page.locator(f"{windows.MACHINE} #estop")).to_be_visible()
    pad.locator("#ctl-pop").click()  # ⧉ Pop out
    expect(stop).to_be_visible(timeout=5000)

    # A home in flight greys the pad, and never its stop.
    held = _held(page, "G28")
    sent = _posts(page)
    pad.locator("button[data-cmd='HOME']").click()
    expect(pad.locator("button[data-jog='Y+']")).to_be_disabled(timeout=5000)
    expect(stop).to_be_enabled()
    with page.expect_response(
        lambda r: r.url.endswith("/firmware/printers/command")
        and r.request.post_data_json["command"] == "M112"
    ) as answered:
        stop.click()
    assert answered.value.ok
    assert _lines(sent)[:2] == ["G28", "M112"], sent
    expect(windows.in_machine(page, "#log").locator(".tx", has_text="M112").last).to_be_visible(
        timeout=8000
    )
    held[0].continue_()
    page.unroute("**/firmware/printers/command")


# Where an element of the Machine's window stands against the window: its top and foot
# inside it, and the window's own scroll.
INSIDE = """(selector) => {
    const win = document.querySelector(".panel[data-panel='machine']").getBoundingClientRect();
    const box = document.querySelector(`.panel[data-panel='machine'] ${selector}`).getBoundingClientRect();
    return box.height > 0 && box.top >= win.top - 1 && box.bottom <= win.bottom + 1
        && box.bottom <= innerHeight;
}"""


@pytest.mark.e2e
@pytest.mark.parametrize("size", [(1100, 700), (1600, 1000)], ids=["1100x700", "1600x1000"])
def test_the_machine_views_head_and_its_stop_stay_in_view(page: Page, url: str, size):
    """The Machine view on a page 1100 by 700 and on one 1600 by 1000: the Machine's
    head -- its link's verbs, the latch and ⏹ E-STOP -- is whole in its window, and
    stays at the window's top as the window scrolls."""
    page.set_viewport_size({"width": size[0], "height": size[1]})
    _machine(page, url)
    for selector in ("#estop", "#ctl-label", "#reconnect"):
        assert page.evaluate(INSIDE, selector), selector
    body = page.locator(f"{windows.MACHINE} > .machine")
    head = page.locator(f"{windows.MACHINE} .machine-head")
    top = head.bounding_box()["y"]
    assert body.evaluate("(e) => e.scrollHeight > e.clientHeight")
    body.evaluate("(e) => { e.scrollTop = e.scrollHeight; }")
    page.wait_for_function(
        "(s) => document.querySelector(s).scrollTop > 0", arg=f"{windows.MACHINE} > .machine"
    )
    assert head.bounding_box()["y"] == pytest.approx(top, abs=1)
    assert page.evaluate(INSIDE, "#estop")


@pytest.mark.e2e
def test_a_disarm_that_failed_is_never_drawn_as_disarmed(page: Page, url: str):
    """A Disarm the server refused leaves the machine armed, and the page says so: the
    refusal, then the latch as the server has it (GET /firmware/printers/control), the
    pad still there. With that unanswered too, the latch stays as last drawn, marked as
    not confirmed, and is never drawn disarmed."""
    pad = _machine(page, url)
    _arm(page)
    # Only what this Machine asks: the page's follower of every armed port is silent.
    page.route("**/firmware/printers/armed", lambda route: route.abort())
    answers = {"get": True}

    def latch(route):
        if route.request.method == "POST":
            route.fulfill(status=500, json={"detail": "the latch did not answer"})
        elif answers["get"]:
            route.continue_()
        else:
            route.abort()

    page.route("**/firmware/printers/control*", latch)
    settled = "() => window.apothecaryMachine.ctl.pending === 0"

    pad.locator("#ctl-disarm").click()
    expect(page.locator("#status")).to_contain_text("Control: the latch did not answer")
    page.wait_for_function(settled)
    assert _armed(url)
    assert pad.is_visible()
    assert page.locator("#ctl").is_checked()
    assert page.locator("#ctl-unknown").is_hidden()

    answers["get"] = False
    page.locator("#ctl").uncheck()  # the head's own Disarm
    page.wait_for_function("() => window.apothecaryMachine.ctl.unknown")
    page.wait_for_function(settled)
    assert pad.is_visible()
    assert page.locator("#ctl").is_checked()
    expect(pad.locator("#ctl-unknown")).to_have_text("not confirmed: the server did not answer")
    expect(page.locator("#ctl-label")).to_have_class(re.compile(r"\bunknown\b"))

    # Answered again, a Disarm is one: the pad goes, and nothing is unconfirmed.
    page.unroute("**/firmware/printers/control*")
    pad.locator("#ctl-disarm").click()
    expect(pad).to_be_hidden(timeout=5000)
    expect(page.locator("#ctl-label")).not_to_have_class(re.compile(r"\bunknown\b"))
    assert not _armed(url)


@pytest.mark.e2e
def test_an_open_machine_hears_its_port_armed_and_let_go_from_elsewhere(page: Page, url: str):
    """With auto-poll off, a port armed by another hand -- the deck, another browser --
    arms the open Machine's own latch within the page's look at the armed ports: its
    pad out, its tick-box ticked. Let go from elsewhere, the pad goes."""
    pad = _machine(page, url)
    page.locator("#auto").uncheck()
    expect(pad).to_be_hidden()
    with httpx.Client(base_url=url, timeout=15.0) as elsewhere:
        elsewhere.post(
            "/firmware/printers/control", json={"port": PRINTER, "armed": True}
        ).raise_for_status()
        expect(pad).to_be_visible(timeout=3 * ARMED_MS)
        expect(page.locator("#ctl")).to_be_checked()
        expect(page.locator("#ctl-ttl")).to_contain_text(":")
        elsewhere.post(
            "/firmware/printers/control", json={"port": PRINTER, "armed": False}
        ).raise_for_status()
        expect(pad).to_be_hidden(timeout=3 * ARMED_MS)
        expect(page.locator("#ctl")).not_to_be_checked()


@pytest.mark.e2e
def test_a_status_gone_old_says_its_age(page: Page, url: str):
    """Polls that fail leave the last status drawn: once it is a few seconds old the
    State card says how old, and the cards drawn from it are marked. A poll answered
    takes both away."""
    _machine(page, url)
    age = windows.in_machine(page, "#c-age")
    expect(age).to_be_hidden()
    page.route("**/firmware/printers/status*", lambda route: route.abort())
    expect(age).to_be_visible(timeout=15000)
    expect(age).to_have_text(re.compile(r"^status \d+ s old$"))
    expect(page.locator(f"{windows.MACHINE} > .machine.status-old")).to_be_attached()
    said = int(re.search(r"\d+", age.text_content()).group())
    expect(age).not_to_have_text(f"status {said} s old", timeout=5000)  # it counts
    page.unroute("**/firmware/printers/status*")
    expect(age).to_be_hidden(timeout=WITHIN_A_POLL)
    expect(page.locator(f"{windows.MACHINE} > .machine.status-old")).to_have_count(0)


@pytest.mark.e2e
def test_a_machine_follows_its_board_to_the_port_it_is_found_on(page: Page, url: str):
    """Two boards replugged trade port names: a scan then finds printer_1's board on
    the port the router's had. printer_1's open Machine goes with its board, to that
    port, and is never left asking the name its board had, which is another board's
    now."""
    _machine(page, url)
    assert page.evaluate("() => window.fractalViewer.machine.path") == "printer_1"
    assert page.evaluate("() => window.apothecaryMachine.state.port") == PRINTER
    swap = {PRINTER: ROUTER, ROUTER: PRINTER}

    def traded(route):
        answer = route.fetch()
        found = answer.json()
        for row in [*found["bindings"], *found["devices"]]:
            device = row.get("device")
            if device and device.get("port") in swap:
                device["port"] = swap[device["port"]]
        route.fulfill(response=answer, json=found)

    page.route("**/sites/garage/devices*", traded)
    page.evaluate("() => window.fractalViewer.boards.rescan()")
    page.wait_for_function(
        "([board, port]) => window.fractalViewer.bindings[board].device.port === port",
        arg=[BOARD, ROUTER],
    )
    page.wait_for_function(
        "(port) => window.fractalViewer.machine && window.fractalViewer.machine.port === port"
        " && window.apothecaryMachine && window.apothecaryMachine.state.port === port",
        arg=ROUTER,
        timeout=10000,
    )
    assert page.evaluate("() => window.fractalViewer.machine.path") == "printer_1"
    expect(windows.tab(page, "machine")).to_contain_text("printer_1")
    page.unroute("**/sites/garage/devices*")
