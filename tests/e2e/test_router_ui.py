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

import doc_capture
import httpx
import pytest
import windows
from boards import wears
from doc_capture import moments
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
    return _router_server(start_server, tmp_path_factory)


def _router_server(start_server, tmp_path_factory) -> str:
    """A server with the simulated router at a twentieth of real time, a printer's
    reading in its state folder, the router identified and its controller pinned."""
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


# The page's test runs first, on the module's fresh server: the card it pictures is the
# one a person first meets, with no job run before it.

# --- walkthrough page 24: a cut from the card, as a person goes round it -----------------

# What changes on every run whatever the page does: a moment, a count of lines or a
# percentage as a cut streams, a position as the tool moves, the log and the bar.
STREAMED = r"\d+/\d+ lines|\(\d+(?:\.\d+)?%\)|\b\d+%|\bG\d+(?: [A-Z][\d.-]+)*"
POSITION = r"-?\d+\.\d+"
CHANGING = (
    *moments(windows.MACHINE_WINDOWS, "#status", ".world-badge", "#selected-body .device-section"),
    *(
        (where, STREAMED)
        for where in (
            f"{windows.MACHINE_WINDOWS} #print-progress",
            f"{windows.MACHINE_WINDOWS} #print-history",
            f"{windows.MACHINE_WINDOWS} #c-state-s",
            ".world-badge",
            "#status",
        )
    ),
    *((f"{windows.MACHINE_WINDOWS} {part}", POSITION) for part in ("#c-pos", "#c-pos-s")),
    f"{windows.MACHINE_WINDOWS} #log",
    f"{windows.MACHINE_WINDOWS} #b-print",
)


