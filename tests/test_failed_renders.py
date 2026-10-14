"""An error is a failed render.

A development snapshot exits 0 after a failed ``assert`` and writes the geometry
it built before the error; 2021.01 exits 1 and writes nothing. Either way any
message OpenSCAD says at error level fails the render: the answer is a 422 with
the messages by line, and, where geometry was written, ``partial`` names it --
served from outside the variant cache, flagged with the failing line, never
cached as a variant. The check evaluates the staged values as ``-D`` too, so an
error only some values reach is caught before anything renders, and Save of a
variant that fails is refused.

Every OpenSCAD here is scripted (tests/scripted_openscad.py) and every part is
the test's own, in its own folder.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from scripted_openscad import calls, renders, scripted_openscad

from apothecary import api
from apothecary.api import app
from apothecary.projects.parts import stl_renderer
from apothecary.projects.parts.base import BasePart
from apothecary.projects.parts.drafts import compile_draft
from apothecary.projects.parts.variants import (
    make_variant,
    partial_dir,
    read_variant,
    variant_cache_dir,
)

# A part whose SCAD refuses a width of 50 or more, at line 4.
SCAD = """// A block.
include <dims.scad>
width = 34; // [10:100]
assert(width < 50);
cube([width, depth, 3]);
"""


class Width(BaseModel):
    width: float = Field(34, gt=0)


@pytest.fixture
def openscad(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_CACHE_DIR", str(tmp_path / "cache"))

    def install(version: str = "2026.09.27", lists: bool = True, partial=None) -> Path:
        exe = scripted_openscad(tmp_path / "bin" / version / "openscad", version, lists, partial)
        monkeypatch.setenv("APOTHECARY_OPENSCAD", str(exe))
        monkeypatch.setattr(stl_renderer, "_renderer", None)
        return exe

    return install


@pytest.fixture
def block(tmp_path, monkeypatch):
    """A part with no Python model at ``/parts/block``; its STL is the test's own."""
    scad = tmp_path / "parts" / "block" / "block.scad"
    scad.parent.mkdir(parents=True)
    scad.write_text(SCAD)
    (scad.parent / "dims.scad").write_text("depth = 20;\n")
    part = BasePart(name="block", source_file=scad)
    monkeypatch.setattr(BasePart, "get_stl_output_path", lambda self: tmp_path / "block.stl")
    real = api._load_part_wrapper
    monkeypatch.setattr(
        api, "_load_part_wrapper", lambda name: part if name == "block" else real(name)
    )
    return part


def _cached(part: BasePart) -> list:
    folder = variant_cache_dir() / part.name
    return sorted(p.name for p in folder.glob("*")) if folder.is_dir() else []


class TestAFailedRender:
    def test_a_snapshots_partial_geometry_is_kept_out_of_the_cache(self, openscad, block):
        exe = openscad()
        made = make_variant(block, {"width": 60})
        assert made.failure == "failed" and made.rendered and made.key is None
        # Said as an exit code would be: the error itself is in its messages, by line.
        assert made.error_message == "OpenSCAD said an error after writing part of it"
        assert "width < 50" in made.messages[0].message
        partial = made.partial
        assert partial is not None and partial.line == 4 and partial.file == "block.scad"
        assert partial.stl_path.is_file() and partial.stl_path.is_relative_to(partial_dir())
        assert partial.measured == {"min": [0, 0, 0], "max": [10, 20, 30], "size": [10, 20, 30]}
        # Never a variant: nothing in the cache, and the same request renders again.
        assert _cached(block) == [] and read_variant(block, partial.key) is None
        again = make_variant(block, {"width": 60})
        assert again.failure == "failed" and again.rendered and len(renders(exe)) == 2

    def test_2021_01_writes_nothing_so_there_is_no_partial(self, openscad, block):
        openscad("2021.01", lists=False)
        made = make_variant(block, {"width": 60})
        assert made.failure == "failed" and made.partial is None
        assert _cached(block) == [] and not any(partial_dir().rglob("*.stl"))

    def test_an_error_said_with_exit_0_fails_it_whichever_openscad(self, openscad, block):
        """2021.01 too exits 0 saying ERROR: when it drops a mesh it cannot read back."""
        openscad("2021.01", lists=False, partial=True)
        made = make_variant(block, {"width": 40}, draft=SCAD + "assert(false);\n")
        assert made.failure == "failed" and made.partial is not None
        assert made.partial.line == 6 and _cached(block) == []

    def test_values_that_pass_are_a_variant_as_before(self, openscad, block):
        openscad()
        made = make_variant(block, {"width": 40})
        assert made.success and made.key and made.partial is None
        assert read_variant(block, made.key) is not None


