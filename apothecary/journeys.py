"""The page's journeys: the paths a person takes through its windows.

A journey's windows are laid out together as a view, as each focused system's are
(systems.py): listed in the header's ⚙ View › Views and on the ring's Panels ›
Windows after the systems', and defined on the page from this registry by
static/systems.js. docs/plans/journeys-2026-11-11.md plans them.

A view is written as a system's is (systems.py's ``Layout``): window ids, a
``stack`` of tabs, a ``row`` or ``column`` of them, the world's window as
``{"world": True}``. A window the page has not got when the view is laid out --
a board's Machine while none is open -- is left out of it.

A journey is chosen and stepped in the Tour box (static/widgets/tour_popover.js,
tour.py), and nowhere else: its steps numbered there, the one a person is on marked,
‹ and › going to the one before and after. A step brings its windows forward, the one
it is about first; choosing a window it owns -- its tab, ⊞ Windows or a stack's + --
moves the box to it. The box closed, the journey is left, its windows where they are.

The journeys are in the order of the chain the page manages, each handing the next
what it made: a part designed; the part made on a printer, or cut on a router; the
board that runs a machine built, flashed and heard; a deck's knobs on the machines;
the site brought up a step at a time through the family's hub; the site watched; a
drawing photographed into pieces, which are parts to design; and two ends joined by
an adapter the server derives between them, a part to print.

The tour takes the page to a stage by its ``puts``: what the page does to stand where
the stage is, each a verb the page already has and its subject, done only where it is
not so already (the template's ``stagePut``). Each journey names the site its subjects
stand in, which the tour opens first where another is open, so a stage is the same
from wherever a person opens the tour. None arms, starts or sends anything, and
none supplies what is a person's to bring -- a board plugged in, a photograph taken:
where that is missing the rest is left, the stage is entered all the same, and the
page says what the stage needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from .site_names import UNIVERSE
from .systems import FAMILY, PART, Layout


@dataclass(frozen=True)
class Step:
    id: str
    # Its name in the Tour box, after its number.
    label: str
    # The tour's words for the stage, and the status line's as it is entered.
    hint: str
    # The windows entering it brings forward, the one it is about first: that one is
    # in front where two share a stack. A closed one is opened again.
    forward: Tuple[str, ...]
    # The windows that say a person is on it, when chosen. Each window is one step's.
    owns: Tuple[str, ...] = ()
    # Whether entering it draws the path of the file the machine has chosen, as the
    # Machine view does.
    draws: bool = False
    # The walkthrough steps that go through it, ``page.md#step``, and the pages that
    # show it whole, ``page.md``: what the tour gives a person to try while on it
    # (apothecary/tour.py).
    shown_by: Tuple[str, ...] = ()
    # What the tour does to take the page to it, after its journey's ``staged_on``: (verb,
    # subject) pairs, in order.
    puts: Tuple[Tuple[str, str], ...] = ()


# What takes the page to a stage, each as a person would do it (the template's stagePut):
#   pin       a board on a port pinned to a piece, ``piece:port``, as Pin in the
#             piece's Device section does, where that port is listed: a piece with
#             no board pinned and no such port says to pin one
#   machine   a piece's Machine opened, the piece chosen first: with no board
#             connected, as the site plans it
#   part      a piece chosen
#   makes     the open Machine's Print window naming a piece under makes, and the file kept
#             made from it chosen where one is kept: nothing is sliced
#   file      the open Machine keeping a file for a part: sliced, or its toolpath
#             written, where none is kept
#   feedback  a part's cabinet in Part › Feedback, the piece chosen first, as its
#             Part › View › Feedback does
#   fit       a piece chosen and framed in the world, as f does
#   edit      a part's editor opened, as Part › Edit does
#   scad      a part's SCAD in its window, as Part › SCAD does
#   bench     the Bench opened on a piece's sketch, as Device › Flash sketch does
#   working   the Workspace opened on a machine, or on the site ("")
#   picture   a picture of the folder pinned at a piece, ``piece:file``, and framed
#             where it lies
#   shapes    the shapes of the picture drawn at a piece found, ``piece:finder``
PUTS = (
    "pin",
    "machine",
    "part",
    "makes",
    "file",
    "feedback",
    "fit",
    "edit",
    "scad",
    "bench",
    "working",
    "picture",
    "shapes",
)


# The site every journey is staged in: the bench's own, whose pieces and machines
# their puts name.
SITE = "garage"


@dataclass(frozen=True)
class Journey:
    id: str
    title: str
    # The colour it wears where it is listed: the group of windows it is mostly in.
    group: str
    # The window its view needs open first, the page's own for a subject, and how
    # that subject is opened: until it is, the view is greyed and says so.
    requires: str
    opened_by: str
    view: Layout
    # What the tour calls it: what a person does and to what, the title's verb and one
    # thing (Design a part, Print a part).
    name: str = ""
    steps: Tuple[Step, ...] = ()
    # What the tour does for every stage of it, before the stage's own ``puts``: the
    # machine whose window it opens and the piece it chooses.
    staged_on: Tuple[Tuple[str, str], ...] = ()
    # Its view's cell under the ring's Panels › Windows, as a system's view's is, and
    # its entry in ⚙ View › Views. That ring is full, so only the first journey has
    # one: the others' views are laid out by the tour alone.
    cell: str = ""
    # The site its subjects stand in -- the pieces and machines its puts name -- which
    # the tour opens first where another is open: the garage, or the universe, where
    # every part stands.
    site: str = SITE


def _machine_view(*beside_the_machine: str, active: str) -> Layout:
    """The world beside a column of Site, Selected, Parameters and the chosen machine's
    windows in one stack at the column's foot."""
    return {
        "row": [
            {"world": True, "size": 62},
            {
                "column": [
                    {
                        "stack": ["site", "problems", "pinned", "jobs", "scad"],
                        "size": 22,
                        "active": "site",
                    },
                    {"stack": ["selected"], "size": 26},
                    {"stack": ["part-parameters"], "size": 22},
                    {"stack": ["machine", *beside_the_machine], "size": 30, "active": active},
                ],
                "size": 38,
            },
        ]
    }


