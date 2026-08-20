"""A number two documents state differently is not settled by editing one.

`datum-core` has three: the wall thickness and fit clearance, which the
enclosure record and `parts/datum/datum.scad` disagree about, and the board
depth, where the datum packet gives a bound and that part gives a specific
board. Each candidate is recorded with its provenance and put on a slider, so
the choice is made by looking rather than by whoever edits last.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.projects.parts.base import ContestedValue
from apothecary.projects.parts.datum_core import DEFAULT

client = TestClient(app)


class TestContestedAreDeclared:
    def test_the_three_known_disagreements_are_recorded(self):
        assert set(DEFAULT.contested) == {"walls", "tolerence", "board_y"}

    @pytest.mark.parametrize("name", ["walls", "tolerence", "board_y"])
    def test_every_candidate_cites_a_source(self, name):
        """A value with no provenance is an opinion, and cannot be adjudicated."""
        for candidate in DEFAULT.contested[name]:
            assert candidate.source.strip()
            assert candidate.note.strip()

    def test_the_defaults_are_among_the_candidates(self):
        """The part must ship one of the contested values, not a third one."""
        params = DEFAULT.params_model()
        for name, candidates in DEFAULT.contested.items():
            assert getattr(params, name) in [c.value for c in candidates], name

    def test_the_record_value_is_what_the_part_ships(self):
        """Clause 3 of the enclosure record is the one with authority; a part
        that differs has to say why in its docstring, and this one does not.
        """
        params = DEFAULT.params_model()
        assert params.walls == 3.0
        assert params.tolerence == 0.4

    def test_a_part_nobody_disputes_declares_nothing(self):
        from apothecary.projects.parts.calibration_cube import DEFAULT as cube

        assert cube.contested == {}


class TestParamsEndpoint:
    def test_it_describes_every_parameter(self):
        body = client.get("/parts/datum-core/params").json()
        names = {f["name"] for f in body["fields"]}
        assert {"walls", "tolerence", "board_x", "board_y", "show"} <= names

    def test_numeric_fields_carry_a_range_a_slider_can_use(self):
        body = client.get("/parts/datum-core/params").json()
        for field in body["fields"]:
            if field["type"] == "number":
                assert field["min"] < field["max"], field["name"]

    def test_the_range_reaches_every_candidate(self):
        """A slider that cannot reach a candidate cannot be used to judge it."""
        body = client.get("/parts/datum-core/params").json()
        for field in body["fields"]:
            for candidate in field["contested"]:
                assert field["min"] <= candidate["value"] <= field["max"], field["name"]

    def test_candidates_carry_their_provenance_to_the_client(self):
        body = client.get("/parts/datum-core/params").json()
        walls = next(f for f in body["fields"] if f["name"] == "walls")
        sources = {c["source"] for c in walls["contested"]}
        assert any("DRAFT-enclosure-parts-live-in-apothecary" in s for s in sources)
        assert any("parts/datum/datum.scad" in s for s in sources)

    def test_an_unknown_part_is_404(self):
        assert client.get("/parts/no-such-part/params").status_code == 404


class TestDashboardPage:
    def test_it_serves(self):
        response = client.get("/viewer/parts/datum-core")
        assert response.status_code == 200
        assert "datum-core" in response.text

    def test_an_unknown_part_is_404_at_the_page_not_the_fetch(self):
        """Better a 404 than a page that loads and then cannot explain itself."""
        assert client.get("/viewer/parts/no-such-part").status_code == 404

    def test_it_reaches_no_cdn(self):
        page = client.get("/viewer/parts/datum-core").text
        assert "jsdelivr" not in page
        assert '"three": "/vendor/three/build/three.module.js"' in page


class TestChangingAContestedValueChangesTheObject:
    """The point of the dashboard: the disagreement has a visible consequence."""

    def test_wall_thickness_moves_the_envelope(self):
        model = DEFAULT.params_model
        record = DEFAULT.get_bounds(model(walls=3.0).model_dump()).size
        other = DEFAULT.get_bounds(model(walls=2.4).model_dump()).size
        assert record.x == pytest.approx(46.8)
        assert other.x == pytest.approx(45.6)

    def test_board_depth_moves_only_the_depth(self):
        model = DEFAULT.params_model
        bound = DEFAULT.get_bounds(model(board_y=40.0).model_dump()).size
        specific = DEFAULT.get_bounds(model(board_y=30.0).model_dump()).size
        assert bound.y - specific.y == pytest.approx(10.0)
        assert bound.x == pytest.approx(specific.x)


class TestContestedValueModel:
    def test_a_note_is_optional_but_a_source_is_not(self):
        from pydantic import ValidationError

        ContestedValue(value=1.0, source="somewhere")
        with pytest.raises(ValidationError):
            ContestedValue(value=1.0)
