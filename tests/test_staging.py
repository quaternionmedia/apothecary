"""Move a slider, validate the staged set, then iterate the design.

A render is thirty seconds of OpenSCAD. Validation is a Pydantic call. Putting
the cheap check between the slider and the expensive one means a set that could
never render is refused where it costs nothing, and the reader sees the
envelope a change would produce before paying for it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.projects.parts.datum_core import DEFAULT as CORE

client = TestClient(app)


def validate(params):
    return client.post("/parts/datum-core/validate", json={"params": params}).json()


class TestValidationIsCheapAndHonest:
    def test_a_valid_set_reports_the_envelope_it_would_produce(self):
        body = validate({"walls": 2.4})
        assert body["valid"]
        assert body["bounds"]["size"]["x"] == pytest.approx(45.6)
        assert body["params"]["walls"] == 2.4

    def test_it_renders_nothing(self):
        """The whole point of staging: the expensive step waits for Apply."""
        stl = CORE.source_file.with_suffix(".stl")
        before = stl.stat().st_mtime if stl.exists() else None

        validate({"walls": 2.4})
        validate({"board_x": 55.0})

        after = stl.stat().st_mtime if stl.exists() else None
        assert before == after, "validation touched the rendered geometry"

    def test_a_value_the_model_refuses_is_refused_here(self):
        body = validate({"walls": -1})
        assert not body["valid"]
        assert body["errors"][0]["field"] == "walls"
        assert body["bounds"] is None

    def test_an_unknown_parameter_is_named(self):
        body = validate({"nozzle_diameter": 0.4})
        assert not body["valid"]
        assert body["errors"][0]["field"] == "nozzle_diameter"
        assert "no such parameter" in body["errors"][0]["message"]

    def test_an_empty_set_is_valid_and_changes_nothing(self):
        body = validate({})
        assert body["valid"]
        assert body["params"] == {}

    def test_every_error_names_its_field(self):
        body = validate({"walls": -1, "board_x": -2})
        assert not body["valid"]
        assert {e["field"] for e in body["errors"]} == {"walls", "board_x"}


class TestStagingReachesTheViewer:
    def test_the_panel_stages_rather_than_applying(self):
        page = client.get("/viewer/sites/parts_library").text
        for marker in ("stagedDiff", "refreshStage", "committedParams", "apply-btn"):
            assert marker in page, marker

    def test_a_slider_change_calls_validate_not_generate(self):
        """`refreshStage` is what a control's handler runs, and it posts to
        /validate. Only the Apply handler reaches stl/generate.
        """
        page = client.get("/viewer/sites/parts_library").text
        stage = page[page.index("async refreshStage()") : page.index("bindStageActions")]
        assert "/validate" in stage
        assert "stl/generate" not in stage

    def test_apply_commits_what_rendered(self):
        """Otherwise the next diff is measured against the wrong baseline and
        the panel shows changes that are already in the geometry.
        """
        page = client.get("/viewer/sites/parts_library").text
        bind = page[page.index("bindStageActions(name)") :]
        bind = bind[: bind.index("// The part's parameters")]
        assert "regeneratePart" in bind
        assert "this.committedParams = { ...this.partParams }" in bind
