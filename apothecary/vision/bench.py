"""Measuring how well a finder actually does.

The rulebook says a claim to be checked has to name its checker, and that a
number in a document must have been measured rather than asserted. This is the
meter for "the plain finder works well enough".

It draws pictures whose answers are known — varying position, size, rotation,
speckle and how many shapes are present — then asks a finder what it sees and
scores the reply. Everything is drawn from a fixed starting number, so the same
run gives the same score on any machine, and a change to the finder shows up as
a change to the number rather than as an argument.

What it does not measure: real photographs. Everything here is clean synthetic
drawing, so a good score means "handles the easy case", not "works". A real
photograph brings shadow, texture, blur and overlap, none of which appear below.
That limit is the honest reading of any number this produces.

Runs on your own machine with nothing fetched. See
``docs/plans/proposals/runs-and-stays-local.md``.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from .finder import ShapeFinder
from .models import ShapeKind

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
    turn: bool = True,
    speckle: bool = True,
    blur: float = 0.0,
    faintness: float = 0.0,
    smallest: float = 0.14,
    largest: float = 0.26,
    crowd: int = 4,
) -> List[Case]:
    """Draw a set of pictures with known answers.

    ``blur`` softens every edge, ``faintness`` from 0 to 1 pulls the shapes
    towards the background colour, and ``smallest``/``largest``/``crowd`` control
    how small and how many the shapes get. Each one makes the job harder in a
    different way, so a drop in the score says which way.
    """
    from PIL import Image, ImageDraw, ImageFilter

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
            _paint(pen, kind, cx, cy, span, angle, ink)
            truth.append(TrueShape(kind, (cx / width, cy / height), angle))

        if speckled:
            for _ in range(dice.randint(6, 14)):
                sx = dice.randint(0, width - 3)
                sy = dice.randint(0, height - 3)
                pen.rectangle((sx, sy, sx + 2, sy + 2), fill=min(255, ink + 15))

        if blur > 0:
            image = image.filter(ImageFilter.GaussianBlur(blur))

        path = into / f"case_{index:02d}.png"
        image.save(path)
        cases.append(Case(path.stem, path, truth, turned, speckled))

    return cases


def _free_spot(dice, width, height, span, taken):
    """Find a centre far enough from everything already drawn. Gives up quietly."""
    for _ in range(40):
        cx = dice.uniform(span, width - span)
        cy = dice.uniform(span, height - span)
        if all(math.dist((cx, cy), (ox, oy)) > (span + ospan) * 0.75 for ox, oy, ospan in taken):
            return cx, cy
    return None


def _paint(pen, kind: ShapeKind, cx, cy, span, angle, ink: int = 25) -> None:
    half = span / 2
    if kind is ShapeKind.DISC:
        # A circle looks the same however it is turned, so the angle is ignored.
        pen.ellipse((cx - half, cy - half, cx + half, cy + half), fill=ink)
        return
    if kind is ShapeKind.RECT:
        corners = [(-half, -half), (half, -half), (half, half), (-half, half)]
    else:
        corners = [(0, -half), (half, half), (-half, half)]
    pen.polygon([_turn(x, y, angle, cx, cy) for x, y in corners], fill=ink)


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
