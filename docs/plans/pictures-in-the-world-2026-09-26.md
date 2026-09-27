# Pictures in the world: a look is pinned where it was seen

*Nothing in this page is built. It works inside the frame of
[one-screen-2026-09-20.md](one-screen-2026-09-20.md) (anchors, popups,
panels; the world is never replaced; every action has a cell; the census is
the meter) and under the draft record* Personal data stays on the device
*(§6: the picture root, `captures/` and `uploads/`, and what a page may
forget).*

## The end state

A picture is not a record in a panel. When a picture is taken or dropped at
a place, it becomes a **look**: that picture, pinned at one root structure
of the site on screen, or at the site's floor. It is drawn there as a mat
lying on the host's top. The shapes a finder saw are outlines on the mat. A
shape becomes a piece with one ring cell, and the piece stands where the
shape was seen, in the same site, checked against the world for overlap. A
camera is a badge at the structure it is pinned to, and its frustum looks
down onto the mat. While it is live, the mat shows its video. No picture
ever builds a site of its own, and nothing ever switches the site on screen
as a side effect.

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ toolbar: site ▾ · ◀ out · garage ›                              ⌗ Ring   │
 ├───────────────────────────────────────────────────────────┬──────────────┤
 │                                                           │ Contents     │
 │          ┌ cam: bench cam · still │ look: 3 shapes ┐      │  workbench   │
 │          └───────────────────╥────────────────────┘       │  disc_1      │
 │    anchor: one place badge   ║ apex                       │  printer_1   │
 │                             ╱│╲   frustum looks down      ├──────────────┤
 │                            ╱ │ ╲  (in the scene)          │ Selected     │
 │        ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓        │ disc_1       │
 │ ═══════┃ THE MAT: the look's picture (or live    ┃═══════ │ disc because │
 │ bench  ┃ video, outlines hidden), on the top     ┃        │ round; plain │
 │        ┃  ▆▆ disc_1      ┌┄┄┄┄┐ plate  ◯ post    ┃        │ 0.67; seen at│
 │        ┃  (made: a piece ┊    ┊ (found) (found)  ┃        │ workbench by │
 │        ┃   standing on   └┄┄┄┄┘ ← chosen shape   ┃        │ bench cam    │
 │        ┃   its outline)                          ┃        │ width [___]mm│
 │        ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛        │ Part ▸       │
 │                                                           ├──────────────┤
 │  drop a file on a structure: kept in uploads/, pinned     │ [Kept] tab   │
 │  there, found. ⌗ on a structure: … Why this · Into ·      │ (closed)     │
 │  Camera · Picture · Part                                  │              │
 ├───────────────────────────────────────────────────────────┴──────────────┤
 │ status: 3 shapes found at workbench                                      │
 └──────────────────────────────────────────────────────────────────────────┘
