"""Taking in many pictures at once, and working out which are of the same thing.

One picture at a time is the easy case and it is already built. The real case is
a handful of pictures taken at different moments, from different distances, in
different light — some of the same object, some of neighbouring parts of one
larger thing, and some of nothing in particular.

This works out which is which, says how sure it is about each answer, and
**refuses rather than guessing** when the answers contradict each other.

PROTOTYPE — not ratified. See ``docs/plans/features/gathering.md``.
"""

from .combine import combine, whole_gathering
from .models import (
    ALONE,
    CANNOT_TELL,
    PARTS_OF_ONE,
    SAME_THING,
    UNRELATED,
    VERDICTS,
    Cluster,
    Gathering,
    Kinship,
    Reading,
    ShapeMark,
    Signature,
)
from .report import as_text
from .resolve import gather, kinship_between, read_one
from .signature import signature_of

__all__ = [
    "ALONE",
    "CANNOT_TELL",
    "Cluster",
    "Gathering",
    "Kinship",
    "PARTS_OF_ONE",
    "Reading",
    "SAME_THING",
    "Signature",
    "ShapeMark",
    "UNRELATED",
    "VERDICTS",
    "as_text",
    "combine",
    "gather",
    "kinship_between",
    "read_one",
    "signature_of",
    "whole_gathering",
]
