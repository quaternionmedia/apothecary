"""A SCAD text's top-level assignments, where they are, and how to write one.

The text is the truth: a part's values are the assignments in its SCAD, a
control moves one by rewriting its value in place, and a value typed in the
text moves its control. The page rewrites lines itself, so it and this module
must agree on what a top-level assignment is. This is the grammar both follow.

**Reading the text.** It is read as OpenSCAD reads it: a ``//`` comment runs
to the end of its line; a ``/* */`` comment to its ``*/``; a string from ``"``
to the next ``"`` not escaped by ``\\``. Inside a comment or a string nothing
counts. Outside them, ``(``, ``[`` and ``{`` open and ``)``, ``]`` and ``}``
close; the **depth** is how many are open.

**Statements.** At depth 0 a statement starts at the beginning of the text,
after a ``;`` at depth 0, after a ``}`` that brings the depth back to 0, and
after an ``include <...>`` or ``use <...>`` (which end at their ``>``),
whitespace and comments skipped.

**A top-level assignment** is a statement that is a name, then ``=`` (not
``==``), then its value, then ``;`` at depth 0:

    name  ::= "$"? [A-Za-z_] [A-Za-z0-9_]*
    value ::= the text from the first character after "=" that is not
              whitespace up to the last such character before the ";"

``from`` and ``to`` are the value's span: its first character, and one past
its last. Two assignments may share a line (``a = 1; b = 2;``); each has its
own span. A statement that starts with ``module`` or ``function`` defines one,
and every assignment after the first such definition is not a parameter, as
OpenSCAD's customizer has it; neither is one after ``/* [Hidden] */``. A
block comment that is a word in brackets, ``/* [Size] */``, starts that group.

**What else is read.** The **trailing comment** is a ``//`` comment on the
assignment's line after its ``;``, with only whitespace between; its text is
trimmed. Where that text is all one bracket, it is the customizer's:
``[10:100]`` a range, ``[1:0.5:20]`` a range with its step, ``[10]`` a
maximum (from 0), ``[a, b, c]`` or ``[1:one, 2:two]`` options; a plain number
is a step (a string's maximum length). Anything after a bracket stops
OpenSCAD reading it, and so it stops this. The **caption** is the ``//``
comment alone on the line just above. The **unit** is what
``customizer.unit_of`` reads: a caption ending ``[mm]``, or a trailing
comment that is one word.

**A literal value** is a number (``12``, ``-0.5``, ``1e3``), a string, ``true``,
``false``, ``undef``, or a vector of literals (``[1, 2, 3]``). Anything else
-- ``size * 0.1``, ``str("a", b)``, a range -- is an expression, and the
assignment is **computed**; its value is what OpenSCAD evaluates it to
(``customizer.compile_scad`` echoes each one after the text, which changes
nothing it compiles).

**Writing a value** replaces the value's span and nothing else: the name, the
spacing, the ``;`` and the comment stay. The last assignment of a name is the
one written (it is the one OpenSCAD uses). A name with no top-level assignment
is set by a line ``name = value;`` appended at the end of the text. A number
is written as Python's shortest form, a whole one without ``.0``; a string
with ``"`` and ``\\`` escaped; a boolean ``true``/``false``; a vector
``[1, 2, 3]``.

**Offsets.** ``from`` and ``to`` count what a JavaScript string counts, UTF-16
code units, so an editor in the page can use them as they are; ``line`` is
1-based. (The functions here take and return Python strings, whose indexes
count code points; ``Assignment.start``/``end`` are those.)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from pydantic import BaseModel, Field

NAME = re.compile(r"\$?[A-Za-z_][A-Za-z0-9_]*")
_NUMBER = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_GROUP = re.compile(r"^\s*\[\s*([^\]]+?)\s*\]\s*$")
_DEFINES = ("module", "function")
HIDDEN = "Hidden"


class Unparsed(ValueError):
    """Not a literal: an expression."""


class Option(BaseModel):
    value: Any
    label: str


class Assignment(BaseModel):
    """One top-level assignment, as the page builds a control from it and
    rewrites it."""

    name: str
    expression: str = Field(description="The value's text, exactly as it stands")
    computed: bool = Field(description="An expression, not a literal")
    value: Any = Field(
        None,
        description="The literal's value; a computed one's as OpenSCAD evaluated it, "
        "where it was (value_known)",
    )
    value_known: bool = Field(True, description="False: a computed value not evaluated yet")
    line: Optional[int] = Field(description="1-based; None for a value this text does not set")
    from_: Optional[int] = Field(
        alias="from", description="The value's first character, UTF-16 offset"
    )
    to: Optional[int] = Field(description="One past the value's last character, UTF-16 offset")
    printed: Optional[str] = Field(
        None, description="A computed value as OpenSCAD printed it, where it was evaluated"
    )
    comment: Optional[str] = Field(None, description="The trailing // comment, trimmed")
    caption: Optional[str] = Field(None, description="The // comment alone on the line above")
    group: Optional[str] = Field(None, description="The /* [Group] */ it is under")
    parameter: bool = Field(
        description="What gets a control: before the first module or function, not Hidden"
    )
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    options: List[Option] = Field(default_factory=list)
    unit: Optional[str] = None
    set: bool = Field(
        True,
        description="Assigned in this text: false for an upstream's value an overlay does not set",
    )

    model_config = {"populate_by_name": True}

    # Where it is in the Python string (code points): not part of the answer.
    start: int = Field(0, exclude=True)
    end: int = Field(0, exclude=True)


@dataclass
class _Scan:
    """The text with comments and strings marked, and the statements found."""

    text: str
    assignments: List[Assignment] = field(default_factory=list)


def _utf16(text: str) -> List[int]:
    """UTF-16 offset of each code point index (one past the end included)."""
    offsets, at = [0], 0
    for ch in text:
        at += 2 if ord(ch) > 0xFFFF else 1
        offsets.append(at)
    return offsets


# --- literals ---------------------------------------------------------------------------


def _literal(text: str, at: int = 0) -> Tuple[Any, int]:
    """The literal starting at ``at`` (whitespace skipped) and where it ends."""
    n = len(text)
    while at < n and text[at].isspace():
        at += 1
    if at >= n:
        raise Unparsed("nothing")
    ch = text[at]
    if ch == '"':
        out, i = [], at + 1
        escapes = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}
        while i < n and text[i] != '"':
            if text[i] == "\\" and i + 1 < n:
                nxt = text[i + 1]
                if nxt in escapes:
                    out.append(escapes[nxt])
                    i += 2
                    continue
                if nxt == "x" and i + 3 < n:
                    out.append(chr(int(text[i + 2 : i + 4], 16)))
                    i += 4
                    continue
                if nxt == "u" and i + 5 < n:
                    out.append(chr(int(text[i + 2 : i + 6], 16)))
                    i += 6
                    continue
            out.append(text[i])
            i += 1
        if i >= n:
            raise Unparsed("an unclosed string")
        return "".join(out), i + 1
    if ch == "[":
        items, i = [], at + 1
        while True:
            while i < n and text[i].isspace():
                i += 1
            if i < n and text[i] == "]":
                return items, i + 1
            value, i = _literal(text, i)
            items.append(value)
            while i < n and text[i].isspace():
                i += 1
            if i < n and text[i] == ",":
                i += 1
                continue
            if i < n and text[i] == "]":
                return items, i + 1
            raise Unparsed("not a vector of literals")
    word = NAME.match(text, at)
    if word is not None:
        keyword = {"true": True, "false": False, "undef": None}
        if word.group(0) in keyword:
            return keyword[word.group(0)], word.end()
        raise Unparsed(f"a name: {word.group(0)}")
    number = _NUMBER.match(text, at)
    if number is not None:
        written = number.group(0)
        if re.fullmatch(r"[+-]?\d+", written):
            return int(written), number.end()
        return float(written), number.end()
    raise Unparsed(f"not a literal at {text[at : at + 10]!r}")


def literal_value(text: str) -> Any:
    """The literal ``text`` is, whole: Unparsed for an expression."""
    value, end = _literal(text)
    if text[end:].strip():
        raise Unparsed("more after the literal: an expression")
    return value


def literal_text(value: Any) -> str:
    """``value`` as a SCAD literal, as this module writes one."""
    from enum import Enum

    if isinstance(value, Enum):
        return literal_text(value.value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "undef"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"{value!r} has no OpenSCAD literal")
        return str(int(value)) if value.is_integer() and abs(value) < 1e15 else repr(value)
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(literal_text(v) for v in value) + "]"
    raise TypeError(f"no OpenSCAD literal for {type(value).__name__}: {value!r}")


# --- the customizer's comment --------------------------------------------------------------


def _bracket_parts(inner: str) -> List[str]:
    return [p.strip() for p in inner.split(",")]


def customizer_comment(comment: Optional[str]) -> Dict[str, Any]:
    """What a trailing comment tells the customizer: ``min``, ``max``, ``step``,
    ``options``, as the module's docstring has it; {} for anything else."""
    if not comment:
        return {}
    text = comment.strip()
    if _NUMBER.fullmatch(text):
        return {"step": float(text)}
    if not (text.startswith("[") and text.endswith("]")) or text.count("[") != 1:
        return {}
    inner = text[1:-1].strip()
    if not inner:
        return {}
    if "," not in inner and inner.count(":") in (1, 2):
        bits = [b.strip() for b in inner.split(":")]
        if all(_NUMBER.fullmatch(b) for b in bits):
            numbers = [float(b) for b in bits]
            if len(numbers) == 2:
                return {"min": numbers[0], "max": numbers[1]}
            return {"min": numbers[0], "step": numbers[1], "max": numbers[2]}
    if "," not in inner and ":" not in inner and _NUMBER.fullmatch(inner):
        return {"min": 0.0, "max": float(inner)}
    options = []
    for part in _bracket_parts(inner):
        if not part:
            return {}
        value, _, label = part.partition(":")
        value = value.strip()
        try:
            parsed = literal_value(value) if value else value
        except Unparsed:
            parsed = value  # an unquoted word: a string choice, as the customizer has it
        if isinstance(parsed, float) and parsed.is_integer():
            parsed = parsed  # numbers stay as written
        options.append(Option(value=parsed, label=(label.strip() or value)))
    return {"options": options}