```

What stands in front of the world, and nothing else:

- **The place badge** (an anchor): one per host that has a camera or a look,
  the floor included. It is read, not operated. A click selects the host, as
  a machine badge does.
- **Selected** (a panel, tethered to the selection from Phase 6): the facts
  of whatever is picked -- a host's camera and looks, a chosen shape, a
  piece's provenance -- the one box a ring cannot type, a width in
  millimetres, and, for a part or a made piece, the part editor's sections.
  It carries no verb buttons: verbs are the ring's.
- **Kept** (a panel, closed to its tab): the one list §6 asks for. Every
  kept picture, and everything this page pinned on every site (cameras,
  boards, looks), each taken back from its row.

The Camera & pictures panel is gone. So are the preview in the rail, the
name box, the placement note, the second list of cameras, the three refresh
buttons, the gather half (to the `[photos]` extra), the site switch after
Look, the arrangement sites in the site picker, the album and picture routes
no page links to, and `apothecary photo view`.

## What each thing is, and how they link

**Host.** A root structure of the site whose `world_bounds()` is not `None`,
or the site itself (*the floor*). Only these hold cameras and looks; any
other structure is refused with its reason (in garage, `garage_building`
has no footprint and is refused). A root structure's `world_bounds()` is
already in the site's frame (`apothecary/hierarchy.py:126-137`), so its
world top-centre needs no walk up the tree; the gizmo edits only root
structures at the top level (`isEditableSelection`,
`templates/fractal_viewer.html.j2:1893`), and `check_no_overlaps` compares
only siblings (`hierarchy.py:271-296`). The floor's top is z = 0 at the
centre, in x and y, of the union of the root structures' `world_bounds()`,
or the origin when there are none; `vision/looks.py` computes it. The floor
is a selection like a node: its key is `@floor` in the page, and `host: ""`
in every look and camera route. It is selected by a click on its badge, on
its mat outside the outlines, or on one of its outlines at the top level.
Selected then shows its camera, looks and width box.

**Where a picture lands.** A drop, paste or Add on any node pins at that
node's root ancestor (a made piece's host is its own root, the one it was
made on); on empty canvas, at the floor. When the view is zoomed in (`focusPath`
not empty), the page first steps out to the top level, as ◀ out does -- a
view change, never a site switch -- so the new mat is seen. Several files
dropped at once are each kept and pinned as their own look; the finds run
one after another, the last is drawn, and the status names the count and
every file refused.

**Picture.** A file under the picture root, as today: the folder's own,
`captures/`, `uploads/`. Its one name is its path relative to the root, and
`GET /photos/pictures/file?path=` is its one route, gaining `&px=` for mats
and Kept cards: clamped to a few sizes, JPEGs decoded with `Image.draft`,
magic-byte checked as now, answered with `Cache-Control: no-store` so no
picture enters the browser's disk cache. Reuse is in memory: one texture
per drawn look and one object URL per Kept card for the page's lifetime. A
picture carries no links itself; looks point at it.

**Camera.** Two halves, as today: the browser's device (deviceId and label,
per origin) and its pin in `cameras.json` (`apothecary/routes/pictures.py`),
which gains `mm_across`: the default copied into each new look from it.
Typing a width on a look that has a camera also writes that camera's
`mm_across` in the same request (`PUT /sites/{s}/looks/{id}/scale`), so a
camera at a fixed height is sized once; Selected's camera row shows it as
*from the last width typed*, and a later look can still be rescaled alone.
The UI says *pin* and *unpin* for cameras, boards and pictures alike; the
`/cameras` route names stay until one-screen Phase 5. The live stream
exists only while Live is on at its host, and stops when the host is
deselected, leaves the level in view, or a Look is taken: Look ends Live,
and the mat shows the new look with its outlines (Live is one cell away).
Look from Still opens the pinned device, waits for `loadeddata` and 500 ms
more, keeps the frame, and stops the stream again. Captures are
`<stamp>-<camera id>.png`: the id already matches `CAMERA_ID`; the
browser's label stays in the pin only.

**Look** (new; replaces the shelf's `Built` as what the browser sees):
`{id: look_<UTC stamp>, site, host, picture, camera | null, taken_at,
finder, scale: {mm_across} | {shape index, mm} | null, pixel size, shapes,
made: {shape index → piece path}}`. A host may hold several looks; one is
*drawn* (the newest, until a person picks another), and every Picture verb
acts on the drawn one. Picking a look to draw -- by Looks, by Why this or
Shape on a piece made from another look -- is a view change, not a site
switch. A look never changes its finder or its shapes: Find with another
finder makes a new look of the same picture at the same host, which becomes
the drawn one, and the old keeps its shapes and made map. A look is *data
attached to a host*, not a node in the tree: `GET /sites/{name}` does not
change, so SCAD, STL, validation and jobs never see one. The page fetches a
site's cameras and looks in one request, `GET /sites/{s}/attached`, at
`loadSite`. The store is `apothecary/vision/looks.py`, in memory (as the
shelf is today) behind its own `threading.Lock`. Its shapes come from the
photo-finders plan's look cache, keyed as that plan keys it (picture hash,
backend, model digest, prompt version), with no second key; that cache is
held in memory too until the "this machine" decision (todo.md) lets it
reach the disk.

**Scale.** A look's scale is the only width drawn and used. Selected's one
box edits the drawn look's scale (and its camera's default, above), or the
camera's default when the host has no look; Size and Size from this focus
that box (for the latter, it then means the chosen shape's long side).
`ScaleReference` gains `known_index`, since labels may repeat
(`apothecary/vision/models.py:151-157`). Rescaling a look moves its unmade
outlines only; made pieces keep the scale in their provenance.

**Found shape.** `vision/models.FoundShape`, no longer thrown away after
`finder.look()`: box, points, confidence, origin, label, turn, sides, and the
word and reason `word_for` gave. Identity: (look id, index). Drawn as an
outline on the drawn look's mat, with an invisible pick mesh, except while
Live (outlines of a past frame are hidden over the present one) and except
when it is made (its piece is picked instead). An outline whose centre falls
inside the footprint of a piece already made at the same host, from any
look, is drawn as *already made (piece)*; Make all skips it and says how
many it skipped. Outline pick meshes join the node meshes in one
depth-sorted raycast, so a printer standing over an outline is still the
printer. Clicking an outline selects its host and *chooses* the shape; a
click on the mat outside the outlines, or on the host, clears the choice. A
person's word overrides the table's, recorded as stated.

**Piece.** A root structure of the same site, built by `piece_from_shape`
(the per-shape half of `vision/compose.build`, split out; the CLI's `build`
uses it). `compose.py:139-147` measures from the picture's lower-left
corner; `piece_from_shape` takes the centred frame instead: its offset from
the host's world top-centre is `((cx - 0.5) * W, (0.5 - cy) * H)`, where `W
= factor` and `H = tallness * factor` are the mat's extent, drawn centred
at that same point. Being a sibling of its host, the gizmo moves it, `POST
/sites/{s}/layout` keeps it, and it renders as its own node without
re-rendering the host's composite. Only garage's validator runs the generic
overlap check (`example_hierarchy.py:704`; `validate_parts_library` is a
deliberate no-op, `validate_datum_core` checks tray against lid), so the
make route and the page's validation add `check_no_overlaps(site.children)`
violations that name a made piece to every site's report (resting on its
host's top it only touches it, `_penetrates`). Its provenance -- picture,
host, camera, shape index, **a copy of the shape**, word (stated or not),
reason, finder, confidence, scale -- is keyed by (site, piece path) and
lives in `vision/looks.py` behind its lock, never in the site store, so a
plain-`def` forget can mark it. The copy lets it find its outline after the
look is unpinned or the picture forgotten. An unsized shape is never made
into a piece: the outline is drawn, and the piece waits for a person's
number.

**The part editor.** The browser-editing spike's decision
([part-editing-in-the-browser-2026-09-27.md](part-editing-in-the-browser-2026-09-27.md),
*Decided*) is that one editor, tethered to the part, also opens a shape
found in a picture; it is this plan's editor for a piece. It is not a second
popup: when the selection is a part or a made piece, Selected holds its
Parameters and Source sections below the facts, and Part › Edit on the ring
opens them. A made piece's parameters start as its shape and width.

**Links now:** camera → its looks; look → picture, host, shapes; shape →
piece; piece → look and shape; picture → looks (the store is indexed by
picture). Never made: a site built from a picture; a piece in another site.

**Cascades.** Forgetting a kept picture unpins its looks; pieces made from it
stay, their provenance saying the picture is gone. Purge does that for every
kept picture. Unpinning a look never deletes a picture; its made pieces stay.
Unpinning a camera leaves its looks (they belong to the place). Reset returns
the site to its code: made pieces go with the other layout edits, and their
shapes read as found again. A look whose host is gone is listed in Kept as
*gone*, as a stale pin is today.

**Browser.** `localStorage` keeps the panel layout, as today. Nothing
picture-shaped is stored in the browser, its HTTP cache included.

## Every surface today, and where it goes

| Today | Becomes | Why |
|---|---|---|
| Camera & pictures panel, `apothecary/static/widgets/camera.js` | Deleted by Phase 5; its parts go to the rows below. Stream and file calls move to `apothecary/static/pictures.js` with no markup | Five record types in one panel, none at its place |
| Live preview `<video>` in the rail | A `VideoTexture` on the mat at the camera's host; a 1×1 `<video>` in the anchor layer is its source | The camera's view drawn where it looks |
| Allow, camera pick, camera ⟳ | Camera › Pin here › *label* (an Allow leaf until the browser has asked); devices re-listed on `devicechange` | Allow opens the first device, not the pinned one |
| Name and width boxes | Name gone; width is Selected's one box (see *Scale*) | The name box names a site that is no longer made |
| Capture | Camera › Keep: the frame is kept and listed in Kept, not pinned, not found | Reference frames of the bench need no finder |
| Look | Camera › Look: keep the frame with camera and host, find, pin the look | A frame is always taken somewhere |
| Place note, Place at selected, Unplace | Camera › Pin here / Unpin on the host's ring; the badge is the note | Placing starts from the place |
| Pictures grid, ticks, all, ⟳, ✕ | Kept's grid (look count per picture, ✕ on kept ones; a card dragged onto a structure pins there); ticks and all go with gathering; ⟳ goes | Home for a picture at no place |
| Add pictures, Purge kept | Canvas ring Pictures › Add / Purge; drop and paste in the world | Adding lands at a place in one gesture |
| Gather report, answers, Open as one | The `[photos]` extra, CLI only, never registering a site | Decided (todo.md, Next round); Open as one replaces the world |
| Cameras in the world list | Kept's pinned rows | The same record as the badge |
| Boards pinned to pieces list | Kept's pinned rows (stale pins still shown) | Here only because of §6; Kept is that list |
| Camera badge | The place badge: camera and look at one host; a click selects it | Anchors are read, not operated |
| Camera frustum (fixed +Y) | Looks down onto its host; its base is the mat | Compose already reads a picture as a view from above |
| Selected panel | Stays, with provenance for every node that has one (`renderEditablePanel` shows none), camera and look facts with a row per look, the width box, the part editor's sections; no verb buttons; tethered from Phase 6 | The one sheet for what is picked |
| Contents and word chips | Unchanged; made pieces are root rows | The tree already covers them |
| OpenSCAD panel | Unchanged; no longer the only visible provenance | Build output |
| `openSite` after Look / Open as one; arrangement sites in the picker | Deleted | Each picture makes a new world |
| Status bar and `#cam-note` | Status bar only, refusals in the error class | Every message is written twice, refusals as success |
| Canvas ring Camera group | Canvas ring Pictures in the same seat | Adding and purging start from empty canvas |
| Node ring | Camera and Picture groups appended on hosts, Part after them; a floor ring | Verbs on the host they are about |
| `GET /photos/{name}` (album) | Provenance in `GET /sites/{s}/attached`; the route goes in Phase 7 | No page caller |
| `GET /photos/{name}/picture` | `GET /photos/pictures/file`; goes in Phase 7 | One picture, one route |
| `POST /photos`, `GET /photos`, `DELETE /photos/{name}`, `vision/shelf.py` | Look routes; the old ones go in Phase 7 | Build, shelve and register is written four times |
| `/photos/pictures*` | Stay; `POST` gains `site`, `host`, `camera` (keep and pin in one request); forget and purge cascade | §6's file layer, now joined |
| `/cameras` | Stay; `PUT` gains `mm_across` and accepts the floor | The pin store is right |
| Board pin routes, Selected › Device | Unchanged; listed through `GET /placed` | Firmware's own |
| `photo look / build / words / finders / check` | Stay; `build` uses `piece_from_shape` | Terminal tools, not windows |
| `photo view`, `photo gather --open` | Deleted (Phase 1 for `--open`, Phase 7 for `view`): `apothecary serve`, then drop the file on a structure | Each starts a second server on the same port and can cover a built-in site |
| `photo gather`, `gather-check`, the gathering map | The `[photos]` extra | Decided |
| Walkthroughs 11 and 12 | Rewritten to drive the world, not `page.request` | Chapter 11's captions for steps 14-15 say more than its screenshots show |

