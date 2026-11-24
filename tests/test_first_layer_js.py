"""The first layer's words (apothecary/static/first_layer.js): each choice of the Print
window's levelling and adhesion rows is one the server takes and sets what the server's
sets; how a kept slice was made is said from the settings the slicer recorded; and a try
on a print that stopped is refused where the part declares against it or the piece was
made with it already. The module is pure, so node runs it here, on settings the slicer
itself resolved."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from apothecary.models import PrintSettings
from apothecary.projects.parts import bed_shims
from apothecary.slicer import compose
from apothecary.slicer.modules import get_module
from apothecary.slicer.profiles import ADHESIONS, Declared, load_profile

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "apothecary" / "static" / "first_layer.js"
NODE = shutil.which("node") or str(Path.home() / ".local" / "bin" / "node")

pytestmark = pytest.mark.skipif(not Path(NODE).exists(), reason="node is not installed")

SCRIPT = """
import * as f from "%(module)s";
const slices = %(slices)s;
const out = {};
out.levelling = f.LEVELLING.map((c) => [c.value, f.words(c)]);
out.adhesion = f.ADHESION.map((c) => [c.value, f.words(c), c.sets || null]);
out.tries = Object.fromEntries(Object.entries(f.TRIES).map(([k, t]) => [k, [t.row, t.choice.value]]));
out.options = f.options(f.LEVELLING);
out.made = Object.fromEntries(Object.entries(slices).map(([k, s]) => [k, f.made(s)]));
out.refused = ["probe", "brim", "raft", "nothing"].map((how) => f.tryRefused(how,
    slices.shims, { brim_width: 0, levelling: "probe-each-print" }, "bed_shims"));
out.free = ["probe", "brim", "raft"].map((how) => f.tryRefused(how, slices.plain, {}, "cube"));
out.again = ["probe", "brim", "raft"].map((how) => f.tryRefused(how, slices[how], {}, "cube"));
out.other = f.tryRefused("raft", slices.brim, {}, "cube");
console.log(JSON.stringify(out));
"""


def _settings(declared: Declared, levelling=None) -> list:
    """What the slicer records of a slice for printer_1 of what ``declared`` declares."""
    profile = compose.levelled(load_profile("ender3"), levelling, declared.by)
    resolved = get_module("orcaslicer").settings(profile, declared)
    return [s.model_dump(mode="json") for s in resolved.settings]


def _run(tmp_path: Path, slices: dict) -> dict:
    script = tmp_path / "run.mjs"
    script.write_text(SCRIPT % {"module": MODULE.as_uri(), "slices": json.dumps(slices)})
    done = subprocess.run([NODE, str(script)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.fixture
def out(fake_orcaslicer, tmp_path):
    shims = Declared.of(bed_shims.DEFAULT.print_settings, "part bed_shims")
    plain = Declared.of(PrintSettings(layer_height=0.2), "part calibration_cube")
    slices = {
        "shims": _settings(shims, shims.values["levelling"]),
        "plain": _settings(plain),
        **{how: _settings(plain.adhered(how)) for how in ADHESIONS},
        "probe": _settings(plain, "probe-each-print"),
        "stored": [{"name": "start", "value": ["home", "stored-mesh"]}],
    }
    return _run(tmp_path, slices)


def test_each_choice_is_one_the_server_takes_and_sets_what_it_sets(out):
    """The rows' choices, "" the part's own: a levelling the slice route takes, an
    adhesion of the server's own with the values it sets, every one of them offered."""
    levelling = [value for value, _ in out["levelling"]]
    assert levelling[0] == "" and set(levelling[1:]) <= set(compose.LEVELLINGS)
    adhesion = {value: sets for value, _, sets in out["adhesion"]}
    assert adhesion.pop("") is None
    assert adhesion == ADHESIONS
    assert out["tries"] == {
        "probe": ["levelling", "probe-each-print"],
        "brim": ["adhesion", "brim"],
        "raft": ["adhesion", "raft"],
    }
    words = dict((v, w) for v, w, _ in out["adhesion"])
    assert words["brim"] == f"brim: {ADHESIONS['brim']['brim_width']:g} mm round each piece"
    assert words["raft"] == f"raft: {ADHESIONS['raft']['raft_layers']} layers under each piece"
    assert out["options"].startswith('<option value="">the part\'s own</option>')
    probe = '<option value="probe-each-print">probe first: G29 once the bed is hot</option>'
    assert probe in out["options"]


def test_how_a_slice_was_made_is_said_in_the_rows_words(out):
    made = out["made"]
    assert made["shims"] == {
        "levelling": "probe first: G29 once the bed is hot",
        "skirt": "no skirt",
        "adhesion": "no brim",
    }
    assert made["plain"] == {
        "levelling": "home only: no levelling",
        "skirt": "the printer's own skirt",
        "adhesion": None,
    }
    assert made["brim"]["adhesion"] == "brim: 5 mm round each piece"
    assert made["raft"]["adhesion"] == "no brim, raft: 3 layers under each piece"
    assert made["none"]["adhesion"] == "neither brim nor raft"
    assert made["stored"]["levelling"] == "the stored mesh: M420 S1 after G28"


def test_a_try_the_part_declares_against_or_the_piece_had_is_refused_saying_so(out):
    """bed_shims declares no brim and a probe first: its piece's Brim is refused for the
    first, its Probe first for the second, and its Raft is offered. A piece made with a
    probe first, a brim or a raft already is not offered it again."""
    probe = "this piece was made with probe first: G29 once the bed is hot"
    assert out["refused"] == [
        f"{probe}, as bed_shims declares",
        "bed_shims declares no brim",
        None,
        None,
    ]
    assert out["free"] == [None, None, None]
    assert out["again"] == [
        probe,
        "this piece was made with brim: 5 mm round each piece",
        "this piece was made with raft: 3 layers under each piece",
    ]
    assert out["other"] is None


def test_the_print_window_and_feedback_take_their_words_from_the_module():
    """Neither widget writes a choice's words of its own: the rows' options are the
    module's, and Feedback's tries and made row read it."""
    machine = (ROOT / "apothecary" / "static" / "widgets" / "machine.js").read_text()
    feedback = (ROOT / "apothecary" / "static" / "widgets" / "feedback.js").read_text()
    assert "options(LEVELLING)" in machine and "options(ADHESION)" in machine
    assert '<option value="probe-each-print"' not in machine
    assert '<option value="brim"' not in machine
    for widget in (machine, feedback):
        assert "/static/first_layer.js" in widget
        assert "mm round each piece" not in widget and "layers under each" not in widget
