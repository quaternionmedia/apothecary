"""A machine planned before its board is connected: the router's Machine opened with
no board pinned, the coupon's toolpath written for it and drawn over it, kept as its
plan, and chosen again whenever its Machine opens -- with its board, once it is.

Runs against a server of its own with nothing pinned; the simulated router answers on
``/dev/ttyFAKE3`` (``APOTHECARY_SIMULATED_ROUTER``, ``FAKE_ROUTER``) once a test pins it.
Nothing here opens a real port.
"""

from __future__ import annotations

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
DRAWN = (
    "() => { const m = window.fractalViewer.marks['cnc_router'];"
    " return !!(m && m.marks && m.marks.toolpath() && m.marks.toolpath().drawn > 0); }"
)


@pytest.fixture(scope="module")
def url(start_server):
    return start_server(
        env_overrides={
            "APOTHECARY_SIMULATED_ROUTER": ROUTER,
            "APOTHECARY_SIMULATED_SPEED": "0.05",
            "FAKE_ROUTER": "1",
        }
    )


def _machines_known(page: Page) -> None:
    page.wait_for_function(
        "() => window.fractalViewer.machinesHere.some((m) => m.path === 'cnc_router')",
        timeout=15000,
    )


@pytest.mark.e2e
def test_the_router_is_planned_with_no_board_connected(page: Page, url: str):
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    open_garage(page, url, settle=False)
    _machines_known(page)
    # Its Machine, with no board pinned: its plan, not a refusal.
    assert page.evaluate("() => window.fractalViewer.openMachine('cnc_router')") is True
    expect(page.locator("#status")).to_contain_text(
        "Opened cnc_router's Machine with no board connected"
    )
    windows.machine_ready(page, "router")
    expect(windows.in_machine(page, "#print-slice")).to_have_text("Toolpath", timeout=10000)
    expect(windows.in_machine(page, "#ident")).to_contain_text("no board connected")
    # The coupon's toolpath, written for the router by its node.
    windows.in_machine(page, "#print-part").select_option("router_coupon")
    windows.in_machine(page, "#print-slice").click()
    expect(page.locator("#status")).to_contain_text("kept and chosen", timeout=15000)
    expect(windows.in_machine(page, "#print-pick")).to_have_value(re.compile("router_coupon"))
    # ▶ Cut is the board's.
    start = windows.in_machine(page, "#print-start")
    expect(start).to_be_disabled()
    assert "has no board connected" in start.get_attribute("title")
    # Its path drawn over the router, standing on its table.
    page.evaluate("() => window.apothecaryMachine.print.show()")
    page.wait_for_function(DRAWN, timeout=10000)
    assert page.evaluate("() => window.fractalViewer.marks['cnc_router'].plan") is True
    expect(windows.in_machine(page, "#print-preview-said")).to_contain_text(
        "its zero is set at the machine"
    )
    # Kept as its plan.
    windows.in_machine(page, "#print-plan").click()
    expect(page.locator("#status")).to_contain_text("cnc_router's plan kept: router_coupon")
    plan = httpx.get(f"{url}/sites/garage/machines/cnc_router", timeout=15.0).json()["plan"]
    assert plan["part"] == "router_coupon" and plan["kind"] == "router" and plan["file_id"]
    # Closed, its marks go; the Machine view on the router, selected, opens the plan
    # and lands on its path.
    page.evaluate("() => window.fractalViewer.closeMachine()")
    assert page.evaluate("() => window.fractalViewer.marks['cnc_router'] === undefined")
    _select(page, "cnc_router")
    page.evaluate("() => window.fractalViewer.openView('machine')")
    page.evaluate("() => window.fractalViewer.viewDone")
    expect(page.locator("#status")).to_contain_text("path is drawn on cnc_router", timeout=15000)
    page.wait_for_function(DRAWN, timeout=10000)
    assert errors == [], errors


@pytest.mark.e2e
def test_the_plan_is_chosen_when_its_machine_opens_and_when_its_board_is_connected(
    page: Page, url: str
):
    with httpx.Client(base_url=url, timeout=30.0) as http:
        cut = http.post(
            "/cam/cut", json={"part": "router_coupon", "site": "garage", "router": "cnc_router"}
        ).json()
        kept = http.put(
            "/sites/garage/machines/cnc_router/plan",
            json={"part": "router_coupon", "file_id": cut["file_id"]},
        )
        assert kept.status_code == 200, kept.text
        # A router's file kept after it: newer, and not the plan's.
        newer = http.post(
            "/firmware/printers/prints",
            params={"name": "other.nc", "machine": "router"},
            content=b"G21 G90\nG0 X1 Y1\n",
        ).json()
    open_garage(page, url, settle=False)
    _machines_known(page)
    page.evaluate("() => window.fractalViewer.openMachine('cnc_router')")
    windows.machine_ready(page, "router")
    expect(windows.in_machine(page, "#print-part")).to_have_value("router_coupon", timeout=10000)
    expect(windows.in_machine(page, "#print-pick")).to_have_value(cut["file_id"])
    expect(windows.in_machine(page, "#print-plan-said")).to_contain_text("router_coupon")
    page.evaluate("() => window.fractalViewer.closeMachine()")
    # Its board connected and pinned: its Machine is the board's, and the plan is chosen
    # over the newer file.
    with httpx.Client(base_url=url, timeout=30.0) as http:
        http.post("/firmware/devices/identify", json={"port": ROUTER}).raise_for_status()
        http.put(
            f"/sites/garage/nodes/{CONTROLLER}/device", json={"identity": ROUTER}
        ).raise_for_status()
    try:
        page.evaluate("() => window.fractalViewer.boards.scan()")
        wears(page, "cnc_router")
        page.evaluate("() => window.fractalViewer.openMachine('cnc_router')")
        windows.machine_ready(page, "router")
        expect(windows.in_machine(page, "#print-pick")).to_have_value(cut["file_id"], timeout=10000)
        assert newer["id"] != cut["file_id"]
        expect(windows.in_machine(page, "#print-start")).to_be_enabled()
    finally:
        httpx.delete(f"{url}/sites/garage/nodes/{CONTROLLER}/device", timeout=15.0)
