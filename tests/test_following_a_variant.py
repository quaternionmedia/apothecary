"""Slice and the readiness checklist follow the variant a page draws
(docs/plans/part-iteration-2026-10-12.md, item 4).

``POST /slicer/slice`` takes a cached variant's key and slices its STL, and the
slice record names the variant; ``GET /parts/{name}/checklist`` takes the key
and asks about that variant, and takes the build volume of the printer pinned
in a site instead of telling a person to type one.

The variant cache is the test's own, a variant in it written by hand: its STL a
box of a known size, its record what the cache writes. Pins go to the test's
own state folder.
"""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from apothecary import api
from apothecary.api import _site_store, app
from apothecary.meshes import write_stl
from apothecary.projects.parts.calibration_cube import DEFAULT as CUBE
from apothecary.projects.parts.readiness import BOUNDS, Drawn, assess
from apothecary.projects.parts.variants import variant_paths

client = TestClient(app)
KEY = "0123456789abcdef01234567"
BOARD = "printer_1.frame_system.mainboard"


def _box(x: float, y: float, z: float):
    return [((0, 0, 0), (x, 0, 0), (x, y, z)), ((0, 0, 0), (0, y, z), (x, y, z))]


@pytest.fixture
def cached(tmp_path, monkeypatch):
    """``cached(size, params)``: a variant of the calibration cube in the test's
    own cache, measured as ``size`` on each side, rendered with ``params``."""
    monkeypatch.setenv("APOTHECARY_CACHE_DIR", str(tmp_path / "cache"))

    def put(size: float = 12.0, params=None, key: str = KEY, draft=None):
        stl, record = variant_paths(CUBE, key)
        stl.parent.mkdir(parents=True, exist_ok=True)
        write_stl(_box(size, size, size), stl)
        measured = {"min": [0, 0, 0], "max": [size] * 3, "size": [size] * 3}
        record.write_text(
            json.dumps(
                {
                    "part": CUBE.name,
                    "key": key,
                    "params": params if params is not None else {"size": size},
                    "measured": measured,
                    "measured_from": "summary",
                    "messages": [],
                    "draft": draft,
                }
            )
        )
        return stl

    return put


@pytest.fixture
def garage():
    _site_store.reset("garage")
    yield _site_store.get("garage")
    _site_store.reset("garage")


def _check(body, name):
    return next(c for c in body["checks"] if c["name"] == name)


class TestTheChecklistOfAVariant:
    def test_it_asks_about_the_variant_not_the_parts_own_stl(self, cached):
        cached(12.0)
        body = client.get(f"/parts/calibration_cube/checklist?variant={KEY}").json()
        assert body["variant"] == KEY
        assert _check(body, "Geometry renders")["state"] == "pass"
        assert KEY in _check(body, "Geometry renders")["detail"]
        bounds = _check(body, BOUNDS)
        assert bounds["state"] == "pass" and "12.0 x 12.0 x 12.0" in bounds["detail"]

    def test_a_variant_grown_past_what_it_declares_is_blocked_by_the_difference(self, cached):
        cached(12.0, params={"size": 20.0})
        bounds = _check(
            client.get(f"/parts/calibration_cube/checklist?variant={KEY}").json(), BOUNDS
        )
        assert bounds["state"] == "blocked" and "off by 8.00 mm" in bounds["detail"]

    def test_it_fits_by_the_size_it_measured(self, cached):
        cached(30.0)
        body = client.get(
            f"/parts/calibration_cube/checklist?variant={KEY}&build_volume=25,220,250"
        ).json()
        fit = _check(body, "Fits the printer")
        assert fit["state"] == "blocked" and "X 30.0 > 25.0" in fit["detail"]
        assert body["build_volume"] == {"size": [25.0, 220.0, 250.0], "from": "given"}

    def test_a_variant_the_cache_does_not_have_is_a_404(self, cached):
        assert client.get(f"/parts/calibration_cube/checklist?variant={KEY}").status_code == 404
        assert client.get("/parts/calibration_cube/checklist?variant=nope").status_code == 404

    def test_a_part_whose_bounds_are_its_defaults_alone_is_not_compared(self, tmp_path):
        from apothecary.models import BoundingBox3D, Vector3D
        from apothecary.projects.parts.base import BasePart

        plain = BasePart(
            name="plain",
            source_file=CUBE.source_file,
            default_bounds=BoundingBox3D(
                min_point=Vector3D(x=0, y=0, z=0), max_point=Vector3D(x=10, y=10, z=10)
            ),
        )
        drawn = Drawn(
            key=KEY,
            stl=tmp_path / "x.stl",
            params={"size": 20},
            measured={"min": [0, 0, 0], "max": [20] * 3, "size": [20] * 3},
        )
        bounds = next(c for c in assess(plain, drawn=drawn).checks if c.name == BOUNDS)
        assert bounds.state == "unknown" and "defaults only" in bounds.detail


