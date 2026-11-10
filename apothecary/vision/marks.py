"""A whiteboard's marks, sorted: a diagram's, writing, or unsure.

A stroke is one touching run of marker (``outline.read_strokes``). A mark is the
strokes that belong together: a closed stroke, a line, or a run of small strokes
along one baseline, which is how writing lies. Each mark is sorted by plain
features of its strokes -- how tall it is against the picture, whether it closes,
how straight it runs, how many strokes it has and how they sit in a row -- and
says how sure it is. A mark the sorter cannot place is ``unsure``, which is an
answer.

A person's word on a mark wins, and says who decided. Each word is kept as an
example: the mark's place, its features, what the sorter said and what the person
said. ``fit`` reads examples and writes the sorter's table of thresholds; the
sorter reads the table, so the same picture gives the same answer.

A mark's colour is read and kept with it. It decides nothing.

Pillow and plain Python, with the network switched off.

A prototype: no ratified record governs it.
"""

from __future__ import annotations

import hashlib
import json
import os
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from pydantic import BaseModel, Field

from ..evidence.words import hex_of, nearest_colour
from ..models.vectors import Vector2D
from .geometry import edge_points, smallest_box
from .outline import Reading, Stroke
from .plain import LINE_RATIO

FORMAT = "apothecary.marks/1"

# The sorter's thresholds, as the table holds them. Lengths are shares of the
# working picture's longer edge.
DEFAULTS: Dict[str, float] = {
    # A stroke shorter than this, top to bottom, is as small as writing is.
    "small": 0.07,
    # Two small strokes belong to one run when the gap between them is under this
    # many times the taller one's height.
    "gap": 1.5,
    # A run this many strokes long is writing; a shorter one is writing only when
    # it is this many times wider than it is tall.
    "run": 3,
    "wide": 2.0,
    # Under this sureness a mark is unsure, whatever it leans to.
    "sure": 0.55,
}

# A marker's line, widened as it is read, covers no more than this share of the
# working picture's longer edge for each unit of its length.
LINE_THICK = 0.0175

TABLE_ENV = "APOTHECARY_MARKS_TABLE"
TABLE = Path(__file__).with_name("marks_table.json")


class Kind(str, Enum):
    DIAGRAM = "diagram"
    WRITING = "writing"
    UNSURE = "unsure"
    # A person's word alone: a smear, a magnet, a reflection.
    NOTHING = "nothing"


class Mark(BaseModel):
    """Strokes that belong together, and what they are taken to be."""

    id: str
    kind: Kind
    sure: float = Field(ge=0.0, le=1.0)
    why: str
    # Who decided its kind: the sorter, or a person.
    by: str = "sorter"
    # What the sorter said, kept when a person says otherwise.
    guess: Optional[Kind] = None
    min_point: Vector2D
    max_point: Vector2D
    strokes: List[int]
    # The mark it lies inside, where it lies inside a closed stroke.
    inside: Optional[str] = None
    # Whether a closed stroke makes it, so it may be a shape.
    closed: bool = False
    colour: str = ""
    rgb: str = ""
    features: Dict[str, float] = Field(default_factory=dict)

    @property
    def centre(self) -> Tuple[float, float]:
        return (
            (self.min_point.x + self.max_point.x) / 2,
            (self.min_point.y + self.max_point.y) / 2,
        )


class Example(BaseModel):
    """One mark with what the sorter said of it and what a person said."""

    picture: str
    min: Tuple[float, float]
    max: Tuple[float, float]
    guess: Kind
    sure: float
    word: Kind
    by: str = "you"
    colour: str = ""
    features: Dict[str, float] = Field(default_factory=dict)


class Answers(BaseModel):
    """A person's words on a picture's marks, as a file holds them."""

    format: str = FORMAT
    examples: List[Example] = Field(default_factory=list)


def table() -> Dict[str, float]:
    """The sorter's thresholds: the defaults, under the packaged table, under the
    table ``APOTHECARY_MARKS_TABLE`` names."""
    values = dict(DEFAULTS)
    for source in (TABLE, os.environ.get(TABLE_ENV)):
        if not source or not Path(source).is_file():
            continue
        held = json.loads(Path(source).read_text(encoding="utf-8"))
        values.update({key: float(held[key]) for key in DEFAULTS if key in held})
    return values


