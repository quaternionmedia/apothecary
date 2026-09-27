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
shape was seen, in the same site, checked against the world by the site's
own overlap check. A camera is a badge at the structure it is pinned to, and
its frustum looks down onto the mat. While it is live, the mat shows its
video. No picture ever builds a site of its own, and nothing ever switches
the site on screen as a side effect.

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
 │        ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛        │ [Look][Live] │
 │                                                           ├──────────────┤
 │  drop a file on a structure: kept in uploads/, pinned     │ [Kept] tab   │
 │  there, found. ⌗ on a structure: … Why this · Into ·      │ (closed)     │
 │  Camera · Picture                                         │              │
 ├───────────────────────────────────────────────────────────┴──────────────┤
 │ status: 3 shapes found at workbench                                      │
 └──────────────────────────────────────────────────────────────────────────┘
```

What stands in front of the world, and nothing else:

- **The place badge** (an anchor): one per host that has a camera or a look.
  It is read, not operated. A click selects the host, as a machine badge
  does.
- **Selected** (a panel, tethered to the selection from Phase 6): the facts
  of whatever is picked -- a host's camera and looks, a chosen shape, a
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

**Host.** A root structure of the site, or the site itself (*the floor*: its
top is z = 0 at the centre of the site's bounds). Only these hold cameras
and looks. A root structure's `world_bounds()` is already in the site's
frame (`apothecary/hierarchy.py:126-137`), so its world top-centre needs no
walk up the tree; the gizmo edits only root structures at the top level
(`isEditableSelection`, `templates/fractal_viewer.html.j2:1893`), and
`check_no_overlaps` compares only siblings (`hierarchy.py:271-296`). A look
lower down would make pieces the view at that level does not draw, and that
overlap their own root every time. A made piece is not a host: a picture
dropped on one pins at the piece's host.

**Picture.** A file under the picture root, as today: the folder's own,
`captures/`, `uploads/`. Its one name is its path relative to the root, and
`GET /photos/pictures/file?path=` is its one route, gaining `&px=` for mats
and Kept cards: clamped to a few sizes, JPEGs decoded with `Image.draft`,
magic-byte checked as now, answered with an ETag of (path, mtime, size, px)
and `Cache-Control: private, max-age`. A picture carries no links itself;
looks point at it.

**Camera.** Two halves, as today: the browser's device (deviceId and label,
per origin) and its pin in `cameras.json` (`apothecary/routes/pictures.py`),
which gains `mm_across`: only the default copied into each new look from
it, shown as such. The UI says *pin* and *unpin* for cameras, boards and
pictures alike; the `/cameras` route names stay until one-screen Phase 5.
The live stream exists only while Live is on at its host, and stops when the
host is deselected or leaves the level in view. Look from Still opens the
pinned device, waits for `loadeddata` and 500 ms more, keeps the frame, and
stops the stream again. Captures are `<stamp>-<camera id>.png`: the id
already matches `CAMERA_ID`; the browser's label stays in the pin only.

**Look** (new; replaces the shelf's `Built` and the album's site face):
`{id: look_<UTC stamp>, site, host, picture, camera | null, taken_at,
finder, scale: {mm_across} | {shape index, mm} | null, pixel size, shapes,
made: {shape index → piece path}}`. A host may hold several looks; one is
*drawn* (the newest, until a person picks another), and every Picture verb
acts on the drawn one. A look never changes its finder or its shapes: Find
with another finder makes a new look of the same picture at the same host,
which becomes the drawn one, and the old keeps its shapes and made map. A
look is *data attached to a host*, not a node in the tree: `GET
/sites/{name}` does not change, so SCAD, STL, validation and jobs never see
one. The page fetches a site's cameras and looks in one request, `GET
/sites/{s}/attached`, at `loadSite`. The store is
`apothecary/vision/looks.py`, in memory (as the shelf is today) behind its
own `threading.Lock`, keyed so that moving it to the state folder later is a
storage swap: its shapes are the photo-finders plan's look cache, keyed by
the picture's sha256 and the finder.

**Scale.** A look's scale is the only width drawn and used. Selected's one
box edits the drawn look's scale, or the camera's default when the host has
no look; Size and Size from this focus that box (for the latter, it then
means the chosen shape's long side). `ScaleReference` gains `known_index`,
since labels may repeat (`apothecary/vision/models.py:151-157`). Rescaling a
look moves its unmade outlines only; made pieces keep the scale in their
provenance.

**Found shape.** `vision/models.FoundShape`, no longer thrown away after
`finder.look()`: box, points, confidence, origin, label, turn, sides, and the
word and reason `word_for` gave. Identity: (look id, index). Drawn as an
outline on the drawn look's mat, with an invisible pick mesh, except while
Live (outlines of a past frame are hidden over the present one) and except
when it is made (its piece is picked instead). Outline pick meshes join the
node meshes in one depth-sorted raycast, so a printer standing over an
outline is still the printer. Clicking an outline selects its host and
*chooses* the shape; a click on the mat outside the outlines, or on the
host, clears the choice. A person's word overrides the table's, recorded as
stated.

**Piece.** A root structure of the same site, built by `piece_from_shape`
(the per-shape half of `vision/compose.build`, split out; the CLI's `build`
uses it). `compose.py:139-147` measures from the picture's lower-left
corner; `piece_from_shape` takes the centred frame instead: its offset from
the host's world top-centre is `((cx - 0.5) * W, (0.5 - cy) * H)`, where `W
= factor` and `H = tallness * factor` are the mat's extent, drawn centred
at that same point. Being a sibling of its host, the gizmo moves it, `POST
/sites/{s}/layout` keeps it, `check_no_overlaps` checks it (resting on its
host's top it only touches it, `_penetrates`), and it renders as its own
node without re-rendering the host's composite. It carries provenance keyed
by (site, piece path): picture, host, camera, shape index, **a copy of the
shape**, word (stated or not), reason, finder, confidence, scale. The copy
lets it find its outline after the look is unpinned or the picture
forgotten. An unsized shape is never made into a piece: the outline is
drawn, and the piece waits for a person's number.

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
picture-shaped is stored in the browser.

## Every surface today, and where it goes

| Today | Becomes | Why |
|---|---|---|
| Camera & pictures panel, `apothecary/static/widgets/camera.js` | Deleted by Phase 5; its parts go to the rows below. Stream and file calls move to `apothecary/static/pictures.js` with no markup | Five record types in one panel, none at its place |
| Live preview `<video>` in the rail | A `VideoTexture` on the mat at the camera's host; a 1×1 `<video>` in the anchor layer is its source | The camera's view drawn where it looks |
| Allow, camera pick, camera ⟳ | Camera › Pin here › *label* (an Allow leaf until the browser has asked); devices re-listed on `devicechange` | Allow opens the first device, not the pinned one |
| Name and width boxes | Name gone; width is Selected's one box (see *Scale*) | The name box names a site that is no longer made |
| Capture | Camera › Keep: the frame is kept and listed in Kept, not pinned, not found | Reference frames of the bench need no finder |
| Look | Camera › Look: keep the frame with camera and host, find, pin the look | A frame is always taken somewhere |
| Place note, Place at selected, Unplace | Camera › Pin here / Unpin on the node ring; the badge is the note | Placing starts from the place |
| Pictures grid, ticks, all, ⟳, ✕ | Kept's grid (look count per picture, ✕ on kept ones, Pin at selected, and a card dragged onto a structure pins there); ticks and all go with gathering; ⟳ goes | Home for a picture at no place |
| Add pictures, Purge kept | Kept's Add and Purge; canvas ring Pictures › Add / Purge; drop and paste in the world | Adding lands at a place in one gesture |
| Gather report, answers, Open as one | The `[photos]` extra, CLI only this round, never registering a site | Decided (todo.md, Next round); Open as one replaces the world |
| Cameras in the world list | Kept's pinned rows | The same record as the badge |
| Boards pinned to pieces list | Kept's pinned rows (stale pins still shown) | Here only because of §6; Kept is that list |
| Camera badge | The place badge: camera and look at one host; a click selects it | Anchors are read, not operated |
| Camera frustum (fixed +Y) | Looks down onto its host; its base is the mat | Compose already reads a picture as a view from above |
| Selected panel | Stays, with provenance for every node that has one (`renderEditablePanel` shows none), camera and look facts with a row per look, the width box; tethered from Phase 6 | The one sheet for what is picked |
| Contents and word chips | Unchanged; made pieces are root rows | The tree already covers them |
| OpenSCAD panel | Unchanged; no longer the only visible provenance | Build output |
| `openSite` after Look / Open as one; arrangement sites in the picker | Deleted | Each picture makes a new world |
| Status bar and `#cam-note` | Status bar only, refusals in the error class | Every message is written twice, refusals as success |
| Canvas ring Camera group | Canvas ring Pictures in the same seat | Camera verbs act on a place from empty canvas |
| Node ring | Camera and Picture groups appended on hosts | Verbs on the host they are about |
| `GET /photos/{name}` (album) | Provenance in `GET /sites/{s}/attached`; the route goes in Phase 7 | No page caller |
| `GET /photos/{name}/picture` | `GET /photos/pictures/file`; goes in Phase 7 | One picture, one route |
| `POST /photos`, `GET /photos`, `DELETE /photos/{name}`, `vision/shelf.py` | Look routes; the old ones go in Phase 7 | Build, shelve and register is written four times |
| `/photos/pictures*` | Stay; `POST` gains `site`, `host`, `camera` (keep and pin in one request); forget and purge cascade | §6's file layer, now joined |
| `/cameras` | Stay; `PUT` gains `mm_across` | The pin store is right |
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
| Take a frame from a camera pinned at the bench | Click its badge (the bench is selected); Look, in Selected or Camera › Look, from Live or Still. The frame is kept with its camera and host, the finder runs, the mat shows it with outlines. | None (the browser's prompt the first time) |
| Keep a frame without finding | Click the badge; Camera › Keep. Listed in Kept. | None |
| Add a photo from disk | Drag the file onto a structure: kept in `uploads/`, pinned there, found. Onto empty canvas: pinned at the floor. Paste pins at the selected host (named `<stamp>-paste.png`). By ring: Picture › Add or Pictures › Add, then the OS dialog. | The file manager, or the OS dialog |
| Find shapes in a picture | None after a pin: finding is part of pinning. A picture already under the root: select a host, Picture › Folder › *name* (every picture, lettered into groups past eight), or Pictures › Folder › *name* for the floor. | None |
| Photograph a loose part on paper and model it | Drop the photo on empty canvas; click an outline; Picture › Make piece. | None |
| Make a found shape a piece | Click the outline; Picture › Make piece. It stands on its outline, and an overlap shows red in the world and in Validation. At an unsized look, Picture › Size from this and type the width once. Move it with the gizmo. | None |
| From a piece, see its picture and shape | Select it: Selected shows its provenance. Why this frames it, lights its outline and draws a thread to it, the selection staying on the piece; with the look gone, the outline is drawn from the piece's copy. Picture › Shape selects the host and chooses the shape. | None |
| Go back to an older look | Picture › Looks › *time*, or its row in Selected. | None |
| Forget pictures | One: Picture › Forget, or ✕ in Kept. Everything kept: Pictures › Purge, then one confirm naming the counts; the folder's own stay. | The confirm, for Purge |
| Pin or unpin a camera or picture | Camera: select a host, Camera › Pin here › *label*. Picture: any of the add or find paths above. Unpin from the host's group, from Kept's row, or, when the host is gone, Pictures › Stale › *row*. | None (the prompt the first time) |

## The ring

Seating is menu.py's, cardinals first by option order; absent options are
absent, not greyed; no ring holds more than eight. Addresses are the
resolver's to compute and the page's to write on each new button
(`annotateControls` is extended to Selected and Kept). The resolver is told
a Picture context -- `{looks here, drawn look, chosen shape, made, sized,
finders, camera here, this browser's cameras, pictures}` -- as it is told a
Device today; it never looks one up. The page re-fetches `GET
/photos/pictures` (newest first) when a ring opens, coalesced with the
ring's other context requests, so a file copied in by hand is listed.

- **Canvas ring.** The Camera group becomes **Pictures** in the same seat,
  so no other canvas cell moves: Add, Folder › (both pin at the floor),
  [Floor look › (the look verbs below)], Purge, [Stale › *row*]. Panels ›
  Camera becomes Panels › Kept in the same seat.
- **Node ring.** Zoom in, Move, [Device], Why this, [Into], [Up], then
  **[Camera]**, **[Picture]**, appended so no existing cell moves. Camera and
  Picture are offered on hosts only, and Up only below the root, so the most
  a node holds is seven. One-screen Phase 4's Probe, Identify and Live join
  Device › Link (three leaves there now), keeping the node ring at seven.
  - Camera: Pin here › *this browser's cameras* (Allow until asked), Live |
    Still, Look, Keep, Unpin.
  - Picture on a host: Add, Folder ›, then with a look here: [Looks ›
    *time*], Make all, Size, [Find › *finder*] (only when more than one
    finder can read this picture), Unpin, Forget (kept pictures only,
    destructive). At most eight.
  - Picture with a shape chosen replaces that ring: Make piece | Its piece,
    Word › (the vocabulary's words), Size from this, Unchoose.
  - Picture on a made piece: Word ›, Shape (selects the host and chooses
    the shape), Drop (the piece goes; its shape stays).
  - Why this stays `explain` everywhere.
- **Kept rows and cards** carry the addresses of their ring equivalents:
  the host's groups, Picture › Folder for Pin at selected, Pictures › Stale
  for a gone host, Pictures › Purge.
- `CARRIED_BY` (menu.py) gains `camera:*` as now and the picture verbs that
  touch only the view or the browser's camera, carried by the viewer;
  `picture:make`, `picture:drop`, `picture:word` and scale changes are
  carried by the server, as menu.py's own note on `move`'s commit says a
  change to the arrangement is. The deleted camera verbs leave it.

## Phases

Each phase ships alone, and the world works between them. Each ends with
`uv run apothecary census`, `VIEWER_CEILING` in `tests/test_census.py` edited
to what it measures with its docstring saying why and naming any ring
address that moved (Phase 1: Camera › Allow, Unplace, Kept; Phase 4: the
canvas Camera group becoming Pictures), a CHANGELOG.md line for what a user
would notice, and any rewritten walkthrough page committed.

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
  camera panel was never mounted.

### Phase 1 — Gathering leaves core

- Delivers: `apothecary/gathering`, `photo gather`, `gather-check`, the map
  and the benches behind `apothecary[photos]`; `POST /photos/gather` on the
  extra's router, answering the report and the questions only.
  `PICTURE_SUFFIXES` moves into `vision/`, so `routes/pictures.py` (line 48)
  and `cli/photo.py` (line 364) load without the extra. `apothecary/vision`
  stays in core whole. The draft record's §1 install-point list and §7's
  install-point test are edited to match: gathering installs the guard when
  the extra is present, and the stays-local test skips it by name when it is
  absent. CONTRIBUTING.md's `pytest.yml` row names the extra-absent job and
  the extra-only tests, which the existing unit job runs with the extra
  installed; `preflight` runs both. Every new or moved listener is
  classified in `census.py` in the same change.
- Deletes: `GatherRequest.build` and `name`, the build branch of `POST
  /photos/gather` (`apothecary/routes/pictures.py:407-430`), `photo gather
  --open`; `whole_gathering` stays a function of the extra that nothing
  shelves or registers. `camera.js`'s gather section (ticks, all, Gather,
  Open as one, answers) and the ring cells `camera:gather`, `camera:open`.
  The extra ships no viewer surface this round.
- Tests: a job with the extra absent imports `routes.pictures`, answers
  `/cameras` and `/photos/pictures`, and finds no Gather cell
  (`tests/test_menu.py`). `tests/test_pictures_api.py`'s gather cases, minus
  build, and `tests/e2e/test_gathering_map_in_a_browser.py` run under an
  extra-only marker. `tests/e2e/test_camera.py`'s browser gather tests are
  deleted: `test_a_camera_records_its_own_surroundings` is cut at its gather
  half (line 160) and `test_gather_says_what_it_refused_and_what_it_set_aside`
  goes. Walkthrough 11's gathering half is marked extra-only.

### Phase 2 — Looks, server only

- Delivers: `apothecary/vision/looks.py` (the store) and
  `apothecary/routes/looks.py`: `POST /sites/{s}/looks` `{host, picture,
  camera?, finder?}` (finds and keeps the shapes; a plain `def` in the
  threadpool that writes only the look store), and, `async def` on the event
  loop as `api.py`'s rule for routes that change a site says (line 619):
  `PUT /sites/{s}/looks/{id}/scale`, `PUT /sites/{s}/looks/{id}/shapes/{i}`
  `{word}`, `POST /sites/{s}/looks/{id}/make` `{shape | all}`, `DELETE
  /sites/{s}/looks/{id}`; `GET /sites/{s}/attached`, `GET /placed`. A host
  that is not a root structure or the floor is refused with its reason.
  `POST /photos/pictures` takes `site`, `host`, `camera` and pins the look
  it keeps. Forget and purge cascade. `piece_from_shape` split from
  `compose.build`, in the centred frame; provenance gains the shape index
  and copy; `ScaleReference.known_index`. `?px=` thumbnails. The camera pin
  gains `mm_across`.
- Deletes: nothing a person sees; the old `/photos` routes stay (one-screen
  rule 1).
- Tests: new `tests/test_looks_api.py`, a stated fixture pinned at node
  `workbench` in site `garage`: boxes and points kept; making shape *i* at
  a stated width puts the piece's centre on the outline's centre, for a
  non-square picture and an off-centre shape, and on the floor; an overlap
  with `printer_1` is reported; a look at `storage_shelving.shelf_unit` is
  refused; an unsized make is refused with its reason; Find with another
  finder makes a second look and leaves the first's made map; a make during
  a running find neither loses nor duplicates a piece; names stay unique;
  unpinning a look leaves the file; forgetting a kept picture unpins its
  looks and leaves pieces marked forgotten; Purge leaves the folder's own;
  Reset takes made pieces back and leaves looks; a path outside the root is
  refused. `tests/test_stays_local.py`: nothing written outside the root,
  its two folders and the state folder; the new modules are among the ones
  §7 allows to open an image.

### Phase 3 — Looks drawn in the world

- Delivers: `apothecary/static/picture_marks.js`, mounted like
  `machine_marks.js`: the mat (a texture from `?px=`, made once per look and
  disposed when it is unpinned or the site changes; sized by the look's
  scale, or fitted to the host's top for drawing only and marked unsized),
  outlines with pick meshes in the node meshes' depth-sorted raycast, the
  downward frustum, the place badge. Mats are drawn at the site's top level
  only. Choosing and clearing a shape. Selected shows camera and look facts.
  `loadSite` makes one `GET /sites/{s}/attached`; `this.cameras` is filled
  from it, and `refreshCameras` re-fetches it and redraws the badges, so the
  camera panel's Place and Unplace keep working until Phase 4.
- Deletes: `syncCameras`' frustum block, `refreshCameraMarks`,
  `openCamera` (`templates/fractal_viewer.html.j2:1158-1218`); the page's
  `GET /cameras?site=`.
- Tests: new `tests/e2e/test_picture_in_the_world.py` (a stated fixture
  dropped at `workbench`): the mat's pixels come from the picture; one
  outline per shape; clicking an outline chooses it; a click on `printer_1`
  over an outline selects `printer_1`; the badge follows within a frame and
  is not dimmed by the mat; a camera placed from the panel shows its badge.
  The `cameraMarks` assertions in `tests/e2e/test_camera.py` and
  `tests/e2e/test_docs_bench_walkthrough.py` (`_camera_marks_visible`) are
  rewritten to `picture_marks`' own handle in this phase.

### Phase 4 — The loop's verbs on the host

- Delivers: node ring Camera and Picture, canvas Pictures, the Picture
  context, `CARRIED_BY` (Panels › Camera still opens what is left of the
  camera panel, its two lists and grid, until Phase 5). Live puts a
  `VideoTexture` on the mat; Look keeps, finds and pins, from Live or Still;
  Keep keeps. Drop and paste on the world. Make piece, Word, Size, Shape,
  Drop, Looks, Why this with its thread. Selected's width box, look rows,
  and Look and Live buttons, their addresses written on them. New code goes
  into modules, not the template's inline script.
- Deletes: `openSite` and the page's `POST /photos`; `camera.js`'s camera,
  capture, Look and placement sections; `CAMERA_VERBS` and `KEPT_VERBS`.
- Tests: `tests/test_menu.py`: Camera and Picture present on hosts and
  absent below the root; the fullest context (a board, a camera, several
  looks, a chosen shape, several finders, a long folder) holds every ring
  and sub-ring at eight or fewer; no existing node or canvas cell moved; the
  shape and made-piece rings; `tests/conformance/nine_cells.json` updated.
  New `tests/e2e/test_the_loop.py`, launched with
  `--use-file-for-fake-video-capture` on a drawn fixture (the rectangle,
  disc and triangle `test_camera.py` draws): badge, Look from Still and from
  Live, choose an outline, type a width, Make piece, the overlap shows, the
  gizmo clears it, a click on the piece selects the piece, the URL never
  changes; the same with the fixture dropped through `DataTransfer`, and on
  empty canvas. `tests/e2e/test_camera.py` rewritten around the host.
  Walkthrough 11's browser half and 12 §9-11 regenerated.

### Phase 5 — One Kept panel

- Delivers: `apothecary/static/widgets/kept.js`, registered as `kept` in the
  camera panel's seat (Panels › Kept, `PANELS` in menu.py), docked right and
  closed to its tab: the grid (Pin at selected, drag onto a structure),
  Add, Purge, and *Pinned, every site's* (cameras, boards, looks; stale ones
  say so) from one `GET /placed`. A row click selects its host, switching
  site through the picker when the row is another site's.
- Deletes: the rest of `apothecary/static/widgets/camera.js` and its
  registration.
- Tests: new `tests/e2e/test_kept_panel.py`: rows for two sites, stale rows
  and their Pictures › Stale cells, unpin per row, a card pinned at the
  selection, Purge asks once and leaves the folder's own.
  `tests/e2e/test_ring.py` (Kept registered, closed by default);
  `tests/e2e/test_docs_bench_walkthrough.py` §12-13 on Kept.

### Phase 6 — Selected stands at the selection

- Delivers: Selected tethered through `panels.tether` to the selection's
  anchor (the host's top, a shape's centre, the camera's apex): the plan's
  *a piece's properties*. Dragging lets it go; docking is remembered.
  `panels.update` caches panel sizes with a `ResizeObserver` instead of
  reading `offsetWidth` every frame (`apothecary/static/panels.js:300`).
- Deletes: Selected's docked default.
- Tests: `tests/e2e/test_viewer.py`: opens within 300 ms of a click, follows
  within a frame, dock remembered across a reload; the loop test re-run.

### Phase 7 — Old doors closed, with one-screen Phase 5

- Deletes: `POST /photos`, `GET /photos`, `GET` and `DELETE /photos/{name}`,
  `GET /photos/{name}/picture` (`api.py:1149-1283`), `RESERVED_NAMES`,
  `vision/shelf.py`, the album's site face (`vision/album.py` keeps
  `Provenance`), `photo view` with its README line. Nothing in the extra
  uses any of them after Phase 1.
- Tests: `tests/test_photo_in_the_viewer.py` retired, its provenance facts
  already in `tests/test_looks_api.py`; a test holds that no route registers
  a site from a picture, run in the job with the extra installed.

## What is decided here, and what a person decides

Decided by this plan: a picture enters the world only as a look pinned at a
root structure or the floor; no verb switches the site as a side effect; a
piece made from a shape is a root structure of the site on screen, and this
plan refuses to make one unsized; a look's scale is the one width used; one
Kept panel is the §6 list; *pin* is the UI's one verb pair; new ring options
are appended, never inserted; looks are in memory until the record below
says otherwise; `apothecary/vision` stays in core, and only
`apothecary/gathering` and its benches go to `[photos]`, which ships no
viewer surface and registers no site this round; the browser offers a
finder choice only where more than one finder can read the picture.

For a person, and for governance:

- *Personal data stays on the device* §6: confirm that a look is *what a page
  placed or pinned*, listed every site's and taken back the same way; that
  forgetting a kept picture unpins its looks and leaves made pieces marked
  forgotten, each still holding its shape's outline until Reset or Drop;
  that `uploads/` also takes dropped and pasted pictures, pasted ones named
  `<stamp>-paste.png`; that a pin may carry a person-stated width. §1 and
  §7: gathering's install point moves with the extra (Phase 1), and whether
  `apothecary.vocabulary` stays under the guard is settled with it, as the
  record's revision trigger asks.
- Whether looks and made pieces may be kept in the state folder across a
  restart. This waits on what "this machine" means (todo.md).
- *One screen* §1: add "a verb never switches the site as a side effect".
  §3: name the mat, the downward frustum and the outlines as drawn in the
  world. §2: Selected tethered to the selection serves a host, a shape, a
  camera and a piece.
- *rad host integration* §6: its node-ring list is edited to match: Word
  and get shape (Shape) sit under Picture on a made piece, and Why this
  stays apart. Its revision trigger for a ninth option does not fire: the
  fullest node ring is seven.
- The photo-finders plan's open question (the finder choice): answered here
  as Picture › Find, present only when it can do something.

## Not in this plan

Merging `cameras.json` and the firmware bindings into one store; a camera
that looks sideways (direction and field of view are not recorded; a picture
is a view from above); pictures standing upright on a wall; looks below the
root; a gathering face in the browser (when the extra grows one, it pins a
look at a host, never a site); a finder chosen by a model; persistence
across restart, until the record allows it; the CLI's `photo look` and
`build` reading paths outside the picture root.
