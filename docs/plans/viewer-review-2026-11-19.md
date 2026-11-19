# The viewer as a way to explore, reviewed

*Reviewed on 2026-11-19 at 435db0a4: the page used read-only at the universe, at the
garage, stepped into the router and into a part, and its code read. Five aims: a cabinet
in the world of each part's made versions; the universe's sphere made legible; one
standard for the groupings the page uses, now that rad's ring is settled; more links
between what the page shows, the minimap first; and layers that nest, joined to a view of
the parts in lanes. Decided with the owner one question at a time, the groupings first.*

## What the review found

### A part's made versions

- **Saved variants are the one lasting history of a part's versions**: a git ref each,
  under `refs/apothecary/variants/<part>/<name>`, with its parent, author and date
  (`apothecary/projects/parts/saved.py`). They already form a tree.
- **What was made is kept in six places, with no key in common.** A slice's record goes
  with its kept file. A cut's record names its variant. A print-tuning turn names its
  variant and outlives the slice. A job names the part and its G-code's hash, and no
  variant, parameters or STL (`apothecary/jobs.py`). An as-cut measurement names no
  variant. A piece made from a picture is held in memory and is gone at a restart.
- **Nothing answers "everything made of this part"**: jobs, slices and cuts take no part
  to filter by.
- The render cache keeps `PART_VARIANTS_KEEP` renders of a part, in the checkout's cache,
  and a tab's applies live in that tab alone.
- At most two versions are drawn at once: Compare draws two, Ghost one.
- `Shelf` already names the arrangements built from pictures (`apothecary/vision/shelf.py`).

### The universe's sphere

Counted in the page on the day:

- **One shell holds nearly every part**: 31 of the 38 are on the innermost. Seven parts are
  built from another, so composition depth tells few apart.
- **The categories are finer than the parts**: 19 of them, 7 with a single part, so the
  innermost shell wears about eighteen clusters of one or two parts, each outlined and
  labelled.