def _features(reading: Reading, stroke: Stroke) -> Dict[str, float]:
    edge = max(reading.width, reading.height)
    left, top, right, bottom = stroke.box
    wide, tall = right - left + 1, bottom - top + 1
    box = smallest_box(edge_points(stroke.blob, reading.width, set(stroke.blob)))
    long_side = max(box.width, box.height, 1.0)
    return {
        "tall": round(tall / edge, 4),
        "wide": round(wide / edge, 4),
        "thin": round(min(box.width, box.height) / long_side, 4),
        "long": round(long_side / edge, 4),
        "thick": round(len(stroke.blob) / long_side / edge, 4),
        "full": round(len(stroke.blob) / max(box.area, 1.0), 4),
        "closed": 1.0 if stroke.closed else 0.0,
        "holes": float(len(stroke.holes)),
    }


def _colour(reading: Reading, blobs: Iterable[List[int]]) -> Tuple[str, str]:
    """The colour word and hex of some strokes: the median of each channel over
    their darkest fifth: a stroke is read wider than it is drawn, and its edge
    is part whiteboard."""
    pixels = [index for blob in blobs for index in blob]
    pixels.sort(key=lambda index: reading.grey[index])
    core = pixels[: max(1, len(pixels) // 5)]
    step = max(1, len(core) // 400)
    sample = core[::step]
    channels = [sorted(reading.rgb[3 * index + c] for index in sample) for c in range(3)]
    rgb = tuple(channel[len(channel) // 2] for channel in channels)
    return nearest_colour(rgb)[0], hex_of(rgb)


def sort(reading: Reading, thresholds: Optional[Dict[str, float]] = None) -> List[Mark]:
    """A reading's marks, sorted, top to bottom and left to right."""
    held = thresholds or table()
    edge = max(reading.width, reading.height)
    features = {stroke.index: _features(reading, stroke) for stroke in reading.strokes}

    small: List[Stroke] = []
    drafts: List[Tuple[List[Stroke], Kind, float, str]] = []
    for stroke in reading.strokes:
        if stroke.outer != reading.ground and stroke.outer not in reading.encloser:
            # Round the whiteboard, not on it: the wall, its frame, its tray.
            continue
        f = features[stroke.index]
        if reading.ground in stroke.holes:
            continue
        if _a_line(f, held):
            drafts.append(([stroke], Kind.DIAGRAM, 0.7, "a long straight stroke is a line"))
        elif f["tall"] < held["small"] and not (
            stroke.closed and f["wide"] >= 2 * held["small"] and f["full"] < 0.5
        ):
            small.append(stroke)
        elif stroke.closed:
            drafts.append(([stroke], Kind.DIAGRAM, 0.8, "a closed stroke this size is a shape"))
        elif stroke.holes or f["full"] > 0.45:
            drafts.append(([stroke], Kind.DIAGRAM, 0.65, "a mark filled in is a shape"))
        else:
            drafts.append(([stroke], Kind.UNSURE, 0.4, "an open stroke this size is neither"))

    for run in _runs(small, held["gap"]):
        left = min(s.box[0] for s in run)
        right = max(s.box[2] for s in run)
        tall = max(s.box[3] - s.box[1] + 1 for s in run)
        stretch = (right - left + 1) / max(tall, 1)
        if len(run) >= held["run"] or stretch >= held["wide"]:
            sure = min(0.85, 0.5 + 0.1 * len(run) + 0.03 * stretch)
            drafts.append((run, Kind.WRITING, sure, "small strokes in a row are writing"))
        elif len(run) == 1 and run[0].closed:
            drafts.append(
                (run, Kind.UNSURE, 0.45, "a small closed stroke alone: a letter, or a hole")
            )
        else:
            drafts.append((run, Kind.UNSURE, 0.4, "too few small strokes to be a line of writing"))

    drafts.sort(
        key=lambda d: (
            min(s.box[1] for s in d[0]) // max(1, edge // 12),
            min(s.box[0] for s in d[0]),
        )
    )
    marks: List[Mark] = []
    owner: Dict[int, str] = {}
    for number, (strokes, kind, sure, why) in enumerate(drafts, start=1):
        if sure < held["sure"]:
            kind = Kind.UNSURE
        word, rgb = _colour(reading, [s.blob for s in strokes])
        first = features[strokes[0].index]
        mark = Mark(
            id=f"m{number}",
            kind=kind,
            sure=round(sure, 2),
            why=why,
            min_point=Vector2D(
                x=min(s.box[0] for s in strokes) / reading.width,
                y=min(s.box[1] for s in strokes) / reading.height,
            ),
            max_point=Vector2D(
                x=(max(s.box[2] for s in strokes) + 1) / reading.width,
                y=(max(s.box[3] for s in strokes) + 1) / reading.height,
            ),
            strokes=[s.index for s in strokes],
            closed=len(strokes) == 1
            and (strokes[0].closed or bool(strokes[0].holes) or first["full"] > 0.45),
            colour=word,
            rgb=rgb,
            features={**first, "strokes": float(len(strokes))},
        )
        marks.append(mark)
        for stroke in strokes:
            owner[stroke.index] = mark.id
    by_index = {stroke.index: stroke for stroke in reading.strokes}
    for mark in marks:
        outer = by_index[mark.strokes[0]].outer
        if outer != reading.ground and outer in reading.encloser:
            mark.inside = owner.get(reading.encloser[outer])
    return marks


def _a_line(features: Dict[str, float], held: Dict[str, float]) -> bool:
    """Whether a stroke is a line: long, thin, and along its length no thicker
    than a marker draws, ticks at its ends or not, which a row of letters run
    together is."""
    return (
        features.get("thin", 1.0) < LINE_RATIO
        and features.get("long", 0.0) >= held["small"]
        and features.get("thick", 1.0) <= LINE_THICK
    )


def _runs(strokes: Sequence[Stroke], gap: float) -> List[List[Stroke]]:
    """Small strokes gathered into rows: two belong together when their heights
    overlap and the gap between them is under ``gap`` times the taller's height."""
    parent = list(range(len(strokes)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(strokes):
        for j in range(i + 1, len(strokes)):
            b = strokes[j]
            if a.outer != b.outer:
                continue
            overlap = min(a.box[3], b.box[3]) - max(a.box[1], b.box[1]) + 1
            tall = max(a.box[3] - a.box[1], b.box[3] - b.box[1]) + 1
            apart = max(a.box[0], b.box[0]) - min(a.box[2], b.box[2])
            if overlap > 0.3 * tall and apart < gap * tall:
                parent[root(j)] = root(i)
    rows: Dict[int, List[Stroke]] = {}
    for i, stroke in enumerate(strokes):
        rows.setdefault(root(i), []).append(stroke)
    return [sorted(row, key=lambda s: s.box[0]) for row in rows.values()]


def _overlap(mark: Mark, example: Example) -> float:
    """How much of the smaller of a mark's box and an example's the two share."""
    left = max(mark.min_point.x, example.min[0])
    top = max(mark.min_point.y, example.min[1])
    right = min(mark.max_point.x, example.max[0])
    bottom = min(mark.max_point.y, example.max[1])
    if right <= left or bottom <= top:
        return 0.0
    ours = (mark.max_point.x - mark.min_point.x) * (mark.max_point.y - mark.min_point.y)
    theirs = (example.max[0] - example.min[0]) * (example.max[1] - example.min[1])
    return (right - left) * (bottom - top) / max(min(ours, theirs), 1e-9)


def apply(marks: List[Mark], answers: Optional[Answers]) -> List[Mark]:
    """The marks with a person's words on them: each example's word given to the
    mark whose box it shares most of, more than half. The last word on a mark wins."""
    if answers is None:
        return marks
    said = list(marks)
    for example in answers.examples:
        best = max(said, key=lambda mark: _overlap(mark, example), default=None)
        if best is None or _overlap(best, example) <= 0.5:
            continue
        place = said.index(best)
        said[place] = best.model_copy(
            update={
                "guess": best.guess or best.kind,
                "kind": example.word,
                "by": example.by,
                "sure": 1.0,
                "why": f"{example.by} said so",
            }
        )
    return said


def say(marks: List[Mark], mark_id: str, word: Kind, picture: str, by: str = "you") -> Example:
    """A person's word on one mark, as the example it is kept as."""
    mark = next((m for m in marks if m.id == mark_id), None)
    if mark is None:
        raise KeyError(f"no mark {mark_id!r}; have {[m.id for m in marks]}")
    return Example(
        picture=picture,
        min=(mark.min_point.x, mark.min_point.y),
        max=(mark.max_point.x, mark.max_point.y),
        guess=mark.guess or mark.kind,
        sure=mark.sure,
        word=word,
        by=by,
        colour=mark.colour,
        features=mark.features,
    )


def diagram_strokes(marks: Iterable[Mark]) -> Set[int]:
    """The strokes of every mark that is a diagram's."""
    return {index for mark in marks if mark.kind is Kind.DIAGRAM for index in mark.strokes}


def answers_path(image: Path) -> Path:
    """Where a person's words on a picture's marks lie beside it."""
    return Path(image).with_suffix(".marks.json")


def load(path: Path) -> Answers:
    held = json.loads(Path(path).read_text(encoding="utf-8"))
    if held.get("format") != FORMAT:
        raise ValueError(f"{path} is not {FORMAT}: its format is {held.get('format')!r}")
    return Answers.model_validate(held)


def save(path: Path, answers: Answers) -> None:
    Path(path).write_text(answers.model_dump_json(indent=2) + "\n", encoding="utf-8")


def answers_beside(image: Path) -> Optional[Answers]:
    """The words beside a picture, where a person put a file of them there."""
    path = answers_path(image)
    try:
        return load(path) if path.is_file() else None
    except (OSError, ValueError):
        return None


def digest(image: Path) -> str:
    """What a reading of ``image`` rests on besides its bytes: the words beside
    it and the sorter's table."""
    seen = hashlib.sha256(json.dumps(table(), sort_keys=True).encode())
    path = answers_path(image)
    if path.is_file():
        seen.update(path.read_bytes())
    return seen.hexdigest()


def marks_in(image: Path, answers: Optional[Answers] = None) -> List[Mark]:
    """A picture's marks, sorted, with the words beside it and those given."""
    from .outline import read_strokes

    sorted_marks = apply(sort(read_strokes(Path(image))), answers_beside(Path(image)))
    return apply(sorted_marks, answers)


def score(examples: Sequence[Example], thresholds: Dict[str, float]) -> float:
    """The share of examples the thresholds sort as the person did, from each
    example's own features: what a fit is judged by."""
    if not examples:
        return 1.0
    right = sum(1 for example in examples if _lean(example.features, thresholds) is example.word)
    return right / len(examples)


def _lean(features: Dict[str, float], held: Dict[str, float]) -> Kind:
    """One mark's kind from its kept features alone, as ``sort`` leans."""
    strokes = features.get("strokes", 1.0)
    if _a_line(features, held):
        return Kind.DIAGRAM
    if features.get("tall", 1.0) < held["small"]:
        stretch = features.get("wide", 0.0) / max(features.get("tall", 1.0), 1e-9)
        if strokes >= held["run"] or stretch >= held["wide"]:
            return Kind.WRITING
        return Kind.UNSURE
    if (
        features.get("closed", 0.0)
        or features.get("holes", 0.0)
        or features.get("full", 0.0) > 0.45
    ):
        return Kind.DIAGRAM
    return Kind.UNSURE


def fit(examples: Sequence[Example]) -> Tuple[Dict[str, float], float, float]:
    """The thresholds that sort the most examples as their person did, with the
    score before and after. Searched over a small grid of ``small``, ``run`` and
    ``wide``; of the tables that sort as many, the one that moves the fewest
    thresholds, and none when the table in use already does."""
    before = table()
    best, best_score, best_moved = dict(before), score(examples, before), 0
    start = best_score
    for small in (0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.1):
        for run in (2, 3, 4):
            for wide in (1.5, 2.0, 2.5, 3.0):
                tried = {**before, "small": small, "run": float(run), "wide": wide}
                moved = sum(1 for key in tried if tried[key] != before[key])
                got = score(examples, tried)
                # As many examples as can be, with as few thresholds moved.
                if got > best_score or (got == best_score and moved < best_moved):
                    best, best_score, best_moved = tried, got, moved
    return best, start, best_score


__all__ = [
    "Answers",
    "DEFAULTS",
    "Example",
    "FORMAT",
    "Kind",
    "Mark",
    "answers_beside",
    "answers_path",
    "apply",
    "diagram_strokes",
    "digest",
    "fit",
    "load",
    "marks_in",
    "save",
    "say",
    "score",
    "sort",
    "table",
]
