"""A part's motion in the viewer: its pieces drawn once and moved, with no OpenSCAD while
it plays, and each gap where the server measured it.

A part whose wrapper declares a motion (``BasePart.motion``) has Part › View › Motion
on its ring: the Motion window (widgets/motion.js), a window of the Part group. Opened,
it asks for the motion's table (``GET /parts/{name}/motion``), draws the still piece and
each moving piece once through OpenSCAD, and from then on only moves them -- Play,
Back, Step, Reset and a slider -- drawing each gap the table follows as a mark where it
is least and reading it as a number, the nearest sample's as the server measured it.

Runs against a server of its own from the conftest's ``start_server``, with this
machine's OpenSCAD; nothing here reaches the network.
"""

from __future__ import annotations

import pytest
import windows
from playwright.sync_api import Page, expect
from rings import labels, on_row

PANEL = ".panel[data-panel='motion']"
RENDERS = ("/stl/generate", "/draft/render", "/draft/check")


@pytest.fixture(scope="module")
def url(start_server):
    return start_server({})


def _open(page: Page, url: str, part: str) -> None:
    page.goto(f"{url}/viewer/sites/apothecary")
    expect(page.locator("#status")).to_contain_text("Loaded", timeout=20000)
    page.evaluate("() => localStorage.removeItem('apothecary.layout')")
    page.wait_for_function("() => !!window.apothecaryRing && !!window.apothecaryPanels", timeout=15000)
    page.locator(f"#contents-list .contents-item[data-path='{part}']").click()


def _drawn(page: Page, part: str) -> None:
    """The Motion window on the part, its pieces drawn."""
    expect(page.locator(PANEL)).to_be_visible(timeout=5000)
    page.wait_for_function(
        "(part) => { const m = window.apothecaryMotion; return m && m.state().ref === part && m.state().drawn; }",
        arg=part,
        timeout=120000,
    )


def _pose_of(page: Page, part: str, piece: str) -> dict:
    return page.evaluate(
        """([part, piece]) => {
            const mesh = window.fractalViewer.meshByName[part];
            const p = mesh.getObjectByName(`piece:${piece}`);
            const marks = mesh.getObjectByName('motion-marks').children.filter((c) => c.isMesh);
            return { at: p.position.toArray(), turn: p.quaternion.toArray(),
                     marks: marks.map((m) => m.position.toArray()) };
        }""",
        [part, piece],
    )


def _moved(a: dict, b: dict) -> bool:
    return any(abs(x - y) > 1e-6 for x, y in zip(a["at"] + a["turn"], b["at"] + b["turn"], strict=True))


@pytest.mark.e2e
def test_the_cycloidal_disc_plays_its_pieces_move_its_marks_travel_and_nothing_renders(page: Page, url: str):
    """Part › View › Motion › Play on the cycloidal disc: the window opens, the stator and
    the disc are drawn once, and while it plays the disc moves and turns, the gap's marks
    travel, and no request for a render is made."""
    _open(page, url, "cycloidal_disc")
    expect(windows.tab(page, "motion")).to_have_count(0)
    on_row(page, "cycloidal_disc", "Part", "View", "Motion", "Play")
    _drawn(page, "cycloidal_disc")
    page.wait_for_function("() => window.apothecaryMotion.state().playing", timeout=10000)
    asked: list[str] = []
    page.on("request", lambda r: asked.append(r.url) if any(k in r.url for k in RENDERS) else None)
    first = _pose_of(page, "cycloidal_disc", "disc")
    page.wait_for_timeout(1200)
    then = _pose_of(page, "cycloidal_disc", "disc")
    assert _moved(first, then), (first, then)
    assert first["marks"] != then["marks"]
    # The output's pins, bought and never printed, turn with the disc.
    output = _pose_of(page, "cycloidal_disc", "output")
    assert output["turn"] != [0, 0, 0, 1]
    assert asked == [], asked
    assert "No force, torque or flux is computed" in page.locator(PANEL).inner_text()


