"""One parameter contract, in core: what a part's two routes answer is what
``params_spec`` and ``validate_staged`` compute, typed, and unchanged in shape."""

from __future__ import annotations

from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.projects.parts.datum_core import DEFAULT as CORE
from apothecary.projects.parts.params import (
    FieldError,
    NoParameters,
    ParamField,
    ParamsSpec,
    Validation,
    params_spec,
    validate_staged,
)

client = TestClient(app)

FIELD_KEYS = ["name", "type", "default", "min", "max", "pattern", "description", "contested"]


def _route(path: str):
    return next(r for r in app.routes if getattr(r, "path", None) == path)


class TestTheRoutesAreTheContract:
    def test_params_is_the_spec_of_the_part(self):
        body = client.get("/parts/datum_core/params").json()
        assert list(body) == ["part", "description", "fields", "bounds"]
        assert [list(f) for f in body["fields"]] == [FIELD_KEYS] * len(body["fields"])
        assert body == params_spec(CORE).model_dump(mode="json")
        assert _route("/parts/{name}/params").response_model is ParamsSpec

    def test_validate_is_the_staged_check_of_the_part(self):
        for params in ({"walls": 2.4}, {"walls": -1, "nope": 1}, {}):
            body = client.post("/parts/datum_core/validate", json={"params": params}).json()
            assert list(body) == ["valid", "params", "errors", "bounds"]
            assert body == validate_staged(CORE, params).model_dump(mode="json")
        assert _route("/parts/{name}/validate").response_model is Validation

    def test_every_candidate_keeps_its_provenance(self):
        board_y = next(f for f in params_spec(CORE).fields if f.name == "board_y")
        assert [list(c.model_dump()) for c in board_y.contested] == [
            ["value", "source", "note"]
        ] * len(board_y.contested)
        # Listed as the part declares them, the one it ships included: what a
        # reader turns is the whole disagreement, not the part of it not chosen.
        assert {c.value for c in board_y.contested} >= {board_y.default}

    def test_a_part_without_a_model_declares_no_parameters(self):
        from apothecary.projects.parts.base import BasePart

        bare = BasePart(name="bare", source_file=CORE.source_file)
        try:
            params_spec(bare)
        except NoParameters as none:
            assert "declares no parameters" in str(none)
        else:  # pragma: no cover - the assertion is the except branch
            raise AssertionError("a part without a model has no spec")
        assert validate_staged(bare, {}) == Validation(valid=True)


class TestTheModels:
    def test_a_field_is_typed_and_a_validation_names_its_errors(self):
        field = ParamField(name="walls", type="number", default=2.0, min=0.5, max=5.0)
        assert field.contested == [] and field.pattern is None
        refused = Validation(valid=False, errors=[FieldError(field="walls", message="too thin")])
        assert refused.params == {} and refused.bounds is None
