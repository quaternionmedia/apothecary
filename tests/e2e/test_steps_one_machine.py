"""One Machine per board, a step at a time, as the bench checklist goes on the Ender
(docs/bench-checklist.md, A to E): printer_1's Machine opened from its ring and watched,
a report asked in its one box, control armed, the bed heated and let cool, the head homed
and jogged, docs/validation/dry-run-square.gcode printed from here to its end, control
disarmed and a jog refused; then the devkit's Machine opened in its place, and listened to.

Each step first checks that the page is where the step before it leaves it, then acts as
a person does and holds what the page says. Control lapses after minutes without a
command, so a step that needs it arms it again when it has lapsed, as a person would. In
the suite every step runs in order on a server of the test's own: the simulated printer
idle on ``/dev/ttyFAKE1`` pinned to printer_1's mainboard, and the simulated devkit on
``/dev/ttyFAKE2`` flashed with the Arduino esp32_blink, as the demo's are. Given ``--step
N`` and ``--base-url`` naming the demo, only step N runs, on the demo's walk tab, and the
tab is left there (tests/e2e/stepping.py); its picture is
``.cache/walk/one-machine-step-N.png``::

    uv run pytest tests/e2e/test_steps_one_machine.py --base-url http://127.0.0.1:8000 --step 1
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Callable, List, Tuple

import httpx
import pytest
from playwright.sync_api import Page, expect
from stepping import ROOT, chosen, where
from test_the_firmware_loop import ARDUINO, DEVKIT, MACHINE, NODE
from test_the_loop import _press, _ring_on, _said
from viewer_ready import settled

PRINTER = "/dev/ttyFAKE1"
BOARD = "printer_1.frame_system.mainboard"
DRY_RUN = ROOT / "docs" / "validation" / "dry-run-square.gcode"
WITHIN_A_POLL = 10000  # the Machine polls every 2 s; a slow page gets a few


@dataclass
class Walk:
    """The page a step acts on, the server it is on, and whether it is the demo's tab."""

    page: Page
    base: str
    on_the_demo: bool

    @property
    def machine(self):
        return self.page.locator(MACHINE)

    @property
    def pad(self):
        """The control pad: popped out into the page while armed, the Machine's otherwise."""
        return self.page.locator("#control")

    def on(self, name: str) -> bool:
        """Whether the Machine is open, and is this board's."""
        return (
            self.machine.is_visible() and name in self.machine.locator(".panel-name").inner_text()
        )

    def armed(self) -> None:
        """Control armed: pressed again when it has lapsed, as a person would."""
        if not self.machine.locator("#ctl").is_checked():
            self.machine.locator("#ctl").check()
        expect(self.pad).to_be_visible(timeout=5000)


