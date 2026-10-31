"""Finders and readers behind a model, kept apart from ``apothecary/vision/``.

``qmcp`` is the client: image models answer through qmcp alone, only when a
person asks, and what comes back is observations. ``simulated`` is a qmcp that
answers in process, for the demo and the tests. ``switches`` turns an origin
off, and ``kept`` holds what was asked and said, in memory.

The plan is ``docs/plans/image-models-through-qmcp-2026-10-30.md``.

A prototype: no ratified record governs it.
"""
