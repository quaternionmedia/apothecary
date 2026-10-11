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


class ParamOption(BaseModel):
    """One choice of an ``enum``: the value it sets, and what it is called."""

    value: Any
    label: str


class ParamField(BaseModel):
    """One parameter, as a control surface needs it."""

    name: str
    # "number" gets a slider over min..max, "enum" a choice of ``options`` (or
    # of the words in ``pattern``), "boolean" a tick, "text" a string,
    # "vector" a list of numbers as long as its default.
    type: str
    default: Any = None
    min: Optional[float] = None
    max: Optional[float] = None
    # The increment the source states (a customizer's ``[1:0.5:20]``); None
    # where it states none.
    step: Optional[float] = None
    pattern: Optional[str] = None
    options: List[ParamOption] = Field(default_factory=list)
    # The customizer tab a SCAD puts it under (``/* [Size] */``); None for a model's.
    group: Optional[str] = None
    description: Optional[str] = None
    # The candidates the part's sources disagree about, each with where it
    # comes from: the number a person can turn instead of argue about.
    contested: List[ContestedValue] = Field(default_factory=list)


# Where a spec's fields come from: the part's Python model, or its SCAD's own
# parameters as OpenSCAD's customizer lists them (a part without a model).
FROM_MODEL = "model"
FROM_CUSTOMIZER = "customizer"


class ParamsSpec(BaseModel):
    """What a part accepts, in a form the page builds its editor from."""

    part: str
    description: Optional[str] = None
    fields: List[ParamField] = Field(default_factory=list)
    bounds: Optional[BoundingBox3D] = None
    source: str = Field(
        FROM_MODEL,
        description='"model": the part\'s Python model; "customizer": its SCAD\'s own '
        "parameters, as OpenSCAD lists them",
    )
    openscad: Optional[str] = Field(
        None, description="The OpenSCAD that listed them, for the customizer's"
    )


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
        if isinstance(default, bool) or not isinstance(default, (int, float)):
            # A tick is not a number, though Python counts True as one.
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

        if spec.get("pattern"):
            kind = "enum"
        elif isinstance(default, bool):
            kind = "boolean"
        else:
            kind = "number" if high else "text"
        fields.append(
            ParamField(
                name=field_name,
                type=kind,
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
    "FROM_CUSTOMIZER",
    "FROM_MODEL",
    "FieldError",
    "NoParameters",
    "ParamField",
    "ParamOption",
    "ParamsSpec",
    "Validation",
    "params_spec",
    "validate_staged",
]
