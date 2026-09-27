# Pictures in the world: a look is pinned where it was seen

*Nothing in this page is built. It works inside the frame of
[one-screen-2026-09-20.md](one-screen-2026-09-20.md) (anchors, popups,
panels; the world is never replaced; every action has a cell; the census is
the meter) and under the draft record* Personal data stays on the device
*(§6: the picture root, `captures/` and `uploads/`, and what a page may
forget).*

## The end state

A picture is not a record in a panel. When a picture is taken or dropped at
a place, it becomes a **look**: that picture, pinned at one node of the site
on screen. It is drawn there as a mat lying on the node's top. The shapes a
finder saw are outlines on the mat. A shape becomes a piece with one ring
cell, and the piece stands on the bench where the shape was seen, in the same
site, checked against the world by the site's own overlap check. A camera is
a badge at the node it is pinned to, and its frustum looks down onto the mat.
While it is live, the mat shows its video. No picture ever builds a site of
its own, and nothing ever switches the site on screen as a side effect.

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ toolbar: site ▾ · ◀ out · garage ›                              ⌗ Ring   │
 ├───────────────────────────────────────────────────────────┬──────────────┤
 │                                                           │ Contents     │
 │          ┌ cam: bench cam · live │ look: 3 shapes ┐       │  workbench   │
 │          └───────────────────╥────────────────────┘       │  disc_1      │
 │    anchor: one place badge   ║ apex                       │  printer_1   │
 │                             ╱│╲   frustum looks down      ├──────────────┤
 │                            ╱ │ ╲  (in the scene)          │ Selected     │
 │        ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓        │ disc_1       │
 │ ═══════┃ THE MAT: live video, or the look's      ┃═══════ │ disc because │
 │ bench  ┃ picture, lying on the bench top         ┃        │ round; plain │
 │        ┃  ▆▆ disc_1      ┌┄┄┄┄┐ plate  ◯ post    ┃        │ 0.67; seen at│
 │        ┃  (made: a piece ┊    ┊ (found) (found)  ┃        │ workbench by │
 │        ┃   standing on   └┄┄┄┄┘ ← chosen shape   ┃        │ bench cam    │
 │        ┃   its outline)                          ┃        │ width [___]mm│
 │        ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛        │ [Look][Live] │
 │                                                           ├──────────────┤
 │  drop a file on a piece: kept in uploads/, pinned there,  │ [Kept] tab   │
 │  found. ⌗ on a node: … Why this · Into · Up · Camera ·    │ (closed)     │
 │  Picture                                                  │              │
 ├───────────────────────────────────────────────────────────┴──────────────┤
 │ status: 3 shapes found at workbench                                      │
 └──────────────────────────────────────────────────────────────────────────┘
