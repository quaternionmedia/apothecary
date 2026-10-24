"""Choosing a word for a found shape.

A plain table, read top to bottom, first match wins. Deliberately not clever:
the rule is legible, arguing with it is easy, and changing it is one line. When
this stops being good enough the answer is a written decision about fitting
shapes properly, not a cleverer table — see
``docs/plans/features/word-parameters.md``.

PROTOTYPE — not ratified.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, NamedTuple, Optional

from ..vision.models import ShapeKind

if TYPE_CHECKING:  # pragma: no cover - for readers and type checkers only
    from ..vision.models import FoundShape


class Rule(NamedTuple):
    """One row of the table."""

    kind: ShapeKind
    word: str
    reason: str
    tall: Optional[bool] = None
    thin: Optional[bool] = None


# A shape counts as tall when it is much taller than it is wide, and thin when
# it is much wider than it is tall. Same number both ways, so the table stays
# symmetric and there is one thing to argue about rather than two.
STRETCH = 2.5

TABLE: List[Rule] = [
    Rule(ShapeKind.DISC, "post", "a circle much taller than wide reads as an upright", tall=True),
    Rule(ShapeKind.DISC, "disc", "any other circle reads as a flat round piece"),
    Rule(ShapeKind.RECT, "slot", "a very long thin rectangle reads as a channel", thin=True),
    Rule(ShapeKind.RECT, "plate", "any other rectangle reads as a flat slab"),
    Rule(ShapeKind.TRI, "wedge", "a triangle reads as a tapering block"),
    Rule(ShapeKind.LINE, "slot", "a line reads as a channel"),
    Rule(ShapeKind.POLY, "plate", "anything unrecognised falls back to a flat slab"),
]


class Choice(NamedTuple):
    """Which word was chosen, and why."""

    word: str
    reason: str


def word_for(shape: "FoundShape") -> Choice:
    """Pick a word for one found shape. Always returns something."""
    tall = shape.aspect > 0 and shape.aspect < 1 / STRETCH
    thin = shape.aspect > STRETCH
    for rule in TABLE:
        if rule.kind is not shape.kind:
            continue
        if rule.tall is not None and rule.tall != tall:
            continue
        if rule.thin is not None and rule.thin != thin:
            continue
        return Choice(rule.word, rule.reason)
    return Choice("plate", "no rule matched, so the fallback applied")


__all__ = ["Choice", "Rule", "STRETCH", "TABLE", "word_for"]
