"""What the router's state asks of a person, read in its Machine and not in its log: a
controller in alarm says what it needs before anything moves, a line that did not go
stays in the Needs you card until one goes, each axis's home says beside its button
which way it will seek and what the port must show first, and the router armed says so
on its badge and its row in Site. Walkthrough page 31 is what it writes.

Runs against a server of its own with the simulated router on ``/dev/ttyFAKE3``, started
in alarm and held to the homing proof as a real one is
(``APOTHECARY_SIMULATED_ROUTER_UNPROVED``). A switch pressed by hand is the bench's
(docs/bench-checklist.md, section I). Nothing here opens a real port.
"""

from __future__ import annotations

import re

import httpx
import pytest
import windows
from boards import wears
from doc_capture import TIME_LEFT, moments
from garage import open_garage
from garage import select as _select
from playwright.sync_api import Page, expect

ROUTER = "/dev/ttyFAKE3"
CONTROLLER = "cnc_router.frame_system.controller"
WITHIN_A_POLL = 6000

# What changes on every run whatever the page does: a moment, the time an armed latch
# has left, the tool's position, and the log.
CHANGING = (
    *moments(windows.MACHINE_WINDOWS, "#status", ".world-badge", "#selected-body .device-section"),
    *(
        (where, TIME_LEFT)
        for where in (
            windows.MACHINE_WINDOWS,
            "#control",
            ".world-badge",
            "#contents-list",
            "#selected-body .device-section",
        )
    ),
    *((f"{windows.MACHINE_WINDOWS} {part}", r"-?\d+\.\d+") for part in ("#c-pos", "#c-pos-s")),
    f"{windows.MACHINE_WINDOWS} #log",
)


@pytest.fixture(scope="module")
def url(start_server):
    url = start_server(
        env_overrides={
            "APOTHECARY_SIMULATED_ROUTER": ROUTER,
            "APOTHECARY_SIMULATED_ROUTER_STATE": "alarm",
            "APOTHECARY_SIMULATED_ROUTER_UNPROVED": "1",
            "APOTHECARY_SIMULATED_SPEED": "0.05",
            "FAKE_ROUTER": "1",
        }
    )
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": ROUTER}).raise_for_status()
        http.put(
            f"/sites/garage/nodes/{CONTROLLER}/device", json={"identity": ROUTER}
        ).raise_for_status()
    return url


def _position(url: str) -> dict:
    return httpx.get(f"{url}/firmware/printers/status", params={"port": ROUTER}).json()["position"]


