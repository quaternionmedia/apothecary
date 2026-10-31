# A working space, seen from every kind of evidence at once: a plan

*Not built. Queued behind the camera on the Ender 3, whose tie to the printer's
polls is its first slice. The image models served through qmcp, an
always-optional source of readings off a picture, are planned beside it in
`docs/plans/image-models-through-qmcp-2026-10-30.md`, not yet on this branch.*

## What this plans

A working space is a place where things are made and run: the garage with the
Ender 3 and its bench, a rig on a stage, the airgap's test rig, a server room.
Apothecary already knows such a place in pieces:

- the site draws what is meant to be there;
- a port says which board answers, and a poll what the printer is doing;
- a camera keeps a frame, and a picture read through a pinned face says which
  sockets have a plug;
- a person pins a board to a node, flashes a sketch, starts a print.

Each piece is right about what it sees and says nothing about the others.

This layer joins them into one view of the place, which answers four questions
at any moment:

- **What is here**: every subject some evidence speaks for, and every subject
  the site expects that nothing speaks for.
- **What state it is in**: each subject's properties, with every source's value
  side by side.
- **How we know**: for each value, where it came from (a person's word, an
  instrument, a reading off a picture, a model's guess, or a rule over other
  observations) and the evidence itself: the frame, the poll, the answer.
- **What changed**: between two moments, every transition, with the evidence
  on each side of it and the actions and directives nearest it in time.

Every line the view shows names the observations it rests on, and every
observation names its evidence. A line that cannot is not shown.

## The rules it stands on

Org records, which this layer applies and does not relax:

- *Nothing is both a claim and its own evidence*: a claim carries who made it,
  a measurement carries its method and its moment, and the two are shown
  together and never reconciled into one number.
- *A disagreement is a delta*: named by the address and field that disagree,
  neither value discarded; detection decides nothing, convergence is reported
  rather than concluded, and closing is a person's.
- *The monitoring seam, and instance identity*: a view reads a document and a
  collector reads the world; identity is asserted before a measurement is
  attributed; a view does not render a quiet state it has not earned.
- *Shrink the black box*: a model is never the check, and its calls go through
  qmcp, the one door that counts them.
- The charter's *a person is interrupted only by a decision*.

Apothecary's own:

