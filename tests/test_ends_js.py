"""The page's ends (apothecary/static/ends.js): a preset staged over a part's defaults,
an end as the server takes it, the body of the adapter's request, and an end in the
server's words, held against apothecary.adapters.End.label for the same ends. The
module is pure, so node runs it here."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from apothecary.adapters import ADAPTER, end
from apothecary.projects.parts import dust_port
from apothecary.projects.parts.params import params_spec

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "apothecary" / "static" / "ends.js"
NODE = shutil.which("node") or str(Path.home() / ".local" / "bin" / "node")

pytestmark = pytest.mark.skipif(not Path(NODE).exists(), reason="node is not installed")

PORT = dust_port.DEFAULT
SPEC = params_spec(PORT).model_dump(mode="json")
DEFAULTS = {f["name"]: f["default"] for f in SPEC["fields"]}

SCRIPT = """
import * as e from "%(module)s";
const presets = %(presets)s, defaults = %(defaults)s;
const out = {};
out.staged = e.presetStaged(defaults, presets.hose_40);
out.none = e.presetStaged(defaults, null);
// The hose as chosen; a port chosen and a caliper's reading typed over it; a port typed
// from the defaults with no preset chosen.
const hose = e.endOf("dust_port", e.presetStaged(defaults, presets.hose_40), defaults, "hose_40", presets);
const measured = e.endOf("dust_port", { ...e.presetStaged(defaults, presets.port_32), diameter: 31.6, measured: true }, defaults, "port_32", presets);
const typed = e.endOf("dust_port", { ...defaults, diameter: 35 }, defaults);
const unknown = e.endOf("dust_port", defaults, defaults, "port_99", presets);
out.ends = [hose, measured, typed, unknown];
out.labels = out.ends.map((x) => e.label(x, "end"));
out.short = e.label(measured);
out.body = e.betweenBody(hose, measured);
out.checked = e.betweenBody(hose, measured, { b_d: 33 });
out.adapter = e.ADAPTER;
out.keys = [e.paramsKey({ b: 1, a: 2 }) === e.paramsKey({ a: 2, b: 1 }), e.paramsKey({ a: 1 }) === e.paramsKey({ a: 2 })];
console.log(JSON.stringify(out));
"""


def _run() -> dict:
    presets = {name: {"params": p["params"]} for name, p in SPEC["presets"].items()}
    script = SCRIPT % {
        "module": MODULE.as_uri(),
        "presets": json.dumps(presets),
        "defaults": json.dumps(DEFAULTS),
    }
    done = subprocess.run(
        [NODE, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_a_preset_is_staged_over_the_part_s_defaults():
    out = _run()
    assert out["staged"] == {**DEFAULTS, **PORT.preset("hose_40")}
    assert out["none"] == DEFAULTS


def test_an_end_names_its_preset_and_only_what_a_person_set_over_it():
    hose, measured, typed, unknown = _run()["ends"]
    assert hose == {"part": "dust_port", "preset": "hose_40", "params": {}}
    assert measured == {
        "part": "dust_port",
        "preset": "port_32",
        "params": {"diameter": 31.6, "measured": True},
    }
    assert typed == {"part": "dust_port", "params": {"diameter": 35}}
    # A preset the part has not got is no preset: what differs from the defaults is said.
    assert unknown == {"part": "dust_port", "params": {}}


def test_an_end_reads_as_the_server_says_it():
    """The page's words for an end are the server's for the same end."""
    out = _run()
    for asked, said in zip(out["ends"], out["labels"], strict=True):
        server = end(PORT, asked.get("preset"), "end", asked["params"] or None)
        assert said == server.label
    assert out["short"] == "dust_port@port_32 (diameter=31.6, measured=true)"


def test_the_request_names_both_ends_and_the_numbers_to_check():
    out = _run()
    hose, measured = out["ends"][:2]
    assert out["body"] == {"a": hose, "b": measured}
    assert out["checked"] == {"a": hose, "b": measured, "params": {"b_d": 33}}


def test_the_adapter_part_and_a_set_of_numbers_in_any_order():
    out = _run()
    assert out["adapter"] == ADAPTER
    assert out["keys"] == [True, False]
