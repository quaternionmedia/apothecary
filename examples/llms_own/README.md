# LLM's own

A lane for language-model agents' own contributions to this repository:
scenes made for the pleasure of making them, forms the library has no use for
yet, arrangements that test what the model can say. The parts library is
curated and the viewer is governed; this folder is neither. It is where an
agent working here is encouraged to put something of its own, in its own
voice, under the same few rules as everything else.

## What a contribution is

One folder, named with underscores, holding:

- a **scene that renders** -- a Python script that builds a `Scene` from
  `apothecary`'s objects and prints `scene.render()` when run, or a scene
  document (JSON) `apothecary render` reads, or both;
- a **README** that says what the thing is and what it shows, in the present
  tense, as the rest of this repository's prose is written: what is there,
  not what was going to be. It ends with a `Tools:` line naming the agent
  and the session, as a commit here does ([CONTRIBUTING.md](../../CONTRIBUTING.md)).

Nothing here is a part. A contribution that grows into one -- that wants a
wrapper, an envelope, a place in the viewer's catalog -- moves to `parts/`
under the parts-authoring rules ([docs/parts-authoring.md](../../docs/parts-authoring.md))
and is reviewed as a part.

## What holds it

`tests/test_examples.py` runs every script, loads every document, and, where
an OpenSCAD is installed, compiles each scene's SCAD; it checks that every
folder here has its README, and that a script's document twin, where one is
committed beside it, is the script's own `--json` output (the two here commit
none: a thousand lines of JSON say nothing the script does not). A contribution
that stops rendering stops the suite, as a part would. The repository's other rules hold too: nothing
reaches the network at run time ([`apothecary/stays_local.py`](../../apothecary/stays_local.py));
the licence is the repository's, MIT, through `REUSE.toml`; a human ratifies
before merge, and may decline.

## How to contribute

1. Make the folder and the scene. Primitives, booleans and transforms are in
   `apothecary` (`Cube`, `Sphere`, `Cylinder`, `Import`; `Union`, `Difference`,
   `Intersection`, `Hull`; `Translate`, `Rotate`, `Scale`); a script that
   takes `--json` and prints `scene.model_dump(mode="json")` gives the
   document twin for free.
2. Run it: `uv run python examples/llms_own/<name>/<name>.py > <name>.scad`,
   and `openscad -o <name>.stl <name>.scad` if there is time to see it.
3. Write the README. Say what it is. If it came from somewhere -- a curve, a
   mechanism, another contribution -- say where.
4. Run `uv run pytest tests/test_examples.py`, then commit, with a `Tools:`
   line and no co-author trailer, on a branch, as a draft pull request.

The two here are the seed: a Möbius band swept from slabs, the solid form of
the ribbon the `airgap` part wears; and a nautilus of hulled chambers along a
logarithmic spiral, the curve the same part's rotor steps along. Neither
is needed by anything. Both render.

Tools: Claude Code (Anthropic) drafted this lane and its first two contributions; a human ratifies before merge.
