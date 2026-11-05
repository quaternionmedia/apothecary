"""The Working space, as a person goes through it, from each of its doors.

⊞ Windows › Working space opens it on the site: a row per pinned printer, each
with its hour's button, and its first line naming the next step. printer_1's
hour has no camera yet, so that line offers to add one above it; three added,
each chooses its device in its own row, and a frame set is kept with the next
poll. A frame opens beside the poll it rests on, the budget is set, ‹ garage
goes back to the site, and printer_1's ring (Camera › Workspace) and the canvas
ring (Panels › Site › Workspace) open the same two views.

This module is a walkthrough page too: `walkthrough/18-the-working-space.md` is
written by its run, as the browser suite runs it, and not by the quicker
`apothecary test run`.

Its server is the module's own: the simulated Ender printing, its progress held
still so the pictures are the same on every run, identified and pinned to
printer_1's mainboard as the bench's real board is. Its browser has three fake
cameras, as the bench plan has the Ender's three: the bed, the head, the room.
"""

from __future__ import annotations

import re

import httpx
import pytest
import windows
from boards import BOARD, PRINTER
from browsers import launch
from doc_capture import MOMENT, TEMPERATURE, moments
from garage import open_garage, said, status
from playwright.sync_api import expect
from rings import on_row, on_world

CAMERAS = 3
HELD = "0.42"  # the simulated print held at 42 %, so what it shows is the same each run
WINDOW = ".working-space"
FRAMES_MS = 30000  # a newly chosen camera's first frame waits for a poll, ten seconds apart
KEEP_APART_MS = 10000  # widgets/working_space.js: no two frame sets closer together than this
REFRESH_MS = 5000  # widgets/working_space.js: the document asked for again

# What changes on every run whatever the page does: the moments, how many observations
# the hour holds, the frames (the fake camera's moving picture), the heaters' lines
# and dots (where each poll fell in the hour), a temperature to its tenth, and how
# much the kept frames take; in a poll's lines, a temperature beside its target.
CHANGING = (
    *moments(WINDOW, "#status"),
    f"{WINDOW} .ws-said",
    f"{WINDOW} .ws-frames",
    f"{WINDOW} .ws-frame-large",
    f"{WINDOW} .ws-chart path",
    f"{WINDOW} .ws-chart circle",
    (WINDOW, r"\d+(?:\.\d)? °C"),
    (f"{WINDOW} pre", TEMPERATURE),
    (f"{WINDOW} .ws-budget", r"\d+ frames? kept, \d+(?:\.\d)? [kMG]B"),
)


def _words(text: str) -> str:
    """A status line as the page keeps it: its moments left out, as its pictures blank them."""
    return re.sub(MOMENT, "…", text)


@pytest.fixture(scope="module")
def url(base_url, start_server):
    """This module's own server: the simulated printer printing, held at 42 %, identified
    and pinned to printer_1's mainboard. ``base_url`` is asked for only so that with no
    server to run against this is skipped, as every browser test is."""
    url = start_server(
        {"APOTHECARY_SIMULATED_PRINTER": "printing", "APOTHECARY_SIMULATED_PROGRESS": HELD}
    )
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()
        http.put(
            f"/sites/garage/nodes/{BOARD}/device", json={"identity": PRINTER}
        ).raise_for_status()
    return url


@pytest.fixture(scope="module")
def _three_camera_browser(browser_type):
    browser = launch(
        browser_type,
        args=[
            "--use-fake-ui-for-media-stream",
            f"--use-fake-device-for-media-stream=device-count={CAMERAS}",
        ],
    )
    yield browser
    browser.close()


@pytest.fixture
def page(_three_camera_browser, url):
    """A page of the three-camera browser on this module's server, the camera allowed."""
    context = _three_camera_browser.new_context(
        viewport={"width": 1280, "height": 900}, base_url=url
    )
    context.grant_permissions(["camera"], origin=url)
    yield context.new_page()
    context.close()