## The tasks, walked in the end state

A step is one pointer act or one ring path. A window is anything in front of
the world other than a panel already open.

| Task | Steps | Windows |
|---|---|---|
| Take a frame from a camera pinned at the bench | Click its badge (the bench is selected); Camera › Look, from Live or Still. The frame is kept with its camera and host, Live ends, the finder runs, the mat shows it with outlines, sized from the camera's last width. | None (the browser's prompt the first time) |
| Keep a frame without finding | Click the badge; Camera › Keep. Listed in Kept. | None |
| Add a photo from disk | Drag the file (or several) onto a structure: kept in `uploads/`, pinned at its root, found. Onto empty canvas: pinned at the floor. Paste pins at the selected host (named `<stamp>-paste.png`). By ring: Picture › Add on the selection, or Pictures › Add for the floor, then the OS dialog. | The file manager, or the OS dialog |
| Find shapes in a picture | None after a pin: finding is part of pinning. A picture already under the root: select a host or the floor, Picture › Folder › *one of the seven newest*; any other picture from Kept's grid, dragged onto the host (the Folder cell's eighth leaf opens Kept, and its address is written on the grid). | None, or Kept |
| Photograph a loose part on paper and model it | Drop the photo on empty canvas (the floor is selected, its look drawn); click an outline; type the width in Selected; Picture › Make piece. | None |
| Make a found shape a piece | Click the outline; Picture › Make piece. It stands on its outline, and an overlap shows red in the world and in Validation. At an unsized look, Picture › Size from this and type the width once. Move it with the gizmo. | None |
| From a piece, see its picture and shape | Select it: Selected shows its provenance. Why this frames it, draws its look, lights its outline and draws a thread to it, the selection staying on the piece; with the look gone, the outline is drawn from the piece's copy. Picture › Shape draws its look, selects the host and chooses the shape. | None |
| Go back to an older look | Picture › Looks › *one of the seven newest*, or its row in Selected (every look). | None |
| Forget pictures | One: Picture › Forget, or ✕ in Kept. Everything kept: Pictures › Purge, then one confirm naming the counts; the folder's own stay. | The confirm, for Purge |
| Pin or unpin a camera or picture | Camera: select a host or the floor, Camera › Pin here › *label*. Picture: any of the add or find paths above. Unpin from the host's group, from Kept's row, or, when the host is gone, Pictures › Stale › *row*. | None (the prompt the first time) |

