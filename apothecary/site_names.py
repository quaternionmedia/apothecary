"""The names sites go by, for what is kept under one.

A pin, a camera's record, a job, a procedure and a day of evidence are each kept
under the name of the site they belong to, and read for the site of that name.

This module imports nothing, so the firmware package and the evidence log can
read it without reaching into the site layer.
"""

from __future__ import annotations

# The universe: every registered part a leaf of it, and every other site one piece.
UNIVERSE = "apothecary"
# What the page calls it.
UNIVERSE_SHOWN = "Apothecary"
