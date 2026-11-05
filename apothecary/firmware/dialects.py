"""The dialects of the machine seam, as one shape: what a port's board answers in.

Marlin's G-code (``gcode.py``, a printer) and GRBL's (``grbl.py``, a router) each
poll, control and query a link in their own words, bound their own controls, keep
their own report-only queries, stop their own way and say what a person may still
send while a streamed job holds the port. ``devices.py`` asks for the dialect of a
port and calls that; a port nothing has identified yet takes a line either dialect
allows, Marlin's first.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Pattern

from . import gcode, grbl


@dataclass(frozen=True)
class Dialect:
    word: str  # what PrinterInfo.dialect carries
    machine: str  # the kind of machine it drives (apothecary/jobs.py)
    poll: Callable[..., gcode.PrinterStatus]
    control: Callable[[gcode.GcodeLink, str], List[str]]
    query: Callable[[gcode.GcodeLink, str], List[str]]
    normalise_control: Callable[[str], str]
    normalise_query: Callable[[str], str]
    stop: str  # the emergency stop's line, the one that goes whatever holds the port
    query_codes: Dict[str, str]  # the report-only queries, each with what it reports
    line_timeout: Callable[[str], float]  # how long a streamed line may take
    job_allows: Pattern[str]  # what a person may send while a streamed job holds the port
    explain: Optional[Callable[[str], Optional[str]]]  # the words for a board's objection


MARLIN = Dialect(
    word=gcode.DIALECT,
    machine=gcode.MACHINE,
    poll=gcode.poll_printer,
    control=gcode.control_printer,
    query=gcode.query_printer,
    normalise_control=gcode.normalise_control,
    normalise_query=gcode.normalise_query,
    stop=gcode.EMERGENCY_STOP,
    query_codes=gcode.QUERY_CODES,
    line_timeout=gcode.line_timeout,
    job_allows=gcode.JOB_ALLOWS,
    explain=None,
)
GRBL = Dialect(
    word=grbl.DIALECT,
    machine=grbl.MACHINE,
    poll=grbl.poll_router,
    control=grbl.control_router,
    query=grbl.query_router,
    normalise_control=grbl.normalise_control,
    normalise_query=grbl.normalise_query,
    stop=grbl.EMERGENCY_STOP,
    query_codes=grbl.QUERY_CODES,
    line_timeout=grbl.line_timeout,
    job_allows=grbl.JOB_ALLOWS,
    explain=grbl.explain,
)
BY_WORD: Dict[str, Dialect] = {MARLIN.word: MARLIN, GRBL.word: GRBL}
BY_MACHINE: Dict[str, Dialect] = {d.machine: d for d in BY_WORD.values()}
STOPS = tuple(d.stop for d in BY_WORD.values())


def by_word(word: Optional[str]) -> Dialect:
    """The dialect named ``word``; Marlin's for None, a port nothing has identified."""
    return BY_WORD.get(word or "", MARLIN)


def either(command: str, how: str) -> str:
    """``command`` normalised (``how``: ``normalise_control`` or ``normalise_query``) by
    whichever dialect takes it, Marlin's first: for a port nothing has identified.
    A line one dialect knows and bounds is refused for its bound
    (``gcode.OutOfBounds``), not as unknown to the other."""
    try:
        return getattr(MARLIN, how)(command)
    except ValueError as marlin_said:
        try:
            return getattr(GRBL, how)(command)
        except gcode.OutOfBounds:
            raise
        except ValueError:
            raise marlin_said from None
