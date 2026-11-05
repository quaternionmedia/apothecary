"""A G-code file as something to draw and scrub through, whichever machine it is for.

``of(lines, process)`` reads a file through the interpreter (``moves.py``) and a
``Process`` (``process.py``) into one shape: every piece of tool travel in order, what
kind of move it is, the groups a person scrubs through, and what the moves add up to.
The page draws that shape the same way for a printer and for a router.

A long file is drawn to within a distance rather than in full: consecutive short moves
of one kind in one group become one, the distance doubling until the file fits. What it
adds up to is read before that, so the sums are always the file's own.
"""

from __future__ import annotations

import math
from array import array
from typing import Dict, Iterable, List, Optional

from pydantic import BaseModel

from .moves import Comment, Dwell, Move, Reader, read
from .process import Process

# What the page is given at most: enough for a part's every wall at a viewer's scale.
MAX_SEGMENTS = 100_000
FIRST_WITHIN_MM = 0.05
LAST_WITHIN_MM = 1600.0


class Box(BaseModel):
    """Where a kind of move reaches, in the file's coordinates."""

    min: List[float]
    max: List[float]


class Group(BaseModel):
    """Moves a person scrubs through as one: a layer, a pass."""

    label: str
    z: Optional[float] = None
    first: int  # the first segment drawn in it
    count: int  # how many segments are drawn in it
    sent: int  # how many lines would be sent before it


class Preview(BaseModel):
    machine: str
    process: str
    word: str  # what a group is called
    kinds: List[str]  # what `kind_of` indexes
    points: List[float]  # six per segment, x y z x y z, in the file's coordinates
    kind_of: List[int]  # one per segment
    groups: List[Group]
    bounds: Dict[str, Box]  # by kind, where it has moves
    length_mm: Dict[str, float]  # by kind, along every move of it
    time_s: float  # at the feeds written
    moves: int  # the moves the file holds
    within_mm: float  # how closely `points` follows them; 0 for exactly
    lines: int  # the lines that would be sent


def _before(process: Process) -> str:
    return f"before the first {process.word}"


class _Sums:
    """What the moves add up to, by kind."""

    def __init__(self, process: Process) -> None:
        self.process = process
        self.low: Dict[str, List[float]] = {}
        self.high: Dict[str, List[float]] = {}
        self.length: Dict[str, float] = {}
        self.time_s = 0.0

    def add(self, move: Move, kind: str) -> None:
        dist = math.dist(move.start, move.end)
        self.length[kind] = self.length.get(kind, 0.0) + dist
        feed = self.process.rapid if move.rapid and self.process.rapid else move.feed
        if feed:
            self.time_s += dist / feed * 60.0
        low = self.low.setdefault(kind, list(move.start))
        high = self.high.setdefault(kind, list(move.start))
        for point in (move.start, move.end):
            for i in range(3):
                low[i] = min(low[i], point[i])
                high[i] = max(high[i], point[i])

    def boxes(self) -> Dict[str, Box]:
        return {
            kind: Box(
                min=[round(v, 3) for v in self.low[kind]],
                max=[round(v, 3) for v in self.high[kind]],
            )
            for kind in self.low
        }


def reach(lines: Iterable[str], process: Process, kind: Optional[str] = None) -> Optional[Box]:
    """Where one kind of move reaches (the part's, for none named), or None for a file
    that has none: read as it streams, for a file too long to want drawn."""
    wanted = kind or process.kinds[0]
    sums = _Sums(process)
    for event in read(lines):
        if isinstance(event, Move):
            found = process.classify(event)
            if found == wanted:
                sums.add(event, found)
    return sums.boxes().get(wanted)


def _thin(
    points: "array[float]", kinds: "array[int]", ends: List[int], within: float
) -> "tuple[array[float], array[int], List[int]]":
    """Consecutive moves of one kind in one group, each short, as one: its first's start
    to its last's end, none longer than ``within``. ``ends`` are where each group ends."""
    out_points = array("d")
    out_kinds = array("B")
    out_ends: List[int] = []
    begin = 0
    for end in ends:
        run_kind = -1
        run_start = run_end = (0.0, 0.0, 0.0)
        count = 0
        for i in range(begin, end):
            at = i * 6
            start = (points[at], points[at + 1], points[at + 2])
            stop = (points[at + 3], points[at + 4], points[at + 5])
            if (
                count
                and kinds[i] == run_kind
                and start == run_end
                and math.dist(run_start, stop) <= within
            ):
                run_end = stop
                continue
            if count:
                out_points.extend(run_start + run_end)
                out_kinds.append(run_kind)
            run_kind, run_start, run_end = kinds[i], start, stop
            count += 1
        if count:
            out_points.extend(run_start + run_end)
            out_kinds.append(run_kind)
        out_ends.append(len(out_kinds))
        begin = end
    return out_points, out_kinds, out_ends


def of(lines: Iterable[str], process: Process, max_segments: int = MAX_SEGMENTS) -> Preview:
    """The preview of a file's ``lines`` for ``process``."""
    kind_index = {kind: i for i, kind in enumerate(process.kinds)}
    rule = process.groups()
    sums = _Sums(process)
    points = array("d")
    kinds = array("B")
    groups: List[dict] = []
    ends: List[int] = []
    reader = Reader(lines)
    for event in reader:
        if isinstance(event, Comment):
            rule.comment(event.text)
        elif isinstance(event, Dwell):
            sums.time_s += process.dwell(event.p, event.s)
        else:
            kind = process.classify(event)
            sums.add(event, kind)
            started = rule.move(event, kind)
            if started is None and not groups:
                started = (_before(process), None)
            if started is not None:
                if groups:
                    ends.append(len(kinds))
                groups.append({"label": started[0], "z": started[1], "sent": event.sent})
            points.extend(event.start + event.end)
            kinds.append(kind_index[kind])
    if groups:
        ends.append(len(kinds))
    moves = len(kinds)
    within = 0.0
    step = FIRST_WITHIN_MM
    drawn_points, drawn_kinds, drawn_ends = points, kinds, ends
    while len(drawn_kinds) > max_segments and step <= LAST_WITHIN_MM:
        drawn_points, drawn_kinds, drawn_ends = _thin(points, kinds, ends, step)
        within = step
        step *= 2
    begin = 0
    finished: List[Group] = []
    for group, end in zip(groups, drawn_ends, strict=True):
        finished.append(Group(first=begin, count=end - begin, **group))
        begin = end
    return Preview(
        machine=process.machine,
        process=process.name,
        word=process.word,
        kinds=list(process.kinds),
        points=[round(v, 3) for v in drawn_points],
        kind_of=list(drawn_kinds),
        groups=finished,
        bounds=sums.boxes(),
        length_mm={kind: round(mm, 1) for kind, mm in sums.length.items()},
        time_s=round(sums.time_s, 1),
        moves=moves,
        within_mm=within,
        lines=reader.sent,
    )
