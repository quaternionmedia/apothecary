# examples/

Small things to run, by kind. Each is held by `tests/test_examples.py`: every
scene loads and renders, every script runs and prints OpenSCAD, and where an
OpenSCAD is installed each scene's SCAD compiles.

| Folder | What is in it | Run it with |
|---|---|---|
| [scenes/](scenes/) | Scene documents, the JSON `apothecary render` and `apothecary validate` read ([docs/scene-json.md](../docs/scene-json.md)) | `uv run apothecary render --scene-file examples/scenes/cube.json -o scene.scad` |
| [scripts/](scripts/) | Python that builds a `Scene` from the library and prints its OpenSCAD | `uv run python examples/scripts/snowplow_scene.py > snowplow.scad` |
| [pictures/](pictures/) | Pictures the shape finder reads ([docs/pictures.md](../docs/pictures.md)) | `uv run apothecary photo view examples/pictures/shapes.png --width-mm 300 --port 8001` |
| [theatre-rig/](theatre-rig/) | A lighting console's two exports, `patches.csv` and `fixture-parameters.csv`: the made-up rig the `theatre` site hangs when `APOTHECARY_THEATRE_RIG` names none ([docs/lighting.md](../docs/lighting.md)) | `uv run apothecary serve`, then `/viewer/sites/theatre` |
| [llms_own/](llms_own/) | **LLM's own**: contributions by language-model agents, in their own lane -- a folder each, a scene that renders, a README that says what it is | `uv run python examples/llms_own/mobius_band/mobius_band.py > mobius_band.scad` |

## scenes/

| | |
|---|---|
| `cube.json` | One cube with a comment: the smallest scene there is. The README's first `render` |
| `house.json` | The scene `apothecary render` falls back to with no `--scene-file`, as a file: a base, a roof, a door cut out. `tests/test_examples.py` holds it equal to `apothecary.example.create_example_scene()` |

A scene is a name and a list of objects, each tagged by `type` (`cube`, `sphere`,
`cylinder`, `import`, `union`, `difference`, `intersection`, `hull`, `translate`,
`rotate`, `scale`); `apothecary validate --scene-file <path>` says whether one
reads, and `apothecary templategenerate -t @templates/basic.scad.j2 --scene-file
<path>` renders one through a template.

## scripts/

| | |
|---|---|
| `snowplow_scene.py` | The RC snowplow's assembly, built by its Python (`apothecary.projects.parts.rc.snowplow`), placed in a scene and printed as OpenSCAD: a part whose geometry is Python, used from a script |

A script builds a `Scene` from `apothecary`'s objects and prints `scene.render()`;
`scene.model_dump(mode="json")` is the same scene as a document for `scenes/`.

## pictures/

| | |
|---|---|
| `shapes.png` | Three shapes on a grey ground, 640 × 480: what the finder reads in [walkthrough page 01](../walkthrough/01-photographs-into-pieces.md) and `apothecary photo view` |

## theatre-rig/

| | |
|---|---|
| `patches.csv` | Each patched channel: its fixture type, DMX address, label and, for a fixture hung in the room, its place and aim in metres in the site's frame |
| `fixture-parameters.csv` | Each fixture type's parameters, as the console exports them |

`tests/test_theatre_site.py` hangs it in the theatre and checks it clean; another console's two exports, under the same names in a folder `APOTHECARY_THEATRE_RIG` names, stand in for it.

## llms_own/

The lane for language-model agents' own contributions: what one is, how to add
one, and what holds each to the same rules as the rest -- [llms_own/README.md](llms_own/README.md).
