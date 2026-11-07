"""The Procedure window, as a person goes through it on the simulated bench: walkthrough
page 25, written by the test here.

⊞ Windows › Procedure says who the family is and how each step stands. GO on a person's
own step does it. A step's node is a door to the window its work is in, and the status
line says why not where it has none; a step fired opens the section its member works
in, where that Machine is open. GO on a machine's step with its control down is refused
in the member's own words, the node's door right after them, and may be fired again;
with control armed it homes the machine and the next step stands by, because the log
now says the printer is idle. A member's name is a door too. Start over counts all of
that no more.
"""

from __future__ import annotations

import httpx
import pytest
import rings
import windows
from boards import ARDUINO, BOARD, DEVKIT, NODE, PRINTER
from doc_capture import TEMPERATURE, moments
from garage import open_garage
from playwright.sync_api import Page, expect

MACHINE = f"garage:{BOARD}"
BLINK = f"garage:{NODE}"
WITHIN = 15_000
# A flash through the scripted arduino-cli, and a hello heard: a member's work, longer
# than an answer.
WORK = 30_000

STEPS = [
    {
        "number": "1",
        "name": "Check the devkit's lead",
        "discipline": "electrical",
        "node": BLINK,
        "notes": "A person's own step: its GO says the person did it.",
    },
    {
        "number": "2",
        "name": "Flash the devkit",
        "discipline": "firmware",
        "node": BLINK,
        "family": {"board": {"flash": {"port": DEVKIT, "sketch": ARDUINO}}},
    },
    {
        "number": "3",
        "name": "Hear its hello",
        "discipline": "firmware",
        "node": BLINK,
        "family": {"board": {"expect": {"node": BLINK}}},
    },
    {
        "number": "4",
        "name": "Home the printer",
        "discipline": "mechanical",
        "node": MACHINE,
        "notes": "Arm its control in the Machine window first: GO never does.",
        "family": {"machine": {"home": {"node": MACHINE}}},
    },
    {
        "number": "5",
        "name": "See it idle",
        "discipline": "mechanical",
        "waits": {"subject": "garage:printer_1", "property": "state", "value": "idle"},
    },
]


@pytest.fixture(scope="module")
def url(start_server):
    """The simulated Ender idle and pinned, the simulated devkit on its port with the
    scripted arduino-cli to flash it, and a procedure under the garage."""
    url = start_server(
        env_overrides={
            "APOTHECARY_SIMULATED_PRINTER": "idle",
            "APOTHECARY_SIMULATED_SPEED": "0",
            "APOTHECARY_SIMULATED_DEVKIT": "",
            "FAKE_DEVKIT": "1",
        }
    )
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()
        http.put(
            f"/sites/garage/nodes/{BOARD}/device", json={"identity": PRINTER}
        ).raise_for_status()
        http.put("/sites/garage/procedures/bring-up", json={"steps": STEPS}).raise_for_status()
    return url


# What changes from run to run whatever the page does: moments, how long a member took
# to answer, the devkit's log and the flash's output, and the printer's temperatures.
CHANGING = (
    *moments(windows.MACHINE_WINDOWS, "#status", ".world-badge", "#selected-body .device-section"),
    (".procedure-ui", r"\d+ ms"),
    "#log",
    "#flash-task",
    *(
        (where, TEMPERATURE)
        for where in (windows.MACHINE_WINDOWS, ".world-badge", "#selected-body")
    ),
)


def _step(page: Page, number: str):
    return page.locator(f'.procedure-step[data-number="{number}"]')


def _stands(step, status: str, timeout: int = WITHIN) -> None:
    expect(step.locator(".procedure-status")).to_have_text(status, timeout=timeout)


def _machine_of_kind(page: Page, kind: str) -> None:
    """The open board's Machine once it is of this kind, however it was laid out."""
    expect(page.locator(f"{windows.MACHINE} > .machine.kind-{kind}")).to_be_attached(timeout=WITHIN)


