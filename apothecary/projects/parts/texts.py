"""A part's text, which is the truth: its values are the assignments in it.

Decided with the owner on 2026-10-12 (docs/plans/part-iteration-2026-10-12.md,
"parameters and text, tied together"): for a part whose SCAD the page edits,
nothing is passed to OpenSCAD on the side. A check, a render and a save each
take a text, and the values are what that text assigns (the grammar of an
assignment is apothecary/projects/parts/assignments.py's). A caller that still
sends parameters has them written into the text first (``with_params``), so
there is one path.

- **The text a part is edited as** (``own_text``): its SCAD file as saved --
  which is also its defaults -- or, for a part whose SCAD is in a submodule
  (gridfinity's), its **overlay**: a SCAD beside the submodule that includes
  the upstream file and sets values after it. ``edit_file`` is where a draft
  of that text is written to be checked or rendered, so its includes resolve
  as they will from where it is saved. An overlay's text that is not one --
  no ``include`` of the upstream file -- is an edit of the upstream file,
  which is refused (``saved.UpstreamEdit``): it is upstream's.
- **The values checked** (``check_values``): a part's Python model still
  checks the values its text assigns -- a range, a type, a whole number --
  each reported with the field it is and why it is refused; a part without
  one has them checked against what its SCAD's customizer lists. A computed
  assignment is checked by the value OpenSCAD gives it, where that is known.
- **Where a model's default and its SCAD disagree** (``defaults_disagree``):
  the SCAD is the default now, and ``apothecary problems`` and a part's
  checklist say where the model says otherwise.
"""

from __future__ import annotations

import posixpath
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError
from pydantic_core import to_jsonable_python

from .assignments import Assignment, last_of, parse_assignments, write_values
from .base import BasePart
from .params import FieldError

OVERLAY_SUFFIX = ".overlay.scad"
_INCLUDES = re.compile(r"\binclude\s*<\s*([^>]+?)\s*>")
_COMMENTS = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)


# --- the overlay of a part in a submodule ----------------------------------------------


@lru_cache(maxsize=256)
def _overlay_of(source: str) -> Optional[Tuple[Path, str]]:
    """(the overlay's path, the upstream SCAD from the checkout's top) for a SCAD
    in a submodule; None for one that is not (or not in git). Asked of git once
    per file: whether a folder is a submodule does not change while serving."""
    from .saved import GitError, _where

    part = BasePart(name=Path(source).stem, source_file=Path(source))
    try:
        where = _where(part)
    except GitError:
        return None
    if not where.overlay:
        return None
    return where.checkout / where.scad, str(where.upstream)


def upstream_path(part: BasePart) -> Optional[str]:
    """A part in a submodule: its upstream SCAD, from the top of the checkout
    that holds the submodule; None for any other part."""
    found = _overlay_of(str(Path(part.source_file).resolve()))
    return found[1] if found else None


def overlay_path(part: BasePart) -> Optional[Path]:
    """Where a part in a submodule is edited and saved as its overlay; None for
    any other part."""
    found = _overlay_of(str(Path(part.source_file).resolve()))
    return found[0] if found else None


def is_overlaid(part: BasePart) -> bool:
    return overlay_path(part) is not None


def edit_file(part: BasePart) -> Path:
    """The file a draft of the part's text stands in for: its SCAD, or its overlay."""
    return overlay_path(part) or part.source_file


def overlay_header(part: BasePart) -> str:
    """An overlay's first lines: what it is, and the include of the upstream file."""
    found = _overlay_of(str(Path(part.source_file).resolve()))
    assert found is not None, f"{part.name} is in no submodule"
    path, upstream = found
    include = posixpath.relpath(
        Path(part.source_file).resolve().as_posix(), path.parent.resolve().as_posix()
    )
    return (
        f"// {part.name}: {Path(upstream).name}, in its submodule, with the values set below.\n"
        f"// The submodule is not changed: {upstream}\n"
        f"include <{include}>\n"
    )


def own_text(part: BasePart) -> str:
    """The text the part is edited as when nothing is changed: its SCAD as saved
    (its defaults), or, for a part in a submodule, its overlay setting nothing."""
    if is_overlaid(part):
        return overlay_header(part)
    return part.source_file.read_text(encoding="utf-8")