# --- the scan ------------------------------------------------------------------------------


def _skip_space_and_comments(text: str, i: int, groups: List[Tuple[int, str]]) -> int:
    n = len(text)
    while i < n:
        if text[i].isspace():
            i += 1
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end < 0 else end + 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            close = n if end < 0 else end + 2
            group = _GROUP.match(text[i + 2 : close - 2] if end >= 0 else "")
            if group:
                groups.append((i, group.group(1)))
            i = close
        else:
            break
    return i


def _statement_end(text: str, i: int) -> Tuple[int, Optional[int]]:
    """From ``i``, the end of the statement there (one past its ``;``, its
    closing ``}``, or its ``>``), and where its ``;`` at depth 0 is (None if
    it ended otherwise)."""
    n, depth = len(text), 0
    if re.match(r"(include|use)\s*<", text[i:]):
        close = text.find(">", i)
        return (n if close < 0 else close + 1), None
    while i < n:
        ch = text[i]
        if text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end < 0 else end + 1
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        if ch == '"':
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
            i += 1
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if ch == "}" and depth <= 0:
                return i + 1, None
        elif ch == ";" and depth <= 0:
            return i + 1, i
        i += 1
    return n, None


def _line_of(text: str, at: int) -> int:
    return text.count("\n", 0, at) + 1


