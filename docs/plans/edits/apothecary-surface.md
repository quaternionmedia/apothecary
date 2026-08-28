# Twenty controls of its own become none

| | |
|---|---|
| **Kind** | repo-edit |
| **Repo** | quaternionmedia/apothecary (`feat/photo-shape-vocabulary`) |
| **State** | the option builder is built and tested; the drawing has not started |
| **Depends on** | rad is a unification engine — the foundational principle; Photo → shapes → words → placed scenes → links |
| **Graduates to** | rad host integration for apothecary (qm `project/apothecary`) |
| **Verified** | Counted by `apothecary census`, which reads `templates/fractal_viewer.html.j2` and refuses to give a number when it meets anything unclassified. Twenty controls of its own, four things done to the scene, six places in the lists, three ways of taking hold of a piece, no ring. `grep -i menu` across the whole tree returns zero hits; `rad` appears only as `math.radians`. |

## What
The viewer today has **twenty controls of its own**: a drop-down of arrangements,
a load button, a step-out button, a snapping tick-box, a form for jobs with four
boxes and a submit button, a go-in button, a drop-down for the state of a piece,
three boxes for typing a position, a rebuild button, a download link, a drop-down
of machines, and two buttons on each job. Beside them, four things done to the
scene (pointing, double-tapping, the wheel with a counter of its own, a key), six
places in the trails and lists, and the handle for dragging a piece.

After: **none of its own.** The ring, the scene, the lists, and dragging.

**This paragraph used to say twelve become three, and both numbers were wrong.**
Twelve was a hand tally. When a counter was written to reproduce it, an
independent reviewer showed the counter had been built until it agreed: it
counted names rather than controls, so two buttons side by side were one; it
could not see a control nothing listens to; and its own rule, applied evenly,
gave nine or sixteen but never twelve. The counter was rebuilt against a rule
written down first, and it now counts one control at a time. See
[counting the controls](../features/surface-census-tooling.md).

The meter is the first number and it has to reach **nothing**, not something
smaller. A ring that leaves five buttons behind has not replaced them.
`#violations-list`, `#minimap`, `#breadcrumb` and `#code-content` are untouched
because they were already read-only views.

The resolver is **Python**, server-side — `apothecary/menu.py` mirroring rad's
`MenuItem`/`MenuContext`/`MenuSpec`/`Intent` and providing `resolve(context,
site, links)` with `assert_ring` raising above 8. rad's state machine, geometry
and rendering stay in rad's JS.

## Why now
Now, and before the photo verbs arrive, because new capability landing into an
already-unified surface is a different job from unifying a surface that is also
growing. Steps 1–6 of the migration carry no new features at all.

## What is built

**The option builder**, `apothecary/menu.py`. The shared contract's shapes in
Python — what you are pointing at, the options, the choice — plus the two limits
that are easiest to break by accident, now ordinary tests: at most eight options
to a ring, at most twelve characters to a label, and shortening rather than
trailing off. It changes nothing; a choice becomes an intent and the intent is
what the rest of the program acts on. The state machine and the drawing stay
where they are, because porting them would make this a second implementation.

**Grouping, nearly for free.** The viewer already gathers nodes by category and
offers them as filters, so naming each piece's word as its category makes that a
filter by word. It was claimed here that this took *no* new drawing code. That
was wrong, and driving the real thing in a browser is what caught it: the chips
were only drawn for categories on a list written into the page, so a word nobody
had written down got no chip and could not be filtered at all — invisible rather
than merely plain.

One change fixed it, and it was worth making for its own sake: any group present
gets a chip, and a group not on the list gets a colour worked out from its name,
the same colour every time. A fixed list of categories cannot hold a vocabulary
that is meant to grow.

**What is known about each piece**, `apothecary/vision/album.py` — which finder
saw it, how sure, which word and why, whether anything was measured. Held beside
the tree and joined by the dotted path, for the same reason links are: the shape
of a node is not this feature's to change.

**One command that builds and shows**, `apothecary photo view picture.png`. An
arrangement built from a picture is held in memory, so building it in one program
and serving it from another would lose it in between.

## Seam
The project's first `APIRouter`s (photos, menu, links; the existing 27 routes
stay on `app`) and its first `StaticFiles` mount. `POST /menu/resolve` and
`POST /menu/intent` are the two that matter — **every** mutation routes through
the second, including the gizmo commit, which is what makes the generalized
superset rule true by construction.

Dotted paths are already the node identity in `_find_node_by_path`,
`pathForChild`, `?focus=` deep links, `diff_assemblies` keys and
`/sites/{name}/nodes/{path}/stl`. They become `MenuContext.targetIds` verbatim
and the endpoints of every `SceneLink`. **No new identifier scheme is needed
anywhere** — worth writing into the integration standard as a finding.

Migration order, each step replacing a control rather than adding one:
(1) the two routes land, resolving only verbs that already exist — nothing
visible changes; (2) toolbar buttons are rewired to post `Intent`s — still
nothing visible, but there is now one mutation path and it is provable; (3) the
ring appears, exposing exactly the verbs the toolbar exposes — the only step
where two surfaces coexist; (4) `#snap-toggle`, `#zoom-out-btn`, `#site-select`,
`#load-btn`, the wheel accumulator and `#category-filters` are deleted;
(5) `#job-form` deleted; (6) `#selected-body` becomes an inspector; (7) photo and
link verbs join the rings.

## Open questions
- Ring composition. The proposed rings fit the ≤8 ceiling, but `Site ▸`, `Word ▸`
  and `Filter ▸` all overflow in practice, so grouping is mandatory — by source,
  by `ShapeKind`, by category respectively. Overflow is a design problem, not a
  scrolling problem.
- Label length. `printer_1.gantry_system` is 18 characters against rad's 12-char,
  ellipsize-never rule. The resolver must shorten, and a unit test should say so
  rather than a screenshot.
- rad is `"private": true` at `0.0.0` with no npm export, so the consumption mode
  is copy or submodule. Either way, **vendor it, do not CDN it** — and note this
  lands on the adoption record's existing CDN gap (Three.js from jsDelivr)
  rather than opening a new one.
- Which three journeys the census measures. Proposed: filter a category, create
  and assign a job, replace a node with a word.
