"""A toolpath, previewed: one core for a print and for a cut.

``moves`` reads G-code, ``process`` says what a move means for each way of making a
part, ``core`` builds what the page draws. See ``docs/toolpath-preview.md``.
"""

from .core import Box, Group, Preview, of, reach
from .process import ADDITIVE, BY_MACHINE, SUBTRACTIVE, Process, for_machine

__all__ = [
    "ADDITIVE",
    "BY_MACHINE",
    "SUBTRACTIVE",
    "Box",
    "Group",
    "Preview",
    "Process",
    "for_machine",
    "of",
    "reach",
]
