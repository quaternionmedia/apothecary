"""Drafts of a part's SCAD: written beside the part for one OpenSCAD run, checked
(evaluated, not rendered) and rendered into the variant cache, errors by line;
a part whose geometry is Python shows its generated SCAD and refuses a draft.

Every OpenSCAD here is scripted (tests/scripted_openscad.py) and every part is
the test's own, in its own folder, so nothing is written into parts/.
"""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from scripted_openscad import calls, renders, scripted_openscad, stl_names

from apothecary import api
from apothecary.api import app
from apothecary.projects import registry
from apothecary.projects.parts import stl_renderer, variants
from apothecary.projects.parts.base import BasePart
from apothecary.projects.parts.customizer import lists_parameters
from apothecary.projects.parts.drafts import (
    ReadOnly,
    check_draft,
    draft_digest,
    written_beside,
)
from apothecary.projects.parts.rc_snowplow import DEFAULT as SNOWPLOW
from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.parts.stl_renderer import OpenSCADRenderer, geometry_scad
from apothecary.projects.parts.variants import make_variant, read_variant_draft, variant_paths

SCAD = """// A block.
include <dims.scad>
width = 34; // [10:100]
hollow = true;
module block() { cube([width, depth, 3]); }
block();
"""


class Width(BaseModel):
    width: float = Field(34, gt=0)


