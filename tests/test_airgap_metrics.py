"""The Airgap panel's metrics document: its schema, a view of it, the routes and the command.

The panel computes; Python validates and renders. These tests hold the document's contract
(``airgap/metrics/1``: four group ids, open keys, finite values) and the view's promise that
it rounds for display and never recomputes.
"""

from __future__ import annotations

import json
import re

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apothecary.airgap_metrics import (
    SCHEMA,
    AirgapMetrics,
    Metric,
    format_value,
    load_metrics,
    render_markdown,
)
from apothecary.api import app
from apothecary.cli import cli
from apothecary.projects.parts.skeleton import ROOT

GOOD = {
    "schema": SCHEMA,
    "generated_at": "2026-10-17T02:00:00.000Z",
    "units": "SI unless stated; lengths in mm where labelled",
    "preset": "mobius",
    "groups": [
        {
            "id": "geometry",
            "metrics": [
                {"key": "bore_s0", "label": "bore s₀", "value": 37.86, "unit": "mm"},
                {"key": "stator_cover", "label": "stator cover", "value": 100, "unit": "%"},
            ],
        },
        {
            "id": "field",
            "title": "Field and torque (static)",
            "metrics": [
                {"key": "mean_torque", "label": "mean torque", "value": 0.00716, "unit": "N·m"},
                {"key": "dominant_order", "label": "dominant ripple order", "value": 12},
                {"key": "lcm", "label": "lcm(Nr, Ns)", "value": None, "note": "no teeth"},
            ],
        },
        {
            "id": "dynamics",
            "metrics": [{"key": "touchdown", "label": "touchdown", "value": False}],
        },
    ],
}


class TestTheDocument:
    def test_a_good_document_reads_and_is_addressed_by_group_and_key(self):
        doc = AirgapMetrics.model_validate(GOOD)
        assert doc.schema_ == SCHEMA
        assert doc.get("field.mean_torque").value == pytest.approx(0.00716)
        assert doc.flat()["geometry.stator_cover"] == 100
        assert doc.groups[0].title == "Geometry"  # the group's title filled from its id
        assert doc.groups[1].title == "Field and torque (static)"

    def test_the_schema_key_keeps_its_name_through_a_round_trip(self):
        dumped = AirgapMetrics.model_validate(GOOD).model_dump(by_alias=True)
        assert dumped["schema"] == SCHEMA
        assert "schema_" not in dumped

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda d: d.update(schema="airgap/metrics/0"),
            lambda d: d["groups"].append({"id": "thermal", "metrics": []}),
            lambda d: d["groups"].append({"id": "geometry", "metrics": []}),
            lambda d: d["groups"][0]["metrics"].append(
                {"key": "bore_s0", "label": "dup", "value": 1}
            ),
            lambda d: d["groups"][0]["metrics"].append(
                {"key": "Bad Key", "label": "x", "value": 1}
            ),
            lambda d: d.pop("generated_at"),
        ],
        ids=[
            "schema",
            "unknown-group",
            "duplicate-group",
            "duplicate-key",
            "bad-key",
            "no-timestamp",
        ],
    )
    def test_a_document_off_the_contract_is_refused(self, mutate):
        bad = json.loads(json.dumps(GOOD))
        mutate(bad)
        with pytest.raises(ValidationError):
            AirgapMetrics.model_validate(bad)

    def test_a_value_that_is_not_finite_is_refused_null_stands_for_unavailable(self):
        bad = json.loads(json.dumps(GOOD))
        bad["groups"][0]["metrics"][0]["value"] = float("inf")
        with pytest.raises(ValidationError):
            AirgapMetrics.model_validate(bad)


class TestTheView:
    def test_the_markdown_rounds_for_display_and_recomputes_nothing(self):
        md = render_markdown(AirgapMetrics.model_validate(GOOD))
        assert md.startswith("# Airgap metrics")
        assert "## Geometry" in md and "## Dynamics" in md
        assert "| bore s₀ (`geometry.bore_s0`) | 37.9 mm |" in md
        assert "| lcm(Nr, Ns) (`field.lcm`) | — | no teeth |" in md
        assert "| touchdown (`dynamics.touchdown`) | no |" in md

    def test_a_value_is_shown_by_its_size_and_kind(self):
        assert format_value(Metric(key="a", label="a", value=1616.0, unit="g")) == "1616 g"
        assert (
            format_value(Metric(key="a", label="a", value=0.000161, unit="kg·m²"))
            == "1.610e-04 kg·m²"
        )
        assert format_value(Metric(key="a", label="a", value=True)) == "yes"
        assert format_value(Metric(key="a", label="a", value="auto")) == "auto"

    def test_a_document_loads_from_a_file(self, tmp_path):
        p = tmp_path / "m.json"
        p.write_text(json.dumps(GOOD), encoding="utf-8")
        assert load_metrics(p).preset == "mobius"


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


