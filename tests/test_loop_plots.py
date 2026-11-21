"""A loop's plots (apothecary/static/loop_plots.js): the axes, a path through known points,
the marks where the server's answer names a crossover, a measured point drawn as its trust
says, and a figure rounded as the document's Markdown view rounds it. The module is pure,
so node runs it here; the Loops window (widgets/loops.js) draws with it and computes
nothing the server computes.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from apothecary.loop_document import Figure, format_value

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "apothecary" / "static" / "loop_plots.js"
NODE = shutil.which("node") or str(Path.home() / ".local" / "bin" / "node")

pytestmark = pytest.mark.skipif(not Path(NODE).exists(), reason="node is not installed")

# Figures to round both ways: ties at each number of places, where Python's format and
# JavaScript's toFixed part (182.5, 12.25, 0.0625 are exact halves in binary), the
# boundaries between the ways, the very small and large, and the signs.
FIGURES = [
    182.5,
    183.5,
    -182.5,
    12.25,
    12.35,
    0.0625,
    0.0375,
    99.95,
    100.0,
    9.9996,
    10.0,
    47.57436156576156,
    2.9725034629209937,
    1.6961550677882014,
    0.0281246636998093,
    18.29374598475713,
    0.0,
    -0.3,
    0.001,
    0.000999,
    1e-5,
    -2.5e-7,
    1234567.0,
    999999.5,
    6.503,
    1.195,
    35.465665,
    254.99,
    0.5,
    2.5,
]

SCRIPT = """
import * as m from "%(module)s";
const out = {};
out.logTicks = [m.logTicks(1e-5, 11.1), m.logTicks(1e-3, 1e5, 4), m.logTicks(2, 30), m.logTicks(0.1, 1)];
out.linearTicks = [m.linearTicks(0, 187.3), m.linearTicks(-540, 90), m.stepTicks(-540, 90, 90), m.linearTicks(0.1, 0.35)];
out.linearDomain = [m.linearDomain(22.8, 186.2), m.linearDomain(5, 5)];
out.logDomain = [m.logDomain(0.0003, 4.2), m.logDomain(1e-12, 3e4, 6), m.logDomain(2, 3)];
out.labels = [[1e-5, true], [0.01, true], [1000, true], [1e4, true], [20, true], [-180, false]].map(([v, log]) => m.tickLabel(v, log));
const lin = m.linearScale([0, 10], [0, 100]);
const flip = m.linearScale([0, 100], [200, 0]);
const log = m.logScale([0.01, 100], [0, 400]);
out.scales = [lin(2.5), flip(25), log(1), log(0.1), log(100), log(0)];
out.paths = [
    m.pathOf([0, 5, 10], [0, 50, 100], lin, flip),
    m.pathOf([0, 1, 2, 3, 4], [10, null, 30, NaN, 50], lin, flip),
    m.pathOf([0.01, 1, 100], [100, 50, 0], log, flip),
    m.pathOf([0, 5, 10], [0, 500, 100], lin, flip, (x, y) => y <= 100),
];
const answer = %(answer)s;
const designed = answer.bode.designed, marks = answer.margins.designed;
out.svg = m.plotSvg({
    name: "open-loop", title: "the open loop",
    x: { log: true, domain: m.logDomain(designed.w[0], designed.w[designed.w.length - 1]), label: "ω", unit: "rad/s" },
    y: { log: true, domain: m.logDomain(1e-3, 1e3), label: "|L|" },
    series: [{ name: "loop_mag_designed", cls: "designed", xs: designed.w, ys: designed.loop_mag, label: "designed" }],
    rules: [{ y: 1, label: "|L| = 1" }],
    marks: [
        { name: "gain_crossover_designed", x: marks.gain_crossover, label: "ωc" },
        { name: "phase_crossover_designed", x: marks.phase_crossover, label: "ω180" },
        { name: "nowhere", x: null, label: "no crossover" },
    ],
    points: answer.frequency.map((p) => ({ x: p.frequency, y: p.magnitude, trust: p.trust, why: p.why })),
});
out.shown = %(figures)s.map(m.shown);
out.shownOthers = [m.shown(null), m.shown(true), m.shown(false), m.shown("words")];
console.log(JSON.stringify(out));
"""

# An answer as the server gives one (loop_document.curves), small enough to read: three
# frequencies, a crossover between the first two, and a point of each trust.
ANSWER = {
    "bode": {
        "designed": {
            "w": [0.001, 0.1, 10.0],
            "loop_mag": [400.0, 2.0, 0.004],
        }
    },
    "margins": {"designed": {"gain_crossover": 0.15848931924611134, "phase_crossover": 2.5}},
    "frequency": [
        {"frequency": 0.01, "magnitude": 30.0, "trust": "good", "why": "w"},
        {"frequency": 0.03, "magnitude": 10.0, "trust": "fair", "why": "x"},
        {"frequency": 0.05, "magnitude": 3.0, "trust": "poor", "why": "y"},
        {"frequency": 0.07, "magnitude": 1.0, "trust": "unknown", "why": "z"},
    ],
}


@pytest.fixture(scope="module")
def drawn():
    script = SCRIPT % {
        "module": MODULE.as_uri(),
        "answer": json.dumps(ANSWER),
        "figures": json.dumps(FIGURES),
    }
    run = subprocess.run(
        [NODE, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60
    )
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def test_a_log_axis_ticks_its_decades_thinned_and_its_twos_and_fives_over_less_than_two(drawn):
    whole, thinned, short, one = drawn["logTicks"]
    assert whole == [1e-5, 1e-4, 1e-3, 0.01, 0.1, 1, 10]
    assert thinned == [1e-3, 1, 1000]  # nine decades, four at most: every third
    assert short == [2, 5, 10, 20]
    assert one == [0.1, 0.2, 0.5, 1]


def test_a_linear_axis_ticks_nice_steps(drawn):
    temps, phase, ninety, small = drawn["linearTicks"]
    assert temps == [0, 50, 100, 150]
    assert phase == [-400, -200, 0]
    assert ninety == [-540, -450, -360, -270, -180, -90, 0, 90]
    assert small == [0.1, 0.15, 0.2, 0.25, 0.3, 0.35]
    assert drawn["linearDomain"] == [[0, 200], [4, 6]]


def test_a_log_domain_is_whole_decades_and_no_more_below_the_top_than_asked(drawn):
    assert drawn["logDomain"] == [[1e-4, 10], [0.1, 1e5], [1, 10]]  # six decades below 1e5
    assert drawn["labels"] == ["10⁻⁵", "0.01", "1000", "10⁴", "20", "-180"]


def test_scales_map_the_ends_and_the_middle(drawn):
    assert drawn["scales"] == [25, 150, 200, 100, 400, None]  # NaN is JSON's null


def test_a_path_goes_through_the_points_and_breaks_where_one_is_missing_or_outside(drawn):
    straight, gapped, logged, clipped = drawn["paths"]
    assert straight == "M0 200L50 100L100 0"
    assert gapped == "M0 180M20 140M40 100"  # each lone point begins its own piece
    assert logged == "M0 0L200 100L400 200"
    assert clipped == "M0 200M100 0"  # the middle point is above the plot: the path breaks


def test_the_marks_stand_where_the_answer_names_its_crossovers(drawn):
    """Each mark carries the answer's own number, every digit, and stands at its pixel
    on the axis; a margin the answer has none of (null) is not drawn."""
    svg = drawn["svg"]
    marks = {
        name: (float(at), float(x))
        for name, at, x in re.findall(
            r'data-mark="(\w+)" data-at="([^"]+)"><line x1="([\d.]+)"', svg
        )
    }
    assert set(marks) == {"gain_crossover_designed", "phase_crossover_designed"}
    assert marks["gain_crossover_designed"][0] == ANSWER["margins"]["designed"]["gain_crossover"]
    # The log axis runs over the decades 1e-3 to 10, from x = 46 to x = 350.
    for name, (at, x) in marks.items():
        expected = 46 + (math.log10(at) + 3) / 4 * (350 - 46)
        assert abs(x - expected) <= 0.05, (name, x, expected)
    path = re.search(
        r'data-series="loop_mag_designed" data-n="(\d+)" data-from="([^"]+)" data-to="([^"]+)"', svg
    )
    assert path.groups() == ("3", "0.001", "10")
    assert 'data-rule="1"' in svg


def test_a_measured_point_is_drawn_as_its_trust_says_and_no_two_trusts_alike(drawn):
    svg = drawn["svg"]
    shapes = {
        trust: shape
        for trust, shape in re.findall(
            r'<g class="point trust-(\w+)" data-trust="\1" data-at="[^"]+"><title>[^<]*</title>(<[^>]+>)',
            svg,
        )
    }
    assert set(shapes) == {"good", "fair", "poor", "unknown"}
    assert 'fill="currentColor"' in shapes["good"] and "fill-opacity" not in shapes["good"]
    assert 'fill-opacity="0.45"' in shapes["fair"]
    assert 'fill="none"' in shapes["poor"] and "stroke-dasharray" in shapes["poor"]
    assert shapes["unknown"].startswith("<rect") and 'fill="none"' in shapes["unknown"]
    # Stripped of where each stands, no two look alike.
    looks = {re.sub(r'(c?[xy]|cx|cy)="[^"]*"', "", s) for s in shapes.values()}
    assert len(looks) == 4


def test_a_figure_is_rounded_as_the_document_s_markdown_rounds_it(drawn):
    """`shown` is format_value's rounding, ties included: Python's format takes an exact
    half to the even place, JavaScript's toFixed takes it up, and the page says what the
    document's Markdown says."""
    python = [
        format_value(Figure(key="x", label="x", value=v, basis="computed", source="plant"))
        for v in FIGURES
    ]
    assert drawn["shown"] == python
    assert drawn["shownOthers"] == ["—", "yes", "no", "words"]
