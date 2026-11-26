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
- Nor the SCAD editor's own keys, which its CodeMirror keymap holds (F5, F6,
  Ctrl+Enter and Ctrl+S, `widgets/scad_editor.js`): they work inside the editor
  only, as its typing does, and are written in the viewer's documentation.
- The drawing library's own listeners (turning and sliding the view) are not in
  this count.
- It is one page, the viewer (``/firmware`` and ``/firmware/monitor`` lead to
  it, as the Bench and a board's Machine) -- plus the widget modules it imports
  and the marks modules it imports by name (`MARKS`: what the world wears -- a
  machine's marks, a picture's -- and the boards' model behind them).
  `ring.js`, `panels.js`, `anchors.js` and `keys.js` (how a key is named, and
  when a shortcut may act) stay off the meter as chrome with their own tests;
  `board_text.js` writes text and listens to nothing. The command line and
  direct requests are not in the number.
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
# The pages there are to count: one, the viewer. /firmware and /firmware/monitor
# redirect to it, to the Bench and a board's Machine in front of the world.
PAGES = (VIEWER,)

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


class NothingFound(Exception):  # timeless: allow a search's result, in the present
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
    # The view banner: its first crumb and the site's are the trail; a site under the
    # site crumb's ▾ is the control that chooses one.
    "universe-crumb": (LIST, WHAT_YOU_SEE, "the trail's first crumb: the universe, from anywhere"),
    "site-level": (LIST, WHAT_YOU_SEE, "the trail's crumb for the site: up to its own level"),
    "site-item": (WIDGET, WHAT_YOU_SEE, "a site under the site crumb's ▾, loading the one chosen"),
    # The header's View menu (a fold, like Site's): how the world is drawn, under
    # the views panels.js lists there as it opens.
    "snap-toggle": (WIDGET, WHAT_YOU_SEE, "a tick-box for snapping to a grid"),
    "walls-toggle": (WIDGET, WHAT_YOU_SEE, "a tick-box that lets a click in the world pick a wall"),
    "settings-open": (
        WIDGET,
        WHAT_YOU_SEE,
        "an item of the View menu that opens the Settings panel",
    ),
    "zoom-in-btn": (WIDGET, WHAT_YOU_SEE, "a button that goes into the chosen piece"),
    "status-select": (WIDGET, WHAT_IS_THERE, "a drop-down for the state of a piece"),
    "pos-x": (WIDGET, WHAT_IS_THERE, "a box for typing where a piece is, across"),
    "pos-y": (WIDGET, WHAT_IS_THERE, "a box for typing where a piece is, along"),
    "pos-z": (WIDGET, WHAT_IS_THERE, "a box for typing where a piece is, up"),
    "part-scad-download": (WIDGET, NOTHING, "a link that downloads the piece's recipe"),
    # The staged numbers of a piece: changed on the sliders, then kept or not.
    "apply-btn": (WIDGET, WHAT_IS_THERE, "a button that rebuilds a piece with its staged numbers"),
    "revert-btn": (WIDGET, WHAT_YOU_SEE, "a button that puts the staged numbers back"),
    "defaults-btn": (WIDGET, WHAT_YOU_SEE, "a button that stages a part's own numbers"),
    # The staged numbers' undo and redo, and the ghost of what was drawn before:
    # Part › History and Part › View.
    "undo-btn": (
        WIDGET,
        WHAT_YOU_SEE,
        "a button that undoes the last change to the staged numbers",
    ),
    "redo-btn": (WIDGET, WHAT_YOU_SEE, "a button that redoes the change undone"),
    "ghost-toggle": (
        WIDGET,
        WHAT_YOU_SEE,
        "a tick-box that shows a ghost of what was drawn before the newest Apply",
    ),
    # What a tab kept of a part's work before it was reloaded, offered back.
    "kept-restore": (
        WIDGET,
        WHAT_YOU_SEE,
        "a button that puts back the work the tab kept from before a reload",
    ),
    "kept-discard": (WIDGET, WHAT_YOU_SEE, "a button that lets go of that kept work"),
    # One control per parameter (widgets/part_controls.js), written there as markup,
    # so the census counts them.
    "param-slider": (WIDGET, WHAT_YOU_SEE, "a slider that stages one of a part's numbers"),
    "param-number": (
        WIDGET,
        WHAT_YOU_SEE,
        "a box that stages one of a part's numbers exactly, in step with its slider",
    ),
    "param-choice": (WIDGET, WHAT_YOU_SEE, "a drop-down that stages one of a part's choices"),
    "param-tick": (WIDGET, WHAT_YOU_SEE, "a tick-box that stages a part's yes or no"),
    "param-text": (WIDGET, WHAT_YOU_SEE, "a box that stages a part's words"),
    "param-coord": (WIDGET, WHAT_YOU_SEE, "a box that stages one number of a vector, captioned"),
    "cand": (WIDGET, WHAT_YOU_SEE, "a button that stages a contested number's candidate"),
    # A saved variant managed from its ⋯ in the part's Variants window (widgets/scad_editor.js):
    # renamed or duplicated under the name typed beside it, its history and a save of it
    # restored, compared with what is drawn, deleted to the trash; the trash's Deleted
    # fold restores one, or deletes one or all for good, each asked twice.
    "variant-more": (WIDGET, WHAT_YOU_SEE, "a button that unfolds what can be done to a variant"),
    "variant-to": (WIDGET, WHAT_YOU_SEE, "a box for the name a variant is renamed or copied to"),
    "variant-rename": (WIDGET, WHAT_IS_THERE, "a button that renames a saved variant"),
    "variant-duplicate": (WIDGET, WHAT_IS_THERE, "a button that copies a saved variant"),
    "variant-history": (WIDGET, WHAT_YOU_SEE, "a button that lists a variant's saves"),
    "variant-restore": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that saves a variant again as it was at an earlier save",
    ),
    "variant-compare": (
        WIDGET,
        WHAT_YOU_SEE,
        "a button that compares a variant with what is drawn",
    ),
    "variant-delete": (WIDGET, WHAT_IS_THERE, "a button that moves a variant to the trash"),
    "trash-restore": (WIDGET, WHAT_IS_THERE, "a button that brings a deleted variant back"),
    "trash-forget": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that deletes one variant for good, asked twice",
    ),
    "trash-empty": (WIDGET, WHAT_IS_THERE, "a button that empties the trash, asked twice"),
    # Two variants compared, in the part's editor: what with, how drawn, and closed.
    "compare-with": (WIDGET, WHAT_YOU_SEE, "a drop-down of what a variant is compared with"),
    "compare-mode": (WIDGET, WHAT_YOU_SEE, "a drop-down: the two overlaid, or side by side"),
    "compare-close": (WIDGET, WHAT_YOU_SEE, "a button that ends a comparison"),
    # A part's controls tied to its text: a computed value moved asks first, whether
    # its expression gives way to the plain value; and a part in a submodule's
    # upstream SCAD, read only.
    "computed-replace": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that puts a plain value in place of a computed one's expression",
    ),
    "computed-keep": (WIDGET, WHAT_YOU_SEE, "a button that leaves a computed value computed"),
    "part-upstream": (WIDGET, NOTHING, "a link that opens a part's upstream SCAD, read only"),
    # The SCAD editor (widgets/scad_editor.js):
    # the name a save keeps a variant under, Save and Fullscreen; and a saved variant
    # chosen from the list in the part's Variants window.
    "scad-name": (WIDGET, WHAT_YOU_SEE, "a box for the name a variant is saved under"),
    "scad-save": (WIDGET, WHAT_IS_THERE, "a button that saves the SCAD as a variant in git"),
    "scad-fullscreen": (
        WIDGET,
        WHAT_YOU_SEE,
        "a button that puts the SCAD editor over the whole page, or back",
    ),
    "saved-variant": (WIDGET, WHAT_YOU_SEE, "a button that draws a saved variant of a part"),
    "made-piece": (
        LIST,
        WHAT_YOU_SEE,
        "a piece made of a part, a row under the variant it was made of or among those of "
        "none: its drawer opened in Part › Feedback",
    ),
    "part-preset": (WIDGET, WHAT_YOU_SEE, "a drop-down that stages one of a part's presets"),
    "join-btn": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that keeps an end, then makes and draws the adapter between it and the end edited",
    ),
    # How much of a subassembly to draw, and whether to outline its extent.
    "detail-mode": (WIDGET, WHAT_YOU_SEE, "a drop-down for how much of each subassembly to draw"),
    "overlay-toggle": (WIDGET, WHAT_YOU_SEE, "a tick-box that outlines each subassembly's extent"),
    "detail-select": (WIDGET, WHAT_YOU_SEE, "the same drop-down, for the chosen piece only"),
    # The Device section of the chosen piece: one line, the board pinned to it
    # and what it is doing, with Open (its Machine) and the pin's take-back; or,
    # with nothing pinned, the boards it can be pinned to. Drawn afresh each
    # time the piece changes, so these are found by class rather than id.
    "dev-open": (WIDGET, WHAT_YOU_SEE, "a button that opens the pinned board's Machine"),
    # On a printer, the pin on its own board, which the printer's Pin made.
    "dev-unpin": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that unpins the board from the piece, or a printer's from its board",
    ),
    "dev-via": (WIDGET, WHAT_YOU_SEE, "a link to the piece inside that holds the board"),
    "dev-rescan": (WIDGET, WHAT_YOU_SEE, "a button that looks for boards again"),
    "dev-flash-sketch": (
        WIDGET,
        WHAT_YOU_SEE,
        "a button that opens the Bench on the piece's own sketch, which no board runs",
    ),
    "dev-manual": (WIDGET, WHAT_IS_THERE, "a box for typing a port, S/N or address to pin"),
    "dev-pin-manual": (WIDGET, WHAT_IS_THERE, "the button that pins the typed board"),
    "dev-pick": (WIDGET, WHAT_YOU_SEE, "a drop-down of boards not yet pinned"),
    "dev-query": (WIDGET, WHAT_YOU_SEE, "a button that asks the chosen board what it is"),
    "dev-pin": (WIDGET, WHAT_IS_THERE, "a button that pins the chosen board to the piece"),
    # The ring. One control, and it is the destination rather than the meter.
    "ring-open": (RING, WHAT_YOU_SEE, "the button that opens the ring"),
    # The header's Docs: the documentation and the walkthrough, in a new tab.
    "docs-link": (WIDGET, NOTHING, "a link that opens the documentation in a new tab"),
    # Made by the page as it goes, rather than written into it. Found by the
    # listening scan below, and named here so both scans agree on what exists.
    "category-chip": (LIST, WHAT_YOU_SEE, "a row of buttons, one per word, that fold and unfold"),
    "tree-caret": (LIST, WHAT_YOU_SEE, "the arrow that opens a branch of the list"),
    "contents-item": (LIST, WHAT_YOU_SEE, "a row of the list of pieces"),
    "breadcrumb": (LIST, WHAT_YOU_SEE, "the trail back to where you came from"),
    # ---- a board's Machine, apothecary/static/widgets/machine.js ------------
    # One board, close up. The header: how often to poll, and the link itself.
    "auto": (WIDGET, WHAT_YOU_SEE, "a tick-box that polls on a schedule"),
    "interval": (WIDGET, WHAT_YOU_SEE, "a drop-down for how often to poll"),
    "poll": (WIDGET, WHAT_YOU_SEE, "a button that polls the printer once"),
    "reconnect": (WIDGET, WHAT_YOU_SEE, "a button that reopens the serial link"),
    "identify": (WIDGET, WHAT_YOU_SEE, "a button that asks the board what it is"),
    "reset": (WIDGET, WHAT_IS_THERE, "a button that reboots the board"),
    "release": (WIDGET, WHAT_YOU_SEE, "a button that lets go of the port"),
    # A devkit's port is opened only when asked: Listen streams what it says
    # (opening the port may reset it), Probe asks esptool what its chip is.
    "listen": (WIDGET, WHAT_YOU_SEE, "a button that opens a devkit's port and streams it"),
    "probe": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that asks esptool what a devkit's chip is (resets it)",
    ),
    "ctl": (WIDGET, WHAT_YOU_SEE, "a tick-box that arms the control latch"),
    "estop": (WIDGET, WHAT_IS_THERE, "the emergency stop"),
    "pad-estop": (WIDGET, WHAT_IS_THERE, "the emergency stop on the popped-out control pad"),
    # The board's one log, in its Machine: a report to ask a printer for, and
    # what to show of the traffic.
    "qform": (WIDGET, WHAT_YOU_SEE, "a form for asking the printer for a report"),
    "q": (WIDGET, WHAT_YOU_SEE, "a box for the report code to ask for"),
    "qform:submit": (WIDGET, WHAT_YOU_SEE, "the button that asks for the report"),
    "show-polls": (WIDGET, WHAT_YOU_SEE, "a tick-box that shows the poll traffic"),
    "follow": (WIDGET, WHAT_YOU_SEE, "a tick-box that keeps the log scrolled to the end"),
    "clear": (WIDGET, WHAT_YOU_SEE, "a button that empties the log"),
    "download": (WIDGET, NOTHING, "a button that downloads the log"),
    # The control pad, behind the latch. The buttons carry the G-code line
    # they send rather than a name, and are named here by that line; a box
    # beside a button holds the number the line is filled in with.
    "ctl-disarm": (WIDGET, WHAT_YOU_SEE, "a button that disarms the control latch"),
    "ctl-pop": (
        WIDGET,
        WHAT_YOU_SEE,
        "a button that pops the control pad out into a loud window or puts it back",
    ),
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
    "cmd:HOME": (WIDGET, WHAT_IS_THERE, "a button that homes every axis, in the machine's dialect"),
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
    "cmd:HOME-X": (WIDGET, WHAT_IS_THERE, "a button that homes the X axis alone"),
    "cmd:HOME-Y": (WIDGET, WHAT_IS_THERE, "a button that homes the Y axis alone"),
    "cmd:HOME-Z": (WIDGET, WHAT_IS_THERE, "a button that homes the Z axis alone"),
    "cmd:M84": (WIDGET, WHAT_IS_THERE, "a button that lets the motors go"),
    "cmd:M410": (WIDGET, WHAT_IS_THERE, "a button that drops every planned move"),
    "cmd:M24": (WIDGET, WHAT_IS_THERE, "a button that starts or resumes the print on the card"),
    "cmd:M25": (WIDGET, WHAT_IS_THERE, "a button that pauses the print on the card"),
    "cmd:M524": (WIDGET, WHAT_IS_THERE, "a button that abandons the print on the card"),
    "cmd:M420 S1": (WIDGET, WHAT_IS_THERE, "a button that turns bed levelling on"),
    "cmd:M420 S0": (WIDGET, WHAT_IS_THERE, "a button that turns bed levelling off"),
    "cmd:M108": (WIDGET, WHAT_IS_THERE, "a button that breaks out of a heat-and-wait"),
    # The router's pad (apothecary/firmware/grbl.py's dialect): what a printer's has
    # no need of, beside the jog grid and feed the two share.
    "cmd:$X": (WIDGET, WHAT_IS_THERE, "a button that unlocks the controller after an alarm"),
    "cmd:G53 G0 Z0": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that lifts the tool to the top of its travel",
    ),
    "cmd:G0 X0 Y0": (WIDGET, WHAT_IS_THERE, "a button that moves the tool over the work zero"),
    "cmd:JOG-CANCEL": (WIDGET, WHAT_IS_THERE, "a button that stops a jog in flight"),
    "r-rpm": (WIDGET, WHAT_YOU_SEE, "a box for the spindle speed to set"),
    "cmd:M3 S{r-rpm}": (WIDGET, WHAT_IS_THERE, "a button that runs the spindle at that"),
    "cmd:M5": (WIDGET, WHAT_IS_THERE, "a button that turns the spindle off"),
    "cmd:G10 L20 P1 X0 Y0 Z0": (WIDGET, WHAT_IS_THERE, "a button that makes here the work zero"),
    "cmd:G10 L20 P1 Z0": (WIDGET, WHAT_IS_THERE, "a button that makes this height the work Z zero"),
    "r-probe": (WIDGET, WHAT_YOU_SEE, "a box for how far down to probe"),
    "cmd:G38.2 Z-{r-probe} F100": (WIDGET, WHAT_IS_THERE, "a button that probes down to the plate"),
    "r-plate": (
        WIDGET,
        WHAT_IS_THERE,
        "a box for the touch plate's thickness, kept as it is changed",
    ),
    "cmd:PROBE-PLATE Z{r-plate} D{r-probe} F100": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that probes down to the plate and makes the touch its thickness in the work zero",
    ),
    "needs-unlock": (
        WIDGET,
        WHAT_IS_THERE,
        "a button in the Needs you card that unlocks the controller",
    ),
    "cmd:RESUME": (WIDGET, WHAT_IS_THERE, "a button that resumes the held controller and the cut"),
    "cmd:HOLD": (WIDGET, WHAT_IS_THERE, "a button that holds the controller where it is"),
    "cmd:RESET": (WIDGET, WHAT_IS_THERE, "a button that abandons the cut with the soft reset"),
    # the bed
    "level-probe": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that homes, probes the bed (a router's table, at a grid of points) and "
        "keeps the reading",
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
    # ---- the Bench, apothecary/static/widgets/{toolchain,sketches,tasks}.js
    # The Bench's sections, written once in the modules and named by class, since
    # the form and the task log are mounted by the Bench and by a board's Flashing
    # card. The toolchain: install it, list what it knows, add to it.
    "install-btn": (WIDGET, WHAT_IS_THERE, "a button that installs or updates arduino-cli"),
    "install-force": (WIDGET, WHAT_YOU_SEE, "a tick-box that makes the install start over"),
    "lib-input": (WIDGET, WHAT_YOU_SEE, "a box for a library to install"),
    "lib-btn": (WIDGET, WHAT_IS_THERE, "a button that installs that library"),
    "core-install": (WIDGET, WHAT_IS_THERE, "a button that installs a board core"),
    # Every other toolchain module, drawn from the status beside arduino-cli, one
    # Install each.
    "module-install": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that installs a toolchain module's tools (Rust for the ESP32)",
    ),
    # The slicer's modules, drawn after the toolchain's from GET /slicer/status, each
    # with its pinned release installed by its own Install.
    "slicer-install": (WIDGET, WHAT_IS_THERE, "a button that installs the slicer (OrcaSlicer)"),
    # Sketches: pick one from a drop-down, name the board and the port, build and
    # send.
    "sketch-select": (WIDGET, WHAT_YOU_SEE, "a drop-down of the sketches under parts/"),
    "fqbn-input": (WIDGET, WHAT_YOU_SEE, "a box for the board to build for"),
    "port-select": (WIDGET, WHAT_YOU_SEE, "a drop-down of ports to upload to"),
    "compile-btn": (WIDGET, WHAT_IS_THERE, "a button that compiles the chosen sketch"),
    "upload-btn": (WIDGET, WHAT_IS_THERE, "a button that compiles and uploads it"),
    # esptool: raw images onto an Espressif chip, one offset and path a line.
    "esp-chip": (WIDGET, WHAT_YOU_SEE, "a box for the chip to flash"),
    "esp-baud": (WIDGET, WHAT_YOU_SEE, "a box for the flashing baud rate"),
    "esp-images": (
        WIDGET,
        WHAT_YOU_SEE,
        "a box for the images to flash, one offset and path a line",
    ),
    "esp-erase": (WIDGET, WHAT_YOU_SEE, "a tick-box that erases the flash first"),
    "esp-flash-btn": (WIDGET, WHAT_IS_THERE, "a button that flashes the images"),
    "cancel-btn": (WIDGET, WHAT_IS_THERE, "a button that cancels the running task"),
    # ---- Pictures, apothecary/static/widgets/picture_list.js -------------
    # Every picture under the picture root, each row chosen by a click for the
    # ring's Picture › Folder to pin (a list, not a control), a kept one with
    # Forget (TAKEN_BACK), Purge, a file picker that keeps pictures here pinned
    # nowhere, and the gathering's section: the pictures ticked, gathered into a
    # report, and what a person says about them.
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
    # What a page added or pinned, every site's, each taken back from its row
    # (TAKEN_BACK): a camera removed, a view unpinned, a board's pin taken back.
    "pinned-camera-remove": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that removes one camera, in any site",
    ),
    "pinned-view-unpin": (WIDGET, WHAT_IS_THERE, "a button that unpins one view, in any site"),
    "pinned-board-unpin": (WIDGET, WHAT_IS_THERE, "a button that takes one board's pin back"),
    # ---- Layers, apothecary/static/widgets/layers.js ----------------------
    # Tick-boxes and a stepper that set the pick scope (static/pick_scope.js), each the
    # act of a cell under View › Layers or View › Depth (RING_BACKED).
    "layers-tick": (
        WIDGET,
        WHAT_YOU_SEE,
        "a tick-box of a layer, Shown or Selectable, one in each row of the Layers window",
    ),
    "layers-depth-less": (WIDGET, WHAT_YOU_SEE, "a button that reaches one level less deep"),
    "layers-depth-more": (WIDGET, WHAT_YOU_SEE, "a button that reaches one level deeper"),
    "layers-reset-all": (
        WIDGET,
        WHAT_YOU_SEE,
        "a button that puts depth and every layer back as they began",
    ),
    # ---- Bed, apothecary/static/widgets/bed_shims.js -----------------------------------
    # A printer's bed readings and the shims that level it, in four windows: Fixes' two
    # acts, each a cell of Panels › Machine › Bed (RING_BACKED). A run chosen in Runs is a
    # row of a list, LISTENING's.
    "bed-keep": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that keeps the screw hole and the ring Parameters holds for bed_shims as "
        "the printer's mount",
    ),
    "bed-make": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that renders the shims at their thicknesses and slices them for the "
        "printer in its Print window",
    ),
    "bed-hot-c": (
        WIDGET,
        WHAT_YOU_SEE,
        "a field for the bed's temperature to probe it at, the filament's filled in",
    ),
    "bed-soak": (WIDGET, WHAT_YOU_SEE, "a field for how long the bed is held before it is probed"),
    "bed-probe-hot": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that heats the bed, holds it, probes it twice and turns it off after",
    ),
    # Fixes' Here: where the nozzle stands kept as a screw or a corner of the plate, the
    # place chosen beside it; the cell Panels › Machine › Bed › Here (RING_BACKED).
    "bed-where-what": (
        WIDGET,
        WHAT_YOU_SEE,
        "a choice of the place Here keeps: a levelling screw or a corner of the plate",
    ),
    "bed-where-here": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that keeps where the printer's nozzle stands, as its board says, as that "
        "screw or corner",
    ),
    # ---- Loops, apothecary/static/widgets/loops.js -------------------------------------
    # A heater loop of the printer whose Machine is open: its choices and its acts, each a
    # cell of Panels › Machine › Loops (RING_BACKED); the figures an experiment is planned
    # by are typed, and no cell types a value. Nothing here saves to the board's memory.
    "loops-loop": (WIDGET, WHAT_YOU_SEE, "a drop-down of the loops: hotend 0 or the bed"),
    "loops-rule": (
        WIDGET,
        WHAT_YOU_SEE,
        "a drop-down of the rules the server lists, each with the kinds of controller it gives",
    ),
    "loops-read": (WIDGET, WHAT_YOU_SEE, "a button that reads the gains the board holds (M503)"),
    "loops-set": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that sets the designed gains on the board and reads them back, not saved",
    ),
    "loops-kind": (
        WIDGET,
        WHAT_YOU_SEE,
        "a drop-down of the experiments: a step, an autotune, a perturbation",
    ),
    "loops-param": (
        WIDGET,
        WHAT_YOU_SEE,
        "a box for one figure of the experiment chosen, one for each, as the server lists them",
    ),
    "loops-ceiling": (WIDGET, WHAT_YOU_SEE, "a box for the experiment's ceiling, typed every time"),
    "loops-longest": (
        WIDGET,
        WHAT_YOU_SEE,
        "a box for the experiment's longest time, typed every time",
    ),
    "loops-start": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that starts the experiment, heating the machine",
    ),
    "loops-cancel": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that ends the experiment, the heater turned off and read back",
    ),
    # ---- Deck, apothecary/static/widgets/deck.js --------------------------
    # The Stream Deck + as drawn from here: a simulated deck is pressed, turned and
    # tapped from its window, each the event a real deck reports (a real deck's are off);
    # the piece's Open Deck opens the window.
    "deck-open": (
        WIDGET,
        WHAT_YOU_SEE,
        "a button on the Stream Deck + piece that opens the Deck window",
    ),
    # ---- Make: a part sent to a machine -----------------------------------
    "make-here": (
        WIDGET,
        WHAT_IS_THERE,
        "a button in the header that makes the piece selected, or the part in view, on its"
        " first machine: chosen there and sliced, or its toolpath written",
    ),
    "deck-key": (WIDGET, WHAT_IS_THERE, "a key of a simulated deck, pressed and released"),
    "deck-strip-tap": (WIDGET, WHAT_IS_THERE, "the touch strip of a simulated deck, tapped"),
    "deck-turn": (WIDGET, WHAT_IS_THERE, "a button that turns a simulated deck's knob one step"),
    "deck-press": (WIDGET, WHAT_IS_THERE, "a button that presses a simulated deck's knob"),
    # The knobs, the server's layout on the deck: started or stopped, the machine they
    # move and their step chosen, in the Deck window; Knobs here in a Control pad. Each
    # is a cell of Panels › Tools › Deck.
    "deck-run": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that starts or stops the deck's knobs, the layout that jogs the machines",
    ),
    "deck-machine": (WIDGET, WHAT_IS_THERE, "a machine's name, a button that the knobs move it"),
    "deck-step": (WIDGET, WHAT_YOU_SEE, "a button that makes a knob's step so many millimetres"),
    # The strip's screen, which only a swipe on the deck changed: a real deck's from here.
    "deck-screen-to": (
        WIDGET,
        WHAT_YOU_SEE,
        "a screen's name, a button that the deck's strip shows it, as a swipe along it does",
    ),
    "deck-here": (
        WIDGET,
        WHAT_IS_THERE,
        "a button in a Control pad that the deck's knobs move this machine",
    ),
    # ---- Models, apothecary/static/widgets/models.js ----------------------
    # Image models through qmcp: an origin switched, the shape chosen on a mat asked
    # about, and a person's word on one of its properties. Ask and a person's word
    # are Panels › Pictures › Models too (RING_BACKED).
    "models-switch": (
        WIDGET,
        WHAT_IS_THERE,
        "a tick-box per origin, the plain reader or a model, switching it on or off",
    ),
    "models-ask": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that asks about the shape chosen on a mat: its colour read off its "
        "pixels, and each model's guesses",
    ),
    "models-word": (
        WIDGET,
        WHAT_IS_THERE,
        "a box per property for a person's word, said with Enter, over every guess",
    ),
    # ---- Marks, apothecary/static/widgets/marks.js -------------------------
    # A whiteboard's marks sorted: the picture whose marks are listed, a mark chosen,
    # a person's word on what one is, and what a note says. A mark's kind is Panels ›
    # Pictures › Marks too (RING_BACKED), on the mark chosen here.
    "marks-view": (
        WIDGET,
        WHAT_YOU_SEE,
        "a drop-down of the pictures pinned in the site: the one whose marks are listed",
    ),
    "marks-choose": (
        WIDGET,
        WHAT_YOU_SEE,
        "a button per mark that chooses it, for the ring's Marks cells to say what it is",
    ),
    "marks-kind": (
        WIDGET,
        WHAT_IS_THERE,
        "a drop-down per mark for a person's word on what it is, over the sorter's",
    ),
    "marks-corner": (
        WIDGET,
        WHAT_IS_THERE,
        "a handle per corner of a whiteboard on its photograph, dragged or nudged with the "
        "arrow keys and set with Enter: a person's word on where the whiteboard is",
    ),
    "marks-when": (
        WIDGET,
        WHAT_YOU_SEE,
        "a slider over a whiteboard's history: the photograph of the moment it stands at "
        "drawn, with the words given by then",
    ),
    "marks-take": (
        WIDGET,
        WHAT_IS_THERE,
        "a button per change since the photograph before that taking changes a piece or "
        "carries a note's words",
    ),
    "marks-place": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that places the moment the slider stands at, with its words, at the "
        "place selected in the world",
    ),
    "marks-words": (
        WIDGET,
        WHAT_IS_THERE,
        "a box per note for what its writing says, typed and said with Enter",
    ),
    # Selected: the one width a view is sized by (a chosen shape's long side
    # when one is chosen). A number the ring cannot type; Size puts the cursor in it.
    "view-width": (WIDGET, WHAT_IS_THERE, "a box for how wide a picture is, or one shape's side"),
    # Selected's camera section: Take picture, the camera's ring's cell (RING_BACKED).
    "cam-take": (WIDGET, WHAT_IS_THERE, "a button that takes a picture with the selected camera"),
    # printing from here: a kept file, streamed
    "print-file": (WIDGET, WHAT_YOU_SEE, "a file picker that keeps a G-code file on the host"),
    "print-pick": (WIDGET, WHAT_YOU_SEE, "a drop-down of the files kept on the host"),
    "print-delete": (WIDGET, WHAT_YOU_SEE, "a button that forgets the chosen file"),
    "print-part": (
        WIDGET,
        WHAT_YOU_SEE,
        "a drop-down of the parts a print from here makes: its site's, then every part's",
    ),
    "print-slice": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that slices what makes names for the printer, and chooses its G-code",
    ),
    "print-adhesion": (
        WIDGET,
        WHAT_YOU_SEE,
        "a drop-down of how the next slice's first layer holds: the part's own, a brim, a"
        " raft, or neither",
    ),
    "print-level": (
        WIDGET,
        WHAT_YOU_SEE,
        "a drop-down of how the next slice levels the bed at its start: the part's own,"
        " probe first, or home only",
    ),
    "print-offset": (
        WIDGET,
        WHAT_IS_THERE,
        "a drop-down of the printer's first-layer offset, the nozzle lower or higher than"
        " its probe puts it, which keeps the one chosen: its next slices are made with it",
    ),
    "print-filament": (
        WIDGET,
        WHAT_IS_THERE,
        "a drop-down of the filaments the printer can load, which loads the one chosen:"
        " its next slices are made with it",
    ),
    "print-preview": (
        WIDGET,
        WHAT_YOU_SEE,
        "a slider that draws the chosen file's path in the world, through a layer or a pass",
    ),
    "print-start": (WIDGET, WHAT_IS_THERE, "a button that streams the chosen file to the printer"),
    "print-plan": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that keeps what is made and the file chosen as the machine's plan",
    ),
    "print-pause": (WIDGET, WHAT_IS_THERE, "a button that stops feeding the print from here"),
    "print-resume": (WIDGET, WHAT_IS_THERE, "a button that feeds the print from here again"),
    "print-cancel": (WIDGET, WHAT_IS_THERE, "a button that ends the print from here, heaters off"),
    # ---- Part › Feedback, apothecary/static/widgets/feedback.js ---------------
    # A part's cabinet: a drawer for each piece made of it, and what is said of a piece
    # filed there. Its acts are the cells of a part's piece's Feedback (RING_BACKED).
    "feedback-piece": (
        WIDGET,
        WHAT_YOU_SEE,
        "a drop-down of the pieces made of the part, a drawer each, the newest first, then"
        " its kept slices and toolpaths made elsewhere",
    ),
    "feedback-measure": (
        WIDGET,
        WHAT_YOU_SEE,
        "a field for what the piece a toolpath cut measures, each feature it names",
    ),
    "measure-read": (
        WIDGET,
        WHAT_YOU_SEE,
        "a field for what one feature of a printed piece reads, one in each row of its"
        " plan under measured",
    ),
    "feedback-measure-keep": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that checks what was read against what was made and files it in the"
        " piece's drawer: its printer's next turn of its tuning, or its router's allowance",
    ),
    "seen-read": (
        WIDGET,
        WHAT_YOU_SEE,
        "a drop-down of how badly one fault shows on a printed piece, none to bad, one for"
        " each fault under seen",
    ),
    "feedback-seen-keep": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that files what the piece shows in its drawer as its printer's next look,"
        " which moves one setting",
    ),
    "feedback-note": (WIDGET, WHAT_YOU_SEE, "a field for a note on the piece"),
    "feedback-note-keep": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that files the note in the piece's drawer",
    ),
    "feedback-tune-apply": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that takes the last turn of the tuning of the printer that made the piece"
        " into its next slices",
    ),
    "feedback-tune-undo": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that drops the last turn of that printer's tuning, and what it applied",
    ),
    "feedback-try-probe": (
        WIDGET,
        WHAT_IS_THERE,
        "a button on a print that stopped that slices the piece again, its printer's"
        " levelling probe first",
    ),
    "feedback-try-brim": (
        WIDGET,
        WHAT_IS_THERE,
        "a button on a print that stopped that slices the piece again with a brim",
    ),
    "feedback-try-raft": (
        WIDGET,
        WHAT_IS_THERE,
        "a button on a print that stopped that slices the piece again on a raft",
    ),
    # ---- Procedure, apothecary/static/widgets/procedure.js -------------------
    # A site's procedures. GO and Start over are Site › Procedure too (RING_BACKED).
    "procedure-choice": (WIDGET, WHAT_YOU_SEE, "a drop-down of the site's procedures"),
    "procedure-go": (
        WIDGET,
        WHAT_IS_THERE,
        "a button on the step standing by, firing it through the family's hub",
    ),
    "procedure-again": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that starts a procedure over, what came before staying in the log",
    ),
    "procedure-node": (
        WIDGET,
        WHAT_YOU_SEE,
        "a step's node, a button that opens the window its work is in: a Machine, or Pictures",
    ),
    # ---- Family, apothecary/static/widgets/family.js -------------------------
    "family-member": (
        WIDGET,
        WHAT_YOU_SEE,
        "a member's name, a button that opens the window of the node its next step names, "
        "or its own page beside the hub",
    ),
    # ---- Settings, apothecary/static/widgets/settings.js -------------------
    # Every shortcut and navigation setting: one row each, its default shown and a
    # reset beside it, and Reset all. They change how the page takes a press, not
    # what is there, and none is ring-backed: the panel has a cell (View ›
    # Settings), not each row one.
    "setting-key": (
        WIDGET,
        WHAT_YOU_SEE,
        "a field that takes the next key pressed as a shortcut: the ring's, a step in or out",
    ),
    "setting-choice": (
        WIDGET,
        WHAT_YOU_SEE,
        "a drop-down of the modifier a right-click opens the ring with",
    ),
    "setting-tick": (
        WIDGET,
        WHAT_YOU_SEE,
        "a tick-box that turns automatic zoom, or one way of it, on or off",
    ),
    "setting-number": (
        WIDGET,
        WHAT_YOU_SEE,
        "a box for automatic zoom's resistance, or how near or far the camera may dolly",
    ),
    "setting-reset": (WIDGET, WHAT_YOU_SEE, "a button that puts one setting back to its default"),
    "settings-reset-all": (
        WIDGET,
        WHAT_YOU_SEE,
        "a button that puts every setting back to its default",
    ),
    # ---- the Airgap, apothecary/static/widgets/airgap.js ------------------------
    # The airgap part as a field, torque and dynamics model. Its geometry is the
    # part's text (the SCAD editor's while the part is edited), so the panel has no
    # geometry controls of its own: a preset, the scrub, the rig as one document, the
    # sweep as one line, and the verbs, each a cell of Panels › Airgap.
    "airgap-preset": (
        WIDGET,
        WHAT_YOU_SEE,
        "a drop-down of arrangements to start from, written into the editor's text",
    ),
    "airgap-to-editor": (
        WIDGET,
        WHAT_YOU_SEE,
        "a button that writes the panel's values into the airgap part's text",
    ),
    "airgap-from-editor": (WIDGET, WHAT_YOU_SEE, "a button that reads the part's text again"),
    "airgap-copy-scad": (
        WIDGET,
        WHAT_YOU_SEE,
        "a button that copies the part's text with the panel's values written in",
    ),
    "airgap-copy-metrics": (WIDGET, WHAT_YOU_SEE, "a button that copies the metrics document"),
    "airgap-reset": (WIDGET, WHAT_YOU_SEE, "a button that puts the panel back on the part's text"),
    "airgap-play": (
        WIDGET,
        WHAT_YOU_SEE,
        "a button that spins the rotor, or plays the run, and pauses",
    ),
    "airgap-phi": (WIDGET, WHAT_YOU_SEE, "a slider for the rotor angle, or time through the run"),
    "airgap-rig": (
        WIDGET,
        WHAT_YOU_SEE,
        "a box holding the rig -- excitation, drive, load, bearing, mount, actuation, "
        "playback -- as JSON",
    ),
    "airgap-sweep": (
        WIDGET,
        WHAT_YOU_SEE,
        "a line naming two ranges and the metric to map over them",
    ),
    "airgap-run": (WIDGET, WHAT_YOU_SEE, "a button that maps the metric the sweep line names"),
    # ---- Motion, apothecary/static/widgets/motion.js ------------------------------
    # A part's pieces moved through its motion, from the table the server samples. Each
    # control is a cell of the part's ring, Part › View › Motion; the slider is Back and
    # Step, a sample at a time, as the Marks history's slider is Earlier and Later.
    "motion-at": (
        WIDGET,
        WHAT_YOU_SEE,
        "a slider over the motion's parameter, the pieces moved to it",
    ),
    "motion-play": (WIDGET, WHAT_YOU_SEE, "a button that plays the motion, and pauses it"),
    "motion-back": (WIDGET, WHAT_YOU_SEE, "a button that moves the pieces to the sample before"),
    "motion-step": (WIDGET, WHAT_YOU_SEE, "a button that moves the pieces to the sample after"),
    "motion-reset": (WIDGET, WHAT_YOU_SEE, "a button that puts the motion back at its start"),
    "motion-bought": (
        WIDGET,
        WHAT_YOU_SEE,
        "a tick-box that draws what is bought -- pins, inserts -- in a colour of its own",
    ),
    # ---- the Badge, apothecary/static/widgets/badge.js ----------------------------
    # A badge composed through its part's editor: a face or the word, each a cell of its
    # ring's Part › View › Badge, and made on a machine as ⚒ Make makes a part. Its word,
    # font and size are the Parameters window's own controls.
    "badge-face": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that stages a face of the badge, or the word, and draws it",
    ),
    "badge-make": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that makes the badge drawn on the first printer or router that makes it:"
        " chosen there and sliced, or its toolpath written",
    ),
    # ---- the Tour, apothecary/static/widgets/tour_popover.js -------------------
    # The journeys a stage at a time, in a box over the page: a journey chosen, Back and
    # Next, the page taken to a stage, and a person's word on the stage (Off with what
    # its field says), under the name its other field holds. The header's Tour opens
    # it. All but the journeys' drop-down and the field for what is off are cells of
    # Panels › Windows › Tour; its ✕ is that ring's Tour, which closes it too.
    "tour-pop-open": (
        WIDGET,
        WHAT_YOU_SEE,
        "a button that opens the tour's box, or closes it and leaves its journey",
    ),
    "tour-pop-close": (
        WIDGET,
        WHAT_YOU_SEE,
        "a button that closes the tour's box and leaves its journey",
    ),
    "tour-pop-journeys": (
        WIDGET,
        WHAT_YOU_SEE,
        "a drop-down of the journeys, each with its stages",
    ),
    "tour-pop-note": (WIDGET, WHAT_YOU_SEE, "a field for what is off at the stage shown"),
    "tour-pop-by": (WIDGET, WHAT_YOU_SEE, "a field for the name a word is kept under"),
    "tour-pop-back": (WIDGET, WHAT_YOU_SEE, "a button that goes to the stage before"),
    "tour-pop-put": (WIDGET, WHAT_YOU_SEE, "a button that takes the page to the stage shown"),
    "tour-pop-works": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that says the stage does what it says, kept on the server",
    ),
    "tour-pop-off": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that says the stage is off, with what the field says, kept on the server",
    ),
    "tour-pop-next": (WIDGET, WHAT_YOU_SEE, "a button that goes to the next stage"),
    "tour-pop-page": (
        WIDGET,
        WHAT_YOU_SEE,
        "a link to the first walkthrough page the stage names",
    ),
    # ---- the Workspace, apothecary/static/widgets/working_space.js ---------
    # Its first line's buttons take the step it names; a printer's hour has a row
    # per camera, a camera's device chosen there, and its frames' budget set.
    "ws-back": (WIDGET, WHAT_YOU_SEE, "a button that goes back from a printer's hour to the site"),
    "ws-hour": (WIDGET, WHAT_YOU_SEE, "a button that opens a printer's hour"),
    "ws-add-camera": (WIDGET, WHAT_IS_THERE, "a button that adds a camera above the printer"),
    "ws-keep": (
        WIDGET,
        WHAT_IS_THERE,
        "a button that keeps a frame from each of the printer's cameras with its last poll",
    ),
    "ws-choose": (
        WIDGET,
        WHAT_IS_THERE,
        "a drop-down saying which of this browser's cameras it is",
    ),
    "ws-permit": (WIDGET, WHAT_YOU_SEE, "a button that asks the browser for its cameras"),
    "ws-gb": (WIDGET, WHAT_YOU_SEE, "a number box for a printer's frame budget, in gigabytes"),
    "ws-budget-set": (WIDGET, WHAT_IS_THERE, "a button that sets a printer's frame budget"),
    "ws-close": (WIDGET, WHAT_YOU_SEE, "a button that closes the evidence opened"),
}

