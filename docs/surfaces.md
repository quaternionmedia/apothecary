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
| `jobs` | `none` | `apothecary/jobs.py` | `site`, `port` | a job begins and ends, and while it runs when its stage changes or its progress passes a whole percent (below) |
| `projector` | `bed_mm` | `apothecary/routes/projector.py` | `site` and `path`, both needed | a poll of the machine's board, a job of it begun or ended, a calibration kept or forgotten: its picture's `key` and what moves |
| `lighting` | `none` | `apothecary/routes/lighting.py` | `site`, needed | levels or slots are put, and as a console's own feeds (sACN, OSC) set levels or status: at most every 0.1 s, the last change of a burst told at the receiver's next idle look |
| `pictures` | `none` | `apothecary/routes/pictures.py` | | a picture is kept or forgotten here, and a pile is gathered |
| `whiteboard_marks` | `picture_fractions` | `apothecary/routes/marks.py` | `site` and `view`, both needed | a person's word on a mark or a note |
| `carlos_holds` | `none` | `apothecary/routes/wiring.py` | `site` | a hold is sent to carlos through the hub, with what carlos answered or why it did not; kept in the state folder's `carlos-holds.json`, read back at start |
| `tune` | `none` | `apothecary/firmware/loops.py` | `port` | a heater experiment's stage or whole percent changes, or every 5 s of its own clock: the experiment as `GET /firmware/printers/loops/job` has it (its reading, target, power, result), keyed by the port; and once more as it ends |
| `control_loop` | `none` | `apothecary/firmware/loops.py` | `experiment`, `port` | an experiment is kept: its `control/loop/1` document, `{"experiment", "document", "error"}`, keyed by the experiment's id; read with `experiment` for one, else the kept experiments (of a `port`) without their samples |
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

## A job's stages

A job on the stream is a change of `jobs` keyed by the job's id, whose `body` is the job as
`GET /jobs/{id}` has it, less its `log`. One is told when the job begins (`outcome`
`running`, `detail.stage` `starting`), when its stage changes -- a print's `printing`,
`paused`, `printing` again, `finishing` and `cancelling`; a router's cut says `running`; a
tune's `running` -- when its `progress` passes another whole percent, and when it ends (`outcome` `done`, `cancelled`
or `failed`, `detail.stage` the same). Between those it is silent: not on every line, and
no timer of its own, the job's own thread says it as it sends. Each stage holds for as
long as it holds, so a reader that follows from the start hears them in order:

```text
event: change
data: {"format": "apothecary.surface-change/1", "seq": 43, "surface": "jobs", "frame": "none",
       "key": "20261118T101500123Z-dev_ttyUSB0", "at": "2026-11-18T10:15:03+00:00",
       "body": {"id": "20261118T101500123Z-dev_ttyUSB0", "kind": "print", "outcome": "running",
                "progress": 0.31, "detail": {"stage": "paused", "sent": 1240, "total": 4000}}}
```

The stream still polls nothing: what is told is what the job's thread already holds, and
no job's state is built while no reader follows the jobs.

A tune's stage and progress are also on `jobs` (above); `tune` adds what the experiment
reads. `control_loop` builds the document with the design's defaults (`simc`, `pi`) from the
kept experiment alone and never reads the board's gains (`read_board`); an experiment with
too little to identify a plant is told with `document` null and an `error`.

## Contributed

A member of the family's hub may say what it found about a surface: alfred watching a
camera's frames, joe a performance, each reading the surfaces and the stream and driving
nothing. An observation is posted to `POST /surfaces/contributed`, with the member's own token
([A member's token](#a-members-token)):

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
| `by` | the member's name, as the hub's table names it (`family.json`: `members`, `pull`, `start`); a name it does not hold is 403, and the token must be that member's: 401 |
| `at` | when what it says held, ISO 8601 |
| `surface` | the surface it is about, a declared one; another is 404 |
| `frame` | the frame of the body's coordinates, one of the four; another is 422 |
| `key` | which of the surface, as its changes key it; optional |
| `body` | a JSON object of the member's own, at most 16 KB |

It answers 201 with the observation as kept, `format` `apothecary.contributed/1` and the
server's `recorded_at` added; it is relayed on the stream as a change of `contributed`
keyed by the surface it is about. The newest 200 of each surface are kept in the state
folder's `surfaces/contributed.json`, written whole under one lock, and read back by
`GET /surfaces/contributed?surface=&by=`, newest first. A file that does not read whole is
never read as fewer: a read of it answers 503 and leaves it, and a post moves it aside as
`surfaces/contributed.unreadable-<time>.json`, answers 503 naming that file, and keeps
nothing; the next post starts a file of its own.

The route is under the app's guard as every route is (`apothecary/stays_local.py`): it
answers this machine alone, and no page of another origin may post to it.

### A member's token

`by` is a claim; the token proves it. The hub makes each member a secret when the member
is added (`apothecary family add NAME URL`, or `apothecary family token NAME` for a
member already in the table), shows it once to the person who made it, and keeps only
its SHA-256 in `family-tokens.json` in the state folder, readable by this account alone.
The member sends it on every post, in the one header:

```text
Authorization: Bearer <the member's token>
```

| Answer | When |
|---|---|
| 201 | the token is `by`'s own |
| 401, `WWW-Authenticate: Bearer` | no `Authorization` header, a scheme other than `Bearer`, a token that is not `by`'s (another member's included), or a `by` the hub holds no token for |
| 403 | `by` is no member the table names |

A 401 never carries a token, and none is logged or returned by any route: the list of
members (`apothecary family members`) says only whether a member holds one.

**A member in the table with no token is refused.** Before tokens the table's names were
enough, so a table written earlier names members that hold none. They are refused until
the owner makes them one, and nothing is let through on the old footing:

```text
apothecary family token alfred     # shown once: give it to alfred
apothecary family token joe
```

### The simulated server's members

`apothecary serve --simulated` keeps a state folder of its own (`.cache/simulated/state`)
whose table names `alfred` and `joe` and holds these tokens, so a sibling can be tried
against it. They are published here because that folder is the simulated server's alone;
a real hub makes its own and shows each once.

| Member | Token |
|---|---|
| `alfred` | `simulated-alfred-token` |
| `joe` | `simulated-joe-token` |

```text
curl -X POST http://127.0.0.1:6283/surfaces/contributed \
     -H 'Authorization: Bearer simulated-joe-token' -H 'Content-Type: application/json' \
     -d '{"by": "joe", "at": "2026-11-18T10:00:00+00:00", "surface": "jobs", "frame": "none",
          "body": {"saw": "a performance"}}'
```

A table or a token already in that folder is kept as it is.

## What would move to the stream

The world page polls what the stream could carry; none of it is moved yet. Each would
move once its owner says its change:

- `apothecary/static/lighting.js` asks for a site's levels every 200 ms; the `lighting`
  surface says each put and each console feed's change, and a page could take them from
  the stream.
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
