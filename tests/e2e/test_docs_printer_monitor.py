"""Doc-workflow E2E test for the printer monitor (Device panel, overlay, firmware page).

Same on-demand pattern as test_docs_fractal_viewer.py: a plain test run takes
no screenshots; `apothecary docs generate` runs this with `--generate-docs`
and turns the manifest into docs/generated/printer-monitor/printer-monitor.md.

The doc server (apothecary/cli/docs.py) runs with the scripted fake
arduino-cli and the simulated printer mid-print, so every screenshot shows
the same two ports and the same printing state on any machine. Against any
other server -- a plain `pytest tests/e2e --start-server`, which sees the
host's real ports -- this test skips rather than depend on hardware.
"""

import pytest
from playwright.sync_api import Page, expect

BOARD = "printer_1.frame_system.mainboard"


def _select(page: Page, name: str):
    page.locator("#contents-list .contents-item", has_text=name).first.click()


def _expand_to(page: Page, path: str):
    parts = path.split(".")
    for depth in range(1, len(parts)):
        caret = page.locator(
            f"#contents-list .contents-item[data-path='{'.'.join(parts[:depth])}'] .tree-caret"
        )
        if caret.text_content() == "▸":
            caret.click()
    page.locator(f"#contents-list .contents-item[data-path='{path}']").click()


