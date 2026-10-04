"""Count the ways a page accepts a command.

A report, not a gate: `apothecary census` prints it, and one test holds the
viewer's count under a ceiling. The count is taken from the page itself, by
the rule written down here.

## What is counted, and how

**Controls of its own.** Every button, drop-down, tick-box, typing box, form and
link written into the page, found by reading its markup, so a control counts
whether or not anything listens to it. Each is counted separately: three
typing boxes are three.

**Places the page listens.** Every point where the page waits for something a
person does, identified by three things together: what it listens on, what it
listens for, and *the first thing it then does*. The third part makes two
buttons in the same row of a list two entries, so a new control cannot hide
inside an old one.

Each is looked up in a table below. Anything not in the table is counted as
`unclassified` and listed with its line; an unclassified control in the markup
still counts toward the meter, so adding one raises the number whether or not
anybody filed it.

## The two questions asked of each one

**What kind of surface is it?**

- `widget` -- a control of its own, invented for one job. **This is the
  meter.** Unifying means it falls to zero, not to a smaller pile.
- `gesture` -- something done to the scene itself: the wheel, a double tap, a key.
- `list` -- the trails, trees and rows beside the scene.
- `drag` -- taking hold of the thing on screen and moving it.
- `ring` -- the button that opens the ring. The ring's own listeners live in
  `/static/ring.js` and are counted once, behind that button.
- `automatic` -- the page reacting to itself.

**What does it change?**

- `what-is-there` -- the arrangement itself, or the machine is told to change
  something.
- `what-you-see` -- which part you are looking at, what is picked out, what is
  folded away. The arrangement is the same afterwards, though the machine may
  have fetched and built shapes to show it.

## Ring-backed

A control of its own that does the same thing as a cell of the ring is
**ring-backed**: `RING_BACKED` names the ring action beside the control's name.
The meter does not fall because a control is ring-backed; it falls when the
control is deleted.

## What this cannot see

- It reads the page as text. A listener written inside a comment or a quoted
  string would be counted.
- It sees listening done with `addEventListener`, not a handler assigned to
  `.onclick`. Such a control is still counted from the markup, which is why the
  markup is the meter.
- The drawing library's own listeners (turning and sliding the view) are not in
  this count.
- It is one page at a time, plus the widget modules the page imports and the
  marks modules it imports by name (`MARKS`: what the world wears -- a
  machine's marks, a picture's -- and the boards' model behind them).
  `ring.js`, `panels.js` and `anchors.js` stay off the meter as chrome with
  their own tests; `board_text.js` writes text and listens to nothing. The command line, direct
  requests and the other pages are not in the number.
- It refuses when it finds nothing, because a page it failed to read and a page
  with no controls must not produce the same answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
VIEWER = TEMPLATES / "fractal_viewer.html.j2"
MONITOR = TEMPLATES / "monitor.html.j2"
FIRMWARE = TEMPLATES / "firmware.html.j2"
PAGES = (VIEWER, MONITOR, FIRMWARE)

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

# Both the surface and the effect of something in neither table.
UNCLASSIFIED = "unclassified"


class NothingFound(Exception):
    """The page was read and nothing was found in it.

    A refusal, not an answer of zero: a page that could not be read and a page
    with no controls in it must not produce the same number.
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
    "zoom-in-btn": (WIDGET, WHAT_YOU_SEE, "a button that goes into the chosen piece"),
    "status-select": (WIDGET, WHAT_IS_THERE, "a drop-down for the state of a piece"),
    "pos-x": (WIDGET, WHAT_IS_THERE, "a box for typing where a piece is, across"),
    "pos-y": (WIDGET, WHAT_IS_THERE, "a box for typing where a piece is, along"),
    "pos-z": (WIDGET, WHAT_IS_THERE, "a box for typing where a piece is, up"),
    "part-regenerate-btn": (WIDGET, WHAT_IS_THERE, "a button that rebuilds a piece"),
    "part-scad-download": (WIDGET, NOTHING, "a link that downloads the piece's recipe"),
    # The staged numbers of a piece: changed on the sliders, then kept or not.
    "apply-btn": (WIDGET, WHAT_IS_THERE, "a button that rebuilds a piece with its staged numbers"),
    "revert-btn": (WIDGET, WHAT_YOU_SEE, "a button that puts the staged numbers back"),
    # How much of a subassembly to draw, and whether to outline its extent.
    "detail-mode": (WIDGET, WHAT_YOU_SEE, "a drop-down for how much of each subassembly to draw"),
    "overlay-toggle": (WIDGET, WHAT_YOU_SEE, "a tick-box that outlines each subassembly's extent"),
    "detail-select": (WIDGET, WHAT_YOU_SEE, "the same drop-down, for the chosen piece only"),
    "firmware-link": (WIDGET, NOTHING, "a link to the firmware page"),
    "monitor-link": (WIDGET, NOTHING, "a link to the printer monitor page"),
    # The Device section of the chosen piece: one line, the board pinned to it
    # and what it is doing, with Open (its Machine) and the pin's take-back; or,
    # with nothing pinned, the boards it can be pinned to. Drawn afresh each
    # time the piece changes, so these are found by class rather than id.
    "dev-open": (WIDGET, WHAT_YOU_SEE, "a button that opens the pinned board's Machine"),
    "dev-monitor": (WIDGET, NOTHING, "a link to a printer's monitor page"),
    "dev-unpin": (WIDGET, WHAT_IS_THERE, "a button that unpins the board from the piece"),
    "dev-via": (WIDGET, WHAT_YOU_SEE, "a link to the piece inside that holds the board"),
    "dev-rescan": (WIDGET, WHAT_YOU_SEE, "a button that looks for boards again"),
    "dev-manual": (WIDGET, WHAT_IS_THERE, "a box for typing a port, S/N or address to pin"),
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
    # The board's one log, in its Machine: a report to ask a printer for, and
    # what to show of the traffic.
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
    # the bed
    "level-probe": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that homes, probes the bed and keeps the reading",
    ),
    "level-read": (
        WIDGET,
        WHAT_YOU_SEE,
        "a button that reads the stored mesh and keeps the reading",
    ),
    "corner:FL": (WIDGET, WHAT_IS_THERE, "a button that moves the nozzle to the front-left corner"),
    "corner:FR": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that moves the nozzle to the front-right corner",
    ),
    "corner:BL": (WIDGET, WHAT_IS_THERE, "a button that moves the nozzle to the back-left corner"),
    "corner:BR": (WIDGET, WHAT_IS_THERE, "a button that moves the nozzle to the back-right corner"),
    # ---- the firmware page, templates/firmware.html.j2 -------------------
    # The toolchain: install it, list what it knows, add to it.
    "refresh-btn": (WIDGET, WHAT_YOU_SEE, "a button that asks the toolchain's state again"),
    "boards-btn": (WIDGET, WHAT_YOU_SEE, "a button that rescans the ports"),
    "install-btn": (WIDGET, WHAT_IS_THERE, "a button that installs or updates arduino-cli"),
    "install-force": (WIDGET, WHAT_YOU_SEE, "a tick-box that makes the install start over"),
    "lib-input": (WIDGET, WHAT_YOU_SEE, "a box for a library to install"),
    "lib-btn": (WIDGET, WHAT_IS_THERE, "a button that installs that library"),
    "core-install": (WIDGET, WHAT_IS_THERE, "a button that installs a board core"),
    # Sketches: pick one, name the board and the port, build and send.
    "fqbn-input": (WIDGET, WHAT_YOU_SEE, "a box for the board to build for"),
    "port-select": (WIDGET, WHAT_YOU_SEE, "a drop-down of ports to upload to"),
    "compile-btn": (WIDGET, WHAT_IS_THERE, "a button that compiles the chosen sketch"),
    "upload-btn": (WIDGET, WHAT_IS_THERE, "a button that compiles and uploads it"),
    # esptool: raw images onto an Espressif chip.
    "esp-chip": (WIDGET, WHAT_YOU_SEE, "a box for the chip to flash"),
    "esp-baud": (WIDGET, WHAT_YOU_SEE, "a box for the flashing baud rate"),
    "esp-off": (WIDGET, WHAT_YOU_SEE, "a box for an image's flash offset"),
    "esp-path": (WIDGET, WHAT_YOU_SEE, "a box for an image's path"),
    "esp-rm": (WIDGET, WHAT_YOU_SEE, "a button that drops an image row"),
    "esp-add": (WIDGET, WHAT_YOU_SEE, "a button that adds an image row"),
    "esp-erase": (WIDGET, WHAT_YOU_SEE, "a tick-box that erases the flash first"),
    "esp-flash-btn": (WIDGET, WHAT_IS_THERE, "a button that flashes the images"),
    "cancel-btn": (WIDGET, WHAT_IS_THERE, "a button that cancels the running task"),
    # Each device card: what a board is, and the ways of asking it. (Its
    # monitor link shares `dev-monitor` with the viewer's Device section.)
    "dev-probe": (WIDGET, WHAT_IS_THERE, "a button that probes the chip with esptool (resets it)"),
    "dev-identify": (WIDGET, WHAT_YOU_SEE, "a button that listens for the sketch's hello"),
    "dev-printer": (WIDGET, WHAT_YOU_SEE, "a button that asks M115, or polls a printer once"),
    "dev-live": (WIDGET, WHAT_YOU_SEE, "a button that streams the board's serial output"),
    # ---- the Bench, apothecary/static/widgets/{toolchain,sketches,tasks}.js
    # The firmware page's sections in front of the world, written once in the
    # modules, named as the page named them (by class now, since a form is
    # mounted by the Bench and by a board's Flashing card). Added: the sketch is
    # chosen from a drop-down rather than a list, and raw flash takes its images
    # as lines of one box rather than rows of three controls and an add button.
    "sketch-select": (WIDGET, WHAT_YOU_SEE, "a drop-down of the sketches under parts/"),
    "esp-images": (
        WIDGET,
        WHAT_YOU_SEE,
        "a box for the images to flash, one offset and path a line",
    ),
    # ---- Pictures, apothecary/static/widgets/picture_list.js -------------
    # Every picture under the picture root, each row chosen by a click for the
    # ring's Picture › Folder to pin (a list, not a control), a kept one with
    # Forget (TAKEN_BACK), Purge, a file picker that keeps pictures here pinned
    # nowhere, and the gathering's section until gathering leaves core: the
    # pictures ticked, gathered into a report, and what a person says about them.
    "pictures-forget": (WIDGET, WHAT_YOU_SEE, "a button that forgets one kept picture"),
    "pictures-purge": (
        WIDGET,
        WHAT_YOU_SEE,
        "a button that forgets every picture the browser put here",
    ),
    "pic-file": (WIDGET, WHAT_YOU_SEE, "a file picker that keeps chosen pictures on this machine"),
    "pic-all": (WIDGET, WHAT_YOU_SEE, "a tick-box that ticks every picture"),
    "pic-gather": (WIDGET, WHAT_YOU_SEE, "a button that gathers the ticked pictures"),
    "gather-answers": (WIDGET, WHAT_YOU_SEE, "a box for what you know about the pictures"),
    "answer": (WIDGET, WHAT_YOU_SEE, "a button that answers one of the machine's questions"),
    # ---- Site's Pinned, apothecary/static/widgets/pinned.js ---------------
    # What a page pinned, every site's, each taken back from its row (TAKEN_BACK).
    "pinned-camera-unpin": (WIDGET, WHAT_IS_THERE, "a button that unpins one camera, in any site"),
    "pinned-view-unpin": (WIDGET, WHAT_IS_THERE, "a button that unpins one view, in any site"),
    "pinned-board-unpin": (WIDGET, WHAT_IS_THERE, "a button that takes one board's pin back"),
    # Selected: the one width a view is sized by (a chosen shape's long side
    # when one is chosen). A number the ring cannot type; Size puts the cursor in it.
    "view-width": (WIDGET, WHAT_IS_THERE, "a box for how wide a picture is, or one shape's side"),
    # printing from here: a kept file, streamed
    "print-file": (WIDGET, WHAT_YOU_SEE, "a file picker that keeps a G-code file on the host"),
    "print-pick": (WIDGET, WHAT_YOU_SEE, "a drop-down of the files kept on the host"),
    "print-delete": (WIDGET, WHAT_YOU_SEE, "a button that forgets the chosen file"),
    "print-part": (
        WIDGET,
        WHAT_YOU_SEE,
        "a drop-down of the parts a print from here makes, from the printer's site",
    ),
    "print-start": (WIDGET, WHAT_IS_THERE, "a button that streams the chosen file to the printer"),
    "print-pause": (WIDGET, WHAT_IS_THERE, "a button that stops feeding the print from here"),
    "print-resume": (WIDGET, WHAT_IS_THERE, "a button that feeds the print from here again"),
    "print-cancel": (WIDGET, WHAT_IS_THERE, "a button that ends the print from here, heaters off"),
}

