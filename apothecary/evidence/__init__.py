"""A working space seen from every kind of evidence at once.

Each source says what it saw as observations in one format
(``observation``): a subject, a property, a value or why there is none, where
it came from and when, and the evidence it rests on, by reference. The log
keeps them in the state folder, one space a folder (``log``); collectors write
them, one per source -- a printer's polls first (``printers``) -- and the view
reads the log and nothing else (``view``), answering one document,
``apothecary.evidence``, that the page, the command line and carlos read.

The plan is docs/plans/working-space-view-2026-10-30.md.
"""

# An install point of the guard (apothecary/stays_local.py), before any module
# in this package runs: it keeps what a person's machines did and when.
from ..stays_local import install_guard as _install_guard

_install_guard()
