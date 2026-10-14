"""The variant cache, and the routes the part loop uses: generate, a cached
variant, and the part's state on disk.

Every render here is by a scripted OpenSCAD (or the installed one, where a
test says so) into the test's own cache; a part's own STL is pointed at a temp
file, so nothing is written into parts/.
"""

from __future__ import annotations

import os
import stat
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from apothecary import api
from apothecary.api import app
from apothecary.meshes import bounds, read_mesh, write_stl
from apothecary.projects.parts import stl_renderer, variants
from apothecary.projects.parts.base import BasePart
from apothecary.projects.parts.calibration_cube import DEFAULT as CUBE
from apothecary.projects.parts.stl_renderer import (
    Cancellation,
    OpenSCADRenderer,
    has_summary,
    read_params_sidecar,
    write_params_sidecar,
)
from apothecary.projects.parts.variants import (
    PageRenders,
    make_variant,
    measure_stl,
    part_state,
    trim_variants,
    variant_key,
    variant_paths,
    wants,
)

# One facet 4 x 5 x 6, which is what the STL measures; the summary says 10 x 20 x 30.
FACET = (
    "facet normal 0 0 0\\nouter loop\\nvertex 0 0 0\\nvertex 4 0 0\\nvertex 0 5 6"
    "\\nendloop\\nendfacet"
)


def _scripted(path: Path, version: str, body: str = "") -> Path:
    """An `openscad` that reports ``version`` and logs its arguments to
    ``<path>.calls``; a render runs ``body``, then writes an STL naming its
    arguments (so each set of -D is a different file) whose one facet
    measures 4 x 5 x 6 and, when asked, a summary saying 10 x 20 x 30."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> "{path}.calls"\n'
        f'[ "$1" = --version ] && echo "OpenSCAD version {version}" >&2 && exit 0\n'
        f"{body}\n"
        'for arg in "$@"; do case "$arg" in --summary-file=*)\n'
        '  printf \'{"geometry":{"bounding_box":{"min":[0,0,0],"max":[10,20,30],'
        '"size":[10,20,30]}}}\' > "${arg#--summary-file=}";; esac; done\n'
        f'printf "solid %s\\n{FACET}\\nendsolid\\n" "$*" > "$2"\n'
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _renders(executable: Path) -> list[str]:
    log = Path(f"{executable}.calls")
    lines = log.read_text().splitlines() if log.exists() else []
    return [line for line in lines if line.startswith("-o")]


@pytest.fixture
def openscad(tmp_path, monkeypatch):
    """``openscad(body="", version=...)``: the scripted OpenSCAD every render in
    the test uses. The variant cache is the test's own."""
    monkeypatch.setenv("APOTHECARY_CACHE_DIR", str(tmp_path / "cache"))

    def install(body: str = "", version: str = "2026.09.27") -> Path:
        exe = _scripted(tmp_path / "bin" / version / "openscad", version, body)
        monkeypatch.setenv("APOTHECARY_OPENSCAD", str(exe))
        monkeypatch.setattr(stl_renderer, "_renderer", None)
        return exe

    return install


class Size(BaseModel):
    x: float = Field(10, gt=0)


def _part(tmp_path: Path, **kw) -> BasePart:
    scad = tmp_path / "parts" / "block" / "block.scad"
    scad.parent.mkdir(parents=True, exist_ok=True)
    if not scad.exists():
        scad.write_text("include <dims.scad>\nx = 10;\ncube([x, depth, 30]);\n")
        (scad.parent / "dims.scad").write_text("depth = 20;\n")
    return BasePart(name="block", source_file=scad, params_model=Size, **kw)


def _later(path: Path, than: Path) -> None:
    moment = than.stat().st_mtime + 5
    os.utime(path, (moment, moment))


