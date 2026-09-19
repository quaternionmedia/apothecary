# Externally authored scene documents are validated, never inferred

| | |
|---|---|
| **Kind** | feature |
| **Repo** | quaternionmedia/apothecary |
| **State** | stub |
| **Depends on** | nothing |
| **Graduates to** | a record on qm `project/apothecary` — this is a contract change |
| **Verified** | **Reproduced by execution**, `uv run python -c "from apothecary.api import _rehydrate; ..."` at `f1c1543`. Output quoted below. The reading agrees: line 148 tests `if t == "sphere" or "r" in obj_dict:` and sits above the cylinder branch at line 152; line 182 returns `Union(children=[], comment="unrecognized object")`. |

## What
`Scene.objects: List[OpenSCADObject]` has no discriminated union, so Pydantic
validates JSON into the base class and drops every subclass field. `_rehydrate`
patches this up heuristically. Run against the four interesting inputs:

```
{'type': 'cylinder', 'h': 10, 'r': 5}           -> Sphere     sphere(r=5.0);
{'type': 'cylinder', 'h': 10, 'r1': 3, 'r2': 5} -> Cylinder   cylinder(h=10.0, r1=3.0, r2=5.0, center=false);
{'type': 'sphere', 'r': 5}                      -> Sphere     sphere(r=5.0);
{'h': 10, 'r': 5}                               -> Sphere     sphere(r=5.0);
```

Three failures, one of them worse than the docs admit:

1. **An explicit `type` discriminator is ignored.** `{"type": "cylinder", "h":
   10, "r": 5}` renders `sphere(r=5.0)`. The sphere branch's `or "r" in
   obj_dict` fires before the cylinder branch is ever reached, so the escape
   hatch `docs/scene-json.md` offers — "accepts either explicit `type` or
   inferred shapes" — does not work for the commonest cylinder spelling. A
   caller who does everything the documentation asks still gets the wrong solid,
   silently.
2. A type-less `{"h": 10, "r": 5}` fails the same way, which is the documented
   looseness behaving as documented.
3. Anything unrecognised becomes an empty `Union` with a comment — empty
   geometry, no error.

The change: a real discriminated union that **rejects what it cannot name**,
with the inference path reserved for hand-written documents.

## Why now
Photo-derived scenes are the first externally authored scene documents apothecary
will accept, which is what makes a latent looseness into a live one.

Finding 1 changes the ranking, though. Honouring an explicit `type` is not a
contract change — the contract already promises it — so that part is a bug fix
and can land on its own, ahead of everything else here and independently of the
photo work. Findings 2 and 3 remain a contract change and still rank last.

## Seam
`api.py::_rehydrate`, `api.py::_primitive_descriptor`, `jscad.py::_render_node`
and `templates/fractal_viewer.html.j2::buildPrimitiveMesh` are the four places a
new object type must be registered today. A discriminated union would collapse
the first two.

## Open questions
- Finding 1 is a bug against the documented contract and should be fixed
  separately and first — reorder the branch tests so an explicit `type` wins,
  with a regression test that has been **seen to fail** before the fix lands.
- Findings 2 and 3 are a **contract change**: `docs/scene-json.md` documents the
  looseness as intentional, so tightening it needs to be argued rather than
  patched.
- Whether to keep the inference path at all, or to make explicit `type` mandatory
  and accept breaking hand-written documents.
- How far the same ordering bug reaches. `_primitive_descriptor` (viewer
  geometry) and `jscad.py::_render_node` dispatch separately and were not
  executed against these inputs.
