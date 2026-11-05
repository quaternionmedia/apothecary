# The Working space

A site as every kind of evidence has it: what is there, what state it is in,
how that is known, and what changed. The plan it builds toward, its decisions
and its open questions are
[plans/working-space-view-2026-10-30.md](plans/working-space-view-2026-10-30.md).
What exists is a machine's polls -- a printer's or a router's -- and the frames its cameras keep with them.

## What is kept

Every poll of a printer whose board is pinned in a site is kept as
observations (`apothecary/evidence/`), in one format for every source,
`apothecary.observation`: a subject (`garage:printer_1`,
`garage:printer_1#heater:bed`), a property, a value with its unit or the
reason there is none, its origin (`measured`, by the poll's commands), when it
held, and the evidence it rests on by reference (the poll's id, the pin). A
poll of a port no pin names is kept as a sighting, `usb:<its identity>`.

Only what changed is written: a word when it changes, a number past its
tolerance, the board's `present` at least once a minute while polled, and
every value at least every few hours. The poll an observation rests on is
written beside it with every line the printer sent.

A frame the Working space keeps with a poll is kept under the picture root's
`captures/`, as any camera's frame is, and recorded beside that poll. It is
not the camera's view. A printer's kept frames live under a budget, 5 GB
unless set otherwise; past it the oldest are forgotten first. A picture taken
by hand is never counted or forgotten.

Everything lives in the state folder, `<state>/evidence/<site>/`, a folder a
site, private to the account, and is never sent anywhere:

| File | Holds |
|---|---|
| `observations/<day>.jsonl` | one observation a line |
| `polls/<day>.jsonl` | the polls observations rest on, every line each sent |
| `frames/<day>.jsonl` | the frames kept with polls, and those forgotten since |
| `budgets.json` | a printer's frame budget, where one was set |

## The window

*Working space* is a window of the viewer, closed until asked for.
[Walkthrough 18](../walkthrough/18-the-working-space.md) goes through it from
each of its doors, written by the browser test that does it.

Its first line, under the title, names the next step and carries the button
that takes it, whichever door opened it: choose a printer; add a camera above
it; choose a camera's device; or, with every camera this browser's, when
frames are kept and Keep a set now. The status line says the same.

- **⊞ Windows › Working space**, or **Panels › Site › Workspace** on the
  canvas ring, opens it on the whole site: a row for each printer a board
  pinned here drives -- what it is doing, whether it is answering, how many
  cameras look at it, and its hour's button -- then every subject the log has
  said of, named as a person names it (printer_1 › bed heater), each value
  with how it is known and when.
- **Camera › Workspace** on a machine's ring, or its row's button, opens it on
  that printer: its state as a strip and its heaters as lines over the last
  hour, a key under them, and a row for each camera that looks at it, with the
  frames kept at its polls. ‹ and the site's name go back.
  - A camera row whose device is not this browser's has a box to choose one,
    or Allow when the browser has not been asked; a printer no camera looks at
    has *Add a camera above* it, as Camera › Add here does.
  - While open, it watches the printer's board and keeps a frame set with its
    polls: a frame from each of those cameras whose device is this browser's,
    when the printer's state changes, at every 5 % of its progress and when a
    camera is newly this browser's, never closer together than ten seconds.
    Closed, it keeps none, even while the printer's Machine polls it.
  - Under the rows, how much its kept frames take of their budget, and a box
    to set it.

Each dot, frame and row opens its evidence under the timeline -- a frame, and
the poll it was kept with, every line the printer sent -- and × closes it.

## Doors

| Door | What it answers |
|---|---|
| `GET /sites/{s}/evidence?at=&since=` | the `apothecary.evidence` document: every subject, each value at `at` with its sources and evidence, and the transitions, series and frames since `since` |
| `GET /sites/{s}/evidence/printers` | each printer a board pinned in the site drives, as the next door answers it |
| `GET /sites/{s}/evidence/printers/{path}` | the port a machine's board answers on, the cameras that look at it, and what its kept frames take of their budget |
| `PUT /sites/{s}/evidence/printers/{path}/budget` `{gb}` | that budget set |
| `GET /evidence/polls/{id}?space=` | one poll, every line the printer sent |
| `POST /photos/pictures?site=&camera=&poll=` | a frame kept with a poll |
| `apothecary evidence show` | every subject and its values, from the log |
| `apothecary evidence changed --since 1h` | what changed in the span |
| `apothecary evidence budget printer_1 [--gb N]` | a printer's kept frames, and its budget |