## The ring

Seating is menu.py's, cardinals first by option order; absent options are
absent, not greyed; no ring holds more than eight, and no address is more
than four rings from the top. Picture lists never go through `_grouped`,
which refuses more than 64 and would 409 the whole ring
(`menu.py:442-447`, `routes/menu.py:110-113`): a list is the seven newest,
and the eighth cell says where the rest are. Addresses are the resolver's to
compute and the page's to write (`annotateControls` is extended to Selected
and Kept). The resolver is told a Picture context -- `{looks here, drawn
look, chosen shape, made, sized, finders, camera here, this browser's
cameras, the seven newest pictures}` -- as it is told a Device today; it
never looks one up. The page re-fetches `GET /photos/pictures` (newest
first) when a ring opens, coalesced with the ring's other context requests,
and adds the Picture context to its ring cache key
(`templates/fractal_viewer.html.j2:3957`, `:4001`), so a choose, look or
make is never answered from a stale ring.

- **Canvas ring** (nothing selected). The Camera group becomes **Pictures**
  in the same seat, so no other canvas cell moves: Add (pins at the floor),
  Purge, [Stale › *row*]. Panels › Camera becomes Panels › Kept in the same
  seat.
- **Node ring.** Zoom in, Move, [Device], Why this, [Into], [Up], then
  **[Camera]**, **[Picture]**, **[Part]**, appended so no existing cell
  moves. Camera and Picture are offered on hosts and made pieces (Picture
  only) and Up only below the root, so the most a node holds is eight: a
  host with a board, children and a part. Part is the spike's group (Apply,
  Revert, Edit, Variants).
  - Camera: Pin here › *this browser's cameras* (Allow until asked), Live |
    Still, Look, Keep, Unpin.
  - Picture on a host: Add, Folder › (the seven newest, then *In Kept*), then
    with a look here: [Looks › (the seven newest, then *In Selected*)], Make
    all, Size, [Find › *finder*] (only when more than one finder can read
    this picture), Unpin, Forget (kept pictures only, destructive). At most
    eight.
  - Picture with a shape chosen replaces that ring: Make piece | Its piece,
    Word › (the vocabulary's words, grouped past eight), Size from this,
    Unchoose.
  - Picture on a made piece: Word ›, Shape (draws its look, selects the host
    and chooses the shape), Drop (the piece goes; its shape stays).
  - Why this stays `explain` everywhere.
- **Floor ring** (the floor selected): Fit, Camera, Picture (the same groups,
  the chosen-shape ring included), and no Zoom, Move or Into. So the deepest
  path is Picture › Word › *group* › *word*, four rings.
- **Kept rows and cards** carry no verb buttons except the take-back each
  row owes §6 (unpin, ✕); a row click selects what it names and ⌗ opens
  that ring, a card is dragged onto a structure. Their addresses are those
  of the ring equivalents.
- `CARRIED_BY` (menu.py) gains `camera:*` as now and every `picture:*` as
  **VIEWER**, the way `device` is: the page's handler calls the Phase 2 look
  routes, which are the server; the intent route gains no arms. The deleted
  camera verbs leave it.
- One-screen Phase 4's board verbs sit under Device › Link beside
  Reconnect, Reset and Release, because the Device ring on a printer already
  holds eight (`menu.py:642-668`); the serial one is named Listen, so
  Camera › Live is the only Live.

## Phases

Each phase ships alone, and the world works between them. Every new or
moved listener is classified in `census.py` in the same change, in every
phase. Each ends with `uv run apothecary census`, `VIEWER_CEILING` in
`tests/test_census.py` edited to what it measures with its docstring saying
why and naming any ring address that moved (Phase 1: the gather cells;
Phase 4: Camera › Allow, Unplace, the canvas Camera group becoming
Pictures), a CHANGELOG.md line for what a user would notice, and any
rewritten walkthrough page committed.

Phase 1 is todo.md's *Next round* move and lands when that round starts.
Phases 0 and 2-4 do not depend on it: the camera panel's gather section
stays until then. Phase 5 deletes the rest of `camera.js` and so waits on
Phase 1. Phase 4 also waits on the §6 confirmation under *For a person*.

### Phase 0 — Stop the untruths and the doubles

- Delivers: provenance rows in Selected for every node that has one,
  including `renderEditablePanel` (`templates/fractal_viewer.html.j2:2031`),
  and no printer-status select for a piece whose status is `unsized`. One
  status write per message, refusals in the error class. A camera badge click
  selects its node and awaits the camera list before deciding whose camera it
  is (the first-click race in `openCamera`, :1212).
- Deletes: `#cam-note` and the second write
  (`apothecary/static/widgets/camera.js:78`, and
  `templates/fractal_viewer.html.j2:956`, which logs refusals as success).
- Tests: `tests/e2e/test_docs_photo_walkthrough.py` step 15 asserts the
  finder and confidence text, and steps 14-15 are captioned for what the
  screenshots show; a new e2e test clicks a camera badge on a page whose
  camera panel was never mounted. The `#cam-note` assertions
  (`tests/e2e/test_camera.py:95`, `:181`;
  `tests/e2e/test_docs_bench_walkthrough.py:402`) move to the status bar,
  refusals checked in the error class.

### Phase 1 — Gathering leaves core (next round)

- Mechanism: an extra only adds dependencies, and gathering has none beyond
  core, so it becomes its own distribution: a uv workspace member
  `apothecary-photos` shipping `apothecary_photos/` (today's
  `apothecary/gathering`, the map, the benches). Core's `packages.find`
  excludes it and declares `[project.optional-dependencies] photos =
  ["apothecary-photos"]`. Its router and `photo gather` mount only when
  `importlib.util.find_spec("apothecary_photos")` succeeds; otherwise `photo
  gather` names the extra.
- Delivers: `POST /photos/gather` on the extra's router, answering the report
  and the questions only. `PICTURE_SUFFIXES` moves into `vision/`, so
  `routes/pictures.py` (line 48) and `cli/photo.py` (line 364) load without
  the extra. `apothecary/vision` stays in core whole, `album.py` with it:
  `whole_gathering` builds `Album` and returns `Built`
  (`gathering/combine.py:32`, `:353`, `:361`). The draft record's §1
  install-point list and §7's install-point test are edited to match:
  gathering installs the guard when the extra is present, and the
  stays-local test skips it by name when it is absent. CONTRIBUTING.md's
  `pytest.yml` row names the extra-absent job (the workspace member not
  installed) and the extra-only tests, which the existing unit job runs with
  it installed; `preflight` runs both.
- Deletes: `GatherRequest.build` and `name`, the build branch of `POST
  /photos/gather` (`apothecary/routes/pictures.py:407-430`), `photo gather
  --open`; `whole_gathering` stays a function of the extra that nothing
  shelves or registers. `camera.js`'s gather section (ticks, all, Gather,
  Open as one, answers) and the ring cells `camera:gather`, `camera:open`.
  The extra ships no viewer surface.
