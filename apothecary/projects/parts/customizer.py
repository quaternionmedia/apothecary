"""A part's parameters as its own SCAD declares them: OpenSCAD's customizer.

A SCAD file's top-level assignments, up to its first module or function, are
its parameters, annotated the customizer's way: ``width = 34; // [10:100]`` is
a number from 10 to 100 (``[1:0.5:20]`` gives a step too), ``hollow = true;`` a
boolean, ``label = "hi"; // 20`` a string of at most 20 characters,
``shape = "round"; // [round, square]`` and ``n = 2; // [1:one, 2:two]``
choices, ``size = [10, 20];`` a vector, ``/* [Size] */`` the group what follows
is in, and a comment on the line above an assignment its caption.
``/* [Hidden] */`` hides what follows it.

No parser of apothecary's own reads those annotations. OpenSCAD lists them
itself, where it can: a development snapshot exports them
(``-o - --export-format=param``), evaluating the file as it does, so the same
run is the check of a SCAD being edited -- its errors and warnings by line --
and lists what that SCAD declares. OpenSCAD 2021.01 cannot (``Unknown
--export-format option 'param'``): there the check is its echo export, which
evaluates the file and lists nothing, and an answer that needed the list says
the OpenSCAD in use cannot give one.

``GET /parts/{name}/params`` falls back to this listing for a part without a
Python model; ``customizer_values`` checks a staged set against it, as a
model's own validation does for a part with one.

The parameter export leaves a value ``-D`` sets out of what it lists, so the
staged values are evaluated by a second run: the CSG export with them as
``-D`` (``compile_scad``), which says any error only those values reach and
writes the tree OpenSCAD compiled: the same for two texts that differ only in
their comments.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .base import BasePart
from .openscad_messages import OpenSCADMessage, parse_openscad_messages, place_messages
from .params import (
    FROM_CUSTOMIZER,
    FieldError,
    NoParameters,
    ParamField,
    ParamOption,
    ParamsSpec,
)
from .stl_renderer import (
    Cancellation,
    OpenSCADRenderer,
    openscad_version,
    part_renderer,
    run_openscad,
    scad_definitions,
    scad_dependencies,
)
from .variants import renamed, show_path

# A check evaluates a file and renders nothing: a second is long, thirty is stuck.
CHECK_TIMEOUT = 30.0

# How a check was made: the customizer's export, which also lists the
# parameters, or the echo export, which only evaluates.
BY_PARAM = "param"
BY_ECHO = "echo"

INSTALL_HINT = (
    "--export-format=param is in OpenSCAD's development snapshots; "
    "`apothecary openscad install` fetches one"
)


class Unlisted(NoParameters):
    """A part without a model whose SCAD's parameters could not be listed: this
    OpenSCAD cannot list them, OpenSCAD could not read the SCAD, or it
    declares none the customizer lists. ``openscad`` names the OpenSCAD asked,
    ``lists`` whether it can list at all, ``messages`` what it said."""

    def __init__(
        self,
        message: str,
        openscad: Optional[str] = None,
        lists: bool = False,
        messages: Optional[List[OpenSCADMessage]] = None,
    ) -> None:
        super().__init__(message)
        self.openscad = openscad
        self.lists = lists
        self.messages = list(messages or [])


# --- whether an OpenSCAD lists parameters -------------------------------------------

_LISTS: Dict[str, bool] = {}
_LISTS_GUARD = threading.Lock()


def lists_parameters(executable: Optional[Path]) -> bool:
    """Whether ``executable`` exports a SCAD's customizer parameters: its help
    names ``param`` among the formats ``-o`` writes. Asked once per executable.
    A development snapshot does; 2021.01 does not."""
    if executable is None:
        return False
    key = str(executable)
    with _LISTS_GUARD:
        known = _LISTS.get(key)
    if known is not None:
        return known
    try:
        done = subprocess.run(
            [key, "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        found = bool(re.search(r"\bparam\b", f"{done.stdout}\n{done.stderr}"))
    except (OSError, subprocess.SubprocessError):
        found = False
    with _LISTS_GUARD:
        _LISTS[key] = found
    return found


# --- a check: evaluated, not rendered -----------------------------------------------


@dataclass
class Check:
    """What OpenSCAD said of a SCAD it evaluated without rendering it, and the
    parameters it lists (None where this OpenSCAD lists none, or could not
    read the file)."""

    ok: bool
    how: str
    openscad: Optional[str] = None
    messages: List[OpenSCADMessage] = field(default_factory=list)
    parameters: Optional[List[Dict[str, Any]]] = None
    cancelled: bool = False
    timed_out: bool = False
    error_message: Optional[str] = None

    @property
    def lists(self) -> bool:
        return self.how == BY_PARAM


def check_scad(
    scad: Path,
    renderer: OpenSCADRenderer,
    cancel: Optional[Cancellation] = None,
    timeout: float = CHECK_TIMEOUT,
    shown_as: Optional[Path] = None,
) -> Check:
    """Evaluate ``scad`` with ``renderer``'s OpenSCAD, rendering nothing: what it
    said by file and line, and the customizer's parameters where it lists them.
    It runs in the file's own folder, so its includes resolve. A message about
    ``scad`` itself names ``shown_as`` instead, when given: a draft is checked
    from a file of its own, and its lines are the lines of the part it edits."""
    exe = renderer.openscad_path
    version = openscad_version(exe) if exe is not None and Path(exe).exists() else None
    how = BY_PARAM if lists_parameters(exe) else BY_ECHO
    if version is None:
        return Check(ok=False, how=how, error_message="OpenSCAD not found")
    code, out, err, stopped = run_openscad(
        exe, ["-o", "-", f"--export-format={how}", str(scad)], scad.parent, timeout, cancel
    )
    # The param export writes its messages to stderr and its list to stdout;
    # the echo export writes messages and echoes alike to stdout.
    said = err if how == BY_PARAM else f"{err}\n{out}"
    messages = place_messages(parse_openscad_messages(said), scad.parent, show_path, own=scad)
    if shown_as is not None:
        messages = renamed(messages, scad, shown_as)
    check = Check(ok=code == 0, how=how, openscad=version, messages=messages)
    if stopped == "cancelled":
        check.cancelled, check.error_message = True, "Check superseded by a newer request"
        return check
    if stopped == "timeout":
        check.timed_out = True
        check.error_message = f"Check timed out after {timeout} seconds"
        return check
    if code != 0:
        check.error_message = f"OpenSCAD could not read it (exit code {code})"
        return check
    if how == BY_PARAM:
        # A SCAD that declares none is listed as {"title": ...}, with no list at all.
        try:
            listed = json.loads(out).get("parameters", [])
        except (ValueError, AttributeError):
            listed = None
        if not isinstance(listed, list):
            check.ok, check.error_message = False, "OpenSCAD's list of parameters was not one"
            return check
        check.parameters = [p for p in listed if isinstance(p, dict) and p.get("name")]
    return check


# Checks of a part's own SCAD, by everything that decides what OpenSCAD says.
_CHECKS: "OrderedDict[str, Check]" = OrderedDict()
_CHECKS_GUARD = threading.Lock()
CHECKS_KEPT = 128


def _check_key(scad: Path, text: str, renderer: OpenSCADRenderer) -> str:
    """The file a check names, its text, what the text reads, and the OpenSCAD."""
    digest = hashlib.sha256()
    digest.update(f"{Path(scad).resolve()}\0".encode("utf-8"))
    digest.update(text.encode("utf-8"))
    for label, path in sorted(scad_dependencies(scad, text=text).items()):
        try:
            seen = hashlib.sha256(path.read_bytes()).hexdigest() if path is not None else "-"
        except OSError:
            seen = "-"
        digest.update(f"\0{label}={seen}".encode("utf-8"))
    exe = renderer.openscad_path
    digest.update(f"\0{exe}\0{openscad_version(exe) if exe else None}".encode("utf-8"))
    return digest.hexdigest()


def remembered_check(
    scad: Path,
    text: str,
    renderer: OpenSCADRenderer,
    run,
) -> Check:
    """The check of ``text`` (the contents of ``scad``, or a draft standing in
    for it), from memory when the same text, the same includes and the same
    OpenSCAD were checked before; else ``run()``, remembered unless it was
    stopped."""
    key = _check_key(scad, text, renderer)
    with _CHECKS_GUARD:
        known = _CHECKS.get(key)
        if known is not None:
            _CHECKS.move_to_end(key)
            return known
    check = run()
    if check.openscad is not None and not (check.cancelled or check.timed_out):
        with _CHECKS_GUARD:
            _CHECKS[key] = check
            while len(_CHECKS) > CHECKS_KEPT:
                _CHECKS.popitem(last=False)
    return check


def part_check(part: BasePart, renderer: Optional[OpenSCADRenderer] = None) -> Check:
    """The check of a part's own SCAD with the OpenSCAD it renders with."""
    renderer = renderer or part_renderer(part)
    scad = part.source_file
    text = scad.read_text(encoding="utf-8", errors="replace")
    return remembered_check(scad, text, renderer, lambda: check_scad(scad, renderer))