# Design a part: chosen among the site's pieces, its numbers in Parameters, its text in
# the SCAD editor, what was saved and applied, and whether it is ready. The Part
# system's own view (systems.py). What it hands on is a part a machine can make.
DESIGN = Journey(
    id="design",
    title="Design",
    group="Part",
    requires="selected",
    opened_by="a piece's row in Site",
    view=PART.view,
    name="Design a part",
    staged_on=(("part", "footpedal"),),
    steps=(
        Step(
            "choose",
            "Choose",
            "the part, among the site's pieces: what it is drawn from, and its envelope",
            forward=("site", "selected"),
            owns=("site",),
            puts=(("fit", "footpedal"),),
        ),
        Step(
            "numbers",
            "Numbers",
            "its numbers as controls in Parameters: staged, checked, then Apply in Selected",
            forward=("part-parameters", "selected"),
            owns=("selected", "part-parameters"),
            puts=(("edit", "footpedal"),),
            shown_by=(
                "04-designing-a-part.md#1",
                "04-designing-a-part.md#2",
                "04-designing-a-part.md#3",
                "08-fitting.md",
                "11-contested-numbers.md",
            ),
        ),
        Step(
            "text",
            "Text",
            "its SCAD in the editor: checked as typing stops, rendered once it reads",
            forward=("part-scad",),
            owns=("part-scad", "scad"),
            puts=(("scad", "footpedal"),),
            shown_by=(
                "06-editing-a-parts-scad.md#2",
                "06-editing-a-parts-scad.md#3",
                "06-editing-a-parts-scad.md#4",
                "17-a-part-that-computes-itself.md",
            ),
        ),
        Step(
            "kept",
            "Kept",
            "every variant saved of it, and this tab's applies, each drawn again from its row",
            forward=("part-variants", "part-history"),
            owns=("part-variants", "part-history"),
            puts=(("edit", "footpedal"),),
            shown_by=(
                "06-editing-a-parts-scad.md#7",
                "04-designing-a-part.md#11",
                "07-a-part.md",
            ),
        ),
        Step(
            "ready",
            "Ready",
            "whether it is ready to make, and what the site says is wrong",
            forward=("part-readiness", "problems"),
            owns=("part-readiness", "problems"),
            puts=(("edit", "footpedal"),),
            shown_by=(
                "12-ready-to-build.md",
                "13-status-and-progress.md",
                "14-problems-and-solutions.md",
            ),
        ),
    ),
)