class TestTheKey:
    def test_the_same_request_is_the_same_key(self, tmp_path, openscad):
        openscad()
        part, renderer = _part(tmp_path), stl_renderer.get_renderer()
        assert variant_key(part, {"x": 12.0}, renderer) == variant_key(part, {"x": 12.0}, renderer)
        assert variant_key(part, {"x": 12.0}, renderer) != variant_key(part, {}, renderer)

    def test_the_scad_and_what_it_includes_are_in_it(self, tmp_path, openscad):
        openscad()
        part, renderer = _part(tmp_path), stl_renderer.get_renderer()
        before = variant_key(part, {}, renderer)
        (part.part_dir / "dims.scad").write_text("depth = 25;\n")
        after_include = variant_key(part, {}, renderer)
        part.source_file.write_text(part.source_file.read_text() + "// edited\n")
        after_scad = variant_key(part, {}, renderer)
        assert len({before, after_include, after_scad}) == 3

    def test_the_openscad_and_its_backend_are_in_it(self, tmp_path, openscad, monkeypatch):
        old = OpenSCADRenderer(str(openscad(version="2021.01")))
        new = OpenSCADRenderer(str(openscad(version="2026.09.27")))
        part = _part(tmp_path)
        assert variant_key(part, {}, old) != variant_key(part, {}, new)
        same = variant_key(part, {}, new)
        monkeypatch.setattr(variants, "has_manifold", lambda exe: False)
        assert variant_key(part, {}, new) != same


# Two triangles spanning (0, 0, 0) to (10, 20, 30): all a bounding box needs.
BOX = [((0, 0, 0), (10, 0, 0), (10, 20, 30)), ((0, 0, 0), (0, 20, 30), (10, 20, 30))]


class TestMeasuringAnSTL:
    def test_an_stl_is_measured_in_the_frame_its_bounds_are_declared_in(self, tmp_path):
        upright = tmp_path / "upright.stl"
        write_stl(BOX, upright)
        assert measure_stl(upright) == {
            "min": [0, 0, 0],
            "max": [10, 20, 30],
            "size": [10, 20, 30],
        }
        # The same box turned by rotate([90, 0, 0]), as a part's display rotation turns it:
        # (x, y, z) -> (x, -z, y). Measured, it is turned back.
        turned = tmp_path / "turned.stl"
        write_stl([tuple((x, -z, y) for x, y, z in t) for t in BOX], turned)
        assert measure_stl(turned)["size"] == [10, 30, 20]
        assert measure_stl(turned, [90, 0, 0]) == measure_stl(upright)

    def test_nothing_to_measure_is_none(self, tmp_path):
        empty = tmp_path / "empty.stl"
        empty.write_text("solid nothing\nendsolid nothing\n")
        assert measure_stl(empty) is None
        assert measure_stl(tmp_path / "missing.stl") is None