# A control of its own that does the same thing as a cell of the ring, and the
# action that cell carries. Keyed by the control's name, or by a listening
# key, since a button and the place the page listens to it are the same way
# in. Every action here must be one the rings produce; a test holds it to
# `apothecary.menu`'s vocabulary, so a control cannot claim a backing that
# does not exist.
RING_BACKED: Dict[str, str] = {
    # the viewer's Device section: Open is Device › Open, the board's Machine
    "dev-open": "device:open",
    "dev-query": "device:query",
    "dev-pin": "device:pin",
    "dev-pin-manual": "device:pin",
    "dev-unpin": "device:unpin",
    "dev-rescan": "device:rescan",
    "devOpen:click:openMachine": "device:open",
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
    "cmd:M108": "control:break-wait",
    "cmd:M420 S1": "control:mesh-on",
    "cmd:M420 S0": "control:mesh-off",
    "level-probe": "level:probe",
    "level-read": "level:read",
    "corner:FL": "control:corner:FL",
    "corner:FR": "control:corner:FR",
    "corner:BL": "control:corner:BL",
    "corner:BR": "control:corner:BR",
    # The firmware page's device cards: a poll has its cell; the monitor link and
    # the live stream open a board's Machine on a page of its own, as Device ›
    # Open does in front of the world; probe and identify have no cell yet.
    "dev-printer": "device:poll",
    "dev-monitor": "device:open",
    "dev-live": "device:open",
    "boards-btn": "device:rescan",
    # The Bench's buttons are the cells of the canvas ring's Panels › Bench, each
    # acting on what the Bench has chosen; a core's Install is Bench › Cores › its
    # core. The form's boxes and drop-downs, the force tick-box and raw flash's
    # boxes choose what a cell acts on, and no cell chooses them.
    "install-btn": "bench:install",
    "core-install": "bench:core:arduino:avr",
    "coresEl:click:closest": "bench:core:arduino:avr",
    "lib-btn": "bench:libraries",
    "libEl:keydown:libraries": "bench:libraries",
    "compile-btn": "bench:compile",
    "upload-btn": "bench:upload",
    "esp-flash-btn": "bench:esptool",
    "cancel-btn": "bench:cancel",
    # Gather and Pictures' Purge are cells of the canvas ring's Pictures. The
    # per-row take-backs of Pinned and Pictures are not here: see TAKEN_BACK.
    # Pictures has no Pin here: a row chosen there is told to the ring, whose
    # Picture › Folder pins it, the seven newest by name and an older one as
    # the eighth cell.
    "pic-gather": "camera:gather",
    "pictures-purge": "picture:purge",
    # A file dropped on the world, or chosen in the dialog Picture › Add opens.
    "canvas:drop:onDropFiles": "picture:add",
    "input:change:addFiles": "picture:add",
    # A view drawn from its row in Selected, or from its place on a picture's row
    # in Pictures, as Picture › Views draws one.
    "row:click:drawView": "picture:draw:view_1",
    "chip:click:showView": "picture:draw:view_1",
    # The Print cell's verbs go to whichever print is running, the card's or
    # the one from here; Send file is the one from here alone.
    "print-start": "print:start",
    "print-pause": "control:sd-pause",
    "print-resume": "control:sd-resume",
    "print-cancel": "control:sd-abort",
    # Navigation: the list rows, the step-out button and the go-in button are
    # what the canvas ring's Pieces and Up and the node ring's Zoom in do.
    "zoom-out-btn": "zoom-out",
    "zoom-in-btn": "zoom-in",
    "li:click:selectChild": "select:printer_1",
    "badge:click:selectPath": "select:printer_1",
    "zoomOutBtn:click:zoomOut": "zoom-out",
    "zoomInLink:click:zoomIn": "zoom-in",
    "reconnect": "device:reconnect",
    "reset": "device:reset",
    "release": "device:release",
    "ctl:change:arm": "control:arm",
}

