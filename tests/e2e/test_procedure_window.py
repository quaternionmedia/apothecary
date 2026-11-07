"""The Procedure window, as a person goes through it on the simulated bench.

⊞ Windows › Procedure says who the family is and how each step stands. GO on a person's
own step does it; GO on a machine's step with its control down is refused in the
member's own words and may be fired again; with control armed it homes the machine and
the next step stands by, because the log now says the printer is idle. Start over
counts all of that no more.
"""

from __future__ import annotations

import httpx
import pytest
import rings
import windows
from boards import BOARD, PRINTER
from garage import open_garage
from playwright.sync_api import Page, expect

MACHINE = f"garage:{BOARD}"
WITHIN = 15_000

STEPS = [
    {
        "number": "1",
        "name": "Check the lead",
        "discipline": "electrical",
        "node": "garage:esp32_blink",
        "notes": "A person's own step.",
    },
    {
        "number": "2",
        "name": "Home the printer",
        "discipline": "mechanical",
        "node": MACHINE,
        "family": {"machine": {"home": {"node": MACHINE}}},
    },
    {
        "number": "3",
        "name": "See it idle",
        "discipline": "mechanical",
        "waits": {"subject": "garage:printer_1", "property": "state", "value": "idle"},
    },
]


@pytest.fixture(scope="module")
def url(start_server):
    """The simulated Ender idle and pinned, and a procedure under the garage."""
    url = start_server(
        env_overrides={"APOTHECARY_SIMULATED_PRINTER": "idle", "APOTHECARY_SIMULATED_SPEED": "0"}
    )
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()
        http.put(
            f"/sites/garage/nodes/{BOARD}/device", json={"identity": PRINTER}
        ).raise_for_status()
        http.put("/sites/garage/procedures/bring-up", json={"steps": STEPS}).raise_for_status()
    return url


def _step(page: Page, number: str):
    return page.locator(f'.procedure-step[data-number="{number}"]')


@pytest.mark.e2e
def test_a_procedure_through_the_window(page: Page, url: str):
    errors = []
    page.on("pageerror", lambda err: errors.append(str(err)))
    open_garage(page, url)
    windows.open_window(page, "procedure")

    # Who the family is, the hub's own among them.
    family = page.locator(".procedure-family")
    for member in ("machine", "board", "camera"):
        expect(family).to_contain_text(member, timeout=WITHIN)

    first, second, third = (_step(page, n) for n in "123")
    expect(first.locator(".procedure-status")).to_have_text("standing by", timeout=WITHIN)
    expect(first).to_contain_text("A person's own step.")
    expect(second.locator(".procedure-status")).to_have_text("waiting")
    expect(second.locator(".procedure-go")).to_have_count(0)

    first.locator(".procedure-go").click()
    expect(first.locator(".procedure-status")).to_have_text("done", timeout=WITHIN)
    expect(second.locator(".procedure-status")).to_have_text("standing by", timeout=WITHIN)

    # Control down: the member's own words, and it may be fired again.
    second.locator(".procedure-go").click()
    expect(second.locator(".procedure-status")).to_have_text("refused", timeout=WITHIN)
    expect(page.locator("#status")).to_contain_text("Step 2: refused")
    expect(second.locator(".procedure-why")).to_contain_text("arm its control first")
    expect(second.locator(".procedure-outcome")).to_contain_text("machine answered 422")
    expect(third.locator(".procedure-status")).to_have_text("waiting")

    httpx.post(
        f"{url}/firmware/printers/control", json={"port": PRINTER, "armed": True}, timeout=15.0
    ).raise_for_status()
    second.locator(".procedure-go").click()
    expect(second.locator(".procedure-status")).to_have_text("done", timeout=WITHIN)
    expect(second.locator(".procedure-outcome")).to_contain_text("machine answered 202")

    # Homing polled, so the log says the printer is idle, and the next stands by.
    expect(third.locator(".procedure-status")).to_have_text("standing by", timeout=WITHIN)

    page.locator(".procedure-again").click()
    expect(first.locator(".procedure-status")).to_have_text("standing by", timeout=WITHIN)
    expect(second.locator(".procedure-status")).to_have_text("waiting")

    # The ring's GO fires the step the window offers it on, and its Start over the same.
    rings.on_world(page, "Panels", "Site", "Procedure", "GO")
    expect(first.locator(".procedure-status")).to_have_text("done", timeout=WITHIN)
    rings.on_world(page, "Panels", "Site", "Procedure", "Start over")
    expect(first.locator(".procedure-status")).to_have_text("standing by", timeout=WITHIN)
    assert errors == []
