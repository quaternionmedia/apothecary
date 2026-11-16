# Surfaces

A surface is something the server keeps and a page shows: a machine's last poll, the
jobs, a projector's picture, a site's lighting levels, the pictures, a whiteboard's
marks, what carlos was last asked to hold. Each is declared by the module that owns it,
in a few lines beside the code that keeps it (`apothecary/surfaces.py`'s `register`):
its name, the frame its coordinates are in, how it is read now, and whether its owner
says when it changes. One read, one stream of changes and one door for what the
family's members found stand on every surface alike (`apothecary/routes/surfaces.py`).

## Frames

| Frame | Coordinates |
|---|---|
| `site_mm` | a site's millimetres, z up |
| `bed_mm` | a machine's bed's millimetres: its working volume as a file counts it, X and Y from the volume's low corner ([The projector](projector.md)) |
| `picture_fractions` | fractions of a picture, across and down from its top left |
| `none` | no coordinates |

## The surfaces

| Surface | Frame | Owner | Read with | Said changed when |
|---|---|---|---|---|
| `machine_status` | `bed_mm` | `apothecary/firmware/devices.py` | `port` | a poll is kept, whoever made it (`notify_status`): the poll, its raw lines left out |
| `jobs` | `none` | `apothecary/jobs.py` | `site`, `port` | a job begins and ends; its progress between is its machine's polls' |
| `projector` | `bed_mm` | `apothecary/routes/projector.py` | `site` and `path`, both needed | a poll of the machine's board, a job of it begun or ended, a calibration kept or forgotten: its picture's `key` and what moves |
| `lighting` | `none` | `apothecary/routes/lighting.py` | `site`, needed | levels or slots are put; what a console's own feed sets between puts is read, not said |
| `pictures` | `none` | `apothecary/routes/pictures.py` | | a picture is kept or forgotten here, and a pile is gathered |
| `whiteboard_marks` | `picture_fractions` | `apothecary/routes/marks.py` | `site` and `view`, both needed | a person's word on a mark or a note |
| `carlos_holds` | `none` | `apothecary/routes/wiring.py` | `site` | a hold is sent to carlos through the hub, with what carlos answered or why it did not; kept in the server's memory |
| `contributed` | `none` | `apothecary/surfaces.py` | `surface`, `by` | a member's observation is kept (below); each observation names its own frame |

## Reading

`GET /surfaces` lists every surface as the table does -- `name`, `frame`, `about`,
`takes`, `needs`, `tells`, `owner` -- and the frames. `GET /surfaces/{name}` reads one
now, with the words of its query:

```json
{"surface": "projector", "frame": "bed_mm",
 "words": {"site": "garage", "path": "printer_1"},
 "snapshot": {"format": "apothecary.projected/1", "...": "the projector's answer"}}
```

A word the surface does not take, or one it needs and was not given, is 422 saying
which; a name no owner declared is 404. A read asks no port anything: a machine's
surfaces are its polls as kept.

## The stream

`GET /surfaces/events` is server-sent events of every change an owner says, of the
surfaces `names` names (commas between; every surface without it), as the owner says
it. `seconds` ends it after that long. Each opening begins with the surfaces it follows:

```text
event: surfaces
data: {"following": ["projector"]}

id: 42
event: change
data: {"format": "apothecary.surface-change/1", "seq": 42, "surface": "projector",
       "frame": "bed_mm", "key": "garage/printer_1", "at": "2026-11-16T20:15:02+00:00",
       "body": {"key": "3f9c0a1b2c3d4e5f", "moving": {"tool": [60.0, 0.0], "...": "..."}}}
```

(`data` is one line on the wire.) `key` says which of the surface changed -- a port, a
job's id, a site, `site/path` of a machine, `site/view` of a view, the surface a
contribution is about -- and `body` what it is now, as its owner made it. A reader that
falls more than 256 changes behind is sent `event: missed` with how many were let go,
and should read the surfaces again. A comment line keeps a quiet stream open every 15
seconds.

The stream relays and asks nothing. It has no poller of its own: a poller of the
server's would contend for a machine's serial link while it prints. A surface no owner
says has changed is silent however long a reader follows it; a machine's polls are
relayed only as someone makes them -- its Machine, the world, the projector's page.
`tests/test_surfaces.py` holds that a reader following every surface, with a link held
and nobody polling, writes not a byte to the port, makes no poll and opens no port.

## Contributed

A member of the family's hub may say what it found about a surface: alfred watching a
camera's frames, joe a performance, each reading the surfaces and the stream and driving
nothing. An observation is posted to `POST /surfaces/contributed`:

```json
{
  "by": "alfred",
  "at": "2026-11-16T20:15:00+00:00",
  "surface": "projector",
  "frame": "bed_mm",
  "key": "garage/printer_1",
  "body": {"saw": "the first layer lifting at the front left", "where": [12.0, 8.5]}
}
```

| Field | |
|---|---|
| `by` | the member's name, as the hub's table names it (`family.json`: `members`, `pull`, `start`); a name it does not hold is 403 |
| `at` | when what it says held, ISO 8601 |
| `surface` | the surface it is about, a declared one; another is 404 |
| `frame` | the frame of the body's coordinates, one of the four; another is 422 |
| `key` | which of the surface, as its changes key it; optional |
| `body` | a JSON object of the member's own, at most 16 KB |

It answers 201 with the observation as kept, `format` `apothecary.contributed/1` and the
server's `recorded_at` added; it is relayed on the stream as a change of `contributed`
keyed by the surface it is about. The newest 200 of each surface are kept in the state
folder's `surfaces/contributed.json`, written whole under one lock, and read back by
`GET /surfaces/contributed?surface=&by=`, newest first.

The route is under the app's guard as every route is (`apothecary/stays_local.py`): it
answers this machine alone, and no page of another origin may post to it. `by` is what
the member says it is; nothing on this machine proves it.

## What would move to the stream

The world page polls what the stream could carry; none of it is moved yet. Each would
move once its owner says its change:

- `apothecary/static/lighting.js` asks for a site's levels every 200 ms; the `lighting`
  surface says each put, but the console's own feeds (sACN, OSC) set levels without one,
  and would say so first.
- `apothecary/static/boards.js` asks which ports are armed every two seconds; the
  control latch is no surface yet.
- A board's poller in `boards.js` is the poll itself and stays one; a page whose board
  another client already polls could take that client's polls from `machine_status`
  and poll less.
- `apothecary/static/widgets/working_space.js` asks for the evidence document every five
  seconds; a kept poll is said on `machine_status`, which could ask for it instead.
- `apothecary/static/widgets/family.js` and `procedure.js` ask the hub every two seconds;
  the hub's deliveries are no surface, and hearth's `/family/members/<name>/events`
  streams a pull member's own.
- `apothecary/static/widgets/tasks.js` follows a firmware task every half second, and
  the page's render queue every 700 ms; neither is a surface.
