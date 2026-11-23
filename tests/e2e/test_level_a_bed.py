"""Level a bed in the page: the tour's journey through printer_1's bed readings, what
its shims fit and the shims, on the Runs, Differences, Fixes and History windows
(apothecary/static/widgets/bed_shims.js, docs/bed-shims.md, "In the page").

Runs against ``apothecary serve --simulated``, started as a person starts it, with the
scripted OrcaSlicer its slicer. The readings are written into that server's state folder
under the board pinned to printer_1, as a bench's two heated probes keep them: a pair
before the shims, made up from printer_1's recorded probe of 2026-09-26 with a probe's
noise of about a hundredth; and, once the Fit stage is reached, a pair after them. Nothing
is heated, probed, armed or printed, and no real port is touched. Walkthrough page 53 is
what it writes.
"""

from __future__ import annotations

import json
import random
import re
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

from apothecary import bed_shims as bs
from apothecary import journeys
from apothecary.firmware import gcode
from apothecary.simulated import PRINTER

BOX = "#tour-pop"
STEP_ON = "() => window.fractalViewer.journey?.step"
VIEWER = "window.fractalViewer"
MARKS = f"{VIEWER}.marks['printer_1'].marks"
RECORDED = [
    [-0.065, -0.055, 0.017, 0.148, 0.740],
    [0.151, 0.178, 0.241, 0.381, 0.638],
    [0.166, 0.200, 0.286, 0.416, 0.698],
    [0.006, 0.033, 0.128, 0.260, 0.495],
    [-0.090, -0.082, -0.000, 0.117, 0.343],
]
SCREW, OUTER = "M3", "11.8"
CHANGING = ((BOX, MOMENT), ("#status", MOMENT), (".panel[data-panel^='machine']", MOMENT))


def _probe(rng: random.Random, grid, lift=None):
    out = []
    for j, row in enumerate(grid):
        out.append(
            [
                round(
                    v + rng.gauss(0, 0.01) + (lift(10 + i * 39.0, 10 + j * 47.5) if lift else 0.0),
                    3,
                )
                for i, v in enumerate(row)
            ]
        )
    return out


def _keep(state: Path, board: str, rid: str, at: str, grid, note: str) -> None:
    folder = state / "leveling"
    folder.mkdir(parents=True, exist_ok=True)
    record = {
        "id": rid,
        "port": PRINTER,
        "board": board,
        "machine": "printer",
        "at": at,
        "method": "probe",
        "mesh": grid,
        "stats": gcode.mesh_stats(grid),
        "bed_c": 60.1,
        "note": note,
        "probe_offset": {"x": -44.0, "y": -10.0, "z": -3.15},
    }
    (folder / f"{rid}.json").write_text(json.dumps(record), encoding="utf-8")


@pytest.fixture(scope="module")
def simulated(base_url):
    folder = still_folder("bed-simulated")
    env = guarded_env(folder)
    env["APOTHECARY_ORCASLICER"] = str(write_fake_orcaslicer(folder / "their-orcaslicer"))
    url, proc = start_simulated(folder, env)
    state = Path(env["APOTHECARY_CACHE_DIR"]) / "simulated" / "state"
    pins = json.loads((state / "firmware-state.json").read_text(encoding="utf-8"))["bindings"]
    board = next(b["identity"] for b in pins if b["path"] == "printer_1.frame_system.mainboard")
    yield {
        "url": url,
        "state": state,
        "board": board,
        "touched": Path(env["APOTHECARY_TEST_SERIAL_GUARD"]),
    }
    stop(proc)


def _taken_to(page: Page, step: str) -> None:
    expect(page.locator(BOX)).not_to_have_class(re.compile(r"\bbusy\b"), timeout=90000)
    page.wait_for_function(f"(s) => ({STEP_ON})() === s", arg=step, timeout=15000)


def _stage(page: Page, label: str, step: str) -> None:
    page.locator(f"{BOX} .tour-pop-stages button", has_text=label).click()
    _taken_to(page, step)


