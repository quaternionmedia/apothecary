"""The Loops window: a heater loop of the printer whose Machine is open, in the page
(apothecary/static/widgets/loops.js, docs/control-loops.md, "The Loops window").

It opens from ⊞ Windows and from the ring's Panels › Machine › Loops. It shows the
newest kept experiment of the loop chosen: what the board holds beside the controller a
rule designs, the margins and the step's measures as the document says them, and the
plots of the server's curves, every mark where the answer names it. Start stays greyed
with the server's reason until a ceiling and a longest time are typed; a step's progress
comes from the surfaces' stream; Cancel ends one with the heaters off; Set on machine
sends the designed gains and shows them read back. Nothing offers to save to the board's
memory, and a refused act says the server's reason.

Runs against a server of its own: the simulated printer idle on its port, its heaters
modelled (``APOTHECARY_SIMULATED_HEATERS=model``) and run five times faster than real
time, so a step takes half a minute; and in its state folder a step kept before the page
opens, recorded in this process from the simulated hotend itself under the board's own
gains, stepped in its own time with its noise seeded, so its figures and curves -- the
window's pictures -- are the same on every run. Nothing here opens a real port.
"""

from __future__ import annotations

import json
import re
import time

import httpx
import pytest
import rings
import windows
from boards import PRINTER
from doc_capture import moments
from playwright.sync_api import Page, expect

from apothecary.firmware import gcode
from apothecary.loop_document import Figure, format_value

SPEED = 5  # the simulated heaters' seconds to one of the clock's
KEPT = "20260101T000000000Z-dev_ttyFAKE1"  # older than any experiment a test runs
LOOPS = ".panel[data-panel='loops']"
# A step short enough to watch: from cold to 60 °C, settled there ten seconds, stepped to
# 65 and held twenty, read every half second -- two and a half simulated minutes on the
# sped-up heater, whose lag is then eighteen seconds and its dead time over half a second,
# more than a sample: a dead time shorter than a sample is fitted as none.
QUICK = {"base_c": "60", "step_c": "5", "settle_s": "10", "after_s": "20", "sample_period_s": "0.5"}
CEILING, LONGEST = "230", "120"
UNSTATED = "an experiment states its ceiling and its longest time, every time"
# What differs on every run whatever the page does: the moments in the windows and the
# status line; the board's own windows (its latch counting down, its temperatures and
# their chart, its log) and its armed pad, whole; the world's badges, which wear the
# board's temperatures.
STILL = (
    *moments(".panel", "#status"),
    ".panel[data-panel^='machine']",
    "#control",
    ".world-badge",
)


def _kept_step(port: str) -> dict:
    """A step of the simulated hotend as an experiment the server keeps: the simulator's
    own heater (``gcode.SimulatedHeater``, its plant, its noise seeded by the port, the
    board's own gains round it) settled at 180 °C, stepped to 185 at ten minutes and held
    until a thousand seconds, read once a second as M105 says it -- the reading to the
    hundredth, the power a whole count. The simulator's numbers, no heater's."""
    heater = gcode.simulated_heaters(port)["T"]
    heater.settle_at(180.0)
    t, target, actual, power = [], [], [], []
    for second in range(1001):
        if second == 600:
            heater.target = 185.0
        t.append(float(second))
        target.append(heater.target)
        actual.append(round(heater.reading(), 2))
        power.append(float(round(heater.power)))
        for _ in range(round(1 / heater.dt)):
            heater.step()
    return {
        "id": KEPT,
        "kind": "step",
        "started_at": "2026-01-01T00:00:00+00:00",
        "sample_period_s": 1.0,
        "ceiling_c": 200.0,
        "max_duration_s": 1200.0,
        "parameters": {
            "base_c": 180.0,
            "step_c": 5.0,
            "settle_s": 600.0,
            "after_s": 400.0,
            "heater": "hotend",
            "index": 0,
        },
        "outcome": "done",
        "reason": None,
        "job": KEPT,
        "samples": {"t": t, "target": target, "actual": actual, "power": power},
        "lines": [],
        "port": port,
        "result": None,
        "firmware": gcode.SimulatedPrinter.FIRMWARE,
        "identity": None,
    }


@pytest.fixture(scope="module")
def url(start_server, tmp_path_factory):
    state = tmp_path_factory.mktemp("loops-state") / "state"
    (state / "loops").mkdir(parents=True)
    (state / "loops" / f"{KEPT}.json").write_text(json.dumps(_kept_step(PRINTER)), encoding="utf-8")
    url = start_server(
        env_overrides={
            "APOTHECARY_STATE_DIR": str(state),
            "APOTHECARY_SIMULATED_PRINTER": "idle",
            "APOTHECARY_SIMULATED_HEATERS": "model",
            "APOTHECARY_SIMULATED_HEATER_SPEED": str(SPEED),
        }
    )
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()
    return url