- *Personal data stays on the device* (qm#121, open): personal data lives in
  the state folder, the picture root and the page's `localStorage`, and nowhere
  else.
- Gathering's rule for a person's word (`apothecary/gathering/judgement.py`):
  it wins over the machine, it carries, and it is also a measurement; two
  people who disagree are refused, not averaged.

## The sources

| Source | What it says now | Where it is read |
|---|---|---|
| Cameras, one or several on a place | A frame at a moment, from a pose and a lens | `vision/cameras.py`; frames under `captures/`, or a concert's folder |
| Serial: a printer | Its state, heaters, position, endstops, filament, job progress, at each poll; what it is, at `M115` | `firmware/devices.py`, `gcode.py`; `PrinterStatus` |
| Serial: a board | Which port answers, its identity, its chip, its hello | `firmware/devices.py`: detected, probed, expected, observed |
| Sensors | A printer's thermistors, endstops and runout switch, through its poll; a lighting console's levels, received on the local network | the poll; `console_feedback.py` |
| A picture, read | Each control's value and each socket's plug, with why one was not read | `rig/look.py`, `rig/reading.py` |
| A person | Pins, faces pinned, answers, a print started, a sketch flashed | `bindings.py`, `rig setup`, `gathering/judgement.py`, the routes |
| Image models, optional | Quantity, size, shape, material, colour, through qmcp | the sibling plan |

## The model

### A subject

A subject is something the view says things about. Its address is the one
apothecary already uses for it:

| Subject | Address | Example |
|---|---|---|
| a node of a site | the site and the node's dotted path | `garage:printer_1.mainboard` |
| a part of a node | the node's address and a facet: a jack, a control, a heater, a face | `garage:printer_1.mainboard#jack:usb`, `garage:printer_1.mainboard#heater:bed` |
| a module of a rig | the rig's name and the module's id, as its `carlos.patch` has it | `subharmonicon-complex:dfam#control:cutoff` |
| a board no node names | `usb:` and its identity, as `wiring/patch.py` names it | `usb:A106ZTEU` |

A registered part (`part_ref`) is a kind and never a subject: two nodes drawn
from one part are two subjects.

Each source names things its own way: a camera by a region of its frame, serial
by a port, the firmware state by a board's identity, a person in words. The
layer keeps **links** from a source's name to a subject, and a link is itself
an observation, with its origin and its evidence:

| Link | Made by | Origin |
|---|---|---|
| a board's identity to a node | a pin (`ManualBinding`) | a person's word |
| | the board last flashed with the node's sketch (`binding_source` `sketch`) | a rule over the flash record |
| a port to a board's identity | its USB serial number or MAC, as it answers (`stable_identity`) | an instrument |
| a region of a frame to a face, a jack, a control | a face pinned by its four corners (`rig setup`) | a person's word |
| a camera to the subjects in its view | its pose and lens projected onto the site's footprints (`vision/cameras.py`, `projection.py`) | a rule over the site's geometry |
| a region to a subject | a model's label | a guess, never enough alone |

Two rules govern links, and each is already in the code in one place:

- **Identity before attribution.** An observation whose source name has no link
  to a subject is kept as an unattributed **sighting** and shown as one; it is
  never attached to the likeliest subject. A port answering with no pin is
  already `usb:<identity>` in the wiring, and a region of a frame that no face
  covers is a sighting the same way.
- **A pairing is made only when it is the one there is.** The concert follower
  moves a lead's plug to a socket only when one socket takes it
  (`rig/reading.py`). Links follow the same rule: two links that send one name
  to two subjects are a conflict, shown, and nothing is attributed through
  either until a person settles it.

A port's number moves between plugs; a link is to the board's identity, never
to the port, as a pin is now.

### An observation

One thing said about one subject at one moment:

| Field | Holds |
|---|---|
| `subject` | a subject's address, or a sighting: a source's own name, a port, or a frame and a region |
| `property` | from a closed list per facet: `present`, `state`, `firmware`, `plugged`, `value`, `temperature`, `target`, `progress`, `position`, `endstop`, `filament`, `moving`; the image models add `quantity`, `size`, `shape`, `material`, `colour` |
| `value`, `unit` | the value, and its unit: `°C`, `mm`, `fraction`, or none for a word |
| `confidence` | from 0 to 1 as its source gave it, never rounded up; empty where a source gives none |
| `origin` | its kind and what produced it (below) |
| `at` | when it was true: a frame's taken time, a poll's `polled_at` |
| `recorded_at` | when it was written, which may be later: a frame read afterwards |
| `evidence` | references to what it rests on: a frame and a region, a poll and its lines, a person's record, a qmcp invocation, other observations |

| Origin | Is | Carries |
|---|---|---|
| `stated` | a person's word: a pin, an answer, a face pinned, a directive's expectation | who said it |
| `measured` | an instrument: a port answering, `M115`, a poll's `M105`, `M27` and `M114`, a sketch's hello | the method: the command, the module that found the port |
| `read` | arithmetic over a picture, the same answer for the same pixels: `rig/look.py`'s controls and sockets, a difference between frames | the reader and its version; the contrast it read on, as the confidence |
| `guessed` | a model's answer, through qmcp | the tool, the model and its version, the qmcp invocation |
| `derived` | a rule in this layer over other observations: a lead seen because its board answers; a state carried until something changes it | the rule, and the observations it took |

**Unread is not a value.** A control the reader could not read, a face not in
the picture, a model that declined, a poll that timed out: each is an
observation that says so and why, as `look.Seen.why` does, and none of them
reads as absent, as idle, or as the value before. Absence is what an instrument
measures (a port that stopped answering) or what a person states.

### Agreement and disagreement

For a subject and a property, the view puts every source's latest value side by
side and says one of four things:

- **Agreed**: two or more sources give the same value within the window that
  pairs them. The USB lead to `printer_1` answering on its port, and a plug seen
  in the mainboard's USB socket in the frame kept with the same poll, is *seen
  both ways*. Two kinds of origin is the stronger agreement; two cameras
  through one reader share that reader's blind spots, and the line says which
  agreement it is.
- **One source**: one source says, and nothing else is placed to.
- **Disagreed**: the values differ. Both are shown, each with its origin and
  evidence, and neither is the state. The disagreement is a delta: named by the
  subject and property, opened when first seen, and found again, not opened
  again, on the next frame or poll. When the values agree again the view says
  since when and leaves it open; a person closes it.
- **Unknown**: nothing has said, or everything that said is older than its
  budget.

Two precedences are decided, and one is proposed:

- **A person's word wins over a guess.** Where a model's answer and a person's
  differ on a subject and property, the person's is the state, without
  argument. The guess is kept beside it: it is a case where the truth is known,
  and it scores the model, as an answer in gathering scores the sorting.
- **A guess never raises a level on its own.** `warn` or `fault` on a subject
  rests on at least one observation that is not a guess. A guess alone is shown
  as one, at `none`.
- *Proposed:* a person's word against an instrument or a reading is a
  disagreement like any other, not a win. A person says the lead is in and the
  port does not answer: each is true of something, and which one it is, is the
  person's to say when they close it (*Open*, 4).

Levels are the wiring's (`none`, `ok`, `warn`, `fault`). A level is computed
from the observations by rules a test holds, and never set by hand.

### Time

Three things carry time, and the layer keeps them apart:

- **Frames**: a picture taken at a moment, by a camera standing somewhere.
  `captures/` names them by the moment, a concert folder by order;
  `rig/concert.py`'s `taken` reads the moment from a PNG's text, a JPEG's EXIF
  time or the file's time, and the observation records which it was.
- **Polls**: a sample taken on a schedule: a printer every couple of seconds, a
  port scan, a hello. A poll gets an id when it is written, and
  `last_statuses()`, the newest poll per port, becomes a history.
- **Events**: something that happens at a moment: a flash, a job beginning and
  ending (`jobs.py`'s `LISTENERS`), a pin made, a plug moved (derived from two
  frames), a cue fired, a directive given, a person's action.

A **state** is derived: a property holds the value an observation gave it until
another changes it. The concert follower's leads, carried from frame to frame,
are this rule for one property. Each kind of source has a **staleness budget**,
past which its last value is shown as *last known at*, not as *is*: a poll after
a few of its periods, a frame after the camera's cadence. The view does not show
a quiet state it has not earned.

Pairing in time is exact where it can be built in, and a window where it cannot:

- a frame kept *for* a poll carries the poll's id, so the pair is exact;
- a frame and a poll kept apart are paired by nearest time within the poll's
  period, and the gap is shown;
- a frame whose clock is not this machine's (a phone's time-lapse) carries its
  time source and is never paired exactly.

