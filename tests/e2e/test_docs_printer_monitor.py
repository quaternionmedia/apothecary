"""Doc-workflow E2E test for boards and printers in front of the world (Selected's Device
line, a printer's Machine, a devkit's Machine and its Flashing card, the printer monitor's
address, the Bench).

Same on-demand pattern as test_docs_fractal_viewer.py: a plain test run takes
no screenshots; `apothecary docs generate` runs this with `--generate-docs`
and turns the manifest into docs/generated/printer-monitor/printer-monitor.md.

The doc server (apothecary/cli/docs.py) runs with the scripted fake
arduino-cli and the simulated printer mid-print, so every screenshot shows
the same two ports and the same printing state on any machine. Against any
other server -- a plain `pytest tests/e2e --start-server`, which sees the
host's real ports -- this test skips rather than depend on hardware.
"""

import re
import time

import pytest
from playwright.sync_api import Page, expect

BOARD = "printer_1.frame_system.mainboard"
UNO = "/dev/ttyFAKE0"


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
    """Pin the simulated printer to printer_1, see the node follow its state, open
    its Machine and query it, open a devkit's Machine and listen to it, follow the
    printer monitor's address to the printer's Machine, and open the Bench from the
    firmware page's address.
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
        "Open printer_1 › frame_system › mainboard in Site's tree: the board's Device section "
        "offers the detected ports to pin, a Query button, and a box to pin by typed identity"
    )

    section.locator(".dev-pick").select_option("/dev/ttyFAKE1")
    section.locator(".dev-query").click()
    expect(section.locator(".device-query")).to_contain_text("Marlin", timeout=10000)
    docs.step("Query asks the port M115 without pinning it -- a Marlin, so a printer")

    section.locator(".dev-pin").click()
    expect(section.locator(".dev-unpin")).to_be_visible(timeout=8000)
    expect(section.locator(".temps")).to_be_visible(timeout=8000)
    docs.step(
        "Pin it: the section is one line -- the port and what the board is doing, its "
        "state and temperatures -- with Open, its Machine, and Unpin. Its link is held "
        "since the Query, so it is polled once as it is pinned, and the node follows"
    )

    _select(page, "printer_1")
    expect(page.locator("#status-select")).to_have_value("printing", timeout=10000)
    badge = page.locator("#contents-list .contents-item[data-path='printer_1'] .dev-badge")
    expect(badge).to_contain_text("🖨", timeout=5000)
    expect(section).to_contain_text("via frame_system.mainboard")
    page.wait_for_timeout(1500)  # the tree refresh re-fetches meshes; let them land before the shot
    docs.step(
        "The printer followed its board: printer_1's status is now `printing` (the mesh "
        "recolours), its row in Site carries the board's live badge, and its Device "
        "section says which board speaks for it"
    )

    world_badge = page.locator(".world-badge[data-path='printer_1']")
    expect(world_badge).to_contain_text("printing", timeout=10000)
    page.wait_for_timeout(600)
    docs.step(
        "The world wears its machines: a badge stands above the printer in the 3D view -- "
        "state, hotend and bed, progress, a job's stage -- fixed to the printer and following "
        "it as the camera moves; a click selects it. Inside the printer the nozzle marker "
        "sits where the board last said, and a bed reading lies over the bed"
    )

    world_badge.click()
    machine = page.locator(".panel[data-panel='machine']")
    expect(machine.locator("#c-state")).to_contain_text("printing", timeout=10000)
    page.wait_for_timeout(2500)
    docs.step(
        "Click the badge, or Open, or Device › Open on the ring, and the printer's Machine "
        "opens in front of the world: the monitor's own body -- cards, chart, the latch and "
        "control pad, the bed reading, the print from here -- with the board's one log in "
        "it, in a panel tethered to the printer. It is the one place for the board, and "
        "the one thing that polls it: the badges and Selected's line say what its polls "
        "said. Drag it to let go of the tether, or dock it into the rail's strip; the "
        "ring's control verbs go to it"
    )

    machine.locator("#q").fill("M119")
    machine.locator("#qform button").click()
    expect(machine.locator("#log")).to_contain_text("y_min: TRIGGERED", timeout=8000)
    machine.locator("#log").scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    docs.step(
        "The log's query box sends report-only G-code (M119 here) and the answer lands in "
        "the log; anything else is refused, in the log and in the status bar. The polls' "
        "own traffic stays out of the log until its tick-box asks for it"
    )
    page.evaluate("() => window.fractalViewer.closeMachine()")

    # A devkit has a Machine too: the Uno, flashed footpedal by the scripted arduino-cli,
    # is bound to the footpedal node by its sketch.
    task = page.request.post(
        f"{base_url}/firmware/sketches/footpedal/upload",
        data={"fqbn": "arduino:avr:uno", "port": UNO},
    ).json()
    for _ in range(300):
        if (
            page.request.get(f"{base_url}/firmware/tasks/{task['id']}").json()["status"]
            != "running"
        ):
            break
        time.sleep(0.05)
    page.evaluate("() => window.fractalViewer.rescanDevices()")
    devkit = page.locator(".world-badge[data-path='footpedal']")
    expect(devkit).to_be_visible(timeout=10000)
    devkit.click()
    expect(machine.locator("#c-sketch")).to_contain_text("should run footpedal", timeout=8000)
    expect(machine.locator("#c-board")).to_contain_text("not listening")
    machine.locator("#listen").click()
    expect(machine.locator("#log")).to_contain_text("hello", timeout=10000)
    expect(machine.locator("#c-sketch")).to_contain_text("observed", timeout=5000)
    # The sketch at the top of the popup, the Flashing card and the log below it.
    page.evaluate(
        "() => document.querySelector(\"#sketch-card\").scrollIntoView({ block: 'start' })"
    )
    page.wait_for_timeout(1500)
    docs.step(
        "A devkit has a Machine too: its port and board, the sketch it should run against "
        "what it was heard saying (here the scripted board says another sketch's hello, so "
        "they differ) and what changed since it was flashed. Opening it opens no port: "
        "Listen does, saying it may reset the board, and its serial output comes into the "
        "log. Its Flashing card builds the sketch it should run for its board and, asked, "
        "uploads it to this port, its output in the card, then listens for the hello"
    )
    page.evaluate("() => window.fractalViewer.closeMachine()")

    page.goto(f"{base_url}/firmware/monitor?port=/dev/ttyFAKE1")
    expect(page).to_have_url(re.compile(r"/viewer/sites/garage\?machine=%2Fdev%2FttyFAKE1$"))
    expect(page.locator("#c-state")).to_contain_text("printing", timeout=15000)
    page.wait_for_timeout(2 * 2100)  # a few polls, so the chart and log have something to show
    page.locator("#q").fill("M119")
    page.locator("#qform button").click()
    expect(page.locator("#log")).to_contain_text("y_min: TRIGGERED", timeout=8000)
    docs.step(
        "The printer monitor's address, /firmware/monitor?port=, opens the viewer on the "
        "site the port is pinned in with the printer's Machine open in front of the world: "
        "status cards, temperature history, the port's comms log with its query box, and "
        "Reconnect / Reset / Release for the link. A board pinned nowhere opens on the "
        "default site, its Machine floating"
    )

    page.locator("#ctl").check()
    expect(page.locator("#control")).to_be_visible(timeout=5000)
    page.locator("#h-bed").fill("65")
    page.locator("#control button[data-cmd='M140 S{h-bed}']").click()
    expect(page.locator("#c-bed")).to_contain_text("/65°", timeout=8000)
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
    page.wait_for_function(
        "() => { const m = window.fractalViewer.marks['printer_1'];"
        " return m && m.marks && m.marks.mesh(); }",
        timeout=10000,
    )
    page.wait_for_timeout(600)
    docs.step(
        "The reading is drawn in the world too: the printer's marks lay the mesh over its "
        "bed as a relief, stretched so the tilt can be seen and coloured as the heatmap is. "
        "It follows whichever reading the card shows"
    )

    page.locator("#control button[data-cmd='M25']").click()  # the card's print gives way
    expect(page.locator("#c-state")).to_contain_text("idle", timeout=8000)
    page.wait_for_timeout(2300)
    slow = "\n".join(f"G1 X{i} Y{i} E{i / 10:.1f}\nG4 P250" for i in range(1, 61)) + "\n"
    page.locator("#print-file").set_input_files(
        {"name": "bracket.gcode", "mimeType": "text/plain", "buffer": slow.encode()}
    )
    expect(page.locator("#print-pick")).to_contain_text("bracket.gcode · 120 lines", timeout=8000)
    page.once("dialog", lambda d: d.accept())
    page.locator("#print-start").click()
    page.wait_for_function(
        "() => { const j = window.apothecaryMachine.print.job(); return j && j.sent >= 30; }",
        timeout=15000,
    )
    page.locator("#print-card").scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    docs.step(
        "Print from here: a sliced G-code file is kept on the host, checked (no EEPROM "
        "writes, no temperatures over the caps) and streamed to the printer one line per "
        "ok, no SD card needed. Pause stops the feed, Resume needs the latch, Cancel turns "
        "the heaters and fan off and frees the motors; the state card says how far it is, "
        "polls keep coming between lines, and every print is recorded with how it ended"
    )
    page.once("dialog", lambda d: d.accept())
    page.locator("#print-cancel").click()
    expect(page.locator("#print-progress")).to_contain_text("cancelled", timeout=10000)
    page.locator("#control button[data-cmd='M24']").click()
    page.locator("#ctl-disarm").click()

    page.goto(f"{base_url}/firmware")
    expect(page).to_have_url(re.compile(r"/viewer/sites/garage\?panel=bench$"))
    bench = page.locator(".panel[data-panel='bench']")
    expect(bench.locator(".tc-status")).to_contain_text("arduino-cli", timeout=15000)
    expect(bench.locator(".sketch-select option[value='footpedal']")).to_have_count(1)
    page.wait_for_timeout(600)
    docs.step(
        "The firmware page's address, /firmware, opens the viewer with the Bench, a tab of "
        "the rail's strip: the toolchain as installed with Install / Update, the suggested "
        "cores, libraries, the sketches under parts/ each with its board, Compile and "
        "Compile & upload to any detected port, raw flash with esptool, and the task log. "
        "Each verb is a cell of the ring's Panels › Bench too"
    )
