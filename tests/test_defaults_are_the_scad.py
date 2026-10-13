"""A part's default is its SCAD file as saved (docs/parts-authoring.md): where a Python
model's default and its SCAD's own value disagree, the part's checklist and ``apothecary
problems`` say so, naming each value."""

from __future__ import annotations

from importlib import import_module

from pydantic import BaseModel, Field

from apothecary.projects.parts.base import BasePart
from apothecary.projects.parts.readiness import BLOCKED, DEFAULTS, PASS, assess
from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.parts.texts import defaults_disagree
from apothecary.projects.registry import scan_projects
from apothecary.spaces import APOTHECARY, KIND_OWNER, _readiness_problems


class Size(BaseModel):
    size: float = Field(10.0, gt=0)
    hollow: bool = True
    label: str = "a"


def _part(tmp_path, text: str, model=Size) -> BasePart:
    scad = tmp_path / "p.scad"
    scad.write_text(text)
    return BasePart(name="p", source_file=scad, params_model=model)


class TestWhereTheyDisagree:
    def test_each_value_the_model_says_otherwise_is_named(self, tmp_path):
        part = _part(tmp_path, 'size = 12; // [1:50]\nhollow = true;\nlabel = "b";\ncube(size);\n')
        assert defaults_disagree(part) == [
            "size: model 10.0, SCAD 12",
            "label: model 'a', SCAD 'b'",
        ]

    def test_the_same_value_written_otherwise_agrees(self, tmp_path):
        part = _part(tmp_path, 'size = 10; hollow = true; label = "a";\n')
        assert defaults_disagree(part) == []

    def test_a_computed_or_missing_value_is_not_compared(self, tmp_path):
        part = _part(tmp_path, "w = 2;\nsize = w * 6;\n")
        assert defaults_disagree(part) == []

    def test_nothing_to_compare_without_a_model_or_for_generated_scad(self, tmp_path):
        from apothecary.projects.parts.rc_snowplow import DEFAULT as SNOWPLOW

        assert defaults_disagree(_part(tmp_path, "size = 3;\n", model=None)) is None
        assert defaults_disagree(SNOWPLOW) is None


class TestTheChecklistAndProblemsSayIt:
    def test_the_checklist_blocks_on_a_disagreement_naming_it(self, tmp_path):
        part = _part(tmp_path, "size = 12;\n")
        check = next(c for c in assess(part).checks if c.name == DEFAULTS)
        assert check.state == BLOCKED and "size: model 10.0, SCAD 12" in check.detail
        assert "the SCAD as saved is the part's default" in check.fix
        agree = next(
            c for c in assess(_part(tmp_path, "size = 10;\n")).checks if c.name == DEFAULTS
        )
        assert agree.state == PASS

    def test_problems_report_it_as_this_repositorys_to_close(self, tmp_path):
        part = _part(tmp_path, "size = 12;\n")
        found = [p for p in _readiness_problems(part, assess(part)) if p.kind == "disagree"]
        assert len(found) == 1 and found[0].owner == APOTHECARY == KIND_OWNER["disagree"]
        assert "size: model 10.0, SCAD 12" in found[0].detail

    def test_no_part_has_none_today(self):
        """Every part of the library with a model agrees with its SCAD."""
        disagree = {}
        for item in scan_projects(ROOT):
            if item.kind != "part" or not item.wrapper:
                continue
            found = defaults_disagree(import_module(item.wrapper).DEFAULT)
            if found:
                disagree[item.name] = found
        assert disagree == {}
