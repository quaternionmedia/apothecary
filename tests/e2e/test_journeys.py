"""The journeys (apothecary/journeys.py) on the page, as a person goes through them.

The Print view: the windows a part is made through on a machine laid out together from
⊞ Windows, with printer_1's Machine open and the footpedal chosen -- Site with its own
windows, Selected, Parameters, and the Machine sharing a stack with its Print window,
Print in front, the Machine's sections open before it kept behind them. Greyed while
no Machine is open and the piece chosen has no board.

Print a part, its journey: chosen and stepped in the Tour box and nowhere else -- the
header holds no rail of it and ⊞ Windows no entry -- each stage's windows brought
forward and the address holding the stage; a window's tab chosen moves the box and
nothing else, a reload opens the box on the stage the address names, and the box
closed leaves the journey, the windows where they are. An address that names a stage
opens the box on it, and starts no job on the way.
"""

from __future__ import annotations

import re

import httpx
import pytest
import windows
from boards import PRINTER, wears
from garage import open_garage, status
from garage import select as _select
from playwright.sync_api import Page, expect

MAINBOARD = "printer_1.frame_system.mainboard"
BOX = "#tour-pop"
TITLE = f"{BOX} .tour-pop-title"
# The journey the page is on, and the stage the box marks as the one a person is on.
STEP_ON = "() => window.fractalViewer.journey?.step"
STAGE_ON = (
    "() => document.querySelector('#tour-pop .tour-pop-stages [aria-current=step]')?.dataset.stage"
)
NO_SLICE = (
    "No slice of footpedal is kept for printer_1, and a reload starts none: "
    "↻ slices it, as Slice does"
)


@pytest.fixture(scope="module")
def url(start_server):
    """printer_1's board identified and pinned, as the simulated server's is."""
    url = start_server({})
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()
        http.put(
            f"/sites/garage/nodes/{MAINBOARD}/device", json={"identity": PRINTER}
        ).raise_for_status()
    return url


@pytest.fixture(autouse=True)
def no_page_errors(page: Page):
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    yield
    assert errors == [], errors


@pytest.mark.e2e
def test_the_make_view_is_greyed_until_a_machine_is_there(page: Page, url: str):
    """The footpedal chosen and no Machine open: the Print view says what it needs."""
    open_garage(page, url, settle=False)
    _select(page, "footpedal")
    page.locator("#view-menu > summary").click()
    entry = windows.view_entry(page, "make")
    # Greyed as every control the page greys is: its look and "Disabled: <why>".
    expect(entry).to_have_attribute("aria-disabled", "true")
    expect(entry).to_have_attribute("title", re.compile(r"^Disabled: .*footpedal"))
    expect(entry).to_have_css("opacity", "0.45")
    # Pressed all the same, as a person can: aria-disabled alone, which Playwright's own
    # wait for an enabled element counts as disabled.
    entry.click(timeout=5000, force=True)
    said = status(page)
    expect(said).to_contain_text("Print view: ")
    expect(said).to_contain_text("footpedal")
    expect(said).to_have_class(re.compile(r"\berror\b"))
    assert page.evaluate("() => window.fractalViewer.machine") is None


def _machine_open_and_the_part_chosen(page: Page, url: str) -> None:
    """printer_1's Machine open, as its Device section opens it, then the footpedal chosen."""
    open_garage(page, url, settle=False)
    wears(page, "printer_1")
    _select(page, "printer_1")
    page.locator("#selected-body .device-section .dev-open").click()
    windows.machine_ready(page, "printer")
    _select(page, "footpedal")


def _on(page: Page, step: str) -> None:
    """The box done taking the page anywhere, the page's journey and the box on ``step``."""
    expect(page.locator(BOX)).not_to_have_class(re.compile(r"\bbusy\b"), timeout=60000)
    page.wait_for_function(f"(s) => ({STEP_ON})() === s", arg=step, timeout=10000)
    page.wait_for_function(f"(s) => ({STAGE_ON})() === s", arg=f"make/{step}", timeout=10000)


