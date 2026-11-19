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
   | Housings | enclosure |
   | Things | appliance, furniture, cookie-cutter, music, rc, misc |

3. **A list of more than eight is grouped by its facet, then by letters.** Entries with a
   facet (pieces, parts) are grouped by their Kind or System. A plain list of names
   (variants, presets, sites) is split into as few runs of near-equal length as fit, each
   named for its letters (`a–k`). Nothing is dropped. One function does both, for every
   list the ring cuts.

## Open: groupings

- **The Systems**: eight at most, and one word each for the garage's `mechanical` (the
  HVAC beside two machines), a part standing in a site (`router_coupon`'s `structure`) and
  datum_core's `enclosure`.
- **Colours**: a kind's colour, and its categories' as shades of it; written as tokens,
  as rad's theme asks, where the ring carries literal colours now.
- **Names**: Kind and System in the page; the canvas ring's Group cell as Kinds in the
  universe and Systems in a site; "group" kept for windows alone.
- **Each window's door under its own group's cell**: the Procedure, the Knobs, and a door
  for Lighting.
- **The Group cell's address held still.**
- **A grouping rule put to rad**: a long list is grouped by a named facet and not cut into
  runs of a sorted list; until rad takes it, a `Pends on` row naming rad in the host
  record.

## Not seen in the page

The Variants and History windows were not opened. Whether the ring's Parent is refused
where the level in view does not draw itself is read from the code and not tried.