def is_overlay_text(part: BasePart, text: str) -> bool:
    """Whether ``text`` includes the part's upstream SCAD from where its overlay is."""
    path = overlay_path(part)
    if path is None:
        return False
    upstream = Path(part.source_file).resolve()
    for found in _INCLUDES.finditer(_COMMENTS.sub("", text)):
        if (path.parent / found.group(1)).resolve() == upstream:
            return True
    return False


def as_edited(part: BasePart, text: Optional[str]) -> str:
    """The text a request means: ``text``, or the part's own when there is none.
    For a part in a submodule its upstream SCAD as it stands means its overlay
    setting nothing (a caller from before overlays); any other text that is no
    overlay is an edit of the upstream file, refused (``saved.UpstreamEdit``)."""
    if text is None:
        return own_text(part)
    if not is_overlaid(part):
        return text
    if is_overlay_text(part, text):
        return text
    try:
        upstream = part.source_file.read_text(encoding="utf-8")
    except OSError:
        upstream = None
    if text == upstream:
        return own_text(part)
    from .saved import UpstreamEdit

    raise UpstreamEdit(
        f"{part.name}'s SCAD is in a submodule, {_overlay_of(str(Path(part.source_file).resolve()))[1]}: "
        "it is upstream's, and nothing here changes it. It is edited as its overlay -- "
        "the include of that file and the values set after it -- and an edit of the file "
        "itself is to be made upstream."
    )


def with_params(part: BasePart, text: str, params: Optional[Mapping[str, Any]]) -> str:
    """``text`` with ``params`` -- checked, by the part's model's names -- written
    into it under the names its SCAD uses (``scad_overrides``): what a caller
    that sends values on the side means."""
    if not params:
        return text
    return write_values(text, part.scad_overrides(dict(params)))


def upstream_assignments(part: BasePart) -> List[Assignment]:
    """An overlaid part's upstream SCAD's assignments, read only."""
    return parse_assignments(part.source_file.read_text(encoding="utf-8"))


def assignments_of(part: BasePart, text: str) -> List[Assignment]:
    """The assignments a page builds controls from: ``text``'s. For an overlay,
    its own (``set``) and then each parameter of the upstream SCAD it does not
    set, with the upstream's value, no position (``set`` false: setting it
    appends its line)."""
    own = parse_assignments(text)
    if not is_overlaid(part):
        return own
    named = {a.name for a in own}
    rest = []
    for a in upstream_assignments(part):
        if a.parameter and a.name not in named:
            named.add(a.name)
            rest.append(
                a.model_copy(update={"set": False, "line": None, "from_": None, "to": None})
            )
    return own + rest


def known_values(
    part: BasePart, text: str, evaluated: Optional[Mapping[str, Any]] = None
) -> Dict[str, Any]:
    """Each top-level name's value as ``text`` gives it (an overlay's over its
    upstream's): a literal's, or a computed one's where ``evaluated`` has it."""
    values: Dict[str, Any] = {}
    sources = [parse_assignments(text)]
    if is_overlaid(part):
        sources.insert(0, upstream_assignments(part))
    for assignments in sources:
        for name, a in last_of(assignments).items():
            if not a.computed:
                values[name] = a.value
            elif evaluated is not None and name in evaluated:
                values[name] = evaluated[name]
            else:
                values.pop(name, None)
    return values


# --- the values checked ----------------------------------------------------------------


class ValueCheck(BaseModel):
    """One value the text gives, as the part's model or listing checks it."""

    name: str = Field(description="The name assigned in the text")
    field: str = Field(
        description="What checks it: the model's field (a.b nested), or the listed parameter"
    )
    value: Any = None
    computed: bool = False
    valid: Optional[bool] = Field(description="None: a computed value not evaluated yet")
    message: Optional[str] = Field(None, description="Why it is refused")


class ValuesChecked(BaseModel):
    values: List[ValueCheck] = Field(default_factory=list)
    errors: List[FieldError] = Field(default_factory=list)
    # The model's values, validated, for what sizes a part (get_bounds): by field.
    model_params: Dict[str, Any] = Field(default_factory=dict)

    @property
    def valid(self) -> bool:
        return all(v.valid is not False for v in self.values)


def _nested_model(annotation: Any):
    from typing import get_args

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    for arg in get_args(annotation):
        found = _nested_model(arg)
        if found is not None:
            return found
    return None