def _http(url: str) -> httpx.Client:
    return httpx.Client(base_url=url, timeout=30.0)


@pytest.fixture(autouse=True)
def _as_it_starts(url):
    """Each test starts and ends with no experiment running and the latch down."""

    def start_over():
        with _http(url) as http:
            http.post("/firmware/printers/loops/cancel", json={"port": PRINTER})
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if (
                    not http.get("/firmware/printers/loops/job", params={"port": PRINTER})
                    .json()
                    .get("running")
                ):
                    break
                time.sleep(0.3)
            http.post("/firmware/printers/control", json={"port": PRINTER, "armed": False})

    start_over()
    yield
    start_over()


def _arm(url: str) -> None:
    with _http(url) as http:
        http.post(
            "/firmware/printers/control", json={"port": PRINTER, "armed": True, "ttl_s": 600}
        ).raise_for_status()


def _machine(page: Page, url: str) -> None:
    """The printer's Machine, open as a person opens it from its board."""
    page.goto(f"{url}/firmware/monitor?port={PRINTER}")
    windows.machine_ready(page, "printer")


def _loops(page: Page):
    return page.locator(LOOPS)


def _over_the_layout(page: Page) -> None:
    """The Loops window's stack over the whole layout, as a double-click on its tab puts
    it -- again after the armed pad's window, opening, gave the layout back -- with no
    control holding the focus: the window wide, its controls in a column beside its plots."""
    over = page.locator(".lm_stack.lm_maximised", has=page.locator(LOOPS))
    if not over.count():
        windows.tab(page, "loops").dblclick()
    expect(over).to_be_visible(timeout=5000)
    page.evaluate("() => document.activeElement && document.activeElement.blur()")


def _button(page: Page, name: str):
    return _loops(page).locator(f"button.loops-{name}")


def _state(page: Page) -> dict:
    return page.evaluate("() => window.apothecaryLoops.state()")


def _drawn(page: Page) -> None:
    """The window has drawn a kept experiment's document and curves."""
    expect(_loops(page).locator("svg.loops-plot[data-plot='step']")).to_be_visible(timeout=20000)
    expect(_loops(page).locator(".loops-figures tr[data-figure]").first).to_be_visible()


def _asked(url: str, path: str, body: dict) -> dict:
    with _http(url) as http:
        answer = http.post(path, json=body)
        answer.raise_for_status()
        return answer.json()


def _the_window_says_what_the_server_says(page: Page, url: str) -> dict:
    """The window's figures are the document's, rounded as its Markdown rounds them, and
    every plot is drawn from the curves' answer: each series' points, each mark where
    the answer names it. The window's own request, asked again: the same document."""
    s = _state(page)
    body = {
        "experiment_id": s["experiment"],
        "rule": s["rule"],
        "kind": s["ruleKind"],
        "read_board": s["readBoard"],
    }
    doc = _asked(url, "/firmware/printers/loops/document", body)
    curves = _asked(url, "/firmware/printers/loops/curves", body)
    rows = page.evaluate(
        '() => [...document.querySelectorAll("' + LOOPS + ' .loops-figures tr[data-figure]")]'
        ".map((r) => [r.dataset.figure, r.dataset.value, r.querySelector('.loops-value').textContent,"
        " r.querySelector('.loops-basis').dataset.basis, r.querySelector('.loops-source').textContent])"
    )
    figures = {f"{g['id']}.{f['key']}": f for g in doc["groups"] for f in g["figures"]}
    assert [r[0] for r in rows] == list(figures)
    for key, value, text, basis, source in rows:
        f = figures[key]
        assert (
            value == ("null" if f["value"] is None else json.dumps(f["value"]))
            or float(value) == f["value"]
        ), key
        assert text == format_value(Figure(**f)), key
        assert (basis, source) == (f["basis"], f["source"]), key
    assert any(k.startswith("loop.phase_margin") for k in figures)
    plots = page.evaluate(
        '() => Object.fromEntries([...document.querySelectorAll("'
        + LOOPS
        + ' svg.loops-plot")].map((svg) => [svg.dataset.plot, {'
        " series: Object.fromEntries([...svg.querySelectorAll('path[data-series]')].map((p) => [p.dataset.series, [Number(p.dataset.n), p.dataset.from, p.dataset.to]])),"
        " marks: Object.fromEntries([...svg.querySelectorAll('g[data-mark]')].map((g) => [g.dataset.mark, g.dataset.at])),"
        " points: [...svg.querySelectorAll('g[data-trust]')].map((g) => g.dataset.trust) }]))"
    )
    step = curves["step"]
    n, first, last = plots["step"]["series"]["measured"]
    assert (n, float(first), float(last)) == (len(step["measured"]), step["t"][0], step["t"][-1])
    assert plots["step"]["series"]["model_designed"][0] == len(step["model_designed"])
    for name, bode in curves["bode"].items():
        n = len(bode["w"])
        assert plots["magnitude"]["series"][f"loop_mag_{name}"][0] == n
        assert plots["phase"]["series"][f"loop_phase_{name}"][0] == n
        assert plots["sensitivity"]["series"][f"s_mag_{name}"][0] == n
        m = curves["margins"][name]
        for plot, mark, key in (
            ("magnitude", f"gain_crossover_{name}", "gain_crossover"),
            ("phase", f"phase_crossover_{name}", "phase_crossover"),
            ("sensitivity", f"ms_{name}", "ms_at"),
            ("sensitivity", f"mt_{name}", "mt_at"),
        ):
            if m[key] is not None and mark in plots[plot]["marks"]:
                assert float(plots[plot]["marks"][mark]) == m[key], (plot, mark)
        # A margin's number in the window is the document's.
        if m["gain_crossover"] is not None:
            assert (
                float(plots["magnitude"]["marks"][f"gain_crossover_{name}"])
                == figures[f"loop.gain_crossover_{name}"]["value"]
            )
    assert [p["trust"] for p in curves["frequency"]] == plots["magnitude"]["points"]
    return doc