class TestMakingAVariant:
    def test_a_variant_is_the_caches_alone(self, tmp_path, openscad):
        exe = openscad()
        part = _part(tmp_path)
        made = make_variant(part, {"x": 12})
        assert made.success and made.rendered and made.key
        stl, record = variant_paths(part, made.key)
        assert made.stl_path == stl and stl.exists() and record.exists()
        assert b"x=12.0" in stl.read_bytes()
        assert made.measured == {"min": [0, 0, 0], "max": [10, 20, 30], "size": [10, 20, 30]}
        assert made.measured_from == "summary"
        assert (made.openscad, made.backend) == ("OpenSCAD version 2026.09.27", "manifold")
        # The part's own STL is the default variant; this one is not it.
        assert not part.get_stl_output_path().exists() and not made.saved

        again = make_variant(part, {"x": 12})
        assert (again.rendered, again.key, again.measured) == (False, made.key, made.measured)
        assert again.measured_from == "summary"
        assert len(_renders(exe)) == 1

    def test_without_a_summary_the_stl_is_measured(self, tmp_path, openscad):
        openscad(version="2021.01")
        made = make_variant(_part(tmp_path), {"x": 12})
        assert made.measured == {"min": [0, 0, 0], "max": [4, 5, 6], "size": [4, 5, 6]}
        assert made.measured_from == "stl"

    def test_the_defaults_are_also_the_parts_own_stl(self, tmp_path, openscad):
        exe = openscad()
        part = _part(tmp_path)
        made = make_variant(part)
        canonical = part.get_stl_output_path()
        assert canonical.read_bytes() == made.stl_path.read_bytes()
        assert read_params_sidecar(canonical) is None
        assert made.saved
        assert not make_variant(part).rendered
        assert len(_renders(exe)) == 1

    def test_a_value_the_model_defaults_to_is_no_override(self, tmp_path, openscad):
        """A page sends every value its controls hold, the defaults among them."""
        exe = openscad()
        part = _part(tmp_path)
        default = make_variant(part)
        spelled_out = make_variant(part, {"x": 10.0})
        assert spelled_out.key == default.key and spelled_out.params == {}
        assert spelled_out.saved and not spelled_out.rendered
        assert len(_renders(exe)) == 1

    def test_returning_to_the_defaults_costs_nothing(self, tmp_path, openscad):
        exe = openscad()
        part = _part(tmp_path)
        default = make_variant(part)
        make_variant(part, {"x": 12})
        make_variant(part, {"x": 14})
        back = make_variant(part, {})
        assert not back.rendered and back.stl_path.read_bytes() == default.stl_path.read_bytes()
        assert len(_renders(exe)) == 3
        assert b"x=" not in part.get_stl_output_path().read_bytes()

    def test_a_fresh_stl_of_the_parts_own_answers_without_a_render(self, tmp_path, openscad):
        exe = openscad()
        part = _part(tmp_path)
        canonical = part.get_stl_output_path()
        write_stl(BOX, canonical)
        made = make_variant(part)
        assert made.success and not made.rendered and made.saved
        assert (made.key, made.stl_path) == (None, canonical)
        # Built elsewhere, so it is measured from the STL.
        assert (made.measured["size"], made.measured_from) == ([10, 20, 30], "stl")
        assert _renders(exe) == []

    def test_an_edited_include_is_rendered_again(self, tmp_path, openscad):
        exe = openscad()
        part = _part(tmp_path)
        first = make_variant(part)
        (part.part_dir / "dims.scad").write_text("depth = 25;\n")
        _later(part.part_dir / "dims.scad", part.get_stl_output_path())
        second = make_variant(part)
        assert second.rendered and second.key != first.key
        assert len(_renders(exe)) == 2

    def test_a_variant_the_command_line_made_is_never_overwritten(self, tmp_path, openscad):
        """`apothecary parts generate-stl -p x=12` left a variant as the part's STL."""
        exe = openscad()
        part = _part(tmp_path)
        canonical = part.get_stl_output_path()
        canonical.write_text("solid x=12 from the command line\nendsolid\n")
        write_params_sidecar(canonical, {"x": 12.0})

        answered = make_variant(part, {"x": 12})
        assert not answered.rendered and answered.stl_path == canonical

        default = make_variant(part)
        assert default.rendered and default.stl_path != canonical
        assert canonical.read_text().startswith("solid x=12 from the command line")
        assert read_params_sidecar(canonical)["params"] == {"x": 12.0}
        assert len(_renders(exe)) == 1

    def test_force_renders_what_the_cache_has(self, tmp_path, openscad):
        exe = openscad()
        part = _part(tmp_path)
        make_variant(part, {"x": 12})
        assert make_variant(part, {"x": 12}, force=True).rendered
        assert len(_renders(exe)) == 2

    def test_a_render_openscad_refused_is_not_kept(self, tmp_path, openscad):
        exe = openscad(
            "echo \"ERROR: Assertion '(x < 11)' failed in file block.scad, line 3\" >&2\n"
            "echo \"TRACE: called by 'assert' in file block.scad, line 3\" >&2\n"
            'echo "Current top level object is empty." >&2\nexit 1'
        )
        part = _part(tmp_path)
        made = make_variant(part, {"x": 12})
        assert made.failure == "failed" and made.stl_path is None
        error = made.messages[0]
        assert (error.level, error.line) == ("error", 3)
        assert error.file.endswith("parts/block/block.scad") or error.file == "block.scad"
        assert list((tmp_path / "cache" / "part_stl" / "block").glob("*")) == []
        make_variant(part, {"x": 12})
        assert len(_renders(exe)) == 2

    def test_a_cancelled_request_renders_nothing(self, tmp_path, openscad):
        exe = openscad()
        cancel = Cancellation()
        cancel.cancel()
        made = make_variant(_part(tmp_path), {"x": 12}, cancel=cancel)
        assert made.failure == "cancelled" and _renders(exe) == []

    def test_a_part_that_cannot_be_built_here_is_refused(self, tmp_path, openscad):
        class Unbuildable(BasePart):
            def can_generate_stl(self, openscad=None):
                return False, "needs a newer OpenSCAD"

        exe = openscad()
        scad = tmp_path / "u.scad"
        scad.write_text("cube(1);")
        made = make_variant(Unbuildable(name="u", source_file=scad))
        assert (made.failure, made.error_message) == ("refused", "needs a newer OpenSCAD")
        assert _renders(exe) == []


