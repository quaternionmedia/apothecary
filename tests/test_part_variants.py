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
from rendered_parts import face_up

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
    ``<path>.calls``, with the values it was given (``$vals``: each -D
    definition, then each top-level ``name = number`` of the SCAD it renders,
    the text's own); a render runs ``body``, then writes an ASCII STL named for
    those values (so each set is a different file; the cache keeps the name in
    its binary STL's header) whose one facet measures 4 x 5 x 6 and, when asked,
    a summary saying 10 x 20 x 30. It exports no CSG, so a render is never
    matched to another by what it compiles."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/sh\n"
        'vals=""; prev=""; last=""\n'
        'for arg in "$@"; do [ "$prev" = -D ] && vals="$vals $arg"; prev="$arg"; last="$arg"; done\n'
        'if [ -f "$last" ]; then\n'
        "  vals=\"$vals $(grep -o '^[a-z_]* *= *[0-9.]*' \"$last\" | tr -d ' ' | tr '\\n' ' ')\"\n"
        "fi\n"
        f'echo "$@ :$vals" >> "{path}.calls"\n'
        f'[ "$1" = --version ] && echo "OpenSCAD version {version}" >&2 && exit 0\n'
        'case " $* " in *" --export-format=csg "*) exit 1;; esac\n'
        f"{body}\n"
        'for arg in "$@"; do case "$arg" in --summary-file=*)\n'
        '  printf \'{"geometry":{"bounding_box":{"min":[0,0,0],"max":[10,20,30],'
        '"size":[10,20,30]}}}\' > "${arg#--summary-file=}";; esac; done\n'
        f'printf "solid%s\\n{FACET}\\nendsolid\\n" "$vals" > "$2"\n'
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

    def test_a_file_rewritten_at_its_size_within_one_tick_is_read_again(self, tmp_path):
        """A rewrite at the same size within the filesystem clock's tick keeps the
        file's size and mtime: its digest is read again, not the one from before."""
        dims = tmp_path / "dims.scad"
        dims.write_text("depth = 20;\n")
        first = variants._file_digest(dims)
        stamp = dims.stat().st_mtime_ns
        dims.write_text("depth = 25;\n")
        os.utime(dims, ns=(stamp, stamp))
        assert variants._file_digest(dims) != first

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
        stl = part.get_stl_output_path().read_bytes()
        assert b"x=12" not in stl and b"x=14" not in stl

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
        """A variant the command line made (`apothecary parts generate-stl -p x=12`)
        stays a variant: a render never writes it over the part's STL."""
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
        assert stl.status_code == 200 and b"size=12 " in stl.content
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
        assert record["params"] == {"size": 12} and record["stl_url"] == body["stl_url"]
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
        exe = openscad('case "$vals " in *"size=11 "*) exec sleep 300;; esac')
        client = TestClient(app)
        thread, older = self._start(client, {"size": 11}, "page-1")
        self._wait_for(exe, "size=11 ")
        newer = _generate(client, {"size": 12}, "page-1")
        thread.join(60)  # an older render left to run takes five minutes
        assert not thread.is_alive()
        assert newer.status_code == 200, newer.text
        assert older["r"].status_code == 409
        assert older["r"].json()["detail"]["superseded"] is True
        assert api._page_renders.running() == 0

    def test_another_pages_request_does_not_stop_it(self, cube, openscad):
        exe = openscad('case "$vals " in *"size=11 "*) sleep 1;; esac')
        client = TestClient(app)
        thread, first = self._start(client, {"size": 11}, "page-1")
        self._wait_for(exe, "size=11 ")
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
        assert b"size=11 " in client.get(a["r"].json()["stl_url"]).content
        assert b"size=13 " in client.get(b["r"].json()["stl_url"]).content


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
            "can_build": True,
            "build_note": None,
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


# --- a part drawn as it rests -------------------------------------------------------


def test_a_part_without_a_rest_pose_is_answered_as_it_prints(cube, openscad):
    """Asked for as it rests, a part that declares no rest pose is answered as it
    prints: the same files, the same keys, nothing more rendered."""
    exe = openscad()
    client = TestClient(app)
    body = client.post(
        "/parts/calibration_cube/stl/generate",
        params={"pose": "rest"},
        json={"params": {"size": 12}},
    ).json()
    assert body["pose"] == "print"
    assert body["stl_url"] == f"/parts/calibration_cube/variants/{body['variant']}/stl"
    assert client.get(body["stl_url"], params={"pose": "rest"}).content == (
        client.get(body["stl_url"]).content
    )
    assert _generate(client).json()["saved"] is True
    own = "/parts/calibration_cube/stl"
    assert client.get(own, params={"pose": "rest"}).content == client.get(own).content
    state = client.get("/parts/calibration_cube/state", params={"pose": "rest"}).json()
    assert state["stl_url"] == own
    assert sorted(p.name for p in cube.parent.glob("calibration_cube*")) == [cube.name]
    assert len(_renders(exe)) == 2


needs_openscad = pytest.mark.skipif(
    not stl_renderer.get_renderer().is_available, reason="OpenSCAD not installed"
)


@pytest.fixture
def pedal(tmp_path, monkeypatch):
    """The footpedal, its own STLs and the variant cache at temp paths."""
    from apothecary.projects.parts.footpedal import DEFAULT

    monkeypatch.setenv("APOTHECARY_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(BasePart, "get_stl_output_path", lambda self: tmp_path / f"{self.name}.stl")
    return DEFAULT


@needs_openscad
def test_a_footpedal_with_theta_changed_rests_on_its_base(pedal):
    """Its rest pose follows theta, as its SCAD draws it: a variant with theta
    changed, asked for as it rests, stands on its base, its button face tilted by
    theta, kept beside the variant under its key and measured as it is drawn. The
    variant's own STL, what a slice of it reads, lies on its button face."""
    from apothecary.slicer.service import part_target

    made = make_variant(pedal, {"theta": -10}, pose="rest")
    assert made.success, (made.error_message, made.messages)
    printed, _ = variant_paths(pedal, made.key)
    rests, _ = variant_paths(pedal, made.key, pose="rest")
    assert (made.pose, made.stl_path) == ("rest", rests)
    lo, hi = bounds(read_mesh(rests))
    assert lo[2] == pytest.approx(0, abs=1e-3)
    assert face_up(rests) == pytest.approx(10, abs=0.5)
    assert made.measured["min"] == pytest.approx(lo, abs=1e-3)
    assert made.measured["max"] == pytest.approx(hi, abs=1e-3)
    assert face_up(printed) == pytest.approx(0, abs=0.5)
    assert part_target("footpedal", variant=made.key).stl(lambda line: None) == (
        printed.read_bytes()
    )
    again = make_variant(pedal, {"theta": -10}, pose="rest")
    assert (again.rendered, again.key, again.measured) == (False, made.key, made.measured)


@needs_openscad
def test_the_routes_serve_each_pose(pedal, tmp_path):
    """With no pose, the print pose, as a slice and a download read it; with
    ?pose=rest, the footpedal as it rests -- its own STL built beside the print one,
    a variant's rest pose made by generate's ?pose=rest -- measured as it is."""
    from apothecary.projects.parts.stl_renderer import build_stl

    client = TestClient(app)

    def drawn(response, name):
        assert response.status_code == 200, response.text
        (tmp_path / name).write_bytes(response.content)
        lo, hi = bounds(read_mesh(tmp_path / name))
        return face_up(tmp_path / name), lo, hi

    assert client.get("/parts/footpedal/stl").status_code == 404
    tilt, lo, hi = drawn(client.get("/parts/footpedal/stl", params={"pose": "rest"}), "a.stl")
    assert (tilt, lo[2]) == (pytest.approx(16, abs=0.5), pytest.approx(0, abs=1e-3))
    state = client.get("/parts/footpedal/state", params={"pose": "rest"}).json()
    assert (state["exists"], state["stl_url"]) == (False, "/parts/footpedal/stl?pose=rest")
    assert state["measured"]["size"]["z"] == pytest.approx(hi[2] - lo[2], abs=1e-3)

    assert build_stl(pedal).success  # as the server's start builds it
    saved = client.post(
        "/parts/footpedal/stl/generate", params={"pose": "rest"}, json={"params": {}}
    ).json()
    assert (saved["saved"], saved["variant"], saved["pose"]) == (True, None, "rest")
    assert saved["stl_url"] == "/parts/footpedal/stl?pose=rest"
    assert saved["measured"] == state["measured"]

    body = client.post(
        "/parts/footpedal/stl/generate", params={"pose": "rest"}, json={"params": {"theta": -10}}
    ).json()
    key = body["variant"]
    assert (body["pose"], body["stl_url"]) == (
        "rest",
        f"/parts/footpedal/variants/{key}/stl?pose=rest",
    )
    tilt, lo, _ = drawn(client.get(body["stl_url"]), "b.stl")
    assert (tilt, lo[2]) == (pytest.approx(10, abs=0.5), pytest.approx(0, abs=1e-3))
    assert body["measured"]["min_point"]["z"] == pytest.approx(0, abs=1e-3)
    record = client.get(f"/parts/footpedal/variants/{key}", params={"pose": "rest"}).json()
    assert (record["pose"], record["stl_url"]) == ("rest", body["stl_url"])
    assert record["measured"] == body["measured"]
    tilt, lo, _ = drawn(client.get(f"/parts/footpedal/variants/{key}/stl"), "c.stl")
    assert tilt == pytest.approx(0, abs=0.5)
    printed = client.get(f"/parts/footpedal/variants/{key}").json()
    assert printed["pose"] == "print"
    assert printed["measured"]["min_point"]["z"] == pytest.approx(lo[2], abs=1e-3)

    other = client.post("/parts/footpedal/stl/generate", json={"params": {"theta": -12}}).json()
    assert (other["pose"], other["stl_url"]) == (
        "print",
        f"/parts/footpedal/variants/{other['variant']}/stl",
    )
    assert client.get(other["stl_url"], params={"pose": "rest"}).status_code == 404
    rest_record = f"/parts/footpedal/variants/{other['variant']}"
    assert client.get(rest_record, params={"pose": "rest"}).status_code == 404
    assert client.get("/parts/footpedal/stl", params={"pose": "sideways"}).status_code == 422


# A part that rests otherwise than it prints, and the same with another rest branch:
# the print pose compiles to the same tree for both, as OpenSCAD drops the branch not
# taken.
RESTS_A_SPHERE = "print = true;\nif (print) cube(10);\nelse sphere(5);\n"
RESTS_A_DISC = RESTS_A_SPHERE.replace("sphere(5)", "cylinder(r=7, h=3)")


@pytest.fixture
def poser(tmp_path, monkeypatch):
    """A part of the test's own declaring a rest pose, asked for by the routes; the
    variant cache at a temp path."""
    monkeypatch.setenv("APOTHECARY_CACHE_DIR", str(tmp_path / "cache"))
    scad = tmp_path / "parts" / "poser" / "poser.scad"
    scad.parent.mkdir(parents=True)
    scad.write_text(RESTS_A_SPHERE)
    part = BasePart(name="poser", source_file=scad, rest={"print": False})
    monkeypatch.setattr(BasePart, "get_stl_output_path", lambda self: tmp_path / f"{self.name}.stl")
    real = api._load_part_wrapper
    monkeypatch.setattr(
        api, "_load_part_wrapper", lambda name: part if name == "poser" else real(name)
    )
    return part


@needs_openscad
def test_drafts_that_differ_only_in_how_they_rest_do_not_share_a_rest_pose(poser, tmp_path):
    """Checked and drawn as it rests, as the page does: a draft that differs from the
    first only in its rest branch compiles the same in the print pose, whose STL it is
    given, linked; its rest pose compiles otherwise and is rendered, each its own
    branch's geometry. A draft that differs from the first only in its comments is
    given both, linked: nothing is rendered."""
    client = TestClient(app)

    def drawn(text):
        checked = client.post("/parts/poser/draft/check", json={"scad": text, "params": {}})
        assert checked.json()["valid"], checked.text
        body = client.post(
            "/parts/poser/draft/render", params={"pose": "rest"}, json={"scad": text, "params": {}}
        ).json()
        assert body["pose"] == "rest", body
        stl = tmp_path / f"{body['variant']}.rest.stl"
        stl.write_bytes(client.get(body["stl_url"]).content)
        lo, hi = bounds(read_mesh(stl))
        return body, stl, [*lo, *hi]

    sphere, sphere_stl, box = drawn(RESTS_A_SPHERE)
    assert sphere["regenerated"] and box == pytest.approx([-5, -5, -5, 5, 5, 5], abs=0.3)

    disc, disc_stl, box = drawn(RESTS_A_DISC)
    assert disc["compiled_from"] == sphere["variant"]  # the print pose: the same tree
    assert disc["regenerated"], disc["message"]  # its rest pose: rendered
    assert box == pytest.approx([-7, -7, 0, 7, 7, 3], abs=0.1)
    assert disc_stl.read_bytes() != sphere_stl.read_bytes()

    again, again_stl, box = drawn(RESTS_A_SPHERE + "// the same, said again\n")
    assert (again["regenerated"], again["compiled_from"]) == (False, sphere["variant"])
    assert again["variant"] not in (sphere["variant"], disc["variant"])
    assert again_stl.read_bytes() == sphere_stl.read_bytes()


@pytest.fixture
def fife(tmp_path, monkeypatch):
    """The fifel, its own STLs and the variant cache at temp paths."""
    from apothecary.projects.parts.fifel import DEFAULT

    monkeypatch.setenv("APOTHECARY_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(BasePart, "get_stl_output_path", lambda self: tmp_path / f"{self.name}.stl")
    return DEFAULT


@needs_openscad
def test_a_fifel_with_another_bore_lies_on_the_floor_and_prints_standing(fife):
    """Its SCAD lays the fife on its side to rest, its lip rest up, and lifts it by
    how far the head's rim reaches below its middle, which follows its bore: a
    variant with a wider bore, asked for as it rests, lies on z 0, the head's rim
    14.42 below the axis and the lip rest's tip 15 above it. The variant's own STL, what a slice of it reads,
    stands on its head as tall as the fife."""
    from apothecary.slicer.service import part_target

    made = make_variant(fife, {"bore": 24}, pose="rest")
    assert made.success, (made.error_message, made.messages)
    printed, _ = variant_paths(fife, made.key)
    rests, _ = variant_paths(fife, made.key, pose="rest")
    assert (made.pose, made.stl_path) == ("rest", rests)
    lo, hi = bounds(read_mesh(rests))
    assert [*lo, *hi] == pytest.approx([-14.5, 0, 0, 14.5, 200, 29.42], abs=0.01)
    assert made.measured["min"] == pytest.approx(lo, abs=1e-3)
    lo, hi = bounds(read_mesh(printed))
    assert (lo[2], hi[2]) == pytest.approx((0, fife.params_model().height), abs=1e-3)
    assert part_target("fifel", variant=made.key).stl(lambda line: None) == (printed.read_bytes())