def _nothing_saves(page: Page) -> None:
    """No control on the page asks the board to keep anything in its memory."""
    assert page.locator("[data-can='tune.save']").count() == 0
    words = (
        _loops(page)
        .locator("button, select, input")
        .evaluate_all(
            "(els) => els.map((e) => `${e.textContent} ${e.title} ${e.getAttribute('aria-label') || ''}`)"
        )
    )
    assert not [w for w in words if re.search(r"\bsave\b|M500|memory|EEPROM", w, re.I)], words


@pytest.mark.e2e
def test_a_kept_step_its_design_an_experiment_planned_and_the_gains_set(
    page: Page, url: str, walkthrough
):
    """The window, opened from ⊞ Windows beside the printer's Machine, draws the kept
    step's document and curves; Read shows the board's gains and when; Start is greyed
    with the server's reason, the latch's and then the plan's, until a ceiling and a
    longest time are typed; a step runs, its progress told by the stream, and its
    document drawn as the server says it; Set on machine sends the designed gains and
    shows them read back."""
    story = walkthrough(
        ordinal="48",
        slug="a-heater-s-loop-in-the-page",
        title="A heater's loop in the page",
        intro=(
            "The Loops window shows a heater loop of the printer whose Machine is open: what "
            "the board holds beside the controller a named rule designs for the plant the "
            "server identified, the newest kept experiment's plots and figures, and an "
            "experiment to run, its ceiling and its longest time typed every time. Every "
            "number in it is the server's. "
            "[docs/control-loops.md](../docs/control-loops.md#the-loops-window) is the reference."
        ),
        runtime=(
            "It drives a real browser against a real server of its own, its printer simulated "
            "with its heaters modelled and run five times faster than the clock. The kept "
            "step its pictures draw was recorded in the test's own process from the simulated "
            "hotend's model under the board's own gains, so its figures are the same on every "
            "run; the numbers are the simulator's and no heater's."
        ),
        does_not_show=[
            "**A real heater.** Nothing here reaches a board; the bench checklist's steps do.",
            "**The step it runs, in a picture.** Its samples are read on the clock and differ "
            "from run to run; the step is asserted, not pictured.",
            "**Saving the gains.** The window never asks the board to keep them; the reference says how a person does.",
        ],
        browser_suite_only=True,
    )
    _machine(page, url)
    windows.from_the_windows_menu(page, "loops")
    loops = _loops(page)
    expect(loops.locator(".loops-machine")).to_contain_text(PRINTER, timeout=10000)
    _over_the_layout(page)
    _drawn(page)
    assert _state(page)["experiment"] == KEPT
    _nothing_saves(page)

    # Read: the board's gains, and when it answered.
    _button(page, "read").click()
    expect(loops.locator(".loops-gains th[data-col='board'] .loops-when")).to_be_visible(
        timeout=15000
    )
    expect(loops.locator(".loops-said")).to_contain_text("hotend 0 holds P")
    with _http(url) as http:
        held = http.post("/firmware/printers/loops/read", json={"port": PRINTER}).json()["gains"][
            "hotend 0"
        ]
    shown_kp = loops.locator(".loops-gains td[data-gain='kp']").first
    assert float(shown_kp.get_attribute("data-value")) == held["kp"]
    page.wait_for_function("() => window.apothecaryLoops.state().readBoard === true", timeout=20000)
    _drawn(page)
    doc = _the_window_says_what_the_server_says(page, url)
    assert doc["controller"]["on_machine"]["basis"] == "measured"
    marked = page.locator(f"{LOOPS} svg[data-plot='magnitude'] g[data-mark]")
    expect(marked).to_have_count(4)  # each controller's gain and phase crossovers
    start = _button(page, "start")
    expect(start).to_be_disabled()
    expect(start).to_have_attribute(
        "title", re.compile(r"^Disabled: .*arm control first"), timeout=10000
    )
    story.shows(
        "A kept step, its design and the board's gains",
        "The Loops window, its stack over the layout: the newest kept step of hotend 0, "
        "the gains the board answered with beside the PI controller SIMC designs for the "
        "plant the server identified, the step measured beside the model's, the open loop "
        "over frequency with its crossovers marked, and the margins and the step's measures, "
        "each with its basis. Start is greyed: the latch is down.",
        blank=STILL,
    )

    # Armed: Start is the plan's to refuse until the ceiling and the longest time are typed.
    _arm(url)
    expect(page.locator("#control")).to_be_visible(timeout=10000)  # the pad, popped out
    expect(start).to_have_attribute(
        "title",
        re.compile(
            rf"^Disabled: {re.escape(PRINTER)}: {UNSTATED}: its ceiling and its longest time not stated"
        ),
        timeout=10000,
    )
    for name, value in QUICK.items():
        loops.locator(f"input.loops-param[data-param='{name}']").fill(value)
    loops.locator("input.loops-ceiling").fill(CEILING)
    expect(start).to_have_attribute(
        "title", re.compile(rf"{UNSTATED}: its longest time not stated"), timeout=10000
    )
    expect(start).to_be_disabled()
    loops.locator("input.loops-longest").fill(LONGEST)
    expect(start).to_be_enabled(timeout=10000)
    expect(loops.locator(".loops-plan")).to_contain_text(
        "Sets 60 °C at 0 s, 65 °C at 10 s; ends at 30 s"
    )
    _over_the_layout(page)
    story.shows(
        "A ceiling and a longest time typed, and the plan",
        "Armed, Start waited for the two figures nothing states for a person -- the ceiling "
        "no reading may pass and the longest the experiment may run -- in the server's words; "
        "typed, the server says the plan: the targets it sets and when, and its end.",
        blank=STILL,
    )

    # Set on machine: the designed gains sent and read back.
    designed = doc["controller"]["designed"]
    _button(page, "set").click()
    expect(loops.locator(".loops-set-said [data-matches='true']")).to_be_visible(timeout=15000)
    with _http(url) as http:
        held = http.post("/firmware/printers/loops/read", json={"port": PRINTER}).json()["gains"][
            "hotend 0"
        ]
    for k in ("kp", "ki", "kd"):
        assert abs(held[k] - designed[k]) <= 0.0051 + 1e-6 * abs(designed[k]), (k, held, designed)
    expect(loops.locator(".loops-set-said")).to_contain_text("set, not saved")
    # The board read again and the document with it: what it holds is what was designed.
    expect(loops.locator(".loops-said")).to_contain_text(
        "the board holds what was sent", timeout=20000
    )
    _drawn(page)
    board_kp = loops.locator(".loops-gains td[data-gain='kp']").first
    assert abs(float(board_kp.get_attribute("data-value")) - designed["kp"]) <= 0.0051
    _over_the_layout(page)
    story.shows(
        "The designed gains set on the board, and read back",
        "Set on machine sent the designed gains (M301) and read them back (M503): the board "
        "holds what was sent, to the hundredth it prints. Set, not saved: the board's memory "
        "is written only when a request asks for it by name, and this window never asks.",
        blank=STILL,
    )

    # A step: started, its progress told on the stream, ended done, its document drawn.
    heard = []
    start.click()
    expect(loops.locator(".loops-said")).to_contain_text("started", timeout=10000)
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        s = _state(page)
        job = s["job"] or {}
        if job.get("running") and s["via"] == "stream":
            heard.append((s["heard"], job["progress"]))
        if job and not job.get("running") and job.get("outcome"):
            break
        page.wait_for_timeout(250)
    s = _state(page)
    assert s["job"]["outcome"] == "done", s["job"]
    assert s["via"] == "stream" and s["heard"] >= 5, s
    progress = [p for _, p in heard]
    assert len(set(progress)) >= 3 and progress == sorted(progress), progress
    expect(loops.locator(".loops-job [data-heater-off]")).to_contain_text("read back as 0")
    page.wait_for_function(
        f"() => window.apothecaryLoops.state().experiment !== '{KEPT}'", timeout=30000
    )
    _drawn(page)
    page.wait_for_function(
        '() => !!document.querySelector("' + LOOPS + " svg.loops-plot[data-plot='magnitude']\")",
        timeout=30000,
    )
    live = _the_window_says_what_the_server_says(page, url)
    assert live["experiments"][0]["id"] == _state(page)["experiment"] != KEPT
    story.says(
        "A step run from the window",
        "Start ran the planned step; the surfaces' stream told its progress as it ran, never "
        "falling, and its end: done, the heater turned off and its target read back as 0. "
        "The window then drew the new step's document and curves, every figure and mark the "
        "server's. The simulated heater runs five times faster than the clock the step "
        "keeps, so the plant it finds is five times quicker than the simulator's own, and "
        "the board's gains, which are per simulated second, are not the gains round it.",
    )
    _nothing_saves(page)


