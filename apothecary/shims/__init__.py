"""Shims: thin adapters to artifacts apothecary does not author.

Each shim satisfies a protocol defined in `apothecary.models`, so the tool
behind it is replaceable without touching anything that consumes it. They are
deliberately small — a shim that grows logic is a shim that has started
authoring, which is the thing it exists to avoid.
"""

from .kicad import KiCadProvider, t1_core_stub

__all__ = ["KiCadProvider", "t1_core_stub"]
