# nautilus_chambers

A nautilus of hulled chambers along a logarithmic spiral, r = r0 · growth^(θ/360):
the curve the `airgap` part's rotor steps along when its `rotor_spiral_b` is set,
grown here into a shell. Twenty-eight cylinders stand on the spiral over one and
three-quarter turns, each hulled with the next into a chamber; the same chain at
0.72 of the size is cut from the top down to a floor, and a wall is put back
across the tube at every post, square to the spiral and clipped to the shell. The
result is a tray of open chambers with the septa between them standing -- the
plan of a nautilus, with its growth factor as a number.

`Cylinder`, `Cube`, `Hull`, `Union`, `Difference`, `Intersection`, `Translate` and
`Rotate` are all it uses. OpenSCAD 2021.01 renders it in about ten seconds.
`--growth` is the radius's growth per turn (2.6; a nautilus is near 3 per turn),
`--turns` and `--chambers` the length of the spiral and how finely it is divided,
`--hollow` the cut's size (0 is solid), `--floor` and `--wall` the thicknesses.

```bash
uv run python examples/llms_own/nautilus_chambers/nautilus_chambers.py > nautilus_chambers.scad
uv run python examples/llms_own/nautilus_chambers/nautilus_chambers.py --growth 3 --turns 2.5 --chambers 40 > wider.scad
uv run python examples/llms_own/nautilus_chambers/nautilus_chambers.py --json > nautilus_chambers.json   # as a scene document
```

Tools: Claude Code (Anthropic) drafted this contribution; a human ratifies before merge.
