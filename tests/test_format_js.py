"""How the page writes a number (apothecary/static/format.js): one form each for a
temperature, a time of day, a stretch of time, a size and a position, and the status
line's sentence. The module is pure, so node runs it here."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "apothecary" / "static" / "format.js"
NODE = shutil.which("node") or str(Path.home() / ".local" / "bin" / "node")

pytestmark = pytest.mark.skipif(not Path(NODE).exists(), reason="node is not installed")

SCRIPT = """
import * as f from "%(module)s";
const at = new Date(2026, 10, 18, 11, 53, 53);
console.log(JSON.stringify({
    degrees: [f.degrees(23.14), f.degrees(null)],
    heater: [f.heater(23.1, 0), f.heater(209.96, 210), f.heater(null, 5), f.heater(23, undefined)],
    clock: [f.clock(at), f.clock("nonsense")],
    stamp: f.stamp(at),
    span: [f.span(0), f.span(46), f.span(292), f.span(3729), f.span(-4), f.span(null)],
    mm: [f.mm(101.5), f.mm(46), f.mm(106.5031), f.mm(0), f.mm(null)],
    dims: [f.dims(46, 46, 101.5), f.dims(46.0004, 20)],
    xyz: f.xyz({ x: 0, y: 12.34, z: 5 }),
    via: f.viaRing("Home all", 494),
    sentence: ["poll: refused", "Jog X1", "printer_1's bed", "ttyUSB0: gone", "(⌗4)", ""].map(f.sentence),
}));
"""


# What writes a moment the browser's way, in the person's locale: "11:53:53 AM",
# "11/18/2026, 12:06:32 PM", "Nov 18, 2026, 12:06 PM".
LOCALE = re.compile(r"\.toLocale(?:Date|Time)?String\(")


def test_no_page_writes_a_moment_its_own_way():
    """Every time of day and every day the page writes goes through format.js: no
    module of the page, and not the viewer's template, asks the browser's locale for one."""
    sources = [p for p in (ROOT / "apothecary" / "static").rglob("*.js") if "vendor" not in p.parts]
    sources += list((ROOT / "templates").glob("*.j2"))
    own = [
        f"{path.relative_to(ROOT)}:{n}"
        for path in sources
        if path != MODULE
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if LOCALE.search(line)
    ]
    assert own == []


def test_each_number_has_one_form(tmp_path):
    script = tmp_path / "run.mjs"
    script.write_text(SCRIPT % {"module": MODULE.as_uri()})
    done = subprocess.run([NODE, str(script)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    assert out["degrees"] == ["23.1°", "—"]
    assert out["heater"] == ["23.1/0°", "210.0/210°", "—", "23.0/—°"]
    assert out["clock"] == ["11:53:53", "—"]
    assert out["stamp"] == "2026-11-18 11:53:53"
    assert out["span"] == ["0:00", "0:46", "4:52", "1:02:09", "0:00", "—"]
    assert out["mm"] == ["101.5 mm", "46 mm", "106.503 mm", "0 mm", "—"]
    assert out["dims"] == ["46 × 46 × 101.5 mm", "46 × 20 mm"]
    assert out["xyz"] == "X0.0 Y12.3 Z5.00"
    assert out["via"] == "Home all (⌗494)"
    assert out["sentence"] == ["Poll: refused", "Jog X1", "printer_1's bed", "ttyUSB0: gone", "(⌗4)", ""]