# A control kept on purpose beside the ring: the button on a row of Site's
# Pinned or of Pictures that takes back what the row names -- a camera or a view
# unpinned, a board's pin taken back, a kept picture forgotten -- in whichever
# site it stands. §6 of the draft record *Personal data stays on the device* asks
# that what a page placed or pinned be listed by the same page, every site's,
# and taken back the same way, and a ring cell reaches another site's pin only
# from that site. So these are a lasting exception, the one the pictures plan
# asks the *rad host integration* record's §5 to name, and are **not**
# ring-backed: the meter counts them, and never expects them to go. Keyed like
# RING_BACKED, by the control's name or its listening key; the value is what the
# row takes back.
TAKEN_BACK: Dict[str, str] = {
    "pinned-camera-unpin": "a camera's pin, every site's",
    "pinned-view-unpin": "a view, every site's",
    "pinned-board-unpin": "a board's pin, every site's",
    "pinned-list:click:closest": "any pin, from its row",
    "pictures-forget": "a picture the browser kept",
    "forgetBtn:click:forget": "a picture the browser kept, from its row",
}

MARKUP = re.compile(
    r"<(select|input|button|textarea|form|a)\b([^>]*)>",
    re.IGNORECASE,
)
HAS_ID = re.compile(r"\bid=[\"']([\w-]+)[\"']")
HAS_CLASS = re.compile(r"\bclass=[\"']([^\"']+)[\"']")
# Classes that say how a control looks, not what it is: `class="small
# dev-probe"` is the probe button, not a small one.
LOOK_ONLY_CLASSES = frozenset({"small", "primary", "danger", "row", "meta"})
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
    (re.compile(r"\bdata-corner=[\"']([^\"']+)[\"']"), "corner"),
)

