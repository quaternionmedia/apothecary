# Apothecary Documentation

Welcome to the Apothecary documentation. This index links to all available guides.

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