# --- compiled: evaluated with the staged values -------------------------------------


@dataclass
class Compiled:
    """A SCAD evaluated with ``-D`` values and exported as CSG: what OpenSCAD
    said of it with those values, and the digest of the tree it compiled
    (None where it compiled nothing to key on: it failed, said an error, or
    wrote no tree)."""

    ok: bool
    openscad: Optional[str] = None
    messages: List[OpenSCADMessage] = field(default_factory=list)
    digest: Optional[str] = None
    cancelled: bool = False
    timed_out: bool = False
    error_message: Optional[str] = None

    @property
    def errors(self) -> List[OpenSCADMessage]:
        return [m for m in self.messages if m.level == "error"]


def compile_scad(
    scad: Path,
    renderer: OpenSCADRenderer,
    definitions: Optional[Mapping[str, Any]] = None,
    cancel: Optional[Cancellation] = None,
    timeout: float = CHECK_TIMEOUT,
    shown_as: Optional[Path] = None,
) -> Compiled:
    """``scad`` evaluated with ``definitions`` as ``-D`` and exported as CSG,
    rendering nothing. Unlike the parameter export, which leaves a ``-D``
    value out of the parameters it lists, this keeps them: an error only some
    values reach is said here. The CSG is the tree OpenSCAD compiled -- every
    include in it, every comment gone -- so its digest is what a render of
    these values would build from (``variants.py`` files renders under it).
    Messages name ``shown_as`` for ``scad``, as ``check_scad``'s do."""
    exe = renderer.openscad_path
    version = openscad_version(exe) if exe is not None and Path(exe).exists() else None
    if version is None:
        return Compiled(ok=False, error_message="OpenSCAD not found")
    try:
        defs = scad_definitions(dict(definitions or {}))
    except (TypeError, ValueError) as exc:
        return Compiled(ok=False, openscad=version, error_message=str(exc))
    code, out, err, stopped = run_openscad(
        exe,
        ["-o", "-", "--export-format=csg", *defs, str(scad)],
        scad.parent,
        timeout,
        cancel,
    )
    messages = place_messages(parse_openscad_messages(err), scad.parent, show_path, own=scad)
    if shown_as is not None:
        messages = renamed(messages, scad, shown_as)
    compiled = Compiled(ok=code == 0, openscad=version, messages=messages)
    if stopped == "cancelled":
        compiled.cancelled, compiled.error_message = True, "Check superseded by a newer request"
        return compiled
    if stopped == "timeout":
        compiled.timed_out = True
        compiled.error_message = f"Check timed out after {timeout} seconds"
        return compiled
    if code != 0:
        compiled.error_message = f"OpenSCAD could not read it (exit code {code})"
        return compiled
    tree = out.strip()
    if tree and not compiled.errors:
        compiled.digest = hashlib.sha256(tree.encode("utf-8")).hexdigest()
    return compiled


