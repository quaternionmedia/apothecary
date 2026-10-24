"""How well the plain finder actually does, measured rather than asserted.

The floors below were read off a real run and written down. They are deliberately
a little under what was measured, so ordinary wobble does not turn the suite red,
but a real slip does. If one of these fails, the finder got worse — go and look,
do not lower the number.

Marked slow: these draw and examine hundreds of pictures. Run the whole file
before claiming a change to the finder is an improvement.

The measured numbers, and their honest reading, are in
``docs/plans/features/finder-accuracy.md``.
"""

from __future__ import annotations

import pytest

from apothecary.vision import PlainFinder
from apothecary.vision.bench import run

pytestmark = pytest.mark.slow


# condition, drawing settings, least acceptable found rate, least acceptable naming
CONDITIONS = [
    ("clear shapes", {}, 1.00, 1.00),
    ("turned and speckled", dict(turn=True, speckle=True), 1.00, 1.00),
    ("softly blurred", dict(blur=2.0), 1.00, 0.95),
    ("heavily blurred", dict(blur=5.0), 0.95, 0.60),
    ("faint against the background", dict(faintness=0.85), 1.00, 0.95),
    ("small", dict(smallest=0.05, largest=0.10), 0.95, 0.60),
    ("very small", dict(smallest=0.03, largest=0.06), 0.90, 0.25),
    ("crowded", dict(crowd=8, smallest=0.08, largest=0.14), 0.95, 0.90),
]


@pytest.mark.parametrize("label, drawing, least_found, least_named", CONDITIONS)
def test_the_finder_holds_its_measured_floor(label, drawing, least_found, least_named):
    result, _ = run(PlainFinder(), count=20, **drawing)
    assert result.found_rate >= least_found, f"{label}: {result.summary()}"
    assert result.kind_rate >= least_named, f"{label}: {result.summary()}"


def test_speckle_is_never_reported_as_a_shape():
    """Nothing invented. A found shape that was never drawn is worse than a miss."""
    result, _ = run(PlainFinder(), count=20, turn=True, speckle=True)
    assert result.spurious == 0, result.wrong


def test_shapes_are_placed_where_they_actually_are():
    result, _ = run(PlainFinder(), count=20)
    assert result.typical_place_error < 0.01, result.summary()


@pytest.mark.parametrize(
    "label, drawing",
    [
        ("heavily blurred", dict(blur=5.0)),
        ("small", dict(smallest=0.05, largest=0.10)),
        ("very small", dict(smallest=0.03, largest=0.06)),
    ],
)
def test_when_it_is_wrong_it_says_it_is_less_sure(label, drawing):
    """The property that makes a wrong answer survivable.

    Naming a small or blurred shape is unreliable and always will be. What must
    not happen is reporting an unreliable guess at the same confidence as a clear
    one, because everything downstream reads that number.
    """
    result, _ = run(PlainFinder(), count=20, **drawing)
    gap = result.honest
    assert gap is not None, f"{label}: never got one wrong, so nothing to compare"
    assert gap > 0.05, f"{label}: only {gap:+.2f} less sure when wrong"


def test_the_same_pictures_give_the_same_score_twice():
    """A score that wanders is not a measurement."""
    first, _ = run(PlainFinder(), count=12, blur=1.0)
    second, _ = run(PlainFinder(), count=12, blur=1.0)
    assert (first.found_rate, first.kind_rate) == (second.found_rate, second.kind_rate)


def test_a_finder_that_reports_nothing_scores_zero():
    """The harness must be able to fail something, or it measures nothing."""
    from pathlib import Path

    from apothecary.vision.bench import draw_cases, score
    from apothecary.vision.models import Picture

    class SeesNothing:
        def name(self) -> str:
            return "blind"

        def look(self, image: Path) -> Picture:
            return Picture(name=image.stem, pixel_width=10, pixel_height=10, finder="blind")

    import tempfile

    cases = draw_cases(Path(tempfile.mkdtemp()), count=6)
    assert score(SeesNothing(), cases).found_rate == 0.0


def test_a_finder_that_reports_rubbish_everywhere_is_caught_as_spurious():
    """Flooding the picture with guesses must not look like success."""
    from pathlib import Path

    from apothecary.models.vectors import Vector2D
    from apothecary.vision.bench import draw_cases, score
    from apothecary.vision.models import FoundShape, Picture, ShapeKind

    class GuessesEverywhere:
        def name(self) -> str:
            return "noisy"

        def look(self, image: Path) -> Picture:
            grid = [
                FoundShape(
                    kind=ShapeKind.RECT,
                    min_point=Vector2D(x=x / 10, y=y / 10),
                    max_point=Vector2D(x=x / 10 + 0.05, y=y / 10 + 0.05),
                )
                for x in range(10)
                for y in range(10)
            ]
            return Picture(
                name=image.stem, pixel_width=10, pixel_height=10, shapes=grid, finder="noisy"
            )

    import tempfile

    cases = draw_cases(Path(tempfile.mkdtemp()), count=6)
    result = score(GuessesEverywhere(), cases)
    assert result.spurious > 50, "carpeting the picture in guesses went unnoticed"