@pytest.mark.e2e
def test_a_cut_from_the_card_as_a_person_goes_round_it(
    page: Page, start_server, tmp_path_factory, walkthrough
):
    """Walkthrough page 24: the Cut card from makes to a cancelled cut, each control
    there once what it needs holds, pictured at each step. On a server of its own, so
    the card pictured is the one a person first meets, nothing kept and no job run, and
    the module's router stands where its other tests expect it."""
    url = _router_server(start_server, tmp_path_factory)
    story = walkthrough(
        ordinal="24",
        slug="a-cut-from-the-card",
        title="A cut from the card",
        intro=(
            "A cut from the router's Cut card, as a person goes round it: the coupon chosen "
            "under makes, its toolpath written and drawn on the table, kept as the router's "
            "plan, control armed and the work zeroed, the cut streamed, held, resumed and "
            "cancelled. The card shows each control once what it needs holds, and nothing "
            "before. [docs/cnc.md](../docs/cnc.md) is the router's reference and "
            "[docs/cam.md](../docs/cam.md) the toolpath's; "
            "[page 20](20-a-part-through-the-router.md) runs the same loop in this process, "
            "and [page 21](21-a-toolpath-previewed.md) the preview's core."
        ),
        runtime=(
            "It drives a real browser against a real server of its own. The router is the "
            "simulated GRBL controller on a fake port, pinned to cnc_router's controller as "
            "the garage's real one is; its moves take a twentieth of real time. Nothing "
            "opens a real port, and the real router is section I of "
            "[docs/bench-checklist.md](../docs/bench-checklist.md)."
        ),
        does_not_show=[
            "**The real router.** Every line here goes to the simulated controller; the "
            "bench checklist's section I is the same cut on the AnoleX.",
            "**The toolpath's numbers.** What Toolpath writes, pass by pass, and the holes "
            "bored to the tool are [page 20](20-a-part-through-the-router.md)'s.",
            "**A cut run to its end.** The cut is held, resumed and cancelled, so the card's "
            "three verbs are seen; a cut that ends is a job done, listed the same way.",
            "**What changes on every run.** Moments, the lines streamed and the tool's "
            "position are blanked in the pictures.",
        ],
        browser_suite_only=True,
    )
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    open_garage(page, url, settle=False)
    wears(page, "cnc_router")
    _select(page, "cnc_router")
    page.locator("#selected-body .device-section .dev-open").click()
    windows.machine_ready(page, "router", by_hand=True)
    machine = windows.machine(page)
    card = machine.locator("#print-card")
    expect(card.locator("#print-part")).to_be_visible()
    expect(card.locator("#print-file")).to_be_visible()
    for later in (
        "#print-slice",
        "#print-pick",
        "#print-delete",
        "#print-preview-row",
        "#print-plan-row",
        "#print-verbs",
        "#print-progress-row",
    ):
        expect(card.locator(later)).to_be_hidden()
    expect(page.locator("#status")).to_contain_text("No path is drawn: no file is kept yet")
    story.shows(
        "cnc_router's Cut, opened: makes, and Choose File",
        "cnc_router selected in Site, Open in its Device line, then the canvas ring's "
        "Panels › Windows › Machine view: the router's Machine and its windows laid out "
        "together. Its Cut card offers the two ways in, a part under makes or a CAM "
        "post's file from Choose File, and nothing else yet; the status line says so.",
        blank=CHANGING,
    )

    # 2. The coupon under makes: Toolpath and Keep as plan are there, ▶ Cut is not.
    card.locator("#print-part").select_option("router_coupon")
    expect(card.locator("#print-slice")).to_be_visible()
    expect(card.locator("#print-slice")).to_have_text("Toolpath")
    expect(card.locator("#print-plan")).to_be_visible()
    expect(card.locator("#print-verbs")).to_be_hidden()
    story.shows(
        "router_coupon under makes: Toolpath, and Keep as plan",
        "The coupon on the router's table chosen under makes. Toolpath is there, since "
        "the part says how it is cut, and Keep as plan, since there is something to keep. "
        "▶ Cut is not: there is no file yet.",
        blank=CHANGING,
    )

    # 3. Toolpath: the file kept and chosen, the card saying what it holds, the file's
    # row, the preview and ▶ Cut there; the preview moved to the right draws the path.
    card.locator("#print-slice").click()
    expect(page.locator("#status")).to_contain_text("kept and chosen", timeout=15000)
    expect(card.locator("#print-pick option:checked")).to_contain_text(
        "router_coupon-cnc_router.nc"
    )
    expect(card.locator("#print-slice-said")).to_contain_text(
        "router_coupon toolpath for cnc_router"
    )
    for now in ("#print-pick", "#print-delete", "#print-preview-row", "#print-start"):
        expect(card.locator(now)).to_be_visible()
    expect(card.locator("#print-start")).to_be_enabled()
    # The Machine view pressed again lands on the file: its path drawn, all of it, and
    # the world framed on it.
    windows.machine_ready(page, "router", by_hand=True)
    expect(card.locator("#print-preview-said")).to_contain_text("all of it", timeout=10000)
    story.shows(
        "Toolpath writes the coupon's cut: kept, chosen, said, and drawn on the table",
        "Toolpath writes the cut from what the coupon declares, in GRBL's dialect, keeps "
        "it and chooses it: the file's row, its ✕, the preview and ▶ Cut are there now, "
        "and the card says each operation with its passes and what it bored to the tool. "
        "The Machine view, pressed again, lands on the file: all of its path drawn on the "
        "table from the router's work zero, and the world framed on it.",
        blank=CHANGING,
    )

    # 4. Keep as plan: chosen again whenever the Machine opens.
    card.locator("#print-plan").click()
    expect(page.locator("#status")).to_contain_text("cnc_router's plan kept: router_coupon")
    expect(card.locator("#print-plan-said")).to_contain_text(
        "router_coupon, router_coupon-cnc_router.nc"
    )
    story.says(
        "Keep as plan keeps the part and the file as the router's plan",
        "The plan row says what is kept and when. cnc_router's Machine chooses the coupon "
        "and its toolpath whenever it opens, its board connected or not.",
        shown=_words(card.locator("#print-plan-said").inner_text()),
    )

    # 5. Armed: the pad, the probe offered, and the work zeroed where the tool stands.
    machine.locator("#ctl").check()
    expect(page.locator("#control")).to_be_visible(timeout=5000)
    expect(machine.locator("#level-probe")).to_be_visible()
    # The tool over where a stock's corner is touched off, from wherever it stood: the
    # cut's depth under it and the safe height over it, within the travel.
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
    story.shows(
        "⚙ Control armed: the pad, Probe table offered, and the work zeroed",
        "⚙ Control arms the latch for five minutes of activity and opens the control pad, "
        "a loud window beside the world. The Table map's Probe table is there now, since "
        "it moves the machine. The tool jogged over the stock's corner, the pad's XYZ zero "
        "here makes that the work zero, and the path drawn moves with it.",
        blank=CHANGING,
    )

    # 6. ▶ Cut: the cut streams, the operation named; Pause and Cancel while it runs.
    page.once("dialog", lambda d: d.accept())
    card.locator("#print-start").click()
    progress = card.locator("#print-progress")
    expect(progress).to_contain_text(re.compile(r"op \d/4 pass \d/\d: "), timeout=10000)
    expect(card.locator("#print-pause")).to_be_visible()
    expect(card.locator("#print-cancel")).to_be_visible()
    expect(card.locator("#print-resume")).to_be_hidden()
    expect(card.locator("#print-start")).to_be_disabled()
    story.shows(
        "▶ Cut streams it: Pause and Cancel while it runs, the operation named",
        "▶ Cut asks first, then streams the file one line per ok. The progress line names "
        "the operation and the pass the cut is in, the badge in the world says the cut, "
        "and Pause and Cancel are there while it runs; ▶ Cut waits, disabled, until it "
        "ends.",
        blank=CHANGING,
    )

    # 7. Pause: a feed hold, and Resume in Pause's place.
    card.locator("#print-pause").click()
    expect(progress).to_contain_text("paused", timeout=5000)
    expect(machine.locator("#c-state-s")).to_contain_text("Hold", timeout=WITHIN_A_POLL)
    expect(card.locator("#print-resume")).to_be_visible()
    expect(card.locator("#print-pause")).to_be_hidden()
    story.shows(
        "Pause holds the controller: Resume takes Pause's place",
        "Pause is GRBL's feed hold: the controller stops where it is and nothing more is "
        "fed, the state card says Hold, and Resume stands where Pause did.",
        blank=CHANGING,
    )

    # 8. Resume, then Cancel pressed twice: the cut ends, and the card is at rest.
    card.locator("#print-resume").click()
    expect(progress).to_contain_text("running", timeout=10000)
    expect(card.locator("#print-pause")).to_be_visible()
    card.locator("#print-cancel").click()
    expect(page.locator("#status")).to_contain_text("press again to cancel the cut", timeout=5000)
    card.locator("#print-cancel").click()
    expect(progress).to_contain_text("cancelled", timeout=20000)
    expect(machine.locator("#c-state")).to_have_text("idle", timeout=WITHIN_A_POLL)
    expect(card.locator("#print-pause")).to_be_hidden()
    expect(card.locator("#print-cancel")).to_be_hidden()
    expect(card.locator("#print-start")).to_be_enabled()
    expect(card.locator("#print-history")).to_contain_text("cut · router_coupon-cnc_router.nc")
    story.shows(
        "Cancel, pressed twice: the cut ends, and the card is at rest with its history",
        "Cancel asks to be pressed again, then holds and resets the controller: the queue "
        "empties and the spindle is off. The progress line says cancelled, the job is in "
        "the card's history and in Site's Jobs, and ▶ Cut is offered again, the file "
        "still chosen.",
        blank=CHANGING,
    )
    assert errors == []


