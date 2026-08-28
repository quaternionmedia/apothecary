# Photo → shapes → words → placed scenes → links

| | |
|---|---|
| **Kind** | repo-edit |
| **Repo** | quaternionmedia/apothecary (`feat/photo-shape-vocabulary`) |
| **State** | in progress — the model half is built and tested |
| **Depends on** | nothing |
| **Graduates to** | four records on qm `project/apothecary` — see qm-project-apothecary |
| **Verified** | **Built and run.** 47 tests green; the picture path exercised end to end on a generated picture. Names below are what shipped, which differs from the sketch this page started as. Whole tree searched before starting: zero hits for photo, image processing, any CV/ML dependency, `word`, `grammar`, or a link graph. `pillow` is present in the dev group only, used by `cli/docs.py::_assemble_gif`. `models/blackbox.py` read in full. |

## What
**Built.** Two packages, neither touching existing geometry code.

`apothecary/vision/` — `models.py` (`ShapeKind`, `FoundShape` with 0..1
coordinates, `confidence` and an `origin` field, `Picture`, `ScaleReference`),
`finder.py` (a `@runtime_checkable ShapeFinder` Protocol plus a name registry),
`stated.py` (`StatedFinder`, reads `<image>.shapes.json`; deterministic, what
tests use), `plain.py` (`PlainFinder`, Pillow only: shrink → Otsu split →
connected components by queue → fullness classifier), and `compose.py`
(`picture_to_site`).

`apothecary/vocabulary/` — a **word** is a recipe that builds an ordinary
`Assembly` node, not a new type. `Word(name, describes, build, tags)` and a
declarative `WordList` refusing duplicate names; `starter.py` with five words
(`plate`, `disc`, `post`, `slot`, `wedge`) built from existing primitives; and
`match.py`, a table read top to bottom, first match wins.

`apothecary/cli/photo.py` — `photo look`, `photo build`, `photo words`,
`photo finders`.

**Not built:** `apothecary/links.py`. Links wait on the surface work and on item
1 in `../CONCERNS.md`.

### What differs from the original sketch

Names changed to say what the things do rather than what pattern they are:
`ShapeFinder` not `ShapeProvider`, `StatedFinder` not `FixtureProvider`,
`PlainFinder` not `NaiveProvider`, `Picture` not `Detection`, `origin` not
`source`. The shape of it is unchanged.

## Why now
Now, because every one of these is greenfield and the expensive mistakes are all
still avoidable. Two provider implementations from day one is what makes the
Protocol a seam rather than an interface with one caller, and it proves the
pipeline against a real photograph without selecting a detector, vendoring model
weights, or calling a hosted service.

## Seam
`apothecary/models/blackbox.py` is the precedent and is copied rather than
improved on: a `@runtime_checkable` Protocol, a stub implementation, and a
`source` field so a scene can report how much of itself is guessed. Its docstring
already argues the case — the seam is the Protocol, "rather than a KiCad file
format this library would then be married to".

Words attach at the registry question `DRAFT-site-structure-substructure-feature-hierarchy.md`
explicitly deferred: "the exact registry/API wiring for reusable Assembly nodes
(separate record)". A word is a **peer** of `BasePart`, not a subtype —
`BasePart` is one `.scad` file plus print metadata; a word is a parameterized
tree with no file.

Links attach beside the `Assembly` tree, not inside it, so `to_scad_object()` and
`Scene` are untouched and the hierarchy record's "additive, not breaking"
property holds. Endpoints are the dotted paths `api.py::_find_node_by_path`
already resolves.

## Open questions
- `RevisionGraph`/`diff_assemblies` is deliberately **not** the link substrate: a
  revision graph relates states of one tree over time, a link graph relates two
  nodes at one instant, and collapsing them makes "B links to A"
  indistinguishable from "B is a later revision of A". Worth a record rejecting
  it in writing rather than leaving it as an open option.
- `pillow` has moved from the dev group to runtime, with a comment saying why.
  That is the only dependency change and it still needs a line in the adoption
  record's component table.
- `Assembly.render()` draws what is *beneath* a node, so a leaf word renders
  empty; its own shape comes through `to_scad_object()`. Cost two test failures
  before it was noticed. Worth a sentence in the hierarchy record.
- The five-word lexicon is a guess. It should be revisited after the first real
  photograph.