@pytest.mark.e2e
def test_the_working_space_from_each_of_its_doors(page, url, walkthrough):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    story = walkthrough(
        ordinal="18",
        slug="the-working-space",
        title="The working space",
        intro=(
            "A site as its evidence has it, and a printer's hour in it: its state, its "
            "heaters, a frame from each camera that looks at it, kept with its polls, and "
            "what each value rests on. Three doors open it -- ⊞ Windows, a printer's "
            "ring and the canvas ring -- and whichever opens it, its first line, under "
            "the title, names the next step and carries the button that takes it. Every "
            "step is the page's own: a button, a menu, a box or a cell of a ring."
        ),
        runtime=(
            "It drives a real browser against a real server of its own. The printer is "
            "the simulated one, printing, its progress held at 42 %, pinned to "
            "printer_1's board as the bench's real board is; the browser's three "
            "cameras are Chromium's fake ones, each playing its moving test picture. It "
            "needs no network, opens no serial port, and refuses both."
        ),
        does_not_show=[
            "**A real camera or a real printer.** The bench's three cameras -- the bed, "
            "the head, the room -- and where each stands are the working-space plan's "
            "slice 1 (docs/plans/working-space-view-2026-10-30.md); the frames here are "
            "the fake cameras' test picture, blanked, since it moves.",
            "**A print going by.** The progress is held still, so the frames kept at "
            "every 5 % of a job, and with each change of its state, are not shown; "
            "this page keeps a set when a camera is newly chosen and when asked.",
            "**What changes on every run.** The moments, how many observations the hour "
            "holds, where each poll fell in it, a temperature to its tenth and how much "
            "the frames take are blanked in the pictures and left out of the words.",
            "**Looking back past the hour.** The window shows the last hour; an earlier "
            "one is `apothecary evidence changed --since` and the evidence document's "
            "`at` and `since` (docs/working-space.md).",
        ],
        page=page,
        browser_suite_only=True,
    )
    window = page.locator(WINDOW)
    lead = window.locator(".ws-next")
    said_first = lead.locator("span").first  # its words, without its buttons
    open_garage(page, url)

    # 1. ⊞ Windows › Working space: the site, a row per pinned printer.
    windows.from_the_windows_menu(page, "working")
    expect(lead).to_contain_text("Choose a machine to see its hour")
    printer = window.locator(".ws-printer[data-printer='printer_1']")
    expect(printer).to_contain_text("printing", timeout=FRAMES_MS)
    expect(printer).to_contain_text("answering now")
    expect(printer).to_contain_text("no camera")
    # Maximised, as a double-click on its tab does: every step after is the window's own.
    windows.tab(page, "working").dblclick()
    story.shows(
        "⊞ Windows › Working space opens it on the site",
        "The header's ⊞ Windows, Working space under Site: the window opens on the "
        "garage, maximised here by a double-click on its tab. Its first line names the "
        "next step: choose a printer. printer_1's row says what it is doing, that it is "
        "answering now and that no camera looks at it, and its button opens its hour. "
        "Under it, every subject the log has said of, named as a person names it, each "
        "value with how it is known and when.",
        shown=said_first.inner_text(),
        blank=CHANGING,
    )

    # 2. printer_1's hour: its state and heaters, and no camera yet.
    printer.get_by_role("button", name="printer_1's hour ›").click()
    said(page, "printer_1's hour in the Working space: No camera looks at printer_1 yet")
    expect(window.locator(".ws-title")).to_have_text("garage › printer_1")
    expect(window.locator("rect.ws-state.ws-printing")).to_have_count(1)
    expect(window.locator("path.ws-hotend")).to_have_count(1)
    add = lead.get_by_role("button", name="Add a camera above printer_1")
    expect(add).to_be_visible()
    story.shows(
        "printer_1's hour ›: its state, its heaters, and no camera yet",
        "Its row's button: the window is printer_1's last hour, the strip its state, "
        "printing all along, and the lines its hotend and bed, a dot at each poll, with "
        "a key under them. ‹ garage goes back. No camera looks at printer_1, so the "
        "first line offers to add one above it.",
        shown=_words(status(page).inner_text()),
        blank=CHANGING,
    )

    # 3. Three cameras added above it, each a row asking for its device.
    add.click()
    said(page, "above printer_1, looking straight down: choose its device in its row")
    rows = window.locator(".ws-camera-row")
    expect(rows).to_have_count(1)
    for more in range(2, CAMERAS + 1):
        lead.get_by_role("button", name="Add another camera").click()
        expect(rows).to_have_count(more)
    names = rows.evaluate_all("(rows) => rows.map((r) => r.dataset.camera)")
    expect(lead).to_contain_text(f"{', '.join(names)} have no device in this browser")
    for name in names:
        expect(window.locator(f".ws-choose[data-camera='{name}']")).to_be_visible()
    # Each stands beside the last, clear of it: the layout stays valid.
    expect(page.locator("#validity-indicator")).to_have_text("Layout valid")
    story.shows(
        "Add a camera above printer_1, and two more",
        f"The first line's button stands {names[0]} above printer_1, looking straight "
        "down, and Add another camera two more, each a step beside the last so none "
        "overlaps another and the header still says the layout is valid. Each is a "
        "row, saying it has no device in this browser yet, with a box to choose one, "
        "and the first line names them. On the bench each would then be moved where "
        "it looks -- the bed, the head, the room -- with its own ring's Move.",
        shown=said_first.inner_text(),
        blank=CHANGING,
    )

    # 4. Each camera's device chosen in its row; a frame set kept with the next poll.
    for i, name in enumerate(names):
        window.locator(f".ws-choose[data-camera='{name}']").select_option(index=i + 1)
        said(page, f"{name} is ")
    expect(lead).to_contain_text(f"Frames from {', '.join(names)} are kept")
    for name in names:
        expect(
            window.locator(f".ws-camera-row[data-camera='{name}'] .ws-frame").first
        ).to_be_visible(timeout=FRAMES_MS)
        expect(
            window.locator(f".ws-camera-row[data-camera='{name}'] .ws-device.ws-ok")
        ).to_be_visible()
    expect(window.locator(".ws-budget")).to_contain_text(re.compile(r"\d+ frames kept"))
    story.shows(
        "Each camera's device, chosen in its row, keeps a frame with the next poll",
        "Each row's box, one of this browser's three cameras: the row names it, and a "
        "camera newly this browser's has a frame kept with the next poll, ten seconds "
        "apart at the least, laid where it fell in the hour, and the line under the rows "
        "counts them against their budget. The first line says when frames are kept -- "
        "when printer_1's state changes and at every 5 % of a job, while the window "
        "is open -- and offers Keep a set now.",
        shown=said_first.inner_text(),
        blank=CHANGING,
    )

    # 5. Keep a set now: a frame from each camera, with one poll.
    lead.get_by_role("button", name="Keep a set now").click()
    said(page, f"a frame from {', '.join(names)} kept with the poll at")
    kept = page.request.get(f"{url}/sites/garage/evidence").json()["frames"]
    newest = sorted(kept, key=lambda f: f["at"])[-CAMERAS:]
    assert {f["camera"] for f in newest} == set(names)
    assert len({f["poll"] for f in newest}) == 1  # one set, one poll
    story.says(
        "Keep a set now keeps one from every camera, with one poll",
        "The first line's Keep a set now: a frame from each camera, all three kept with "
        "the same poll, and the status line names the next step.",
        shown=_words(status(page).inner_text()),
    )

    # 6. A frame opens beside the poll it rests on.
    window.locator(f".ws-camera-row[data-camera='{names[0]}'] .ws-frame").last.click()
    opened = window.locator(".ws-evidence")
    expect(opened.locator("img.ws-frame-large")).to_be_visible()
    link = opened.get_by_role("link", name="the poll it rests on")
    expect(link).to_have_css("color", "rgb(74, 158, 255)")  # the page's link blue
    link.click()
    expect(opened.locator("pre")).to_contain_text("ok T:")
    expect(opened.locator("pre")).to_contain_text("SD printing byte")
    story.shows(
        "A frame opens under the timeline, and the poll it rests on",
        f"A frame of {names[0]}'s row, clicked: it opens large under the timeline, with "
        "a link to the poll it was kept with; the link shows that poll, every line the "
        "printer sent, its temperatures and its place in the print. A dot on a line, or "
        "a row of the table, opens its poll the same way, and × closes it.",
        shown=_words(status(page).inner_text()),
        blank=CHANGING,
    )

    # 7. The frames' budget, set in the window.
    window.locator(".ws-close").click()
    expect(opened).to_be_empty()
    window.locator(".ws-gb").fill("1")
    window.get_by_role("button", name="Set", exact=True).click()
    said(page, "printer_1's frames now live under 1 GB")
    expect(window.locator(".ws-budget")).to_contain_text("of a 1.0 GB budget")
    story.says(
        "Budget, set under the camera rows",
        "Under the camera rows, how much printer_1's kept frames take of their budget, "
        "5 GB until set; past it, the oldest are forgotten first as the next are kept. "
        "1 typed in its box and Set: the line says 1.0 GB.",
        shown=_words(status(page).inner_text()),
    )

    # 8. ‹ garage: the site again, printer_1 with its cameras.
    window.get_by_role("button", name="‹ garage").click()
    said(page, "the Working space of garage: Choose a machine")
    expect(printer).to_contain_text(f"{CAMERAS} cameras")
    expect(window.locator(".ws-subject", has_text="printer_1 › bed heater")).to_be_visible()
    story.shows(
        "‹ garage goes back to the site",
        "‹ garage: the site again, printer_1's row now saying it has three cameras, "
        "and the subjects named as a person names them -- printer_1 › bed heater, "
        "printer_1 › x min endstop -- each id in its row's title.",
        shown=_words(status(page).inner_text()),
        blank=CHANGING,
    )

    # 9. The other doors: printer_1's ring, and the canvas ring.
    windows.tab(page, "working").dblclick()
    on_row(page, "printer_1", "Camera", "Workspace")
    said(page, f"printer_1's hour in the Working space: Frames from {', '.join(names)} are kept")
    expect(window.locator(".ws-title")).to_have_text("garage › printer_1")
    hour = _words(status(page).inner_text())
    on_world(page, "Panels", "Site", "Workspace")
    said(page, "the Working space of garage: Choose a machine")
    expect(window.locator(".ws-title")).to_have_text("garage")
    story.says(
        "Camera › Workspace on printer_1's ring, and Panels › Site › Workspace",
        "The window restored to its place by a double-click on its tab. printer_1's "
        "ring, Camera › Workspace, opens the same hour, its cameras still this "
        "browser's; the canvas ring's Panels › Site › Workspace opens the site. The "
        "status line says the window's next step whichever door opened it.",
        shown=f"{hour}\n{_words(status(page).inner_text())}",
    )
    assert errors == []