```

What stands in front of the world, and nothing else:

- **The place badge** (an anchor): one per node that has a camera or a look.
  It is read, not operated. A click selects the node, as a machine badge
  does.
- **Selected** (a panel, tethered to the selection from Phase 6): the facts
  of whatever is picked -- a node's camera and look, a chosen shape, a
  piece's provenance -- and the one box a ring cannot type, a width in
  millimetres.
- **Kept** (a panel, closed to its tab): the one list §6 asks for. Every
  kept picture, and everything this page pinned on every site (cameras,
  boards, looks), each taken back from its row.

The Camera & pictures panel is gone. So are the preview in the rail, the
name box, the placement note, the second list of cameras, the three refresh
buttons, the gather half (to the `[photos]` extra), the site switch after
Look, the arrangement sites in the site picker, the album and picture routes
no page links to, and `apothecary photo view`.

## What each thing is, and how they link

**Picture.** A file under the picture root, as today: the folder's own,
`captures/`, `uploads/`. Its one name is its path relative to the root, and
`GET /photos/pictures/file?path=` is its one route, gaining `&px=` (a Pillow
thumbnail, magic-byte checked as now) for mats and Kept cards. A picture
carries no links itself; looks point at it.

**Camera.** Two halves, as today: the browser's device (deviceId and label,
per origin) and its pin in `cameras.json` (`routes/pictures.py`), which
gains `mm_across`, the width a person stated for its frames at that node.
The UI says *pin* and *unpin* for cameras, boards and pictures alike; the
`/cameras` route names stay until one-screen Phase 5. The live stream exists
only while Live is on at its node, and stops when the node is deselected or
leaves the level in view.

**Look** (new; replaces the shelf's `Built` and the album's site face):
`{id: look_<UTC stamp>, site, node, picture, camera | null, taken_at, finder,
scale: {mm_across} | {shape, mm} | null, pixel size, shapes, made: {shape
index → piece path}}`. A node may hold several looks; the newest is drawn,
older ones are listed under it in Selected. It is *data attached to a node*,
not a node in the tree: `GET /sites/{name}` does not change, so SCAD, STL,
validation and jobs never see a look. The page fetches a site's cameras and
looks in one request, `GET /sites/{s}/attached`, at `loadSite`.
The store is `apothecary/vision/looks.py`, held in memory (as the shelf is
today), keyed so that moving it to the state folder later is a storage swap:
its shapes are the photo-finders plan's look cache, keyed by the picture's
sha256 and the finder.

**Found shape.** `vision/models.FoundShape`, no longer thrown away after
`finder.look()`: box, points, confidence, origin, label, turn, sides, and the
word and reason `word_for` gave. Identity: (look id, index). Drawn as an
outline on its look's mat, with an invisible pick mesh. Clicking one selects
its node and *chooses* the shape; the node ring's Picture group then acts on
it. A person's word overrides the table's, recorded as stated.

**Piece.** A root structure of the same site, built by `piece_from_shape`
(the per-shape half of `vision/compose.build`, split out; the CLI's `build`
uses it). It stands on the host's top: host world top-centre plus compose's
own picture-plane offset (`compose.py:139-147`), so it lands on its outline.
Being a root structure, the gizmo moves it (`isEditableSelection`,
`templates/fractal_viewer.html.j2:1893`), `POST /sites/{s}/layout` keeps it,
`check_no_overlaps` checks it (a piece resting on the bench only touches it,
`hierarchy.py` `_penetrates`), and it renders as its own node without
re-rendering the bench's composite. It carries provenance keyed by (site,
piece path): picture, host node, camera, shape index, **a copy of the shape**,
word (stated or not), reason, finder, confidence, scale. The copy lets it
find its outline after the look is unpinned or the picture forgotten. An
unsized shape is never made into a piece: the outline is drawn, and the piece
waits for a person's number.

**Links now:** camera → its looks; look → picture, node, shapes; shape →
piece; piece → look and shape; picture → looks (the store is indexed by
picture). Never made: a site built from a picture; a piece in another site.

**Cascades.** Forgetting a kept picture unpins its looks; pieces made from it
stay, their provenance saying the picture is gone. Purge does that for every
kept picture. Unpinning a look never deletes a picture; its made pieces stay.
Unpinning a camera leaves its looks (they belong to the place). Reset returns
the site to its code: made pieces go with the other layout edits, and their
shapes read as found again. A look whose node is gone is listed in Kept as
*piece gone*, as a stale pin is today.

**Browser.** `localStorage` keeps the panel layout, as today. Nothing
picture-shaped is stored in the browser.

## Every surface today, and where it goes

| Today | Becomes | Why |
|---|---|---|
| Camera & pictures panel, `static/widgets/camera.js` | Deleted by Phase 5; its parts go to the rows below. Stream and file calls move to `static/pictures.js` with no markup | Five record types in one panel, none at its place |
| Live preview `<video>` in the rail | A `VideoTexture` on the mat at the camera's node; a 1×1 `<video>` in the anchor layer is its source | The camera's view drawn where it looks |
| Allow, camera pick, camera ⟳ | Node ring Camera › Pin here › *label* (an Allow leaf until the browser has asked); devices re-listed on `devicechange` | A pinned camera is already chosen; Allow picked the first camera, not the pinned one |
| Name and width boxes | Name gone (captures are `<stamp>-<camera label>.png`); width is Selected's width box, kept as the pin's `mm_across` | The name box named a site that is no longer made |
| Capture and Look | One verb, Look: keep the frame with camera, site and node, find, pin the look | A frame is always taken somewhere |
| Place note, Place at selected, Unplace | Camera › Pin here / Unpin on the node ring; the badge is the note | Placing starts from the place |
| Pictures grid, ticks, all, ⟳, ✕ | Kept's grid (look count per picture, ✕ on kept ones); ticks and all go with gathering; ⟳ goes (Kept re-lists on open and after each change) | Home for a picture at no place |
| Add pictures, Purge kept | Kept's Add and Purge; canvas ring Pictures › Add / Purge; drop and paste in the world | Adding lands at a place in one gesture |
| Gather report, answers, Open as one | The `[photos]` extra, CLI only this round | Decided (todo.md, Next round); Open as one replaced the world |
| Cameras in the world list | Kept's pinned rows | The same record as the badge |
| Boards pinned to pieces list | Kept's pinned rows (stale pins still shown) | Here only because of §6; Kept is that list |
| Camera badge | The place badge: camera and look at one node; a click selects the node | Anchors are read, not operated |
| Camera frustum (fixed +Y) | Looks down onto its node; its base is the mat | Compose already reads a picture as a view from above |
| Selected panel | Stays, with provenance for every node that has one (today `renderEditablePanel` shows none), camera and look facts, the width box; tethered from Phase 6 | The one sheet for what is picked |
| Contents and word chips | Unchanged; made pieces are root rows | The tree already covers them |
| OpenSCAD panel | Unchanged; no longer the only visible provenance | Build output |
| `openSite` after Look / Open as one; arrangement sites in the picker | Deleted | Each picture made a new world |
| Status bar and `#cam-note` | Status bar only, refusals in the error class | Every message was written twice |
| Canvas ring Camera group | Canvas ring Pictures {Add, Purge} in the same seat | Camera verbs acted on a place from empty canvas |
| Node ring | Camera and Picture groups appended after Up | Verbs on the node they are about |
| `GET /photos/{name}` (album) | Provenance in `GET /sites/{s}/attached`; the route goes in Phase 7 | No page caller |
| `GET /photos/{name}/picture` | `GET /photos/pictures/file`; goes in Phase 7 | One picture, one route |
| `POST /photos`, `GET /photos`, `DELETE /photos/{name}`, `vision/shelf.py` | Look routes; the old ones go in Phase 7 | Build, shelve and register was written four times |
| `/photos/pictures*` | Stay; `POST` gains `site`, `path`, `camera` (keep and pin in one request); forget and purge cascade | §6's file layer, now joined |
| `/cameras` | Stay; `PUT` gains `mm_across` | The pin store is right |
| Board pin routes, Selected › Device | Unchanged; listed through `GET /placed` | Firmware's own |
| `photo look / build / words / finders / check` | Stay; `build` uses `piece_from_shape` | Terminal tools, not windows |
| `photo view` | Deleted in Phase 7: `apothecary serve`, then drop the file on a piece | A second server on the same port, and it could cover a built-in site |
| `photo gather`, `gather-check`, the gathering map | The `[photos]` extra | Decided |
| Walkthroughs 11 and 12 | Rewritten to drive the world, not `page.request` | Two of chapter 11's captions are not borne out by its screenshots |