# A markup control with neither an id nor a class is named by where its link
# goes. Read after the id and the class: an anchor that has a class and also a
# link is the thing its class says.
BY_SHAPE: Sequence[Tuple[re.Pattern, str]] = (
    (re.compile(r"\bhref=[\"'][^\"']*/scad[\"']"), "part-scad-download"),
    (re.compile(r"\bhref=[\"'][^\"']*/firmware/monitor[\"']"), "monitor-link"),
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
    "posAxis:change:recomputeWorldBounds": (WIDGET, WHAT_IS_THERE, "typing a position"),
    "statusSelect:change:submitStatus": (WIDGET, WHAT_IS_THERE, "choosing a state"),
    # The editor's Regenerate STL: the staged set applied to its target, a
    # part's STL rendered again (a made piece has no such button: Apply is its
    # rebuild).
    "regenerateBtn:click:applyEditor": (WIDGET, WHAT_IS_THERE, "the rebuild button"),
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
    # An anchor: a machine's badge standing over it in the world (anchors.js).
    "badge:click:selectPath": (LIST, WHAT_YOU_SEE, "picking the machine a badge stands over"),
    # A place badge: a host's camera and view, or the floor's (picture_marks.js).
    "badge:click:onSelect": (
        LIST,
        WHAT_YOU_SEE,
        "picking the place a badge stands over: a structure, or the floor",
    ),
    # ---- pictures in the world: a drop, a paste, Selected's width and rows --
    "canvas:dragover:(nothing)": (
        GESTURE,
        NOTHING,
        "holding a file over the world, so that it can be dropped there",
    ),
    "canvas:drop:onDropFiles": (
        GESTURE,
        WHAT_IS_THERE,
        "dropping pictures on a structure or the floor: kept, and pinned there as views",
    ),
    "window:paste:onPaste": (
        GESTURE,
        WHAT_IS_THERE,
        "pasting a picture: kept, and pinned at the selected place as a view",
    ),
    "widthBox:change:setWidth": (WIDGET, WHAT_IS_THERE, "typing a picture's width, or a shape's"),
    "row:click:drawView": (LIST, WHAT_YOU_SEE, "a view's row in Selected, drawing that view"),
    # pictures.js: the browser's cameras and the dialog Picture › Add opens.
    "mediaDevices:devicechange:listCameras": (
        AUTOMATIC,
        NOTHING,
        "a camera plugged in or out, and the list of this browser's cameras follows",
    ),
    "status:change:listCameras": (
        AUTOMATIC,
        NOTHING,
        "the camera allowed or refused for this site in the address bar, "
        "and the list of this browser's cameras follows",
    ),
    "video:loadeddata:resolve": (
        AUTOMATIC,
        NOTHING,
        "a camera's first frame arrived, so a picture can be taken from it",
    ),
    "input:change:addFiles": (
        WIDGET,
        WHAT_IS_THERE,
        "the pictures chosen in the dialog Picture › Add opens: kept, and pinned there as views",
    ),
    # ---- Pictures ----------------------------------------------------------
    # A row chosen, one at a time, and told to the ring; Escape lets it go.
    "row:click:rowClicked": (
        LIST,
        WHAT_YOU_SEE,
        "a picture's row, chosen for the ring's Picture › Folder to pin, or let go",
    ),
    "window:keydown:letGo": (GESTURE, WHAT_YOU_SEE, "a key that lets go of the chosen picture"),
    "forgetBtn:click:forget": (
        WIDGET,
        WHAT_IS_THERE,
        "a kept picture's Forget: the picture forgotten and its views unpinned, every site's",
    ),
    "chip:click:showView": (
        LIST,
        WHAT_YOU_SEE,
        "a place on a picture's row where it is pinned: selected, and that view drawn",
    ),
    "pic-all:change:(nothing)": (WIDGET, WHAT_YOU_SEE, "ticking every picture at once"),
    "gather-out:click:closest": (WIDGET, WHAT_YOU_SEE, "answering a question with a button"),
    "pic-file:change:addFiles": (WIDGET, WHAT_YOU_SEE, "adding the chosen pictures"),
    # ---- Site --------------------------------------------------------------
    "pinned-list:click:closest": (
        WIDGET,
        WHAT_IS_THERE,
        "taking back what a row of Pinned names -- a camera, a view, a board's pin -- "
        "whatever site it is in",
    ),
    "pinnedEl:toggle:pinnedOpened": (
        LIST,
        WHAT_YOU_SEE,
        "unfolding Site's Pinned, which lists every site's pins again",
    ),
    "li:click:goToProblem": (
        LIST,
        WHAT_YOU_SEE,
        "a problem's row at the top of Site, selecting its piece at its level",
    ),
    "siteJobsListEl:click:closest": (
        LIST,
        WHAT_YOU_SEE,
        "a job's row in Site's Jobs, selecting its machine at its level and opening it",
    ),
    # A readout that opens what it counts, as a badge selects what it stands over;
    # a span listened to, not a control written into the markup.
    "validityEl:click:openProblems": (
        WIDGET,
        WHAT_YOU_SEE,
        "the toolbar's count of problems, opening them at the top of Site",
    ),
    "li:dblclick:zoomIn": (LIST, WHAT_YOU_SEE, "going into a piece from the list"),
    "rootCrumb:click:jumpTo": (LIST, WHAT_YOU_SEE, "the top of the trail"),
    "crumb:click:jumpTo": (LIST, WHAT_YOU_SEE, "a step on the trail"),
    # how much to draw
    "detailModeEl:change:clear": (WIDGET, WHAT_YOU_SEE, "choosing how much to draw"),
    "overlayToggle:change:renderFocus": (WIDGET, WHAT_YOU_SEE, "the outlines tick-box"),
    "select:change:delete": (WIDGET, WHAT_YOU_SEE, "choosing how much to draw of one piece"),
    # the Device section of the chosen piece
    "devOpen:click:openMachine": (WIDGET, WHAT_YOU_SEE, "opening the pinned board's Machine"),
    "devUnpin:click:setNodeDevice": (WIDGET, WHAT_IS_THERE, "unpinning the board"),
    "devPin:click:setNodeDevice": (WIDGET, WHAT_IS_THERE, "pinning the chosen board"),
    "devQuery:click:queryPort": (WIDGET, WHAT_YOU_SEE, "asking the chosen board what it is"),
    "devVia:click:selectPath": (
        WIDGET,
        WHAT_YOU_SEE,
        "going to the piece inside that holds the board",
    ),
    "devRescan:click:rescanDevices": (WIDGET, WHAT_YOU_SEE, "looking for boards again"),
    "devPinManual:click:pinManual": (WIDGET, WHAT_IS_THERE, "pinning the typed board"),
    "manualIn:keydown:pinManual": (WIDGET, WHAT_IS_THERE, "pinning the typed board, by Enter"),
    # the page reacting to itself
    "window:resize:onResize": (AUTOMATIC, NOTHING, "the window changed size on its own"),
    # boards.js: a devkit's serial stream, while its Machine listens to it
    "es:open:opened": (AUTOMATIC, NOTHING, "a devkit's serial stream connected, and says so"),
    "es:close:streamStopped": (
        AUTOMATIC,
        NOTHING,
        "a devkit's serial stream stopped (a task took the port), and is opened again",
    ),
    # ---- the monitor page, templates/monitor.html.j2 ----------------------
    # Most of the monitor's buttons are wired by assignment rather than by
    # listening, so the markup carries them; these are the ones that listen.
    "port:change:selectPort": (WIDGET, WHAT_YOU_SEE, "choosing a printer port"),
    "portSel:change:mountFor": (AUTOMATIC, NOTHING, "the board view following the chosen port"),
    "level-history:click:closest": (
        LIST,
        WHAT_YOU_SEE,
        "picking an earlier bed reading to look at",
    ),
    "level-card:click:closest": (WIDGET, WHAT_IS_THERE, "a corner button, moving the nozzle there"),
    # ---- the Bench --------------------------------------------------------
    "coresEl:click:closest": (WIDGET, WHAT_IS_THERE, "a core's Install button"),
    "libEl:keydown:libraries": (WIDGET, WHAT_IS_THERE, "installing the typed libraries, by Enter"),
    "sketchEl:change:choose": (
        WIDGET,
        WHAT_YOU_SEE,
        "choosing a sketch, which fills in the board it is built for",
    ),
    "fqbnEl:input:enable": (WIDGET, WHAT_YOU_SEE, "typing a board, which enables the buttons"),
    "portEl:change:enable": (WIDGET, WHAT_YOU_SEE, "choosing a port, which enables the buttons"),
    "historyEl:click:closest": (LIST, WHAT_YOU_SEE, "opening an earlier task's output"),
    # ---- the firmware page ------------------------------------------------
    "es:close:stopLive": (AUTOMATIC, NOTHING, "the serial stream stopped, and the card says so"),
    "devices:click:closest": (
        WIDGET,
        WHAT_YOU_SEE,
        "a device card's button: probe, identify, poll, live",
    ),
    "cores:click:closest": (WIDGET, WHAT_IS_THERE, "a core's Install button"),
    "sketches:click:closest": (LIST, WHAT_YOU_SEE, "choosing a sketch from the list"),
    "fqbn-input:input:updateButtons": (
        WIDGET,
        WHAT_YOU_SEE,
        "typing a board, which enables the buttons",
    ),
    "port-select:change:updateButtons": (
        WIDGET,
        WHAT_YOU_SEE,
        "choosing a port, which enables the buttons",
    ),
    "esp-images:click:contains": (WIDGET, WHAT_YOU_SEE, "an image row's drop button"),
    "history:click:closest": (LIST, WHAT_YOU_SEE, "opening an earlier task's log"),
    "print-file:change:keepPrintFile": (
        WIDGET,
        WHAT_YOU_SEE,
        "choosing a file to keep on the host",
    ),
    "print-pick:change:renderPrint": (
        WIDGET,
        WHAT_YOU_SEE,
        "choosing which kept file the buttons mean",
    ),
    "auto:change:schedule": (WIDGET, WHAT_YOU_SEE, "the poll-on-a-schedule tick-box"),
    "interval:change:schedule": (WIDGET, WHAT_YOU_SEE, "choosing how often to poll"),
    "qform:submit:query": (WIDGET, WHAT_YOU_SEE, "asking the printer for a report"),
    "show-polls:change:renderLog": (WIDGET, WHAT_YOU_SEE, "the poll-traffic tick-box"),
    "ctl:change:arm": (WIDGET, WHAT_YOU_SEE, "arming or disarming the control latch"),
    "h-fan:input:(nothing)": (WIDGET, WHAT_YOU_SEE, "sliding the fan speed, shown beside it"),
    "control:click:closest": (
        WIDGET,
        WHAT_IS_THERE,
        "one listener for the whole control overlay, told which button by what it carries",
    ),
    "document:visibilitychange:onVisibility": (
        AUTOMATIC,
        NOTHING,
        "the page was hidden or shown, and the boards' pollers pause or go on",
    ),
    "window:beforeunload:onUnload": (
        AUTOMATIC,
        NOTHING,
        "leaving the page stops the polling and lets go of the serial streams",
    ),
}

