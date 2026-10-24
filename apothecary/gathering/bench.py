"""Measuring whether the sorting is actually any good.

The same discipline as the finder's own meter: draw pictures whose answers are
already known, ask the sorter, and count. A rule that sounds sensible and has
never been scored is an opinion.

Scenes are laid out once in a made-up space, and then *photographed* — a camera
window is chosen inside the scene, so two pictures of one scene really do differ
by where the camera stood, how close it was, and how bright the light was, in
the way two real photographs of a workbench differ. What they share is the
object, which is the whole question.

Four things are counted, and the third matters most:

- **right** — the sorter said what was true.
- **declined** — the sorter said it could not tell. Not a success and not a
  failure. Declining is allowed; declining everything is useless, which is why
  it is counted separately rather than folded into either.
- **wrong** — the sorter said something untrue. Joining two unrelated
  photographs into one object is the worst thing this code can do, so this
  number is the one to watch.
- **unreadable** — a picture nothing could be read from at all.

What this does not measure: real photographs. Everything here is clean drawing,
so a good score means "handles the easy case". Shadow, texture, blur, occlusion
and clutter are all absent. That is the honest reading of any number below.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from ..vision.finder import ShapeFinder
from ..vision.models import ShapeKind
from .models import CANNOT_TELL, PARTS_OF_ONE, SAME_THING, UNRELATED
from .resolve import gather

DRAWABLE = (ShapeKind.RECT, ShapeKind.DISC, ShapeKind.TRI)

# The camera's picture is four across for every three down, and every window
# cut out of a scene has the same shape. A window of a different shape would
# stretch everything in it, and proportion is what the sorting runs on.
WIDE, TALL = 480, 360
WINDOW_TALL = 1.0
WINDOW_WIDE = WINDOW_TALL * WIDE / TALL


@dataclass
class Blob:
    """One shape sitting in a made-up scene."""

    kind: ShapeKind
    x: float
    y: float
    span: float
    turned: float = 0.0


@dataclass
class Occasion:
    """One set of pictures handed in together, and the answers for every pair."""

    name: str
    paths: List[Path]
    names: List[str]
    truth: Dict[Tuple[str, str], str] = field(default_factory=dict)


@dataclass
class Score:
    """What the sorting managed across a set of occasions."""

    right: int = 0
    declined: int = 0
    wrong: int = 0
    unreadable: int = 0
    pictures: int = 0
    joined_wrongly: int = 0
    groups_clean: int = 0
    groups_mixed: int = 0
    groups_possible: int = 0
    mistakes: List[str] = field(default_factory=list)

    @property
    def judged(self) -> int:
        return self.right + self.declined + self.wrong

    @property
    def right_rate(self) -> float:
        return self.right / self.judged if self.judged else 0.0

    @property
    def wrong_rate(self) -> float:
        return self.wrong / self.judged if self.judged else 0.0

    @property
    def declined_rate(self) -> float:
        return self.declined / self.judged if self.judged else 0.0

    @property
    def joined_wrongly_rate(self) -> float:
        """How often two unrelated pictures were made into one thing.

        The one number that has to be nothing. Every other mistake here costs a
        person a moment of confusion; this one silently builds an object out of
        two things that were never together, and nothing downstream can tell.
        """
        return self.joined_wrongly / self.judged if self.judged else 0.0

    @property
    def found_rate(self) -> float:
        """How many of the groups that were there were actually found."""
        return self.groups_clean / self.groups_possible if self.groups_possible else 0.0

    def summary(self) -> str:
        groups = (
            f" Groups: {self.groups_clean} clean, {self.groups_mixed} mixed, "
            f"out of {self.groups_possible} there to find "
            f"({self.found_rate:.0%})."
            if self.groups_possible
            else ""
        )
        return (
            f"{self.judged} pair(s): {self.right_rate:.0%} right, "
            f"{self.declined_rate:.0%} declined, {self.wrong_rate:.0%} wrong. "
            f"{self.unreadable} of {self.pictures} picture(s) could not be read. "
            f"{self.joined_wrongly} unrelated pair(s) were wrongly joined." + groups
        )


def _paint(pen, blob: Blob, window: Tuple[float, float, float, float], ink: int) -> None:
    """Draw one shape as the camera sees it, or not at all if it is outside."""
    x0, y0, x1, y1 = window
    across = WIDE / (x1 - x0)
    down = TALL / (y1 - y0)
    cx = (blob.x - x0) * across
    cy = (blob.y - y0) * down
    half = blob.span * across / 2
    if cx + half < 0 or cx - half > WIDE or cy + half < 0 or cy - half > TALL:
        return
    if blob.kind is ShapeKind.DISC:
        pen.ellipse((cx - half, cy - half, cx + half, cy + half), fill=ink)
        return
    if blob.kind is ShapeKind.RECT:
        corners = [(-half, -half), (half, -half), (half, half), (-half, half)]
    else:
        corners = [(0, -half), (half, half), (-half, half)]
    radians = math.radians(blob.turned)
    cos, sin = math.cos(radians), math.sin(radians)
    pen.polygon([(cx + x * cos - y * sin, cy + x * sin + y * cos) for x, y in corners], fill=ink)


def _photograph(
    scene: Sequence[Blob], window: Tuple[float, float, float, float], into: Path, *, light: int
) -> Path:
    from PIL import Image, ImageDraw

    paper = min(250, 210 + light)
    ink = max(10, 40 - light)
    image = Image.new("L", (WIDE, TALL), paper)
    pen = ImageDraw.Draw(image)
    for blob in scene:
        _paint(pen, blob, window, ink)
    image.save(into)
    return into


def _scene(dice: random.Random, *, spread: float, count: int) -> List[Blob]:
    """Lay out a scene across a strip of made-up space."""
    blobs: List[Blob] = []
    for _ in range(count):
        for _try in range(40):
            span = dice.uniform(0.16, 0.30)
            x = dice.uniform(span, spread - span)
            y = dice.uniform(span, WINDOW_TALL - span)
            if all(math.dist((x, y), (b.x, b.y)) > (span + b.span) * 0.8 for b in blobs):
                blobs.append(Blob(dice.choice(DRAWABLE), x, y, span, dice.choice([0.0, 0.0, 25.0])))
                break
    return blobs


def draw_occasions(into: Path, *, seed: int = 20260820, each: int = 3) -> List[Occasion]:
    """Draw ``each`` occasions of every kind, with the answers written down."""
    dice = random.Random(seed)
    into.mkdir(parents=True, exist_ok=True)
    occasions: List[Occasion] = []

    for round_number in range(each):
        # --- two photographs of one thing, camera moved and light changed ---
        scene = _scene(dice, spread=WINDOW_WIDE, count=4)
        left = (0.0, 0.0, WINDOW_WIDE, WINDOW_TALL)
        shift = 0.06
        right = (shift, shift * 0.4, WINDOW_WIDE + shift, WINDOW_TALL + shift * 0.4)
        a = _photograph(scene, left, into / f"same{round_number}_a.png", light=0)
        b = _photograph(scene, right, into / f"same{round_number}_b.png", light=14)
        occasions.append(
            Occasion(
                f"same{round_number}",
                [a, b],
                [a.stem, b.stem],
                {tuple(sorted((a.stem, b.stem))): SAME_THING},  # type: ignore[dict-item]
            )
        )

        # --- one thing photographed whole and then close up -----------------
        scene = _scene(dice, spread=WINDOW_WIDE, count=5)
        whole = (0.0, 0.0, WINDOW_WIDE, WINDOW_TALL)
        near_wide = WINDOW_WIDE * 0.55
        near_tall = WINDOW_TALL * 0.55
        near = (
            WINDOW_WIDE / 2 - near_wide / 2,
            WINDOW_TALL / 2 - near_tall / 2,
            WINDOW_WIDE / 2 + near_wide / 2,
            WINDOW_TALL / 2 + near_tall / 2,
        )
        a = _photograph(scene, whole, into / f"close{round_number}_whole.png", light=0)
        b = _photograph(scene, near, into / f"close{round_number}_near.png", light=8)
        occasions.append(
            Occasion(
                f"close{round_number}",
                [a, b],
                [a.stem, b.stem],
                {tuple(sorted((a.stem, b.stem))): SAME_THING},  # type: ignore[dict-item]
            )
        )

        # --- two neighbouring parts of one larger thing ---------------------
        # The two windows have to genuinely share several shapes. An earlier
        # version overlapped by so little that typically one shape was in both,
        # and one shared shape is not evidence of anything — the sorter said so,
        # and it was right; the drawing was wrong.
        spread = WINDOW_WIDE * 1.6
        scene = _scene(dice, spread=spread, count=11)
        step = spread - WINDOW_WIDE
        one = (0.0, 0.0, WINDOW_WIDE, WINDOW_TALL)
        two = (step, 0.0, step + WINDOW_WIDE, WINDOW_TALL)
        a = _photograph(scene, one, into / f"parts{round_number}_left.png", light=0)
        b = _photograph(scene, two, into / f"parts{round_number}_right.png", light=4)
        occasions.append(
            Occasion(
                f"parts{round_number}",
                [a, b],
                [a.stem, b.stem],
                {tuple(sorted((a.stem, b.stem))): PARTS_OF_ONE},  # type: ignore[dict-item]
            )
        )

        # --- two photographs of nothing to do with each other ---------------
        first = _scene(dice, spread=WINDOW_WIDE, count=4)
        second = _scene(dice, spread=WINDOW_WIDE, count=4)
        window = (0.0, 0.0, WINDOW_WIDE, WINDOW_TALL)
        a = _photograph(first, window, into / f"apart{round_number}_a.png", light=0)
        b = _photograph(second, window, into / f"apart{round_number}_b.png", light=20)
        occasions.append(
            Occasion(
                f"apart{round_number}",
                [a, b],
                [a.stem, b.stem],
                {tuple(sorted((a.stem, b.stem))): UNRELATED},  # type: ignore[dict-item]
            )
        )

    # --- one picture with nothing in it, handed in alongside two others ----
    scene = _scene(dice, spread=WINDOW_WIDE, count=3)
    window = (0.0, 0.0, WINDOW_WIDE, WINDOW_TALL)
    a = _photograph(scene, window, into / "blankset_a.png", light=0)
    b = _photograph(scene, window, into / "blankset_b.png", light=10)
    blank = _photograph([], window, into / "blankset_empty.png", light=0)
    occasions.append(
        Occasion(
            "blankset",
            [a, b, blank],
            [a.stem, b.stem, blank.stem],
            {tuple(sorted((a.stem, b.stem))): SAME_THING},  # type: ignore[dict-item]
        )
    )
    return occasions


def score(finder: ShapeFinder, occasions: Sequence[Occasion]) -> Score:
    """Sort each occasion and compare every verdict with what was drawn."""
    tally = Score()
    for occasion in occasions:
        pictures = [finder.look(path) for path in occasion.paths]
        tally.pictures += len(pictures)
        result = gather(pictures, paths=occasion.paths)
        tally.unreadable += len(result.readings) - len(result.readable())
        for pair, truth in occasion.truth.items():
            said = result.between(*pair)
            if said is None:
                tally.unreadable += 0
                tally.declined += 1
                tally.mistakes.append(
                    f"{occasion.name}: {pair[0]} + {pair[1]} were never compared "
                    "(one of them could not be read)"
                )
                continue
            if said.verdict == truth:
                tally.right += 1
            elif said.verdict == CANNOT_TELL:
                tally.declined += 1
            else:
                tally.wrong += 1
                if truth == UNRELATED and said.verdict in (SAME_THING, PARTS_OF_ONE):
                    tally.joined_wrongly += 1
                tally.mistakes.append(
                    f"{occasion.name}: {pair[0]} + {pair[1]} are {truth} "
                    f"but were called {said.verdict} — {'; '.join(said.because)}"
                )
    return tally


def score_together(finder: ShapeFinder, occasions: Sequence[Occasion]) -> Score:
    """Hand every picture in at once and score every pair, including across sets.

    This exists because scoring occasion by occasion missed the worst failure
    this code has had. Pair by pair everything looked reasonable; handed a whole
    folder, weak seams chained twelve unrelated photographs into one object.
    Nothing in a pairwise score can see that, because the pairs that did the
    damage were never in the same occasion and so were never compared.

    Every pair from two different occasions is known to be unrelated. Anything
    else is a mistake, and here it is counted as one.
    """
    tally = Score()
    everything: List[Path] = [path for occasion in occasions for path in occasion.paths]
    belongs: Dict[str, str] = {
        path.stem: occasion.name for occasion in occasions for path in occasion.paths
    }
    pictures = [finder.look(path) for path in everything]
    tally.pictures = len(pictures)
    result = gather(pictures, paths=everything)
    tally.unreadable = len(result.readings) - len(result.readable())

    truth: Dict[Tuple[str, str], str] = {}
    for occasion in occasions:
        truth.update(occasion.truth)

    for said in result.kinships:
        pair = said.key
        wanted = truth.get(pair)
        if wanted is None:
            if belongs[said.left] == belongs[said.right]:
                # Same occasion, but no answer was written down for this pair.
                continue
            wanted = UNRELATED
        if said.verdict == wanted:
            tally.right += 1
        elif said.verdict == CANNOT_TELL:
            tally.declined += 1
        else:
            tally.wrong += 1
            if wanted == UNRELATED and said.verdict in (SAME_THING, PARTS_OF_ONE):
                tally.joined_wrongly += 1
            tally.mistakes.append(
                f"{said.left} + {said.right} are {wanted} but were called "
                f"{said.verdict} — {'; '.join(said.because)}"
            )

    # Pairs are not what a person sees. Groups are. A run can look respectable
    # pair by pair and still hand back one group made of five unconnected
    # photographs, so the groups are scored on their own terms.
    tally.groups_possible = sum(1 for occasion in occasions if len(occasion.paths) > 1)
    for cluster in result.clusters:
        if len(cluster.pictures) < 2:
            continue
        homes = {belongs[picture] for picture in cluster.pictures}
        if len(homes) == 1:
            tally.groups_clean += 1
        else:
            tally.groups_mixed += 1
            tally.mistakes.append(
                f"the group {cluster.name!r} mixes pictures from "
                f"{len(homes)} different occasions: {', '.join(sorted(cluster.pictures))}"
            )
    return tally


def run(
    finder: ShapeFinder,
    *,
    into: Optional[Path] = None,
    each: int = 3,
    seed: int = 20260820,
    together: bool = False,
) -> Score:
    """Draw, sort and score, cleaning up after itself unless told where to draw.

    ``together`` hands every picture in at once instead of one occasion at a
    time. Harder, more realistic, and the only way to see a group that grew
    across sets that should never have met.
    """
    import shutil
    import tempfile

    temporary = into is None
    where = Path(tempfile.mkdtemp(prefix="apothecary-gathering-")) if temporary else into
    try:
        drawn = draw_occasions(where, seed=seed, each=each)
        return score_together(finder, drawn) if together else score(finder, drawn)
    finally:
        if temporary:
            shutil.rmtree(where, ignore_errors=True)


__all__ = [
    "Blob",
    "Occasion",
    "Score",
    "draw_occasions",
    "run",
    "score",
    "score_together",
]