- Tests: a job with the extra absent imports `routes.pictures`, answers
  `/cameras` and `/photos/pictures`, and finds no Gather cell
  (`tests/test_menu.py`). `tests/test_pictures_api.py`'s gather cases, minus
  build, and `tests/e2e/test_gathering_map_in_a_browser.py` run under an
  extra-only marker. `tests/e2e/test_camera.py`'s browser gather tests are
  deleted: `test_a_camera_records_its_own_surroundings` is cut at its gather
  half (line 160) and `test_gather_says_what_it_refused_and_what_it_set_aside`
  goes. Walkthrough 11's gathering half is marked extra-only.

### Phase 2 — Looks, server only

- Delivers: `apothecary/vision/looks.py` (the store, the floor's centre,
  provenance) and `apothecary/routes/looks.py`: `POST /sites/{s}/looks`
  `{host, picture, camera?, finder?}` (finds and keeps the shapes; a plain
  `def` in the threadpool that writes only the look store), and, `async def`
  on the event loop as `api.py`'s rule for routes that change a site says
  (line 619): `PUT /sites/{s}/looks/{id}/scale` (also the camera's
  `mm_across`), `PUT /sites/{s}/looks/{id}/shapes/{i}` `{word}`, `POST
  /sites/{s}/looks/{id}/make` `{shape | all}` (skipping shapes already made,
  adding made-piece overlaps to the report), `DELETE /sites/{s}/looks/{id}`;
  `GET /sites/{s}/attached`, `GET /placed`. `host: ""` is the floor in
  every look and camera route, `PUT /cameras` included. A host that is not a
  root structure with bounds or the floor is refused with its reason. `POST
  /photos/pictures` takes `site`, `host`, `camera` and pins the look it
  keeps. Forget and purge cascade through `looks.py` only.
  `piece_from_shape` split from `compose.build`, in the centred frame;
  provenance gains the shape index and copy; `ScaleReference.known_index`.
  `?px=` thumbnails.