class TestTheBuildVolumeOfThePinnedPrinter:
    def test_the_printer_pinned_in_the_site_gives_it(self, no_arduino_cli, garage):
        assert (
            client.put(
                f"/sites/garage/nodes/{BOARD}/device", json={"identity": "FAKESERIAL1"}
            ).status_code
            == 200
        )
        body = client.get("/parts/calibration_cube/checklist?site=garage").json()
        printer = next(c for c in garage.children if c.name == "printer_1")
        size = [printer.build_volume.x, printer.build_volume.y, printer.build_volume.z]
        assert body["build_volume"] == {"size": size, "from": "printer_1 in garage"}
        fit = _check(body, "Fits the printer")
        assert fit["state"] == "pass" and "(printer_1 in garage)" in fit["detail"]
        assert "--build-volume" not in fit["fix"]

    def test_a_volume_given_is_taken_over_the_pinned_printers(self, no_arduino_cli, garage):
        client.put(f"/sites/garage/nodes/{BOARD}/device", json={"identity": "FAKESERIAL1"})
        body = client.get("/parts/calibration_cube/checklist?site=garage&build_volume=1,1,1").json()
        assert body["build_volume"]["from"] == "given"
        assert _check(body, "Fits the printer")["state"] == "blocked"

    def test_with_no_printer_pinned_it_says_so_and_not_to_type_one(self, no_arduino_cli, garage):
        body = client.get("/parts/calibration_cube/checklist?site=garage").json()
        fit = _check(body, "Fits the printer")
        assert fit["state"] == "unknown" and fit["detail"] == "no printer is pinned in garage"
        assert "pin a printer's board in garage" in fit["fix"]
        assert body["build_volume"] is None

    def test_several_pinned_are_named_and_one_is_chosen(self, garage, monkeypatch):
        monkeypatch.setattr(api, "printers_in", lambda site: ["printer_1", "printer_2"])
        body = client.get("/parts/calibration_cube/checklist?site=garage").json()
        fit = _check(body, "Fits the printer")
        assert fit["state"] == "unknown" and "printer_1, printer_2" in fit["detail"]
        body = client.get("/parts/calibration_cube/checklist?site=garage&printer=printer_1").json()
        assert body["build_volume"]["from"] == "printer_1 in garage"

    def test_an_unknown_site_is_a_404(self):
        assert client.get("/parts/calibration_cube/checklist?site=nowhere").status_code == 404

    def test_without_a_site_the_command_lines_advice_stands(self):
        fit = _check(client.get("/parts/calibration_cube/checklist").json(), "Fits the printer")
        assert fit["fix"] == "pass --build-volume X,Y,Z to check it"


# --- slicing the drawn variant -----------------------------------------------------


def _wait(started: dict, timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        now = client.get(f"/slicer/tasks/{started['id']}").json()
        if now["status"] not in ("pending", "running"):
            return now
        time.sleep(0.05)
    raise AssertionError("the slice did not end")


class TestSlicingAVariant:
    def test_the_variants_stl_is_sliced_and_its_record_names_it(
        self, fake_orcaslicer, cached, garage
    ):
        stl = cached(14.0)
        r = client.post(
            "/slicer/slice",
            json={
                "part": "calibration_cube",
                "site": "garage",
                "printer": "printer_1",
                "variant": KEY,
            },
        )
        assert r.status_code == 202, r.text
        assert KEY in r.json()["title"]
        done = _wait(r.json())
        assert done["status"] == "succeeded", done["lines"]
        made = done["slice"]["record"]["made"]
        assert (made["kind"], made["name"], made["variant"]) == ("part", "calibration_cube", KEY)
        assert made["params"] == {"size": 14.0} and made["draft"] is None
        assert any(f"the variant {KEY} of calibration_cube" in line for line in done["lines"])
        record = client.get(f"/slicer/slices/{done['slice']['record']['file_id']}").json()
        assert record["made"]["variant"] == KEY
        assert stl.exists()

    def test_a_part_standing_in_the_site_slices_its_variant_too(
        self, fake_orcaslicer, cached, garage, monkeypatch
    ):
        from apothecary.projects.parts.footpedal import DEFAULT as PEDAL

        stl, record = variant_paths(PEDAL, KEY)
        stl.parent.mkdir(parents=True, exist_ok=True)
        write_stl(_box(5, 5, 5), stl)
        record.write_text(json.dumps({"part": "footpedal", "params": {}, "draft": "ab" * 32}))
        done = _wait(
            client.post(
                "/slicer/slice",
                json={
                    "part": "footpedal",
                    "site": "garage",
                    "printer": "printer_1",
                    "variant": KEY,
                },
            ).json()
        )
        made = done["slice"]["record"]["made"]
        assert (made["path"], made["variant"], made["draft"]) == ("footpedal", KEY, "ab" * 32)

    def test_a_variant_the_cache_does_not_have_is_refused_at_once(self, fake_orcaslicer, cached):
        r = client.post(
            "/slicer/slice",
            json={"part": "calibration_cube", "printer": "ender3", "variant": KEY},
        )
        assert r.status_code == 422 and "no variant" in r.json()["detail"]
        bad = client.post(
            "/slicer/slice",
            json={"part": "calibration_cube", "printer": "ender3", "variant": "../x"},
        )
        assert bad.status_code == 422