class TestTheRoutes:
    def test_the_422_names_the_partial_geometry_and_its_line(self, openscad, block):
        openscad()
        client = TestClient(app)
        r = client.post("/parts/block/stl/generate", json={"params": {"width": 60}})
        assert r.status_code == 422, r.text
        detail = r.json()["detail"]
        assert [(m["level"], m["line"]) for m in detail["messages"]][0] == ("error", 4)
        partial = detail["partial"]
        assert (partial["file"], partial["line"]) == ("block.scad", 4)
        assert partial["stl_url"].startswith("/parts/block/partials/")
        assert partial["measured"]["max_point"] == {"x": 10.0, "y": 20.0, "z": 30.0}
        served = client.get(partial["stl_url"])
        assert served.status_code == 200 and served.content.startswith(b"solid")
        assert served.headers["cache-control"] == "no-store"
        # The key is not a variant: its STL and record are not served.
        key = partial["stl_url"].split("/")[4]
        assert client.get(f"/parts/block/variants/{key}/stl").status_code == 404
        assert client.get(f"/parts/block/variants/{key}").status_code == 404
        assert client.get("/parts/block/partials/not-a-key/stl").status_code == 404

    def test_a_draft_that_fails_is_a_422_with_its_partial(self, openscad, block):
        openscad()
        r = TestClient(app).post(
            "/parts/block/draft/render",
            json={"scad": SCAD.replace("< 50", "< 20"), "params": {}},
        )
        assert r.status_code == 422, r.text
        assert r.json()["detail"]["partial"]["line"] == 4

    def test_on_2021_01_there_is_no_partial_to_name(self, openscad, block):
        openscad("2021.01", lists=False)
        r = TestClient(app).post("/parts/block/stl/generate", json={"params": {"width": 60}})
        assert r.status_code == 422 and r.json()["detail"]["partial"] is None


class TestTheCheckHasTheStagedValues:
    def test_an_error_only_the_staged_values_reach_is_caught(self, openscad, block):
        exe = openscad()
        client = TestClient(app)
        fine = client.post("/parts/block/draft/check", json={"scad": SCAD, "params": {}}).json()
        assert fine["valid"] and fine["with_values"] and fine["messages"] == []
        body = client.post(
            "/parts/block/draft/check", json={"scad": SCAD, "params": {"width": 60}}
        ).json()
        assert body["valid"] is False and body["with_values"]
        assert [(m["level"], m["line"]) for m in body["messages"]] == [("error", 4)]
        # The values are written into the text, and nothing is passed with -D.
        assert "width = 60;" in body["text"]
        compiled = [c for c in calls(exe) if c["format"] == "csg"]
        assert any("width = 60;" in c["text"] for c in compiled)
        assert all("-D" not in c["args"] for c in compiled)
        assert renders(exe) == []

    def test_an_error_the_texts_own_value_reaches_is_caught(self, openscad, block):
        openscad()
        text = SCAD.replace("width = 34;", "width = 70;")
        body = TestClient(app).post("/parts/block/draft/check", json={"scad": text}).json()
        assert body["valid"] is False and body["text"] is None
        assert [(m["level"], m["line"]) for m in body["messages"]] == [("error", 4)]

    def test_a_part_with_a_model_is_checked_with_its_values_at_once(self, openscad, block):
        openscad()
        block.params_model = Width
        client = TestClient(app)
        body = client.post(
            "/parts/block/draft/check", json={"scad": SCAD, "params": {"width": 70}}
        ).json()
        assert body["valid"] is False and body["messages"][0]["line"] == 4
        body = client.post(
            "/parts/block/draft/check", json={"scad": SCAD, "params": {"width": 30}}
        ).json()
        assert body["valid"] and body["messages"] == []

    def test_the_compile_is_remembered_by_its_text_and_values(self, openscad, block):
        exe = openscad()
        first = compile_draft(block, SCAD + "// a\n", {"width": 20})
        assert compile_draft(block, SCAD + "// a\n", {"width": 20}) is first
        compile_draft(block, SCAD + "// a\n", {"width": 21})
        assert len([c for c in calls(exe) if c["format"] == "csg"]) == 2

    def test_what_it_compiled_does_not_change_with_a_comment(self, openscad, block):
        openscad()
        one = compile_draft(block, SCAD + "// a comment\n", {"width": 20})
        two = compile_draft(block, SCAD + "// another\n", {"width": 20})
        three = compile_draft(block, SCAD, {"width": 21})
        assert one.digest and one.digest == two.digest and three.digest != one.digest

    def test_a_compile_that_says_an_error_has_no_digest(self, openscad, block):
        openscad()
        assert compile_draft(block, SCAD, {"width": 60}).digest is None


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout


class TestSaveRefusesAFailure:
    @pytest.fixture
    def in_git(self, block, tmp_path, monkeypatch):
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "no-global-gitconfig"))
        monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
        repo = tmp_path / "parts"
        git(repo, "init", "-q", "-b", "main")
        git(repo, "config", "user.name", "A Person")
        git(repo, "config", "user.email", "person@example.invalid")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "A part")
        return repo

    def test_values_openscad_says_an_error_with_are_not_saved(self, openscad, in_git):
        openscad()
        client = TestClient(app)
        r = client.post("/parts/block/saved", json={"name": "wide", "params": {"width": 60}})
        assert r.status_code == 422, r.text
        detail = r.json()["detail"]
        assert detail["message"].startswith("Not saved") and "line 4" in detail["message"]
        assert detail["messages"][0]["line"] == 4
        assert git(in_git, "for-each-ref", "refs/apothecary/") == ""
        r = client.post("/parts/block/saved", json={"name": "wide", "params": {"width": 45}})
        assert r.status_code == 201, r.text

    def test_an_edit_that_fails_is_not_saved(self, openscad, in_git):
        openscad()
        r = TestClient(app).post(
            "/parts/block/saved", json={"name": "broken", "scad": SCAD + "assert(false);\n"}
        )
        assert r.status_code == 422 and r.json()["detail"]["messages"][0]["line"] == 6
        assert git(in_git, "for-each-ref", "refs/apothecary/") == ""
