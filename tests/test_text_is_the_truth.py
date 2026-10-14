"""The text is the truth (docs/plans/part-iteration-2026-10-12.md, "parameters and
text, tied together"), through the routes: a part's assignments read for a page's
first load and by its check, computed values evaluated, values checked by the
part's model with their fields, a part in a submodule edited as its overlay, and a
part whose SCAD is generated kept one way.

Every OpenSCAD here is scripted (tests/scripted_openscad.py); every part and
repository is the test's own.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from scripted_openscad import calls, renders, scripted_openscad, stl_names

from apothecary import api
from apothecary.api import app
from apothecary.projects.parts import stl_renderer, texts
from apothecary.projects.parts.base import BasePart
from apothecary.projects.parts.drafts import draft_digest

SCAD = """// A block.
width = 34; // [10:100]
wall = width * 0.1;
cube([width, 20, 3]);
"""


class Width(BaseModel):
    width: int = Field(34, gt=0, le=100)


@pytest.fixture
def openscad(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_CACHE_DIR", str(tmp_path / "cache"))

    def install(version: str = "2026.09.27", lists: bool = True) -> Path:
        exe = scripted_openscad(tmp_path / "bin" / version / "openscad", version, lists)
        monkeypatch.setenv("APOTHECARY_OPENSCAD", str(exe))
        monkeypatch.setattr(stl_renderer, "_renderer", None)
        return exe

    return install


def _served(monkeypatch, part: BasePart, stl: Path) -> BasePart:
    monkeypatch.setattr(BasePart, "get_stl_output_path", lambda self: stl)
    real = api._load_part_wrapper
    monkeypatch.setattr(
        api, "_load_part_wrapper", lambda name: part if name == part.name else real(name)
    )
    return part


@pytest.fixture
def block(tmp_path, monkeypatch):
    scad = tmp_path / "parts" / "block" / "block.scad"
    scad.parent.mkdir(parents=True)
    scad.write_text(SCAD)
    return _served(monkeypatch, BasePart(name="block", source_file=scad), tmp_path / "block.stl")


client = TestClient(app)


class TestAssignmentsForTheFirstLoad:
    def test_the_parts_own_text_read_without_openscad(self, openscad, block):
        exe = openscad()
        body = client.get("/parts/block/assignments").json()
        assert (body["part"], body["kind"], body["upstream"]) == ("block", "source", None)
        assert body["draft"] == draft_digest(SCAD)
        width, wall = body["assignments"]
        assert (width["name"], width["value"], width["min"], width["max"]) == ("width", 34, 10, 100)
        assert SCAD[width["from"] : width["to"]] == "34" and width["line"] == 2
        assert (wall["computed"], wall["value_known"], wall["value"]) == (True, False, None)
        assert calls(exe) == []

    def test_a_computed_value_is_known_once_a_check_evaluated_it(self, openscad, block):
        openscad()
        checked = client.post("/parts/block/draft/check", json={"scad": SCAD}).json()
        wall = next(a for a in checked["assignments"] if a["name"] == "wall")
        assert (wall["value"], wall["printed"], wall["value_known"]) == (3.4, "3.4", True)
        assert wall["expression"] == "width * 0.1"
        again = client.get("/parts/block/assignments").json()["assignments"]
        assert next(a for a in again if a["name"] == "wall")["value"] == 3.4

    def test_the_text_the_page_holds(self, openscad, block):
        body = client.post(
            "/parts/block/assignments", json={"scad": SCAD.replace("34", "40")}
        ).json()
        assert body["assignments"][0]["value"] == 40

    def test_the_computed_values_echo_after_the_text_and_move_no_line(self, openscad, block):
        exe = openscad()
        client.post("/parts/block/draft/check", json={"scad": SCAD})
        (compiled,) = [c for c in calls(exe) if c["format"] == "csg"]
        assert compiled["text"].startswith(SCAD)
        assert compiled["text"][len(SCAD) :] == '\necho("__apothecary_value__", "wall", wall);\n'


class TestTheModelChecksTheTextsValues:
    def test_each_value_with_its_field_and_why_it_is_refused(self, openscad, block):
        openscad()
        block.params_model = Width
        fine = client.post("/parts/block/draft/check", json={"scad": SCAD}).json()
        assert fine["valid"] and fine["values"] == [
            {
                "name": "width",
                "field": "width",
                "value": 34,
                "computed": False,
                "valid": True,
                "message": None,
            }
        ]
        for bad, says in (
            ("width = 120;", "less than or equal to 100"),
            ("width = 3.5;", "integer"),
        ):
            body = client.post(
                "/parts/block/draft/check", json={"scad": SCAD.replace("width = 34;", bad)}
            ).json()
            assert body["valid"] is False
            (value,) = body["values"]
            assert value["valid"] is False and says in value["message"]
            assert body["errors"][0]["field"] == "width"

    def test_a_refused_value_is_not_rendered_or_saved(self, openscad, block):
        exe = openscad()
        block.params_model = Width
        bad = SCAD.replace("width = 34;", "width = 120;")
        r = client.post("/parts/block/draft/render", json={"scad": bad})
        assert r.status_code == 422 and "width" in r.json()["detail"]
        assert renders(exe) == []

    def test_a_render_passes_nothing_on_the_side(self, openscad, block):
        exe = openscad()
        body = client.post(
            "/parts/block/draft/render", json={"scad": SCAD.replace("34", "50")}
        ).json()
        (render,) = renders(exe)
        assert "-D" not in render["args"] and "width = 50;" in render["text"]
        assert body["params"] == {"width": 50}
        assert stl_names(client.get(body["stl_url"]).content).startswith(
            draft_digest(SCAD.replace("34", "50"))
        )


class TestAPartWhoseSCADIsGenerated:
    @pytest.mark.parametrize(
        "method,path,body",
        [
            ("get", "/parts/rc.snowplow/assignments", None),
            ("post", "/parts/rc.snowplow/assignments", {"scad": "cube(1);"}),
            ("post", "/parts/rc.snowplow/draft/check", {"scad": "cube(1);"}),
            ("post", "/parts/rc.snowplow/draft/render", {"scad": "cube(1);"}),
            ("post", "/parts/rc.snowplow/saved", {"name": "x", "scad": "cube(1);"}),
        ],
    )
    def test_its_text_is_not_edited_and_says_why(self, method, path, body, openscad):
        openscad()
        r = getattr(client, method)(path, **({"json": body} if body else {}))
        assert r.status_code == 403 and "geometry is Python" in r.json()["detail"]
        assert "Its parameters are what to edit" in r.json()["detail"]


# --- a part in a submodule, edited as its overlay -------------------------------------------

UPSTREAM = "// The library.\nsize = 10; // [1:50]\nlid = true;\ncube(size);\n"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture
def thing(tmp_path, monkeypatch, openscad):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "no-global-gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.name", "Upstream"),
        ("config", "user.email", "upstream@example.invalid"),
    ):
        git(upstream, *args)
    (upstream / "lib.scad").write_text(UPSTREAM)
    git(upstream, "add", "-A")
    git(upstream, "commit", "-q", "-m", "A library")
    repo = tmp_path / "super"
    (repo / "parts" / "thing").mkdir(parents=True)
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.name", "A Person"),
        ("config", "user.email", "person@example.invalid"),
    ):
        git(repo, *args)
    (repo / ".gitignore").write_text("parts/**/.*.draft.scad\n")
    git(
        repo,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(upstream),
        "parts/thing/upstream",
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "A part from upstream")
    part = BasePart(name="thing", source_file=repo / "parts" / "thing" / "upstream" / "lib.scad")
    return _served(monkeypatch, part, tmp_path / "thing.stl")


class TestAPartInASubmodule:
    def test_its_scad_is_its_overlay_and_its_upstream_is_served_read_only(self, thing):
        r = client.get("/parts/thing/scad")
        assert r.headers["x-part-scad"] == "overlay"
        assert r.headers["x-part-upstream"].endswith("parts/thing/upstream/lib.scad")
        assert "include <upstream/lib.scad>\n" in r.text and texts.own_text(thing) == r.text
        up = client.get("/parts/thing/upstream")
        assert (up.text, up.headers["x-part-scad"]) == (UPSTREAM, "upstream")
        assert client.get("/parts/rc.snowplow/upstream").status_code == 404

    def test_its_assignments_are_the_overlays_and_the_upstream_values_it_does_not_set(self, thing):
        text = texts.own_text(thing) + "size = 20;\n"
        body = client.post("/parts/thing/assignments", json={"scad": text}).json()
        assert body["kind"] == "overlay" and body["upstream"].endswith("lib.scad")
        size, lid = body["assignments"]
        assert (size["name"], size["value"], size["set"]) == ("size", 20, True)
        assert text[size["from"] : size["to"]] == "20"
        assert (lid["name"], lid["value"], lid["set"], lid["from"], lid["line"]) == (
            "lid",
            True,
            False,
            None,
            None,
        )

    def test_its_check_and_render_take_the_overlay_written_beside_where_it_is_saved(
        self, thing, openscad
    ):
        exe = openscad()
        text = texts.own_text(thing) + "size = 20;\n"
        checked = client.post("/parts/thing/draft/check", json={"scad": text}).json()
        assert checked["valid"] and checked["kind"] == "overlay"
        # The parameters are the upstream's, as its customizer lists them.
        assert [f["name"] for f in checked["fields"]] == ["size", "lid"]
        made = client.post("/parts/thing/draft/render", json={"scad": text}).json()
        assert made["draft"] == draft_digest(text) and made["params"] == {"size": 20}
        overlay_dir = thing.source_file.parent.parent
        assert {Path(c["scad"]).parent for c in calls(exe) if c["text"] == text} == {overlay_dir}
        assert git(thing.source_file.parent, "status", "--porcelain") == ""

    def test_its_upstream_text_as_it_is_means_the_overlay_setting_nothing(self, thing, openscad):
        openscad()
        body = client.post("/parts/thing/draft/check", json={"scad": UPSTREAM}).json()
        assert body["edited"] is False and body["draft"] == draft_digest(texts.own_text(thing))

    def test_an_edit_of_its_upstream_text_is_refused_saying_why(self, thing, openscad):
        openscad()
        for path in (
            "/parts/thing/draft/check",
            "/parts/thing/draft/render",
            "/parts/thing/assignments",
        ):
            r = client.post(path, json={"scad": UPSTREAM.replace("cube", "sphere")})
            assert r.status_code == 403 and "edited as its overlay" in r.json()["detail"]