@pytest.mark.e2e
def test_a_procedure_through_the_window(page: Page, url: str, walkthrough):
    """Walkthrough page 25: the Procedure window on the simulated bench, each step
    pictured as a person reaches it."""
    story = walkthrough(
        ordinal="25",
        slug="a-procedure-through-the-window",
        title="A procedure through the window",
        intro=(
            "A site's procedure through the Procedure window, as a person goes through it on "
            "the simulated bench: who the family is, GO on a step, a step's node as a door to "
            "the window its work is in, a fire opening the section its member works in, a "
            "machine's step refused in the member's words with its door after them, the "
            "latch armed through that door, and the step fired again. "
            "[docs/family.md](../docs/family.md) is the reference, and "
            "[page 23](23-a-procedure.md) runs a procedure in this process."
        ),
        runtime=(
            "It drives a real browser against a real server of its own, the family's own "
            "members hosted in it. The simulated Ender stands idle on a fake port, pinned to "
            "printer_1's mainboard; the simulated devkit is on another, flashed by the "
            "scripted arduino-cli. Nothing opens a real port."
        ),
        does_not_show=[
            "**Members beside the hub.** carlos and joe are not started here, so no member's "
            "name opens a page in a new tab: the family is the hub's own three.",
            "**The camera's work.** A camera is a pull member, a page's to read, and no step "
            "here fires one.",
            "**What each member answered over time.** The hub's audit is on no window; a "
            "step shows the outcome of its own last fire.",
            "**What changes on every run.** Moments, how long a member took to answer, the "
            "devkit's log and the flash's output are blanked in the pictures.",
        ],
        browser_suite_only=True,
    )
    errors: list = []
    page.on("pageerror", lambda err: errors.append(str(err)))
    open_garage(page, url)
    windows.from_the_windows_menu(page, "procedure")

    # 1. Who the family is, the hub's own among them, and the first step standing by.
    family = page.locator(".procedure-family")
    for member in ("machine", "board", "camera"):
        expect(family).to_contain_text(member, timeout=WITHIN)
    expect(family.locator("button.procedure-member")).to_have_count(2)  # machine and board
    expect(family.locator("span.procedure-member")).to_have_count(1)  # camera, a pull member
    first, second, third, fourth, fifth = (_step(page, n) for n in "12345")
    _stands(first, "standing by")
    expect(first).to_contain_text("A person's own step: its GO says the person did it.")
    expect(first.locator(".procedure-node")).to_have_text(BLINK)
    _stands(second, "waiting")
    expect(second.locator(".procedure-go")).to_have_count(0)
    story.shows(
        "The Procedure, from ⊞ Windows: the family, and the steps",
        "⊞ Windows › Procedure opens the window beside the world. The family is the hub's "
        "own three: machine and board, hosted here, are doors, and camera, a pull member a "
        "page reads, is a name. Each step has its number, its discipline and its node, a "
        "door to the window its work is in; the first stands by with its GO, the rest wait.",
        blank=CHANGING,
    )

    # 2. A person's own step: GO says the person did it.
    first.locator(".procedure-go").click()
    _stands(first, "done")
    _stands(second, "standing by")
    story.says(
        "GO on a person's own step: done, and the next stands by",
        "The first step is a person's own, with nothing handed to a member: its GO says the "
        "person did it, and the flash stands by.",
        shown=(
            f"1 {first.locator('.procedure-status').inner_text()} · "
            f"2 {second.locator('.procedure-status').inner_text()}"
        ),
    )

    # 3. The devkit's door before a port runs its sketch: why not, said.
    second.locator(".procedure-node").click()
    expect(page.locator("#status")).to_contain_text("not connected", timeout=WITHIN)
    expect(page.locator(windows.MACHINE)).to_have_count(0)
    story.says(
        "A node's door with its board not connected: why not, said",
        "esp32_blink's board is pinned but not connected until a port runs its sketch: its "
        "door opens no window, and the status line says so.",
        shown=page.locator("#status").inner_text(),
    )

    # 4. GO flashes the devkit through the board member; the sketch names the board now,
    # so the door opens its Machine.
    second.locator(".procedure-go").click()
    _stands(second, "done", timeout=WORK)
    expect(second.locator(".procedure-outcome")).to_contain_text("board answered 202")
    second.locator(".procedure-node").click()
    _machine_of_kind(page, "devkit")
    expect(page.locator("#status")).to_contain_text(f"Opened {NODE}'s Machine")
    story.shows(
        "GO flashes the devkit through the board member, and its door opens its Machine",
        "GO hands the flash to the board member, which builds the sketch and uploads it to "
        "the devkit's port; the step is done once that work ends, and the outcome says what "
        "the member answered. The devkit's port runs the sketch now, so the node's door "
        "opens its Machine, a tab beside Pictures. No Machine was open when the step fired, "
        "so the fire opened nothing.",
        blank=CHANGING,
    )

    # 5. The hello: the board member listens, and the Log opens where the Machine is open.
    _stands(third, "standing by")
    third.locator(".procedure-go").click()
    _stands(third, "done", timeout=WORK)
    expect(windows.panel(page, "machine-log")).to_be_visible(timeout=WITHIN)
    story.shows(
        "GO hears its hello: the Log opens, where the Machine is open",
        "The board member listens on the port for the sketch's hello, and the step is done "
        "once it is heard. The devkit's Machine being open, the fire opens its Log, the "
        "section the member works in.",
        blank=CHANGING,
    )

    # 6. The printer's step with control down: refused in the member's words, the node's
    # door right after them.
    _stands(fourth, "standing by")
    fourth.locator(".procedure-go").click()
    _stands(fourth, "refused")
    expect(page.locator("#status")).to_contain_text("Step 4: refused")
    expect(fourth.locator(".procedure-why")).to_contain_text("arm its control first")
    expect(fourth.locator(".procedure-outcome")).to_contain_text("machine answered 422")
    expect(fourth.locator(".procedure-why + .meta .procedure-node")).to_have_text(MACHINE)
    _stands(fifth, "waiting")
    story.shows(
        "The printer's step, refused: the member's words, and the node's door after them",
        "GO on the printer's step with its control down is refused in the machine member's "
        "own words, and the node's door stands right after them: the latch is one press "
        "away. The step may be fired again.",
        blank=CHANGING,
    )

    # 7. The door opens the printer's Machine, and control is armed there by hand.
    fourth.locator(".procedure-node").click()
    _machine_of_kind(page, "printer")
    machine = windows.machine(page)
    machine.locator("#ctl").check()
    expect(page.locator("#control")).to_be_visible(timeout=5000)
    story.shows(
        "The door opens the printer's Machine; ⚙ Control armed there",
        "The printer's Machine takes the devkit's place, one Machine at a time. ⚙ Control "
        "arms the latch for five minutes of activity and opens the control pad: GO never "
        "does.",
        blank=CHANGING,
    )

    # 8. GO again: homed through the member, the Status opened, the next standing by.
    fourth.locator(".procedure-go").click()
    _stands(fourth, "done")
    expect(fourth.locator(".procedure-outcome")).to_contain_text("machine answered 202")
    expect(windows.panel(page, "machine-status")).to_be_visible(timeout=WITHIN)
    _stands(fifth, "standing by")
    story.shows(
        "GO again: homed through the member, its Status open, and the next step stands by",
        "Armed, the step goes through: the machine member homes the printer, and the fire "
        "opens the Machine's Status. The next step waits for evidence, the printer idle in "
        "the log, which the homing's poll writes; it stands by.",
        blank=CHANGING,
    )

    # 9. A member's name: the window of the node its next step names.
    family.locator("button.procedure-member[data-member='board']").click()
    _machine_of_kind(page, "devkit")
    story.says(
        "A member's name is a door: board's opens the devkit's Machine",
        "A member hosted here leads to the window of the node its next step names, the last "
        "it worked on when none is left: board's name opens esp32_blink's Machine.",
        shown=page.locator("#status").inner_text(),
    )

    # 10. Start over, and the ring's GO and Start over on the step the window offers.
    page.locator(".procedure-again").click()
    _stands(first, "standing by")
    _stands(second, "waiting")
    rings.on_world(page, "Panels", "Site", "Procedure", "GO")
    _stands(first, "done")
    rings.on_world(page, "Panels", "Site", "Procedure", "Start over")
    _stands(first, "standing by")
    story.says(
        "Start over counts what came before no more; the ring's GO and Start over do the same",
        "Start over puts every step back, what came before staying in the log. The canvas "
        "ring's Panels › Site › Procedure › GO fires the step the window offers it on, and "
        "its Start over is the window's.",
        shown=f"1 {first.locator('.procedure-status').inner_text()}",
    )
    assert errors == []