# Print a part on a machine: a part chosen in Site, its numbers in Parameters, the
# machine's Print window to slice it and draw its path, the job in Jobs, and the piece
# made filed in its part's cabinet, Part › Feedback, where the printer is tuned from the
# coupon made to be measured, a turn at a time. The machine's window and its Print window
# share a stack at the column's foot, Print in front.
MAKE = Journey(
    id="make",
    title="Print",
    cell="Print view",
    group="Machine",
    requires="machine",
    opened_by="a machine's badge or its row in Site, or Slice on a part's ring",
    view=_machine_view(
        "machine-print", "part-feedback", "pictures", "bench", "settings", active="machine-print"
    ),
    name="Print a part",
    staged_on=(("machine", "printer_1"), ("part", "footpedal"), ("makes", "footpedal")),
    steps=(
        Step(
            "choose",
            "Choose",
            "the part, among the site's pieces",
            forward=("site", "selected"),
            owns=("site", "problems", "pinned", "scad"),
        ),
        Step(
            "shape",
            "Shape",
            "its numbers, in Parameters",
            forward=("part-parameters", "selected"),
            owns=("selected", "part-parameters"),
            shown_by=("04-designing-a-part.md#2", "04-designing-a-part.md#3"),
        ),
        Step(
            "slice",
            "Slice",
            "the machine's Print window: the part under makes, then Slice",
            forward=("machine-print",),
            owns=("machine-print",),
            shown_by=("03-a-picture-to-a-print.md#7",),
        ),
        Step(
            "see",
            "See",
            "the chosen file's path, drawn on the machine",
            forward=("machine-print",),
            draws=True,
            puts=(("file", "footpedal"),),
        ),
        Step(
            "print",
            "Start",
            "control armed in the Machine, ▶ Print, the job in Jobs",
            forward=("machine-print", "jobs"),
            owns=("machine", "jobs"),
            shown_by=("03-a-picture-to-a-print.md#8", "03-a-picture-to-a-print.md#9"),
        ),
        Step(
            "measure",
            "Measure",
            "the piece made, in its part's cabinet, Part › Feedback, a drawer a print, "
            "opened on it as its print ends: read under measured a feature a row and filed "
            "as the next turn of the printer's tuning, which says what the readings imply "
            "-- a box's sizes separate nothing, and print_coupon is the piece made to be "
            "measured; or looked at under seen, each fault none to bad, a look that moves "
            "one setting; Take turn takes either into the printer's next slices, for the "
            "filament the piece used",
            forward=("part-feedback",),
            owns=("part-feedback",),
            shown_by=(
                "46-a-printer-tuned-from-its-prints.md",
                "50-a-printer-tuned-from-what-it-shows.md",
            ),
            puts=(("file", "footpedal"), ("feedback", "footpedal")),
        ),
    ),
)


