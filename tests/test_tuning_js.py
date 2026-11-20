"""What the Print window's measured row says of a printer's tuning (apothecary/static/tuning.js):
the plan's rows, what a row's field reads, which document is the slice's, what Apply and
Undo turn would be refused for, and a turn and a trend in a line. The module is pure, so
node runs it here, on a document the server itself built."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from apothecary import print_tuning as pt
from apothecary.projects.parts.print_coupon import DEFAULT as COUPON
from apothecary.slicer import tuning
from apothecary.slicer.models import Made, Setting, SlicedFor, SliceRecord

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "apothecary" / "static" / "tuning.js"
NODE = shutil.which("node") or str(Path.home() / ".local" / "bin" / "node")

pytestmark = pytest.mark.skipif(not Path(NODE).exists(), reason="node is not installed")

PLA = {"filament": "Creality Generic PLA", "process": "0.20mm Standard @Creality Ender3"}

SCRIPT = """
import * as t from "%(module)s";
const record = %(record)s, entry = %(entry)s, applied = %(applied)s;
const out = {};
out.plan = t.planOf(record).map((f) => f.name);
out.box = t.planOf({ size: [10, 20, 30] }).map((f) => [f.name, f.nominal]);
out.none = t.planOf(null);
out.applies = t.appliesOf(record);
out.reads = ["20.08 20.1", "", "20,1", "x", "-1", " 7 "].map(t.parseReads);
out.found = t.documentFor([entry], out.applies) === entry;
out.other = t.documentFor([entry], { filament: "PETG", process: out.applies.process });
out.apply = t.canApply(entry);
out.undo = t.canUndo(entry);
out.again = t.canApply(applied);
out.nothing = [t.canApply(null), t.canUndo(null)];
out.line = t.turnLine(entry.document.turns[0]);
out.history = t.historyLines(applied);
out.boxLine = t.turnLine({ id: "turn-9", slice: { part: "cube" }, applied: [], proposed: [],
    terms: [{ term: "scale_x", determined: false }, { term: "scale_xy", determined: false }] });
console.log(JSON.stringify(out));
"""


def _record() -> SliceRecord:
    settings = {
        "xy_contour_compensation": 0.0,
        "xy_hole_compensation": 0.0,
        "elefant_foot_compensation": 0.0,
        "filament_shrink": 100.0,
        "filament_shrinkage_compensation_z": 100.0,
        "z_offset": 0.0,
        "layer_height": 0.2,
        "initial_layer_print_height": 0.2,
    }
    return SliceRecord(
        file_id="f1",
        name="print_coupon.gcode",
        at=datetime.now(timezone.utc),
        slicer="orcaslicer",
        made=Made(kind="part", name="print_coupon"),
        printer=SlicedFor(part="ender3", name="printer_1", site="garage", path="printer_1"),
        settings=[
            Setting(name="filament profile", value=PLA["filament"], origin="printer", source="p"),
            Setting(name="process profile", value=PLA["process"], origin="printer", source="p"),
            *(
                Setting(name=k, value=f"{v:g}", origin="printer", source="p")
                for k, v in settings.items()
            ),
        ],
        size=[54.0, 36.0, 12.0],
        plan=COUPON.measures(),
    )


def _entry(doc) -> dict:
    trends = {
        k: {"term": t.term, "state": t.state, "stop": t.stop, "said": t.said}
        for k, t in tuning.trends(doc).items()
    }
    return {"document": doc.model_dump(mode="json", by_alias=True), "trends": trends}


def test_the_measured_row_reads_the_servers_document(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    record = _record()
    planted = {"contour": 0.08, "scale_x": 0.0, "scale_y": 0.0}
    reads = {
        f.name: [f.nominal + pt.predicted(f.feature(), planted)]
        for f in COUPON.measures().features
        if f.kind in ("outside",) and f.level == "above"
    }
    doc, _ = tuning.add_turn(record, reads)
    entry = _entry(doc)
    applied, _ = tuning.apply("garage", "printer_1", tuning.AppliesTo(**PLA))
    script = tmp_path / "run.mjs"
    script.write_text(
        SCRIPT
        % {
            "module": MODULE.as_uri(),
            "record": record.model_dump_json(),
            "entry": json.dumps(entry),
            "applied": json.dumps(_entry(applied)),
        }
    )
    done = subprocess.run([NODE, str(script)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    assert out["plan"][:3] == ["plate_x", "plate_y", "a_x"] and len(out["plan"]) == 16
    assert out["box"] == [["x", 10], ["y", 20], ["z", 30]] and out["none"] == []
    assert out["applies"] == PLA
    assert out["reads"] == [[20.08, 20.1], [], [20, 1], None, None, [7]]
    assert out["found"] is True and out["other"] is None
    assert out["apply"] == {
        "ok": True,
        "why": "take turn-1's xy_contour_compensation into this printer's next slices",
    }
    assert out["undo"] == {"ok": True, "why": "drop turn-1"}
    assert out["again"] == {
        "ok": False,
        "why": "turn-1 is applied already: print and read the next piece",
    }
    assert [n["ok"] for n in out["nothing"]] == [False, False]
    assert out["line"].startswith("turn-1, print_coupon: scale_x +0.00 ± ")
    assert "contour +0.080 ± 0.00" in out["line"]
    assert "proposed: xy_contour_compensation +0.000 → -0.040" in out["line"]
    assert (
        out["boxLine"]
        == "turn-9, cube: no term determined; not separated: scale_x; proposed: nothing"
    )
    assert out["history"][0].endswith("(applied)")
    assert out["history"][1].startswith("xy_contour_compensation: one turn")