def _stages(page: Page) -> list:
    """The journey's stages as the box shows them: each one's number and name, and
    whether a person is on it."""
    return page.evaluate(
        """() => [...document.querySelectorAll('#tour-pop .tour-pop-stages button')].map((b) =>
            [b.textContent, b.getAttribute('aria-current') === 'step'])"""
    )


def _choose_print_a_part(page: Page, url: str) -> None:
    """Tour, in the header, and Print a part chosen in its box's drop-down."""
    page.locator("#tour-pop-open").click()
    expect(page.locator(BOX)).to_be_visible()
    journeys = httpx.get(f"{url}/tour", timeout=15.0).json()["journeys"]
    at = next(i for i, j in enumerate(journeys) if j["name"] == "Print a part")
    page.locator(f"{BOX} .tour-pop-journeys").select_option(value=str(at))
    _on(page, "choose")


@pytest.mark.e2e
def test_the_make_view_lays_out_the_windows_a_part_is_made_through(page: Page, url: str):
    _machine_open_and_the_part_chosen(page, url)
    page.locator("#view-menu > summary").click()
    entry = windows.view_entry(page, "make")
    expect(entry).not_to_have_attribute("aria-disabled", "true")
    expect(entry).to_have_text("Print")
    entry.click(timeout=5000)
    expect(page.locator(windows.VIEW_MENU)).to_be_hidden()
    expect(status(page)).to_contain_text("The Print view: its windows laid out together")

    # Print comes in front of the Machine's stack once its card has drawn.
    page.wait_for_function(
        "() => window.apothecaryPanels.state('machine-print').shown", timeout=10000
    )
    stacks = {pid: windows.state(page, pid)["stack"] for pid in ("site", "machine", "selected")}
    assert stacks["site"] == ["site", "problems", "pinned", "jobs", "scad"]
    assert stacks["selected"] == ["selected"]
    assert windows.state(page, "part-parameters")["stack"] == ["part-parameters"]
    assert stacks["machine"][:6] == [
        "machine",
        "machine-print",
        "part-feedback",
        "pictures",
        "bench",
        "settings",
    ]
    assert windows.state(page, "machine")["shown"] is False
    assert windows.world_width(page) > page.viewport_size["width"] / 2


@pytest.mark.e2e
def test_print_a_part_is_chosen_and_stepped_in_the_tour_box_and_nowhere_else(page: Page, url: str):
    """The header holds no rail and ⊞ Windows no journey; chosen in the box, its view is
    laid out and it is entered at Choose; › by › to Slice, then Print chosen by its
    number, each stage's window in front and the address holding the stage. (See and
    Measure need a slice: tests/e2e/test_tour.py goes through them, with a slicer.)"""
    _machine_open_and_the_part_chosen(page, url)
    expect(
        page.locator("#journey-rail, .journey-rail, .journey-next, .journey-leave")
    ).to_have_count(0)
    page.locator("#windows-menu > summary").click()
    body = page.locator(".windows-menu-body")
    expect(body.locator(".window-item[data-window]").first).to_be_visible()
    expect(body.locator(".journey-item, [data-journey]")).to_have_count(0)
    assert "journeys" not in [g.lower() for g in body.locator(".spawn-group").all_inner_texts()]
    page.keyboard.press("Escape")
    assert page.evaluate("() => window.fractalViewer.journey") is None

    _choose_print_a_part(page, url)
    expect(page.locator(TITLE)).to_have_text("Print a part · 1. Choose")
    assert _stages(page) == [
        ["1 Choose", True],
        ["2 Shape", False],
        ["3 Slice", False],
        ["4 See", False],
        ["5 Print", False],
        ["6 Measure", False],
    ]
    expect(status(page)).to_contain_text("Print a part › 1 Choose (the tour)")
    assert windows.state(page, "site")["shown"] is True
    assert windows.state(page, "machine")["stack"][:2] == ["machine", "machine-print"]
    expect(page).to_have_url(re.compile(r"[?&]journey=make\b"))
    expect(page).to_have_url(re.compile(r"[?&]step=choose\b"))
    # Still no rail, with a journey entered.
    expect(
        page.locator("#journey-rail, .journey-rail, .journey-next, .journey-leave")
    ).to_have_count(0)

    for step, window, number, label in (
        ("shape", "part-parameters", 2, "Shape"),
        ("slice", "machine-print", 3, "Slice"),
    ):
        page.locator(f"{BOX} .tour-pop-next").click()
        _on(page, step)
        expect(page.locator(TITLE)).to_have_text(f"Print a part · {number}. {label}")
        page.wait_for_function("(w) => window.apothecaryPanels.state(w).shown", arg=window)
        expect(page).to_have_url(re.compile(f"[?&]step={step}\\b"))
        expect(status(page)).to_contain_text(f"Print a part › {number} {label} (the tour)")
    page.locator(f"{BOX} .tour-pop-stages button", has_text="5 Print").click()
    _on(page, "print")
    page.wait_for_function("() => window.apothecaryPanels.state('machine-print').shown")
    assert windows.state(page, "jobs")["shown"] is True
    expect(page).to_have_url(re.compile(r"[?&]step=print\b"))
    expect(status(page)).to_contain_text("Print a part › 5 Print (the tour)")