@pytest.mark.e2e
def test_the_number_shown_is_the_servers_at_each_sample(page: Page, url: str):
    """Reset, then Step and Back: at each sample the window reads the gap the server's
    table says there, with its unit, and the slider stands on the sample."""
    _open(page, url, "rolling_rotor")
    on_row(page, "rolling_rotor", "Part", "View", "Motion", "Motion")
    _drawn(page, "rolling_rotor")
    table = page.evaluate("async () => (await fetch('/parts/rolling_rotor/motion')).json()")
    assert [g["name"] for g in table["gaps"]] == ["track", "poles"]
    panel = page.locator(PANEL)
    panel.locator(".motion-reset").click()

    def shown(sample: int) -> None:
        page.wait_for_function(
            "(v) => Math.abs(window.apothecaryMotion.state().value - v) < 1e-9", arg=table["samples"][sample], timeout=5000
        )
        for gap in table["gaps"]:
            row = panel.locator(f"[data-gap='{gap['name']}']")
            expect(row.locator(".motion-gap-value")).to_have_text(f"{gap['least'][sample]:.2f} mm")
            expect(row).to_contain_text(f"orbit {table['samples'][sample]:.1f}°")

    shown(0)
    for _ in range(3):
        panel.locator(".motion-step").click()
    shown(3)
    panel.locator(".motion-back").click()
    shown(2)
    # The ring's Step is the button's: the same verb.
    on_row(page, "rolling_rotor", "Part", "View", "Motion", "Step")
    shown(3)
    assert float(panel.locator(".motion-at").input_value()) == pytest.approx(table["samples"][3])


@pytest.mark.e2e
def test_the_flexures_leaves_are_drawn_from_the_model_at_each_swing(page: Page, url: str):
    """The flexure rotor's hub turns rigidly and its leaves are redrawn from the
    outlines the table carries, which the window says is the model's geometry and not
    a simulation; Bought shows and hides the discs in its pockets."""
    _open(page, url, "flexure_rotor")
    on_row(page, "flexure_rotor", "Part", "View", "Motion", "Motion")
    _drawn(page, "flexure_rotor")
    panel = page.locator(PANEL)
    expect(panel).to_contain_text("drawn from the model's outline at each sample, not simulated")

    def leaves() -> list:
        return page.evaluate(
            "() => [...window.fractalViewer.meshByName['flexure_rotor'].getObjectByName('bent:leaves')"
            ".geometry.attributes.position.array.slice(0, 30)]"
        )

    panel.locator(".motion-reset").click()
    at_rest, hub_at_rest = leaves(), _pose_of(page, "flexure_rotor", "hub")
    for _ in range(8):
        panel.locator(".motion-step").click()
    page.wait_for_function("() => Math.abs(window.apothecaryMotion.state().value + 6) < 1e-9", timeout=5000)
    assert leaves() != at_rest
    hub = _pose_of(page, "flexure_rotor", "hub")
    # The hub turns about the axis it is centred on: it turns, and stays where it is.
    assert hub["turn"] != hub_at_rest["turn"]
    assert hub["at"] == pytest.approx(hub_at_rest["at"], abs=1e-6)
    visible = "window.fractalViewer.meshByName['flexure_rotor'].getObjectByName('bought:pocket insert').visible"
    assert page.evaluate(f"() => {visible}") is True
    panel.locator(".motion-bought").click()
    page.wait_for_function(f"() => !{visible}", timeout=5000)


@pytest.mark.e2e
def test_a_part_without_a_motion_says_so_and_has_no_motion_on_its_ring(page: Page, url: str):
    _open(page, url, "calibration_cube")
    windows.from_the_windows_menu(page, "motion")
    expect(page.locator(PANEL)).to_contain_text("declares no motion", timeout=10000)
    on_row(page, "calibration_cube", "Part", "View")
    shown = labels(page)
    assert "Motion" not in shown and "Fit" in shown
