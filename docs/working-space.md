# The Working space

A site as every kind of evidence has it: what is there, what state it is in,
how that is known, and what changed. The plan it builds toward, its decisions
and its open questions are
[plans/working-space-view-2026-10-30.md](plans/working-space-view-2026-10-30.md).
What exists is a printer's polls and the frames its cameras keep with them.

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

*Working space* is a window of the viewer, closed until asked for:

- **Panels › Site › Workspace** opens it on the whole site: every subject the
  log has said of, each property's value, how it is known, and whether its
  source is still heard or the value is last known.
- **Camera › Workspace** on a printer's ring opens it on that printer: its
  state as a strip and its heaters as lines over the last hour, and a row for
  each camera that looks at it, with the frames kept at its polls. While open,
  it watches the printer's board and keeps a frame set with its polls: a frame
  from each of those cameras whose device is this browser's, when the
  printer's state changes and at every 5 % of its progress, never closer
  together than ten seconds.

Each mark and each row opens its evidence underneath: a frame, and the poll
it was kept with, every line the printer sent.

## Doors

| Door | What it answers |
|---|---|
| `GET /sites/{s}/evidence?at=&since=` | the `apothecary.evidence` document: every subject, each value at `at` with its sources and evidence, and the transitions, series and frames since `since` |
| `GET /sites/{s}/evidence/printers/{path}` | the port a printer's board answers on, and the cameras that look at it |
| `GET /evidence/polls/{id}?space=` | one poll, every line the printer sent |
| `POST /photos/pictures?site=&camera=&poll=` | a frame kept with a poll |
| `apothecary evidence show` | every subject and its values, from the log |
| `apothecary evidence changed --since 1h` | what changed in the span |
| `apothecary evidence budget printer_1 [--gb N]` | a printer's kept frames, and its budget |