@pytest.mark.e2e
def test_a_window_chosen_moves_the_box_and_the_box_closed_leaves_the_journey(page: Page, url: str):
    """Parameters' tab pressed moves the box to Shape and no window; Print's to Slice; a
    reload opens the box on Slice with Print in front; folded, the journey stays; ✕
    leaves it, the windows where they are and the address without it; and so does Tour
    pressed again."""
    _machine_open_and_the_part_chosen(page, url)
    _choose_print_a_part(page, url)
    site_shown = windows.state(page, "site")["shown"]
    page.locator(".lm_tab .lm_title", has_text=re.compile(r"^Parameters$")).click()
    _on(page, "shape")
    expect(page.locator(TITLE)).to_have_text("Print a part · 2. Shape")
    assert windows.state(page, "site")["shown"] == site_shown
    expect(page).to_have_url(re.compile(r"[?&]step=shape\b"))
    page.locator(".lm_tab .lm_title", has_text=re.compile(r"^Print$")).click()
    _on(page, "slice")
    expect(page.locator(TITLE)).to_have_text("Print a part · 3. Slice")
    expect(page).to_have_url(re.compile(r"[?&]step=slice\b"))

    page.reload()
    box = page.locator(BOX)
    expect(box).to_be_visible(timeout=20000)
    expect(page.locator(TITLE)).to_have_text("Print a part · 3. Slice")
    _on(page, "slice")
    page.wait_for_function("() => window.apothecaryPanels.state('machine-print').shown")
    expect(status(page)).to_contain_text("Print a part › 3 Slice (the tour)")

    # Folded to its head, the box is open still and the journey is not left.
    box.locator(".tour-pop-head .tour-pop-title").dblclick()
    expect(box).to_have_class(re.compile(r"\bfolded\b"))
    assert page.evaluate(STEP_ON) == "slice"
    expect(page).to_have_url(re.compile(r"[?&]journey=make\b"))
    box.locator(".tour-pop-head .tour-pop-title").dblclick()
    expect(box).not_to_have_class(re.compile(r"\bfolded\b"))

    # Its ✕: the journey left.
    box.locator(".tour-pop-close").click()
    expect(box).to_be_hidden()
    assert page.evaluate("() => window.fractalViewer.journey") is None
    expect(page).not_to_have_url(re.compile(r"[?&](journey|step)="))
    expect(status(page)).to_contain_text("Left Print a part: its windows stay where they are")
    assert windows.state(page, "machine-print")["shown"] is True

    # Opened again it enters nothing; ↻ takes the page to its stage, and Tour pressed
    # again leaves that journey as ✕ did.
    opener = page.locator("#tour-pop-open")
    opener.click()
    expect(box).to_be_visible()
    expect(page.locator(TITLE)).to_have_text("Print a part · 3. Slice")
    assert page.evaluate("() => window.fractalViewer.journey") is None
    expect(page).not_to_have_url(re.compile(r"[?&](journey|step)="))
    box.locator(".tour-pop-put").click()
    _on(page, "slice")
    expect(page).to_have_url(re.compile(r"[?&]journey=make\b"))
    opener.click()
    expect(box).to_be_hidden()
    assert page.evaluate("() => window.fractalViewer.journey") is None
    expect(page).not_to_have_url(re.compile(r"[?&](journey|step)="))
    expect(status(page)).to_contain_text("Left Print a part")
    # And a reload finds no box and no journey.
    page.reload()
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    expect(box).to_be_hidden()
    assert page.evaluate("() => window.fractalViewer.journey") is None