_COMPILED: "OrderedDict[str, Compiled]" = OrderedDict()
_COMPILED_GUARD = threading.Lock()


def _compile_key(
    scad: Path, text: str, definitions: Mapping[str, Any], renderer: OpenSCADRenderer
) -> str:
    try:
        defs = "\0".join(scad_definitions(dict(definitions)))
    except (TypeError, ValueError) as exc:
        defs = f"unwritable: {exc}"
    return hashlib.sha256(f"{_check_key(scad, text, renderer)}\0{defs}".encode("utf-8")).hexdigest()


def known_compile(
    scad: Path, text: str, definitions: Mapping[str, Any], renderer: OpenSCADRenderer
) -> Optional[Compiled]:
    """The compile of ``text`` with ``definitions``, when it was made before."""
    key = _compile_key(scad, text, definitions, renderer)
    with _COMPILED_GUARD:
        known = _COMPILED.get(key)
        if known is not None:
            _COMPILED.move_to_end(key)
        return known


def remembered_compile(
    scad: Path,
    text: str,
    definitions: Mapping[str, Any],
    renderer: OpenSCADRenderer,
    run,
) -> Compiled:
    """As ``remembered_check``, for a compile with ``definitions``."""
    key = _compile_key(scad, text, definitions, renderer)
    with _COMPILED_GUARD:
        known = _COMPILED.get(key)
        if known is not None:
            _COMPILED.move_to_end(key)
            return known
    compiled = run()
    if compiled.openscad is not None and not (compiled.cancelled or compiled.timed_out):
        with _COMPILED_GUARD:
            _COMPILED[key] = compiled
            while len(_COMPILED) > CHECKS_KEPT:
                _COMPILED.popitem(last=False)
    return compiled


