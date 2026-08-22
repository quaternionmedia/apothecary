# 🧪 Apothecary

OpenSCAD generation toolkit + curated printable parts.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Apothecary** composes OpenSCAD code from Python using Pydantic models. It provides a CLI, REST API, and web viewer for building and exploring 3D printable parts.

<!-- Screenshot placeholder - replace with actual screenshot -->
<p align="center">
  <img src="docs/screenshot.png" alt="Apothecary Viewer" width="800">
  <br>
  <em>Interactive 3D parts browser with STL preview</em>
</p>

## ✨ Features

- **Pydantic-based primitives** – Type-safe `Cube`, `Sphere`, `Cylinder`, boolean ops, and transforms
- **Scene composition** – Build complex models by combining simple objects
- **CLI & API** – Render scenes from JSON, serve via FastAPI, explore interactively
- **Parts library** – Curated printable parts with metadata, parameters, and STL generation
- **Web viewer** – Three.js-powered 3D browser with real STL rendering
- **Elephant walk** – Preview all parts arranged in a single view
- **STL generation** – Automatic OpenSCAD → STL conversion via API
- **JSCAD export** – Generate JavaScript modules for OpenJSCAD

## 🚀 Quick Start

```bash
# Install
git clone https://github.com/quaternionmedia/apothecary.git
cd apothecary
uv sync

# Initialize submodules (Gridfinity, etc.)
uv run apothecary submodules

# Generate example
uv run apothecary testrun -o example.scad

# Explore parts
uv run apothecary parts list

# Start the viewer (one-time: install its JS dependencies first)
uv run apothecary install
uv run apothecary serve
# Open http://127.0.0.1:8000/viewer
```

The viewer serves three.js from this origin rather than a CDN, so it works
offline — and `apothecary install` is not optional: without it the page renders
nothing and says so in a banner.

**[→ Full Quickstart Guide](QUICKSTART.md)**

## 📖 Documentation

| Guide                                              | Description                    |
| -------------------------------------------------- | ------------------------------ |
| [QUICKSTART.md](QUICKSTART.md)                     | Get running in 5 minutes       |
| [docs/](docs/README.md)                            | Full documentation index       |
| [docs/scene-json.md](docs/scene-json.md)           | JSON format for scenes         |
| [docs/parts-authoring.md](docs/parts-authoring.md) | Add your own parts             |
| [CONTRIBUTING.md](CONTRIBUTING.md)                 | Development setup & guidelines |
| [CHANGELOG.md](CHANGELOG.md)                       | Version history                |

## 🖥️ CLI Commands

```bash
apothecary --help              # Show all commands

# Core
apothecary testrun -o out.scad # Generate example scene
apothecary render --scene-file scene.json -o out.scad
apothecary render-jscad --scene-file scene.json -o out.js

# Parts
apothecary parts list          # List available parts
apothecary parts info NAME     # Show part details
apothecary parts render NAME   # Generate include stub
apothecary parts generate-stl --all  # Generate all STLs
apothecary parts generate-stl NAME -p wall=3   # Override a parameter
apothecary parts verify NAME         # Declared bounds vs real geometry
apothecary parts elephant-walk # Generate all-parts preview

# Submodules (external libraries like Gridfinity)
apothecary submodules          # Init & update all submodules
apothecary submodules --status # Check submodule status

# Server
apothecary serve               # Start FastAPI server
apothecary serve --port 8765   # Custom port
apothecary dev                 # Dev mode: generate STLs + start server

# Testing
apothecary test all            # Run full suite (unit + E2E)
apothecary test all --coverage # With coverage report
apothecary test run            # Unit tests only
apothecary test run-e2e        # E2E tests only

# Development
apothecary inventory structure # Show repo layout
apothecary check               # Verify installation
```

## 🌐 Web Interface

Start the server and visit http://127.0.0.1:8000:

| Endpoint                     | Description                             |
| ---------------------------- | --------------------------------------- |
| `/viewer`                    | Fractal zoom viewer (Three.js): navigates any registered site's Assembly tree at any depth, including the parts library |
| `/docs`                      | OpenAPI documentation (Swagger)         |
| `/parts`                     | List all parts (JSON)                   |
| `/parts/{name}/scad`         | Download OpenSCAD source                |
| `/parts/{name}/stl`          | Download STL file                       |
| `/parts/{name}/stl/generate` | Generate STL from SCAD                  |
| `/openscad/status`           | Check OpenSCAD availability             |
| `/health`                    | Health check                            |

## 🐍 Python API

```python
from apothecary import Scene, Cube, Sphere, Translate, Union, Vector3D

# Build a scene
base = Cube(size=Vector3D(x=20, y=20, z=5))
dome = Translate(v=Vector3D(x=10, y=10, z=5), children=[Sphere(r=8)])
scene = Scene(name="demo", objects=[Union(children=[base, dome])])

# Generate OpenSCAD
print(scene.render())

# Or JSCAD
print(scene.render_jscad())
```

## 📦 Project Structure

```
apothecary/
├── apothecary/           # Python package
│   ├── primitives.py     # Cube, Sphere, Cylinder
│   ├── booleans.py       # Union, Difference, Intersection
│   ├── transforms.py     # Translate, Rotate, Scale
│   ├── scene.py          # Scene composition
│   ├── api.py            # FastAPI endpoints
│   ├── cli.py            # Click CLI
│   ├── viewer.py         # Three.js viewer
│   └── projects/parts/   # Part wrappers & STL renderer
├── parts/                # Part folders with .scad/.stl
│   ├── parametric_star/
│   ├── couch_block/
│   └── ...
├── templates/            # Jinja2 templates
├── tests/                # Test suite (unit + E2E)
└── docs/                 # Documentation
```

## 🧪 Testing

```bash
# Unit tests only
uv run pytest -q

# Full test suite (unit + E2E with auto-server)
uv run apothecary test all

# With coverage
uv run apothecary test all --coverage

# E2E only (requires running server)
uv run apothecary serve --port 8765  # Terminal 1
uv run apothecary test run-e2e       # Terminal 2
```

## 📁 STL Files

STL files are **not committed to git** – they're generated locally from SCAD sources:

- **On server startup**: Missing STLs are auto-generated if OpenSCAD is installed
- **Manual generation**: `uv run apothecary parts generate-stl --all`
- **Single part**: `uv run apothecary parts generate-stl calibration_cube`
- **Force rebuild**: Add `--force` to regenerate existing STLs

To skip auto-generation at startup: `APOTHECARY_SKIP_STL_GENERATION=1 apothecary serve`

## 🤝 Contributing

We welcome contributions! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for:

- Development setup
- Code style guidelines
- Testing requirements
- Pull request process

## 📜 License

MIT License. See [LICENSE](LICENSE) for details.

## 🔗 Links

- [OpenSCAD](https://openscad.org/) – The 3D CAD modeler we generate code for
- [OpenJSCAD](https://openjscad.xyz/) – JavaScript-based alternative
- [uv](https://docs.astral.sh/uv/) – Fast Python package manager
