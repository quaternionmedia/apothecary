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

import math
import re
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, get_args

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
    # The unit its value is in, where its source declares one: a model's field
    # by ``json_schema_extra={"unit": "mm"}``, a customizer parameter by its
    # comment (``customizer.unit_of``). None where none is declared.
    unit: Optional[str] = None
    # A whole number: its value, its range and its step are integers.
    integer: bool = False
    # A "group": a nested model's own fields, each a field as these are.
    fields: List["ParamField"] = Field(default_factory=list)


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
    can_build: bool = Field(
        True, description="An OpenSCAD here can build the part (gridfinity's cannot on 2021.01)"
    )
    build_note: Optional[str] = Field(None, description="Why it cannot be built here")


class FieldError(BaseModel):
    field: str
    message: str


class Validation(BaseModel):
    """A staged set, checked; the envelope it would produce; nothing rendered."""

    valid: bool
    params: Dict[str, Any] = Field(default_factory=dict)
    errors: List[FieldError] = Field(default_factory=list)
    bounds: Optional[BoundingBox3D] = None


def _resolved(spec: Dict[str, Any], defs: Dict[str, Any]) -> Dict[str, Any]:
    """A property's schema with its ``$ref`` followed and an ``Optional``'s null
    taken out: what the field is, with what the property itself says over it."""
    ref = spec.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        target = dict(defs.get(ref[len("#/$defs/") :], {}))
        spec = {**target, **{k: v for k, v in spec.items() if k != "$ref"}}
    options = spec.get("anyOf")
    if isinstance(options, list):
        real = [o for o in options if o.get("type") != "null"]
        if len(real) == 1:
            inner = _resolved(real[0], defs)
            spec = {**inner, **{k: v for k, v in spec.items() if k != "anyOf"}}
    return spec


def _enum_class(annotation: Any) -> Optional[type]:
    """The Enum a field's annotation names, through an ``Optional``."""
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation
    for arg in get_args(annotation):
        found = _enum_class(arg)
        if found is not None:
            return found
    return None


def _model_class(annotation: Any) -> Optional[type]:
    """The model a nested field's annotation names, through an ``Optional``."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    for arg in get_args(annotation):
        found = _model_class(arg)
        if found is not None:
            return found
    return None


def _label(name: str) -> str:
    """An Enum member's name as words: ``UNITS_EXCLUDE_LIP`` is "units exclude lip"."""
    return name.replace("_", " ").lower()