# Cut a part on the router: the same path as Print a part's through another machine. The part
# says how it is cut, the router's Cut window writes its toolpath and draws it on the
# table, the router says what it needs before it moves, the cut is a job, and the piece
# cut is measured in its part's cabinet, Part › Feedback, its tool's allowance fed back
# to the router.
CUT = Journey(
    id="cut",
    title="Cut",
    group="Machine",
    requires="machine",
    opened_by="the router's badge or its row in Site, or Toolpath on a part's ring",
    view=_machine_view(
        "machine-print",
        "part-feedback",
        "machine-status",
        "machine-level",
        active="machine-print",
    ),
    name="Cut a part",
    staged_on=(("machine", "cnc_router"), ("part", "router_coupon"), ("makes", "router_coupon")),
    steps=(
        Step(
            "choose",
            "Choose",
            "a part that says how it is cut, among the site's pieces",
            forward=("site", "selected"),
            owns=("site", "problems", "pinned", "scad"),
            shown_by=("20-a-part-through-the-router.md",),
        ),
        Step(
            "toolpath",
            "Toolpath",
            "the router's Cut window: the part under makes, then Toolpath",
            forward=("machine-print",),
            owns=("machine-print",),
            shown_by=("24-a-cut-from-the-card.md#1", "24-a-cut-from-the-card.md#2"),
        ),
        Step(
            "see",
            "See",
            "the toolpath drawn on the table, a pass at a time under the preview's slider",
            forward=("machine-print",),
            draws=True,
            puts=(("file", "router_coupon"),),
            shown_by=("24-a-cut-from-the-card.md#3", "21-a-toolpath-previewed.md"),
        ),
        Step(
            "needs",
            "Needs",
            "what the router needs before it moves: its state, its pins, each axis's home",
            forward=("machine-status", "machine"),
            owns=("machine-status", "machine-level"),
            shown_by=(
                "31-what-the-router-needs.md#3",
                "31-what-the-router-needs.md#5",
                "31-what-the-router-needs.md#6",
                "19-the-router.md",
            ),
        ),
        Step(
            "cut",
            "Cut",
            "control armed in the Machine, the work zeroed, ▶ Cut, the job in Jobs",
            forward=("machine-print", "jobs"),
            owns=("machine", "jobs"),
            shown_by=(
                "24-a-cut-from-the-card.md#5",
                "24-a-cut-from-the-card.md#6",
                "24-a-cut-from-the-card.md#8",
            ),
        ),
        Step(
            "measure",
            "Measure",
            "the piece cut, in its part's cabinet, Part › Feedback: each size it names "
            "typed under measured, checked against what was designed, filed, and the "
            "tool's allowance kept for the router's next toolpaths",
            forward=("part-feedback",),
            owns=("part-feedback",),
            puts=(("file", "router_coupon"), ("feedback", "router_coupon")),
            shown_by=("20-a-part-through-the-router.md",),
        ),
    ),
)


# Flash a board: the firmware a machine runs. The board on its port pinned to
# its piece, the piece's sketch on the Bench with its builds, the devkit's Flashing
# window where it is built and uploaded, and its Sketch and Log, where what it says is
# heard. The port is the simulated devkit's (simulated.py's DEVKIT).
BOARD = Journey(
    id="board",
    title="Flash",
    group="Machine",
    requires="machine",
    opened_by="a board's ring, Device › Open",
    view={
        "row": [
            {"world": True, "size": 36},
            {
                "column": [
                    {"stack": ["machine"], "size": 28},
                    {
                        "stack": ["machine-sketch", "machine-flashing"],
                        "size": 36,
                        "active": "machine-sketch",
                    },
                    {"stack": ["machine-log"], "size": 36},
                ],
                "size": 32,
            },
            {
                "column": [
                    {"stack": ["bench"], "size": 62},
                    {"stack": ["selected", "site"], "size": 38, "active": "selected"},
                ],
                "size": 32,
            },
        ]
    },
    name="Flash a board",
    staged_on=(("pin", "esp32_blink:/dev/ttyFAKE2"), ("machine", "esp32_blink")),
    steps=(
        Step(
            "pin",
            "Pin",
            "the board on its port pinned to its piece, in Selected: which device is which",
            forward=("selected", "site"),
            owns=("selected", "site"),
            puts=(("fit", "esp32_blink"),),
        ),
        Step(
            "bench",
            "Bench",
            "the part's sketch on the Bench: each build of it with its toolchain, and Compile",
            forward=("bench",),
            owns=("bench",),
            puts=(("bench", "esp32_blink"),),
            shown_by=("05-firmware.md#1", "05-firmware.md#2", "05-firmware.md#6"),
        ),
        Step(
            "flash",
            "Flash",
            "the board's Flashing window: the sketch built and uploaded to its port, after asking",
            forward=("machine-flashing", "machine"),
            owns=("machine-flashing", "machine"),
            shown_by=("05-firmware.md#3", "05-firmware.md#5", "05-firmware.md#7"),
        ),
        Step(
            "hear",
            "Hear",
            "its Sketch and its Log: what it should run, and what it was heard saying",
            forward=("machine-sketch", "machine-log"),
            owns=("machine-sketch", "machine-log"),
            shown_by=("05-firmware.md#4", "05-firmware.md#8"),
        ),
    ),
)


