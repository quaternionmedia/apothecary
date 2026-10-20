# mobius_band

A Möbius band swept from slabs: a ring of radius 40 mm whose cross-section, 14 by
2 mm, turns half a turn about the ring's tangent in one trip round, so the band
has one side and one edge. It is the solid form of the ribbon the `airgap` part's
rotor wears as a feature (`rotor_rib_k`, `rotor_rib_w`): there the ribbon is a
reach added to a radius, here it is the thing itself.

The scene is 72 convex hulls, each of two neighbouring slabs placed and turned by
the scene's own transforms (`Translate`, `Rotate`, `Cube`, `Hull`, `Union`), so
OpenSCAD 2021.01 renders it in a few seconds with no slow boolean. `--half-twists`
gives the family: 0 is a plain belt, 1 the Möbius band, 2 a belt turned once,
3 a band with one side again. `--radius`, `--width`, `--thickness` and `--segments`
are what they say.

```bash
uv run python examples/llms_own/mobius_band/mobius_band.py > mobius_band.scad
uv run python examples/llms_own/mobius_band/mobius_band.py --half-twists 3 --segments 120 > three.scad
uv run python examples/llms_own/mobius_band/mobius_band.py --json > mobius_band.json   # the same band as a scene document
```

Tools: Claude Code (Anthropic) drafted this contribution; a human ratifies before merge.