- **What is drawn round the parts outnumbers them**: 29 loops (each shell's three rings and
  each cluster's outline), 23 labels, 3 shell edges and 7 lines between parts.
- **The parts are drawn at their true size**, from the calibration cube to the whiteboard,
  about ninety to one. A shell's radius is set by its largest piece, so a part of the usual
  size is about a hundredth of the frame across and the whiteboard, the router and the
  printer are most of what is seen.

### Groupings

- **`category` means two things.** On a site's node it names the subsystem the node
  belongs to (`apothecary/hierarchy.py`): wall, furniture, mechanical, fluid, electrical.
  In the universe it names what a part is: coupon, camera, electromechanical. So
  `router_coupon` is a coupon in the universe and a structure in the garage, and the
  garage's `mechanical` holds the HVAC beside the printer and the router. `electrical`
  (boards) and `electronics` (devices) stand side by side.
- **"Group" names five things**: a window's group, the canvas ring's Group cell (the site's
  categories), the runs a long list is cut into, a widget's set of controls, and groups of
  data.
- **The categories are listed three ways**: the Group cell lists the site's top level by
  name wherever the page stands; Site's chips list what is under the level in view, in the
  table's order; the Layers window lists the whole tree by name.
- `dust` and `building` have no colour in `apothecary/layer_colours.py`'s table; theirs is
  made from the name, and `dust`'s lies close to `electromechanical`'s.
- **A long list is cut three ways.** `_bucket` (`apothecary/menu.py`) sorts it and cuts it
  into the most runs eight cells allow, each named for its first entry: nine entries are
  five runs. Two other functions keep the order. A part's presets past the eighth are
  dropped, where the module refuses a ninth rather than hide it.
- **Windows are seated outside their group**: the Procedure is the Family's and its door
  is under Panels › Site; the Deck is a tool and its Knobs are under Panels › Machine; the
  Lighting group has no door.
- **Four rings are full**: Panels, Panels › Site, Panels › Windows and View. The Group
  cell's address is 1 at a site's top and 7 stepped in, where the cells a ring always has
  keep one address.
- **rad settles the ring and not its contents**: eight cells at most, the keypad's cells,
  its item and its theme's tokens; nothing on how a long list is grouped.

### Links, and the minimap

- **The minimap is a column of dots**, one for each depth of the whole tree, filled down to
  the level in view, with no click (`renderMinimap`, `templates/fractal_viewer.html.j2`). It
  shows the same dots on every branch and none of the Layers window's depth.
- **Selected names the part a machine is drawn as in plain text**, not a link; it shows no
  parent, its "Inside it" is text, and what a part is built from is not shown.
- **The banner's crumbs go up only**; none lists the pieces beside it.
- **No row frames its piece**: `f` does, from the keyboard.
- **The ring's Inside lists a node's children and not its additions and subtractions**,
  which Site's tree lists.
- **No one event says the selection or the level moved**: the level is drawn again whole,
  and three ways of selecting reach different pieces.

### Layers, and the parts

- **Layers are flat**: a piece is on its shell's layer and its category's, and nothing
  nests. Depth is a number of its own.
- **The Layers window lists every category of the loaded tree wherever the page stands**,
  all of them while one part is stepped into, and its outermost shell is "sites" at the
  universe's own level and "built from those inside" in a part.
- **Site's tree lists what a hidden layer holds**, and its chips draw a category's pieces
  rather than narrow the list to them.
- **The page has no view of the parts**: a part is reached as a piece of the universe, and
  the Models window is image models. Nothing is laid out in lanes.

## Order

1. **Groupings**: one vocabulary every surface reads.
2. **Moving about**: one event for the selection and the level, every name a link, the
   minimap a map that is clicked.
3. **Layers that nest, and the parts in lanes**: the layers as a tree over the groupings,
   and a window of the parts, a lane each, whose header is that layer's row.
4. **The sphere**: tried in the page several ways at once (a common size for the parts,
   overlays only for what is pointed at, the outer shells peeled, the sphere unrolled into
   the lanes), and the ways kept chosen there.
5. **The cabinet**: a job naming the variant, its parameters and its STL's hash, one answer
   to what was made of a part, then the cabinet beside a part stepped into. The records
   can be built beside steps 2 to 4.

## Decided: groupings

1. **Two facets, Kind and System.** A part has a Kind: what it is. A site's piece has a
   System: the part of the place it serves, which is what `category` names on a site's
   node. A piece that is a part carries both. The universe groups by Kind and a site by
   System.
2. **Eight kinds over today's categories.** Two levels, Kind › category. Each category lies
   whole in one kind, so no part's category changes:

   | Kind | Categories |
   |---|---|
   | Electronics | electrical, electronics |
   | Cameras | camera |
   | Machines | machine |
   | Motors | electromechanical |
   | Test pieces | calibration, coupon |
   | Shop | dust, tooling, hardware, storage |
   | Housings | enclosure, building (the theatre's part, which the universe leaves out) |
   | Things | appliance, furniture, cookie-cutter, music, rc, misc |

3. **A list of more than eight is grouped by its facet, then by letters.** Entries with a
   facet (pieces, parts) are grouped by their Kind or System. A plain list of names
   (variants, presets, sites) is split into as few runs of near-equal length as fit, each
   named for its letters (`a–k`). Nothing is dropped. One function does both, for every
   list the ring cuts.
4. **Eight Systems, the machines apart.** A site's words become these:

   | System | The site's word |
   |---|---|
   | Building | wall |
   | Furniture | furniture |
   | Machines | the printer and the router, out of mechanical |
   | Mechanical | mechanical: the HVAC |
   | Electrical | electrical |
   | Plumbing | fluid |
   | Lighting | lighting |
   | Scenery | scenic |

   A part standing loose in a site, `router_coupon` or a devkit on the bench, has no
   System and is grouped by its Kind; datum_core's tray takes its part's Kind.
5. **A kind's colour, its categories shades of it.** The eight kinds are set well apart and
   each category is a shade of its kind's colour; the Systems have a set of their own. Each
   is written as a token, as rad's theme asks, and not as a literal in the ring.
6. **The Group cell becomes Kinds or Systems, at one address.** Kinds in the universe and
   Systems in a site, at the same address wherever the ring opens. "Group" names a window's
   group and nothing else, and a long list's runs are named by their letters.
7. **The rule goes to rad once it is built here**, with this page as its worked example.
   Until rad takes it, the host record carries a `Pends on` row naming rad.

## Built with them

- Each window's door is under its own group's cell: the Procedure under the Family's, the
  Knobs beside the Deck, and a door for Lighting.
- The three lists of categories are read from one function, in one order, scoped to the
  level in view.

## Slices: groupings

1. **The vocabulary** (built). `apothecary/facets.py` holds the Kinds over the categories
   and the Systems over a site's words; each value's colour is a token of
   `static/tokens.css`, a category's a shade of its kind's in L*a*b* lightness, and the
   Systems keep the colours the site's words had. A site is sent with its `facets`: the
   facet it is grouped by, its values with their tokens and colours, and its loose words.
   `tests/test_facets.py` holds every registered part's category to one kind, every word a
   site uses to one System or named loose, each colour apart from the others, the states,
   the shells and the world's own, and at 3:1 against the ground.
2. **The sites** (built). The printer and the router are `machine`, the Machines System;
   the router's stand is furniture; a machine's board sets no word and is in its machine's
   System; a part standing loose in a site (the boards, the Stream Deck and the footpedal on
   the bench, `router_coupon`, the whiteboard) carries no word and is grouped by its part's
   kind. Each piece of the tree is sent with its `kind` and `system`, and a site's
   `facets` with the kinds its pieces without a System are grouped by. A site's `machine`
   word wears the Machines token's colour.
3. **The ring.** Built in two parts.
   - **Lists and the facet cell** (built). One function, `_fit`, cuts every long list the
     ring holds, nothing dropped: a plain list of names into as few lettered runs as fit,
     near-equal; a list kept in its own order in that order, each run named for its first.
     Pieces and Inside are cut by facet first: a site's Systems, its loose parts under one
     more ring, Parts, by kind; the universe's kinds, its sites left to the Site cell. The
     canvas ring's every cell is always there: Step out 1, greyed at the universe's own
     level, and Systems 7, Kinds in the universe, each opening its pieces in place, greyed
     where a site has none. A part's presets are all kept.
   - **Panels by group.** The window groups become eight: Selected joins Part, Lighting
     joins Site, and Docs is a tool. Panels is one cell per group, Site, Part, Pictures,
     Machine, Windows, Tools, Family and Airgap, each holding its group's windows: the
     Procedure, Members and Deliveries under Family, the Deck and its Knobs under Tools.
4. **The page.** Site's chips, the Layers window's categories under their kinds, and the
   sphere's clusters by Kind, from the one list function. The walkthrough's pictures go
   with the change.
5. **rad.** The rule proposed, and the `Pends on` row in the host record.

## Not seen in the page

The Variants and History windows were not opened. Whether the ring's Parent is refused
where the level in view does not draw itself is read from the code and not tried.