# Drive a machine: the Stream Deck +, drawn by the server, whose knobs jog the
# machine chosen on it once that machine's control is armed.
HANDS = Journey(
    id="hands",
    title="Drive",
    group="Tools",
    requires="deck",
    opened_by="⊞ Windows › Deck, or Open Deck on the stream_deck piece",
    view={
        "row": [
            {"world": True, "size": 40},
            {"stack": ["deck"], "size": 28},
            {
                "column": [
                    {"stack": ["machine", "machine-status"], "size": 62, "active": "machine"},
                    {"stack": ["selected", "site"], "size": 38, "active": "selected"},
                ],
                "size": 32,
            },
        ]
    },
    name="Drive a machine",
    staged_on=(("part", "stream_deck"),),
    steps=(
        Step(
            "deck",
            "Deck",
            "the Stream Deck + as the server draws it: its keys, its strip, and what it heard",
            forward=("deck", "selected"),
            owns=("deck", "selected"),
            puts=(("fit", "stream_deck"),),
            shown_by=(
                "26-the-stream-deck.md#1",
                "26-the-stream-deck.md#2",
                "26-the-stream-deck.md#3",
            ),
        ),
        Step(
            "knobs",
            "Knobs",
            "its knobs jog the machine chosen on it, once armed: the printer's Machine beside it",
            forward=("deck", "machine"),
            owns=("machine", "machine-status"),
            puts=(("machine", "printer_1"),),
            shown_by=(
                "27-the-deck-jogging-the-machines.md#1",
                "27-the-deck-jogging-the-machines.md#2",
                "27-the-deck-jogging-the-machines.md#3",
                "27-the-deck-jogging-the-machines.md#5",
            ),
        ),
    ),
)


# Start a site: the procedure, each step a member's of the family and fired
# through the hub on GO; the members, each with its door; and the hub's audit of what
# it delivered. The Family system's own view.
BRING_UP = Journey(
    id="bring-up",
    title="Start",
    group="Family",
    requires="procedure",
    opened_by="⊞ Windows › Procedure",
    view=FAMILY.view,
    name="Start a site",
    steps=(
        Step(
            "steps",
            "Steps",
            "the site's procedure: each step a member's, fired through the family's hub on GO",
            forward=("procedure",),
            owns=("procedure",),
            shown_by=(
                "25-a-procedure-through-the-window.md#1",
                "25-a-procedure-through-the-window.md#2",
                "25-a-procedure-through-the-window.md#6",
                "23-a-procedure.md",
            ),
        ),
        Step(
            "members",
            "Members",
            "each member of the family: how it is reached, and its door to where its step works",
            forward=("family-members", "procedure"),
            owns=("family-members",),
            shown_by=(
                "25-a-procedure-through-the-window.md#9",
                "25-a-procedure-through-the-window.md#10",
                "22-the-irl-hub.md",
            ),
        ),
        Step(
            "audit",
            "Audit",
            "the hub's deliveries, newest first: each step, its member, and how it answered",
            forward=("family-deliveries", "jobs"),
            owns=("family-deliveries", "jobs"),
            shown_by=("25-a-procedure-through-the-window.md#4",),
        ),
    ),
)


