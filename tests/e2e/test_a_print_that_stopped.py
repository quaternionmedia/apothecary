"""A print that stopped on its first layer, in the page: its piece's drawer opened by
itself in Part › Feedback where it stopped, a fault filed on that layer, the piece tried
again on a raft, and Site's Jobs opening the Machine and the drawer together
(apothecary/static/widgets/feedback.js, apothecary/cabinet.py; docs/cabinet.md).

Runs against ``apothecary serve --simulated``, started as a person starts it, with the
scripted OrcaSlicer its slicer, each move of its file followed by a dwell so the print
can be stopped part way. The simulated printer_1 prints bed_shims, and the print is
cancelled once a line of its first layer is sent, as a person cancels a first layer that
will not hold. No real port is touched. Walkthrough page 54 is what it writes.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import httpx
import pytest
import windows
from doc_capture import MOMENT
from garage import open_garage
from playwright.sync_api import Page, expect
from rings import on_row
from simulated_process import guarded_env, start_simulated, still_folder, stop
from slicer_helpers import write_fake_orcaslicer
from viewer_ready import settled

from apothecary.firmware.gcode import strip_gcode
from apothecary.simulated import PRINTER

FILE_LAYERS = 4
CHANGING = (
    ("#status", MOMENT),
    (".panel[data-panel^='machine']", MOMENT),
    ("#feedback-piece-said", MOMENT),
)


@pytest.fixture(scope="module")
def simulated(base_url):
    folder = still_folder("print-stopped")
    env = guarded_env(folder)
    env["APOTHECARY_ORCASLICER"] = str(write_fake_orcaslicer(folder / "their-orcaslicer"))
    # Each move followed by a dwell, so a layer takes a second and more to send.
    env["FAKE_ORCA_DWELL"] = "400"
    env["FAKE_ORCA_LAYERS"] = str(FILE_LAYERS)
    url, proc = start_simulated(folder, env)
    state = Path(env["APOTHECARY_CACHE_DIR"]) / "simulated" / "state"
    yield {"url": url, "state": state, "touched": Path(env["APOTHECARY_TEST_SERIAL_GUARD"])}
    stop(proc)


def _first_layer_line(text: str) -> int:
    """How many of the file's lines a print sends before its first layer's first move."""
    lines = text.splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith(";LAYER_CHANGE"))
    return sum(1 for line in lines[:first] if strip_gcode(line)) + 1


def _cancelled_on_its_first_layer(http: httpx.Client, state: Path) -> dict:
    """The running print cancelled once a line of its first layer is sent."""
    deadline = time.monotonic() + 60
    job = http.get("/firmware/printers/print", params={"port": PRINTER}).json()
    text = (state / "prints" / f"{job['file_id']}.gcode").read_text(encoding="utf-8")
    first = _first_layer_line(text)
    while time.monotonic() < deadline:
        job = http.get("/firmware/printers/print", params={"port": PRINTER}).json()
        assert job["running"], job
        if job["sent"] >= first:
            http.post("/firmware/printers/print/cancel", json={"port": PRINTER})
            break
        time.sleep(0.05)
    else:
        raise AssertionError(f"the first layer was never reached: {job}")
    while time.monotonic() < deadline:
        job = http.get("/firmware/printers/print", params={"port": PRINTER}).json()
        if not job["running"]:
            return job
        time.sleep(0.05)
    raise AssertionError(f"the print did not end: {job}")


def _maximised(page: Page, pid: str, row: str):
    """The window ``pid`` maximised from its stack, ``row`` in it scrolled into view, so a
    picture shows it whole; its stack, to restore."""
    panel = windows.panel(page, pid)
    stack = page.locator(".lm_stack", has=panel)
    stack.locator(".lm_maximise").click()
    expect(page.locator(".lm_stack.lm_maximised", has=panel)).to_be_visible(timeout=5000)
    panel.locator(row).scroll_into_view_if_needed()
    return stack


def _restored(page: Page, stack) -> None:
    stack.locator(".lm_maximise").click()
    expect(page.locator(".lm_maximised")).to_have_count(0)


@pytest.mark.e2e
def test_a_print_that_stopped_is_told_where_and_tried_again(page: Page, simulated, walkthrough):
    url, state = simulated["url"], simulated["state"]
    http = httpx.Client(base_url=url, timeout=15.0)
    story = walkthrough(
        ordinal="54",
        slug="a-print-that-stopped",
        title="A print that stopped",
        intro=(
            "A print of bed_shims on printer_1 cancelled on its first layer, as a person "
            "cancels a first layer that will not hold: its piece's drawer opened by itself in "
            "Part › Feedback, saying the layer it stopped on, a fault filed there, the piece "
            "tried again on a raft, and Site's Jobs opening the Machine and the drawer "
            "together. [docs/cabinet.md](../docs/cabinet.md) is the reference."
        ),
        runtime=(
            "It drives a real browser against `apothecary serve --simulated`, started as a "
            "person starts it, with a script that answers as OrcaSlicer's command line does, "
            "each move of its file followed by a dwell so the print is seen running. The "
            "simulated printer prints; the test cancels it once a line of its first layer "
            "is sent."
        ),
        does_not_show=[
            "**Why a first layer does not hold.** A level bed, the mesh on and the first "
            "layer's height are the bench's; the page says where the print stopped and "
            "offers what to slice again with.",
            "**What changes on every run.** Moments are blanked in the pictures.",
        ],
        browser_suite_only=True,
    )

    # Make: bed_shims selected and made on printer_1, sliced in its Print window.
    open_garage(page, url)
    page.locator("#contents-list .contents-item[data-path='bed_shims']").click()
    page.locator("#make-here").click()
    machine = windows.machine(page)
    expect(page.locator("#status")).to_contain_text(
        "bed_shims.gcode kept and chosen", timeout=60000
    )
    # Control armed from printer_1's ring; ▶ Send, asked first; the print begins.
    on_row(page, "printer_1", "Device", "Control", "Arm")
    expect(page.locator("#control")).to_be_visible(timeout=5000)
    page.once("dialog", lambda d: d.accept())
    machine.locator("#print-start").click()
    expect(machine.locator("#print-progress")).to_contain_text("printing", timeout=10000)

    # Cancelled on its first layer: the drawer opens by itself, saying where.
    ended = _cancelled_on_its_first_layer(http, state)
    assert ended["stage"] == "cancelled", ended
    feedback = windows.panel(page, "part-feedback")
    expect(feedback).to_be_visible(timeout=15000)
    said = feedback.locator("#feedback-stopped-said")
    expect(said).to_contain_text(f"cancelled on layer 1 of {FILE_LAYERS}", timeout=15000)
    expect(page.locator("#status")).to_contain_text("its drawer is open in Part › Feedback")
    drawer = http.get("/cabinet", params={"job": ended["job_id"]}).json()["drawer"]
    assert drawer["part"] == "bed_shims", drawer
    expect(feedback.locator("#feedback-piece")).to_have_value(f"drawer:{drawer['id']}")
    stack = _maximised(page, "part-feedback", "#feedback-stopped-row")
    for try_ in ("#feedback-try-probe", "#feedback-try-brim", "#feedback-try-raft"):
        expect(feedback.locator(try_)).to_be_visible()
    # Brim is greyed: bed_shims declares none, its slots being what a brim would fill.
    brim = feedback.locator("#feedback-try-brim")
    expect(brim).to_be_disabled()
    expect(brim).to_have_attribute("title", re.compile("bed_shims declares no brim"))
    # How it was made, and what the board said of its levelling as the print began.
    made = feedback.locator("#feedback-made-said")
    for words in (
        "the part's own values",
        "probe first: G29 once the bed is hot",
        "no skirt",
        "no brim",
        "the board said: levelling on, probe offset Z -3.15",
    ):
        expect(made).to_contain_text(words, timeout=10000)
    settled(page)
    story.shows(
        "Cancelled on its first layer, its drawer open where it stopped",
        "The print is cancelled once a line of its first layer is sent. Its end opens the "
        "piece's drawer in Part › Feedback, which says it was cancelled on layer 1 of the "
        "file's layers and how the piece was made, in the Print window's words: the part's "
        "own values, probe first, no skirt and no brim, as bed_shims declares, and what the "
        "board said of its levelling as the print began -- on, its probe's offset, the "
        "mesh's range and where the probe found the grid. It offers what to try: Probe "
        "first and Raft, each slicing the piece again, and Brim greyed, bed_shims declaring "
        "none. Feedback is maximised here from its stack, so the drawer is seen whole.",
        blank=CHANGING,
    )
    _restored(page, stack)

    # A fault seen, filed on the layer it stopped on.
    feedback.locator("select.seen-read[data-fault='first_layer']").select_option("3")
    feedback.locator("#feedback-seen-keep").click()
    expect(feedback.locator("#feedback-filed")).to_contain_text("look", timeout=10000)
    whole = http.get(f"/cabinet/bed_shims/drawers/{drawer['id']}").json()
    (look,) = [f for f in whole["filed"] if f["kind"] == "look"]
    assert {s["fault"]: s["where"] for s in look["seen"] if s["severity"]} == {
        "first_layer": f"on layer 1 of {FILE_LAYERS}"
    }, look

    # Tried again on a raft: sliced again for printer_1, a raft chosen in its Print window.
    before = {s["file_id"] for s in http.get("/slicer/slices").json()}
    feedback.locator("#feedback-try-raft").click()
    expect(page.locator("#status")).to_contain_text(
        "bed_shims.gcode kept and chosen", timeout=60000
    )
    newest = [s for s in http.get("/slicer/slices").json() if s["file_id"] not in before]
    assert newest and newest[0]["made"]["name"] == "bed_shims", newest
    settings = {s["name"]: s for s in newest[0]["settings"]}
    assert settings["raft_layers"]["value"] == "3", settings["raft_layers"]
    assert "this slice's adhesion 'raft'" in settings["raft_layers"]["source"]
    expect(machine.locator("#print-adhesion")).to_have_value("raft")
    # Its levelling is the part's own, which bed_shims declares: the slice probed first.
    expect(machine.locator("#print-level option:checked")).to_have_text("the part's own")
    assert settings["start"]["value"] == ["home", "probe-each-print"], settings["start"]
    stack = _maximised(page, "machine-print", "#print-adhesion-row")
    settled(page)
    story.shows(
        "Tried again on a raft",
        "First layer, bad, is kept as a look and filed on the layer the print stopped on. "
        "Raft slices the piece again for printer_1 in its Print window, its adhesion row "
        "on a raft and its levelling the part's own, which bed_shims declares probe first; "
        "▶ Send is a person's. Print is maximised here from its stack.",
        blank=CHANGING,
    )
    _restored(page, stack)

    # Disarmed; Site's Jobs, the stopped print's row: its Machine and its drawer.
    on_row(page, "printer_1", "Device", "Control", "Disarm")
    expect(page.locator("#control")).to_be_hidden(timeout=5000)
    badge = page.locator(".world-badge[data-path='printer_1']")
    expect(badge).not_to_contain_text("armed", timeout=10000)
    windows.close(page, "part-feedback")
    expect(windows.panel(page, "part-feedback")).to_be_hidden()
    windows.show(page, "jobs")
    row = page.locator(f"#site-jobs-list li[data-job='{ended['job_id']}']")
    expect(row).to_contain_text("bed_shims.gcode → bed_shims · cancelled")
    row.click()
    expect(windows.panel(page, "machine")).to_be_visible(timeout=10000)
    expect(windows.panel(page, "part-feedback")).to_be_visible(timeout=10000)
    expect(feedback.locator("#feedback-piece")).to_have_value(f"drawer:{drawer['id']}")
    expect(page.locator("#status")).to_contain_text("bed_shims's cabinet in Part › Feedback")
    settled(page)
    story.shows(
        "A job's row opens its Machine and its drawer",
        "Site's Jobs lists the cancelled print. Its row selects printer_1 and opens its "
        "Machine, and opens the piece's drawer in Part › Feedback beside it: the job's own "
        "drawer, chosen among bed_shims's pieces.",
        blank=CHANGING,
    )

    # Nothing left armed, and no real port touched.
    assert http.get("/firmware/printers/armed").json() == {"armed": {}}
    touched = simulated["touched"]
    assert not touched.exists() or not touched.read_text().strip()