LISTENS = re.compile(r"addEventListener\s*\(\s*['\"]([\w-]+)['\"]\s*,")

# Fetched by the label they carry in the page rather than by a plain name.
# Searched only within the current statement, never across one, so a mention in
# the line above cannot claim a listener that is not its own. Longer labels
# before the ones they begin with, so `.dev-pin-manual` is not read as `.dev-pin`.
FETCHED_BY_LABEL: Sequence[Tuple[str, str]] = (
    (r"pos-\$\{axis\}", "posAxis"),
    (r"part-regenerate-btn", "regenerateBtn"),
    (r"\.zoom-in-btn", "zoomInLink"),
    (r"\.dev-pin-manual", "devPinManual"),
    (r"\.dev-open", "devOpen"),
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
    # What the control takes back, when it is a take-back on a row of Site's Pinned
    # or of Pictures (TAKEN_BACK): kept beside the ring on purpose, never ring-backed.
    taken_back: Optional[str] = None
    # Where the control is written: the page itself, or a widget module the
    # page mounts (apothecary/static/widgets/*.js). A widget's controls are
    # the page's on every page that mounts it, and one thing across pages.
    source: str = ""


@dataclass(frozen=True)
class Census:
    found: Tuple[Found, ...]

    def of_surface(self, surface: str) -> Tuple[Found, ...]:
        return tuple(f for f in self.found if f.surface == surface)

    def controls_of_its_own(self) -> Tuple[Found, ...]:
        """The meter: widgets in the markup, and markup nobody has classified yet."""
        return tuple(
            f for f in self.found if f.how == "markup" and f.surface in (WIDGET, UNCLASSIFIED)
        )

    def unclassified(self) -> Tuple[Found, ...]:
        """What is in neither table, markup and listening alike."""
        return self.of_surface(UNCLASSIFIED)

    def ring_backed(self) -> Tuple[Found, ...]:
        """The part of the meter that is also on the ring, and so can go."""
        return tuple(f for f in self.controls_of_its_own() if f.ring_action)

    def taken_back(self) -> Tuple[Found, ...]:
        """The part of the meter kept beside the ring on purpose: the rows' take-backs."""
        return tuple(f for f in self.controls_of_its_own() if f.taken_back)

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
    cannot claim a listener belonging to something else. A gap filled in as the
    page is written -- `pos-${axis}` -- is not a boundary, and is stepped over.
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
    """Just the handler, stopping where the listening call closes."""
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
        named = [c for c in found.group(1).split() if c not in LOOK_ONLY_CLASSES]
        if named:
            return named[0]
    if IS_SUBMIT.search(attributes):
        form = _form_before(text, position)
        return f"{form}:submit" if form else "submit"
    for pattern, name in BY_SHAPE:
        if pattern.search(attributes):
            return name
    return None


def _line_of(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def _from_markup(text: str) -> List[Found]:
    found: List[Found] = []
    for match in MARKUP.finditer(text):
        tag, attributes = match.group(1).lower(), match.group(2)
        name = _name_in_markup(attributes, text, match.start())
        if name is None:
            continue
        surface, effect, description = CONTROLS.get(
            name, (UNCLASSIFIED, UNCLASSIFIED, f"a <{tag}> in neither table")
        )
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
                taken_back=TAKEN_BACK.get(name),
            )
        )
    return found


