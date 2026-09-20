"""Count the ways this application accepts a command.

The claim this exists to hold up is that a page full of controls of its own
becomes one ring. A number somebody wrote down once is not a measurement — the
next person counts differently and both numbers are worthless. So the count is
taken here, from the page itself, by a rule written down beside it.

## An earlier version of this file was wrong, and how

The first attempt reported "twelve controls, fourteen ways in". An independent
reviewer took it apart and was right to. Three faults, all fatal to the figure:

- **It counted names, not controls.** Two different buttons on a job — one that
  gives the job out, one that finishes it — were fetched the same way and counted
  once. Three boxes for typing a position into counted once. A count that cannot
  tell one button from two is not a count.
- **Its own rule did not produce its own number.** Stepping out of a piece was
  called a control; clicking the trail to step out of the same piece was called
  moving your attention. Same three lines of code either way. Applied evenly the
  rule gives nine, or sixteen, but never twelve. Twelve was the answer already
  written in the plan, arrived at backwards.
- **A new control could hide inside an old one.** Adding a delete button to a row
  of a list produced no complaint, because it was attached the same way as the
  buttons already there. The gate only caught new *names*, and the names in play
  were `li`, `chip` and `caret`.

What follows is the repair. It counts two different things two different ways and
does not add them together, because adding them was where the arbitrariness got
in.

## What is counted, and how

**Controls of its own.** Every button, drop-down, tick-box, typing box, form and
link written into the page. Found by reading the page's own markup, so a control
counts whether or not anything is currently listening to it — one drop-down for
choosing a printer has no listener at all and was invisible to the first attempt.
Each is counted separately. Three typing boxes are three.

**Places the page listens.** Every point where the page waits for something a
person does. Each is identified by three things together: what it listens on,
what it listens for, and *the first thing it then does*. That third part is what
makes two buttons in the same row of a list two entries rather than one, and it
is what makes a new control impossible to hide inside an old one.

Every one of both kinds is looked up in a table below. **Anything not in the
table stops the count and is named, with its line.** A new control cannot appear
without somebody deciding, in writing, what kind of thing it is.

## The two questions asked of each one

They are kept apart on purpose. Mixing them is what let the first attempt call
the same behaviour two different things depending on which answer it needed.

**What kind of surface is it?**

- `widget` — a control of its own, occupying space, invented for one job. **This
  is the meter.** Unifying means this number falls. It falls to zero, not to a
  smaller pile: a ring that leaves five buttons behind has not replaced them.
- `gesture` — something done to the scene itself: the wheel, a double tap, a key.
- `list` — the trails, trees and rows beside the scene.
- `drag` — taking hold of the thing on screen and moving it. Kept on purpose;
  this is not a menu problem.
- `ring` — the one ring of options. The destination. One thing is filed here:
  the button that opens it. The ring's own listeners — the `m` key, right-click,
  the arrows and digits once it is open — live in `/static/ring.js`, a module
  the page imports, and are the ring's rather than the page's; they are counted
  once, behind that button, and a test holds the module to that.
- `automatic` — the page reacting to itself. Nobody told it anything.

## Ring-backed

A control of its own that does the same thing as a cell of the ring is
**ring-backed**: `RING_BACKED` names the ring action beside the control's name,
and the sentence says how many of the meter's controls are also on the ring.
The meter does not fall because a control is ring-backed. It falls when the
ring-backed control is deleted, which is the whole migration in one line: a
control gains its ⌗ address, is used from the ring for a while, and goes.
The table is checked against the ring's own vocabulary, so a control cannot
claim to be backed by a verb no ring produces.

**What does it change?**

- `what-is-there` — the arrangement itself, or the machine is told to change
  something.
- `what-you-see` — which part you are looking at, what is picked out, what is
  folded away. The arrangement is the same afterwards.

Note that `what-you-see` does **not** mean "nothing happens". Moving your
attention makes this application fetch and build shapes, and building a shape
writes a file. It was called harmless in an earlier version of this file and that
was wrong. The line is whether the *arrangement* is different afterwards, not
whether the machine did work.

## What this cannot see

Said plainly so nobody mistakes it for more than it is.

- It reads the page as text. A listener written inside a comment or a quoted
  string would be counted.
- It sees listening done with `addEventListener` and not a handler assigned to
  `.onclick`. The monitor page assigns most of its handlers that way; its
  buttons are still counted, from the markup, which is why the markup is the
  meter and the listening is the check on it.
- The drawing library brings its own listeners — turning and sliding the view by
  dragging are real and are not in this count and cannot be.
- It is one page at a time. Anything a person can command from elsewhere — the
  command line, a request made straight to the machine, the other page — is not
  in this number. The viewer and the monitor are counted separately and never
  added together.
- It refuses when it finds nothing, because a page it failed to read and a page
  with no controls must not produce the same answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
VIEWER = TEMPLATES / "fractal_viewer.html.j2"
MONITOR = TEMPLATES / "monitor.html.j2"
PAGES = (VIEWER, MONITOR)

# --- what kind of surface -------------------------------------------------
WIDGET = "widget"
GESTURE = "gesture"
LIST = "list"
DRAG = "drag"
RING = "ring"
AUTOMATIC = "automatic"

SURFACES = (WIDGET, GESTURE, LIST, DRAG, RING, AUTOMATIC)

# --- what it changes ------------------------------------------------------
WHAT_IS_THERE = "what-is-there"
WHAT_YOU_SEE = "what-you-see"
NOTHING = "nothing"

EFFECTS = (WHAT_IS_THERE, WHAT_YOU_SEE, NOTHING)


class Unclassified(Exception):
    """The page has something nobody has said anything about.

    Raised rather than guessed. A census that quietly assumes a kind for
    something it has never seen reports whatever number keeps it quiet.
    """


class NothingFound(Exception):
    """The page was read and nothing was found in it.

    This is a refusal, not an answer of zero. A page that could not be read and
    a page with no controls in it must not produce the same number, or the day
    the reading breaks is the day the count silently becomes perfect.
    """


# ==========================================================================
# Controls of its own — read from the page's markup
# ==========================================================================

# Every control written into the page, by the name it carries there. The name is
# its id where it has one and its class where it does not.
CONTROLS: Dict[str, Tuple[str, str, str]] = {
    "site-select": (WIDGET, WHAT_YOU_SEE, "a drop-down of arrangements"),
    "load-btn": (WIDGET, WHAT_YOU_SEE, "a button that loads the chosen arrangement"),
    "zoom-out-btn": (WIDGET, WHAT_YOU_SEE, "a button that steps back out"),
    "snap-toggle": (WIDGET, WHAT_YOU_SEE, "a tick-box for snapping to a grid"),
    "job-form": (WIDGET, WHAT_IS_THERE, "a form for making a job"),
    "job-name": (WIDGET, WHAT_IS_THERE, "a box for the name of a new job"),
    "job-x": (WIDGET, WHAT_IS_THERE, "a box for where a new job goes, across"),
    "job-y": (WIDGET, WHAT_IS_THERE, "a box for where a new job goes, along"),
    "job-z": (WIDGET, WHAT_IS_THERE, "a box for where a new job goes, up"),
    "job-form:submit": (WIDGET, WHAT_IS_THERE, "the button that makes the job"),
    "zoom-in-btn": (WIDGET, WHAT_YOU_SEE, "a button that goes into the chosen piece"),
    "status-select": (WIDGET, WHAT_IS_THERE, "a drop-down for the state of a piece"),
    "pos-x": (WIDGET, WHAT_IS_THERE, "a box for typing where a piece is, across"),
    "pos-y": (WIDGET, WHAT_IS_THERE, "a box for typing where a piece is, along"),
    "pos-z": (WIDGET, WHAT_IS_THERE, "a box for typing where a piece is, up"),
    "part-regenerate-btn": (WIDGET, WHAT_IS_THERE, "a button that rebuilds a piece"),
    "part-scad-download": (WIDGET, NOTHING, "a link that downloads the piece's recipe"),
    "job-printer-select": (WIDGET, WHAT_IS_THERE, "a drop-down of machines to give a job to"),
    "job-assign-btn": (WIDGET, WHAT_IS_THERE, "a button that gives a job to a machine"),
    "job-complete-btn": (WIDGET, WHAT_IS_THERE, "a button that finishes a job"),
    # The staged numbers of a piece: changed on the sliders, then kept or not.
    "apply-btn": (WIDGET, WHAT_IS_THERE, "a button that rebuilds a piece with its staged numbers"),
    "revert-btn": (WIDGET, WHAT_YOU_SEE, "a button that puts the staged numbers back"),
    # How much of a subassembly to draw, and whether to outline its extent.
    "detail-mode": (WIDGET, WHAT_YOU_SEE, "a drop-down for how much of each subassembly to draw"),
    "overlay-toggle": (WIDGET, WHAT_YOU_SEE, "a tick-box that outlines each subassembly's extent"),
    "detail-select": (WIDGET, WHAT_YOU_SEE, "the same drop-down, for the chosen piece only"),
    # A board's serial log, floated over the view.
    "serial-toggle": (WIDGET, WHAT_YOU_SEE, "a tick-box that floats a board's serial log"),
    "serial-port": (WIDGET, WHAT_YOU_SEE, "a drop-down of connected boards"),
    "serial-baud": (WIDGET, WHAT_YOU_SEE, "a drop-down of speeds to listen at"),
    "serial-refresh": (WIDGET, WHAT_YOU_SEE, "a button that looks for boards again"),
    "serial-clear": (WIDGET, WHAT_YOU_SEE, "a button that empties the log"),
    "serial-close": (WIDGET, WHAT_YOU_SEE, "a button that puts the log away"),
    "firmware-link": (WIDGET, NOTHING, "a link to the firmware page"),
    "firmware-page-link": (WIDGET, NOTHING, "the same link, offered when no board is found"),
    "monitor-link": (WIDGET, NOTHING, "a link to the printer monitor page"),
    # The serial log's second row: identify the board, open its monitor, and
    # ask it for a report by code.
    "serial-identify": (WIDGET, WHAT_YOU_SEE, "a button that asks a board what it is"),
    "serial-monitor": (WIDGET, NOTHING, "a link to the monitor for the board being watched"),
    "serial-query-row": (WIDGET, WHAT_YOU_SEE, "a form for asking a printer for a report"),
    "serial-query": (WIDGET, WHAT_YOU_SEE, "a box for the report code to ask for"),
    "serial-query-row:submit": (WIDGET, WHAT_YOU_SEE, "the button that asks for the report"),
    # Looking for boards again on a schedule.
    "devices-auto": (WIDGET, WHAT_YOU_SEE, "a tick-box that looks for boards on a schedule"),
    "devices-interval": (WIDGET, WHAT_YOU_SEE, "a drop-down for how often to look"),
    # The Device section of the chosen piece: what board it is pinned to, and
    # what can be done with that board. Drawn afresh each time the piece
    # changes, so these are found by class rather than id.
    "dev-watch": (WIDGET, WHAT_YOU_SEE, "a button that floats the pinned board's serial log"),
    "dev-poll": (WIDGET, WHAT_YOU_SEE, "a button that polls the pinned printer once"),
    "dev-monitor": (WIDGET, NOTHING, "a link to the pinned printer's monitor"),
    "dev-unpin": (WIDGET, WHAT_IS_THERE, "a button that unpins the board from the piece"),
    "dev-via": (WIDGET, WHAT_YOU_SEE, "a link to the piece inside that holds the board"),
    "dev-rescan": (WIDGET, WHAT_YOU_SEE, "a button that looks for boards again"),
    "dev-manual": (WIDGET, WHAT_IS_THERE, "a box for typing a port or address to pin"),
    "dev-pin-manual": (WIDGET, WHAT_IS_THERE, "the button that pins the typed board"),
    "dev-pick": (WIDGET, WHAT_YOU_SEE, "a drop-down of boards not yet pinned"),
    "dev-query": (WIDGET, WHAT_YOU_SEE, "a button that asks the chosen board what it is"),
    "dev-pin": (WIDGET, WHAT_IS_THERE, "a button that pins the chosen board to the piece"),
    # The ring. One control, and it is the destination rather than the meter.
    "ring-open": (RING, WHAT_YOU_SEE, "the button that opens the ring"),
    # Made by the page as it goes, rather than written into it. Found by the
    # listening scan below, and named here so both scans agree on what exists.
    "category-chip": (LIST, WHAT_YOU_SEE, "a row of buttons, one per word, that fold and unfold"),
    "tree-caret": (LIST, WHAT_YOU_SEE, "the arrow that opens a branch of the list"),
    "contents-item": (LIST, WHAT_YOU_SEE, "a row of the list of pieces"),
    "breadcrumb": (LIST, WHAT_YOU_SEE, "the trail back to where you came from"),
    # ---- the monitor page, templates/monitor.html.j2 ----------------------
    # One printer, watched closely. The header: which port, how often to poll,
    # and the link itself.
    "port": (WIDGET, WHAT_YOU_SEE, "a drop-down of printer ports"),
    "auto": (WIDGET, WHAT_YOU_SEE, "a tick-box that polls on a schedule"),
    "interval": (WIDGET, WHAT_YOU_SEE, "a drop-down for how often to poll"),
    "poll": (WIDGET, WHAT_YOU_SEE, "a button that polls the printer once"),
    "reconnect": (WIDGET, WHAT_YOU_SEE, "a button that reopens the serial link"),
    "identify": (WIDGET, WHAT_YOU_SEE, "a button that asks the board what it is"),
    "reset": (WIDGET, WHAT_IS_THERE, "a button that reboots the board"),
    "release": (WIDGET, WHAT_YOU_SEE, "a button that lets go of the port"),
    "ctl": (WIDGET, WHAT_YOU_SEE, "a tick-box that arms the control latch"),
    "estop": (WIDGET, WHAT_IS_THERE, "the emergency stop"),
    "viewer-link": (WIDGET, NOTHING, "a link back to the viewer"),
    # The comms log: a report to ask for, and what to show of the traffic.
    "qform": (WIDGET, WHAT_YOU_SEE, "a form for asking the printer for a report"),
    "q": (WIDGET, WHAT_YOU_SEE, "a box for the report code to ask for"),
    "qform:submit": (WIDGET, WHAT_YOU_SEE, "the button that asks for the report"),
    "show-polls": (WIDGET, WHAT_YOU_SEE, "a tick-box that shows the poll traffic"),
    "follow": (WIDGET, WHAT_YOU_SEE, "a tick-box that keeps the log scrolled to the end"),
    "clear": (WIDGET, WHAT_YOU_SEE, "a button that empties the log"),
    "download": (WIDGET, NOTHING, "a button that downloads the log"),
    # The control overlay, behind the latch. The buttons carry the G-code line
    # they send rather than a name, and are named here by that line; a box
    # beside a button holds the number the line is filled in with.
    "ctl-disarm": (WIDGET, WHAT_YOU_SEE, "a button that disarms the control latch"),
    "h-hot": (WIDGET, WHAT_YOU_SEE, "a box for the hotend temperature to set"),
    "cmd:M104 S{h-hot}": (WIDGET, WHAT_IS_THERE, "a button that heats the hotend to that"),
    "cmd:M104 S0": (WIDGET, WHAT_IS_THERE, "a button that turns the hotend off"),
    "h-bed": (WIDGET, WHAT_YOU_SEE, "a box for the bed temperature to set"),
    "cmd:M140 S{h-bed}": (WIDGET, WHAT_IS_THERE, "a button that heats the bed to that"),
    "cmd:M140 S0": (WIDGET, WHAT_IS_THERE, "a button that turns the bed off"),
    "h-fan": (WIDGET, WHAT_YOU_SEE, "a slider for the fan speed to set"),
    "cmd:M106 S{h-fan}": (WIDGET, WHAT_IS_THERE, "a button that runs the fan at that"),
    "cmd:M107": (WIDGET, WHAT_IS_THERE, "a button that turns the fan off"),
    "jog:Y+": (WIDGET, WHAT_IS_THERE, "a button that jogs the bed one step along"),
    "jog:X-": (WIDGET, WHAT_IS_THERE, "a button that jogs the head one step left"),
    "cmd:G28": (WIDGET, WHAT_IS_THERE, "a button that homes every axis"),
    "jog:X+": (WIDGET, WHAT_IS_THERE, "a button that jogs the head one step right"),
    "jog:Y-": (WIDGET, WHAT_IS_THERE, "a button that jogs the bed one step back"),
    "jog:Z+": (WIDGET, WHAT_IS_THERE, "a button that jogs the head one step up"),
    "jog:Z-": (WIDGET, WHAT_IS_THERE, "a button that jogs the head one step down"),
    "step:0.1": (WIDGET, WHAT_YOU_SEE, "a button that makes a jog step a tenth of a millimetre"),
    "step:1": (WIDGET, WHAT_YOU_SEE, "a button that makes a jog step a millimetre"),
    "step:10": (WIDGET, WHAT_YOU_SEE, "a button that makes a jog step a centimetre"),
    "step:50": (WIDGET, WHAT_YOU_SEE, "a button that makes a jog step five centimetres"),
    "h-feed": (WIDGET, WHAT_YOU_SEE, "a box for how fast to jog"),
    "cmd:G28 X Y": (WIDGET, WHAT_IS_THERE, "a button that homes across and along"),
    "cmd:G28 Z": (WIDGET, WHAT_IS_THERE, "a button that homes up"),
    "cmd:M84": (WIDGET, WHAT_IS_THERE, "a button that lets the motors go"),
    "cmd:M410": (WIDGET, WHAT_IS_THERE, "a button that drops every planned move"),
    "cmd:M24": (WIDGET, WHAT_IS_THERE, "a button that starts or resumes the print on the card"),
    "cmd:M25": (WIDGET, WHAT_IS_THERE, "a button that pauses the print on the card"),
    "cmd:M524": (WIDGET, WHAT_IS_THERE, "a button that abandons the print on the card"),
    "cmd:M420 S1": (WIDGET, WHAT_IS_THERE, "a button that turns bed levelling on"),
    "cmd:M420 S0": (WIDGET, WHAT_IS_THERE, "a button that turns bed levelling off"),
    "cmd:M108": (WIDGET, WHAT_IS_THERE, "a button that breaks out of a heat-and-wait"),
}

# A control of its own that does the same thing as a cell of the ring, and the
# action that cell carries. Keyed by the control's name, or by a listening
# key, since a button and the place the page listens to it are the same way
# in. Every action here must be one the rings produce; a test holds it to
# `apothecary.menu`'s vocabulary, so a control cannot claim a backing that
# does not exist.
RING_BACKED: Dict[str, str] = {
    # the viewer's Device section and serial log
    "dev-watch": "device:watch",
    "dev-poll": "device:poll",
    "dev-monitor": "device:monitor",
    "dev-query": "device:query",
    "dev-pin": "device:pin",
    "dev-pin-manual": "device:pin",
    "dev-unpin": "device:unpin",
    "dev-rescan": "device:rescan",
    "serial-identify": "device:query",
    "serial-monitor": "device:monitor",
    "serial-refresh": "device:rescan",
    "devWatch:click:dispatchEvent": "device:watch",
    "devPoll:click:pollNow": "device:poll",
    "devQuery:click:queryPort": "device:query",
    "devPin:click:setNodeDevice": "device:pin",
    "devPinManual:click:pinManual": "device:pin",
    "manualIn:keydown:pinManual": "device:pin",
    "devUnpin:click:setNodeDevice": "device:unpin",
    "devRescan:click:rescanDevices": "device:rescan",
    # the monitor's header and control overlay
    "poll": "device:poll",
    "identify": "device:query",
    "ctl": "control:arm",
    "ctl-disarm": "control:disarm",
    "estop": "control:estop",
    "cmd:M104 S{h-hot}": "control:hotend-on",
    "cmd:M104 S0": "control:hotend-off",
    "cmd:M140 S{h-bed}": "control:bed-on",
    "cmd:M140 S0": "control:bed-off",
    "cmd:M106 S{h-fan}": "control:fan-on",
    "cmd:M107": "control:fan-off",
    "cmd:G28": "control:home",
    "cmd:G28 X Y": "control:home-xy",
    "cmd:G28 Z": "control:home-z",
    "jog:Y+": "control:jog:Y+",
    "jog:X+": "control:jog:X+",
    "jog:Y-": "control:jog:Y-",
    "jog:X-": "control:jog:X-",
    "jog:Z+": "control:jog:Z+",
    "jog:Z-": "control:jog:Z-",
    "cmd:M24": "control:sd-resume",
    "cmd:M25": "control:sd-pause",
    "cmd:M524": "control:sd-abort",
    "cmd:M84": "control:motors-off",
    "cmd:M410": "control:quickstop",
    "reconnect": "device:reconnect",
    "reset": "device:reset",
    "release": "device:release",
    "ctl:change:arm": "control:arm",
}

MARKUP = re.compile(
    r"<(select|input|button|textarea|form|a)\b([^>]*)>",
    re.IGNORECASE,
)
HAS_ID = re.compile(r"\bid=[\"']([\w-]+)[\"']")
HAS_CLASS = re.compile(r"\bclass=[\"']([^\"']+)[\"']")
IS_SUBMIT = re.compile(r"\btype=[\"']submit[\"']")
A_FORM = re.compile(r"<form\b([^>]*)>", re.IGNORECASE)

# A control that carries what it does rather than a name -- the monitor's
# control overlay, where every button carries its G-code line -- is named by
# that. Before the class, because two buttons of one class that send two
# different lines are two buttons.
BY_WHAT_IT_CARRIES: Sequence[Tuple[re.Pattern, str]] = (
    (re.compile(r"\bdata-jog=[\"']([^\"']+)[\"']"), "jog"),
    (re.compile(r"\bdata-cmd=[\"']([^\"']+)[\"']"), "cmd"),
    (re.compile(r"\bdata-step=[\"']([^\"']+)[\"']"), "step"),
)

# A markup control with neither an id nor a class is named by where its link
# goes, because there is nothing else to call it. Read after the id and the
# class, not before: an anchor that has a class and also a link is the thing
# its class says, and naming it by the link alone let two of the Device
# section's links count as the recipe download.
BY_SHAPE: Sequence[Tuple[re.Pattern, str]] = (
    (re.compile(r"\bhref=[\"'][^\"']*/scad[\"']"), "part-scad-download"),
    (re.compile(r"\bhref=[\"'][^\"']*/firmware[\"']"), "firmware-link"),
    (re.compile(r"\bhref=[\"'][^\"']*/viewer[\"']"), "viewer-link"),
)


# ==========================================================================
# Places the page listens
# ==========================================================================

# What it listens on, what it listens for, and the first thing it then does.
# The third part is load-bearing: without it two buttons in the same row of a
# list are one entry, and a new control can be added to that row unnoticed.
LISTENING: Dict[str, Tuple[str, str, str]] = {
    # taking hold of the thing itself
    "transformControls:dragging-changed:(nothing)": (  # noqa: E501 - see NO_CALL
        DRAG,
        WHAT_YOU_SEE,
        "taking hold stops the view from turning under you",
    ),
    "transformControls:objectChange:onGizmoDrag": (
        DRAG,
        WHAT_IS_THERE,
        "dragging the handle moves a piece",
    ),
    "transformControls:mouseUp:commitCurrentDrag": (
        DRAG,
        WHAT_IS_THERE,
        "letting go keeps the move",
    ),
    # controls of its own
    "loadBtn:click:loadSite": (WIDGET, WHAT_YOU_SEE, "the load button"),
    "siteSelect:change:loadSite": (WIDGET, WHAT_YOU_SEE, "choosing from the drop-down"),
    "zoomOutBtn:click:zoomOut": (WIDGET, WHAT_YOU_SEE, "the step-out button"),
    "snapToggle:change:setTranslationSnap": (WIDGET, WHAT_YOU_SEE, "the snapping tick-box"),
    "jobFormEl:submit:createJob": (WIDGET, WHAT_IS_THERE, "sending the job form"),
    "posAxis:change:recomputeWorldBounds": (WIDGET, WHAT_IS_THERE, "typing a position"),
    "statusSelect:change:submitStatus": (WIDGET, WHAT_IS_THERE, "choosing a state"),
    "regenerateBtn:click:regeneratePart": (WIDGET, WHAT_IS_THERE, "the rebuild button"),
    "jobBtn:click:assignJob": (WIDGET, WHAT_IS_THERE, "giving a job to a machine"),
    "jobBtn:click:completeJob": (WIDGET, WHAT_IS_THERE, "finishing a job"),
    "zoomInLink:click:zoomIn": (WIDGET, WHAT_YOU_SEE, "the go-in button on the chosen piece"),
    # done to the scene itself
    "canvas:pointerdown:onPointerDown": (GESTURE, WHAT_YOU_SEE, "pointing at a piece"),
    "canvas:dblclick:onDoubleClick": (GESTURE, WHAT_YOU_SEE, "double-tapping to go in"),
    "canvas:wheel:onWheel": (GESTURE, WHAT_YOU_SEE, "the wheel, with a counter of its own"),
    "window:keydown:zoomOut": (GESTURE, WHAT_YOU_SEE, "a key that steps back out"),
    # the trails, trees and rows beside the scene
    "chip:click:delete": (LIST, WHAT_YOU_SEE, "a word button that folds and unfolds"),
    "caret:click:delete": (LIST, WHAT_YOU_SEE, "an arrow that opens a branch"),
    "li:click:selectChild": (LIST, WHAT_YOU_SEE, "picking a piece from the list"),
    "li:dblclick:zoomIn": (LIST, WHAT_YOU_SEE, "going into a piece from the list"),
    "rootCrumb:click:jumpTo": (LIST, WHAT_YOU_SEE, "the top of the trail"),
    "crumb:click:jumpTo": (LIST, WHAT_YOU_SEE, "a step on the trail"),
    # how much to draw
    "detailModeEl:change:clear": (WIDGET, WHAT_YOU_SEE, "choosing how much to draw"),
    "overlayToggle:change:renderFocus": (WIDGET, WHAT_YOU_SEE, "the outlines tick-box"),
    "select:change:delete": (WIDGET, WHAT_YOU_SEE, "choosing how much to draw of one piece"),
    # the serial log
    "toggle:change:show": (WIDGET, WHAT_YOU_SEE, "the serial log tick-box"),
    "portSel:change:renderMeta": (WIDGET, WHAT_YOU_SEE, "choosing a board"),
    "baudSel:change:connect": (WIDGET, WHAT_YOU_SEE, "choosing a speed"),
    "queryRow:submit:line": (WIDGET, WHAT_YOU_SEE, "asking the watched printer for a report"),
    # looking for boards on a schedule
    "autoEl:change:setItem": (WIDGET, WHAT_YOU_SEE, "the look-for-boards tick-box"),
    "intervalEl:change:setItem": (WIDGET, WHAT_YOU_SEE, "choosing how often to look"),
    # the Device section of the chosen piece
    "devWatch:click:dispatchEvent": (WIDGET, WHAT_YOU_SEE, "floating the pinned board's log"),
    "devUnpin:click:setNodeDevice": (WIDGET, WHAT_IS_THERE, "unpinning the board"),
    "devPin:click:setNodeDevice": (WIDGET, WHAT_IS_THERE, "pinning the chosen board"),
    "devQuery:click:queryPort": (WIDGET, WHAT_YOU_SEE, "asking the chosen board what it is"),
    "devPoll:click:pollNow": (WIDGET, WHAT_YOU_SEE, "polling the pinned printer once"),
    "devVia:click:split": (WIDGET, WHAT_YOU_SEE, "going to the piece inside that holds the board"),
    "devRescan:click:rescanDevices": (WIDGET, WHAT_YOU_SEE, "looking for boards again"),
    "devPinManual:click:pinManual": (WIDGET, WHAT_IS_THERE, "pinning the typed board"),
    "manualIn:keydown:pinManual": (WIDGET, WHAT_IS_THERE, "pinning the typed board, by Enter"),
    # the page reacting to itself
    "window:resize:onResize": (AUTOMATIC, NOTHING, "the window changed size on its own"),
    "es:open:add": (AUTOMATIC, NOTHING, "the serial stream connected, and says so"),
    "es:close:line": (AUTOMATIC, NOTHING, "the serial stream stopped, and says so"),
    "window:beforeunload:disconnect": (AUTOMATIC, NOTHING, "leaving the page lets go of the port"),
    "document:visibilitychange:scheduleAutoRefresh": (
        AUTOMATIC,
        NOTHING,
        "the page was hidden or shown, and looks for boards accordingly",
    ),
    # ---- the monitor page, templates/monitor.html.j2 ----------------------
    # Most of the monitor's buttons are wired by assignment rather than by
    # listening, so the markup carries them; these are the ones that listen.
    "port:change:selectPort": (WIDGET, WHAT_YOU_SEE, "choosing a printer port"),
    "auto:change:schedule": (WIDGET, WHAT_YOU_SEE, "the poll-on-a-schedule tick-box"),
    "interval:change:schedule": (WIDGET, WHAT_YOU_SEE, "choosing how often to poll"),
    "qform:submit:post": (WIDGET, WHAT_YOU_SEE, "asking the printer for a report"),
    "show-polls:change:renderLog": (WIDGET, WHAT_YOU_SEE, "the poll-traffic tick-box"),
    "ctl:change:arm": (WIDGET, WHAT_YOU_SEE, "arming or disarming the control latch"),
    "h-fan:input:(nothing)": (WIDGET, WHAT_YOU_SEE, "sliding the fan speed, shown beside it"),
    "control:click:closest": (
        WIDGET,
        WHAT_IS_THERE,
        "one listener for the whole control overlay, told which button by what it carries",
    ),
    "document:visibilitychange:schedule": (
        AUTOMATIC,
        NOTHING,
        "the page was hidden or shown, and polls accordingly",
    ),
    "window:beforeunload:clearTimeout": (AUTOMATIC, NOTHING, "leaving the page stops the polling"),
}

LISTENS = re.compile(r"addEventListener\s*\(\s*['\"]([\w-]+)['\"]\s*,")

# Fetched by the label they carry in the page rather than by a plain name.
# Searched only within the current statement, never across one, so a mention in
# the line above cannot claim a listener that is not its own. Longer labels
# before the ones they begin with, so `.dev-pin-manual` is not read as `.dev-pin`.
FETCHED_BY_LABEL: Sequence[Tuple[str, str]] = (
    (r"\.job-(assign|complete)-btn", "jobBtn"),
    (r"pos-\$\{axis\}", "posAxis"),
    (r"part-regenerate-btn", "regenerateBtn"),
    (r"\.zoom-in-btn", "zoomInLink"),
    (r"\.dev-pin-manual", "devPinManual"),
    (r"\.dev-watch", "devWatch"),
    (r"\.dev-poll", "devPoll"),
    (r"\.dev-unpin", "devUnpin"),
    (r"\.dev-pin", "devPin"),
    (r"\.dev-query", "devQuery"),
    (r"\.dev-via", "devVia"),
    (r"\.dev-rescan", "devRescan"),
)

# Fetched by id through the monitor page's one-letter helper: `$("port")`.
FETCHED_BY_ID = re.compile(r"\$\(\s*[\"']([\w-]+)[\"']\s*\)\s*$")

# The last plain word before the listening: `this.loadBtn.` gives `loadBtn`.
LAST_WORD = re.compile(r"([\w$]+)\s*$")

# A call in a handler that is plumbing rather than the thing the handler is for.
PLUMBING = frozenset(
    {
        "preventDefault",
        "stopPropagation",
        "parseFloat",
        "parseInt",
        "Number",
        "querySelector",
        "querySelectorAll",
        "getElementById",
        "$",
        "trim",
        "async",
        "if",
        "for",
        "while",
        "switch",
        "catch",
        "function",
        "return",
    }
)
A_CALL = re.compile(r"([\w$]+)\s*\(")
# A handler that is a bare name -- `addEventListener("change", schedule)` --
# does exactly that one thing, and it is named.
BARE_HANDLER = re.compile(r"^\s*(?:this\.)?([\w$]+)\s*(?:,|$)")
NO_CALL = "(nothing)"


@dataclass(frozen=True)
class Found:
    """One thing a person can operate."""

    name: str
    surface: str
    effect: str
    description: str
    line: int
    how: str  # "markup" or "listening"
    key: str
    # The ring action that does the same thing, when there is one. A control
    # with one of these is a control the ring has already replaced in all but
    # deletion.
    ring_action: Optional[str] = None


@dataclass(frozen=True)
class Census:
    found: Tuple[Found, ...]

    def of_surface(self, surface: str) -> Tuple[Found, ...]:
        return tuple(f for f in self.found if f.surface == surface)

    def of_effect(self, effect: str) -> Tuple[Found, ...]:
        return tuple(f for f in self.found if f.effect == effect)

    def controls_of_its_own(self) -> Tuple[Found, ...]:
        """The meter. Unifying means this reaches nothing."""
        return tuple(f for f in self.of_surface(WIDGET) if f.how == "markup")

    def ring_backed(self) -> Tuple[Found, ...]:
        """The part of the meter that is also on the ring, and so can go."""
        return tuple(f for f in self.controls_of_its_own() if f.ring_action)

    def sentence(self) -> str:
        own = len(self.controls_of_its_own())
        backed = len(self.ring_backed())
        listening = [f for f in self.found if f.how == "listening"]
        return (
            f"{own} controls of its own, {backed} of them also on the ring. "
            f"{len(self.of_surface(GESTURE))} things done to the scene, "
            f"{len([f for f in self.of_surface(LIST) if f.how == 'listening'])} "
            f"places in the lists beside it, "
            f"{'a ring' if self.of_surface(RING) else 'no ring yet'}, "
            f"and {len(self.of_surface(DRAG))} ways of taking hold of a piece. "
            f"Counted from {len(self.found) - len(listening)} controls in the "
            f"markup and {len(listening)} places the page listens."
        )


FILLED_IN = re.compile(r"\$\{[^{}]*\}")
BOUNDARY = ";{}"


def _statement_tail(before: str) -> str:
    """The text since the last statement ended.

    Reading stops at a statement boundary so a label mentioned in the line above
    cannot claim a listener belonging to something else.

    A gap filled in as the page is written — `pos-${axis}` — is not a statement
    boundary, however much its brackets look like one. Those are stepped over,
    because one of them once cut a name in half and produced an entry called `?`.
    """
    tail = before[-400:]
    protected = {
        index for span in FILLED_IN.finditer(tail) for index in range(span.start(), span.end())
    }
    cut = max(
        (index for index, char in enumerate(tail) if char in BOUNDARY and index not in protected),
        default=-1,
    )
    return tail[cut + 1 :].replace("\n", " ")


def _handler_body(after: str) -> str:
    """Just the handler, stopping where the listening call closes.

    Reading a fixed number of characters ran off the end of a short handler into
    whatever came next, and reported the next line's work as this one's.
    """
    depth = 1
    for index, char in enumerate(after):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return after[:index]
    return after


def _name_for(before: str) -> str:
    """What the thing being listened on is called."""
    tail = _statement_tail(before)
    for pattern, name in FETCHED_BY_LABEL:
        if re.search(pattern, tail):
            return name
    trimmed = tail.rstrip().rstrip(".?").rstrip()
    by_id = FETCHED_BY_ID.search(trimmed)
    if by_id:
        return by_id.group(1)
    found = LAST_WORD.search(trimmed)
    return found.group(1) if found else "?"


def _verb_in(handler: str) -> str:
    """The first thing the handler actually does."""
    bare = BARE_HANDLER.match(handler)
    if bare and bare.group(1) not in PLUMBING and "(" not in handler.split(",", 1)[0]:
        return bare.group(1)
    for call in A_CALL.finditer(handler):
        word = call.group(1)
        if word not in PLUMBING:
            return word
    return NO_CALL


def _form_before(text: str, position: int) -> Optional[str]:
    """The id of the form a control sits in, read backwards from it."""
    opened = None
    for match in A_FORM.finditer(text, 0, position):
        opened = match
    if opened is None:
        return None
    if text.count("</form>", opened.end(), position):
        return None
    found = HAS_ID.search(opened.group(1))
    return found.group(1) if found else None


def _name_in_markup(attributes: str, text: str = "", position: int = 0) -> Optional[str]:
    """What a control written into the page is called.

    Its id where it has one; failing that what it carries; failing that its
    class; and a submit button, which has none of those, by the form it sends,
    so that two forms' send buttons are two.
    """
    found = HAS_ID.search(attributes)
    if found:
        return found.group(1)
    for pattern, kind in BY_WHAT_IT_CARRIES:
        carried = pattern.search(attributes)
        if carried:
            return f"{kind}:{carried.group(1)}"
    found = HAS_CLASS.search(attributes)
    if found:
        return found.group(1).split()[0]
    if IS_SUBMIT.search(attributes):
        form = _form_before(text, position)
        return f"{form}:submit" if form else "submit"
    for pattern, name in BY_SHAPE:
        if pattern.search(attributes):
            return name
    return None


def _line_of(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def _from_markup(text: str) -> Tuple[List[Found], List[str]]:
    found: List[Found] = []
    unknown: List[str] = []
    for match in MARKUP.finditer(text):
        tag, attributes = match.group(1).lower(), match.group(2)
        name = _name_in_markup(attributes, text, match.start())
        if name is None:
            continue
        if name not in CONTROLS:
            unknown.append(f"line {_line_of(text, match.start())}: <{tag}> called {name!r}")
            continue
        surface, effect, description = CONTROLS[name]
        found.append(
            Found(
                name=name,
                surface=surface,
                effect=effect,
                description=description,
                line=_line_of(text, match.start()),
                how="markup",
                key=name,
                ring_action=RING_BACKED.get(name),
            )
        )
    return found, unknown


def _from_listening(text: str) -> Tuple[List[Found], List[str]]:
    found: List[Found] = []
    unknown: List[str] = []
    for match in LISTENS.finditer(text):
        name = _name_for(text[: match.start()])
        event = match.group(1)
        verb = _verb_in(_handler_body(text[match.end() :]))
        key = f"{name}:{event}:{verb}"
        line = _line_of(text, match.start())
        if key not in LISTENING:
            unknown.append(f"line {line}: {key}")
            continue
        surface, effect, description = LISTENING[key]
        found.append(
            Found(
                name=name,
                surface=surface,
                effect=effect,
                description=description,
                line=line,
                how="listening",
                key=key,
                ring_action=RING_BACKED.get(key),
            )
        )
    return found, unknown


def take(page: Path | None = None) -> Census:
    """Count what a person can operate, from the page itself.

    The viewer unless told otherwise; ``take(MONITOR)`` counts the monitor
    page. One page at a time, and the two numbers are never added.
    """
    text = (page or VIEWER).read_text(encoding="utf-8")
    from_markup, unknown_markup = _from_markup(text)
    from_listening, unknown_listening = _from_listening(text)
    unknown = unknown_markup + unknown_listening
    if unknown:
        raise Unclassified(
            f"The page has {len(unknown)} thing(s) nobody has classified:\n  "
            + "\n  ".join(unknown)
            + "\nAdd each to CONTROLS or LISTENING in apothecary/census.py, saying "
            "what kind of surface it is and what it changes. The count is refused "
            "until then, because a control nobody has decided about is exactly the "
            "one that makes the number wrong."
        )
    if not from_markup and not from_listening:
        raise NothingFound(
            "Nothing at all was found in this page — no controls in the markup and "
            "nowhere it listens. That is far more likely to mean it could not be "
            "read than that it has nothing in it, so no number is given. If the "
            "page really is empty, count something else."
        )
    return Census(found=tuple(from_markup + from_listening))


HEADINGS = {
    "markup": "Controls written into the page — the meter. Unifying takes this to nothing.",
    "listening": "Places the page listens.",
}


def report(page: Path | None = None) -> str:
    """The census as something to read. Every entry, none folded away."""
    census = take(page)
    lines = [census.sentence(), ""]
    for how in ("markup", "listening"):
        lines.append(HEADINGS[how])
        for surface in SURFACES:
            of_surface = [f for f in census.of_surface(surface) if f.how == how]
            if not of_surface:
                continue
            lines.append(f"  {surface} ({len(of_surface)})")
            for entry in sorted(of_surface, key=lambda f: f.line):
                backed = f"  ⌗ {entry.ring_action}" if entry.ring_action else ""
                lines.append(
                    f"    line {entry.line:>5}  {entry.effect:<14}  {entry.description}{backed}"
                )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
