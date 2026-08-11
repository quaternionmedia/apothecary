"""Assemblies: parts placed together, with their integration stubs named.

A part renders geometry. An assembly answers "and then what" -- what it sits
on, what it carries, and which of those is still a guess. Every assembly can
report its own stubs, so a review starts from what nobody has measured.
"""

from .datum_bench import Assembly, Placement, build, write

__all__ = ["Assembly", "Placement", "build", "write"]