**What changed** between two moments is the list of transitions in that span,
per subject and property, each with the evidence before and after it and the
nearest actions and directives before it. The view shows nearness and never
says *because*: a lead plugged a minute after a person flashed a board may have
been plugged for another reason.

### Directives, actions and goals

These are a person's records, kept beside the observations and addressed the
same way:

- **A goal** is what the person is working toward: *print the bracket in PETG*,
  *the Uno's power and USB read true*. It names the subjects it concerns and,
  where it can, a *done when* written over observations: the job ended `done`,
  and the bed is not empty in the frame after. When that holds, the view
  reports the goal *met*, and the person closes it, or drops it. Done is a
  claim about work, and the layer does not make it.
- **A directive** is an instruction about the space. Some say what to keep: *a
  frame at each poll while printing*, *watch the USB lead*. Some state an
  expectation, which becomes a `stated` observation to compare against: *the
  bed stays under 60 °C*, *the DFAM's cutoff is at noon for this song*. The site
  as drawn is already a directive of this kind: a node that names firmware is
  expected plugged in.
- **An action** is something done. What apothecary does at a person's word, it
  records without asking: a flash, a print started or cancelled, a pin, a
  camera added or moved, an answer given. What a person does by hand, a lead
  plugged or a spool changed, is observed or stated.

A model may propose a goal or a directive. It is a proposal until a person takes
it, and is recorded as theirs only then.

## What it stores, and where

The layer adds no fourth place for personal data:

- **The state folder** (`state_dir()`, private as the firmware state is), one
  folder per space:
  - `observations/`, one append-only JSON-lines file a day, written under the
    state lock;
  - `links.json`, the links, each with its origin;
  - `intent.jsonl`, the goals, directives and actions;
  - `deltas.json`, the disagreements, open and closed, keyed by subject and
    property.