def _from_listening(text: str) -> List[Found]:
    found: List[Found] = []
    for match in LISTENS.finditer(text):
        name = _name_for(text[: match.start()])
        event = match.group(1)
        verb = _verb_in(_handler_body(text[match.end() :]))
        key = f"{name}:{event}:{verb}"
        line = _line_of(text, match.start())
        surface, effect, description = LISTENING.get(
            key, (UNCLASSIFIED, UNCLASSIFIED, "a listener in neither table")
        )
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
                taken_back=TAKEN_BACK.get(key),
            )
        )
    return found


WIDGETS = TEMPLATES.parent / "apothecary" / "static" / "widgets"
WIDGET_IMPORT = re.compile(r"from\s+[\"']/static/widgets/([\w-]+)\.js[\"']")


def widgets_of(page: Path) -> List[Path]:
    """The widget modules a page mounts, in the order it imports them."""
    text = page.read_text(encoding="utf-8")
    return [WIDGETS / f"{name}.js" for name in WIDGET_IMPORT.findall(text)]


STATIC = TEMPLATES.parent / "apothecary" / "static"
# The marks modules: what a thing wears in the world, drawn beside the page's own
# scene and listening, when they listen, on what they draw -- and the boards'
# model (boards.js), whose poller, serial streams and page-level listeners stand
# behind every drawer of a board. Counted with the page that imports one
# directly, each entry saying which module it came from; a page that reaches one
# only through another module (the monitor, through board_view.js and
# widgets/machine.js) is not counted for it.
MARKS = ("machine_marks.js", "picture_marks.js", "pictures.js", "boards.js")
STATIC_IMPORT = re.compile(r"from\s+[\"']/static/([\w-]+\.js)[\"']")