@pytest.mark.e2e
@pytest.mark.docs
def test_printer_monitor_workflow(page: Page, base_url: str, doc_recorder):
    """Pin the simulated printer to printer_1, watch it, query it, see the
    node follow its state, and poll it from the firmware page.
    """
    devices = page.request.get(f"{base_url}/firmware/devices").json()
    if not any(v["device"]["port"] == "/dev/ttyFAKE1" for v in devices.get("devices", [])):
        pytest.skip(
            "needs the doc server's scripted ports + simulated printer (apothecary docs generate)"
        )
    page.request.post(f"{base_url}/sites/garage/reset")
    page.request.delete(f"{base_url}/sites/garage/nodes/printer_1/device")
    page.request.delete(f"{base_url}/sites/garage/nodes/{BOARD}/device")

    docs = doc_recorder(
        "printer-monitor",
        title="Printer Monitor: a real printer drives its scene node",
        intro=(
            "A 3D-printer mainboard running a G-code firmware (Marlin on a Creality "
            "board, say) is not a board Apothecary programs -- it is one Apothecary "
            "*monitors*. Each printer in the garage carries a `mainboard` node inside "
            "its base enclosure; pin the port there and every poll writes the printer's "
            "state (`idle`, `printing`, `offline`) into the printer Structure's status, "
            "so the mesh recolours in the viewer without anyone editing it. This "
            "walkthrough runs against the simulated printer engine mid-way through "
            "an SD print (`APOTHECARY_SERIAL_ENGINE=simulated`), so it looks the same "
            "on every machine; with a real board the only difference is the port."
        ),
    )

    page.goto(f"{base_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    _expand_to(page, BOARD)
    section = page.locator("#selected-body .device-section")
    expect(section.locator(".dev-pick")).to_be_visible(timeout=10000)
    docs.step(
        "Open printer_1 › frame_system › mainboard in Contents: the board's Device section "
        "offers the detected ports to pin, a Query button, and a box to pin by typed identity"
    )

    section.locator(".dev-pick").select_option("/dev/ttyFAKE1")
    section.locator(".dev-query").click()
    expect(section.locator(".device-query")).to_contain_text("Marlin", timeout=10000)
    docs.step("Query asks the port M115 without pinning it -- a Marlin, so a printer")

    section.locator(".dev-pin").click()
    expect(section).to_contain_text("pinned", timeout=8000)
    expect(section.locator(".temps")).to_be_visible(timeout=8000)
    docs.step(
        "Pin it: the section shows the last poll -- state, temperatures, position, SD progress"
    )

    _select(page, "printer_1")
    expect(page.locator("#status-select")).to_have_value("printing", timeout=10000)
    badge = page.locator("#contents-list .contents-item[data-path='printer_1'] .dev-badge")
    expect(badge).to_contain_text("🖨", timeout=5000)
    expect(section).to_contain_text("via frame_system.mainboard")
    page.wait_for_timeout(1500)  # the tree refresh re-fetches meshes; let them land before the shot
    docs.step(
        "The printer followed its board: printer_1's status is now `printing` (the mesh "
        "recolours), its Contents row carries the board's live badge, and its Device "
        "section says which board speaks for it"
    )

    section.locator(".dev-watch").click()
    expect(page.locator("#serial-body .temp").first).to_be_visible(timeout=10000)
    page.wait_for_timeout(2500)
    docs.step("Watch opens the ⌨ Serial log on that port; it polls every 2 s instead of streaming")

    page.locator("#serial-query").fill("M119")
    page.locator("#serial-query-row button").click()
    expect(page.locator("#serial-body")).to_contain_text("y_min: TRIGGERED", timeout=8000)
    docs.step("The query box sends report-only G-code (M119 here); anything else is refused")

    page.locator("#devices-auto").check()
    page.locator("#devices-interval").select_option("5000")
    page.wait_for_timeout(300)
    docs.step(
        "↻ Devices rescans ports and re-polls bound printers on a schedule, "
        "so a replugged board shows up by itself"
    )

    page.goto(f"{base_url}/firmware/monitor?port=/dev/ttyFAKE1")
    expect(page.locator("#c-state")).to_contain_text("printing", timeout=10000)
    page.wait_for_timeout(2 * 2100)  # a few polls, so the chart and log have something to show
    page.locator("#q").fill("M119")
    page.locator("#qform button").click()
    expect(page.locator("#log")).to_contain_text("y_min: TRIGGERED", timeout=8000)
    docs.step(
        "⤢ Monitor opens the focused view: status cards, temperature history, the port's "
        "full comms log with a query box, and Reconnect / Reset / Release for the link"
    )

    page.locator("#ctl").check()
    expect(page.locator("#control")).to_be_visible(timeout=5000)
    page.locator("#h-bed").fill("65")
    page.locator("#control button[data-cmd='M140 S{h-bed}']").click()
    expect(page.locator("#c-bed")).to_contain_text("/ 65°", timeout=8000)
    page.wait_for_timeout(600)
    docs.step(
        "⚙ Control arms a latch for five minutes of activity and opens the control overlay: "
        "heaters, fan, homing, bounded jogs, SD pause/resume/abort. Here the bed target is set "
        "to 65 °C; the card follows on the next poll and the line is in the log in amber. "
        "Disarmed, nothing on the page can heat or move the machine; E-STOP always can"
    )

    page.once("dialog", lambda d: d.accept())
    page.locator("#level-probe").click()
    expect(page.locator("#mesh .cell")).to_have_count(25, timeout=20000)
    expect(page.locator("#level-job")).to_have_text("", timeout=10000)
    page.locator("#level-card").scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    docs.step(
        "Bed level: Probe bed homes and probes (armed, and asked once), then reads the mesh, "
        "the probe offset and the temperatures and keeps them as a record. The heatmap is "
        "drawn as the bed lies, with its range, tilt and each corner against the mean; the "
        "history lists every reading on the port, and the corner buttons put the nozzle at "
        "paper height for a tramming check. Read mesh does the same without moving"
    )
    page.locator("#ctl-disarm").click()

    page.goto(f"{base_url}/firmware")
    card = page.locator(".device[data-port='/dev/ttyFAKE1']")
    expect(card).to_be_visible(timeout=10000)
    card.locator(".dev-printer").click()
    expect(card.locator(".printer-status")).to_contain_text("printing", timeout=8000)
    card.scroll_into_view_if_needed()
    docs.step("The firmware page's device card identifies the printer and polls it too")