def _shown(page: Page, pid: str) -> None:
    page.wait_for_function(
        "(id) => window.apothecaryPanels.state(id)?.shown", arg=pid, timeout=15000
    )


def _drawn_shims(page: Page) -> dict:
    return page.evaluate(f"() => {VIEWER}.marks['printer_1']?.marks?.shims() ?? null")


@pytest.mark.e2e
def test_a_bed_levelled_through_the_tour(page: Page, simulated, walkthrough):
    url, state, board = simulated["url"], simulated["state"], simulated["board"]
    rng = random.Random(53)
    _keep(
        state,
        board,
        "20261122T120000.000-dev_ttyFAKE1",
        "2026-11-22T12:00:00Z",
        _probe(rng, RECORDED),
        "heated 60 C, soaked 10 min, 1 of 2",
    )
    _keep(
        state,
        board,
        "20261122T120400.000-dev_ttyFAKE1",
        "2026-11-22T12:04:00Z",
        _probe(rng, RECORDED),
        "heated 60 C, soaked 10 min, 2 of 2",
    )
    story = walkthrough(
        ordinal="53",
        slug="a-bed-levelled-in-the-page",
        title="A bed levelled in the page",
        intro=(
            "The tour's *Level a bed* on printer_1: its bed readings in Runs, the second of a "
            "heated pair less the first in Differences, what a shim fits measured and kept, "
            "the shims in Fixes and drawn at their screws in the world, sliced for the "
            "printer, and the pair taken after them set against the pair before in "
            "Differences and History. [docs/bed-shims.md](../docs/bed-shims.md#in-the-page) "
            "is the reference."
        ),
        runtime=(
            "It drives a real browser against `apothecary serve --simulated`, started as a "
            "person starts it, with a script that answers as OrcaSlicer's command line does. "
            "The readings are written into its state folder as a bench keeps them: a heated "
            "pair made up from printer_1's recorded probe of 2026-09-26 with a probe's noise "
            "of about a hundredth, seeded, and a pair after the shims, the shims' lift added "
            "as a rigid plate would take it. The numbers are this page's and no bed's."
        ),
        does_not_show=[
            "**Heating, probing and fitting.** They are a person's, at the printer; the tour "
            "names them at their stages and does none.",
            "**A real bed's readings.** Every probe here is made up; the bench checklist's "
            "boxes take the real ones.",
            "**What changes on every run.** Moments are blanked in the pictures.",
        ],
        browser_suite_only=True,
    )
    box = page.locator(BOX)
    open_garage(page, url)
    page.locator("#tour-pop-open").click()
    level = next(i for i, j in enumerate(journeys.JOURNEYS) if j.id == "level")
    box.locator(".tour-pop-journeys").select_option(value=str(level))
    _taken_to(page, "heat")
    _shown(page, "machine")

    # Probe: Runs, the newest first, each heated; one chosen is drawn over the bed.
    _stage(page, "Probe", "probe")
    runs = windows.panel(page, "bed-runs")
    expect(runs.locator(".bed-run")).to_have_count(2, timeout=20000)
    expect(runs.locator(".bed-run").first).to_have_attribute("data-heated", "heated")
    runs.locator(".bed-run").nth(1).click()
    page.wait_for_function(
        f"(id) => {VIEWER}.marks['printer_1']?.marks?.mesh()?.record_id === id",
        arg="20261122T120000.000-dev_ttyFAKE1",
    )
    settled(page)
    # Probe hot above the runs, the filament's bed temperature filled in.
    expect(runs.locator("#bed-hot-c")).to_have_value("60", timeout=15000)
    runs.locator(".bed-hot").scroll_into_view_if_needed()
    story.shows(
        "Two heated runs, one drawn over the bed",
        "Runs lists printer_1's readings, newest first, each a small heatmap of its grid with "
        "its bed temperature marked heated, its range and its note. The older is chosen, and "
        "drawn over the bed in the world on the Bed mesh layer. Above them, Probe hot holds "
        "the filament's bed temperature and a hold of 90 s.",
        blank=CHANGING,
    )

    # Compare: the second less the first, the floor; the bow against the bound.
    _stage(page, "Compare", "compare")
    diffs = windows.panel(page, "bed-differences")
    expect(diffs.locator("[data-diff='repeatability'] h4")).to_contain_text(
        "the repeatability floor"
    )
    expect(diffs.locator("[data-diff='after']")).to_contain_text("No pair after shims yet")
    expect(diffs.locator("[data-diff='bow']")).to_have_attribute("data-over", "true")
    settled(page)
    story.shows(
        "The floor, and the bow no shim fixes",
        "Differences: the second run less the first, which is the probe's repeatability and "
        "the least a shim must be; no pair after shims yet; and what the plane leaves, the "
        "plate's bow, over the bound for a stored mesh, so no shim brings a reading under it.",
        blank=CHANGING,
    )

    # Measure: bed_shims in Parameters at the shims the readings call for, stood there by
    # Fixes and drawn, not the part's own defaults; the screw chosen and the mount typed,
    # kept.
    _stage(page, "Measure", "measure")
    fixes = windows.panel(page, "bed-fixes")
    expect(fixes.locator(".bed-mount .bed-default")).to_have_count(2, timeout=20000)
    called = httpx.get(f"{url}/bed/garage/printer_1", timeout=15.0).json()["shims"]["params"]
    assert called["thicknesses"] != [0.5, 0.5, 0.5], called
    page.wait_for_function(
        f"(t) => JSON.stringify({VIEWER}.partStages['part:bed_shims']?.staged?.thicknesses)"
        " === JSON.stringify(t)",
        arg=called["thicknesses"],
        timeout=30000,
    )
    assert page.evaluate(f"() => {VIEWER}.variantByPart['bed_shims']"), "drawn as its defaults"
    params = windows.panel(page, "part-parameters")
    params.locator(".param[data-field='screw'] select.param-choice").select_option(label=SCREW)
    params.locator(".param[data-field='outer_d'] .param-number").fill(OUTER)
    expect(page.locator("#stage-summary")).to_contain_text("staged, valid", timeout=15000)
    page.locator("#apply-btn").click()
    expect(page.locator("#status")).to_contain_text(
        re.compile(r"bed_shims (from the cache|regenerated)"), timeout=120000
    )
    fixes.locator("#bed-keep").click()
    expect(page.locator("#status")).to_contain_text(
        "screw hole 3.4 mm (M3), ring 11.8 mm across: kept"
    )
    expect(fixes.locator(".bed-mount .bed-default")).to_have_count(0)
    with httpx.Client(base_url=url, timeout=15.0) as http:
        assert http.get("/bed/garage/printer_1").json()["mount"]["outer_d"] == 11.8
    settled(page)
    story.shows(
        "What a shim fits, measured and kept",
        "bed_shims in Parameters, at the thicknesses the readings call for, which Fixes "
        "stood on the piece: M3 chosen as its bed screw, which sets the hole, and 11.8 "
        "typed as the ring, what calipers read across the mount. Keep mount in Fixes "
        "keeps both as printer_1's, in the state folder; neither is marked a default now.",
        blank=CHANGING,
    )

    # Shims: Fixes and the world; then a reload keeps what was measured.
    _stage(page, "Shims", "shims")
    expect(fixes.locator(".bed-screw")).to_have_count(4)
    drawn = _drawn_shims(page)
    assert drawn and drawn["ring"] == 11.8, drawn
    page.reload()
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=30000)
    _shown(page, "bed-fixes")
    expect(windows.panel(page, "bed-fixes").locator(".bed-mount")).to_have_attribute(
        "data-kept", "true", timeout=20000
    )
    page.wait_for_function(
        f"() => {VIEWER}.marks['printer_1']?.marks?.shims()?.ring === 11.8", timeout=20000
    )
    settled(page)
    story.shows(
        "The shims at their screws, as wide as the mount",
        "Fixes draws the bed from above: each screw where printer_1's profile puts it, the "
        "highest corner with none, a corner under a layer skipped, the others their shim's "
        "thickness. In the world the shims stand at their screws, 11.8 mm across as kept, "
        "after a reload as before it.",
        blank=CHANGING,
    )
    # One stretch for the relief and the shims: a reading of another range drawn over
    # the bed stretches both alike, and the reading drawn is put back.
    drawn_id = page.evaluate(f"() => {MARKS}.mesh().record_id")
    runs = httpx.get(f"{url}/bed/garage/printer_1", timeout=15.0).json()["runs"]
    shown = next(r for r in runs if r["id"] == drawn_id)
    steeper = {**shown, "id": "steeper", "mesh": [[v * 3 for v in row] for row in shown["mesh"]]}
    stretches = page.evaluate(
        f"""(records) => {{ const m = {MARKS}, seen = [];
            for (const r of records) {{ m.setMesh(r); seen.push([m.mesh().exaggeration, m.shims().stretch]); }}
            return seen; }}""",
        [steeper, shown],
    )
    assert stretches[0][0] != stretches[1][0], stretches
    assert all(relief == shim for relief, shim in stretches), stretches

    # Print: Make these, sliced in the Print window; nothing printed.
    _stage(page, "Print", "print")
    windows.panel(page, "bed-fixes").locator("#bed-make").click()
    # Make these says what it did, and the slice's own line takes its place once the
    # file is kept; the picture waits for that line, the last the status bar changes.
    expect(page.locator("#status")).to_contain_text(
        re.compile(r"chosen in printer_1's Print window and sliced|bed_shims\.gcode kept"),
        timeout=60000,
    )
    expect(page.locator("#status")).to_contain_text(
        "bed_shims.gcode kept and chosen", timeout=60000
    )
    expect(windows.panel(page, "machine-print")).to_contain_text("bed_shims", timeout=60000)
    # The file is of the shims drawn: the variant the piece shows, never the part's defaults.
    drawn_variant = page.evaluate(f"() => {VIEWER}.variantByPart['bed_shims']")
    with httpx.Client(base_url=url, timeout=15.0) as http:
        made = [s for s in http.get("/slicer/slices").json() if s["made"]["name"] == "bed_shims"]
    newest = max(made, key=lambda s: s["at"])
    assert drawn_variant and newest["made"]["variant"] == drawn_variant, newest["made"]
    # Sliced to probe first, the bed not yet level, and with the part's brim.
    said = {s["name"]: s for s in newest["settings"]}
    assert said["start"]["value"] == ["home", "probe-each-print"], said["start"]
    assert said["brim_type"]["value"] == "outer_only" and said["brim_width"]["value"] == "3"
    level = windows.panel(page, "machine-print").locator("#print-level")
    expect(level).to_have_value("probe-each-print")
    settled(page)
    story.shows(
        "The shims sliced for the printer",
        "Make these slices bed_shims as it is drawn, at the shims' thicknesses and the "
        "mount kept, for printer_1 in its Print window, where Print a part goes on. ▶ "
        "Print is a person's, armed.",
        blank=CHANGING,
    )

    # Fit, and the pair after: the shims' lift, as a rigid plate takes it.
    _stage(page, "Fit", "fit")
    told = httpx.get(f"{url}/bed/garage/printer_1", timeout=15.0).json()["shims"]["shims"]
    lift = bs.fit_plane([(s["x"], s["y"], s["printed"] or 0.0) for s in told])
    _keep(
        state,
        board,
        "20261122T140000.000-dev_ttyFAKE1",
        "2026-11-22T14:00:00Z",
        _probe(rng, RECORDED, lift.at),
        "heated 60 C, soaked 10 min, shims in, 1 of 2",
    )
    _keep(
        state,
        board,
        "20261122T140400.000-dev_ttyFAKE1",
        "2026-11-22T14:04:00Z",
        _probe(rng, RECORDED, lift.at),
        "heated 60 C, soaked 10 min, shims in, 2 of 2",
    )

    _stage(page, "After", "after")
    page.evaluate("() => window.apothecaryBedShims.load()")
    history = windows.panel(page, "bed-history")
    expect(history.locator(".bed-point")).to_have_count(4, timeout=20000)
    expect(history.locator(".bed-bound")).to_have_attribute("data-bound", "0.3")
    expect(diffs.locator("[data-diff='after'] h4")).to_contain_text("After less before")
    settled(page)
    story.shows(
        "After less before, and the range over the readings",
        "The pair after the shims less the pair before, in Differences, and each reading's "
        "range in History against the bound for a stored mesh: the tilt taken out, the bow "
        "left.",
        blank=CHANGING,
    )

    # Nothing armed, nothing started, no real port touched.
    with httpx.Client(base_url=url, timeout=15.0) as http:
        assert http.get("/firmware/printers/armed").json() == {"armed": {}}
    touched = simulated["touched"]
    assert not touched.exists() or not touched.read_text().strip()