def marks_of(page: Path) -> List[Path]:
    """The marks modules a page imports directly, in the order it imports them."""
    text = page.read_text(encoding="utf-8")
    return [STATIC / name for name in STATIC_IMPORT.findall(text) if name in MARKS]


def take(page: Path | None = None) -> Census:
    """Count what a person can operate, from the page itself.

    The viewer unless told otherwise; ``take(MONITOR)`` counts the monitor
    page. One page at a time, and the numbers are never added -- except
    that a widget module the page mounts (``/static/widgets/*.js``, its
    markup written in the module) and a marks module it imports (``MARKS``)
    are counted as part of the page, each entry saying which module it came
    from.
    """
    page = page or VIEWER
    sources = [(page, "")] + [
        (module, module.name) for module in widgets_of(page) + marks_of(page) if module.is_file()
    ]
    from_markup: List[Found] = []
    from_listening: List[Found] = []
    for path, label in sources:
        text = path.read_text(encoding="utf-8")
        from_markup += [replace(f, source=label) for f in _from_markup(text)]
        from_listening += [replace(f, source=label) for f in _from_listening(text)]
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
    unclassified = census.unclassified()
    lines = [census.sentence(), f"unclassified: {len(unclassified)}", ""]
    for how in ("markup", "listening"):
        lines.append(HEADINGS[how])
        for surface in SURFACES:
            of_surface = [f for f in census.of_surface(surface) if f.how == how]
            if not of_surface:
                continue
            lines.append(f"  {surface} ({len(of_surface)})")
            for entry in sorted(of_surface, key=lambda f: f.line):
                backed = f"  ⌗ {entry.ring_action}" if entry.ring_action else ""
                if entry.taken_back:
                    backed = f"  ⤺ takes back {entry.taken_back}"
                lines.append(
                    f"    line {entry.line:>5}  {entry.effect:<14}  {entry.description}{backed}"
                )
        lines.append("")
    if unclassified:
        lines.append(
            "Unclassified -- add each to CONTROLS or LISTENING in apothecary/census.py, "
            "saying what kind of surface it is and what it changes:"
        )
        for entry in unclassified:
            where = f"{entry.source}: " if entry.source else ""
            lines.append(f"    {where}line {entry.line:>5}  {entry.key}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
