# apothecary-core

A Rust core inside Python, by [PyO3](https://pyo3.rs) and
[maturin](https://www.maturin.rs). **Not built yet**: the library exposes one
function, `version()`, and nothing else. It is a stub for
[the Rust plan](../../docs/plans/rust-2026-10-08.md) ("Planned and stubbed
only").

## Its future hot paths

Where Python's speed shows today, in the order the plan lists them:

- **Overlap checks** between placed pieces (the bounding-box and mesh
  overlaps a site is checked for).
- **The projection** of pieces and photographs onto a plane.
- **Outline geometry**: outlines of shapes, offsets, simplification.
- **The finder**: the pixel work of the shape finder, which today runs in
  Pillow and pure Python.

Nothing moves here until a profile says it should, and each path keeps its
Python implementation as the reference the Rust one is tested against.

## The wheel does not carry it

`pyproject.toml` builds the `apothecary` package with setuptools and is not
changed to build this crate; the wheel contains none of it. When it does
something, it becomes its own maturin project (a `pyproject.toml` of its own
under this folder), and what the wheel then does with it -- one wheel with an
optional core, or a second distribution -- is a decision for that day.

## Build

```bash
cargo check -p apothecary-core
```

The crate sets `abi3-py311`, matching `requires-python`, so one build serves
every Python from 3.11 on.
