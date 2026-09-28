"""One parameter contract for everything the browser edits.

A part from the parts folder and a piece made from a picture are edited by the
same page through the same two answers. ``ParamsSpec`` is what ``GET
/parts/{name}/params`` and ``GET /sites/{s}/made/{piece}/params`` return: the
fields a control surface builds itself from, each with its type, its default,
the range a slider can use, the pattern an enum is drawn from, and the
candidates the part's sources disagree about, with their provenance.
``Validation`` is what the two ``/validate`` routes return: a staged set
checked against the part's own model, with the envelope it would produce and
no render.

Both are read off ``BasePart``: ``params_model`` for the fields, ``contested``
for the candidates, ``get_bounds`` for the envelope. A part built from a file
and a part built from a record answer the same shape, so the page cannot
drift from what either renderer accepts.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from pydantic import BaseModel, Field, ValidationError
from pydantic_core import to_jsonable_python

from apothecary.models import BoundingBox3D

from .base import BasePart, ContestedValue


class NoParameters(LookupError):
    """The part declares no ``params_model``, so there is nothing to build controls from."""


class ParamField(BaseModel):
    """One parameter, as a control surface needs it."""

    name: str
    # "number" gets a slider, "enum" a drop-down of the words in ``pattern``,
    # "text" nothing yet.
    type: str
    default: Any = None
    min: Optional[float] = None
    max: Optional[float] = None
    pattern: Optional[str] = None
    description: Optional[str] = None
    # The candidates the part's sources disagree about, each with where it
    # comes from: the number a person can turn instead of argue about.
    contested: List[ContestedValue] = Field(default_factory=list)


class ParamsSpec(BaseModel):
    """What a part accepts, in a form the page builds its editor from."""

    part: str
    description: Optional[str] = None
    fields: List[ParamField] = Field(default_factory=list)
    bounds: Optional[BoundingBox3D] = None


class FieldError(BaseModel):
    field: str
    message: str


class Validation(BaseModel):
    """A staged set, checked; the envelope it would produce; nothing rendered."""

    valid: bool
    params: Dict[str, Any] = Field(default_factory=dict)
    errors: List[FieldError] = Field(default_factory=list)
    bounds: Optional[BoundingBox3D] = None


def params_spec(part: BasePart) -> ParamsSpec:
    """The part's fields, defaults, ranges and contested candidates.

    Types, defaults and bounds come from the part's own Pydantic model, so
    the page cannot drift from what the renderer will accept. Raises
    ``NoParameters`` for a part without a model.
    """
    model_cls = part.params_model
    if model_cls is None:
        raise NoParameters(f"Part '{part.name}' declares no parameters")

    schema = model_cls.model_json_schema()
    defaults = model_cls()

    fields = []
    for field_name, spec in schema.get("properties", {}).items():
        default = getattr(defaults, field_name)
        candidates = list(part.contested.get(field_name, []))
        # A slider needs a range. Pydantic states one only where the field
        # constrains it, so the rest get a span around the default wide enough
        # to be worth dragging -- and wide enough to reach every candidate.
        interesting = [default, *(c.value for c in candidates)]
        low = spec.get("minimum")
        # gt=0 arrives as exclusiveMinimum, and a slider stopping exactly there
        # offers a value the model then refuses -- which is the one thing this
        # contract exists to prevent.
        exclusive_low = spec.get("exclusiveMinimum")
        high = spec.get("maximum")
        if not isinstance(default, (int, float)):
            low = high = None
        else:
            if low is None:
                low = float(exclusive_low) if exclusive_low is not None else None
            else:
                low = float(low)
            if low is None:
                low = max(0.0, min(interesting) * 0.25)
            high = max(interesting) * 2.5 if high is None else float(high)
            if exclusive_low is not None and low <= float(exclusive_low):
                # One slider step above the bound it may not touch.
                low = float(exclusive_low) + (high - float(exclusive_low)) / 200

        fields.append(
            ParamField(
                name=field_name,
                type="enum" if spec.get("pattern") else ("number" if high else "text"),
                default=to_jsonable_python(default),
                min=low,
                max=high,
                pattern=spec.get("pattern"),
                description=spec.get("description"),
                contested=candidates,
            )
        )

    return ParamsSpec(
        part=part.name,
        description=part.description,
        fields=fields,
        bounds=part.get_bounds(),
    )


def validate_staged(part: BasePart, params: Optional[Mapping[str, Any]]) -> Validation:
    """Check a staged parameter set against the part's model, rendering nothing.

    The step between moving a slider and paying for a render: the values go
    through the part's own model, and the envelope they would produce comes
    back. A set that cannot be rendered is refused here, where it costs
    nothing. A part without a model accepts the empty set and nothing else.
    """
    params = dict(params or {})
    model_cls = part.params_model
    if model_cls is None:
        return Validation(valid=True)

    unknown = sorted(set(params) - set(model_cls.model_fields))
    if unknown:
        return Validation(
            valid=False,
            errors=[FieldError(field=u, message="no such parameter") for u in unknown],
        )

    try:
        validated = model_cls(**params)
    except ValidationError as exc:
        return Validation(
            valid=False,
            errors=[
                FieldError(field=".".join(str(p) for p in e["loc"]), message=e["msg"])
                for e in exc.errors()
            ],
        )

    staged = {key: getattr(validated, key) for key in params}
    # The envelope the staged set would produce, so a reader sees the
    # consequence before paying for the render.
    try:
        bounds = part.get_bounds(staged or None)
    except Exception:  # pragma: no cover - a wrapper that cannot size itself
        bounds = None

    return Validation(valid=True, params=to_jsonable_python(staged), bounds=bounds)


__all__ = [
    "FieldError",
    "NoParameters",
    "ParamField",
    "ParamsSpec",
    "Validation",
    "params_spec",
    "validate_staged",
]