def _trailing_comment(text: str, after: int) -> Optional[str]:
    """The ``//`` comment on the line of ``after`` (one past a ``;``), with only
    spaces or tabs between."""
    i, n = after, len(text)
    while i < n and text[i] in " \t":
        i += 1
    if text.startswith("//", i):
        end = text.find("\n", i)
        return text[i + 2 : n if end < 0 else end].strip()
    return None


def _caption(text: str, start: int) -> Optional[str]:
    """The ``//`` comment alone on the line above the one ``start`` is on."""
    line_start = text.rfind("\n", 0, start) + 1
    if line_start == 0:
        return None
    above_end = line_start - 1
    above_start = text.rfind("\n", 0, above_end) + 1
    above = text[above_start:above_end].strip()
    if above.startswith("//"):
        return above[2:].strip() or None
    return None


def parse_assignments(text: str) -> List[Assignment]:
    """Every top-level assignment in ``text``, in order, as the grammar in this
    module's docstring has it. Literal values are read; a computed one's is
    left unknown (``value_known`` false)."""
    from .customizer import unit_of

    utf16 = _utf16(text)
    found: List[Assignment] = []
    groups: List[Tuple[int, str]] = []
    defined = False
    i, n = 0, len(text)
    while True:
        i = _skip_space_and_comments(text, i, groups)
        if i >= n:
            break
        word = NAME.match(text, i)
        if word is not None and word.group(0) in _DEFINES:
            defined = True
        assigned = None
        if word is not None:
            j = word.end()
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] == "=" and not text.startswith("==", j):
                assigned = (word.group(0), j + 1)
        end, semicolon = _statement_end(text, i)
        if assigned is not None and semicolon is not None:
            name, after_eq = assigned
            start = after_eq
            while start < semicolon and text[start].isspace():
                start += 1
            stop = semicolon
            while stop > start and text[stop - 1].isspace():
                stop -= 1
            expression = text[start:stop]
            try:
                value, computed = literal_value(expression), False
            except Unparsed:
                value, computed = None, True
            group = groups[-1][1] if groups else None
            comment = _trailing_comment(text, semicolon + 1)
            caption = _caption(text, i)
            told = customizer_comment(comment)
            unit, shown_caption = unit_of({"name": name, "caption": caption}, text)
            found.append(
                Assignment(
                    name=name,
                    expression=expression,
                    computed=computed,
                    value=value,
                    value_known=not computed,
                    line=_line_of(text, i),
                    **{"from": utf16[start]},
                    to=utf16[stop],
                    comment=comment,
                    caption=shown_caption,
                    group=group,
                    parameter=not defined and group != HIDDEN,
                    min=told.get("min"),
                    max=told.get("max"),
                    step=told.get("step"),
                    options=told.get("options", []),
                    unit=unit,
                    start=start,
                    end=stop,
                )
            )
        if end <= i:
            break
        i = end
    return found


