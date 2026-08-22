# Apothecary Documentation

Welcome to the Apothecary documentation. This index links to all available guides.

## The walkthrough

`walkthrough/` is the executable path through this repository: four pages, run
by `pytest walkthrough`. Start there.

| Page | |
|---|---|
| [01 — The parts registry](../walkthrough/01-a-part.md) | What a part is, and how its envelope is checked |
| [02 — Which numbers are whose](../walkthrough/02-fitting.md) | The seam, and driving it with overrides |
| [03 — Navigating a sub-assembly](../walkthrough/03-an-assembly.md) | datum_core as an addressable tree |
| [04 — Serving it](../walkthrough/04-serving-it.md) | The API and the viewer |
| [05 — Contested numbers](../walkthrough/05-contested-numbers.md) | Numbers the sources disagree about, and the dashboard for turning them |
| [06 — Ready to build](../walkthrough/06-ready-to-build.md) | Whether a part can be printed and checked against a real one |
| [07 — Status and progress](../walkthrough/07-status-and-progress.md) | One vocabulary for how the CLI reports state |
| [08 — Problems and solutions](../walkthrough/08-problems-and-solutions.md) | What is unresolved, who can close it, and what exists to close it with |

## Getting Started

| Document | Description |
|----------|-------------|
| [QUICKSTART.md](../QUICKSTART.md) | Get running in 5 minutes |
| [Tutorial](tutorial.md) | Build your first part (calibration cube) |
| [README.md](../README.md) | Project overview and CLI reference |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Development setup and contribution guidelines |

## Core Concepts

| Document | Description |
|----------|-------------|
| [Scene JSON Format](scene-json.md) | JSON schema for scenes, primitives, booleans, and transforms |
| [Parts Authoring](parts-authoring.md) | How to create and register new parts |
| [Iterating a Part](iterating-a-part.md) | Parameter overrides, the render loop, and checking bounds against geometry |
| [Fitting a Part](fitting-a-part.md) | The seam standard: which numbers belong to a consumer and which to this repository |
| [Boundaries](boundaries.md) | Which repository owns what between datum and apothecary, and what happens at the crossing |
| [Geometry Models](models.md) | Vectors, bounds, colors, shapes, and units |

## External Libraries

| Document | Description |
|----------|-------------|
| [Gridfinity](../parts/gridfinity/README.md) | Modular storage bin system (requires submodule) |

## Reference

| Document | Description |
|----------|-------------|
| [Templates README](../templates/README.md) | Using Jinja2 templates for code generation |
| [Parts README](../parts/README.md) | Raw SCAD files and naming conventions |
| [E2E Testing](../tests/e2e/README.md) | Running Playwright end-to-end tests |

## Generated Documentation (screenshots, GIFs, walkthroughs)

The fractal zoom viewer is documented by its own Playwright E2E test, not by
hand-maintained prose: each `docs.step("...")` call in
`tests/e2e/test_docs_fractal_viewer.py` is both a checked assertion point and
a sentence of documentation. Editing that test is how you edit these docs.

```bash
apothecary docs generate   # runs the doc-workflow tests, writes docs/generated/
apothecary docs clean      # removes it
```

`docs/generated/` (Markdown + step-by-step screenshots + an assembled GIF
+ the real Playwright screen recording, per workflow) is gitignored, not
committed — a build artifact, the same way STLs are. Run the command above
to produce it locally; there is nothing to browse on GitHub until you do.
The GIF (hand-assembled from the same step screenshots) is the deliverable
meant for embedding somewhere real video won't play, e.g. a PR description;
the `.webm` alongside it in each workflow's Markdown is the unedited
recording of that same test run. The intermediate per-test recordings this
is extracted from (`docs/generated/_videos_raw/`) are discarded afterward
(`--keep-raw-video` to keep them).

A normal test run (`apothecary test all`, CI) exercises the same test as
ordinary E2E coverage of the fractal zoom viewer — capture only turns on
with the explicit `--generate-docs` flag.

## API Documentation

When running the server (`apothecary serve`):

- **Interactive docs**: http://127.0.0.1:8000/docs (Swagger UI)
- **OpenAPI schema**: http://127.0.0.1:8000/openapi.json

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI (click)                          │
│   apothecary render | parts | serve | test | inventory      │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                     FastAPI Server                          │
│   /render | /parts | /viewer | /openscad/status | /health   │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                      Core Library                           │
├─────────────┬─────────────┬─────────────┬───────────────────┤
│ Primitives  │  Booleans   │ Transforms  │      Scene        │
│ Cube        │  Union      │ Translate   │  render()         │
│ Sphere      │  Difference │ Rotate      │  render_jscad()   │
│ Cylinder    │ Intersection│ Scale       │                   │
└─────────────┴─────────────┴─────────────┴───────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    Geometry Models                          │
├─────────────┬─────────────┬─────────────┬───────────────────┤
│  Vectors    │   Bounds    │   Colors    │    Shapes/Units   │
│ Vector2D/3D │BoundingBox3D│   Color     │ Polygon2D, Length │
└─────────────┴─────────────┴─────────────┴───────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    Parts System                             │
│   Registry → BasePart → PartFiles → STL Renderer            │
│                ↓              ↓            ↓                │
│         BoundingBox3D     Color      OpenSCAD CLI           │
└─────────────────────────────────────────────────────────────┘
```

## Quick Links

- **Source**: [apothecary/](../apothecary/)
- **Tests**: [tests/](../tests/)
- **Examples**: [examples/](../examples/)
- **Changelog**: [CHANGELOG.md](../CHANGELOG.md)

## Document Conventions

- Code blocks use `bash` for shell commands, `python` for Python code
- File paths are relative to repository root unless otherwise noted
- Commands assume `uv run` prefix (or activated virtualenv)