- **The picture root**: the frames, under `captures/` as now, or in a concert's
  folder. An observation points at a frame by its path and a region, and the
  layer copies no picture. A concert's `readings.jsonl` stays beside its frames
  as the concert's own record, which the layer reads.
- **The page's `localStorage`**: the window's layout, and nothing about the
  space.

The package reads personal data, so it is an install point of the stays-local
guard, as `rig` and `gathering` are. Nothing of what it keeps is committed, and
its writer refuses a path inside a repository. A person's goals and directives
are personal data like the rest. Backups are the person's.

How much is kept is a cost to decide. A frame at every poll of a long print is a
frame every couple of seconds for hours, so slice 1 keeps one when the poll's
state changes, at each step of progress, and otherwise no oftener than a
directive says, and the folder's size is shown where its frames are listed
(*Open*, 3).

## What reads it

A collector reads the world, and a view reads a document. The layer is three
parts:

- **Collectors** write observations to the log, each from one source: an entry
  in `STATUS_LISTENERS` for printer polls, one in `jobs.LISTENERS` for jobs, the
  wiring's port scan, the picture route when a frame is kept, the rig
  follower's readings, the routes a person acts through, qmcp's answers.
- **The view** reads the log and writes one document, `apothecary.evidence`
  version 1: for a space, a moment and a span, the subjects, their properties
  with every source's value and origin, the agreements, the open deltas, the
  transitions and the goals. It is pure: the log is its argument, and it imports
  nothing that opens a port, a file or a socket.
- **Renderers** read that document and nothing else:
  - **The viewer.** A window, as every section of the page is (`panels.js`),
    called *Working space*. It lists the subjects with their states, and each
    line opens its evidence: a frame with its region drawn, a poll's lines, a
    person's record. A strip under it scrubs through time, and *what changed* is
    the span between two marks. The 3D view can colour a node by its level.
    `GET /sites/{s}/evidence?at=&since=` answers the document.
  - **Carlos.** The seam does not change: the hold action on `POST
    /family/cue`, a `carlos.patch`, and each module's, lead's and jack's state
    as a level and its lines. The lines come from the document, so each says
    what it rests on: *seen: answering on its port; seen plugged in camera_1 at
    14:02*, or *disagree: answering on its port; no plug seen in camera_1 at
    14:02*. Carlos judges none of it, and refuses fields it does not define, so
    the evidence stays in apothecary.
  - **qmcp's human queue** (`POST /v1/human/requests`). Only a decision goes
    there: a delta at `warn` or `fault` that has not converged within its
    budget, a sighting that needs a person to say what it is, a goal reported
    met. A request carries the subject, both values with their origins, and the
    evidence by reference; the answer comes back as a `stated` observation or a
    link, its claimant the person who answered. The same decisions can be
    answered in the window; qmcp is the door for a person away from it, its
    voice path among them.
  - **The command line**, for machines and debugging: `apothecary evidence
    show`, `apothecary evidence changed --since`.

`apothecary problems` lists the open deltas beside its problem space
(`apothecary/spaces.py`), which is a different thing. This layer is called
*evidence* in code, so the two do not meet by name.

## What exists, and what it generalises

| Here now | What it does | What this makes of it |
|---|---|---|
| `wiring/patch.py`: `Evidence`, `State`, `ModuleState`, `LeadState` | The bench's states (present or absent, firmware, leads seen or declared, how known) as levels and lines, with the evidence beside the patch | The closest thing to this view, for the bench at one moment. `Evidence` becomes observations with origins; `_state`'s lines become a renderer over the document, with the same levels by the same rules; the patch stays |
| `firmware/devices.py`: detected, probed, expected, observed, identified | Five views of one board, kept apart so the page can show where they disagree | Five origins; the principle is this plan's, for one board |
| `devices.last_statuses()`, `STATUS_LISTENERS` | The newest poll per port, in memory, and the hook every poll passes | A collector on the hook, and a history in place of the newest alone |
| `firmware/bindings.py`: `NodeBinding.binding_source` | A board tied to a node by a pin or by its sketch | Links, each with its origin |
| `jobs.py`: a job's record, `LISTENERS` | When a print began and ended, and how far it got | Events, and what a goal's *done when* reads |
| `vision/cameras.py`: pose, lens, `lands` | Where a camera stands and where its centre ray lands | Which subjects each camera can see; several cameras on one place |
| `rig/look.py`: `Seen`; `rig/reading.py`: faces, `held` | Each control and socket read off a picture, with why one was not | `read` observations, unread kept as unread, a face as a link |
| `rig/concert.py`: frames in order, leads carried, `readings.jsonl` | A rig followed through time, a plug moved only when the pairing is unique | The state-carrying rule and the pairing rule, made general |
| `gathering/judgement.py` | A person's word wins, carries and scores; two people who disagree are refused | The precedence of a person's word, for every subject |
| `console_feedback.py`: `ConsoleState` | A console's levels, received on the local network | A sensor stream of the same shape, for a theatre |
| `airgap_metrics.py`: `airgap/metrics/1` | The Airgap panel's prediction, as a document a view reads | An expectation beside the test rig's readings |
| `Assembly.status` | One value on a node, overwritten by each poll's site sync | A summary drawn from the document; the history is the log's |