# A control of its own that does the same thing as a cell of the ring, and the
# action that cell carries. Keyed by the control's name, or by a listening
# key, since a button and the place the page listens to it are the same way
# in. Every action here must be one the rings produce; a test holds it to
# `apothecary.menu`'s vocabulary, so a control cannot claim a backing that
# does not exist.
RING_BACKED: Dict[str, str] = {
    # the header's Docs is the canvas ring's Panels › Tools › Docs
    "docs-link": "panel:docs",
    # The Tour's box and its buttons are the cells of Panels › Windows › Tour
    "tour-pop-open": "tour:toggle",
    "tour-pop-close": "tour:toggle",
    "tour-pop-back": "tour:back",
    "tour-pop-put": "tour:put",
    "tour-pop-works": "tour:works",
    "tour-pop-off": "tour:off",
    "tour-pop-next": "tour:next",
    "tour-pop-page": "tour:page",
    "tour-pop-by": "tour:by",
    # Models' Ask and a person's word are the cells of Panels › Pictures › Models
    "models-ask": "models:ask",
    "models:click:closest": "models:ask",
    "models-word": "models:say:colour:red",
    # A mark's kind is a cell of Panels › Pictures › Marks, on the mark chosen there
    "marks-kind": "marks:say:diagram",
    "marks:change:closest": "marks:say:diagram",
    # The history's slider is Earlier and Later, and Place is Place, under Marks
    "marks-when": "marks:later",
    "marks:input:closest": "marks:later",
    "marks-place": "marks:place",
    "models:keydown:closest": "models:say:colour:red",
    # GO and Start over are the cells of Panels › Family › Procedure; a step's node opens
    # the window its ring's Device › Open does
    "procedure-go": "procedure:go",
    "procedure-again": "procedure:again",
    "procedure-node": "device:open",
    "procedure:click:closest": "procedure:go",
    # the Airgap's verbs are the cells of Panels › Airgap
    "airgap-play": "airgap:play",
    "playEl:click:setPlaying": "airgap:play",
    "airgap-run": "airgap:sweep",
    "runEl:click:act": "airgap:sweep",
    "airgap-to-editor": "airgap:to-editor",
    "toEditorEl:click:act": "airgap:to-editor",
    "airgap-from-editor": "airgap:from-editor",
    "fromEditorEl:click:act": "airgap:from-editor",
    "airgap-copy-scad": "airgap:copy-scad",
    "copyScadEl:click:act": "airgap:copy-scad",
    "airgap-copy-metrics": "airgap:copy-metrics",
    "copyMetricsEl:click:act": "airgap:copy-metrics",
    "airgap-reset": "airgap:reset",
    "resetEl:click:act": "airgap:reset",
    # Motion's controls are the cells of Part › View › Motion; its one listener of each
    # kind serves them all
    "motion-at": "part:motion:step",
    "motion-play": "part:motion:play",
    "motion-back": "part:motion:back",
    "motion-step": "part:motion:step",
    "motion-reset": "part:motion:reset",
    "motion-bought": "part:motion:bought",
    # A face or the word is its cell of Part › View › Badge; ⚒ Print and ⚒ Cut do what a
    # part's Slice and Toolpath cells do on the first machine of their kind that makes it,
    # as ⚒ Make does across sites.
    "badge-face": "part:badge:face:smile",
    "badge-make": "slice:piece:printer_1",
    "badgeEl:click:clicked": "part:badge:face:smile",
    "motionEl:click:clicked": "part:motion:play",
    "motionEl:input:scrubbed": "part:motion:step",
    "motionEl:change:ticked": "part:motion:bought",
    # the viewer's Device section: Open is Device › Open, the board's Machine
    "dev-open": "device:open",
    "dev-query": "device:query",
    "dev-pin": "device:pin",
    "dev-pin-manual": "device:pin",
    "dev-unpin": "device:unpin",
    "dev-rescan": "device:rescan",
    "dev-flash-sketch": "device:flash-sketch",
    "devOpen:click:openMachine": "device:open",
    "devQuery:click:queryPort": "device:query",
    "devPin:click:setNodeDevice": "device:pin",
    "devPinManual:click:pinManual": "device:pin",
    "manualIn:keydown:pinManual": "device:pin",
    "devUnpin:click:setNodeDevice": "device:unpin",
    "devRescan:click:rescanDevices": "device:rescan",
    "devFlashSketch:click:flashSketchOf": "device:flash-sketch",
    # a board's Machine: its header and control overlay
    "poll": "device:poll",
    "identify": "device:query",
    "ctl": "control:arm",
    "ctl-disarm": "control:disarm",
    "ctl-pop": "panel:pad",
    "estop": "control:estop",
    "pad-estop": "control:estop",
    "cmd:M104 S{h-hot}": "control:hotend-on",
    "cmd:M104 S0": "control:hotend-off",
    "cmd:M140 S{h-bed}": "control:bed-on",
    "cmd:M140 S0": "control:bed-off",
    "cmd:M106 S{h-fan}": "control:fan-on",
    "cmd:M107": "control:fan-off",
    "cmd:HOME": "control:home",
    "cmd:HOME-X": "control:home-x",
    "cmd:HOME-Y": "control:home-y",
    "cmd:HOME-Z": "control:home-z",
    "cmd:G28 X Y": "control:home-xy",
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
    # the router's pad: the cells of a router's Control ring
    "cmd:$X": "control:unlock",
    "cmd:G53 G0 Z0": "control:top-z",
    "cmd:G0 X0 Y0": "control:go-zero",
    "cmd:JOG-CANCEL": "control:jog-cancel",
    "cmd:M3 S{r-rpm}": "control:spindle-on",
    "cmd:M5": "control:spindle-off",
    "cmd:G10 L20 P1 X0 Y0 Z0": "control:zero-xyz",
    "cmd:G10 L20 P1 Z0": "control:zero-z",
    "cmd:G38.2 Z-{r-probe} F100": "control:probe-z",
    "cmd:PROBE-PLATE Z{r-plate} D{r-probe} F100": "control:probe-plate",
    "needs-unlock": "control:unlock",
    "cmd:RESUME": "control:job-resume",
    "cmd:HOLD": "control:job-hold",
    "cmd:RESET": "control:job-abort",
    "level-probe": "level:probe",
    "level-read": "level:read",
    "corner:FL": "control:corner:FL",
    "corner:FR": "control:corner:FR",
    "corner:BL": "control:corner:BL",
    "corner:BR": "control:corner:BR",
    # The Bench's buttons are the cells of the canvas ring's Panels › Tools › Bench, each
    # acting on what the Bench has chosen; a core's Install is Bench › Cores › its
    # core. The form's boxes and drop-downs, the force tick-box and raw flash's
    # boxes choose what a cell acts on, and no cell chooses them.
    "install-btn": "bench:install:arduino",
    "module-install": "bench:install:rust-esp32",
    "modulesEl:click:closest": "bench:install:rust-esp32",
    # The slicer's Install is Bench › Install's cell for it, after the toolchain's.
    "slicer-install": "bench:install:slicer:orcaslicer",
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
    "print-preview": "print:preview",
    # Keep as plan keeps the machine's plan, its board connected or not.
    "print-plan": "print:plan",
    # The levelling of the next slice: the Print cell's Levelling steps it.
    "print-level": "print:level",
    # Its first layer's hold: the Print cell's Adhesion steps it.
    "print-adhesion": "print:adhesion",
    # The printer's first-layer offset: the Print cell's First layer steps it and keeps it.
    "print-offset": "print:offset",
    # A part's piece's Feedback › Measure files what is typed under measured, as Keep does,
    # and takes a person to the field when nothing is typed; a fault chosen under seen and
    # nothing read, it files the look, as Keep look does. Note files the note, or takes a
    # person to its field; Take turn and Undo turn are the buttons'.
    "feedback-measure": "feedback:measure",
    "measure-read": "feedback:measure",
    "feedback-measure-keep": "feedback:measure",
    "seen-read": "feedback:measure",
    "feedback-seen-keep": "feedback:measure",
    "feedback-note": "feedback:note",
    "feedback-note-keep": "feedback:note",
    "feedback-tune-apply": "feedback:tune-apply",
    "feedback-tune-undo": "feedback:tune-undo",
    # A print that stopped, tried again: Feedback › Try again's cells.
    "feedback-try-probe": "feedback:try-probe",
    "feedback-try-brim": "feedback:try-brim",
    "feedback-try-raft": "feedback:try-raft",
    "feedback-note:keydown:keepNote": "feedback:note",
    "feedback-measure-plan:keydown:keepOnEnter": "feedback:measure",
    # Slice slices what makes names, as the Slice cell of a made piece's ring or a
    # part's slices that piece or part, chosen under makes first.
    "print-slice": "slice:piece:printer_1",
    # ⚒ Make does what a part's Slice or Toolpath cell does -- the machine's Machine
    # opened, the part chosen under makes, sliced or its toolpath written -- on the
    # first machine that makes it, which may stand in another site or have no board.
    "make-here": "slice:piece:printer_1",
    "print-pause": "control:sd-pause",
    "print-resume": "control:sd-resume",
    "print-cancel": "control:sd-abort",
    # Navigation: the list rows and the go-in button are what the canvas ring's
    # Pieces and the node ring's Zoom in do; the trail's crumb one level up is Up.
    "zoom-in-btn": "zoom-in",
    "li:click:selectChild": "select:printer_1",
    "badge:click:selectPath": "select:printer_1",
    "crumb:click:goUpTo": "zoom-out",
    "zoomInLink:click:stepIn": "zoom-in",
    # The header's View menu: each of its items a cell of the canvas ring's
    # View (a Detail value is View › Detail › that value).
    "snap-toggle": "view:snap",
    "detail-mode": "view:detail:full",
    "overlay-toggle": "view:outlines",
    "walls-toggle": "view:walls",
    # ⚙ View › Settings is the canvas ring's View › Settings: the Settings panel shown.
    "settings-open": "view:settings",
    "settingsOpenBtn:click:openSettings": "view:settings",
    "snapToggle:change:setTranslationSnap": "view:snap",
    "detailModeEl:change:clear": "view:detail:full",
    "overlayToggle:change:renderFocus": "view:outlines",
    "wallsToggle:change:setWallsSelectable": "view:walls",
    "reconnect": "device:reconnect",
    "reset": "device:reset",
    "release": "device:release",
    "listen": "device:listen",
    "probe": "device:probe",
    "ctl:change:arm": "control:arm",
    # the part editor's Defaults, Apply and Revert are Part's on its ring
    "defaults-btn": "part:defaults",
    "apply-btn": "part:apply",
    "revert-btn": "part:revert",
    # the SCAD editor's Save and Fullscreen, and a saved variant chosen, are too
    "scad-save": "part:save",
    "scad-fullscreen": "part:fullscreen",
    "saved-variant": "part:variant:draw",
    # a part's presets, Part › Presets' cells; ⇄ Adapter, Part › Adapter
    "part-preset": "part:preset",
    "join-btn": "part:adapter",
    # and so is what can be done to a saved variant, each a cell of Part › Variants ›
    # its name, and the trash's, of Part › Variants › Deleted
    "variant-rename": "part:variant:rename",
    "variant-duplicate": "part:variant:duplicate",
    "variant-history": "part:variant:history",
    "variant-compare": "part:variant:compare",
    "variant-delete": "part:variant:delete",
    "trash-restore": "part:trash:restore",
    "trash-forget": "part:trash:forget",
    "trash-empty": "part:trash:empty",
    # the staged numbers' Undo and Redo, by button or key, are Part › History's; the
    # ghost is Part › View › Ghost, and f is Part › View › Fit
    "undo-btn": "part:undo",
    "redo-btn": "part:redo",
    "ghost-toggle": "part:ghost",
    "window:keydown:onUndoKey": "part:undo",
    "window:keydown:onFitKey": "part:fit",
    "window:keydown:onSaveKey": "part:save",
    # a camera in Selected: Take picture is its ring's, and so is P
    "cam-take": "camera:take-picture",
    "takeBtn:click:takePictureWith": "camera:take-picture",
    "window:keydown:onPictureKey": "camera:take-picture",
    # the Workspace: ‹ back is Panels › Site › Workspace, a printer's hour its
    # Camera › Workspace, Add a camera its Camera › Add here, and a camera row's
    # device and Allow the camera's own Device (whose leaves are camera:device:<id>)
    "ws-back": "panel:toggle:working",
    "deck-open": "panel:toggle:deck",
    # the knobs' controls are the cells of Panels › Tools › Deck (whose machines,
    # steps and screens are leaves deck:machine:<name>, deck:step:<mm> and
    # deck:screen:<name>)
    "deck-run": "deck:knobs",
    "deck-machine": "deck:machine",
    "deck-step": "deck:step",
    "deck-screen-to": "deck:screen",
    "deck-here": "deck:here",
    # The Layers window's controls are the cells of View › Layers and View › Depth: a
    # layer's Shown or Selectable tick its ring's Shown or Selectable (each layer has
    # its own; the grid's is in every site's), the stepper One less and One more, Reset
    # Reset.
    "layers-tick": "layer:shown:grid",
    "root:change:onChange": "layer:shown:grid",
    "layers-depth-less": "view:depth:less",
    "layers-depth-more": "view:depth:more",
    "layers-reset-all": "layer:reset",
    "root:click:onClick": "view:depth:more",
    # The Loops window's choices and acts are the cells of Panels › Machine › Loops: a loop
    # its Loop's cell, a rule and a kind of controller its Rule's (each rule a ring of the
    # kinds it gives), an experiment its Experiment's, and Read, Start, Cancel and Set on
    # machine their own. Its typed figures are values no cell types.
    "loops-loop": "loops:loop:hotend",
    "loops-rule": "loops:rule:simc:pi",
    "loops-kind": "loops:kind:step",
    "loops-read": "loops:read",
    "loops-start": "loops:start",
    "loops-cancel": "loops:cancel",
    "loops-set": "loops:set",
    "root:click:onLoopsClick": "loops:start",
    "root:change:onLoopsChange": "loops:loop:hotend",
    # Fixes' Keep and Make these are the cells of Panels › Machine › Bed.
    "bed-keep": "bed:keep",
    "bed-make": "bed:make",
    # Runs' Probe hot: the cell Panels › Machine › Bed › Probe hot, its fields the ones it reads.
    "bed-probe-hot": "bed:probe-hot",
    "bed-hot-c": "bed:probe-hot",
    "bed-soak": "bed:probe-hot",
    # Fixes' Here: the cell Panels › Machine › Bed › Here, the place it keeps the one chosen.
    "bed-where-here": "bed:where",
    "bed-where-what": "bed:where",
    "fixes:click:onFixesClick": "bed:make",
    "ws-hour": "working:open",
    "ws-add-camera": "camera:add-here",
    "ws-choose": "camera:device",
    "ws-permit": "camera:allow",
}