class TestTwoTabs:
    def _together(self, *calls):
        barrier = threading.Barrier(len(calls))
        results = [None] * len(calls)

        def run(i, call):
            barrier.wait()
            results[i] = call()

        threads = [threading.Thread(target=run, args=(i, c)) for i, c in enumerate(calls)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        return results

    def test_different_values_at_once_are_different_files(self, tmp_path, openscad):
        openscad("sleep 0.3")
        part = _part(tmp_path)
        a, b = self._together(
            lambda: make_variant(part, {"x": 11}), lambda: make_variant(part, {"x": 13})
        )
        assert a.key != b.key
        assert b"x=11.0" in a.stl_path.read_bytes() and b"x=13.0" in b.stl_path.read_bytes()
        assert not part.get_stl_output_path().exists()

    def test_the_same_values_at_once_are_one_render(self, tmp_path, openscad):
        exe = openscad("sleep 0.3")
        part = _part(tmp_path)
        a, b = self._together(
            lambda: make_variant(part, {"x": 11}), lambda: make_variant(part, {"x": 11})
        )
        assert a.key == b.key and len(_renders(exe)) == 1
        assert sorted([a.rendered, b.rendered]) == [False, True]


class TestPageRenders:
    def test_a_newer_request_from_the_page_cancels_the_older(self):
        renders = PageRenders()
        older = renders.begin("block", "page-1", wants({"x": 11}, False))
        newer = renders.begin("block", "page-1", wants({"x": 12}, False))
        assert older.cancelled and not newer.cancelled

    def test_the_same_request_again_shares_the_render(self):
        renders = PageRenders()
        older = renders.begin("block", "page-1", wants({"x": 11}, False))
        assert renders.begin("block", "page-1", wants({"x": 11}, False)) is older
        assert not older.cancelled

    def test_another_page_or_part_or_no_page_cancels_nothing(self):
        renders = PageRenders()
        mine = renders.begin("block", "page-1", wants({"x": 11}, False))
        renders.begin("block", "page-2", wants({"x": 12}, False))
        renders.begin("other", "page-1", wants({"x": 12}, False))
        renders.begin("block", None, wants({"x": 12}, False))
        assert not mine.cancelled

    def test_a_finished_render_is_forgotten_and_only_by_its_own(self):
        renders = PageRenders()
        older = renders.begin("block", "page-1", wants({"x": 11}, False))
        newer = renders.begin("block", "page-1", wants({"x": 12}, False))
        renders.end("block", "page-1", older)
        assert renders.running() == 1
        renders.end("block", "page-1", newer)
        assert renders.running() == 0


def test_the_cache_keeps_the_most_recently_served(tmp_path):
    folder = tmp_path / "block"
    folder.mkdir()
    for age, key in enumerate(["c", "b", "a"]):
        (folder / f"{key}.stl").write_text("solid\nendsolid\n")
        (folder / f"{key}.json").write_text("{}")
        os.utime(folder / f"{key}.stl", ns=(1_000_000_000 * (age + 1), 0))
    (folder / ".d.0123.stl").write_text("being written")
    trim_variants(folder, keep=2)
    assert sorted(p.name for p in folder.iterdir()) == [
        ".d.0123.stl",
        "a.json",
        "a.stl",
        "b.json",
        "b.stl",
    ]


class TestPartState:
    def test_no_stl_yet(self, tmp_path):
        state = part_state(_part(tmp_path))
        assert (state.exists, state.stl_url, state.default, state.fresh) == (
            False,
            None,
            True,
            False,
        )

    def test_the_defaults(self, tmp_path):
        part = _part(tmp_path)
        part.get_stl_output_path().write_text("solid\nendsolid\n")
        state = part_state(part)
        assert (state.exists, state.params, state.default, state.fresh) == (True, {}, True, True)
        assert state.stl_url == "/parts/block/stl"

    def test_a_variant_on_disk_and_an_edit_since(self, tmp_path):
        part = _part(tmp_path)
        stl = part.get_stl_output_path()
        stl.write_text("solid\nendsolid\n")
        write_params_sidecar(stl, {"x": 12.0})
        state = part_state(part)
        assert (state.params, state.default, state.fresh) == ({"x": 12.0}, False, True)
        assert state.generated
        _later(part.part_dir / "dims.scad", stl)
        assert part_state(part).fresh is False


# --- the routes ---------------------------------------------------------------------


@pytest.fixture
def cube(tmp_path, monkeypatch, openscad):
    """calibration_cube's own STL at a temp path; returns that path."""
    stl = tmp_path / "calibration_cube.stl"
    monkeypatch.setattr(type(CUBE), "get_stl_output_path", lambda self: stl)
    return stl


def _generate(client, params=None, page=None, force=False):
    query = {"force": str(force).lower()}
    if page:
        query["page"] = page
    return client.post(
        "/parts/calibration_cube/stl/generate", params=query, json={"params": params or {}}
    )


class TestTheGenerateRoute:
    def test_a_variant_is_served_from_its_own_url(self, cube, openscad):
        openscad()
        client = TestClient(app)
        r = _generate(client, {"size": 12})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["regenerated"] is True and body["variant"] and body["saved"] is False
        assert body["stl_url"] == f"/parts/calibration_cube/variants/{body['variant']}/stl"
        stl = client.get(body["stl_url"])
        assert stl.status_code == 200 and b"size=12.0" in stl.content
        assert stl.headers["x-part-variant"] == body["variant"]
        assert not cube.exists()
        assert client.get("/parts/calibration_cube/stl").status_code == 404

        again = _generate(client, {"size": 12}).json()
        assert again["regenerated"] is False and again["variant"] == body["variant"]

    def test_a_variant_is_described_by_its_key(self, cube, openscad):
        """What a reloaded tab, which has only the key, starts from."""
        openscad()
        client = TestClient(app)
        body = _generate(client, {"size": 12}).json()
        record = client.get(f"/parts/calibration_cube/variants/{body['variant']}")
        assert record.status_code == 200, record.text
        record = record.json()
        assert record["params"] == {"size": 12.0} and record["stl_url"] == body["stl_url"]
        assert (record["measured"], record["measured_from"]) == (body["measured"], "summary")
        assert record["saved"] is False and record["backend"] == "manifold"
        missing = client.get("/parts/calibration_cube/variants/0123456789abcdef01234567")
        assert missing.status_code == 404

    def test_measured_bounds_come_beside_the_declared_ones(self, cube, openscad):
        openscad()
        body = _generate(TestClient(app), {"size": 12}).json()
        assert body["bounds"]["size"] == {"x": 12.0, "y": 12.0, "z": 12.0}
        assert body["measured"]["min_point"] == {"x": 0.0, "y": 0.0, "z": 0.0}
        assert body["measured"]["size"] == {"x": 10.0, "y": 20.0, "z": 30.0}
        assert body["measured_from"] == "summary"
        assert body["openscad"] == "OpenSCAD version 2026.09.27"
        assert body["backend"] == "manifold"

    def test_2021_01_is_measured_from_the_stl(self, cube, openscad):
        openscad(version="2021.01")
        body = _generate(TestClient(app), {"size": 12}).json()
        assert body["measured"]["size"] == {"x": 4.0, "y": 5.0, "z": 6.0}
        assert body["measured_from"] == "stl" and body["backend"] == "cgal"

    def test_the_defaults_are_left_as_the_parts_own_stl(self, cube, openscad):
        openscad()
        client = TestClient(app)
        body = _generate(client).json()
        assert body["regenerated"] is True and body["saved"] is True
        assert (
            client.get("/parts/calibration_cube/stl").content == client.get(body["stl_url"]).content
        )
        assert _generate(client).json()["regenerated"] is False

    def test_openscads_errors_come_back_by_line(self, cube, openscad):
        openscad(
            "echo \"WARNING: Ignoring unknown variable 'q' in file calibration_cube.scad, "
            'line 21" >&2\n'
            "echo \"ERROR: Assertion '(size < 11)' failed in file calibration_cube.scad, "
            'line 19" >&2\n'
            'echo "Current top level object is empty." >&2\nexit 1'
        )
        r = _generate(TestClient(app), {"size": 12})
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert detail["message"].startswith("STL generation failed")
        where = [(m["level"], m["file"], m["line"]) for m in detail["messages"]]
        assert where == [
            ("warning", "parts/calibration_cube/calibration_cube.scad", 21),
            ("error", "parts/calibration_cube/calibration_cube.scad", 19),
            ("error", None, None),
        ]

    def test_a_failure_openscad_said_nothing_about_is_a_500(self, cube, openscad):
        openscad("exit 3")
        r = _generate(TestClient(app), {"size": 12})
        assert r.status_code == 500
        assert r.json()["detail"]["messages"] == []

    def test_a_value_the_part_refuses_renders_nothing(self, cube, openscad):
        exe = openscad()
        r = _generate(TestClient(app), {"size": 1})
        assert r.status_code == 422 and _renders(exe) == []

    def test_a_cached_variant_that_is_not_there_is_a_404(self, cube, openscad):
        openscad()
        client = TestClient(app)
        assert (
            client.get("/parts/calibration_cube/variants/0123456789abcdef01234567/stl").status_code
            == 404
        )
        assert (
            client.get("/parts/calibration_cube/variants/..%2F..%2Fsecret/stl").status_code == 404
        )


class TestASupersededRender:
    """A newer request from the same page stops the older OpenSCAD run."""

    def _start(self, client, params, page):
        out = {}
        thread = threading.Thread(target=lambda: out.update(r=_generate(client, params, page)))
        thread.start()
        return thread, out

    def _wait_for(self, exe, text):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if any(text in line for line in _renders(exe)):
                return
            time.sleep(0.02)
        raise AssertionError(f"no render with {text} started")

    def test_the_older_request_from_the_page_is_a_409(self, cube, openscad):
        exe = openscad('case "$*" in *size=11.0*) exec sleep 30;; esac')
        client = TestClient(app)
        started = time.monotonic()
        thread, older = self._start(client, {"size": 11}, "page-1")
        self._wait_for(exe, "size=11.0")
        newer = _generate(client, {"size": 12}, "page-1")
        thread.join(15)
        assert newer.status_code == 200, newer.text
        assert older["r"].status_code == 409
        assert older["r"].json()["detail"]["superseded"] is True
        assert time.monotonic() - started < 15
        assert api._page_renders.running() == 0

    def test_another_pages_request_does_not_stop_it(self, cube, openscad):
        exe = openscad('case "$*" in *size=11.0*) sleep 1;; esac')
        client = TestClient(app)
        thread, first = self._start(client, {"size": 11}, "page-1")
        self._wait_for(exe, "size=11.0")
        other = _generate(client, {"size": 12}, "page-2")
        thread.join(15)
        assert other.status_code == 200 and first["r"].status_code == 200

    def test_two_pages_applying_at_once_each_draw_their_own(self, cube, openscad):
        openscad("sleep 0.3")
        client = TestClient(app)
        one, a = self._start(client, {"size": 11}, "page-1")
        two, b = self._start(client, {"size": 13}, "page-2")
        one.join(15)
        two.join(15)
        assert a["r"].status_code == b["r"].status_code == 200
        assert b"size=11.0" in client.get(a["r"].json()["stl_url"]).content
        assert b"size=13.0" in client.get(b["r"].json()["stl_url"]).content


class TestTheStateRoute:
    def test_it_reads_the_params_sidecar(self, cube, openscad):
        client = TestClient(app)
        assert client.get("/parts/calibration_cube/state").json()["exists"] is False
        write_stl(BOX, cube)
        write_params_sidecar(cube, {"size": 12.0})
        state = client.get("/parts/calibration_cube/state").json()
        assert state["measured"]["size"] == {"x": 10.0, "y": 20.0, "z": 30.0}
        assert state == {
            "part": "calibration_cube",
            "exists": True,
            "stl_url": "/parts/calibration_cube/stl",
            "params": {"size": 12.0},
            "default": False,
            "generated": state["generated"],
            "fresh": True,
            "measured": state["measured"],
            "measured_from": "stl",
        }

    def test_the_pages_apply_never_changes_it(self, cube, openscad):
        openscad()
        client = TestClient(app)
        _generate(client)
        before = client.get("/parts/calibration_cube/state").json()
        _generate(client, {"size": 12})
        assert client.get("/parts/calibration_cube/state").json() == before
        assert before["default"] is True


@pytest.mark.skipif(not stl_renderer.get_renderer().is_available, reason="OpenSCAD not installed")
def test_the_installed_openscad_renders_a_variant_through_the_route(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(type(CUBE), "get_stl_output_path", lambda self: tmp_path / "cube.stl")
    client = TestClient(app)
    r = _generate(client, {"size": 12})
    assert r.status_code == 200, r.text
    body = r.json()
    mesh = tmp_path / "variant.stl"
    mesh.write_bytes(client.get(body["stl_url"]).content)
    lo, hi = bounds(read_mesh(mesh))
    assert [round(hi[a] - lo[a], 2) for a in range(3)] == [12, 12, 12]
    size = body["measured"]["size"]
    assert [round(size[a], 2) for a in "xyz"] == [12, 12, 12]
    summary = has_summary(stl_renderer.get_renderer().openscad_path)
    assert body["measured_from"] == ("summary" if summary else "stl")
    assert not (tmp_path / "cube.stl").exists()
