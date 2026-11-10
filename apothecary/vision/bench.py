"""Measuring how well a finder actually does.

The rulebook says a claim to be checked has to name its checker, and that a
number in a document must have been measured rather than asserted. This is the
meter for "the plain finder works well enough".

It draws pictures whose answers are known — varying position, size, rotation,
speckle and how many shapes are present, filled in or drawn in outline as a
marker draws on a whiteboard, under a shadow, a glare or a smear, framed by a
wall, with notes beside — then asks a finder what it sees and scores the reply. Everything is drawn from a fixed starting number, so the same
run gives the same score on any machine, and a change to the finder shows up as
a change to the number rather than as an argument.

What it does not measure: real photographs. Everything here is clean synthetic
drawing, so a good score means "handles the easy case", not "works". A real
photograph brings shadow, texture, blur and overlap, none of which appear below.
That limit is the honest reading of any number this produces.

Runs on your own machine with nothing fetched.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from .finder import ShapeFinder
from .models import ShapeKind

# What the generator writes beside its shapes: sizes, names, a remark.
WORDS = (
    "120 mm",
    "lid, 3 off",
    "M3 x 4",
    "top plate",
    "check the fit",
    "6 mm ply",
    "R 20",
    "this side up",
)

# The families the generator can draw, and therefore the ones scored.
DRAWABLE = (ShapeKind.RECT, ShapeKind.DISC, ShapeKind.TRI)


@dataclass
class TrueShape:
    """One shape the generator drew, and therefore knows the answer for."""

    kind: ShapeKind
    centre: Tuple[float, float]
    turned_degrees: float = 0.0


@dataclass
class Case:
    """One generated picture and its answers."""

    name: str
    path: Path
    truth: List[TrueShape]
    turned: bool
    speckled: bool
    # Where each line of writing drawn beside the shapes is, by its middle.
    writing: List[Tuple[float, float]] = field(default_factory=list)


@dataclass
class Score:
    """What a finder managed on one run of cases."""

    cases: int = 0
    expected: int = 0
    found: int = 0
    matched: int = 0
    right_kind: int = 0
    place_error: List[float] = field(default_factory=list)
    wrong: List[str] = field(default_factory=list)
    sure_when_right: List[float] = field(default_factory=list)
    sure_when_wrong: List[float] = field(default_factory=list)

    @property
    def found_rate(self) -> float:
        return self.matched / self.expected if self.expected else 0.0

    @property
    def kind_rate(self) -> float:
        """Of the shapes it found, how many it named correctly."""
        return self.right_kind / self.matched if self.matched else 0.0

    @property
    def spurious(self) -> int:
        """Shapes reported that match nothing that was drawn."""
        return max(0, self.found - self.matched)

    @property
    def honest(self) -> Optional[float]:
        """How much less sure it is when it is wrong. Positive is honest.

        None when it was never wrong, because there is nothing to compare.
        """
        if not self.sure_when_wrong or not self.sure_when_right:
            return None
        right = sum(self.sure_when_right) / len(self.sure_when_right)
        wrong = sum(self.sure_when_wrong) / len(self.sure_when_wrong)
        return round(right - wrong, 3)

    @property
    def typical_place_error(self) -> float:
        """Middling distance between where a shape is and where it was said to be."""
        if not self.place_error:
            return 0.0
        ordered = sorted(self.place_error)
        return ordered[len(ordered) // 2]

    def summary(self) -> str:
        return (
            f"{self.cases} pictures, {self.expected} shapes: "
            f"found {self.found_rate:.0%}, named right {self.kind_rate:.0%}, "
            f"{self.spurious} spurious, "
            f"typical placement off by {self.typical_place_error:.3f} of the picture"
        )


def draw_cases(
    into: Path,
    *,
    count: int = 24,
    seed: int = 20260814,
    turn: bool = False,
    speckle: bool = False,
    blur: float = 0.0,
    faintness: float = 0.0,
    smallest: float = 0.14,
    largest: float = 0.26,
    crowd: int = 4,
    stroke: float = 0.0,
    gap: int = 0,
    shadow: float = 0.0,
    glare: bool = False,
    smear: bool = False,
    framed: bool = False,
    notes: bool = False,
    writing: int = 0,
) -> List[Case]:
    """Draw a set of pictures with known answers.

    With no settings the shapes are upright and clean. ``turn`` turns every third
    picture's shapes, ``speckle`` dots every fourth picture with specks, ``blur``
    softens every edge, ``faintness`` from 0 to 1 pulls the shapes towards the
    background colour, and ``smallest``/``largest``/``crowd`` control how small
    and how many the shapes get. Each one makes the job harder in a different
    way, so a drop in the score says which way.

    ``stroke`` above zero draws each shape in outline, a marker's line that share
    of the picture's short side wide, and the rest are a whiteboard's troubles:
    ``gap`` leaves each outline open by that many pixels, ``shadow`` from 0 to 1
    darkens the picture from one side to the other, ``glare`` lays a soft bright
    patch over it, ``smear`` a few soft grey ones, ``notes`` draws a dimension
    line and some writing beside the shapes, which are not shapes, and
    ``framed`` stands the whole on a darker wall with a frame round it and a
    tray under it. ``writing`` draws that many lines of words beside the shapes,
    in the picture library's own letters, which a sorter of marks is scored on.
    """
    from PIL import Image, ImageChops, ImageDraw, ImageFilter

    dice = random.Random(seed)
    into.mkdir(parents=True, exist_ok=True)
    cases: List[Case] = []

    for index in range(count):
        width, height = dice.choice([(400, 300), (640, 480), (320, 320)])
        turned = turn and index % 3 == 1
        speckled = speckle and index % 4 == 3
        image = Image.new("L", (width, height), 245)
        pen = ImageDraw.Draw(image)

        ink = int(25 + faintness * 195)
        wanted = dice.randint(1, max(1, crowd))
        truth: List[TrueShape] = []
        taken: List[Tuple[float, float, float]] = []

        for _ in range(wanted):
            kind = dice.choice(DRAWABLE)
            span = dice.uniform(smallest, largest) * min(width, height)
            placed = _free_spot(dice, width, height, span, taken)
            if placed is None:
                continue
            cx, cy = placed
            taken.append((cx, cy, span))
            angle = dice.uniform(0, 90) if turned else 0.0
            line = max(2, round(stroke * min(width, height))) if stroke > 0 else 0
            _paint(pen, kind, cx, cy, span, angle, ink, line)
            if line and gap > 0:
                # The middle of the lower side is on every family's outline.
                gx, gy = _turn(0, span / 2, angle, cx, cy)
                reach = gap / 2 + line
                pen.rectangle((gx - gap / 2, gy - reach, gx + gap / 2, gy + reach), fill=245)
            truth.append(TrueShape(kind, (cx / width, cy / height), angle))

        if speckled:
            for _ in range(dice.randint(6, 14)):
                sx = dice.randint(0, width - 3)
                sy = dice.randint(0, height - 3)
                pen.rectangle((sx, sy, sx + 2, sy + 2), fill=min(255, ink + 15))

        written: List[Tuple[float, float]] = []
        for _ in range(writing):
            from PIL import ImageFont

            words = dice.choice(WORDS)
            tall = dice.uniform(0.045, 0.07) * min(width, height)
            letters = ImageFont.load_default(size=tall)
            left, top, right, bottom = pen.textbbox((0, 0), words, font=letters)
            span = max(right - left, bottom - top)
            placed = _free_spot(dice, width, height, span, taken)
            if placed is None:
                continue
            wx, wy = placed
            taken.append((wx, wy, span))
            pen.text(
                (wx - (right - left) / 2, wy - (bottom - top) / 2 - top),
                words,
                fill=ink,
                font=letters,
            )
            written.append((wx / width, wy / height))

        if notes:
            for _ in range(2):
                span = 0.2 * min(width, height)
                placed = _free_spot(dice, width, height, span, taken)
                if placed is None:
                    continue
                nx, ny = placed
                taken.append((nx, ny, span))
                pen.line((nx - span / 2, ny, nx + span / 2, ny), fill=ink, width=2)
                for tick in range(5):
                    tx = nx - span / 4 + tick * span / 8
                    pen.line((tx, ny + 6, tx + span / 12, ny + 14), fill=ink, width=2)

        if smear:
            smudges = Image.new("L", (width, height), 255)
            smudge = ImageDraw.Draw(smudges)
            for _ in range(4):
                sx, sy = dice.uniform(0, width), dice.uniform(0, height)
                reach = dice.uniform(0.08, 0.2) * min(width, height)
                smudge.ellipse((sx - reach, sy - reach / 2, sx + reach, sy + reach / 2), fill=205)
            image = ImageChops.multiply(image, smudges.filter(ImageFilter.GaussianBlur(8)))

        if glare:
            bright = Image.new("L", (width, height), 0)
            gx, gy = dice.uniform(0, width), dice.uniform(0, height)
            reach = 0.3 * min(width, height)
            ImageDraw.Draw(bright).ellipse(
                (gx - reach, gy - reach, gx + reach, gy + reach), fill=200
            )
            image = ImageChops.screen(image, bright.filter(ImageFilter.GaussianBlur(reach / 3)))

        if shadow > 0:
            ramp = Image.linear_gradient("L").rotate(90).resize((width, height))
            image = ImageChops.multiply(image, ramp.point(lambda v: round(255 - shadow * v)))

        if blur > 0:
            image = image.filter(ImageFilter.GaussianBlur(blur))

        if framed:
            edge = round(0.15 * min(width, height))
            wall = Image.new("L", (width + 2 * edge, height + 2 * edge), 60)
            wall.paste(image, (edge, edge))
            round_it = ImageDraw.Draw(wall)
            round_it.rectangle(
                (edge - 4, edge - 4, edge + width + 3, edge + height + 3), outline=150, width=4
            )
            round_it.rectangle(
                (edge + width // 4, edge + height + 4, edge + 3 * width // 4, edge + height + 12),
                fill=120,
            )
            truth = [
                TrueShape(
                    shape.kind,
                    (
                        (shape.centre[0] * width + edge) / wall.width,
                        (shape.centre[1] * height + edge) / wall.height,
                    ),
                    shape.turned_degrees,
                )
                for shape in truth
            ]
            written = [
                ((x * width + edge) / wall.width, (y * height + edge) / wall.height)
                for x, y in written
            ]
            image = wall

        path = into / f"case_{index:02d}.png"
        image.save(path)
        cases.append(Case(path.stem, path, truth, turned, speckled, written))

    return cases


def _free_spot(dice, width, height, span, taken):
    """Find a centre far enough from everything already drawn. Gives up quietly."""
    for _ in range(40):
        cx = dice.uniform(span, width - span)
        cy = dice.uniform(span, height - span)
        if all(math.dist((cx, cy), (ox, oy)) > (span + ospan) * 0.75 for ox, oy, ospan in taken):
            return cx, cy
    return None


def _paint(pen, kind: ShapeKind, cx, cy, span, angle, ink: int = 25, line: int = 0) -> None:
    """One shape, filled in, or in outline ``line`` pixels wide."""
    half = span / 2
    how = {"outline": ink, "width": line} if line else {"fill": ink}
    if kind is ShapeKind.DISC:
        # A circle looks the same however it is turned, so the angle is ignored.
        pen.ellipse((cx - half, cy - half, cx + half, cy + half), **how)
        return
    if kind is ShapeKind.RECT:
        corners = [(-half, -half), (half, -half), (half, half), (-half, half)]
    else:
        corners = [(0, -half), (half, half), (-half, half)]
    pen.polygon([_turn(x, y, angle, cx, cy) for x, y in corners], **how)


def _turn(x: float, y: float, angle: float, cx: float, cy: float) -> Tuple[float, float]:
    radians = math.radians(angle)
    cos, sin = math.cos(radians), math.sin(radians)
    return (cx + x * cos - y * sin, cy + x * sin + y * cos)


def score(finder: ShapeFinder, cases: List[Case], *, near: float = 0.12) -> Score:
    """Ask a finder about each picture and compare with what was drawn.

    A reported shape counts as matching a drawn one when their centres are within
    ``near`` of each other, measured as a fraction of the picture. Each drawn
    shape can be claimed once.
    """
    result = Score()
    for case in cases:
        result.cases += 1
        result.expected += len(case.truth)
        seen = finder.look(case.path)
        result.found += len(seen.shapes)

        unclaimed = list(seen.shapes)
        for truth in case.truth:
            best, best_gap = None, near
            for candidate in unclaimed:
                centre = candidate.centre
                gap = math.dist((centre.x, centre.y), truth.centre)
                if gap < best_gap:
                    best, best_gap = candidate, gap
            if best is None:
                result.wrong.append(f"{case.name}: missed a {truth.kind.value}")
                continue
            unclaimed.remove(best)
            result.matched += 1
            result.place_error.append(best_gap)
            if best.kind is truth.kind:
                result.right_kind += 1
                result.sure_when_right.append(best.confidence)
            else:
                result.sure_when_wrong.append(best.confidence)
                turn = f" turned {truth.turned_degrees:.0f}°" if truth.turned_degrees else ""
                result.wrong.append(
                    f"{case.name}: a {truth.kind.value}{turn} was called a {best.kind.value}"
                )
    return result


@dataclass
class Sorting:
    """How a sorter of marks did on one run of cases."""

    diagrams: int = 0
    writing: int = 0
    diagrams_right: int = 0
    writing_right: int = 0
    unsure: int = 0
    # Writing read as a diagram's makes a piece nobody drew; a diagram read as
    # writing loses one. Counted apart.
    writing_as_diagram: int = 0
    diagram_as_writing: int = 0
    missed: int = 0

    @property
    def right_rate(self) -> float:
        drawn = self.diagrams + self.writing
        return (self.diagrams_right + self.writing_right) / drawn if drawn else 1.0


def score_sorting(cases: List[Case], thresholds=None) -> Sorting:
    """Sort each picture's marks and compare with what was drawn: each drawn shape
    and each line of writing is looked for by its middle."""
    from . import marks as sorter
    from .outline import read_strokes

    result = Sorting()
    for case in cases:
        found = sorter.sort(read_strokes(case.path), thresholds)
        drawn = [("diagram", shape.centre) for shape in case.truth]
        drawn += [("writing", middle) for middle in case.writing]
        for kind, (x, y) in drawn:
            over = [
                mark
                for mark in found
                if mark.min_point.x <= x <= mark.max_point.x
                and mark.min_point.y <= y <= mark.max_point.y
            ]
            said = (
                min(over, key=lambda m: m.max_point.x - m.min_point.x).kind.value if over else None
            )
            if kind == "diagram":
                result.diagrams += 1
            else:
                result.writing += 1
            if said is None:
                result.missed += 1
            elif said == kind:
                if kind == "diagram":
                    result.diagrams_right += 1
                else:
                    result.writing_right += 1
            elif said == "unsure":
                result.unsure += 1
            elif kind == "writing":
                result.writing_as_diagram += 1
            else:
                result.diagram_as_writing += 1
    return result


def run_sorting(count: int = 20, thresholds=None, **drawing) -> Sorting:
    """Draw whiteboards with writing on them and score the sorter, in a scratch
    folder cleared away after."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="apothecary-bench-") as scratch:
        cases = draw_cases(Path(scratch), count=count, **{"stroke": 0.012, "writing": 2, **drawing})
        return score_sorting(cases, thresholds)


def run(
    finder: ShapeFinder,
    into: Optional[Path] = None,
    **drawing,
) -> Tuple[Score, List[Case]]:
    """Draw the cases and score one finder against them.

    Given nowhere to work, it uses a scratch folder and clears it away
    afterwards. Leaving hundreds of pictures behind on every run sits badly
    beside a promise to write only where you are pointed.
    """
    import shutil
    import tempfile

    if into is not None:
        cases = draw_cases(into, **drawing)
        return score(finder, cases), cases

    folder = Path(tempfile.mkdtemp(prefix="apothecary-bench-"))
    try:
        cases = draw_cases(folder, **drawing)
        return score(finder, cases), cases
    finally:
        shutil.rmtree(folder, ignore_errors=True)


__all__ = ["Case", "DRAWABLE", "Score", "TrueShape", "draw_cases", "run", "score"]
