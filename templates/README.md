# templates/
Jinja2 templates for generating OpenSCAD.

- `part.include.scad.j2` is used by `apothecary parts render` when no `--template` is provided.
- Use an inline template or point to a file with `-t @path/to/template.j2`.

Example:
```bash
apothecary templategenerate -t @templates/basic.scad.j2 --scene-file examples/scene.json -o out.scad
```