@pytest.mark.e2e
def test_probe_hot_heats_holds_probes_twice_and_turns_the_bed_off(page: Page, simulated):
    """Runs' Probe hot on a simulated printer_1: the filament's bed temperature and a hold of
    90 s filled in, the hold typed down to none, then the bed heated, probed twice -- a
    reading each, noted how and which -- and turned off after, in the Machine's own probe."""
    url = simulated["url"]
    open_garage(page, url)
    on_row(page, "printer_1", "Device", "Open")
    _shown(page, "machine")
    windows.open_window(page, "bed-runs")
    runs = windows.panel(page, "bed-runs")
    expect(runs.locator("#bed-hot-c")).to_have_value("60", timeout=20000)  # Generic PLA's bed
    expect(runs.locator("#bed-soak")).to_have_value("90")
    runs.locator("#bed-soak").fill("0")
    on_row(page, "printer_1", "Device", "Control", "Arm")
    expect(page.locator("#control")).to_be_visible(timeout=5000)
    windows.show(page, "bed-runs")  # in front again, the control pad opened beside it
    asked = []
    page.once("dialog", lambda d: (asked.append(d.message), d.accept()))
    runs.locator("#bed-probe-hot").click()
    second = runs.locator(".bed-run", has_text="heated 60 C, soaked 0 s, 2 of 2")
    expect(second).to_have_count(1, timeout=30000)
    expect(runs.locator(".bed-run", has_text="heated 60 C, soaked 0 s, 1 of 2")).to_have_count(1)
    assert asked and "60 °C" in asked[0] and "probe it twice" in asked[0], asked
    with httpx.Client(base_url=url, timeout=15.0) as http:
        job = http.get("/firmware/printers/level", params={"port": PRINTER}).json()
        assert job["stage"] == "saved" and len(job["record_ids"]) == 2, job
        newest = http.get("/firmware/printers/leveling", params={"port": PRINTER}).json()[:2]
        assert [r["id"] for r in newest] == job["record_ids"][::-1]
        assert all(r["bed_c"] is not None for r in newest)
    with httpx.Client(base_url=url, timeout=15.0) as http:
        log = http.get("/firmware/printers/log", params={"port": PRINTER}).json()["entries"]
    sent = [e["text"] for e in log if e["kind"] == "tx"]
    assert "M190 S60" in sent and sent.index("M190 S60") < sent.index("G29 V3"), sent[-12:]
    assert any(e["text"] == "the bed heated for the reading turned off" for e in log)
    assert "M140 S0" in sent[sent.index("M190 S60") :]
    on_row(page, "printer_1", "Device", "Control", "Disarm")
    expect(page.locator("#control")).to_be_hidden(timeout=5000)
    with httpx.Client(base_url=url, timeout=15.0) as http:
        assert http.get("/firmware/printers/armed").json() == {"armed": {}}