def _on_printer_1(page, url) -> None:
    """The garage, and printer_1's hour opened from its ring."""
    open_garage(page, url)
    on_row(page, "printer_1", "Camera", "Workspace")
    expect(page.locator(f"{WINDOW} .ws-title")).to_have_text("garage › printer_1")


def _settled(page) -> None:
    """Whatever a timer has started is asked for before /health is."""
    with page.expect_request("**/health"):
        page.evaluate("() => fetch('/health')")


def _refreshes(page, path: str) -> list:
    """The requests for ``path`` over one REFRESH_MS, the clock paused and then moved
    on by hand: one for each timer the window holds, each firing once."""
    page.clock.pause_at(page.evaluate("Date.now()") + 1000)
    _settled(page)
    asked = []
    page.on("request", lambda r: asked.append(r.url) if r.url.endswith(path) else None)
    page.clock.fast_forward(REFRESH_MS)
    _settled(page)
    return asked


@pytest.mark.e2e
def test_closed_it_keeps_no_frame_whoever_polls_the_printer(page, url):
    """Closed by its tab's ✕, the window turns on no camera: a poll of printer_1 that
    another window asked for -- its Machine's, say -- keeps no frame set."""
    with httpx.Client(base_url=url, timeout=15.0) as http:
        if not http.get("/sites/garage/evidence/printers/printer_1").json()["cameras"]:
            http.post("/sites/garage/cameras", json={"host": "printer_1"}).raise_for_status()
    page.clock.install()
    _on_printer_1(page, url)
    window = page.locator(WINDOW)
    window.locator(".ws-choose").first.select_option(index=1)
    said(page, "kept with the poll at", timeout=FRAMES_MS)
    page.evaluate(
        """() => {
            const verbs = window.apothecaryPictureVerbs, frameOf = verbs.frameOf;
            window.framesAsked = [];
            verbs.frameOf = (name) => { window.framesAsked.push(name); return frameOf(name); };
        }"""
    )
    windows.close(page, "working")
    expect(window).to_have_count(0)
    page.clock.pause_at(page.evaluate("Date.now()") + 1000)
    page.clock.fast_forward(KEEP_APART_MS)  # past what would hold a set back
    # A poll of printer_1's port, its state changed, as boards.js sends every poll.
    page.evaluate(
        """(port) => window.dispatchEvent(new CustomEvent("apothecary:board", { detail: {
            port, what: "status", status: { state: "paused", poll: "another-windows-poll",
            polled_at: new Date().toISOString(), sd_progress: 0.5 } } }))""",
        PRINTER,
    )
    assert page.evaluate("() => window.framesAsked") == []