def open_(w: Walk) -> None:
    """printer_1's ring, Device › Open (⌗78): its Machine docked in the rail, idle, at
    room temperature, the chart filling as it is polled."""
    w.page.goto(f"{w.base}/viewer/sites/garage")
    expect(w.page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    settled(w.page)
    _ring_on(w.page, "printer_1")
    assert _press(w.page, "Device", "Open") == "78"
    expect(w.machine).to_be_visible(timeout=5000)
    expect(w.machine.locator(".panel-name")).to_contain_text("printer_1")
    assert w.page.evaluate("() => window.apothecaryPanels.state('machine').where") == "rail"
    expect(w.machine.locator("#c-state")).to_contain_text("idle", timeout=WITHIN_A_POLL)
    expect(w.machine.locator("#c-hot")).to_contain_text("/0°")
    expect(w.machine.locator("#c-bed")).to_contain_text("/0°")
    expect(w.machine.locator("#chart-span")).not_to_contain_text("no polls", timeout=WITHIN_A_POLL)
    _said(w.page, "Opened printer_1")
    settled(w.page)


def report(w: Walk) -> None:
    """M119 in the Machine's one box: the endstops and the filament, answered in its log."""
    where("Report", "printer_1's Machine open", w.on("printer_1"))
    w.machine.locator("#q").fill("M119")
    w.machine.locator("#qform button").click()
    log = w.machine.locator("#log")
    expect(log).to_contain_text("Reporting endstop status", timeout=8000)
    expect(log).to_contain_text("filament: TRIGGERED")
    log.scroll_into_view_if_needed()


def arm(w: Walk) -> None:
    """⚙ Control: the latch armed and counting down from 5:00, the control pad popped out
    over the world, loud, naming the printer it heats and moves, and printer_1 framed in
    what the pad leaves of the world. A latch still armed from before is let go first."""
    where("Arm", "printer_1's Machine open", w.on("printer_1"))
    if w.machine.locator("#ctl").is_checked():
        w.pad.locator("#ctl-disarm").click()
        expect(w.pad).to_be_hidden(timeout=5000)
    w.machine.locator("#ctl").check()
    expect(w.pad).to_be_visible(timeout=5000)
    expect(w.pad).to_have_class(re.compile(r"\bout\b"))
    expect(w.pad.locator(".head")).to_contain_text("printer_1 armed: it can heat and move")
    expect(w.machine.locator("#ctl-ttl")).to_have_text(re.compile(r"^[45]:\d\d$"), timeout=5000)
    settled(w.page)
    framed = w.page.evaluate(FRAMED, "printer_1")
    assert framed["clear_of_the_pad"] and framed["in_the_world"], framed


# Where a piece's middle is drawn in the page, against the world and the control pad.
FRAMED = """(key) => {
    const v = window.fractalViewer, b = v.renderNodeByKey[key].world_bounds;
    const s = v.sceneAt(...b.min.map((m, i) => (m + b.max[i]) / 2)).project(v.camera);
    const world = v.renderer.domElement.getBoundingClientRect();
    const pad = document.querySelector('#control').getBoundingClientRect();
    const x = world.left + (s.x + 1) / 2 * world.width, y = world.top + (1 - s.y) / 2 * world.height;
    return {
        at: [Math.round(x), Math.round(y)],
        in_the_world: x > world.left && x < world.right && y > world.top && y < world.bottom,
        clear_of_the_pad: x < pad.left || x > pad.right || y < pad.top || y > pad.bottom,
    };
}"""


def heat(w: Walk) -> None:
    """The bed to 45° and Set: M140 S45 sent, the bed card's target 45 within a poll; Off,
    and the target 0 again."""
    where("Heat", "printer_1's Machine open", w.on("printer_1"))
    w.armed()
    bed, control, log = (
        w.machine.locator("#c-bed"),
        w.pad,
        w.machine.locator("#log"),
    )
    control.locator("#h-bed").fill("45")
    control.locator("button[data-cmd='M140 S{h-bed}']").click()
    expect(log.locator(".tx", has_text="M140 S45").last).to_be_visible(timeout=5000)
    expect(bed).to_contain_text("/45°", timeout=WITHIN_A_POLL)
    control.locator("button[data-cmd='M140 S0']").click()
    expect(log.locator(".tx", has_text="M140 S0").last).to_be_visible(timeout=5000)
    expect(bed).to_contain_text("/0°", timeout=WITHIN_A_POLL)
    log.scroll_into_view_if_needed()  # the two lines sent, the chart above them


def motion(w: Walk) -> None:
    """Home XY, then a step of 10 and Y+: the position card at X0 Y0, then Y10, each within
    a poll."""
    where("Motion", "printer_1's Machine open", w.on("printer_1"))
    w.armed()
    pos, control = w.machine.locator("#c-pos"), w.pad
    control.locator("button[data-cmd='G28 X Y']").click()
    expect(pos).to_contain_text("X0.0 Y0.0", timeout=WITHIN_A_POLL)
    control.locator("button[data-step='10']").click()
    control.locator("button[data-jog='Y+']").click()
    expect(pos).to_contain_text("X0.0 Y10.0", timeout=WITHIN_A_POLL)
    pos.scroll_into_view_if_needed()


def print_(w: Walk) -> None:
    """Print from here: the bench's dry run chosen, 23 lines; ▶ Print, after asking, streams
    it to its end, and the state is idle again."""
    where("Print from here", "printer_1's Machine open", w.on("printer_1"))
    w.armed()
    card = w.machine.locator("#print-card")
    card.locator("#print-file").set_input_files(str(DRY_RUN))
    expect(card.locator("#print-pick option:checked")).to_contain_text(
        "dry-run-square.gcode · 23 lines", timeout=8000
    )
    asked: List[str] = []
    w.page.once("dialog", lambda d: (asked.append(d.message), d.accept()))
    card.locator("#print-start").click()
    progress = card.locator("#print-progress")
    expect(progress).to_contain_text("dry-run-square.gcode · printing", timeout=10000)
    assert asked and asked[0].startswith(f"Print dry-run-square.gcode on {PRINTER}"), asked
    expect(progress).to_contain_text("dry-run-square.gcode · done · 23/23", timeout=60000)
    expect(card.locator("#print-history")).to_contain_text("dry-run-square.gcode · done")
    expect(w.machine.locator("#c-state")).to_contain_text("idle", timeout=WITHIN_A_POLL)
    card.scroll_into_view_if_needed()


def disarm(w: Walk) -> None:
    """🔒 Disarm: the overlay closed; the ring's Control › Jog › Y+ (⌗7728) then refused,
    said in the status bar as an error."""
    where("Disarm", "printer_1's Machine open", w.on("printer_1"))
    if w.machine.locator("#ctl").is_checked():
        w.pad.locator("#ctl-disarm").click()
    expect(w.pad).to_be_hidden(timeout=5000)
    _ring_on(w.page, "printer_1")
    assert _press(w.page, "Device", "Control", "Jog", "Y+") == "7728"
    status = w.page.locator("#status")
    expect(status).to_contain_text("not armed", timeout=5000)
    expect(status).to_have_class(re.compile(r"\berror\b"))


def devkit(w: Walk) -> None:
    """esp32_blink's ring, Device › Open: the one Machine is the devkit's now, saying what it
    should run, and no port opened until Listen."""
    where("The devkit's Machine", "printer_1's Machine open", w.on("printer_1"))
    _ring_on(w.page, NODE)
    _press(w.page, "Device", "Open")
    expect(w.machine).to_have_count(1)
    expect(w.machine.locator(".panel-name")).to_contain_text(NODE, timeout=5000)
    expect(w.machine.locator("#c-board")).to_contain_text(DEVKIT)
    expect(w.machine.locator("#c-sketch")).to_contain_text(f"should run {NODE}@", timeout=8000)
    expect(w.machine.locator("#listen")).to_be_visible()
    expect(w.pad).to_be_hidden()
    assert not w.page.evaluate(f"() => !!window.fractalViewer.boards.board('{DEVKIT}').stream")
    settled(w.page)


def listen(w: Walk) -> None:
    """Listen: the port opened and the hello, the chip line and a blink in the one log;
    Release lets it go."""
    where("Listen", "esp32_blink's Machine open", w.on(NODE))
    log = w.machine.locator("#log")
    w.machine.locator("#listen").click()
    expect(log).to_contain_text("apothecary esp32_blink: hello", timeout=10000)
    expect(log).to_contain_text("chip: ESP32-D0WD-V3")
    expect(log).to_contain_text("blink 1")
    w.machine.locator("#release").click()
    w.page.wait_for_function(
        f"() => !window.fractalViewer.boards.board('{DEVKIT}').stream", timeout=5000
    )
    log.scroll_into_view_if_needed()


STEPS: List[Tuple[str, Callable[[Walk], None]]] = [
    ("Device › Open: printer_1's Machine", open_),
    ("A report in the one box", report),
    ("⚙ Control armed", arm),
    ("The bed heated, then off", heat),
    ("Home XY, then Y+", motion),
    ("The dry run printed from here", print_),
    ("Disarmed, a jog refused", disarm),
    ("The devkit's Machine", devkit),
    ("Listen", listen),
]


@pytest.fixture
def steps(request, base_url):
    """One step on the demo's walk tab under --step; every step on a server of the
    test's own otherwise (stepping.chosen)."""

    def own():
        return request.getfixturevalue("page"), request.getfixturevalue("own_server")

    yield from chosen(request, base_url, "one-machine", STEPS, own)


@pytest.fixture
def own_server(start_server):
    """The test's own server, as the demo is: the simulated printer idle on
    ``/dev/ttyFAKE1``, identified and pinned to printer_1's mainboard, and the simulated
    devkit on ``/dev/ttyFAKE2`` flashed with the Arduino esp32_blink, which binds the
    garage's esp32_blink to it."""
    url = start_server(
        {
            "APOTHECARY_SIMULATED_PRINTER": "idle",
            "APOTHECARY_SIMULATED_DEVKIT": "",
            "FAKE_DEVKIT": "1",
        }
    )
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()
        http.put(
            f"/sites/garage/nodes/{BOARD}/device", json={"identity": PRINTER}
        ).raise_for_status()
        task = http.post(
            f"/firmware/sketches/{ARDUINO}/upload",
            json={"fqbn": "esp32:esp32:esp32", "port": DEVKIT},
        )
        task.raise_for_status()
        deadline = time.monotonic() + 30
        while (done := http.get(f"/firmware/tasks/{task.json()['id']}").json())[
            "status"
        ] == "running":
            assert time.monotonic() < deadline, done
            time.sleep(0.05)
    assert done["status"] == "succeeded", done
    return url


@pytest.mark.e2e
def test_one_machine_a_step_at_a_time(steps):
    page, url, on_the_demo, numbers = steps
    walk = Walk(page, url, on_the_demo)
    for n in numbers:
        STEPS[n - 1][1](walk)
