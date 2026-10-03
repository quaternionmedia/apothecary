"""Move a slider, validate the staged set, then iterate the design.

A render runs OpenSCAD (`apothecary parts generate-stl` says how long).
Validation is a Pydantic call. Putting
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
    return client.post("/parts/datum_core/validate", json={"params": params}).json()


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
    """The editor is one, over a *target*: a part from the parts folder, or a
    piece made from a picture. The target says where a staged set is validated
    and what Apply does; the staging is the same code for both."""

    def test_the_panel_stages_rather_than_applying(self):
        page = client.get("/viewer/sites/parts_library").text
        for marker in ("stagedDiff", "refreshStage", "committedParams", "apply-btn"):
            assert marker in page, marker

    def test_a_slider_change_calls_validate_not_generate(self):
        """`refreshStage` is what a control's handler runs, and it posts to the
        target's validateUrl, which for either target ends in /validate. Only
        a part target's apply reaches stl/generate; a made piece's PUTs the
        made route.
        """
        page = client.get("/viewer/sites/parts_library").text
        stage = page[page.index("async refreshStage()") : page.index("bindStageActions")]
        assert "target.validateUrl" in stage
        assert "stl/generate" not in stage
        targets = page[page.index("partTarget(ref) {") : page.index("appendPartPanel(node")]
        assert targets.count("/validate`") == 2
        assert targets.count("stl/generate") == 1
        assert "method: 'PUT'" in targets[targets.index("pieceTarget(name") :]

    def test_a_render_commits_what_it_sent(self):
        """Otherwise the next diff is measured against the wrong baseline and
        the panel shows changes that are already in the geometry.
        """
        page = client.get("/viewer/sites/parts_library").text
        bind = page[page.index("bindStageActions(target)") :]
        bind = bind[: bind.index("// The part's parameters")]
        assert "applyEditor" in bind
        render = page[page.index("async applyEditor(target)") :]
        render = render[: render.index("recomputeWorldBounds")]
        # What was sent, once the build succeeded: not what the sliders say by then.
        assert "Object.assign(stage.committed, params)" in render

    def test_a_made_piece_gets_the_same_editor_under_its_provenance(self):
        """Selected appends the editor for a made piece after its picture facts,
        with the same element ids a part's editor has."""
        page = client.get("/viewer/sites/garage").text
        panel = page[page.index("renderSelectedPanel() {") : page.index("bindPictureFacts() {")]
        assert "this.appendEditor(this.pieceTarget(" in panel
        assert panel.index("this.shownFacts") < panel.index("this.appendEditor(this.pieceTarget(")
        editor = page[page.index("appendEditor(target) {") : page.index("openEditor(path) {")]
        for element in ("part-params", "stage-summary", "apply-btn", "revert-btn", "part-envelope"):
            assert f'id="{element}"' in editor, element