def last_of(assignments: List[Assignment]) -> Dict[str, Assignment]:
    """Each name's last assignment: the one OpenSCAD uses."""
    out: Dict[str, Assignment] = {}
    for a in assignments:
        out[a.name] = a
    return out


def literal_values(text: str) -> Dict[str, Any]:
    """Each top-level name's literal value (its last assignment); a computed
    one is left out."""
    return {name: a.value for name, a in last_of(parse_assignments(text)).items() if not a.computed}


def write_values(text: str, values: Mapping[str, Any]) -> str:
    """``text`` with each of ``values`` written into its name's last top-level
    assignment, the value's span replaced and nothing else; a name with none
    is appended as ``name = value;`` on a line of its own at the end."""
    if not values:
        return text
    at = last_of(parse_assignments(text))
    spans = []
    appended = []
    for name, value in values.items():
        if not NAME.fullmatch(name):
            raise ValueError(f"{name!r} is not a SCAD name")
        written = literal_text(value)
        if name in at:
            spans.append((at[name].start, at[name].end, written))
        else:
            appended.append(f"{name} = {written};")
    out = text
    for start, end, written in sorted(spans, reverse=True):
        out = out[:start] + written + out[end:]
    if appended:
        if out and not out.endswith("\n"):
            out += "\n"
        out += "\n".join(appended) + "\n"
    return out


def differences(text: str, own: str) -> Dict[str, Any]:
    """What ``text`` sets otherwise than ``own``: each top-level name whose value
    (literal, else its expression) differs, or that ``own`` does not assign."""

    def values(t: str) -> Dict[str, Any]:
        return {
            n: (a.expression if a.computed else a.value)
            for n, a in last_of(parse_assignments(t)).items()
        }

    mine, theirs = values(text), values(own)
    return {n: v for n, v in mine.items() if n not in theirs or theirs[n] != v}


__all__ = [
    "Assignment",
    "HIDDEN",
    "Option",
    "Unparsed",
    "customizer_comment",
    "differences",
    "last_of",
    "literal_text",
    "literal_value",
    "literal_values",
    "parse_assignments",
    "write_values",
]