@pytest.mark.e2e
def test_the_machine_says_what_it_needs_and_what_did_not_go(page: Page, url: str, walkthrough):
    story = walkthrough(
        ordinal="31",
        slug="what-the-router-needs",
        title="What the router needs",
        intro=(
            "What stops a person at the router, read in its Machine and not in its log: a "
            "controller in alarm says what clears it before anything moves, a line that did "
            "not go stays in the **Needs you** card until one goes, each axis's home says "
            "beside its button which way it will seek and what the port must show first, "
            "and a home not proved does not go. [docs/cnc.md](../docs/cnc.md#what-the-state-asks-of-a-person) "
            "is the reference; [page 24](24-a-cut-from-the-card.md) is a cut from the same "
            "Machine once nothing is asked."
        ),
        runtime=(
            "It drives a real browser against a real server of its own. The router is the "
            "simulated GRBL controller on a fake port, pinned to cnc_router's controller, "
            "started in alarm and held to the homing proof as the real one is. Nothing "
            "opens a real port."
        ),
        does_not_show=[
            "**A limit switch pressed.** The simulated router has no switch for a hand to "
            "press, so no home here is proved; pressing each is section I of "
            "[docs/bench-checklist.md](../docs/bench-checklist.md).",
            "**What changes on every run.** Moments, the time an armed latch has left, the "
            "tool's position and the log are blanked in the pictures.",
        ],
        browser_suite_only=True,
    )
    open_garage(page, url, settle=False)
    wears(page, "cnc_router")
    _select(page, "cnc_router")
    page.locator("#selected-body .device-section .dev-open").click()
    windows.machine_ready(page, "router", by_hand=True)
    machine = windows.machine(page)
    needs = machine.locator("#c-needs-card")

    # 1. In alarm: the card is there before anything is asked, saying what clears it.
    expect(needs).to_be_visible(timeout=WITHIN_A_POLL)
    expect(needs).to_contain_text("In alarm")
    expect(needs).to_contain_text("until Unlock ($X) or a home")
    needs.scroll_into_view_if_needed()
    story.shows(
        "In alarm, Needs you says what clears it",
        "cnc_router selected in Site, Open in its Device line, then the canvas ring's "
        "Panels › Windows › Machine view. The controller came up in alarm, and before "
        "anything is asked the Machine's **Needs you** card says so, and that nothing "
        "moves until Unlock (`$X`) or a home.",
        blank=CHANGING,
    )

    # 2. A jog in alarm: the controller's own objection, kept in the card.
    machine.locator("#ctl").check()
    pad = page.locator("#control")
    expect(pad).to_be_visible(timeout=5000)
    pad.locator("button[data-step='1']").click()
    pad.locator("button[data-jog='Z+']").click()
    expect(needs).to_contain_text("$J=G91 G21 Z1", timeout=WITHIN_A_POLL)
    expect(needs).to_contain_text("did not go")
    expect(needs.locator(".need.bad .why")).to_contain_text("error:")
    needs.scroll_into_view_if_needed()
    story.shows(
        "A jog in alarm did not go, and the card keeps why",
        "⚙ Control armed, the pad's step at 1 mm and Z+ pressed. The controller refused "
        "the jog, and the card keeps the line that did not go with the controller's own "
        "error beside it until a line goes.",
        blank=CHANGING,
    )

    # 3. Each axis's home beside its button: not proved, and what to do first.
    z = pad.locator("#ctl-homing .home-axis[data-axis='Z']")
    expect(z).to_contain_text("seeks +Z · switch ✗ · way ✗", timeout=WITHIN_A_POLL)
    expect(z).to_contain_text("first: jog Z 1 mm toward +Z")
    expect(pad.locator("button[data-cmd='HOME-Z']")).to_have_class("unproved")
    pad.locator("#ctl-homing").scroll_into_view_if_needed()
    story.shows(
        "Each axis's home, beside its button: not proved, and what to do first",
        "Under the pad, each axis says which way its home will seek, whether its switch "
        "has been seen and whether the axis has been jogged that way, and what to do "
        "first. A Home not yet proved is outlined.",
        blank=CHANGING,
    )

    # 4. Unlock: nothing is asked of the person any more, and the line that went clears
    #    the one that did not.
    needs.locator(".needs-unlock").click()  # the card's own Unlock: where it says so
    expect(needs).to_be_hidden(timeout=WITHIN_A_POLL)
    story.shows(
        "Unlock in the card: nothing is asked any more",
        "The card's own Unlock sends `$X`. The alarm is cleared, the line that went "
        "clears the one that did not, and the card is gone: nothing is asked of a person "
        "now.",
        blank=CHANGING,
    )

    # 5. A home not proved does not go, and the card says why in the controller's figures.
    before = _position(url)
    pad.locator("button[data-cmd='HOME-Z']").click()
    expect(needs).to_be_visible(timeout=WITHIN_A_POLL)
    expect(needs).to_contain_text("$HZ did not go")
    expect(needs.locator(".need.bad .why")).to_contain_text("home refused: Z will seek +Z at")
    assert _position(url) == before
    needs.scroll_into_view_if_needed()
    story.shows(
        "A home not proved does not go, and the card says why",
        "Home Z pressed before Z has shown its switch or its way. Nothing is sent to the "
        "controller and the router has not moved; the card says `$HZ` did not go, in the "
        "controller's own figures for where Z will seek and how fast.",
        blank=CHANGING,
    )

    # 6. Jogged the way it homes, the axis has shown its way; its switch is the bench's.
    pad.locator("button[data-jog='Z+']").click()
    expect(z).to_contain_text("switch ✗ · way ✓", timeout=WITHIN_A_POLL)
    expect(needs).to_be_hidden(timeout=WITHIN_A_POLL)  # the jog went
    expect(pad.locator("button[data-cmd='HOME-Z']")).to_have_class("unproved")
    story.shows(
        "Jogged the way it homes, Z has shown its way",
        "Z+ pressed: the jog went, so the card is gone, and Z's line says its way is "
        "shown. Its switch is not, so its Home is still outlined; a switch is pressed "
        "by hand at the bench.",
        blank=CHANGING,
    )

    # 7. Armed in its Machine, the router says so on its badge and its row in Site.
    badge = page.locator(".world-badge[data-path='cnc_router']")
    row = page.locator("#contents-list .contents-item[data-path='cnc_router'] .dev-badge")
    expect(badge).to_contain_text(re.compile(r"🔓 armed \d:\d\d"), timeout=WITHIN_A_POLL)
    expect(badge).to_have_class(re.compile(r"\barmed\b"))
    expect(row).to_have_text(re.compile(r"^🪚 🔓 armed \d:\d\d$"))
    expect(row).to_have_class(re.compile(r"\barmed\b"))
    row.scroll_into_view_if_needed()
    story.shows(
        "Armed, the router says so on its badge and its row in Site",
        "Control was armed in the Machine at the second step, and the router's badge in "
        "the world and its row in Site say so, with the time its control has left; "
        "the deck's two long presses arm it the same way.",
        blank=CHANGING,
    )