# Where a piece is drawn on the page, from its world bounds' eight corners projected,
# and where the Tour box stands: whether they meet, and the piece's middle.
DRAWN_AND_BOX = """(key) => {
    const v = window.fractalViewer, node = v.renderNodeByKey[key], b = node.world_bounds;
    const r = v.viewRect(), box = document.getElementById('tour-pop').getBoundingClientRect();
    const xs = [], ys = [];
    for (const x of [b.min[0], b.max[0]]) for (const y of [b.min[1], b.max[1]]) for (const z of [b.min[2], b.max[2]]) {
        const s = v.sceneAt(x, y, z).project(v.camera);
        xs.push(r.left + (s.x + 1) / 2 * r.width); ys.push(r.top + (1 - s.y) / 2 * r.height);
    }
    const drawn = { left: Math.min(...xs), right: Math.max(...xs), top: Math.min(...ys), bottom: Math.max(...ys) };
    const meet = drawn.left < box.right && drawn.right > box.left && drawn.top < box.bottom && drawn.bottom > box.top;
    const inView = drawn.left >= r.left - 1 && drawn.right <= r.left + r.width + 1 && drawn.top >= r.top - 1 && drawn.bottom <= r.top + r.height + 1;
    return { meet, inView, drawn, box: box.toJSON(), view: { left: r.left, top: r.top, width: r.width, height: r.height } };
}"""


@pytest.mark.e2e
def test_a_stage_frames_what_it_shows_where_the_box_does_not_cover_it(page: Page, url: str):
    """Design a part chosen in the Tour box: its first stage frames the footpedal, and
    the footpedal is drawn whole in the world's window, clear of the box."""
    open_garage(page, url, settle=False)
    page.locator("#tour-pop-open").click()
    expect(page.locator(BOX)).to_be_visible()
    journeys = httpx.get(f"{url}/tour", timeout=15.0).json()["journeys"]
    at = next(i for i, j in enumerate(journeys) if j["name"] == "Design a part")
    page.locator(f"{BOX} .tour-pop-journeys").select_option(value=str(at))
    expect(page.locator(BOX)).not_to_have_class(re.compile(r"\bbusy\b"), timeout=60000)
    page.wait_for_function("() => window.fractalViewer.journey?.step === 'choose'", timeout=10000)
    page.wait_for_timeout(300)
    seen = page.evaluate(DRAWN_AND_BOX, "footpedal")
    assert seen["inView"], seen
    assert not seen["meet"], seen


@pytest.mark.e2e
def test_the_box_closed_after_a_journey_in_another_site_opens_the_first_site_again(
    page: Page, url: str
):
    """Join a hose stands in the universe: chosen in the box from the garage, the page
    opens it; the box closed, the garage is opened again and the status line says so."""
    open_garage(page, url, settle=False)
    page.locator("#tour-pop-open").click()
    expect(page.locator(BOX)).to_be_visible()
    journeys = httpx.get(f"{url}/tour", timeout=15.0).json()["journeys"]
    at = next(i for i, j in enumerate(journeys) if j["name"] == "Join a hose")
    page.locator(f"{BOX} .tour-pop-journeys").select_option(value=str(at))
    expect(page.locator(BOX)).not_to_have_class(re.compile(r"\bbusy\b"), timeout=60000)
    page.wait_for_function("() => window.fractalViewer.siteName !== 'garage'", timeout=30000)
    page.locator(f"{BOX} .tour-pop-close").click()
    page.wait_for_function("() => window.fractalViewer.siteName === 'garage'", timeout=30000)
    expect(status(page)).to_contain_text(
        "Left Join a hose: garage opened again, where the page was before the tour"
    )


