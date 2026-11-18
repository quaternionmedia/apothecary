"""static/ring.js draws a wedge that cannot be chosen greyed, with its reason: a title on
the wedge, and the reason in words under the ring while the wedge is lit -- by the
pointer, an arrow, or a digit or tap that chose it anyway -- since a title alone is not
seen on a touch screen. Run under node over the ring's markup."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RING_JS = Path(__file__).resolve().parents[1] / "apothecary" / "static" / "ring.js"
WHY = "/dev/x: control is not armed -- arm it first"

SCRIPT = r"""
import { ringMarkup, refusalOf, refusedWords, whyLines, withCells } from %(url)s;
const why = %(why)s;
const ring = { title: "Jog", options: withCells([
    { id: "y", label: "Y+", action: "control:jog:Y+", enabled: false, why },
    { id: "x", label: "X+", action: "control:jog:X+" },
    { id: "f", label: "Flash", action: "device:flash", enabled: false },
]) };
const out = {
    plain: ringMarkup({ ring, highlight: null, armed: null, address: "772", below: true }),
    lit: ringMarkup({ ring, highlight: 8, armed: null, address: "772", below: true }),
    above: ringMarkup({ ring, highlight: 8, armed: null, address: "772", below: false }),
    litOk: ringMarkup({ ring, highlight: 6, armed: null, address: "772", below: true }),
    refusal: refusalOf(ring.options[0]),
    bare: refusalOf(ring.options[2]),
    allowed: refusalOf(ring.options[1]),
    said: refusedWords(ring.options[0], "7728"),
    lines: whyLines("Disabled: " + why, 24),
};
console.log(JSON.stringify(out));
"""


def _run() -> dict:
    script = SCRIPT % {"url": json.dumps(RING_JS.as_uri()), "why": json.dumps(WHY)}
    run = subprocess.run(
        ["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60
    )
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def _wedge(markup: str, cell: int) -> str:
    """The wedge of ``cell``, its path and what is inside it."""
    found = re.search(rf'<path id="ring-cell-{cell}"[^>]*>(.*?)</path>', markup, re.S)
    assert found, markup
    return found[0]


def _why_text(markup: str) -> str:
    found = re.search(r'<text class="why"[^>]*>(.*?)</text>', markup, re.S)
    return re.sub(r"<[^>]+>", " ", found[1]).split() if found else None


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_a_greyed_wedge_wears_its_reason_and_says_it_under_the_ring_while_lit():
    out = _run()
    greyed = _wedge(out["plain"], 8)
    assert re.search(r'class="wedge disabled"', greyed), greyed
    assert 'aria-disabled="true"' in greyed and 'aria-label="Y+"' in greyed
    assert f"<title>Disabled: {WHY}</title>" in greyed
    # Unlit, the reason is the wedge's title alone; lit, it is written under the ring.
    assert _why_text(out["plain"]) is None
    assert _why_text(out["lit"]) == f"Disabled: {WHY}".split()
    below = float(re.search(r'<text class="why"[^>]* y="(-?[\d.]+)"', out["lit"])[1])
    above = float(re.search(r'<text class="why"[^>]* y="(-?[\d.]+)"', out["above"])[1])
    assert below > 108 and above < -108  # outside the wedges' outer edge, either side
    # A wedge that can be chosen, lit or not, says nothing of the kind.
    allowed = _wedge(out["litOk"], 6)
    assert "disabled" not in allowed and "<title>" not in allowed and "aria-disabled" not in allowed
    assert _why_text(out["litOk"]) is None
    # One with no reason given still says it cannot be chosen.
    assert out["bare"] == "Disabled" and "<title>Disabled</title>" in _wedge(out["plain"], 2)
    assert out["refusal"] == f"Disabled: {WHY}" and out["allowed"] is None
    # Chosen anyway, the status line says it as a refused verb is said: label, address, why.
    assert out["said"] == f"Y+ (⌗7728): {WHY}"
    # The reason is broken at spaces into lines short enough to read under the ring.
    assert all(len(line) <= 24 for line in out["lines"]), out["lines"]
    assert " ".join(out["lines"]) == f"Disabled: {WHY}"


ANNOTATE = r"""
import { annotate, withCells } from %(url)s;
const el = (title) => {
  const attrs = new Map(title === undefined ? [] : [["title", title]]);
  return {
    dataset: {},
    removeAttribute: (k) => attrs.delete(k),
    set title(v) { attrs.set("title", v); }, get title() { return attrs.get("title") || ""; },
    attrs,
  };
};
const ring = { options: withCells([{ id: "arm", label: "Arm", action: "control:arm" }]) };
const bare = el(), worded = el("Arm control"), gone = el(), wordedGone = el("Arm control");
annotate(ring, [[bare, "control:arm"], [worded, "control:arm"], [gone, "control:arm"], [wordedGone, "control:arm"]]);
const first = { bare: bare.attrs.get("title"), worded: worded.attrs.get("title") };
annotate(ring, [[bare, "control:arm"], [worded, "control:arm"]]);
const again = { bare: bare.attrs.get("title"), worded: worded.attrs.get("title") };
annotate(ring, [[gone, "control:nothing"], [wordedGone, "control:nothing"]]);
console.log(JSON.stringify({ first, again, gone: gone.attrs.has("title") ? gone.attrs.get("title") : null,
  goneAddress: gone.dataset.address || null, wordedGone: wordedGone.attrs.get("title") }));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_an_address_is_written_once_and_taken_away_whole():
    """annotate writes a cell's address after a control's own title, or as its title where
    it has none, the same however often it runs; a control whose act leaves the ring loses
    the address, a bare one included, and keeps its own words."""
    script = ANNOTATE % {"url": json.dumps(RING_JS.as_uri())}
    run = subprocess.run(
        ["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60
    )
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    assert out["first"] == {"bare": "⌗8", "worded": "Arm control · ⌗8"}
    assert out["again"] == out["first"]
    assert out["gone"] is None and out["goneAddress"] is None
    assert out["wordedGone"] == "Arm control"
