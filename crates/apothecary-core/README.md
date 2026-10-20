# apothecary-core

A Rust core inside Python, by [PyO3](https://pyo3.rs) and
[maturin](https://www.maturin.rs). It is a stub: the library exposes one
function, `version()`, and nothing else (`src/lib.rs`).

## The hot paths it is for

Where Python's speed shows:

- **Overlap checks** between placed pieces (the bounding-box and mesh
  overlaps a site is checked for).
- **The projection** of pieces and photographs onto a plane.
- **Outline geometry**: outlines of shapes, offsets, simplification.
- **The finder**: the pixel work of the shape finder, which runs in Pillow
  and pure Python.

Nothing moves here until a profile says it should, and each path keeps its
Python implementation as the reference the Rust one is tested against.

## The wheel does not carry it

`pyproject.toml` builds the `apothecary` package alone, with setuptools; the
wheel contains none of this crate. A core that does something is its own
maturin project (a `pyproject.toml` of its own under this folder); whether the
wheel then carries it as an optional core or as a second distribution is
undecided.

## Build

```bash
cargo check -p apothecary-core
```

The crate sets `abi3-py311`, matching `requires-python`, so one build serves
every Python from 3.11 on.