@pytest.mark.e2e
def test_print_a_part_s_shape_shows_its_numbers_and_each_whole(page: Page, url: str):
    """Print a part at Shape, at 1280 by 800: Parameters shows two of the footpedal's
    numbers whole; and in Design a part's view, Selected's position fields hold every
    digit of theirs."""
    page.set_viewport_size({"width": 1280, "height": 800})
    _machine_open_and_the_part_chosen(page, url)
    _choose_print_a_part(page, url)
    page.locator(f"{BOX} .tour-pop-stages button").nth(1).click()
    _on(page, "shape")
    shown = page.evaluate(
        """() => {
            const body = document.querySelector(".panel[data-panel='part-parameters']").closest('.lm_content') || document.querySelector(".panel[data-panel='part-parameters']");
            const r = body.getBoundingClientRect();
            return [...body.querySelectorAll('input[type=range]')].filter((i) => {
                const b = i.getBoundingClientRect();
                return b.height > 0 && b.top >= r.top && b.bottom <= r.bottom;
            }).length;
        }"""
    )
    geo = page.evaluate(
        """() => { const p = document.querySelector(".panel[data-panel='part-parameters']"); const c = p.closest('.lm_content') || p; const r = c.getBoundingClientRect();
          return { win: [r.top, r.height, innerHeight], ranges: [...p.querySelectorAll('input[type=range]')].slice(0, 3).map((i) => Math.round(i.getBoundingClientRect().top)) }; }"""
    )
    assert shown >= 2, (shown, geo)
    # Design a part's view, where Selected is a narrow column beside the world.
    journeys = httpx.get(f"{url}/tour", timeout=15.0).json()["journeys"]
    at = next(i for i, j in enumerate(journeys) if j["name"] == "Design a part")
    page.locator(f"{BOX} .tour-pop-journeys").select_option(value=str(at))
    expect(page.locator(BOX)).not_to_have_class(re.compile(r"\bbusy\b"), timeout=60000)
    page.wait_for_function("() => window.fractalViewer.journey?.id === 'design'", timeout=10000)
    expect(page.locator("#pos-x")).to_be_visible()
    cut = page.evaluate(
        """() => {
            const c = document.createElement('canvas').getContext('2d');
            return ['pos-x', 'pos-y', 'pos-z'].map((id) => document.getElementById(id)).filter((i) => {
                const s = getComputedStyle(i);
                c.font = `${s.fontSize} ${s.fontFamily}`;
                const room = i.clientWidth - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight) - 14;
                return c.measureText(i.value).width > room;
            }).map((i) => [i.id, i.value, i.clientWidth]);
        }"""
    )
    assert cut == [], cut
    page.set_viewport_size({"width": 1280, "height": 720})


