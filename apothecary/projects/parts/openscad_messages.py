"""What OpenSCAD said about a render, by file and line.

OpenSCAD reports on stderr, one message a line: ``ERROR: <what> in file <f>,
line <n>``, the same shape for a ``WARNING:`` or a ``DEPRECATED:``, followed
by ``TRACE:`` lines naming the calls that led there. 2021.01 and the
development snapshots share that shape and differ in the details, each kept
as it is said:

- 2021.01 quotes a name with ``'``, a snapshot with ``"`` (``Ignoring unknown
  variable 'foo'`` / ``"foo"``);
- a missing include is ``Can't open include file 'x'.`` with no location in
  2021.01, and ``Can't find include file 'x'. in file f, line n`` in a snapshot;
- a snapshot traces the module a failure is inside (``call of 'thing()'``).

A render that produced nothing ends ``Current top level object is empty.``,
which is the error when there is no other. Echoes, the cache and timing
report, and the summary are not messages. A line past the end of a file is
OpenSCAD counting the text it appends after it (its ``-D`` definitions), so
a parser error there is at the file's end.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, List, Optional

from pydantic import BaseModel, Field


class TraceStep(BaseModel):
    """One call on the way to a message, innermost first."""

    message: str
    file: Optional[str] = None
    line: Optional[int] = None


class OpenSCADMessage(BaseModel):
    """One error or warning, where OpenSCAD said it is."""

    level: str = Field(description='"error" or "warning"')
    message: str
    file: Optional[str] = Field(None, description="As OpenSCAD names it, or repository-relative")
    line: Optional[int] = Field(None, description="1-based; None where OpenSCAD gave none")
    trace: List[TraceStep] = Field(default_factory=list)


_TAGGED = re.compile(r"^(?P<tag>[A-Z]+(?:-[A-Z]+)?):\s?(?P<body>.*)$")
_WHERE = re.compile(r"^(?P<text>.*?),?\s+in file (?P<file>.+?), line (?P<line>\d+)\s*\.?\s*$")
_LEVELS = {"ERROR": "error", "WARNING": "warning", "DEPRECATED": "warning"}
_NOTHING_MADE = "Current top level object is"


def _located(body: str):
    where = _WHERE.match(body)
    if where is None:
        return body.strip(), None, None
    return where.group("text").strip(), where.group("file"), int(where.group("line"))


def parse_openscad_messages(stderr: Optional[str]) -> List[OpenSCADMessage]:
    """Every error and warning in ``stderr``, in order, each with its trace."""
    messages: List[OpenSCADMessage] = []
    for raw in (stderr or "").splitlines():
        line = raw.strip()
        if line.startswith(_NOTHING_MADE):
            messages.append(OpenSCADMessage(level="error", message=line))
            continue
        tagged = _TAGGED.match(line)
        if tagged is None:
            continue
        tag, body = tagged.group("tag"), tagged.group("body")
        if tag == "TRACE":
            if messages:
                text, file, number = _located(body)
                messages[-1].trace.append(TraceStep(message=text, file=file, line=number))
            continue
        level = _LEVELS.get(tag)
        if level is None and tag.endswith("-ERROR"):
            level = "error"
        elif level is None and tag.endswith("-WARNING"):
            level = "warning"
        if level is None:
            continue  # ECHO, and anything else that is not a diagnosis
        text, file, number = _located(body)
        messages.append(OpenSCADMessage(level=level, message=text, file=file, line=number))
    return messages


def place_messages(
    messages: List[OpenSCADMessage],
    base: Optional[Path],
    show: Callable[[Path], Optional[str]],
    own: Optional[Path] = None,
) -> List[OpenSCADMessage]:
    """``messages`` with each file that exists named as ``show`` names it: a
    relative name resolved against ``base``, the directory OpenSCAD ran in
    (None: only absolute names resolve). Any other keeps its own name, never
    a directory. A line past the end of ``own`` (the part's SCAD) is its last
    line: see the module's note."""
    own_lines = None
    if own is not None:
        try:
            own_lines = max(1, len(own.read_text(encoding="utf-8", errors="replace").splitlines()))
        except OSError:
            own_lines = None

    def place(file: Optional[str], line: Optional[int]):
        if file is None:
            return None, line
        written = Path(file)
        if written.is_absolute():
            where = written
        elif base is not None:
            where = base / written
        else:
            return written.name, line
        where = where.resolve()
        if not where.is_file():
            return written.name, line
        if own_lines is not None and line is not None and where == own.resolve():
            line = min(line, own_lines)
        named = show(where)
        return (named if named is not None else written.name), line

    placed = []
    for message in messages:
        file, line = place(message.file, message.line)
        trace = []
        for step in message.trace:
            step_file, step_line = place(step.file, step.line)
            trace.append(TraceStep(message=step.message, file=step_file, line=step_line))
        placed.append(message.model_copy(update={"file": file, "line": line, "trace": trace}))
    return placed


__all__ = ["OpenSCADMessage", "TraceStep", "parse_openscad_messages", "place_messages"]
