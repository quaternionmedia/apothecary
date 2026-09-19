# Apothecary Quickstart

Get up and running with Apothecary in under 5 minutes.

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip
- **OpenSCAD** (optional, for viewing generated files)

## Installation

```bash
# Clone the repository
git clone https://github.com/quaternionmedia/apothecary.git
cd apothecary

# Install dependencies
uv sync

# Initialize git submodules (for external parts like Gridfinity)
uv run apothecary submodules

# Verify installation
uv run apothecary system
```

## Your First Scene

### 1. Generate an example

```bash
uv run apothecary testrun -o example.scad
```

Open `example.scad` in OpenSCAD to see a simple 3D scene.

### 2. Create a scene programmatically

```python
from apothecary import Scene, Cube, Sphere, Translate, Union, Vector3D

# Create primitives
base = Cube(size=Vector3D(x=20, y=20, z=5), comment="Base plate")
dome = Translate(
    v=Vector3D(x=10, y=10, z=5),
    children=[Sphere(r=8, fn=32)]
)

# Compose into a scene
scene = Scene(name="my_first_scene", objects=[
    Union(children=[base, dome])
])

# Generate OpenSCAD code
print(scene.render())
```

### 3. Render from JSON

Create a file `my_scene.json`:

```json
{
  "name": "json_demo",
  "objects": [
    {
      "type": "cube",
      "size": {"x": 15, "y": 15, "z": 10},
      "center": true
    }
  ]
}
```

Render it:

```bash
uv run apothecary render --scene-file my_scene.json -o output.scad
```

## Explore Available Parts

Apothecary includes curated printable parts with metadata:

```bash
# List all parts
uv run apothecary parts list

# Get info about a specific part
uv run apothecary parts info parametric_star

# Generate an include stub
uv run apothecary parts render parametric_star -o star.scad
```

## Start the Web Interface

The fractal viewer serves three.js from this origin rather than a CDN, and the
library is checked in under `apothecary/static/vendor/three/`, so nothing needs
installing for it. The separate JSCAD viewer is optional and is fetched once
with:

```bash
uv run apothecary install     # or: npm install --ignore-scripts
```

Then start the server:

```bash
# Generates any missing STLs, then serves
uv run apothecary dev

# Or serve only
uv run apothecary serve
uv run apothecary serve --port 8765

# In a browser
# http://127.0.0.1:8000/viewer  - the viewer
# http://127.0.0.1:8000/docs    - API documentation
```

`uv run apothecary check` tells you whether OpenSCAD and the 3D library are
both present before you wonder why something is empty.

**`/viewer` is the only entry point.** It opens on the `garage` site; the
dropdown switches sites, and `parts_library` is every registered part. Select a
part and its panel carries the part's parameters, its generated OpenSCAD, and
any values this project's sources disagree about. There is no separate parts
browser — a link like `/viewer/parts/datum_core` redirects here.

> **Note**: STL files are generated automatically on server startup if OpenSCAD is installed.
> They're not stored in git (see `.gitignore`). To manually regenerate all STLs:
> ```bash
> uv run apothecary parts generate-stl --all
> ```

## What's Next?

| Goal | Resource |
|------|----------|
| Learn the Scene JSON format | [docs/scene-json.md](docs/scene-json.md) |
| Add your own parts | [docs/parts-authoring.md](docs/parts-authoring.md) |
| Use templates | [templates/README.md](templates/README.md) |
| Contribute | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Full CLI reference | `uv run apothecary --help` |

## Common Commands

```bash
# System info
apothecary system

# Program a board (Arduino, ESP32, ...) from a sketch under parts/
apothecary firmware install --avr      # one-time: arduino-cli + the AVR core
apothecary firmware boards             # what's plugged in
apothecary firmware upload footpedal   # compile + upload; or use the /firmware page

# Initialize/update git submodules (Gridfinity, etc.)
apothecary submodules
apothecary submodules --status  # Check submodule status only

# List everything in the repo
apothecary inventory structure

# Render scene with template
apothecary templategenerate -t @templates/basic.scad.j2 --scene-file scene.json -o out.scad

# Export to JSCAD format
apothecary render-jscad --scene-file scene.json -o scene.jscad.js

# Run tests
apothecary test run
```

## Troubleshooting

**Command not found?**
```bash
# Use uv run prefix, or activate the virtualenv
uv run apothecary --help
# or
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows
apothecary --help
```

**Missing dependencies?**
```bash
uv sync
```

**Need help?**
```bash
apothecary --help
apothecary <command> --help
```