@pytest.fixture
def openscad(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_CACHE_DIR", str(tmp_path / "cache"))

    def install(version: str = "2026.09.27", lists: bool = True) -> Path:
        exe = scripted_openscad(tmp_path / "bin" / version / "openscad", version, lists)
        monkeypatch.setenv("APOTHECARY_OPENSCAD", str(exe))
        monkeypatch.setattr(stl_renderer, "_renderer", None)
        return exe

    return install


def _part(tmp_path: Path, model=None) -> BasePart:
    scad = tmp_path / "parts" / "block" / "block.scad"
    scad.parent.mkdir(parents=True, exist_ok=True)
    scad.write_text(SCAD)
    (scad.parent / "dims.scad").write_text("depth = 20;\n")
    part = BasePart(name="block", source_file=scad, params_model=model)
    return part


@pytest.fixture
def block(tmp_path, monkeypatch):
    """A part with no Python model at ``/parts/block``; its STL is the test's own."""
    part = _part(tmp_path)
    monkeypatch.setattr(BasePart, "get_stl_output_path", lambda self: tmp_path / "block.stl")
    real = api._load_part_wrapper
    monkeypatch.setattr(
        api, "_load_part_wrapper", lambda name: part if name == "block" else real(name)
    )
    return part


def _beside(part: BasePart) -> list:
    """Every file in the part's folder but its own."""
    return sorted(
        p.name for p in part.part_dir.iterdir() if p.name not in ("block.scad", "dims.scad")
    )


# --- written beside the part --------------------------------------------------------


class TestWrittenBeside:
    def test_a_draft_is_a_hidden_file_beside_the_part_for_the_block_only(self, tmp_path):
        part = _part(tmp_path)
        with written_beside(part, "cube(1);\n") as path:
            assert path.parent == part.part_dir and path.name.startswith(".block.")
            assert path.name.endswith(".draft.scad") and path.read_text() == "cube(1);\n"
            assert part.source_file.read_text() == SCAD
        assert not path.exists() and _beside(part) == []

    def test_two_at_once_are_two_files(self, tmp_path):
        part = _part(tmp_path)
        with written_beside(part, "a") as one, written_beside(part, "b") as two:
            assert one != two and (one.read_text(), two.read_text()) == ("a", "b")

    def test_it_is_removed_whatever_happened(self, tmp_path):
        part = _part(tmp_path)
        with pytest.raises(RuntimeError), written_beside(part, "x") as path:
            raise RuntimeError("the run failed")
        assert not path.exists()

    def test_a_part_built_by_python_has_no_scad_to_draft(self):
        with pytest.raises(ReadOnly, match="geometry is Python"), written_beside(SNOWPLOW, "x"):
            pass

    def test_git_ignores_a_draft_left_behind(self):
        """Should a killed run leave one, it is never committed."""
        for left in (
            "parts/contranot/.contranot.0123456789ab.draft.scad",
            "parts/boards/arduino_uno/.arduino_uno.0123456789ab.draft.scad",
        ):
            ignored = subprocess.run(["git", "check-ignore", "-q", left], cwd=ROOT)
            assert ignored.returncode == 0, f"{left} would be committed"
        kept = subprocess.run(
            ["git", "check-ignore", "-q", "parts/contranot/contranot.scad"], cwd=ROOT
        )
        assert kept.returncode == 1

    def test_a_hidden_scad_beside_a_part_is_never_a_part(self, tmp_path):
        parts = tmp_path / "parts"
        (parts / "knob").mkdir(parents=True)
        (parts / "knob" / "knob.scad").write_text("cube(1);\n")
        (parts / "knob" / ".knob.0123456789ab.draft.scad").write_text("cube(2);\n")
        (parts / ".flat.0123456789ab.draft.scad").write_text("cube(3);\n")
        (parts / "loose").mkdir()
        (parts / "loose" / ".a.draft.scad").write_text("cube(4);\n")
        (parts / "loose" / "b.scad").write_text("cube(5);\n")
        registry.invalidate()
        found = sorted(
            p.path.relative_to(parts).as_posix()
            for p in registry.scan_projects(tmp_path)
            if p.kind == "part" and p.path.is_relative_to(parts)
        )
        assert found == ["knob/knob.scad", "loose/b.scad"]


# --- the check ----------------------------------------------------------------------


class TestTheCheck:
    def test_it_is_evaluated_beside_the_part_and_names_the_parts_scad(self, tmp_path, openscad):
        exe = openscad()
        part = _part(tmp_path)
        draft = SCAD.replace(
            "hollow = true;", "hollow = true;\nlid = 2; // [1:5]\nWARN\nassert(false);"
        )
        check = check_draft(part, draft)
        asked = [c for c in calls(exe) if c["format"] == "param"]
        assert len(asked) == 1 and asked[0]["there"] and asked[0]["text"] == draft
        assert Path(asked[0]["scad"]).parent == part.part_dir and asked[0]["cwd"] == str(
            part.part_dir
        )
        assert _beside(part) == [] and part.source_file.read_text() == SCAD
        # What OpenSCAD said, by line of the draft, naming the part's SCAD.
        where = [(m.level, m.file, m.line) for m in check.messages]
        assert where == [("warning", "block.scad", 6), ("error", "block.scad", 7)]
        assert check.messages[1].trace[0].file == "block.scad"
        # What the draft declares, the new parameter with its range among them.
        listed = {p["name"]: p for p in check.parameters}
        assert list(listed) == ["width", "hollow", "lid"]
        assert (listed["lid"]["min"], listed["lid"]["max"]) == (1, 5)

    def test_the_same_text_is_checked_once(self, tmp_path, openscad):
        exe = openscad()
        part = _part(tmp_path)
        first = check_draft(part, SCAD + "// one\n")
        assert check_draft(part, SCAD + "// one\n") is first
        check_draft(part, SCAD + "// two\n")
        assert len([c for c in calls(exe) if c["format"] == "param"]) == 2

    def test_an_edited_include_is_checked_again(self, tmp_path, openscad):
        exe = openscad()
        part = _part(tmp_path)
        check_draft(part, SCAD)
        (part.part_dir / "dims.scad").write_text("depth = 25;\n")
        check_draft(part, SCAD)
        assert len([c for c in calls(exe) if c["format"] == "param"]) == 2

    def test_a_parse_error_is_where_it_is(self, tmp_path, openscad):
        openscad()
        check = check_draft(_part(tmp_path), "x = 1;\ncube(x) SYNTAX ERROR\n")
        assert not check.ok and check.parameters is None
        assert [(m.level, m.line) for m in check.messages] == [("error", 2)]

    def test_2021_01_evaluates_it_and_lists_nothing(self, tmp_path, openscad):
        exe = openscad("2021.01", lists=False)
        check = check_draft(_part(tmp_path), SCAD + "assert(false);\n")
        assert check.how == "echo" and not check.lists and check.parameters is None
        assert [(m.level, m.line) for m in check.messages] == [("error", 7)]
        assert [c["format"] for c in calls(exe) if c["format"]] == ["echo"]


# --- the render ---------------------------------------------------------------------


class TestTheRender:
    def test_a_draft_is_a_variant_of_its_own_in_the_cache(self, tmp_path, openscad):
        exe = openscad()
        part = _part(tmp_path, model=Width)
        draft = SCAD.replace("cube([width, depth, 3])", "cube([width, depth, 5])")
        made = make_variant(part, {"width": 40}, draft=draft)
        assert made.success and made.rendered and made.key
        assert made.draft == draft_digest(draft) and not made.saved
        stl, record = variant_paths(part, made.key)
        assert stl_names(stl.read_bytes()).startswith(draft_digest(draft))
        assert read_variant_draft(part, made.key) == draft
        # The part's own SCAD and STL are untouched; nothing is left beside it.
        assert part.source_file.read_text() == SCAD
        assert not part.get_stl_output_path().exists() and _beside(part) == []
        assert renders(exe)[0]["there"] and Path(renders(exe)[0]["scad"]).parent == part.part_dir
        again = make_variant(part, {"width": 40}, draft=draft)
        assert (again.rendered, again.key) == (False, made.key) and len(renders(exe)) == 1

    def test_a_draft_the_same_as_the_scad_is_the_part(self, tmp_path, openscad):
        openscad()
        part = _part(tmp_path, model=Width)
        own = make_variant(part)
        same = make_variant(part, draft=SCAD)
        assert same.draft is None and same.saved and not same.rendered
        assert same.stl_path == own.stl_path or same.key == own.key

    def test_the_defaults_of_a_draft_are_not_the_saved_part(self, tmp_path, openscad):
        openscad()
        part = _part(tmp_path, model=Width)
        make_variant(part)
        before = part.get_stl_output_path().read_bytes()
        made = make_variant(part, draft=SCAD + "// edited\n")
        assert made.rendered and made.key and not made.saved
        assert part.get_stl_output_path().read_bytes() == before

    def test_a_name_the_draft_declares_is_one_it_takes(self, tmp_path, openscad):
        """No model: the names -D reaches are the draft's own top-level variables."""
        openscad()
        part = _part(tmp_path)
        with pytest.raises(ValueError, match="unknown parameter"):
            make_variant(part, {"lid": 2})
        made = make_variant(part, {"lid": 2}, draft=SCAD + "lid = 1;\n")
        assert made.success and made.params == {"lid": 2}

    def test_a_part_built_by_python_has_none(self, openscad):
        openscad()
        with pytest.raises(ValueError, match="geometry is Python"):
            make_variant(SNOWPLOW, draft="cube(1);\n")


# --- the routes ---------------------------------------------------------------------


def _check(client, scad, params=None, page=None):
    query = {"page": page} if page else {}
    return client.post(
        "/parts/block/draft/check", params=query, json={"scad": scad, "params": params or {}}
    )


def _render(client, scad, params=None, page=None):
    query = {"page": page} if page else {}
    return client.post(
        "/parts/block/draft/render", params=query, json={"scad": scad, "params": params or {}}
    )


class TestTheCheckRoute:
    def test_it_answers_what_the_draft_declares_and_what_openscad_said(self, openscad, block):
        openscad()
        draft = SCAD.replace("hollow = true;", "hollow = true;\nlid = 2; // [1:5]")
        r = _check(TestClient(app), draft)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["valid"] and body["edited"] and body["listed"]
        assert (body["checked_by"], body["source"]) == ("param", "customizer")
        assert body["draft"] == draft_digest(draft) and body["messages"] == []
        assert [f["name"] for f in body["fields"]] == ["width", "hollow", "lid"]
        # The values are the text's own, each checked against what it lists.
        assert body["params"] == {"width": 34, "hollow": True, "lid": 2}
        assert body["note"] is None and body["text"] is None
        assert [(v["name"], v["valid"]) for v in body["values"]] == [
            ("width", True),
            ("hollow", True),
            ("lid", True),
        ]
        lid = next(a for a in body["assignments"] if a["name"] == "lid")
        assert (lid["value"], lid["line"], lid["min"], lid["max"]) == (2, 5, 1, 5)
        assert draft[lid["from"] : lid["to"]] == "2"

    def test_values_sent_on_the_side_are_written_into_the_text(self, openscad, block):
        openscad()
        draft = SCAD.replace("hollow = true;", "hollow = true;\nlid = 2; // [1:5]")
        body = _check(TestClient(app), draft, {"lid": 4, "width": "50"}).json()
        written = draft.replace("width = 34;", "width = 50;").replace("lid = 2;", "lid = 4;")
        assert body["text"] == written and body["draft"] == draft_digest(written)
        assert body["valid"] and body["params"] == {"width": 50, "hollow": True, "lid": 4}

    def test_what_is_wrong_with_it_is_said(self, openscad, block):
        openscad()
        body = _check(TestClient(app), SCAD + "assert(false);\n", {"width": 500}).json()
        assert body["valid"] is False
        assert [(m["level"], m["file"], m["line"]) for m in body["messages"]] == [
            ("error", "block.scad", 7)
        ]
        assert [e["field"] for e in body["errors"]] == ["width"]

    def test_unedited_it_says_so(self, openscad, block):
        openscad()
        assert _check(TestClient(app), SCAD).json()["edited"] is False

    def test_a_part_with_a_model_answers_the_models_fields(self, openscad, block):
        openscad()
        block.params_model = Width
        body = _check(TestClient(app), SCAD + "lid = 1;\n", {"width": -1}).json()
        assert body["source"] == "model" and [f["name"] for f in body["fields"]] == ["width"]
        assert body["valid"] is False and body["errors"][0]["field"] == "width"

    def test_2021_01_says_it_cannot_list_them(self, openscad, block):
        openscad("2021.01", lists=False)
        body = _check(TestClient(app), SCAD, {"width": 50}).json()
        assert body["valid"] and body["checked_by"] == "echo" and body["listed"] is False
        assert body["fields"] == [] and body["source"] is None
        assert "cannot list the draft's parameters" in body["note"]


class TestTheRenderRoute:
    def test_a_draft_is_drawn_from_its_own_variant(self, openscad, block):
        exe = openscad()
        client = TestClient(app)
        draft = SCAD.replace("cube([width, depth, 3])", "cube([width, depth, 9])")
        r = _render(client, draft, {"width": 50, "hollow": True})
        assert r.status_code == 200, r.text
        body = r.json()
        # The values sent on the side are written into the text, which is what renders.
        written = draft.replace("width = 34;", "width = 50;")
        assert body["text"] == written
        assert body["draft"] == draft_digest(written) and body["saved"] is False
        assert body["params"] == {"width": 50}  # hollow is what the draft assigns
        assert body["stl_url"] == f"/parts/block/variants/{body['variant']}/stl"
        assert stl_names(client.get(body["stl_url"]).content).startswith(draft_digest(written))
        assert '"width=' not in stl_names(client.get(body["stl_url"]).content)  # no -D
        record = client.get(f"/parts/block/variants/{body['variant']}").json()
        assert record["draft"] == body["draft"] and record["saved"] is False
        assert client.get(record["scad_url"]).text == written
        assert len(renders(exe)) == 1 and _beside(block) == []
        assert block.source_file.read_text() == SCAD

    def test_openscads_errors_come_back_by_line(self, openscad, block):
        openscad()
        r = _render(TestClient(app), SCAD + "assert(false);\n")
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert detail["message"].startswith("STL generation failed")
        assert [(m["level"], m["file"], m["line"]) for m in detail["messages"]][0] == (
            "error",
            "block.scad",
            7,
        )

    def test_a_value_the_draft_does_not_take_renders_nothing(self, openscad, block):
        exe = openscad()
        r = _render(TestClient(app), SCAD, {"width": 500})
        assert r.status_code == 422 and "width" in r.json()["detail"]
        assert renders(exe) == []

    def test_the_parts_own_text_has_no_draft_and_applied_values_have_one(self, openscad, block):
        openscad()
        client = TestClient(app)
        own = client.post("/parts/block/stl/generate", json={"params": {}}).json()
        assert own["draft"] is None and own["saved"] is True
        # Apply's values are written into the part's text, which is what renders; it
        # is recorded as the part with those values, no draft of its own.
        body = client.post("/parts/block/stl/generate", json={"params": {"width": 50}}).json()
        written = SCAD.replace("width = 34;", "width = 50;")
        assert body["draft"] is None and body["params"] == {"width": 50}
        assert stl_names(client.get(body["stl_url"]).content).startswith(draft_digest(written))
        assert client.get(f"/parts/block/variants/{body['variant']}/scad").status_code == 404
        r = client.get(f"/parts/block/scad?variant={body['variant']}")
        assert (r.text, r.headers["x-part-scad"]) == (written, "values")
        assert client.get("/parts/block/variants/not-a-key/scad").status_code == 404

    def test_a_newer_render_from_the_page_stops_the_older(self, openscad, block):
        exe = openscad()
        client = TestClient(app)
        out = {}
        older = threading.Thread(
            target=lambda: out.update(r=_render(client, SCAD + "// SLEEP\n", page="page-1"))
        )
        started = time.monotonic()
        older.start()
        deadline = time.monotonic() + 10
        while not renders(exe) and time.monotonic() < deadline:
            time.sleep(0.02)
        newer = _render(client, SCAD + "// quick\n", page="page-1")
        older.join(15)
        assert newer.status_code == 200, newer.text
        assert out["r"].status_code == 409 and out["r"].json()["detail"]["superseded"] is True
        assert time.monotonic() - started < 15 and _beside(block) == []


class TestAPartBuiltByPython:
    """The snowplow's geometry is Python: its SCAD is shown, generated, and never edited."""

    def test_its_scad_is_the_generated_one(self):
        client = TestClient(app)
        r = client.get("/parts/snowplow/scad")
        assert r.status_code == 200 and r.headers["x-part-scad"] == "generated"
        assert r.text == geometry_scad(SNOWPLOW, {})
        wider = client.get("/parts/snowplow/scad", params={"params": '{"blade_width": 150}'})
        assert wider.text == geometry_scad(SNOWPLOW, {"blade_width": 150.0})
        assert wider.text != r.text
        bad = client.get("/parts/snowplow/scad", params={"params": '{"blade_width": -1}'})
        assert bad.status_code == 422

    def test_a_scad_parts_is_its_source(self):
        client = TestClient(app)
        r = client.get("/parts/calibration_cube/scad")
        assert r.headers["x-part-scad"] == "source"
        assert (
            client.get("/parts/calibration_cube/scad", params={"params": "{}"}).status_code == 422
        )

    def test_the_parts_answer_says_which(self):
        client = TestClient(app)
        assert client.get("/parts/snowplow").json()["files"]["scad"]["editable"] is False
        assert client.get("/parts/snowplow").json()["files"]["scad"]["generated"] is True
        assert client.get("/parts/calibration_cube").json()["files"]["scad"]["editable"] is True

    @pytest.mark.parametrize(
        "method, path, body",
        [
            ("post", "/parts/snowplow/draft/check", {"scad": "cube(1);"}),
            ("post", "/parts/snowplow/draft/render", {"scad": "cube(1);"}),
            ("post", "/parts/snowplow/saved", {"name": "wider", "scad": "cube(1);"}),
        ],
    )
    def test_a_draft_or_a_save_of_it_is_refused(self, method, path, body, openscad):
        exe = openscad()
        r = getattr(TestClient(app), method)(path, json=body)
        assert r.status_code == 403 and "geometry is Python" in r.json()["detail"]
        assert calls(exe) == []


def test_the_cache_lets_go_of_a_drafts_text_with_its_mesh(tmp_path):
    folder = tmp_path / "block"
    folder.mkdir()
    for key in ("a", "b"):
        for suffix in (".stl", ".json", ".scad"):
            (folder / f"{key}{suffix}").write_text("x")
    import os

    os.utime(folder / "a.stl", ns=(1, 0))
    variants.trim_variants(folder, keep=1)
    assert sorted(p.name for p in folder.iterdir()) == ["b.json", "b.scad", "b.stl"]


# --- with a real OpenSCAD that lists parameters, where this machine has one ---------------


def _a_listing_openscad():
    for path in stl_renderer._openscad_candidates():
        if lists_parameters(path):
            return path
    return None


LISTING = _a_listing_openscad()


@pytest.mark.skipif(
    LISTING is None, reason="no OpenSCAD here lists parameters (`apothecary openscad install`)"
)
def test_a_real_snapshot_checks_and_renders_a_draft_beside_its_part(tmp_path, monkeypatch):
    """The draft's include resolves from beside the part, its error is on its own line
    of the part's SCAD, and its new parameter is listed with its range."""
    monkeypatch.setenv("APOTHECARY_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(BasePart, "get_stl_output_path", lambda self: tmp_path / "block.stl")
    part = _part(tmp_path)
    renderer = OpenSCADRenderer(str(LISTING))
    broken = SCAD.replace(
        "hollow = true;", "hollow = true;\nlid = 2; // [1:5]\nassert(width < 10);"
    )
    check = check_draft(part, broken, renderer)
    assert check.lists and [p["name"] for p in check.parameters] == ["width", "hollow", "lid"]
    assert [(m.file, m.line) for m in check.messages if m.level == "error"] == [("block.scad", 6)]
    draft = SCAD.replace("cube([width, depth, 3])", "cube([width, depth, 7])")
    made = make_variant(part, {}, renderer=renderer, draft=draft)
    assert made.success and made.draft == draft_digest(draft)
    assert [round(v, 3) for v in made.measured["size"]] == [34, 20, 7]
    assert _beside(part) == [] and not part.get_stl_output_path().exists()
