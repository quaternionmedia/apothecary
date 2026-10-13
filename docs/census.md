# The census

`apothecary census` counts the ways the viewer accepts a command: the controls
written into the page and the places the page listens. It is a report, read
from the page itself by the rules in `apothecary/census.py`, and one test holds
two of its numbers. Prose never states its counts; it names the command.

```bash
uv run apothecary census                 # the viewer's report, every entry with its line
uv run apothecary census --page FILE     # another page, counted the same way
```

## What is counted

**Controls of its own** -- the meter. Every button, drop-down, tick-box, typing
box, form and link written into the page's markup, found by reading the markup,
so a control counts whether or not anything listens to it; three typing boxes
are three. A control is named by its id where it has one and its class where it
does not.

**Places the page listens.** Every `addEventListener`, keyed by three things:
what it listens on, what it listens for, and the first thing it then does
(`canvas:wheel:onWheel`). Two buttons in one row of a list are two entries, so
a new control cannot hide inside an old one.

What is read: the viewer's template, the widget modules it imports from
`apothecary/static/widgets/`, and the marks modules it imports by name
(`census.MARKS`: what the world wears -- a machine's marks, a picture's -- and
the boards' model behind them). `ring.js`, `panels.js`, `anchors.js` and
`keys.js` are chrome with tests of their own, off the meter; `board_text.js`
writes text and listens to nothing.

## How each is classified

Each control and each place is looked up in `CONTROLS` or `LISTENING` in
`apothecary/census.py`, which say what kind of surface it is and what it
changes:

| Surface | |
|---|---|
| `widget` | A control of its own, invented for one job: the meter. Unifying takes it to nothing, not to a smaller pile |
| `gesture` | Something done to the scene itself: the wheel, a double tap, a key |
| `list` | The trails, trees and rows beside the scene: Contents, a picture's row, a job's row |
| `drag` | Taking hold of a thing on screen and moving it: the move arrows, a camera's turn ring and tilt arc |
| `ring` | The button that opens the ring; the ring's own listeners are counted once, behind it |
| `automatic` | The page reacting to itself or to the browser: Back and Forward, the camera's permission, the page hidden |

| Changes | |
|---|---|
| `what-is-there` | The arrangement itself, or a machine told to change something |
| `what-you-see` | Which part is looked at, what is picked out or folded away |
| `nothing` | Neither: a link that opens the docs, a download |

Anything in neither table is counted as `unclassified` and listed with its line,
and a control in the markup still counts toward the meter, so adding one raises
the number whether or not anybody filed it. A readout the page listens to (the
header's validity count) is a place it listens, not a control.

## Ring-backed, and taken back

A control is **ring-backed** when it does what a cell of the ring does:
`RING_BACKED` names the cell's action beside the control. Being backed does
not lower the meter; deleting the control does. A control is not backed when
no cell does exactly what it does:

- a value no cell can type: a number box, the name a variant is saved under;
- a question that stands only until it is answered: the offer of a tab's kept
  work (Restore, Discard), a computed value's Replace or Keep;
- a choice no cell makes: the part a print makes, a comparison's drop-downs.

**Taken back** (`TAKEN_BACK`) is the one lasting exception: a row's button that
takes back what the row shows -- Pinned's Remove and Unpin, Pictures' Forget --
counted on the meter and never ring-backed, since a row can name another
site's pin, which a ring cell reaches only from that site. Nothing is both.

## The ceiling and the floor

`tests/test_census.py` holds the viewer's controls of its own at or under
`VIEWER_CEILING`, and the share of them that is ring-backed at or above a
floor (`test_the_viewers_ring_backed_share_did_not_fall`). A change to the
page keeps them so:

- A change that adds a control raises `VIEWER_CEILING` in the same change; one
  that removes a control may lower it.
- Every new or moved listener is classified in `census.py` in the same change.
- A control added ring-backed raises the share's floor with it.
- A new ring cell is seated after the cells a ring always has, so no address
  moves ([the viewer](viewer.md#the-ring): addresses hold still).
- A control is written as markup -- one template per control in its widget
  module -- because the census reads markup; a control the page builds one
  element at a time is unseen.

The commit that changes the page says what `apothecary census` reported before
and after, and which ring addresses moved.

## What it cannot see

- It reads the page as text: a listener written inside a comment or a quoted
  string would be counted.
- It sees listening done with `addEventListener`, not a handler assigned to
  `.onclick`; such a control is still counted from the markup, which is why the
  markup is the meter.
- The SCAD editor's own keys (F5, F6, Ctrl+Enter, Ctrl+S) are its CodeMirror
  keymap's, and work inside the editor only; [the viewer](viewer.md#the-scad-editor)
  lists them.
- three.js's own listeners, turning and sliding the view.
- The command line and direct requests.
- It refuses a page where it finds nothing, since a page it could not read and a
  page with no controls must not give the same answer.