# Watch a site: the Workspace, the site as its evidence has it, then one
# machine's hour of it.
WATCH = Journey(
    id="watch",
    title="Watch",
    group="Site",
    requires="working",
    opened_by="⊞ Windows › Workspace",
    view={
        "row": [
            {"world": True, "size": 40},
            {"stack": ["working"], "size": 36},
            {
                "column": [
                    {"stack": ["site", "pinned", "jobs"], "size": 50, "active": "site"},
                    {"stack": ["selected"], "size": 50},
                ],
                "size": 24,
            },
        ]
    },
    name="Watch a site",
    steps=(
        Step(
            "space",
            "Space",
            "the site as its evidence has it: each machine's state, heard or quiet, and its pins",
            forward=("working", "site"),
            owns=("working",),
            puts=(("working", ""),),
            shown_by=(
                "18-the-working-space.md#1",
                "32-a-quiet-board-and-a-router-s-pins.md#1",
                "32-a-quiet-board-and-a-router-s-pins.md#2",
            ),
        ),
        Step(
            "hour",
            "Hour",
            "one machine's hour: its state and heaters poll by poll, and the cameras over it",
            forward=("working", "selected"),
            owns=("selected",),
            puts=(("fit", "printer_1"), ("working", "printer_1")),
            shown_by=(
                "18-the-working-space.md#2",
                "18-the-working-space.md#3",
                "18-the-working-space.md#6",
            ),
        ),
    ),
)


# Read a drawing: the whiteboard on the wall, a photograph of it pinned and
# squared, its strokes found as shapes, its marks sorted, a model asked and never
# trusted, and the shapes ready to stand up as pieces: parts, to design.
DRAWING = Journey(
    id="drawing",
    title="Read",
    group="Pictures",
    requires="pictures",
    opened_by="⊞ Windows › Pictures",
    view={
        "row": [
            {"world": True, "size": 52},
            {
                "column": [
                    {
                        "stack": ["pictures", "marks", "models"],
                        "size": 58,
                        "active": "pictures",
                    },
                    {"stack": ["selected", "site"], "size": 42, "active": "selected"},
                ],
                "size": 48,
            },
        ]
    },
    name="Read a drawing",
    staged_on=(("part", "whiteboard"),),
    steps=(
        Step(
            "board",
            "Board",
            "the whiteboard on the garage's wall: a place a picture can lie",
            forward=("selected", "site"),
            owns=("site",),
            puts=(("fit", "whiteboard"),),
            shown_by=("30-a-whiteboard-round-twice-through-the-page.md#1",),
        ),
        Step(
            "picture",
            "Picture",
            "a photograph of it pinned there: squared to it, sized by it, laid in front",
            forward=("pictures", "selected"),
            owns=("pictures",),
            puts=(("picture", "whiteboard:whiteboard.png"),),
            shown_by=(
                "30-a-whiteboard-round-twice-through-the-page.md#2",
                "28-a-whiteboard-to-a-model.md",
            ),
        ),
        Step(
            "shapes",
            "Shapes",
            "each closed stroke outlined as a shape, with a word for it and how sure it is",
            forward=("selected",),
            owns=("selected",),
            puts=(("picture", "whiteboard:whiteboard.png"), ("shapes", "whiteboard:outline")),
            shown_by=("30-a-whiteboard-round-twice-through-the-page.md#3",),
        ),
        Step(
            "marks",
            "Marks",
            "each mark sorted, a diagram's or writing; the corners it was squared from",
            forward=("marks",),
            owns=("marks",),
            puts=(("picture", "whiteboard:whiteboard.png"), ("shapes", "whiteboard:outline")),
            shown_by=(
                "30-a-whiteboard-round-twice-through-the-page.md#4",
                "37-marks-worn-in-the-world.md#1",
                "38-a-whiteboard-s-corners.md#1",
            ),
        ),
        Step(
            "models",
            "Models",
            "an image model asked about a shape chosen on the picture, and never trusted",
            forward=("models",),
            owns=("models",),
            puts=(("picture", "whiteboard:whiteboard.png"), ("shapes", "whiteboard:outline")),
            shown_by=(
                "35-the-models-window.md#1",
                "35-the-models-window.md#3",
                "35-the-models-window.md#4",
                "36-the-models-window-narrow-and-wide.md#2",
            ),
        ),
        Step(
            "pieces",
            "Pieces",
            "Picture › Make stands each shape up as a piece: a part, to design and to make",
            forward=("selected", "site"),
            puts=(("picture", "whiteboard:whiteboard.png"), ("shapes", "whiteboard:outline")),
            shown_by=(
                "30-a-whiteboard-round-twice-through-the-page.md#5",
                "29-a-whiteboard-round-twice.md",
            ),
        ),
    ),
)