def part_compile(
    part: BasePart,
    definitions: Optional[Mapping[str, Any]] = None,
    renderer: Optional[OpenSCADRenderer] = None,
    cancel: Optional[Cancellation] = None,
) -> Compiled:
    """A part's own SCAD compiled with ``definitions`` (what ``-D`` gets)."""
    renderer = renderer or part_renderer(part)
    scad = part.source_file
    text = scad.read_text(encoding="utf-8", errors="replace")
    defs = dict(definitions or {})
    return remembered_compile(
        scad, text, defs, renderer, lambda: compile_scad(scad, renderer, defs, cancel)
    )


def merged(*lists: List[OpenSCADMessage]) -> List[OpenSCADMessage]:
    """Messages from several runs over one text, each said once, in order."""
    seen = set()
    out: List[OpenSCADMessage] = []
    for messages in lists:
        for message in messages:
            mark = (message.level, message.message, message.file, message.line)
            if mark not in seen:
                seen.add(mark)
                out.append(message)
    return out


# --- what the customizer lists, as fields -------------------------------------------


def _shown(value: Any) -> str:
    """A choice's value as the page writes it: 2.0 as 2."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _span(initial: float, step: Optional[float]) -> Tuple[float, float]:
    """A slider's range for a number whose SCAD states none, as ``params_spec``
    spans a model's: a quarter of it to two and a half times it (mirrored below
    zero; ten steps either side of zero)."""
    if initial > 0:
        return initial * 0.25, initial * 2.5
    if initial < 0:
        return initial * 2.5, initial * 0.25
    reach = 10 * (step or 1.0)
    return -reach, reach


def scad_fields(parameters: List[Dict[str, Any]]) -> List[ParamField]:
    """The customizer's parameters as the fields a control surface builds from.

    A number gets the range its SCAD states, else one spanned around its value
    for a slider (which the check does not hold it to); choices are an
    ``enum`` with their options (and, for a page that reads words, a pattern
    of them); a boolean is ``boolean``, a string ``text``, a vector
    ``vector``."""
    fields = []
    for entry in parameters:
        initial, kind = entry.get("initial"), entry.get("type")
        common = {
            "name": entry["name"],
            "default": initial,
            "step": entry.get("step"),
            "group": entry.get("group"),
            "description": entry.get("caption"),
        }
        options = [
            ParamOption(value=o.get("value"), label=str(o.get("name", _shown(o.get("value")))))
            for o in entry.get("options") or []
            if isinstance(o, dict)
        ]
        if options:
            words = "|".join(re.escape(_shown(o.value)) for o in options)
            fields.append(
                ParamField(type="enum", options=options, pattern=f"^({words})$", **common)
            )
        elif kind == "boolean":
            fields.append(ParamField(type="boolean", **common))
        elif kind == "string":
            fields.append(ParamField(type="text", **common))
        elif isinstance(initial, list):
            fields.append(
                ParamField(type="vector", min=entry.get("min"), max=entry.get("max"), **common)
            )
        elif kind == "number" and isinstance(initial, (int, float)):
            low, high = entry.get("min"), entry.get("max")
            if low is None or high is None:
                low, high = _span(float(initial), entry.get("step"))
            fields.append(ParamField(type="number", min=low, max=high, **common))
        else:
            fields.append(ParamField(type="text", **common))
    return fields


def customizer_spec(part: BasePart, renderer: Optional[OpenSCADRenderer] = None) -> ParamsSpec:
    """A part's parameters as its own SCAD declares them, for a part with no
    Python model. Raises ``Unlisted`` (a ``NoParameters``) saying why there are
    none: its geometry is Python, this OpenSCAD cannot list them, OpenSCAD
    could not read the SCAD, or the customizer lists nothing in it."""
    if part.geometry({}) is not None:
        raise Unlisted(f"Part '{part.name}' is built by Python and declares no parameters")
    renderer = renderer or part_renderer(part)
    if not renderer.is_available:
        raise Unlisted(
            f"Part '{part.name}' declares no Python model, and OpenSCAD is not installed"
        )
    exe = renderer.openscad_path
    if not lists_parameters(exe):
        version = openscad_version(exe) if exe is not None else None
        raise Unlisted(
            f"Part '{part.name}' declares no Python model, and {version or 'this OpenSCAD'} "
            f"cannot list its SCAD's parameters ({INSTALL_HINT})",
            openscad=version,
        )
    check = part_check(part, renderer)
    if check.parameters is None:
        raise Unlisted(
            f"Part '{part.name}' declares no Python model, and OpenSCAD could not read its SCAD "
            f"to list its parameters: {check.error_message}",
            openscad=check.openscad,
            lists=True,
            messages=check.messages,
        )
    if not check.parameters:
        raise Unlisted(
            f"Part '{part.name}' declares no parameters: no Python model, and nothing in its "
            "SCAD that OpenSCAD's customizer lists",
            openscad=check.openscad,
            lists=True,
            messages=check.messages,
        )
    return ParamsSpec(
        part=part.name,
        description=part.description,
        fields=scad_fields(check.parameters),
        bounds=part.get_bounds(),
        source=FROM_CUSTOMIZER,
        openscad=check.openscad,
    )


# --- a staged set, checked against the listing --------------------------------------


def _number(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("a number, not true or false")
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            raise ValueError(f"{value!r} is not a number") from None
    else:
        raise ValueError("a number")
    if not math.isfinite(number):
        raise ValueError("a finite number")
    return number


def _within(entry: Mapping[str, Any], number: float) -> None:
    low, high = entry.get("min"), entry.get("max")
    if low is not None and number < low:
        raise ValueError(f"at least {_shown(float(low))}")
    if high is not None and number > high:
        raise ValueError(f"at most {_shown(float(high))}")


def _coerce(entry: Mapping[str, Any], value: Any) -> Any:
    """``value`` as the parameter ``entry`` takes it, or ValueError saying what it takes."""
    kind, initial = entry.get("type"), entry.get("initial")
    options = [o.get("value") for o in entry.get("options") or [] if isinstance(o, dict)]
    if kind == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in ("true", "false"):
            return value.strip().lower() == "true"
        raise ValueError("true or false")
    if kind == "string":
        if not isinstance(value, str):
            raise ValueError("a string")
        out: Any = value
    elif kind == "number" and isinstance(initial, list):
        if not isinstance(value, (list, tuple)) or len(value) != len(initial):
            raise ValueError(f"a list of {len(initial)} numbers")
        out = [_number(v) for v in value]
        for number in out:
            _within(entry, number)
        return out
    elif kind == "number":
        out = _number(value)
    else:
        return value  # a kind this module does not know: OpenSCAD has the last word
    if options:
        if out not in options:
            raise ValueError("one of " + ", ".join(_shown(o) for o in options))
        return out
    if kind == "string":
        limit = entry.get("maxLength")
        if limit is not None and len(out) > limit:
            raise ValueError(f"at most {int(limit)} characters")
        return out
    _within(entry, out)
    return out


def customizer_values(
    parameters: List[Dict[str, Any]], params: Optional[Mapping[str, Any]]
) -> Tuple[Dict[str, Any], List[FieldError]]:
    """A staged set checked against what the customizer lists: each value as
    its parameter takes it (a number as a number, a choice one of its
    options, a stated range or length kept to), and an error for each that
    is not, or that names no parameter."""
    entries = {p["name"]: p for p in parameters}
    values: Dict[str, Any] = {}
    errors: List[FieldError] = []
    for name, value in (params or {}).items():
        entry = entries.get(name)
        if entry is None:
            errors.append(FieldError(field=name, message="no such parameter"))
            continue
        try:
            values[name] = _coerce(entry, value)
        except ValueError as exc:
            errors.append(FieldError(field=name, message=str(exc)))
    return values, errors


def without_initial(parameters: List[Dict[str, Any]], params: Mapping[str, Any]) -> Dict[str, Any]:
    """Checked values less those equal to what the SCAD itself assigns: the same
    render, so the same variant, and the saved part when that is all of them."""
    initial = {p["name"]: p.get("initial") for p in parameters}
    missing = object()
    return {name: value for name, value in params.items() if initial.get(name, missing) != value}


__all__ = [
    "BY_ECHO",
    "BY_PARAM",
    "Check",
    "Compiled",
    "Unlisted",
    "check_scad",
    "compile_scad",
    "known_compile",
    "merged",
    "part_compile",
    "remembered_compile",
    "customizer_spec",
    "customizer_values",
    "lists_parameters",
    "part_check",
    "remembered_check",
    "scad_fields",
    "without_initial",
]