@pytest.mark.e2e
def test_the_ring_opens_the_window_and_a_refused_act_says_the_server_s_reason(page: Page, url: str):
    """Panels › Machine › Loops › Loops opens the window; its Experiment cell chooses
    what its drop-down chooses; its Start, with the latch down, is greyed in the server's
    words, as the window's button is, and chosen anyway says them on the status line."""
    _machine(page, url)
    rings.on_world(page, "Panels", "Machine", "Loops", "Loops")
    expect(_loops(page)).to_be_visible(timeout=10000)
    expect(_loops(page).locator(".loops-machine")).to_contain_text(PRINTER, timeout=10000)
    _drawn(page)
    address = rings.on_world(page, "Panels", "Machine", "Loops", "Experiment", "Autotune")
    assert address == "44416"
    expect(_loops(page).locator("select.loops-kind")).to_have_value("autotune", timeout=10000)
    expect(_loops(page).locator("input.loops-param[data-param='cycles']")).to_be_visible()
    start = _button(page, "start")
    expect(start).to_have_attribute(
        "title", re.compile(r"^Disabled: .*arm control first"), timeout=10000
    )
    reason = re.search(r"^Disabled: (.*?)\. Start", start.get_attribute("title")).group(1)
    rings.on_world(page, "Panels", "Machine", "Loops", "Start")
    assert rings.greyed(page)["2"] == f"Disabled: {reason}"
    status = page.locator("#status")
    expect(status).to_contain_text(f"Start (⌗4442): {reason}", timeout=10000)
    expect(status).to_have_class(re.compile(r"\berror\b"))
    with _http(url) as http:
        assert (
            not http.get("/firmware/printers/loops/job", params={"port": PRINTER})
            .json()
            .get("running")
        )