# Join a hose: two ends, each one part at its numbers -- a preset chosen, what calipers
# read typed over it -- and the adapter between them derived by the server, drawn, and
# each end's fit said; its numbers adjusted, each fit said again. It stands in the
# universe, where the port part and the adapter are. What it hands on is the adapter,
# which ⚒ Make takes to a printer, where Print a part goes on.
JOIN = Journey(
    id="join",
    title="Join",
    group="Part",
    requires="selected",
    opened_by="a part's row in Site, and ⇄ Adapter in its Selected",
    view=PART.view,
    name="Join a hose",
    site=UNIVERSE,
    steps=(
        Step(
            "ends",
            "Ends",
            "each end one part at its numbers: a preset chosen in Parameters, what calipers "
            "read typed over it; ⇄ Adapter in Selected keeps the first",
            forward=("part-parameters", "selected"),
            owns=("part-parameters",),
            puts=(("edit", "dust_port"),),
            shown_by=("43-parts-that-meet.md",),
        ),
        Step(
            "adapter",
            "Adapter",
            "⇄ Adapter again at the other end's numbers: the adapter between them derived, "
            "drawn, and each end's fit said in Selected",
            forward=("selected",),
            owns=("selected",),
            puts=(("edit", "dust_port"),),
            shown_by=("43-parts-that-meet.md",),
        ),
        Step(
            "ready",
            "Ready",
            "its numbers adjusted and each fit said again after Apply; whether it is ready "
            "to print; ⚒ Make takes it to a printer, where Print a part goes on",
            forward=("part-readiness", "selected"),
            owns=("part-readiness", "problems"),
            puts=(("edit", "hose_adapter"),),
        ),
    ),
)


# In the order of the chain, each handing the next what it made; a view's cell on the
# ring is the first's alone. Join a hose comes last: an adapter between two ends is a
# part designed by the server, which hands it to Print a part as Design a part does.
JOURNEYS: Tuple[Journey, ...] = (DESIGN, MAKE, CUT, BOARD, HANDS, BRING_UP, WATCH, DRAWING, JOIN)


def by_id(journey_id: str) -> Journey:
    return next(j for j in JOURNEYS if j.id == journey_id)


def manifest(journeys: Tuple[Journey, ...] = JOURNEYS) -> List[Dict[str, Any]]:
    """Every journey (or those given: a test's own) as the page reads it: plain JSON."""
    return [
        {
            "id": j.id,
            "title": j.title,
            "cell": j.cell,
            "group": j.group,
            "requires": j.requires,
            "opened_by": j.opened_by,
            "view": j.view,
            "name": j.name,
            "staged_on": [list(put) for put in j.staged_on],
            "site": j.site,
            "steps": [
                {
                    "id": s.id,
                    "label": s.label,
                    "hint": s.hint,
                    "forward": list(s.forward),
                    "owns": list(s.owns),
                    "draws": s.draws,
                    "puts": [list(put) for put in s.puts],
                }
                for s in j.steps
            ],
        }
        for j in journeys
    ]
