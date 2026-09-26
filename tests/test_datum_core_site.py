"""datum_core exists twice: as a printable SCAD file and as a navigable tree.

Two descriptions of one object drift the moment nothing compares them, so the
first test here reads the SCAD file's own defaults and holds the assembly to
them. The rest check that the tree is actually navigable to the bottom and that
every node in it compiles.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from apothecary import datum_core_site as dc
from apothecary.api import app
from apothecary.datum_core_site import create_datum_core_site, validate_datum_core
from apothecary.projects.parts.skeleton import ROOT

client = TestClient(app)

CORE_SCAD = ROOT / "parts" / "datum_core" / "datum_core.scad"
CAP_SCAD = ROOT / "parts" / "datum_cap" / "datum_cap.scad"

# Every constant the assembly claims to share with the printable part.
# The tray's numbers live in datum_core.scad, the cover's in datum_cap.scad.
SHARED_CORE = [
    "board_x", "board_y", "board_t", "board_clearance",
    "walls", "tolerence", "floor_t", "corner_r", "standoff_h", "headroom",
    "mount_inset", "boss_d", "screw_d",
    "connector_w", "connector_h", "connector_margin",
]
SHARED_CAP = [
    "lid_t", "lip_h", "indicator_d", "indicator_x", "indicator_y",
    "contact_d", "contact_pitch_x", "contact_pitch_y",
]


def scad_defaults(path=None) -> dict[str, float]:
    """Top-level numeric assignments from a SCAD file."""
    values = {}
    for line in (path or CORE_SCAD).read_text(encoding="utf-8").splitlines():
        match = re.match(r"^(\w+)\s*=\s*(-?[\d.]+)\s*;", line)
        if match:
            values[match.group(1)] = float(match.group(2))
    return values


class TestTheTwoDescriptionsAgree:
    def test_both_scad_files_are_parseable(self):
        assert CORE_SCAD.is_file() and CAP_SCAD.is_file()
        assert len(scad_defaults(CORE_SCAD)) >= len(SHARED_CORE)
        assert len(scad_defaults(CAP_SCAD)) >= len(SHARED_CAP)

    @pytest.mark.parametrize("name", SHARED_CORE)
    def test_each_tray_dimension_matches(self, name):
        """The assembly models the parts, so its numbers are theirs."""
        assert scad_defaults(CORE_SCAD)[name] == pytest.approx(getattr(dc, name.upper()))

    @pytest.mark.parametrize("name", SHARED_CAP)
    def test_each_cover_dimension_matches(self, name):
        assert scad_defaults(CAP_SCAD)[name] == pytest.approx(getattr(dc, name.upper()))

    def test_derived_envelope_matches_the_part(self):
        # What `apothecary parts info datum_core` reports for the tray.
        assert (dc.OUTER_X, dc.OUTER_Y, dc.TRAY_H) == pytest.approx((46.8, 46.8, 15.6))


class TestTheTreeIsNavigable:
    def setup_method(self):
        self.site = create_datum_core_site()

    def _walk(self, node, path=""):
        here = f"{path}.{node.name}" if path else node.name
        yield here, node
        for child in [*node.children, *node.additions, *node.subtractions]:
            yield from self._walk(child, here)

    def test_every_expected_node_is_present(self):
        names = {path for path, _ in self._walk(self.site)}
        for expected in (
            "datum_core.tray.shell.cavity",
            "datum_core.tray.shell.connector-opening",
            "datum_core.tray.mounting.boss-front-left.pilot-hole",
            "datum_core.lid.plate.indicator-light-pipe",
            "datum_core.lid.plate.contact-back-right",
            "datum_core.lid.lip",
        ):
            assert expected in names, expected

    def test_it_goes_four_levels_deep(self):
        depths = [path.count(".") for path, _ in self._walk(self.site)]
        assert max(depths) == 4

    def test_every_node_compiles(self):
        """A node that cannot compile is a node the viewer cannot render."""
        for _path, node in self._walk(self.site):
            node.to_scad_object().render()  # raises if it cannot

    def test_the_four_standoffs_each_carry_a_pilot_hole(self):
        holes = [p for p, _ in self._walk(self.site) if p.endswith("pilot-hole")]
        assert len(holes) == 4

    def test_the_lid_carries_four_contacts_and_one_indicator(self):
        names = [p.rsplit(".", 1)[-1] for p, _ in self._walk(self.site)]
        assert sum(n.startswith("contact-") for n in names) == 4
        assert names.count("indicator-light-pipe") == 1


class TestGeometry:
    def test_the_openings_are_actually_cut(self):
        scad = create_datum_core_site().render()
        lid = scad[scad.index("// Structure: lid") :]
        assert "difference()" in lid
        assert lid.count(f"r={dc.CONTACT_D / 2}") == 4
        assert lid.count(f"r={dc.INDICATOR_D / 2}") == 1

    def test_corners_are_rounded_not_square(self):
        scad = create_datum_core_site().render()
        assert "hull()" in scad
        assert f"r={dc.CORNER_R}" in scad

    def test_curves_are_rendered_at_the_parts_facet_count(self):
        """At OpenSCAD's default a hulled corner falls short of its own radius,
        and the assembly then reports an envelope narrower than the part's.
        """
        assert f"$fn={dc.CURVE_FACETS}" in create_datum_core_site().render()


class TestLayoutValidation:
    def test_the_default_explosion_is_valid(self):
        assert validate_datum_core(create_datum_core_site()).is_valid

    def test_a_lid_sunk_into_the_tray_is_a_violation(self):
        site = create_datum_core_site()
        lid = next(s for s in site.children if s.name == "lid")
        lid.position.z = dc.TRAY_H - 5
        report = validate_datum_core(site)
        assert not report.is_valid
        assert "inside the tray" in report.violations[0].message


class TestServedAsASite:
    def test_it_is_registered(self):
        assert "datum_core" in client.get("/sites").json()

    def test_the_tree_reaches_the_viewer(self):
        body = client.get("/sites/datum_core").json()
        assert body["is_valid"] is True
        assert {s["name"] for s in body["structures"]} == {"tray", "lid"}
        assert "hull()" in body["scad"]

    @pytest.mark.slow
    @pytest.mark.parametrize(
        "path", ["tray", "tray.shell", "tray.mounting", "lid", "lid.plate", "lid.lip"]
    )
    def test_each_node_renders_on_demand(self, path):
        from apothecary.projects.parts.stl_renderer import get_renderer

        if not get_renderer().is_available:
            pytest.skip("OpenSCAD not installed")
        response = client.get(f"/sites/datum_core/nodes/{path}/stl")
        assert response.status_code == 200, response.text
        assert len(response.content) > 500