What it replaces, once each renderer reads the document: the wiring's
line-building in `_state`, and `_LAST_STATUS` as the only memory of a printer's
polls. Slice 1 replaces nothing.

## The first slice: the Ender seen by its camera and by its port

A camera goes on the Ender 3 next, to tie printer monitoring to it. What is
ready: `camera_1`, added on `printer_1`'s ring, its device one of the browser's
cameras, with Live and Take picture; the printer's Machine polling it; the
mainboard's polls reaching carlos as lines; `rig setup` and `rig follow`. The
bench plan's *Next: a camera on the Ender* names three pieces the tie needs.
This slice puts them in order and lays the layer under them, one pull request a
step, stacked.

1. **The log, and polls into it.** The observation, its origin, the evidence
   reference and the append-only log in the state folder; a collector on
   `STATUS_LISTENERS` that writes each poll of a pinned port as observations of
   the node it is pinned to (`present`, `state`, each heater's `temperature` and
   `target`, `progress`, `endstop`, `filament`), and a poll of an unpinned port
   as a sighting. Each poll gets an id, and its raw lines are its evidence. A
   test on `serve --demo`'s simulated Ender holds it: polls in, observations
   out, the pin as their link.
2. **Frames kept with polls.** The page holds the camera and drives the polls,
   so the page keeps the frames: while `camera_1` is Live and `printer_1` is
   polled, a frame when the poll's state changes, at each step of progress, and
   no oftener than a directive's cadence, posted to the picture route (`POST
   /photos/pictures?site=&camera=`) with the poll's id. The route keeps the frame
   under `captures/` as now, and writes it as evidence beside that poll. That
   is a print's record of polls and pictures, readable as a timeline before any
   picture is read, and a folder `rig follow` reads. The *Working space*
   window's first form is `printer_1`'s timeline: state and heaters as a strip,
   the frames at their polls.
3. **The lead, seen two ways.** The Ender's side faces laid out: the mainboard's
   USB socket and the power inlet placed as fractions of their face, as the
   Uno's edge is, measured off `camera_1`'s own frames, and pinned once with
   `rig setup`. Each kept frame is read through the face, and the USB lead's
   `plugged` from the picture stands beside its port's `present`. The lead's
   state in carlos says both, and where they disagree. It is validated as the
   Uno is: the lead in and out by hand with the camera fixed, and what was read
   against what was there, in `docs/validation/`.
4. **Moving, seen two ways.** A frame compared with the frame before it inside
   the gantry's face: `moving`, read, with the difference as its confidence,
   beside the poll's `printing` or `idle`. A print the poll calls printing while
   nothing moves across several frames is a delta at `warn`: a pause, a stall,
   or a camera knocked aside. The view names those and decides none. This is
   arithmetic, not a model; changing light is its known weakness, and it is
   measured on the Ender's own frames before any threshold is trusted.

After step 4 the four questions have answers for one printer: `printer_1`, its
mainboard and its lead are here; it is printing, at these temperatures, and seen
moving; that is known by its port and by `camera_1`, each line opening its poll
or its frame; and the window shows what changed in the last hour. The image
models' readings (whether a part is on the bed, its colour, a print gone to
spaghetti) arrive as guesses once the sibling plan's first slice is built, and
change none of the above.

## The slices after it

Each follows once the one before it reads real evidence.

- **The rig through a concert.** The concert's readings become `read`
  observations of the rig's modules, the follower's carried leads the derived
  state, and the hub's cues events (the concert plan's slice 5). A setlist is a
  directive: each song's expected values beside the readings. Two cameras on
  one rig, each with its own setup: a control both see is seen both ways, and
  one a player stands in front of is unread in one camera and read in the
  other, never absent.
- **The airgap's test rig.** Three origins for one property: the Airgap panel's
  prediction (`airgap/metrics/1`), the dials and gauges read off a picture, and a
  board on the rig reporting over serial. A board's readings need a line format
  for sensors, which is a seam of its own (*Open*, 9).
- **A server room.** Racks are faces, patch panels are sockets, a camera looks
  along each row, and the room as drawn is the expectation. What a switch says
  of its own ports arrives over the network, which the stays-local guard
  refuses; until a record allows it, the room is known by camera and by what a
  person states.

## The governance it needs

Drafted when its slice is built, in `governance/qm/adr/` on
`project/apothecary`, and ratified by a person:

- **A project record for the evidence model**: the observation's fields, the
  origin kinds, unread as no value, identity before attribution, a pairing only
  when unique, a person's word over a guess, a guess never raising a level on
  its own, every rendered line naming its observations. It tightens the org
  records above. Its teeth are tests, each seen to fail: a renderer handed an
  observation with no evidence refuses it; a guess alone yields `none`; two
  links for one name attribute nothing.
- **An amendment to *Personal data stays on the device*** (qm#121, open). §6
  names the log, the links, and a person's goals and directives in the state
  folder, and the frames' retention; §1 names the new package as an install
  point. It also says whether carlos and qmcp, reached over loopback on this
  machine and each keeping its own database, are *here*: carlos already holds
  the bench's states, and qmcp would hold a person's questions and answers. A
  capture on the server, if chosen (*Open*, 2), is a subprocess outside the
  socket guard that the record names, as it names OpenSCAD.
- **For governance/qm**: whether *A disagreement is a delta* covers a working
  space's runtime state. Its rule (one delta per address and field, closed by a
  person) fits this layer; its queue is the organisation's, and a garage's lead
  disagreeing with its port does not belong in it. A project cannot relax an
  org record, so the record's scope has to say where it stops.
- The site hierarchy record (`DRAFT-site-structure-substructure-feature-hierarchy`)
  gains a reader of its node addresses, and a facet after them that is this
  layer's.

## Open, for the owner

1. **Which comes first on the Ender**: frames kept with polls (recommended:
   it needs no faces, and everything after it reads its folder), the lead seen
   two ways, or the faces laid out.
2. **Who takes the frames during a print.** The page, as built, which needs the
   tab open and Live for the length of the print; or a capture on the server, a
   subprocess reading the camera device, which runs with no page open.
3. **How long frames are kept**, and who forgets them. The page forgets only
   what the browser put there, and frames kept for a print are that.
4. **A person's word against an instrument**: a disagreement to close
   (proposed), or the person's word as the state until it is closed.
5. **Where a person's goals, directives and answers are kept, and when one
   expires**, `todo.md`'s question widened. Proposed: in the state folder; a
   link holds until it is replaced; a stated state ages as any observation; a
   goal holds until the person closes it.
6. **Which deltas reach qmcp's queue**, and at what budget. Proposed: `warn` and
   `fault` that have not converged, sightings, and goals reported met.
7. **What may be sent to carlos and qmcp**: references only (proposed), or
   frames too.
8. **People in the frames.** A camera on a working space sees whoever walks
   past it. Proposed: subjects are things; a person appears as a claimant or an
   actor, by the name they give, and a model's sighting of a person is not
   recorded.
9. **A line format for a board's sensor readings**, beside its hello: a standard
   one with more than one implementation (*Seams on standard protocols*), or
   the hello's own form extended.
10. **Names**: `apothecary/evidence/` for the package and `apothecary.evidence`
    for the document, *Working space* for the window.

## Decided

- **2026-10-30:** a layer that correlates a working space's cameras, sensors,
  serial feedback, a person's directives, actions and goals, and image models'
  readings into one view is queued, planned and not built. Its first slice ties
  the Ender's camera to its polls. The image models through qmcp are an
  always-optional source, planned on their own.