def check_values(
    part: BasePart,
    text: str,
    evaluated: Optional[Mapping[str, Any]] = None,
    listing: Optional[List[Dict[str, Any]]] = None,
) -> ValuesChecked:
    """Each value ``text`` gives, checked: by the part's model where it has one
    (each field it names, a nested model's fields under it), else against what
    its SCAD's customizer lists (``listing``). A computed value is checked by
    what ``evaluated`` says it is, else reported unchecked (``valid`` None)."""
    assigned = {}
    for a in [*(upstream_assignments(part) if is_overlaid(part) else []), *parse_assignments(text)]:
        assigned[a.name] = a
    values = known_values(part, text, evaluated)
    out = ValuesChecked()
    model = part.params_model
    if model is not None:
        kwargs: Dict[str, Any] = {}
        rows: Dict[str, ValueCheck] = {}
        for field_name, info in model.model_fields.items():
            nested = _nested_model(info.annotation)
            names = list(nested.model_fields) if nested is not None else [field_name]
            for scad_name in names:
                if scad_name not in assigned:
                    continue
                key = f"{field_name}.{scad_name}" if nested is not None else field_name
                a = assigned[scad_name]
                known = scad_name in values
                rows[key] = ValueCheck(
                    name=scad_name,
                    field=key,
                    value=to_jsonable_python(values.get(scad_name)),
                    computed=a.computed,
                    valid=True if known else None,
                )
                if not known:
                    continue
                if nested is not None:
                    kwargs.setdefault(field_name, {})[scad_name] = values[scad_name]
                else:
                    kwargs[field_name] = values[scad_name]
        try:
            checked = model(**kwargs)
            out.model_params = {f: getattr(checked, f) for f in kwargs}
        except ValidationError as exc:
            for error in exc.errors():
                loc = [str(p) for p in error["loc"]]
                key = (
                    ".".join(loc[:2])
                    if loc and loc[0] in kwargs and isinstance(kwargs[loc[0]], dict)
                    else (loc[0] if loc else "")
                )
                row = rows.get(key) or rows.get(loc[0] if loc else "")
                if row is not None:
                    row.valid, row.message = False, error["msg"]
                out.errors.append(FieldError(field=key, message=error["msg"]))
        out.values = list(rows.values())
        return out
    if listing is None:
        return out
    from .customizer import customizer_values

    for entry in listing:
        name = entry.get("name")
        if name not in assigned:
            continue
        known = name in values
        row = ValueCheck(
            name=name,
            field=name,
            value=to_jsonable_python(values.get(name)),
            computed=assigned[name].computed,
            valid=True if known else None,
        )
        if known:
            _, errors = customizer_values([entry], {name: values[name]})
            if errors:
                row.valid, row.message = False, errors[0].message
                out.errors.append(errors[0])
        out.values.append(row)
    return out


# --- where a model's default and its SCAD disagree ---------------------------------------


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b or a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= 1e-9 * max(1.0, abs(float(a)), abs(float(b)))
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b, strict=True))
    return a == b


def defaults_disagree(part: BasePart) -> Optional[List[str]]:
    """Where the part's model's defaults and its SCAD's literals disagree, each
    as "name: model X, SCAD Y"; [] where they agree; None where there is
    nothing to compare (no model, or a SCAD its geometry generates)."""
    from enum import Enum

    if part.params_model is None or part.geometry({}) is not None:
        return None
    try:
        text = part.source_file.read_text(encoding="utf-8")
    except OSError:
        return None
    defaults = part.params_model()
    said = part.scad_overrides({f: getattr(defaults, f) for f in part.params_model.model_fields})
    at = last_of(parse_assignments(text))
    found = []
    for name, value in said.items():
        a = at.get(name)
        if a is None or a.computed:
            continue
        value = value.value if isinstance(value, Enum) else value
        if not _same(value, a.value):
            found.append(f"{name}: model {value!r}, SCAD {a.value!r}")
    return found


__all__ = [
    "OVERLAY_SUFFIX",
    "ValueCheck",
    "ValuesChecked",
    "as_edited",
    "assignments_of",
    "check_values",
    "defaults_disagree",
    "edit_file",
    "is_overlaid",
    "is_overlay_text",
    "known_values",
    "overlay_header",
    "overlay_path",
    "own_text",
    "upstream_assignments",
    "with_params",
]
