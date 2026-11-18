# The tour

The page's journeys, a stage at a time, in a box over the page: the way a person finds
their way through the app, and the way they say how each part of it is.
[Walkthrough 34](../walkthrough/34-the-tour.md) goes through the box, and
[walkthrough 39](../walkthrough/39-the-chain-a-stage-at-a-time.md) through every stage
it takes the page to.

## What it takes, and in what order

The tour is [the viewer's journeys](viewer.md#journeys), in their order, which is the
order of the chain the page manages: a part designed; made on the printer, or cut on
the router; the board a machine runs on; a deck's knobs on the machines; the site
brought up, and watched; photographs, a drawing read into shapes that stand up as
parts to design; and last two ends joined by the adapter the server derives
between them, a part to print. Each journey hands the next what it made.

The box has no words of its own. A stage's line is the one its journey's rail shows.
Under it is what there is to try on the stage: the steps of the walkthrough that go
through it, each a link to its picture, and the pages that show the same thing whole,
at the command line (`shown_by`, in `apothecary/journeys.py`).

## Opening it

**Tour**, in the header, or the canvas ring's **Panels › Windows › Tour › Tour**. The box
opens above the windows, so a view or a journey laid out moves them and not it. It is
small, since it stands over the world: its head names the stage and how many have a
word on them. It is dragged by its head, folded to its head by a double-click there,
and closed by its ✕ or by Tour again. Where it stands, whether it is open and the stage
it shows are this browser's (`apothecary.tour` in its local storage), so a reload opens
it where it was: the page is then taken to that stage as ↻ does, so the box is not left
over a page it is not true of.

Opened in a browser that has not taken it before, it starts at the first stage with no
word on the build the server runs.

## A stage, and the page taken there

Going to a stage -- a journey chosen in the drop-down, a stage's number, ›, ‹, or a
word said on the one before -- takes the page there, and ↻ beside the stage's words
takes it there again. **its page**, beside ↻, is the first walkthrough page the stage
names, in a tab. The page then does what a person would do to get there, each
thing only where it is not so already:

- the site the journey stands in opened, where another is, as the banner's ▾ opens
  it (`Journey.site`): the garage, whose pieces and machines every journey but one
  names, or the universe, where *Join a hose*'s port part and adapter stand; so a
  stage is the same whichever site the tour was opened in;
- what the journey is staged on, then what the stage itself needs (`staged_on` and a
  stage's `puts`, in `apothecary/journeys.py`), from a short list of things the page
  already does:

  | Put | What the page does | As |
  |---|---|---|
  | `pin` | a board on a port pinned to a piece, where that port is listed | Pin, in the piece's Device section |
  | `machine` | a piece chosen, and its Machine opened, in place of another's, where it is not open already; with no board connected, as the site plans it | its badge, or Device › Open |
  | `part` | a piece chosen | its row in Site |
  | `fit` | a piece chosen and framed in the world | `f` |
  | `makes` | the piece named under makes in the open Machine's Print window, and the file kept made from it chosen, where one is kept: nothing is sliced | the card's makes, and its files |
  | `file` | the open Machine's file made from a part: the one chosen, else the newest kept chosen, else one made; another part's file chosen before is not the stage's | the card's file, Slice, or a router's Toolpath |
  | `edit` | a part's editor opened | Part › Edit |
  | `scad` | a part's SCAD in its window | Part › SCAD |
  | `bench` | the Bench opened on a piece's sketch | Device › Flash sketch |
  | `working` | the Working space opened on the site, or on a machine | ⊞ Windows › Working space, Camera › Workspace |
  | `picture` | a picture of the folder pinned at a piece, and framed where it lies | Picture › Folder |
  | `shapes` | the shapes of the picture drawn at a piece found | Picture › Find shapes |

- a Machine that is open is closed where the journey has no machine in it;
- the journey is entered at the stage, its windows laid out and its rail in the
  header.

So a stage that needs the work of the one before it has it done first: See draws a
file's path, so with no file of its piece kept the piece is sliced for the machine; Marks needs a
photograph pinned and its shapes found.

The box keeps what the page did, then what the page said of the stage, folded under
one line with what there is to try. The stage is there to explore.

**It is the same on every server.** The page does the same things whether the
machines are real or simulated, and each acts on what is there.

**A machine whose board is not connected is taken as the site plans it.** Its Machine
opens as its badge opens it then: what it makes, its slice or its toolpath and the
path drawn are planned there, and ▶ is its board's once it is connected
([the viewer](viewer.md)).

**What is a person's to bring is not stood in for.** Which board is a piece's, a
photograph taken: where a stage needs one that is not there, the page leaves the
rest and enters the stage all the same, so a person stands where it is done, and the
box opens on what the stage needs, in the page's own words for it -- *esp32_blink's
board is pinned to a board, but not connected: connect it, or ⟳ Rescan in its Device
section*. With that done, ↻ takes the page the rest of the way.

**Nothing is armed, started, sent or made.** Start's stage brings the Print window, where ▶ Print is, and Jobs
forward, Flash's the board's Flashing window, Steps' the Procedure, Pieces' the shapes
found: arming control, ▶ Print and ▶ Cut, an upload, GO, a knob turned and Picture ›
Make are a person's.

Moving the rail in the page moves the box to that stage, and takes the page nowhere.

## Saying how a stage is

- **✓ Works**: the stage does what it says.
- **✗ Off**: something is not right, with what is off typed in the field beside the
  buttons; Enter in the field is ✗ Off. Off with the field empty is refused, the box
  saying so and staying on the stage.

Either is kept on the server, and the box goes to the next stage. A stage with a word
on it wears it among the journey's stages, and the box says what was said, by whom and
when.

**A word is kept under a name.** The field above the buttons holds it: asked once,
where a word is given with none, and kept by this browser. The server refuses a word
with no name.

**A word is of the build it was said of.** Once the server runs another commit, what
was said is still shown, dimmed among the stages and marked as said of an earlier
build, and the stage waits for a word again: the box's count is of words on this
build, and it opens on the first stage without one.

A word is a line of `tour/feedback.jsonl` under the state folder
(`APOTHECARY_STATE_DIR`, [configuration](configuration.md#apothecary_-variables)): the
stage (`make/slice`), `works` or `off`, what is off, who said it, the moment, and the
commit the server ran, with whether its tree had changes beside it. A line is never
rewritten; the latest for a stage is its feedback.

## The routes

- `GET /tour`: the journeys in their order, each stage with its words, what to try on
  it and its latest feedback, with whether that is `current` (said of the commit now
  running), and the commit the server runs. The box reads this.
- `POST /tour/feedback`: one word, `{stage, verdict, note, by}`. A stage no journey
  has is refused (404), and so is a verdict that is neither, Off with nothing said,
  or a word with no name (422).
- `GET /tour/feedback`: every word kept, oldest first.

What the project plans, and what was found of each thing it claims, are not kept in
this repository or read by it. The roadmap is the project's own, `project/ROADMAP.md`
on apothecary's branch of the governance corpus, and `qmcp tour` reads it beside the
two `GET` routes above: each claim, the journey or pages that show it, and what was
said of each stage.

## The ring

Panels › Windows › Tour is the box, then its buttons: Tour (open or closed), Back,
Works, Off (with what the box's field says), Next, Its page (the first walkthrough
page the stage names, in a tab), Take me here, and Who, the field for the name. It is
seated after the views, so no cell before it moves.

## What it does not do

- It takes the page to a journey's stage, and to nothing else. What no journey holds
  is in the walkthrough: a fresh clone installed and served, the checks before a push,
  being depended on, an assembly stepped into, and a camera's picture, which needs the
  browser's camera.
- It does not bring about a state only a fault brings: a router in alarm, a board not
  heard for ten minutes. Those are at their stage as steps to read.
- It does not arm, start, send or make anything.
- The box stands over the world, so what a stage frames there can lie under it until
  the box is dragged or folded.
- Nothing leaves the machine: the feedback is under the state folder, and the server
  answers this machine only.