@pytest.mark.e2e
def test_opened_again_from_the_windows_menu_it_is_the_site_and_read_again(page, url):
    """⊞ Windows › Working space, after the window was closed on printer_1, opens it on
    the site, as it does the first time, and the site is read again on its timer."""
    page.clock.install()
    _on_printer_1(page, url)
    windows.close(page, "working")
    windows.from_the_windows_menu(page, "working")
    window = page.locator(WINDOW)
    expect(window.locator(".ws-title")).to_have_text("garage")
    expect(window.locator(".ws-next")).to_contain_text("Choose a machine to see its hour")
    assert len(_refreshes(page, "/sites/garage/evidence/printers")) == 1


@pytest.mark.e2e
def test_two_opens_at_once_leave_one_timer(page, url):
    """Two doors pressed at once -- a printer's hour, then the site -- leave the later:
    the site, read again once a REFRESH_MS, not once for each."""
    page.clock.install()
    open_garage(page, url)
    windows.from_the_windows_menu(page, "working")
    window = page.locator(WINDOW)
    expect(window.locator(".ws-title")).to_have_text("garage")
    page.evaluate(
        """() => { const ws = window.apothecaryWorkingSpace;
                   return Promise.all([ws.open("printer_1"), ws.open(null)]).then(() => null); }"""
    )
    expect(window.locator(".ws-title")).to_have_text("garage")
    assert len(_refreshes(page, "/sites/garage/evidence/printers")) == 1


@pytest.mark.e2e
def test_another_site_loaded_is_the_one_it_shows(page, url):
    """Open on printer_1 when another site is loaded, the window shows that site,
    whether it is in front then or brought in front after."""
    _on_printer_1(page, url)
    page.evaluate("() => window.fractalViewer.loadSite('theatre')")
    windows.show(page, "working")
    expect(page.locator(f"{WINDOW} .ws-title")).to_have_text("theatre")