def _shown(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _number_range(
    spec: Dict[str, Any], interesting: List[float], integer: bool, step: Optional[float]
) -> tuple:
    """(min, max) for a slider: what the model states, else a span around the
    default (and every contested candidate), a quarter of it to two and a
    half times it, mirrored below zero. A whole number's are whole."""
    low = spec.get("minimum")
    # gt=0 arrives as exclusiveMinimum, and a slider stopping exactly there
    # offers a value the model then refuses -- which is the one thing this
    # contract exists to prevent.
    exclusive_low = spec.get("exclusiveMinimum")
    high = spec.get("maximum")
    exclusive_high = spec.get("exclusiveMaximum")
    if low is None and exclusive_low is not None:
        low = float(exclusive_low)
    if high is None and exclusive_high is not None:
        high = float(exclusive_high)
    if low is None:
        smallest = min(interesting)
        low = max(0.0, smallest * 0.25) if smallest >= 0 else smallest * 2.5
    if high is None:
        largest = max(interesting)
        high = largest * 2.5 if largest > 0 else largest * 0.25
    low, high = float(low), float(high)
    if high <= low:
        high = low + 10 * (step or 1.0)
    if integer:
        low, high = float(math.ceil(low)), float(math.floor(high))
        if exclusive_low is not None and low <= float(exclusive_low):
            low = float(math.floor(float(exclusive_low)) + 1)
        if exclusive_high is not None and high >= float(exclusive_high):
            high = float(math.ceil(float(exclusive_high)) - 1)
        return low, high
    if exclusive_low is not None and low <= float(exclusive_low):
        # One slider step above the bound it may not touch.
        low = float(exclusive_low) + (high - float(exclusive_low)) / 200
    if exclusive_high is not None and high >= float(exclusive_high):
        high = float(exclusive_high) - (float(exclusive_high) - low) / 200
    return low, high


def _field(
    name: str,
    spec: Dict[str, Any],
    default: Any,
    annotation: Any,
    defs: Dict[str, Any],
    candidates: List[ContestedValue],
) -> ParamField:
    """One property of a model's schema as the field a control surface builds."""
    spec = _resolved(spec, defs)
    common = {
        "name": name,
        "description": spec.get("description"),
        "unit": spec.get("unit") if isinstance(spec.get("unit"), str) else None,
        "contested": candidates,
    }
    nested = _model_class(annotation)
    if nested is not None or isinstance(spec.get("properties"), dict):
        inner = nested.model_fields if nested is not None else {}
        fields = [
            _field(
                sub,
                sub_spec,
                getattr(default, sub, None) if default is not None else sub_spec.get("default"),
                inner[sub].annotation if sub in inner else None,
                defs,
                [],
            )
            for sub, sub_spec in (spec.get("properties") or {}).items()
        ]
        return ParamField(
            type="group", default=to_jsonable_python(default), fields=fields, **common
        )
    values = spec.get("enum")
    if values is None and "const" in spec:
        values = [spec["const"]]
    if isinstance(values, list) and values:
        members = _enum_class(annotation)
        names = {m.value: m.name for m in members} if members is not None else {}
        options = [
            ParamOption(value=v, label=_label(names[v]) if v in names else _shown(v))
            for v in values
        ]
        words = "|".join(re.escape(_shown(v)) for v in values)
        return ParamField(
            type="enum",
            default=to_jsonable_python(default),
            options=options,
            pattern=f"^({words})$",
            **common,
        )
    if spec.get("pattern"):
        return ParamField(
            type="enum", default=to_jsonable_python(default), pattern=spec["pattern"], **common
        )
    kind = spec.get("type")
    if kind == "boolean" or isinstance(default, bool):
        # A tick is not a number, though Python counts True as one.
        return ParamField(type="boolean", default=default, **common)
    if kind in ("number", "integer") or (kind is None and isinstance(default, (int, float))):
        integer = kind == "integer"
        step = spec.get("multipleOf")
        step = float(step) if isinstance(step, (int, float)) else (1.0 if integer else None)
        interesting = [float(v) for v in [default, *(c.value for c in candidates)] if v is not None]
        low, high = _number_range(spec, interesting or [0.0], integer, step)
        return ParamField(
            type="number",
            default=to_jsonable_python(default),
            min=low,
            max=high,
            step=step,
            integer=integer,
            **common,
        )
    numbers = isinstance(default, (list, tuple)) and all(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in default
    )
    if kind == "array" and numbers:
        items = spec.get("items") or {}
        return ParamField(
            type="vector",
            default=to_jsonable_python(default),
            min=items.get("minimum"),
            max=items.get("maximum"),
            integer=items.get("type") == "integer",
            **common,
        )
    return ParamField(type="text", default=to_jsonable_python(default), **common)


def params_spec(part: BasePart) -> ParamsSpec:
    """The part's fields, defaults, ranges and contested candidates.

    Types, defaults and bounds come from the part's own Pydantic model, so
    the page cannot drift from what the renderer will accept. Raises
    ``NoParameters`` for a part without a model.

    A number has a slider's range (the model's bounds, else a span around its
    default) and, where it is an ``int``, ``integer`` and a step of 1, its
    range in whole numbers; a ``multiple_of`` is its step. An Enum, a
    ``Literal`` or an ``enum`` in the schema is an "enum" with its options
    (an Enum member's label is its name in words). A nested model is a
    "group" of its own fields. A field's ``json_schema_extra={"unit": ...}``
    is its ``unit``; none is given where none is declared.
    """
    model_cls = part.params_model
    if model_cls is None:
        raise NoParameters(f"Part '{part.name}' declares no parameters")

    schema = model_cls.model_json_schema()
    defs = schema.get("$defs", {})
    defaults = model_cls()
    annotations = model_cls.model_fields

    fields = [
        _field(
            field_name,
            spec,
            getattr(defaults, field_name),
            annotations[field_name].annotation if field_name in annotations else None,
            defs,
            list(part.contested.get(field_name, [])),
        )
        for field_name, spec in schema.get("properties", {}).items()
    ]

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