@pytest.mark.e2e
def test_cancel_ends_an_experiment_with_the_heaters_off(page: Page, url: str):
    """A long step started from the window, then Cancel: the experiment ends cancelled,
    the window says the heater was turned off and read back, and the board's targets read
    0, the hotend's and the bed's."""
    _arm(url)
    _machine(page, url)
    windows.from_the_windows_menu(page, "loops")
    loops = _loops(page)
    _drawn(page)
    for name, value in {**QUICK, "settle_s": "60", "after_s": "60"}.items():
        loops.locator(f"input.loops-param[data-param='{name}']").fill(value)
    loops.locator("input.loops-ceiling").fill(CEILING)
    loops.locator("input.loops-longest").fill(LONGEST)
    start, cancel = _button(page, "start"), _button(page, "cancel")
    expect(start).to_be_enabled(timeout=10000)
    expect(cancel).to_be_disabled()
    start.click()
    page.wait_for_function(
        "() => (window.apothecaryLoops.state().job || {}).stage === 'running'", timeout=20000
    )
    expect(cancel).to_be_enabled(timeout=10000)
    cancel.click()
    expect(loops.locator(".loops-job [data-outcome='cancelled']")).to_be_visible(timeout=30000)
    expect(loops.locator(".loops-job [data-heater-off]")).to_contain_text(
        "its target read back as 0"
    )
    with _http(url) as http:
        status = http.get("/firmware/printers/status", params={"port": PRINTER}).json()
    assert [h["target"] for h in status["hotends"]] == [0.0] and status["bed"]["target"] == 0.0, (
        status
    )