## The tasks, walked in the end state

A step is one pointer act or one ring path. A window is anything in front of
the world other than a panel already open.

| Task | Steps | Windows |
|---|---|---|
| Take a frame from a camera pinned at the bench | Click its badge (the bench is selected); Look, in Selected or Camera › Look. The frame is kept with its camera and place, the finder runs, the mat shows it with outlines. | None (the browser's prompt the first time) |
| Add a photo from disk | Drag the file onto a piece. It is kept in `uploads/`, pinned there and found. Paste pins at the selected node. Dropped on empty canvas at the site root, it is kept and listed in Kept. By ring: Picture › Add, then the OS dialog. | The file manager, or the OS dialog |
| Find shapes in a picture | None after a pin: finding is part of pinning. A picture already in the folder: select the node, Picture › Folder › *name* (the newest seven, then More, which opens Kept). | None, or Kept |
| Make a found shape a piece | Click the outline; Picture › Make piece. It stands on its outline, and an overlap shows red in the world and in Validation. The first time at an unsized place, type the width once. Move it with the gizmo. | None |
| From a piece, see its picture and shape | Select it: Selected shows its provenance. Why this frames the host, lights the outline and draws a thread to it; with the look gone, the outline is drawn from the piece's copy. | None |
| Forget pictures | One: Picture › Forget on a node showing it, or ✕ in Kept. Everything kept: Pictures › Purge, then one confirm naming the counts; the folder's own stay. | The confirm, for Purge |
| Pin or unpin a camera or picture | Camera: select the node, Camera › Pin here › *label*. Picture: any of the add or find paths above. Unpin from the node's group or from Kept's row, on any site. | None (the prompt the first time) |

## The ring

Seating is menu.py's, cardinals first by option order; absent options are
absent, not greyed. Addresses are the resolver's to compute and the page's to
write on each new button (`annotateControls` is extended to Selected and
Kept). The resolver is told a Picture context -- `{looks here, chosen shape,
made, sized, finders, camera here, this browser's cameras, folder's newest}`
-- as it is told a Device today; it never looks one up.

- **Canvas ring.** The Camera group becomes **Pictures** {Add, Purge}
  in the same seat, so no other canvas cell moves. Panels › Camera becomes
  Panels › Kept in the same seat.
- **Node ring.** Zoom in, Move, [Device], Why this, [Into], [Up], then
  **[Camera]**, **[Picture]**, appended so no existing cell moves. The most a
  node can hold is eight: full, with nothing to spare.
  - Camera (a camera is pinned here, or this browser can offer one): Pin here
    › *this browser's cameras* (Allow until asked), Live | Still, Look,
    Unpin.
  - Picture on a node: Add, Folder ›, then with a look here: Make all,
    Size, Unpin, Forget (kept pictures only, destructive), Find › *finder*
    (only when more than one finder can read this picture).
  - Picture with a shape chosen: Make piece | Its piece, Word › (the
    vocabulary's words), Size from this.
  - Picture on a made piece: Word ›, Drop (the piece goes; its shape stays).
  - Why this on a made piece selects its shape. That is the rad record's
    promised *get shape*, and Word is its *Word option*
    (DRAFT-rad-host-integration.md:101-103), so rad needs no amendment.
- **Kept rows** have one Unpin or ✕ each; their ring equivalents are the
  node's own groups and Pictures › Purge.
- `CARRIED_BY` (menu.py) gains `camera:*` as now, `picture:*`, `pictures:*`,
  all carried by the viewer; the deleted camera verbs leave it.

## Phases

Each phase ships alone, and the world works between them. Each ends with
`uv run apothecary census`, `VIEWER_CEILING` in `tests/test_census.py` edited
to what it measures with its docstring saying why, and any rewritten
walkthrough page committed.

### Phase 0 — Stop the untruths and the doubles

- Delivers: provenance rows in Selected for every node that has one,
  including `renderEditablePanel` (`templates/fractal_viewer.html.j2:2031`),
  and no printer-status select for a piece whose status is `unsized`. One
  status write per message, refusals in the error class. A camera badge click
  selects its node and awaits the camera list before deciding whose camera it
  is (the first-click race in `openCamera`, :1212).
- Deletes: `#cam-note` and the second write (`camera.js:78`, :956).
- Tests: `tests/e2e/test_docs_photo_walkthrough.py` step 15 asserts the
  finder and confidence text, and steps 14-15 are captioned for what the
  screenshots show; a new e2e test clicks a camera badge on a page whose
  camera panel was never mounted.

### Phase 1 — Gathering leaves core

- Delivers: `apothecary/gathering`, `photo gather`, `gather-check`, the map
  and the benches behind `apothecary[photos]`; `POST /photos/gather` on the
  extra's router. `PICTURE_SUFFIXES` moves into `vision/`, so
  `routes/pictures.py` (which imports it at line 48) loads without the extra.
  Every new or moved listener is classified in `census.py` in the same change.
- Deletes: `camera.js`'s gather section (ticks, all, Gather, Open as one,
  answers, answer buttons) and the ring cells `camera:gather`, `camera:open`.
  The extra ships no viewer surface this round.
- Tests: a CI job with the extra absent imports `routes.pictures`, answers
  `/cameras` and `/photos/pictures`, and finds no Gather cell
  (`tests/test_menu.py`). The gathering tests
  (`tests/test_pictures_api.py` gather cases, `tests/e2e/test_camera.py`
  gather case, `tests/e2e/test_gathering_map_in_a_browser.py`) run under an
  extra-only marker. Walkthrough 11's gathering half is marked extra-only.

### Phase 2 — Looks, server only

- Waits on: the site-store lock (todo.md, Next round), since making a piece
  changes a site while a finder runs in the threadpool.
- Delivers: `apothecary/vision/looks.py` (the store) and
  `apothecary/routes/looks.py`: `POST /sites/{s}/nodes/{path}/looks`
  `{picture, camera?, finder?}` (finds and keeps the shapes), `PUT
  …/looks/{id}/scale`, `PUT …/looks/{id}/shapes/{i}` `{word}`, `POST
  …/looks/{id}/make` `{shape | all}`, `DELETE /sites/{s}/looks/{id}`, `GET
  /sites/{s}/attached`, `GET /placed`. `POST /photos/pictures` takes `site`,
  `path`, `camera` and pins the look it keeps. Forget and purge cascade.
  `piece_from_shape` split from `compose.build`; provenance gains the shape
  index and copy. `?px=` thumbnails. The camera pin gains `mm_across`.
- Deletes: nothing a person sees; the old `/photos` routes stay (one-screen
  rule 1).
- Tests: new `tests/test_looks_api.py`: a stated fixture pinned at
  `garage.workbench` keeps boxes and points; making shape *i* at a stated
  width puts a root structure's centre on the outline's centre; an overlap
  with `printer_1` is reported; an unsized make is refused with its reason;
  names stay unique; unpinning a look leaves the file; forgetting a kept
  picture unpins its looks and leaves pieces marked forgotten; Purge leaves
  the folder's own; Reset takes made pieces back and leaves looks; a path
  outside the root is refused. `tests/test_stays_local.py`: nothing written
  outside the root, its two folders and the state folder; the new modules
  are among the ones §7 allows to open an image.

### Phase 3 — Looks drawn in the world

- Delivers: `static/picture_marks.js`, mounted like `machine_marks.js`: the
  mat (a texture from `?px=`, sized by the look's scale or fitted to the
  node's top for drawing only, marked unsized), outlines with pick meshes
  raycast before node meshes, the downward frustum, the place badge. Mats
  are drawn only for the level in view and disposed on site change.
  Choosing a shape. Selected shows camera and look facts. `loadSite` makes
  one `GET /sites/{s}/attached`.
- Deletes: `syncCameras`' frustum block, `refreshCameraMarks`,
  `openCamera` (`templates/fractal_viewer.html.j2:1158-1218`); the page's
  `GET /cameras?site=`.
- Tests: new `tests/e2e/test_picture_in_the_world.py` (the fake camera,
  `tests/e2e/conftest.py` `FAKE_CAMERA`): the mat's pixels come from the
  picture; one outline per shape; clicking an outline chooses it; the badge
  follows within a frame and is not dimmed by the mat.

### Phase 4 — The loop's verbs on the node

- Delivers: node ring Camera and Picture, canvas Pictures, the Picture
  context, `CARRIED_BY` (Panels › Camera still opens what is left of the
  camera panel, its two lists and grid, until Phase 5). Live puts a `VideoTexture` on the mat; Look keeps,
  finds and pins. Drop and paste on the world. Make piece, Word, Size, Drop,
  Why this to the shape with its thread. Selected's width box and its Look
  and Live buttons, their addresses written on them. New code goes into
  modules, not the template's inline script.
- Deletes: `openSite` and the page's `POST /photos`; `camera.js`'s camera,
  capture, Look and placement sections; `CAMERA_VERBS` and `KEPT_VERBS`.
- Tests: `tests/test_menu.py`: Camera and Picture present by context, never
  more than eight on a node, no existing node or canvas cell moved, the
  shape and made-piece groups; `tests/conformance/nine_cells.json` updated.
  New `tests/e2e/test_the_loop.py`: fake camera, badge, Look, choose an
  outline, type a width, Make piece, the overlap shows, the gizmo clears it,
  the URL never changes; the same with a stated fixture dropped through
  `DataTransfer`. `tests/e2e/test_camera.py` rewritten around the node.
  Walkthrough 11's browser half and 12 §9-11 regenerated.

### Phase 5 — One Kept panel

- Delivers: `static/widgets/kept.js`, registered as `kept` in the camera
  panel's seat (Panels › Kept, `PANELS` in menu.py), docked right and
  closed to its tab: the grid, Add, Purge, and *Pinned, every site's*
  (cameras, boards, looks; stale ones say so) from one `GET /placed`. A row
  click selects its node, switching site through the picker when the row is
  another site's.
- Deletes: the rest of `static/widgets/camera.js` and its registration.
- Tests: new `tests/e2e/test_kept_panel.py`: rows for two sites, stale rows,
  unpin per row, Purge asks once and leaves the folder's own.
  `tests/e2e/test_ring.py` (Kept registered, closed by default);
  `tests/e2e/test_docs_bench_walkthrough.py` §12-13 on Kept.

### Phase 6 — Selected stands at the selection

- Delivers: Selected tethered through `panels.tether` to the selection's
  anchor (the node's top, a shape's centre, the camera's apex): the plan's
  *a piece's properties*. Dragging lets it go; docking is remembered.
  `panels.update` caches panel sizes with a `ResizeObserver` instead of
  reading `offsetWidth` every frame (`static/panels.js:300`).
- Deletes: Selected's docked default.
- Tests: `tests/e2e/test_viewer.py`: opens within 300 ms of a click, follows
  within a frame, dock remembered across a reload; the loop test re-run.

### Phase 7 — Old doors closed, with one-screen Phase 5

- Deletes: `POST /photos`, `GET /photos`, `GET` and `DELETE /photos/{name}`,
  `GET /photos/{name}/picture` (`api.py:1149-1283`), `RESERVED_NAMES`,
  `vision/shelf.py`, the album's site face (`vision/album.py` keeps
  `Provenance`), `photo view` with its README line.
- Tests: `tests/test_photo_in_the_viewer.py` retired, its provenance facts
  already in `tests/test_looks_api.py`; a test holds that no route registers
  a site from a picture.

## What is decided here, and what a person decides

Decided by this plan: a picture enters the world only as a look pinned at a
node; no verb switches the site as a side effect; a piece made from a shape
is a root structure of the site on screen and is refused unsized; one Kept
panel is the §6 list; *pin* is the UI's one verb pair; new ring options are
appended, never inserted; looks are in memory until the record below says
otherwise; the extra has no viewer surface this round; the browser offers a
finder choice only where more than one finder can read the picture.

For a person, and for governance:

- *Personal data stays on the device* §6: confirm that a look is *what a page
  placed or pinned*, listed every site's and taken back the same way; that
  forgetting a kept picture unpins its looks and leaves made pieces marked
  forgotten; that a pin may carry a person-stated width.
- Whether looks and made pieces may be kept in the state folder across a
  restart. This waits on what "this machine" means (todo.md).
- *One screen* §1: add "a verb never switches the site as a side effect".
  §3: name the mat, the downward frustum and the outlines as drawn in the
  world. §2: Selected tethered to the selection serves a node, a shape, a
  camera and a piece.
- The photo-finders plan's open question (the finder choice): answered here
  as Picture › Find, present only when it can do something.
- "Build badly or not at all" (todo.md): this plan picks *not at all* for
  making unsized pieces into a site.
- Whether a node ring full at eight is acceptable, or the rad record wants
  headroom kept.

## Not in this plan

Merging `cameras.json` and the firmware bindings into one store; a camera
that looks sideways (direction and field of view are not recorded; a picture
is a view from above); pictures standing upright on a wall; a gathering face
in the browser (when the extra grows one, it pins a look at a node, never a
site); a finder chosen by a model; persistence across restart, until the
record allows it; the CLI's `photo look` and `build` reading paths outside the
picture root.