- Deletes: nothing a person sees; the old `/photos` routes stay (one-screen
  rule 1).
- Tests: new `tests/test_looks_api.py`, a stated fixture pinned at node
  `workbench` in site `garage`: boxes and points kept; making shape *i* at
  a stated width puts the piece's centre on the outline's centre, for a
  non-square picture and an off-centre shape, and on the floor; an overlap
  with `printer_1` is reported, and one in `datum_core`; looks at
  `storage_shelving.shelf_unit` and at `garage_building` are refused; an
  unsized make is refused with its reason; a second look from the same
  camera is sized with the first's width; a second look at the same host
  does not remake a made shape, and Make all says how many it skipped; Find
  with another finder makes a second look and leaves the first's made map;
  a make during a running find neither loses nor duplicates a piece; a
  forget during a make loses neither the mark nor the piece; names stay
  unique; unpinning a look leaves the file; forgetting a kept picture
  unpins its looks and leaves pieces marked forgotten; Purge leaves the
  folder's own; Reset takes made pieces back and leaves looks; a path
  outside the root is refused. `tests/test_stays_local.py`: nothing written
  outside the root, its two folders and the state folder; `?px=` and
  `/photos/pictures/file` answer `no-store`; the new modules are among the
  ones §7 allows to open an image.

### Phase 3 — Looks drawn in the world

- Delivers first: `census.take` counts every module under
  `apothecary/static/` that the page imports, not only `widgets/`
  (`census.py:891`), so `pictures.js`, `picture_marks.js` and the existing
  `machine_marks.js` are metered; a test fails when an imported module's
  listener is unclassified.