class TestTheRoutes:

    def test_the_schema_is_published(self, client):
        r = client.get("/airgap/metrics/schema")
        assert r.status_code == 200
        assert r.json()["properties"]["schema"]["const"] == SCHEMA

    def test_a_document_is_read_back_normalized_or_as_markdown(self, client):
        r = client.post("/airgap/metrics/validate", json=GOOD)
        assert r.status_code == 200 and r.json()["groups"][0]["title"] == "Geometry"
        r = client.post("/airgap/metrics/validate?format=md", json=GOOD)
        assert r.status_code == 200 and r.text.startswith("# Airgap metrics")
        r = client.post("/airgap/metrics/validate", json={"schema": "nope"})
        assert r.status_code == 422


class TestTheCommand:
    def test_validate_says_ok_or_prints_the_document_or_its_markdown(self, tmp_path):
        p = tmp_path / "m.json"
        p.write_text(json.dumps(GOOD), encoding="utf-8")
        runner = CliRunner()
        r = runner.invoke(cli, ["airgap", "metrics", "validate", str(p)])
        assert r.exit_code == 0 and r.output.startswith("OK airgap/metrics/1")
        r = runner.invoke(cli, ["airgap", "metrics", "validate", str(p), "--format", "md"])
        assert r.exit_code == 0 and "## Geometry" in r.output
        r = runner.invoke(cli, ["airgap", "metrics", "validate", str(p), "--format", "json"])
        assert r.exit_code == 0 and json.loads(r.output)["schema"] == SCHEMA

    def test_validate_refuses_a_document_off_the_contract(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text(
            json.dumps({"schema": SCHEMA, "groups": [{"id": "thermal"}]}), encoding="utf-8"
        )
        r = CliRunner().invoke(cli, ["airgap", "metrics", "validate", str(p)])
        assert r.exit_code == 1 and "Invalid metrics document" in r.output

    def test_schema_prints_the_contract(self):
        r = CliRunner().invoke(cli, ["airgap", "metrics", "schema"])
        assert r.exit_code == 0 and json.loads(r.output)["title"] == "AirgapMetrics"


class TestThePanelInThePage:
    """The panel is a window of the viewer's layout, each of its sections a window of
    its own, mounted from its own module, and the module speaks the metrics document
    this schema reads."""

    def test_the_page_mounts_the_panel_from_the_vendored_free_module(self):
        page = (ROOT / "templates" / "fractal_viewer.html.j2").read_text(encoding="utf-8")
        assert "panels.register('airgap'" in page
        assert "import { mountAirgap, AIRGAP_SECTIONS } from '/static/widgets/airgap.js'" in page
        assert "for (const sec of AIRGAP_SECTIONS)" in page
        assert 'href="{{ base_url }}/static/widgets/airgap.css"' in page
        module = (ROOT / "apothecary" / "static" / "widgets" / "airgap.js").read_text(
            encoding="utf-8"
        )
        assert "export function mountAirgap" in module
        # Every section the module exports is a part of its markup, moved into a window.
        sections = re.findall(r"\{ id: \"([\w-]+)\", title:", module)
        assert sections and all(f'data-section="{s}"' in module for s in sections)
        assert f"schema:'{SCHEMA}'" in module
        # Nothing of the panel's comes from outside the page.
        assert not re.search(r"https?://", module)
        assert "import {" in module and "/static/widgets/assignments.js" in module

    def test_the_panels_group_ids_are_the_schemas(self):
        module = (ROOT / "apothecary" / "static" / "widgets" / "airgap.js").read_text(
            encoding="utf-8"
        )
        ids = set(re.findall(r"\{id:'(\w+)',title:", module))
        assert ids == {"geometry", "windings", "field", "dynamics"}

    def test_the_panel_reads_the_scads_names_and_writes_them_back(self):
        """The names the panel maps are the part's top-level assignments, every one."""
        from apothecary.projects.parts.airgap import Params

        module = (ROOT / "apothecary" / "static" / "widgets" / "airgap.js").read_text(
            encoding="utf-8"
        )
        flat = set(Params().flat())
        flat -= {
            "show_rotor",
            "show_stator",
            "show_windings",
            "resolution",
        }  # drawing, not geometry
        named = set(re.findall(r"'(\w+)'", module))
        side_keys = re.search(r"side: \[([^\]]+)\]", module).group(1)
        sides = re.findall(r"'(\w+)'", side_keys)
        snake = lambda k: re.sub(r"[A-Z]", lambda m: "_" + m.group(0).lower(), k)  # noqa: E731
        reachable = {f"{side}_{snake(k)}" for side in ("rotor", "stator") for k in sides}
        reachable |= {n for n in named if n in flat}
        assert flat <= reachable, sorted(flat - reachable)