# A control kept on purpose beside the ring: the button on a row of Site's
# Pinned or of Pictures that takes back what the row names -- a camera removed, a
# view unpinned, a board's pin taken back, a kept picture forgotten -- in whichever
# site it stands. §6 of the draft record *Personal data stays on the device* asks
# that what a page placed or pinned be listed by the same page, every site's,
# and taken back the same way, and a ring cell reaches another site's pin only
# from that site. So these are a lasting exception, the one the pictures plan
# asks the *rad host integration* record's §5 to name, and are **not**
# ring-backed: the meter counts them, and never expects them to go. Keyed like
# RING_BACKED, by the control's name or its listening key; the value is what the
# row takes back.
TAKEN_BACK: Dict[str, str] = {
    "pinned-camera-remove": "a camera, every site's",
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
)


# ==========================================================================
# Places the page listens
# ==========================================================================

# What it listens on, what it listens for, and the first thing it then does.
# The third part is load-bearing: without it two buttons in the same row of a
# list are one entry, and a new control can be added to that row unnoticed.
LISTENING: Dict[str, Tuple[str, str, str]] = {
    # A drag along a simulated deck's strip is the swipe a real deck reports: the layout
    # changes the screen the strip shows (knobs, Progress, Status).
    "strip:pointerdown:startSwipe": (
        GESTURE,
        NOTHING,
        "pressing the Deck window's strip: where a swipe along it would begin",
    ),
    "strip:pointerup:endSwipe": (
        GESTURE,
        WHAT_YOU_SEE,
        "a drag along the Deck window's strip, a swipe: the deck's strip shows the next screen",
    ),
    # Make, the header's button
    "makeHereEl:click:makeNow": (
        WIDGET,
        WHAT_IS_THERE,
        "⚒ Make makes the piece selected, or the part in view, on its first machine",
    ),
    # the Machine: what its state asks of a person, and the touch plate
    "r-plate:change:keepPlate": (
        WIDGET,
        WHAT_IS_THERE,
        "changing the plate's thickness keeps it for the machine's board",
    ),
    # the Print window's first layer row, left without a choice: drawn again as kept
    "print-offset:blur:renderOffset": (
        AUTOMATIC,
        WHAT_YOU_SEE,
        "leaving the first layer drop-down draws it again as the offset kept",
    ),
    "c-needs:click:closest": (
        WIDGET,
        WHAT_IS_THERE,
        "the Needs you card's Unlock, sent as the pad's own",
    ),
    # taking hold of the thing itself
    "transformControls:dragging-changed:noteDragStart": (
        DRAG,
        WHAT_YOU_SEE,
        "taking hold notes where the piece was, for Escape, and stops the view turning under you",
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
    # A selected camera's turn ring and tilt arc: its press heard ahead of the
    # move arrows and the orbit, the camera aimed as the pointer goes, and its aim
    # kept on letting go.
    "canvas:pointerdown:onCameraHandleDown": (
        DRAG,
        WHAT_YOU_SEE,
        "taking hold of a camera's turn ring or tilt arc stops the view from turning under you",
    ),
    "canvas:pointermove:onCameraDragMove": (
        DRAG,
        WHAT_YOU_SEE,
        "dragging a camera's turn ring or tilt arc aims it, its pyramid following",
    ),
    "canvas:pointerup:onCameraDragEnd": (DRAG, WHAT_IS_THERE, "letting go keeps the camera's aim"),
    # controls of its own
    "siteMenuBody:click:closest": (
        WIDGET,
        WHAT_YOU_SEE,
        "choosing a site under the site crumb's ▾, which loads it and puts it in the address",
    ),
    # The site crumb's ▾: listed afresh as it opens, the site in view focused; the
    # arrows move along the sites.
    "siteMenuEl:toggle:fillSiteMenu": (
        AUTOMATIC,
        NOTHING,
        "the site crumb's ▾ opened: the sites listed afresh, the one in view focused",
    ),
    "siteMenuBody:keydown:stepFocus": (
        GESTURE,
        NOTHING,
        "the arrows, Home and End moving along the sites under the site crumb's ▾",
    ),
    "snapToggle:change:setTranslationSnap": (WIDGET, WHAT_YOU_SEE, "the snapping tick-box"),
    "wallsToggle:change:setWallsSelectable": (
        WIDGET,
        WHAT_YOU_SEE,
        "the tick-box that lets a click pick walls, for the session",
    ),
    "settingsOpenBtn:click:openSettings": (
        WIDGET,
        WHAT_YOU_SEE,
        "⚙ View › Settings, showing the Settings panel with its tab in front",
    ),
    # The View menu folds away when a press lands anywhere else, as a menu does.
    "document:pointerdown:foldViewMenu": (
        WIDGET,
        WHAT_YOU_SEE,
        "a press outside the View menu, folding it away",
    ),
    "posAxis:change:recomputeWorldBounds": (WIDGET, WHAT_IS_THERE, "typing a position"),
    "statusSelect:change:submitStatus": (WIDGET, WHAT_IS_THERE, "choosing a state"),
    "zoomInLink:click:stepIn": (WIDGET, WHAT_YOU_SEE, "the step-in button on the chosen piece"),
    # done to the scene itself
    "canvas:dblclick:onDoubleClick": (GESTURE, WHAT_YOU_SEE, "double-tapping to step in"),
    "canvas:wheel:onWheel": (GESTURE, WHAT_YOU_SEE, "the wheel, with a counter of its own"),
    # The pointer in the world: a still left click selects, or clears the selection
    # on empty space; a still right click re-centres; a drag is the view's. Held with
    # Settings' modifier, the right button is the ring's, counted with the ring. A
    # badge passes the right button to what it stands for.
    "canvas:pointerdown:onPress": (
        GESTURE,
        WHAT_YOU_SEE,
        "a press on the world, kept to tell a still click from a turn or a pan",
    ),
    "canvas:pointermove:onTravel": (
        GESTURE,
        NOTHING,
        "how far a press has travelled, so one that wandered and came back is no click",
    ),
    "canvas:pointermove:onHoverName": (
        AUTOMATIC,
        NOTHING,
        "the pointer's nearest piece named in a small badge at the universe's own level, selecting nothing",
    ),
    "canvas:pointerleave:invalidate": (
        AUTOMATIC,
        NOTHING,
        "the pointer leaving the world, so the name it showed goes",
    ),
    "canvas:pointerup:onRelease": (
        GESTURE,
        WHAT_YOU_SEE,
        "a still click: a piece selected, the selection let go, or the view re-centred",
    ),
    "layer:pointerdown:onPress": (
        GESTURE,
        WHAT_YOU_SEE,
        "a press on a badge, kept to tell a still right click on it",
    ),
    "layer:pointerup:onRelease": (
        GESTURE,
        WHAT_YOU_SEE,
        "a still right click on a badge, re-centring the view on what it stands for",
    ),
    "document:keydown:noteTab": (
        AUTOMATIC,
        NOTHING,
        "Tab pressed, which can bring the focus to the world: its ring shows again",
    ),
    "document:pointerdown:notePress": (
        AUTOMATIC,
        NOTHING,
        "where the last press landed, so Page Up and Page Down are the world's after one there",
    ),
    "window:keydown:onZoomKey": (
        GESTURE,
        WHAT_YOU_SEE,
        "keys (Page Down and Page Up while the world has the keys, Backspace) that step in and out",
    ),
    # A Machine's button that is a ring verb's, pressed: the sections that verb acts
    # on opened, as the ring's cell opens them (apothecary/systems.py's verbs).
    "btn:click:onVerb": (
        AUTOMATIC,
        NOTHING,
        "a Machine's button pressed: the windows its ring verb acts on opened",
    ),
    # The header's ⊞ Windows: listed afresh as it opens, every window by its group,
    # the first focused; the arrows move along them.
    "windowsMenuEl:toggle:fillMenu": (
        AUTOMATIC,
        NOTHING,
        "⊞ Windows opened: its windows listed afresh, the first focused",
    ),
    "windowsBody:keydown:stepFocus": (
        GESTURE,
        NOTHING,
        "the arrows, Home and End moving along ⊞ Windows' list",
    ),
    # The header's ⚙ View: its views listed afresh as it opens, each saying whether
    # it can be laid out now, the first focused; the arrows move along them.
    "viewMenuEl:toggle:fillViews": (
        AUTOMATIC,
        NOTHING,
        "⚙ View opened: its views listed afresh, the first focused",
    ),
    "viewsBody:keydown:stepFocus": (
        GESTURE,
        NOTHING,
        "the arrows, Home and End moving along ⚙ View's views",
    ),
    "window:keydown:onEscapeKey": (
        GESTURE,
        WHAT_YOU_SEE,
        "Escape: the View menu folded, a drag put back unsaved, then the selection let go",
    ),
    "window:keydown:onSaveKey": (
        GESTURE,
        WHAT_IS_THERE,
        "Ctrl+S, while a part's editor is open: its variant saved, from anywhere on the page",
    ),
    "window:keydown:onHintKey": (GESTURE, WHAT_YOU_SEE, "a key (?) that brings the hint bar back"),
    "window:keydown:onSeeThroughKey": (
        GESTURE,
        WHAT_YOU_SEE,
        "a key (o, as Settings has it) that makes the windows see-through, or solid again",
    ),
    "window:keydown:onFitKey": (
        GESTURE,
        WHAT_YOU_SEE,
        "keys (f, Shift+F) that frame the selected piece, else the level, and the level",
    ),
    "window:keydown:onUndoKey": (
        GESTURE,
        WHAT_YOU_SEE,
        "keys (Ctrl+Z, Ctrl+Shift+Z) that undo and redo the staged numbers",
    ),
    # A part's recent applies in its editor, one clicked drawn again from the cache.
    "historyList:click:closest": (
        LIST,
        WHAT_YOU_SEE,
        "a recent apply's row in a part's editor, drawing it again from the cache",
    ),
    # the trails, trees and rows beside the scene
    "chip:click:chooseFacet": (
        LIST,
        WHAT_YOU_SEE,
        "a System's, a Kind's or a word's button that opens and closes its pieces, "
        "or opens a Kind's ring in the universe",
    ),
    "caret:click:delete": (LIST, WHAT_YOU_SEE, "an arrow that opens a branch"),
    "li:click:selectChild": (LIST, WHAT_YOU_SEE, "picking a piece from the list"),
    # A board's badge, at the board in the world (anchors.js, machine_marks.js).
    "badge:click:selectPath": (
        LIST,
        WHAT_YOU_SEE,
        "picking the machine a board's badge stands for, and opening its Machine",
    ),
    # A place badge: a host's camera and view, or the floor's (picture_marks.js).
    "badge:click:onSelect": (
        LIST,
        WHAT_YOU_SEE,
        "picking the place a badge stands at: a structure, or the floor",
    ),
    # A note's badge, where its writing is on a whiteboard's picture (picture_marks.js).
    "badge:click:onNote": (
        LIST,
        WHAT_YOU_SEE,
        "opening the note a badge stands at in Marks, its box in front to type what it says",
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
    # A camera in Selected: Take picture, by its button or by P, and its pictures,
    # one clicked drawn where it landed.
    "takeBtn:click:takePictureWith": (
        WIDGET,
        WHAT_IS_THERE,
        "the selected camera's Take picture: a frame kept, lying where it looks",
    ),
    "window:keydown:onPictureKey": (
        GESTURE,
        WHAT_IS_THERE,
        "a key (P) that takes a picture with the selected camera",
    ),
    "thumbList:click:closest": (
        LIST,
        WHAT_YOU_SEE,
        "a camera's picture in Selected, drawn where it landed",
    ),
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
    "print-preview:input:previewOn": (
        WIDGET,
        WHAT_YOU_SEE,
        "the Cut or Print card's preview slider, drawing a file's toolpath in the world",
    ),
    "procedure:click:closest": (
        WIDGET,
        WHAT_IS_THERE,
        "GO or Start over, or a step's node",
    ),
    "procedure:change:closest": (WIDGET, WHAT_YOU_SEE, "the procedure chosen"),
    "members:click:closest": (
        WIDGET,
        WHAT_YOU_SEE,
        "a member's name in Members, opening the window of its next step's node or its page",
    ),
    "models:click:closest": (WIDGET, WHAT_IS_THERE, "Ask, about the shape chosen on a mat"),
    "models:change:closest": (WIDGET, WHAT_IS_THERE, "an origin's tick-box, switching it"),
    "models:keydown:closest": (WIDGET, WHAT_IS_THERE, "Enter in a person's word, saying it"),
    "marks:change:closest": (
        WIDGET,
        WHAT_IS_THERE,
        "a mark's kind chosen, a person's word on it; or another picture's marks listed",
    ),
    "marks:click:closest": (WIDGET, WHAT_YOU_SEE, "a mark chosen, for the ring's Marks cells"),
    "tourJourneys:change:chosen": (
        WIDGET,
        WHAT_YOU_SEE,
        "a journey chosen, the page taken to its first stage",
    ),
    # The Tour's box (widgets/tour_popover.js): the header's button, its buttons by one
    # listener, its fold, its name, and its head, by which it is dragged and folded.
    "tourOpen:click:toggle": (WIDGET, WHAT_YOU_SEE, "the header's Tour, its box opened or closed"),
    "box:click:closest": (
        WIDGET,
        WHAT_IS_THERE,
        "a button of the tour's box: a stage gone to, the page taken there, or a word kept",
    ),
    "more:toggle:keep": (
        WIDGET,
        WHAT_YOU_SEE,
        "what the page did and what to try folded or unfolded, kept by this browser",
    ),
    "who:change:named": (WIDGET, WHAT_YOU_SEE, "the name typed, kept by this browser"),
    "noteField:keydown:act": (WIDGET, WHAT_IS_THERE, "Enter in the field for what is off: Off"),
    "head:pointerdown:closest": (WIDGET, WHAT_YOU_SEE, "the tour's box taken hold of by its head"),
    "head:pointermove:move": (
        WIDGET,
        WHAT_YOU_SEE,
        "the tour's box dragged, kept where it is left",
    ),
    "head:pointerup:up": (WIDGET, NOTHING, "the tour's box let go"),
    "head:dblclick:closest": (
        WIDGET,
        WHAT_YOU_SEE,
        "a double-click on the tour's box's head: folded to it, or unfolded",
    ),
    "window:resize:isOpen": (
        AUTOMATIC,
        WHAT_YOU_SEE,
        "the window resized: the tour's box kept whole on the page",
    ),
    "marks:input:closest": (
        WIDGET,
        WHAT_YOU_SEE,
        "the history's slider moved: the whiteboard as it stood then",
    ),
    "marks:pointerdown:grabCorner": (
        WIDGET,
        WHAT_YOU_SEE,
        "a whiteboard's corner taken hold of on its photograph",
    ),
    "marks:pointermove:dragCorner": (
        WIDGET,
        WHAT_YOU_SEE,
        "a whiteboard's corner dragged on its photograph",
    ),
    "marks:pointerup:dropCorner": (
        WIDGET,
        WHAT_IS_THERE,
        "a whiteboard's corner let go: its photograph squared again with it",
    ),
    "marks:keydown:closest": (
        WIDGET,
        WHAT_IS_THERE,
        "Enter in a note's box, saying what it says; an arrow key or Enter on a whiteboard's corner",
    ),
    "?:click:open": (
        WIDGET,
        WHAT_YOU_SEE,
        "the Stream Deck + piece's Open Deck, opening the Deck window",
    ),
    "pinned-list:click:closest": (
        WIDGET,
        WHAT_IS_THERE,
        "taking back what a row of Pinned names -- a camera, a view, a board's pin -- "
        "whatever site it is in",
    ),
    "li:click:goToProblem": (
        LIST,
        WHAT_YOU_SEE,
        "a problem's row in Problems, selecting its piece at its level",
    ),
    "siteJobsListEl:click:closest": (
        LIST,
        WHAT_YOU_SEE,
        "a job's row in Site's Jobs, selecting its machine at its level and opening it",
    ),
    # A readout that opens what it counts, as a badge selects what it stands for;
    # a span listened to, not a control written into the markup.
    "validityEl:click:openProblems": (
        WIDGET,
        WHAT_YOU_SEE,
        "the header's count of problems, bringing Problems in front",
    ),
    "li:dblclick:stepIn": (LIST, WHAT_YOU_SEE, "stepping into a piece from the list"),
    "universeCrumbEl:click:toUniverse": (
        LIST,
        WHAT_YOU_SEE,
        "the trail's first crumb: out to the universe, or up to its own level",
    ),
    "siteLevelEl:click:toSiteLevel": (
        LIST,
        WHAT_YOU_SEE,
        "the trail's crumb for the site: up to its own level, and there the other sites",
    ),
    "crumb:click:goUpTo": (LIST, WHAT_YOU_SEE, "a step on the trail"),
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
    "devFlashSketch:click:flashSketchOf": (
        WIDGET,
        WHAT_YOU_SEE,
        "opening the Bench on the piece's own sketch",
    ),
    "devPinManual:click:pinManual": (WIDGET, WHAT_IS_THERE, "pinning the typed board"),
    "manualIn:keydown:pinManual": (WIDGET, WHAT_IS_THERE, "pinning the typed board, by Enter"),
    "feedback-note:keydown:keepNote": (
        WIDGET,
        WHAT_IS_THERE,
        "filing the typed note in the piece's drawer, by Enter",
    ),
    "feedback-measure-plan:keydown:keepOnEnter": (
        WIDGET,
        WHAT_IS_THERE,
        "filing what is typed in a printed piece's dimensions' rows, by Enter in one",
    ),
    # the page reacting to itself
    "window:resize:onResize": (AUTOMATIC, NOTHING, "the window changed size on its own"),
    # Render on demand: the move arrows lighting up under the pointer change nothing
    # in the scene until it is drawn, so they ask for a frame.
    "transformControls:change:invalidate": (
        AUTOMATIC,
        NOTHING,
        "the move arrows lit under the pointer, and the world drawn again",
    ),
    "window:beforeunload:onLeaving": (
        AUTOMATIC,
        NOTHING,
        "leaving with a part's numbers not applied or its SCAD not rendered or saved, "
        "which asks first; what the tab keeps of it is written",
    ),
    # The browser's Back and Forward, not a control of the page's: the site the
    # address names is loaded, as the drop-down put it there.
    "window:popstate:followAddress": (
        AUTOMATIC,
        WHAT_YOU_SEE,
        "the browser's Back or Forward, and the site the address names loaded again",
    ),
    # boards.js: a devkit's serial stream, while its Machine listens to it
    "es:open:opened": (AUTOMATIC, NOTHING, "a devkit's serial stream connected, and says so"),
    "es:close:streamStopped": (
        AUTOMATIC,
        NOTHING,
        "a devkit's serial stream stopped (a task took the port), and is opened again",
    ),
    # ---- a board's Machine, apothecary/static/widgets/machine.js ------------
    # Most of the Machine's buttons are wired by assignment rather than by
    # listening, so the markup carries them; these are the ones that listen.
    "level-history:click:closest": (
        LIST,
        WHAT_YOU_SEE,
        "picking an earlier bed reading to look at",
    ),
    "level-card:click:closest": (WIDGET, WHAT_IS_THERE, "a corner button, moving the nozzle there"),
    # ---- the Bench --------------------------------------------------------
    "coresEl:click:closest": (WIDGET, WHAT_IS_THERE, "a core's Install button"),
    "modulesEl:click:closest": (WIDGET, WHAT_IS_THERE, "a toolchain module's Install button"),
    "libEl:keydown:libraries": (WIDGET, WHAT_IS_THERE, "installing the typed libraries, by Enter"),
    "sketchEl:change:choose": (
        WIDGET,
        WHAT_YOU_SEE,
        "choosing a sketch, which fills in the board it is built for",
    ),
    "fqbnEl:input:enable": (WIDGET, WHAT_YOU_SEE, "typing a board, which enables the buttons"),
    "portEl:change:enable": (WIDGET, WHAT_YOU_SEE, "choosing a port, which enables the buttons"),
    "historyEl:click:closest": (LIST, WHAT_YOU_SEE, "opening an earlier task's output"),
    # ---- a board's Machine, its print card, header, log and control overlay --
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
    # ---- Layers (widgets/layers.js): one listener of each kind on the window's root; ----
    # its rows (depth, a shown and a selectable tick for each layer) are drawn by it and
    # are the pick scope's (static/pick_scope.js) to change: tick-boxes and a stepper, as
    # Settings' are, not a list of the scene's things.
    "root:change:onChange": (
        WIDGET,
        WHAT_YOU_SEE,
        "a layer's Shown or Selectable tick, applied at once",
    ),
    "root:click:onClick": (
        WIDGET,
        WHAT_YOU_SEE,
        "the depth stepper's - and +, or Reset, in the Layers window",
    ),
    # ---- Bed (widgets/bed_shims.js): a run chosen in Runs, by a click or Enter on its ----
    # row, and Fixes' buttons, by one listener on its window.
    "runs:click:onRunsClick": (
        LIST,
        WHAT_YOU_SEE,
        "a run chosen in Runs, drawn over the printer's bed in the world; or Probe hot above",
    ),
    "hotC:input:(nothing)": (
        WIDGET,
        WHAT_YOU_SEE,
        "a bed temperature typed in Runs, kept over the filament's as the runs redraw",
    ),
    "runs:keydown:onRunsKey": (
        LIST,
        WHAT_YOU_SEE,
        "a run chosen in Runs with Enter, drawn over the printer's bed in the world",
    ),
    "fixes:click:onFixesClick": (
        WIDGET,
        WHAT_IS_THERE,
        "Keep or Make these in Fixes, told which by its id",
    ),
    # ---- Loops (widgets/loops.js): one listener of each kind on the window's root, ----
    # its buttons, choices and figures drawn by it; and the surfaces' stream, on which the
    # server tells an experiment's progress and a kept experiment's document.
    "root:click:onLoopsClick": (
        WIDGET,
        WHAT_IS_THERE,
        "Read, Start, Cancel or Set on machine in the Loops window, told which by its class",
    ),
    "root:change:onLoopsChange": (
        WIDGET,
        WHAT_YOU_SEE,
        "a loop, a rule or an experiment chosen in the Loops window",
    ),
    "root:input:onLoopsInput": (
        WIDGET,
        WHAT_YOU_SEE,
        "a figure, the ceiling or the longest time typed: the server asked whether it would start",
    ),
    "tellings:change:heardLoop": (
        AUTOMATIC,
        WHAT_YOU_SEE,
        "the server telling an experiment's progress, or a kept experiment's document",
    ),
    "tellings:surfaces:catchUp": (
        AUTOMATIC,
        WHAT_YOU_SEE,
        "the surfaces' stream opened again: the experiment asked for afresh",
    ),
    "tellings:missed:catchUp": (
        AUTOMATIC,
        WHAT_YOU_SEE,
        "tellings missed on the surfaces' stream: the experiment asked for afresh",
    ),
    "tellings:error:streamFaltered": (
        AUTOMATIC,
        WHAT_YOU_SEE,
        "the surfaces' stream dropped: a running experiment asked for once a second",
    ),
    # ---- Settings (widgets/settings.js): one listener of each kind on the panel ----
    "settingsEl:click:settingClicked": (
        WIDGET,
        WHAT_YOU_SEE,
        "a shortcut's field set waiting for a key, a setting's reset, or Reset all",
    ),
    "settingsEl:change:settingChanged": (
        WIDGET,
        WHAT_YOU_SEE,
        "a setting's tick-box, drop-down or number, changed and applied at once",
    ),
    "settingsEl:keydown:keyCaptured": (
        WIDGET,
        WHAT_YOU_SEE,
        "the key a waiting shortcut's field takes, refused when another shortcut holds it",
    ),
    "settingsEl:focusout:captureLetGo": (
        WIDGET,
        NOTHING,
        "a waiting shortcut's field let go of when the focus leaves it",
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
    # ---- the Airgap (widgets/airgap.js): its controls, and its pictures hovered and clicked
    "toEditorEl:click:act": (
        WIDGET,
        WHAT_YOU_SEE,
        "the panel's values written into the part's text",
    ),
    "fromEditorEl:click:act": (WIDGET, WHAT_YOU_SEE, "the part's text read again"),
    "copyScadEl:click:act": (WIDGET, WHAT_YOU_SEE, "the text with the panel's values copied"),
    "copyMetricsEl:click:act": (WIDGET, WHAT_YOU_SEE, "the metrics document copied"),
    "resetEl:click:act": (WIDGET, WHAT_YOU_SEE, "the panel put back on the part's text"),
    "phiEl:input:scrubTo": (WIDGET, WHAT_YOU_SEE, "the rotor angle, or the run's time, scrubbed"),
    "playEl:click:setPlaying": (
        WIDGET,
        WHAT_YOU_SEE,
        "the rotor spun or the run played, and paused",
    ),
    "presetEl:change:choosePreset": (WIDGET, WHAT_YOU_SEE, "a preset's arrangement taken"),
    "rigEl:change:rigChanged": (WIDGET, WHAT_YOU_SEE, "the rig document read, checked and run"),
    "sweepEl:change:sweepChanged": (WIDGET, WHAT_YOU_SEE, "the sweep line read and checked"),
    "runEl:click:act": (WIDGET, WHAT_YOU_SEE, "the metric mapped over the two ranges"),
    "dynSpeedEl:mousemove:sayRunAt": (
        GESTURE,
        NOTHING,
        "the run's reading at the time under the pointer",
    ),
    "dynSpeedEl:click:scrubRunTo": (GESTURE, WHAT_YOU_SEE, "the playback scrubbed to that time"),
    "gapmapEl:mousemove:sayGapAt": (GESTURE, NOTHING, "the gap at the angles under the pointer"),
    "gapmapEl:click:setPhiFromGap": (GESTURE, WHAT_YOU_SEE, "the rotor angle set from the map"),
    "energyEl:mousemove:sayEnergyAt": (
        GESTURE,
        NOTHING,
        "co-energy and torque at the angle under the pointer",
    ),
    "energyEl:click:setPhiTo": (GESTURE, WHAT_YOU_SEE, "the rotor angle set from the curve"),
    "inductEl:click:setPhiFromInductance": (
        GESTURE,
        WHAT_YOU_SEE,
        "the rotor angle set from the inductance",
    ),
    "sweepMapEl:mousemove:saySweepCell": (
        GESTURE,
        NOTHING,
        "the sweep cell under the pointer read out",
    ),
    "sweepMapEl:click:loadSweepCell": (
        GESTURE,
        WHAT_YOU_SEE,
        "that cell's two values taken, into the text where it is edited",
    ),
    # ---- Motion (widgets/motion.js): one listener of each kind on the window ----
    "motionEl:click:clicked": (
        WIDGET,
        WHAT_YOU_SEE,
        "Play or Pause, Back, Step or Reset, each doing what its cell of Part › View › Motion does",
    ),
    "motionEl:input:scrubbed": (
        WIDGET,
        WHAT_YOU_SEE,
        "the motion's slider moved, the pieces with it",
    ),
    "motionEl:change:ticked": (
        WIDGET,
        WHAT_YOU_SEE,
        "Bought ticked or not, what is bought shown or hidden",
    ),
    # ---- Badge (widgets/badge.js): one listener on the window ----
    "badgeEl:click:clicked": (
        WIDGET,
        WHAT_IS_THERE,
        "a face, the word, ⚒ Print or ⚒ Cut, each doing what its cell or ⚒ Make does",
    ),
    # ---- the Workspace ------------------------------------------------------
    "root:click:closest": (
        WIDGET,
        WHAT_YOU_SEE,
        "a Workspace button doing what it names, or a frame, dot or row opening its evidence",
    ),
    "root:change:closest": (WIDGET, WHAT_IS_THERE, "a camera's device chosen in its row"),
}

LISTENS = re.compile(r"addEventListener\s*\(\s*['\"]([\w-]+)['\"]\s*,")

# Fetched by the label they carry in the page rather than by a plain name.
# Searched only within the current statement, never across one, so a mention in
# the line above cannot claim a listener that is not its own. Longer labels
# before the ones they begin with, so `.dev-pin-manual` is not read as `.dev-pin`.
FETCHED_BY_LABEL: Sequence[Tuple[str, str]] = (
    (r"pos-\$\{axis\}", "posAxis"),
    (r"\.zoom-in-btn", "zoomInLink"),
    (r"\.dev-pin-manual", "devPinManual"),
    (r"\.dev-open", "devOpen"),
    (r"\.dev-unpin", "devUnpin"),
    (r"\.dev-pin", "devPin"),
    (r"\.dev-query", "devQuery"),
    (r"\.dev-via", "devVia"),
    (r"\.dev-rescan", "devRescan"),
    (r"\.dev-flash-sketch", "devFlashSketch"),
)

# Fetched by id through a module's one-letter helper: `$("auto")`.
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
        # The page's guard against a key a person is typing (in a box, or the SCAD
        # editor) is not what the key does.
        "typing",
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
# directly, each entry saying which module it came from; one reached only
# through another module is not counted for it.
MARKS = ("machine_marks.js", "picture_marks.js", "pictures.js", "boards.js")
STATIC_IMPORT = re.compile(r"from\s+[\"']/static/([\w-]+\.js)[\"']")


def marks_of(page: Path) -> List[Path]:
    """The marks modules a page imports directly, in the order it imports them."""
    text = page.read_text(encoding="utf-8")
    return [STATIC / name for name in STATIC_IMPORT.findall(text) if name in MARKS]


def take(page: Path | None = None) -> Census:
    """Count what a person can operate, from the page itself.

    The viewer unless told otherwise; ``take(path)`` counts another page (a
    draft, or one a test writes). One page at a time, and the numbers are
    never added -- except
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