def _words(text: str) -> str:
    """A line with its moment blanked, so the page's words hold from run to run."""
    return re.sub(doc_capture.MOMENT, "<moment>", text)


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
def test_each_axis_of_the_router_homes_alone_and_only_while_armed(page: Page, url: str):
    """Home X, Home Y and Home Z each send `$HX`, `$HY` or `$HZ` and no other line, and
    only that axis goes back to its switch; disarmed, the pad is not there and the
    controller is refused the line."""
    open_garage(page, url, settle=False)
    wears(page, "cnc_router")
    _select(page, "cnc_router")
    page.locator("#selected-body .device-section .dev-open").click()
    windows.machine_ready(page, "router")
    machine = windows.machine(page)
    expect(page.locator("#control")).to_be_hidden()
    refused = page.request.post(
        f"{url}/firmware/printers/command", data={"port": ROUTER, "command": "$HX"}
    )
    assert refused.status == 409

    machine.locator("#ctl").check()
    pad = page.locator("#control")
    expect(pad).to_be_visible(timeout=5000)

    def machine_position() -> dict:
        return {a: float(v) for a, v in re.findall(r"([XYZ])\s*(-?\d+(?:\.\d+)?)", _where(machine))}

    def sent() -> list:
        return [t for t in _log(page).locator(".tx.control").all_inner_texts()]

    # All three home, then each axis is pulled 10 mm off its switch, so each home that
    # follows has somewhere to come back from.
    pad.locator("button[data-cmd='HOME']").click()
    expect(machine.locator("#c-pos-s")).to_contain_text("X-3.0", timeout=WITHIN_A_POLL)
    pad.locator("button[data-step='10']").click()
    for jog in ("X-", "Y-", "Z-"):
        pad.locator(f"button[data-jog='{jog}']").click()
        expect(_log(page)).to_contain_text(re.compile(rf"> \$J=G91 G21 {jog[0]}-10"), timeout=5000)
    expect(machine.locator("#c-pos-s")).to_contain_text("Z-13.0", timeout=WITHIN_A_POLL)
    assert machine_position() == {"X": -13.0, "Y": -13.0, "Z": -13.0}

    expect_at = {"X": {"X": -3.0, "Y": -13.0, "Z": -13.0}, "Y": {"X": -3.0, "Y": -3.0, "Z": -13.0}}
    expect_at["Z"] = {"X": -3.0, "Y": -3.0, "Z": -3.0}
    for axis in "XYZ":
        before = len(sent())
        home = pad.locator(f"button[data-cmd='HOME-{axis}']")
        expect(home).to_have_attribute(
            "title",
            re.compile(
                rf"^Home {axis} alone \(\$H{axis}\): the other axes stay where they stand\. "
                r"Moves the machine: control must be armed · ⌗\d+$"
            ),
        )
        home.click()
        expect(_log(page)).to_contain_text(f"> $H{axis}", timeout=5000)
        expect(machine.locator("#c-pos-s")).to_contain_text(f"{axis}-3.0", timeout=WITHIN_A_POLL)
        assert machine_position() == expect_at[axis], axis
        assert sent()[before:] == [f"> $H{axis}"], (axis, sent()[before:])
    pad.locator("#ctl-disarm").click()
    expect(pad).to_be_hidden(timeout=3000)


def _where(machine) -> str:
    """The machine position the card shows, as text."""
    return machine.locator("#c-pos-s").inner_text()


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