@pytest.mark.e2e
def test_a_window_chosen_while_the_page_is_on_its_way_is_followed_once_it_is_there(
    page: Page, url: str
):
    """Slice gone to in the box, and Parameters' tab pressed before the page is there:
    the page arrives at Slice, its Print window brought forward, and then Parameters is
    in front again, the box and the page's journey on Shape, the stage that owns it."""
    _machine_open_and_the_part_chosen(page, url)
    _choose_print_a_part(page, url)
    # The page held on its way: a stage is not gone to until the test lets it.
    page.evaluate(
        """() => {
            const viewer = window.fractalViewer, real = viewer.stageJourney.bind(viewer);
            viewer.stageJourney = async (...given) => {
                await new Promise((go) => { window.letThePageGo = go; });
                return real(...given);
            };
        }"""
    )
    box = page.locator(BOX)
    box.locator(".tour-pop-stages button").nth(2).click()
    expect(page.locator(TITLE)).to_have_text("Print a part · 3. Slice")
    expect(box).to_have_class(re.compile(r"\bbusy\b"))
    page.locator(".lm_tab .lm_title", has_text=re.compile(r"^Parameters$")).click()
    page.wait_for_function("() => window.fractalViewer.chosenOnTheWay === 'part-parameters'")
    # Nothing has moved yet: the box is on the stage it was sent to.
    expect(page.locator(TITLE)).to_have_text("Print a part · 3. Slice")
    page.evaluate("() => window.letThePageGo()")
    _on(page, "shape")
    expect(page.locator(TITLE)).to_have_text("Print a part · 2. Shape")
    expect(page).to_have_url(re.compile(r"[?&]step=shape\b"))
    assert windows.state(page, "part-parameters")["shown"] is True
    # The page did arrive at Slice on the way: its window was brought forward.
    assert windows.state(page, "machine-print")["shown"] is True


@pytest.mark.e2e
def test_an_address_naming_a_journey_and_a_stage_opens_the_box_there_and_starts_no_job(
    page: Page, url: str
):
    """``?journey=make&step=see`` in a browser that has not taken the tour: the box opens
    on Print a part's See, the page taken there as a reload with the box open takes it
    -- printer_1's Machine opened, the footpedal chosen, the stage's window in front --
    and, no slice of the footpedal being kept, none is started: the box says ↻ slices
    it. The journey's view is not laid out: the windows stay as the browser has them."""
    jobs = []

    def asked(request):
        if request.method == "POST" and (
            "/cam/cut" in request.url or "/slicer/slice" in request.url
        ):
            jobs.append(request.url)

    page.on("request", asked)
    page.goto(f"{url}/viewer/sites/garage?journey=make&step=see")
    box = page.locator(BOX)
    expect(box).to_be_visible(timeout=30000)
    expect(page.locator(TITLE)).to_have_text("Print a part · 4. See")
    page.wait_for_function(
        "() => window.fractalViewer.machine?.handle?.kind() === 'printer'"
        " && window.fractalViewer.selectedName === 'footpedal'",
        timeout=60000,
    )
    _on(page, "see")
    page.wait_for_function("() => window.apothecaryPanels.state('machine-print').shown")
    expect(box.locator(".tour-pop-needs")).to_have_text(NO_SLICE)
    assert jobs == []
    # No path is drawn, so the world is on the printer it would be drawn on, clear of
    # the box.
    seen = page.evaluate(DRAWN_AND_BOX, "printer_1")
    assert seen["inView"] and not seen["meet"], seen
    did = [t.strip() for t in box.locator(".tour-pop-did li").all_text_contents()]
    assert not any("its windows laid out" in d for d in did), did
    expect(page).to_have_url(re.compile(r"[?&]journey=make\b"))
    expect(page).to_have_url(re.compile(r"[?&]step=see\b"))
    # Its ✕ leaves it, and the address forgets it, as for a journey chosen in the box.
    box.locator(".tour-pop-close").click()
    expect(page).not_to_have_url(re.compile(r"[?&](journey|step)="))
    expect(status(page)).to_contain_text("Left Print a part")


@pytest.mark.e2e
def test_at_1280_with_a_journey_entered_make_names_what_it_makes_and_stays_in_view(
    page: Page, url: str
):
    """A journey takes no room in the header: at a page 1280 px wide ⚒ Make is whole in
    its row, naming what it makes, with Print a part entered."""
    page.set_viewport_size({"width": 1280, "height": 800})
    _machine_open_and_the_part_chosen(page, url)
    _choose_print_a_part(page, url)
    expect(page.locator("#make-here")).to_have_text(re.compile(r"^⚒ Make footpedal on "))
    expect(page.locator("#make-here")).to_be_in_viewport(ratio=1)