- Delivers: `apothecary/static/picture_marks.js`, mounted like
  `machine_marks.js`: the mat (a texture from `?px=`, made once per look and
  disposed when it is unpinned or the site changes; sized by the look's
  scale, or fitted to the host's top for drawing only and marked unsized),
  outlines with pick meshes in the node meshes' depth-sorted raycast,
  *already made* outlines, the downward frustum, the place badge, the floor
  as a selection (`@floor`). Mats are drawn at the site's top level only.
  Choosing and clearing a shape. Selected shows camera and look facts.
  `loadSite` makes one `GET /sites/{s}/attached`; `this.cameras` is filled
  from it, and `refreshCameras` re-fetches it and redraws the badges, so the
  camera panel's Place and Unplace keep working until Phase 4.
- Deletes: `syncCameras`' frustum block, `refreshCameraMarks`,
  `openCamera` (`templates/fractal_viewer.html.j2:1158-1218`); the page's
  `GET /cameras?site=`.
- Tests: new `tests/e2e/test_picture_in_the_world.py` (a stated fixture
  dropped at `workbench`): the mat's pixels come from the picture; one
  outline per shape; clicking an outline chooses it; a click on `printer_1`
  over an outline selects `printer_1`; a click on the floor's mat selects
  the floor; the badge follows within a frame and is not dimmed by the mat;
  a camera placed from the panel shows its badge. The `cameraMarks`
  assertions in `tests/e2e/test_camera.py` and
  `tests/e2e/test_docs_bench_walkthrough.py` (`_camera_marks_visible`) are
  rewritten to `picture_marks`' own handle in this phase.

### Phase 4 — The loop's verbs on the host

- Delivers: node ring Camera, Picture and the floor ring, canvas Pictures,
  the Picture context and its cache key, `CARRIED_BY`. Live puts a
  `VideoTexture` on the mat; Look keeps, finds and pins, from Live or Still,
  and ends Live; Keep keeps. Drop (one file or several) and paste on the
  world, stepping out to the top level first. Make piece, Make all, Word,
  Size, Shape, Drop, Looks, Why this with its thread. Selected's width box
  and look rows. Until Kept lands, the camera panel's placed list gains a
  looks section from `GET /placed`, every site's, with unpin per row, so
  every page-made pin is listed from the phase that makes it (§6). Panels ›
  Camera opens what is left of the camera panel until Phase 5. New code goes
  into modules, not the template's inline script.
- Deletes: `openSite` and the page's `POST /photos`; `camera.js`'s camera,
  capture, Look and placement sections; `CAMERA_VERBS` and `KEPT_VERBS`.
- Tests: `tests/test_menu.py`: Camera and Picture present on hosts and the
  floor, absent below the root; a root with more than 64 pictures and with
  500, and a host with more than eight looks, still resolve; the fullest
  context (a board, a camera, a part, several looks, a chosen shape, several
  finders) holds every ring and sub-ring at eight or fewer and no address
  deeper than four; every `picture:*` is VIEWER; no existing node or canvas
  cell moved; the shape, made-piece and floor rings;
  `tests/conformance/nine_cells.json` updated. New
  `tests/e2e/test_the_loop.py`, launched with
  `--use-file-for-fake-video-capture` on a drawn fixture (the rectangle,
  disc and triangle `test_camera.py` draws): badge, Look from Still and from
  Live (Live ends, the outlines show), the host ring opened before and after
  choosing an outline (Make piece appears after), type a width, Make piece,
  a second Look sized from the first and not remaking it, the overlap shows,
  the gizmo clears it, Why this on the piece draws its look, a click on the
  piece selects the piece, the URL never changes; the same with the fixture
  dropped through `DataTransfer` (one file, and two: two looks, the last
  drawn), on a child while zoomed in (pinned at the root, the view stepped
  out), and on empty canvas (the floor selected, a width typed, the piece
  made); a look's row in the placed list unpins it. `tests/e2e/test_camera.py`
  rewritten around the host. Walkthrough 11's browser half and 12 §9-11
  regenerated.

### Phase 5 — One Kept panel (after Phase 1)

- Delivers: `apothecary/static/widgets/kept.js`, registered as `kept` in the
  camera panel's seat (Panels › Kept, `PANELS` in menu.py), docked right and
  closed to its tab: the grid (drag onto a structure) and *Pinned, every
  site's* (cameras, boards, looks; stale ones say so) from one `GET
  /placed`. A row click selects its host, switching site through the picker
  when the row is another site's.
- Deletes: the rest of `apothecary/static/widgets/camera.js` and its
  registration.
- Tests: new `tests/e2e/test_kept_panel.py`: rows for two sites; a stale row,
  made by pinning a board to a made piece and then Drop or Reset (*piece
  gone*), and its Pictures › Stale cell; unpin per row; a card dragged onto
  the selection; Purge asks once and leaves the folder's own.
  `tests/e2e/test_ring.py` (Kept registered, closed by default);
  `tests/e2e/test_docs_bench_walkthrough.py` §12-13 on Kept, their stale pin
  made the same way instead of `POST /photos` and `DELETE /photos/pins_check`
  (`:370-381`).

### Phase 6 — Selected stands at the selection

- Delivers: Selected tethered through `panels.tether` to the selection's
  anchor (the host's top, a shape's centre, the camera's apex, the floor's
  badge), holding the part editor's sections for a part or a made piece:
  the plan's *a piece's properties*. Dragging lets it go; docking is
  remembered. `panels.update` caches panel sizes with a `ResizeObserver`
  instead of reading `offsetWidth` every frame
  (`apothecary/static/panels.js:300`).
- Deletes: Selected's docked default.
- Tests: `tests/e2e/test_viewer.py`: opens within 300 ms of a click, follows
  within a frame, dock remembered across a reload, one popup for a made
  piece; the loop test re-run.

### Phase 7 — Old doors closed, with one-screen Phase 5

- Deletes: `POST /photos`, `GET /photos`, `GET` and `DELETE /photos/{name}`,
  `GET /photos/{name}/picture` (`api.py:1149-1283`), `RESERVED_NAMES`,
  `vision/shelf.py`, `photo view` with its README line. `vision/album.py`
  keeps `Album`, `Built` and `Provenance`, which the extra's
  `whole_gathering` uses.
- Tests: `tests/test_photo_in_the_viewer.py` retired, its provenance facts
  already in `tests/test_looks_api.py`; `tests/e2e/test_docs_photo_walkthrough.py`
  (`:61`, `:263`, `:271`, `:334`, `:338`, and `:369-378`, the grouping check)
  rewritten to the look routes; a test holds that no route registers a site
  from a picture, and one imports `apothecary_photos`' combine, both run in
  the job with the extra installed.

## What is decided here, and what a person decides

Decided by this plan: a picture enters the world only as a look pinned at a
root structure with bounds or the floor; the floor is a selection; no verb
switches the site as a side effect; a piece made from a shape is a root
structure of the site on screen, overlap-checked in every site, and this
plan refuses to make one unsized; a look's scale is the one width used, and
the last width typed is its camera's default; one Kept panel is the §6 list;
*pin* is the UI's one verb pair; new ring options are appended, never
inserted; picture lists in the ring are the seven newest; looks are in
memory until the record below says otherwise; `apothecary/vision` stays in
core, and only gathering and its benches go to `[photos]`, a distribution of
their own, which ships no viewer surface and registers no site; the browser
offers a finder choice only where more than one finder can read the
picture; the piece's editor is the spike's, inside Selected.

For a person, and for governance:

- *Personal data stays on the device* §6: confirm that a look is *what a page
  placed or pinned*, listed every site's and taken back the same way (Phase
  4 waits on this); that forgetting a kept picture unpins its looks and
  leaves made pieces marked forgotten, each still holding its shape's
  outline until Reset or Drop; that `uploads/` also takes dropped and pasted
  pictures, pasted ones named `<stamp>-paste.png`; that a pin may carry a
  person-stated width. §1 and §7: gathering's install point moves with the
  extra (Phase 1), and whether `apothecary.vocabulary` stays under the guard
  is settled with it, as the record's revision trigger asks.
- *rad host integration* §5: a lasting exception for Kept's per-row unpin
  and per-card ✕, ring-backed buttons kept because §6 asks for things to be
  taken back from the list that shows them. Selected carries none.
- Whether looks and made pieces may be kept in the state folder across a
  restart, and the finder cache with them. This waits on what "this
  machine" means (todo.md).
- *One screen* §1: add "a verb never switches the site as a side effect".
  §3: name the mat, the downward frustum and the outlines as drawn in the
  world. §2: Selected tethered to the selection serves a host, the floor, a
  shape, a camera and a piece.
- *rad host integration* §6: its node-ring list is edited to match: Word
  and get shape (Shape) sit under Picture on a made piece, and Why this
  stays apart. Its Consequences' Link cell is edited to hold Probe, Identify
  and Listen beside Reconnect, Reset and Release. Its revision triggers do
  not fire: the fullest node ring is eight, with Part, and no address is
  deeper than four rings.
- The photo-finders plan's open question (the finder choice): answered here
  as Picture › Find, present only when it can do something; that plan's
  *Pends on* row points here.

## Not in this plan

Merging `cameras.json` and the firmware bindings into one store; a camera
that looks sideways (direction and field of view are not recorded; a picture
is a view from above); a look's offset on its host: a mat is centred on its
host's top, so a camera that frames the bench off-centre puts every piece
off by the same amount, and each is moved with the gizmo (a per-camera
offset, inherited like `mm_across`, is the follow-up if that proves costly);
pictures standing upright on a wall; looks below the root; a gathering face
in the browser (when the extra grows one, it pins a look at a host, never a
site); a finder chosen by a model; persistence across restart, until the
record allows it; the CLI's `photo look` and `build` reading paths outside
the picture root.
