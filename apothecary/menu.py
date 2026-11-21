"""The ring's options: a plain function from what was pointed at to a ring.

Nothing here changes anything; a chosen option becomes an `Intent`. Three
rules are enforced here rather than described:

- **Eight options to a ring.** More means the ring needs grouping, so a ninth
  is refused rather than hidden.
- **Twelve characters to a label, never trailed off with dots.** Shortening is
  this module's job (`shorten`, `distinct`).
- **Nine cells, numbered as a keypad** (rad's ``DRAFT-the-menu-addresses-nine-cells``)::

      7 8 9
      4 5 6
      1 2 3

  Cell 5 holds nothing and backs out. Options are seated cardinals first
  (``PLACEMENT``); a digit chooses a cell, an arrow moves to the nearest
  occupied cell (``nearest``), and the digits pressed through nested rings are
  an option's address. ``COMPASS`` names the cell each of the browser's eight
  wedges draws, up first and clockwise. ``tests/conformance/nine_cells.json``
  holds this module and ``static/ring.js`` to the same rules.

Addresses hold still (docs/viewer.md): the cells a ring always has come first
and keep one address wherever it is opened, and an option that comes and goes
is seated after them, so adding one moves no cell before it.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Callable, Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .facets import KIND, KINDS, SYSTEM, SYSTEM_LAYER, facet_of, facets_of, kinds_and_systems
from .facets import SYSTEMS as SITE_SYSTEMS
from .hierarchy import Assembly, find_node_by_path
from .journeys import JOURNEYS
from .journeys import by_id as journey_by_id
from .layer_colours import (
    BED_MESH,
    CATEGORY,
    GRID,
    MACHINE_BUTTONS,
    MEASURE,
    SHELL,
    colour_of,
    shells_in,
)
from .projects.parts.skeleton import ROOT
from .projects.registry import category_of
from .site_names import UNIVERSE, UNIVERSE_SHOWN
from .systems import SYSTEMS, by_id

MOST_OPTIONS = 8
LONGEST_LABEL = 12

# The order options are seated in: cardinals first, then corners. The i-th
# option of a ring sits in cell PLACEMENT[i]. Eight entries, so eight is the
# ceiling structurally and not just by a check.
PLACEMENT: Tuple[int, ...] = (8, 6, 2, 4, 9, 3, 1, 7)

# The centre. Holds nothing, ever; backs out one level and closes at the top.
BACK = 5

# The browser's eight wedges, up first and clockwise: compass slot -> cell.
# angleToIndex with rad's geometry (start at -90 degrees, clockwise) gives the
# slot, and this names the cell that slot draws.
COMPASS: Tuple[int, ...] = (8, 9, 6, 3, 2, 1, 4, 7)

# Where each cell sits on the keypad, as (column, row) with 7 at the top left.
CELLS: Dict[int, Tuple[int, int]] = {
    7: (0, 0), 8: (1, 0), 9: (2, 0),
    4: (0, 1), 5: (1, 1), 6: (2, 1),
    1: (0, 2), 2: (1, 2), 3: (2, 2),
}  # fmt: skip

# An arrow, as the step it means on the keypad.
DIRECTIONS: Dict[str, Tuple[int, int]] = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}

ADDRESS = re.compile(r"^[1-46-9]+$")


class RingTooFull(ValueError):
    """More options than a ring holds. Group them instead of scrolling them."""


class NoSuchCell(LookupError):
    """An address that reaches nothing, or an option no address reaches."""


class Pointing(str, Enum):
    """What the ring was opened on."""

    NODE = "node"
    CANVAS = "canvas"
    DEVICE = "device"


class Context(BaseModel):
    """What the ring was opened on, and which things it applies to.

    ``targets`` are the dotted paths the rest of the tool names a node by --
    ``printer_1.gantry_system`` and so on. A ring opened on a device names its
    port instead. Fields a page sends beyond these are ignored.
    """

    pointing: Pointing
    targets: List[str] = Field(default_factory=list)


class Verdict(BaseModel):
    """What the server would say to one command on a port now (firmware/can.py)."""

    ok: bool
    why: Optional[str] = None
    kind: Optional[str] = None


class Device(BaseModel):
    """What the resolver is told about a board, so it can offer the right verbs.

    Told rather than looked up: the resolver stays a plain function over data,
    and the page already knows each of these about the port it is standing
    on. ``bound`` says the port is pinned to the node the ring was opened on;
    ``printer`` says it speaks G-code, so control is on offer; ``armed`` is the
    control latch, which decides whether the ring says Arm or Disarm.
    """

    port: str
    printer: bool = False
    armed: bool = False
    bound: bool = False
    # The kind of machine a G-code board drives, when the page knows it: ``printer``
    # or ``router`` (apothecary/jobs.py's machine kinds). A router's Control ring is
    # its own: no heaters or bed, but the spindle, work zero and a probe.
    machine: Optional[str] = None
    # What the server would refuse of the port now, per command: ``can`` on its status
    # (firmware/can.py), with what the page knows over it (static/can.js), the answer
    # its Machine's buttons are greyed from. Each act on the ring the answer refuses is
    # greyed with the server's reason (``CAN_VERBS``); told nothing, nothing is.
    can: Optional[Dict[str, Verdict]] = None
    # What the board's machine is called: the machine it is pinned to, as a reason names
    # it (firmware/can.py ``who``), which the server fills in; a ring standing on the
    # port is titled by it, and by the port where nothing is pinned.
    name: Optional[str] = None


class CameraSeen(BaseModel):
    """A camera as the page names it: this browser's device, or a camera part's."""

    id: str
    label: str = "camera"


class ShapeSeen(BaseModel):
    """One shape of a drawn view: its index, its word, and whether it is made."""

    index: int
    word: str = "shape"
    status: str = "found"  # found | made | already_made


class ViewSeen(BaseModel):
    """A view at the place the ring stands on, as the page has it drawn.

    ``finder`` is None for a view pinned and not yet searched: Find shapes is its
    next step."""

    id: str
    picture: str = ""
    finder: Optional[str] = "plain"
    sized: bool = False
    kept: bool = False  # its picture is one the browser kept, so it can be forgotten
    shapes: List[ShapeSeen] = Field(default_factory=list)


class Place(BaseModel):
    """The place the ring stands on -- a host, on the canvas ring the floor, or a
    camera part: its views, newest first; and on a camera part, its device (which
    the intent route fills in from the camera's record) and whether it is live."""

    camera: Optional[CameraSeen] = None
    live: bool = False
    views: List[ViewSeen] = Field(default_factory=list)
    drawn: Optional[str] = None
    chosen_view: Optional[str] = None


class PartSeen(BaseModel):
    """The part under a node ring, as the server knows it: whether its SCAD is its
    own source, to edit (a part built by Python geometry shows what it generates),
    its variants saved in git, newest first (apothecary/projects/parts/saved.py), and
    whether it is a board -- bought and pinned to, never printed, so never sliced."""

    editable: bool = True
    variants: List[str] = Field(default_factory=list)
    # Its deleted variants, in the trash (refs/apothecary/trash/), newest first.
    deleted: List[str] = Field(default_factory=list)
    board: bool = False
    # Whether it says how it is cut (its wrapper's `cuts`): a router's Toolpath is
    # offered on such a part, as Slice is on a printed one.
    cuts: bool = False
    # Its presets by name (``BasePart.presets``), on a part whose numbers drive its model:
    # Part › Presets stages one, as the Preset drop-down in its Parameters does. Each
    # cell says its label where the part gives one (a name longer than a cell holds).
    presets: List[str] = Field(default_factory=list)
    preset_labels: Dict[str, str] = Field(default_factory=dict)
    # Whether it has one round interface, a spigot or a socket, so it is an end an
    # adapter is made between: Part › Adapter does what ⇄ Adapter in Selected does.
    end: bool = False
    # Whether its pieces move as one of its parameters goes (its wrapper's `motion`):
    # Part › View › Motion is offered on such a part.
    motion: bool = False
    # Whether it is a Stream Deck + (tagged ``streamdeck``): its ring's Deck opens the Deck
    # window, as Open Deck in its Selected does.
    deck: bool = False


class PictureContext(BaseModel):
    """What the resolver is told about pictures, as it is told a Device.

    Told rather than looked up: ``cameras`` are this browser's (``asked`` once
    the browser has been allowed to name them), ``pictures`` the ones under the
    picture root, newest first, and ``here`` the place the ring stands on. The
    intent route fills in ``made`` (the site's made pieces), ``camera_parts``
    (its cameras), ``printers`` (the site's printers with a board pinned, which a
    made piece's Print offers), ``words`` (the vocabulary), ``finders`` (those
    that can read the drawn view's picture), on a camera part ``here.camera``
    (its device), and on a part from the parts folder ``part`` (whether its SCAD
    is its own, and its saved variants) from what the server knows, so a page
    cannot claim them."""

    cameras: List[CameraSeen] = Field(default_factory=list)
    asked: bool = False
    pictures: List[str] = Field(default_factory=list)
    chosen_picture: Optional[str] = None
    finders: List[str] = Field(default_factory=list)
    made: List[str] = Field(default_factory=list)
    camera_parts: List[str] = Field(default_factory=list)
    printers: List[str] = Field(default_factory=list)
    # The site's routers with a board pinned, which a part's Toolpath offers.
    routers: List[str] = Field(default_factory=list)
    words: List[str] = Field(default_factory=list)
    here: Place = Field(default_factory=Place)
    part: Optional[PartSeen] = None


class Option(BaseModel):
    """One cell of the ring.

    ``cell`` is where it sits, and it is given by the ring that holds the option
    rather than by whoever builds it. An option built by hand has no cell until
    a ring seats it, and a cell passed in is refused: a number chosen by hand
    is exactly the kind that drifts from the position the browser draws.
    """

    id: str
    label: str
    action: Optional[str] = None
    enabled: bool = True
    # Why it cannot be chosen, while it cannot (``enabled`` false): for a machine's act,
    # the server's own refusal. The wedge shows it, and says it when chosen anyway
    # (static/ring.js).
    why: Optional[str] = None
    destructive: bool = False
    # Not undoable in the page (a site rebuilt, a camera removed, a picture forgotten,
    # a board rebooted): chosen once, the wedge says "again to ..." and waits; chosen
    # again, it is done (the input plan's "confirming by consequence").
    twice: bool = False
    # The one of a list the page has chosen elsewhere (a picture chosen in
    # Pictures), drawn marked; a leaf like any other.
    marked: bool = False
    # The group of windows its work is in (Site, Pictures, a Machine), where it is
    # the way into one: the wedge wears that group's colour, as its windows do
    # (static/tokens.css).
    group: Optional[str] = None
    # The layer of the world whose acts it is (View › Layers): the wedge wears that
    # layer's colour, the colour the world draws the layer in (apothecary/layer_colours.py).
    colour: Optional[str] = None
    children: Optional[List["Option"]] = None
    cell: Optional[int] = None

    model_config = ConfigDict(validate_assignment=True)

    @field_validator("colour")
    @classmethod
    def _a_colour_is_written_as_the_table_writes_one(cls, colour):
        if colour is not None and not re.fullmatch(r"#[0-9a-f]{6}", colour):
            raise ValueError(f"{colour!r} is no colour: #rrggbb, as layer_colours.py writes one")
        return colour

    @field_validator("label")
    @classmethod
    def _label_is_readable(cls, label: str) -> str:
        """Checked on the field, so it still holds when a label is assigned later."""
        if not label.strip():
            raise ValueError("this option has no label; a blank wedge cannot be chosen")
        if len(label) > LONGEST_LABEL:
            raise ValueError(
                f"{label!r} is {len(label)} characters; a label has "
                f"{LONGEST_LABEL}. Shorten it, do not trail it off."
            )
        return label

    @field_validator("children")
    @classmethod
    def _a_submenu_is_a_ring(cls, children):
        # A submenu is held to the same limits, and seating gives each child its cell.
        if children is not None:
            place(children)
        return children

    @field_validator("cell")
    @classmethod
    def _a_cell_is_given_by_the_ring(cls, cell):
        if cell is not None:
            raise ValueError(
                f"cell {cell!r} was given by hand. A cell is where the ring seats "
                "an option, in placement order; put the option in a ring instead."
            )
        return cell

    def model_post_init(self, _context) -> None:
        if (self.action is None) == (self.children is None):
            raise ValueError(
                f"option {self.id!r} must either do something or open a further "
                "ring, and not both or neither"
            )


Option.model_rebuild()


class Ring(BaseModel):
    """One ring of options, each seated in its cell."""

    model_config = ConfigDict(validate_assignment=True)

    title: Optional[str] = None
    options: List[Option]

    @field_validator("options")
    @classmethod
    def _seat_the_options(cls, options):
        # On the field rather than after building, so a ring whose options are
        # swapped later is checked and seated again.
        place(options)
        return options

    def cells(self) -> Dict[int, Option]:
        """Which option sits in which cell. Cell 5 is never a key."""
        return {option.cell: option for option in self.options if option.cell is not None}

    def at(self, cell: int) -> Option:
        """The option in a cell, or a refusal that says what is there instead."""
        if cell == BACK:
            raise NoSuchCell(f"cell {BACK} holds nothing; it backs out one level")
        if cell not in CELLS:
            raise NoSuchCell(f"{cell!r} is not a cell; the cells are 1 to 9")
        seated = self.cells()
        if cell not in seated:
            held = sorted(seated)
            raise NoSuchCell(
                f"cell {cell} is empty on {self.title or 'this ring'}; "
                f"the occupied cells are {held}"
            )
        return seated[cell]


class Intent(BaseModel):
    """What was chosen. The one thing that reaches the rest of the program.

    Everything that changes anything arrives as one of these, from the ring or
    from anywhere else. One way in is what makes it possible to say that
    everything you can do is reachable from the ring.

    ``address`` is the digits pressed to reach the option, when the ring was
    the way in. It is carried so a choice can be repeated and so a log of
    choices reads as something a person could type back.
    """

    action: str
    context: Context
    option_id: str
    address: Optional[str] = None

    @field_validator("address")
    @classmethod
    def _an_address_is_cells(cls, address):
        if address is not None and not ADDRESS.match(address):
            raise ValueError(
                f"address {address!r} is not a run of cells: digits 1 to 9, never "
                f"{BACK}, since {BACK} backs out and is never recorded"
            )
        return address


def check_ring(options: Sequence[Option]) -> None:
    """Refuse a ring that holds too many, or none at all."""
    if not options:
        raise ValueError("a ring with nothing in it is not a ring")
    if len(options) > MOST_OPTIONS:
        raise RingTooFull(
            f"{len(options)} options, and a ring holds {MOST_OPTIONS}. "
            "Group some of them behind one option rather than making the ring "
            f"longer: {[o.id for o in options]}"
        )
    labels = [o.label for o in options]
    if len(set(labels)) != len(labels):
        raise ValueError(
            f"two wedges in one ring read the same: {sorted(labels)}. "
            "Nobody can choose between them on purpose."
        )
    actions = [o.action for o in options if o.action]
    if len(set(actions)) != len(actions):
        raise ValueError(f"two wedges in one ring do the same thing: {sorted(actions)}")


def place(options: Sequence[Option]) -> None:
    """Check a ring, then seat each option in its cell, cardinals first.

    The one place a cell is ever written. It goes round the field's own
    refusal on purpose: that refusal exists so nobody else writes one.
    """
    check_ring(options)
    for option, cell in zip(options, PLACEMENT, strict=False):
        object.__setattr__(option, "cell", cell)


def nearest(occupied: Iterable[int], from_cell: Optional[int], direction: str) -> Optional[int]:
    """The occupied cell an arrow reaches, or where it was if the arrow reaches nothing.

    Not a walk along a row or column: in a four-option ring the corners are
    empty, and walking left from the top cell would hit the edge without ever
    turning down, leaving one cardinal unreachable by arrows. So every occupied
    cell that lies ahead of the arrow is a candidate, and the best is the one
    that sits most squarely in the arrow's line — least off to the side, then
    least far along, then the lower number to settle a tie. The browser runs
    the same rule, and ``tests/conformance/nine_cells.json`` holds both to it.

    With nothing highlighted yet the arrow starts from the centre, so the first
    press lands on the cell nearest the middle in that direction.
    """
    if direction not in DIRECTIONS:
        raise ValueError(f"{direction!r} is not a direction; the arrows are {sorted(DIRECTIONS)}")
    cells = set(occupied)
    if BACK in cells:
        raise ValueError(f"cell {BACK} cannot be occupied; it backs out")
    unknown = cells - set(CELLS)
    if unknown:
        raise ValueError(f"{sorted(unknown)} are not cells; the cells are 1 to 9")

    start = BACK if from_cell is None else from_cell
    if start not in CELLS:
        raise ValueError(f"{from_cell!r} is not a cell to move from")
    col, row = CELLS[start]
    dx, dy = DIRECTIONS[direction]

    best: Optional[Tuple[int, int, int]] = None
    for cell in cells:
        if cell == start:
            continue
        c, r = CELLS[cell]
        along = (c - col) * dx + (r - row) * dy
        if along <= 0:
            continue
        aside = abs((c - col) * dy) + abs((r - row) * dx)
        score = (aside, along, cell)
        if best is None or score < best:
            best = score
    return best[2] if best is not None else from_cell


def shorten(text: str, most: int = LONGEST_LABEL) -> str:
    """Make a label fit, without trailing it off -- in ``most`` characters, a
    label's twelve unless a part of one is being made.

    **Nothing is taken away from a label that already fits**, so ``M3.5_bolt``
    and ``nozzle_0.4mm`` are never read as dotted paths and cut to ``5 bolt``
    and ``4mm``.

    When it does not fit, four steps, each tried only if the one before was not
    enough:

    1. keep only the last part of a dotted path, since the ring is already
       standing on the thing the earlier parts name;
    2. turn separators into spaces;
    3. shorten each word to its first few letters;
    4. drop the middle words, keeping the first and last.

    Never adds dots. A label ending in an ellipsis says something was taken away
    and not what. Never returns nothing either: a blank wedge is a wedge nobody
    can choose on purpose.
    """
    whole = text.strip()
    if 0 < len(whole) <= most:
        return whole

    label = whole.rsplit(".", 1)[-1].replace("_", " ").replace("-", " ").replace(".", " ").strip()
    label = " ".join(label.split())

    if not label:
        # Nothing but separators. Fall back to what was actually passed in, so
        # the wedge says something rather than nothing.
        stripped = "".join(ch for ch in whole if not ch.isspace())
        return (stripped or "unnamed")[:most]

    if len(label) <= most:
        return label

    words = label.split()
    if len(words) == 1:
        return label[:most].rstrip()

    for keep in (6, 5, 4, 3):
        shortened = " ".join(word[:keep] for word in words)
        if len(shortened) <= most:
            return shortened

    ends = f"{words[0][:5]} {words[-1][:5]}"
    return ends[:most].rstrip() or words[0][:most]


def distinct(names: Sequence[str]) -> List[str]:
    """Shorten a set of names so that no two come out the same.

    Shortening alone can make two read the same (``gantry_system_leftmost`` and
    ``gantry_system_leftish``), so a repeat gets a number, made room for rather
    than pushing the label over the limit.
    """
    out: List[str] = []
    seen: Dict[str, int] = {}
    for name in names:
        label = shorten(name)
        if label not in seen:
            seen[label] = 1
            out.append(label)
            continue
        seen[label] += 1
        mark = f" {seen[label]}"
        out.append((label[: LONGEST_LABEL - len(mark)]).rstrip() + mark)
    return out


def resolve(
    context: Context,
    site: Optional[Assembly] = None,
    *,
    site_names: Sequence[str] = (),
    part_category: Optional[Callable[[str], Optional[str]]] = None,
    device: Optional[Device] = None,
    picture: Optional[PictureContext] = None,
    sketch: Optional[str] = None,
    can: Optional[Dict[str, Verdict]] = None,
    rig: bool = False,
) -> Ring:
    """Work out which options belong on the ring, and hand them back.

    ``part_category`` gives a part's category by its name, for the facets a piece is
    grouped by (``facets.py``): the registry's, unless told another.

    ``rig`` is whether the site has a lighting rig, whose window Panels › Site opens.

    ``device`` is what the page knows about the board under the ring: for a
    node ring, the board pinned to that node, if any; for a device ring, the
    board itself. ``picture`` is what it knows about pictures and cameras
    (``PictureContext``); without one, a host still offers Camera and Picture,
    with nothing pinned, drawn or listed. ``sketch`` is the sketch of a part of its
    own that no board connected runs, for a node ring: Flash its sketch. ``can``, on
    the canvas ring, is what the page knows would be refused now of Panels › Machine's
    acts -- the open Machine's port's answer for its heater loops (``tune.*``), the
    deck's for the knobs (``knobs.*``, ``here``) -- and greys each act it refuses, as
    ``device.can`` greys a board's; told nothing, nothing is.
    """
    picture = picture or PictureContext()
    category = part_category or _registered_category
    if context.pointing is Pointing.CANVAS:
        ring = _canvas_ring(context, site, site_names, category, picture, rig)
        if can is not None:
            judged(ring.options, {verb: Verdict.model_validate(v) for verb, v in can.items()})
        return ring
    if context.pointing is Pointing.NODE:
        return _node_ring(context, site, device, picture, sketch, category)
    if context.pointing is Pointing.DEVICE:
        return _device_ring_on_top(context, device)
    raise ValueError(f"no ring is built for {context.pointing!r}")


def _grouped(
    prefix: str,
    names: Sequence[str],
    action_of: Callable[[str], str],
    shown: Optional[Dict[str, str]] = None,
) -> Optional[Option]:
    """One option that opens a ring of names, or nothing when there are none.

    Each name is a leaf whose id and action are ``action_of(name)``, labelled
    so that no two read the same -- by what ``shown`` says of it, where it says
    anything. A list of things is not a list of verbs, so more than eight are cut
    into lettered runs (``_fit``) -- one more press, nothing hidden -- and more than
    eight runs of eight is refused.
    """
    ordered = list(names)
    if not ordered:
        return None
    shown = shown or {}
    said = distinct([shown.get(name, name) for name in ordered])
    leaves = [
        Option(id=action_of(name), label=label, action=action_of(name))
        for name, label in zip(ordered, said, strict=True)
    ]
    return Option(id=prefix, label=shorten(prefix), children=_fit(prefix, leaves))


def _letters(runs: Sequence[Sequence[str]]) -> List[str]:
    """Each run of a list sorted by name, named for its letters: its first entry's and its
    last's, as many as tell the runs apart (``a–k``, ``pa–pr``), one alone where the two
    share it. Where no such letters fit a label, each run is named for its first entry."""
    for count in range(1, (LONGEST_LABEL - 1) // 2 + 1):
        named = []
        for run in runs:
            first, last = run[0][:count].lower(), run[-1][:count].lower()
            named.append(first if first == last else f"{first}–{last}")
        if len(set(named)) == len(named):
            return named
    return distinct([run[0] for run in runs])


def _fit(
    prefix: str, options: Sequence[Option], room: int = MOST_OPTIONS, *, by_name: bool = True
) -> List[Option]:
    """A list in the ``room`` cells a ring has for it, every entry kept. It is as it is
    when it fits; else it is cut into as few runs as fit, of near-equal length and eight at
    most each, each a ring of its own. A list listed by name is sorted, and each run named
    for its letters (``_letters``); a list kept in its own order (the newest pictures first,
    a vocabulary's order) is cut in that order, and each run named for its first. More than
    ``room`` runs of eight is refused: it needs searching, not a bigger menu."""
    if len(options) <= room:
        return list(options)
    listed = sorted(options, key=lambda o: o.label.lower()) if by_name else list(options)
    count = -(-len(listed) // MOST_OPTIONS)
    if count > room:
        raise RingTooFull(
            f"{len(listed)} to choose between under {prefix!r}, and {room} runs of "
            f"{MOST_OPTIONS} hold {room * MOST_OPTIONS}. This needs searching, not a "
            "bigger menu."
        )
    each, over = divmod(len(listed), count)
    runs: List[List[Option]] = []
    for index in range(count):
        start = index * each + min(index, over)
        runs.append(listed[start : start + each + (1 if index < over else 0)])
    named = (
        _letters([[o.label for o in run] for run in runs])
        if by_name
        else distinct([run[0].label for run in runs])
    )
    return [
        Option(id=f"{prefix}:run{index}", label=name, children=run)
        for index, (name, run) in enumerate(zip(named, runs, strict=True))
    ]


# A site's pieces with no System, gathered when the Systems and their kinds would not fit
# one ring: each a part standing loose, grouped by its kind.
PARTS = "Parts"


def _by_facet(
    prefix: str,
    leaves: Sequence[Tuple[Option, Optional[str], Optional[str]]],
    room: int = MOST_OPTIONS,
) -> Optional[List[Option]]:
    """A long list of pieces cut by facet, ``leaves`` being each piece's option with its
    kind and its System: one ring per System its pieces are in, in the vocabulary's order,
    then one per kind of the pieces with no System; where those do not fit, or a kind is
    named as one of those Systems is (Machines), the kinds go under one ring more, Parts, so
    no two cells of a ring read the same. Each ring's id says its facet
    (``<prefix>:system:machines``, ``<prefix>:parts:kind:machines``), and its pieces are
    listed by name (``_fit``). None where the facet does not cut the list -- a piece in
    neither, every piece in one -- or where, folded, it still does not fit: the list is
    lettered then."""
    if any(kind is None and system is None for _, kind, system in leaves):
        return None
    systems = [s for s in SITE_SYSTEMS if any(system == s for _, _, system in leaves)]
    kinds = [k for k in KINDS if any(kind == k and system is None for _, kind, system in leaves)]
    if len(systems) + len(kinds) < 2:
        return None

    def ring(facet: str, value: str, members: Sequence[Option], at: str) -> Option:
        cut = f"{at}:{facet}:{value.lower().replace(' ', '-')}"
        return Option(id=cut, label=value, children=_fit(cut, members))

    def of_kind(kind: str) -> List[Option]:
        return [o for o, k, system in leaves if system is None and k == kind]

    by_system = [
        ring(SYSTEM, s, [o for o, _, system in leaves if system == s], prefix) for s in systems
    ]
    named_alike = set(systems) & set(kinds)
    if not named_alike and len(systems) + len(kinds) <= room:
        return [*by_system, *(ring(KIND, k, of_kind(k), prefix) for k in kinds)]
    if len(systems) + 1 > room:
        return None
    parts = f"{prefix}:parts"
    return [
        *by_system,
        Option(id=parts, label=PARTS, children=[ring(KIND, k, of_kind(k), parts) for k in kinds]),
    ]


def _registered_category(name: str) -> Optional[str]:
    """A registered part's category, by its name (``projects.registry.category_of``)."""
    return category_of(name, ROOT)


# What can be done to a saved variant: each its own cell, under the variant's name,
# Draw first.
VARIANT_VERBS = (
    ("draw", "Draw"),
    ("rename", "Rename"),
    ("duplicate", "Duplicate"),
    ("history", "History"),
    ("compare", "Compare"),
    ("delete", "Delete"),
)
# And to a deleted one, in the trash: back among the variants, or deleted for good.
TRASH_VERBS = (("restore", "Restore"), ("forget", "Forget"))


def _variants_group(names: Sequence[str], deleted: Sequence[str]) -> Optional[Option]:
    """Part › Variants: each saved variant a ring of what can be done to it -- Draw,
    Rename, Duplicate, History, Compare, Delete (``part:variant:<verb>:<name>``) --
    and, when anything is deleted, Deleted last: the trash, each deleted variant a
    ring of Restore and Forget (``part:trash:<verb>:<name>``), and Empty
    (``part:trash:empty``), which empties it once confirmed. Nothing saved and
    nothing deleted: no Variants. More than fit in one ring are grouped, as any
    list is."""

    def ring_of(prefix: str, verbs, name: str, label: str) -> Option:
        return Option(
            id=f"{prefix}:{name}",
            label=label,
            children=[
                Option(
                    id=f"{prefix}:{verb}:{name}",
                    label=said,
                    action=f"{prefix}:{verb}:{name}",
                    twice=(prefix, verb) == ("part:trash", "forget"),
                )
                for verb, said in verbs
            ],
        )

    def rings(prefix: str, verbs, members: Sequence[str], room: int) -> List[Option]:
        made = [
            ring_of(prefix, verbs, name, label)
            for name, label in zip(members, distinct(members), strict=True)
        ]
        return _fit(prefix, made, room)

    trash: Optional[Option] = None
    if deleted:
        kept = rings("part:trash", TRASH_VERBS, deleted, MOST_OPTIONS - 1)
        kept.append(
            Option(
                id="part:trash:empty",
                label="Empty",
                action="part:trash:empty",
                destructive=True,
                twice=True,
            )
        )
        trash = Option(id="part:trash", label="Deleted", children=kept)
    if not names and trash is None:
        return None
    children = rings("part:variant", VARIANT_VERBS, names, MOST_OPTIONS - (1 if trash else 0))
    if trash is not None:
        children.append(trash)
    return Option(id="part:variants", label="Variants", children=children)


def _pieces(
    prefix: str,
    parent: str,
    node: Optional[Assembly],
    faceted: Optional[Dict[str, Tuple[Optional[str], Optional[str]]]] = None,
    *,
    names: Optional[Sequence[str]] = None,
    room: int = MOST_OPTIONS,
) -> List[Option]:
    """The pieces directly inside a node, or those of them ``names`` says, by name, each
    ``select:<its dotted path>``, in the ``room`` cells a ring has for them. More than fit
    are cut by facet -- ``faceted`` being each piece's kind and System by its path
    (``_by_facet``) -- else into lettered runs (``_fit``)."""
    if names is None:
        names = sorted({child.name for child in node.children}) if node is not None else []

    def path(name: str) -> str:
        return f"{parent}.{name}" if parent else name

    leaves = [
        Option(id=f"select:{path(n)}", label=label, action=f"select:{path(n)}")
        for n, label in zip(names, distinct(list(names)), strict=True)
    ]
    cut = None
    if len(leaves) > room and faceted is not None:
        cut = _by_facet(
            prefix,
            [
                (leaf, *faceted.get(path(n), (None, None)))
                for leaf, n in zip(leaves, names, strict=True)
            ],
            room,
        )
    return cut or _fit(prefix, leaves, room)


# The panels the world's page registers, in the order the ring seats them
# (cardinals first): what stands in front of the world, each a cell away.
# The page registers exactly these; a test holds the two lists to each other.
PANELS: Sequence[Tuple[str, str]] = (
    # Site: the site's chips and its Contents tree.
    ("site", "Site"),
    ("selected", "Selected"),
    # Site's own windows, tabs beside Site, each a cell of Panels › Site: the site's
    # problems (the header's count opens them), every site's pins (Pinned), each
    # taken back from its row, the site's jobs, each row opening its machine, and
    # its generated SCAD.
    ("problems", "Problems"),
    ("pinned", "Pinned"),
    ("jobs", "Jobs"),
    ("scad", "SCAD"),
    # Layers: how deep a click reaches and which layers are drawn and selectable
    # (widgets/layers.js), a window beside the world registered by the page's script
    # and closed until asked for. View › Layers opens it too.
    ("layers", "Layers"),
    # Workspace: the site as every kind of evidence has it (apothecary/evidence/),
    # a tab of Site's ring registered by the page's script, closed until asked for;
    # a printer's ring opens it on that printer.
    ("working", "Workspace"),
    # Procedure: the steps that bring a site into working order, each fired through the
    # family's hub on GO, a tab of Site's ring registered by the page's script.
    ("procedure", "Procedure"),
    # Registered by the page's script rather than marked in its markup: Pictures
    # (every picture under the picture root, each pinned here or forgotten), Models
    # (image models through qmcp asked about the shape chosen on a mat, closed until
    # asked for, its verbs a ring of their own under its cell: _models) and Gather
    # (the gathering, a window beside it, closed until asked for), a ring of their
    # own under Pictures' cell, at start; a board's Machine, its log in it, when a
    # board is opened.
    ("pictures", "Pictures"),
    ("models", "Models"),
    ("gather", "Gather"),
    # Marks: a whiteboard's marks sorted, and a person's word on any (widgets/marks.js),
    # a stack beside the world registered at start and closed until asked for. Its verbs
    # are a ring of their own under its cell (_marks), seated last under Pictures.
    ("marks", "Marks"),
    ("machine", "Machine"),
    # The Bench: the toolchain, the sketches, compile and upload, raw flash and
    # the task log, a tab beside Pictures, registered at start and shown when
    # asked for. Its verbs are a ring of
    # their own under its cell (_bench).
    ("bench", "Bench"),
    # Settings: every shortcut and navigation setting, kept per browser, a tab
    # beside Pictures registered at start. Its cell is View's (View › Settings),
    # as ⚙ View › Settings opens it, not one of Panels'.
    ("settings", "Settings"),
    # The Airgap: the airgap part as a field, torque and dynamics model, a tab
    # beside Pictures registered at start and shown when asked for; it follows the
    # part's text while the part is edited. Its verbs are a ring of their own under
    # its cell (_airgap), seated last.
    ("airgap", "Airgap"),
    # The Deck: the Stream Deck + as apothecary has drawn it and what it has heard
    # (widgets/deck.js), a stack beside the world registered at start and closed until
    # asked for; the Stream Deck + piece's Open Deck opens it too.
    ("deck", "Deck"),
    # Loops: the heater loops of the printer whose Machine is open (widgets/loops.js), a
    # window of the Machine's group registered at start and closed until asked for. Its
    # acts are a ring of their own under Panels › Machine (_loops).
    ("loops", "Loops"),
    # Motion: the selected part's pieces moved through its motion (widgets/motion.js), a
    # window in the column registered at start and closed until asked for: Panels ›
    # Part's, beside Selected, and the part's own Part › View › Motion, on a part whose
    # pieces move.
    ("motion", "Motion"),
    # Lighting: a rig's legend and its console's levels (static/lighting.js), registered
    # while the site has a rig: Panels › Site's, greyed on a site without one.
    ("lighting", "Lighting"),
)
# The group each panel's window is registered under, as the page registers it (its
# markup's data-group, its script's `group:`, a system's entry): a panel's cell wears
# its group's colour. tests/test_group_colours.py holds this to the page.
PANEL_GROUPS = {
    "site": "Site",
    "problems": "Site",
    "pinned": "Site",
    "jobs": "Site",
    "scad": "Site",
    "layers": "Site",
    "working": "Site",
    "lighting": "Site",
    "procedure": "Family",
    "selected": "Part",
    "pictures": "Pictures",
    "models": "Pictures",
    "gather": "Pictures",
    "marks": "Pictures",
    "machine": "Machine",
    "bench": "Tools",
    "settings": "Tools",
    "deck": "Tools",
    "airgap": "Airgap",
    "loops": "Machine",
    "motion": "Part",
}
# What a person may say a whiteboard's mark is (apothecary/vision/marks.py's Kind).
MARK_KINDS = ("diagram", "writing", "unsure", "nothing")
# The views: each focused system's windows laid out together (systems.py), then each
# journey's that has a cell (journeys.py: the ring is full, so the first's alone), a cell
# of Panels › Windows after the layout's own two and an entry of the header's ⊞ Windows. The page defines each from the same entry; a view's
# windows the page has not got are left out of it.
VIEWS = tuple((system.id, system.cell) for system in SYSTEMS) + tuple(
    (journey.id, journey.cell) for journey in JOURNEYS if journey.cell
)
JOURNEY_IDS = frozenset(journey.id for journey in JOURNEYS)
# Panels is one cell per group of windows, each a ring of its group's windows and their
# verbs: Site 8, Part 6, Pictures 2, Machine 4, then the layout's own Windows 9, Tools 3,
# Family 1 and Airgap 7. These four come before Windows.
_BEFORE_WINDOWS = ("site", "part", "pictures", "machine")
_RINGS = {
    "site": ("site", "problems", "pinned", "jobs", "scad", "working", "lighting", "layers"),
    # Models before Gather, so Models keeps its address when Gather goes
    # (docs/plans/ui-coordination-2026-10-31.md).
    # Marks last, so Models and Gather keep their addresses.
    "pictures": ("pictures", "models", "gather", "marks"),
}


def _panels(rig: bool = False) -> Option:
    """Panels, cell 4 of the canvas ring: one cell per group of windows, each a ring of its
    group's windows, each a toggle, and their verbs, wearing the group's colour. ``rig``:
    the site has a lighting rig, whose window is Site's; without one its cell is greyed."""

    def toggle(pid: str, label: str) -> Option:
        return Option(
            id=f"panel:{pid}",
            label=label,
            group=PANEL_GROUPS.get(pid),
            action=f"panel:toggle:{pid}",
        )

    labels = dict(PANELS)

    def lighting() -> Option:
        cell = toggle("lighting", labels["lighting"])
        if not rig:
            cell.enabled = False
            cell.why = "this site has no lighting rig"
        return cell

    def of_site(each: str) -> Option:
        if each == "lighting":
            return lighting()
        return toggle(each, labels[each])

    def of_pictures(each: str) -> Option:
        if each == "models":
            return _models(toggle(each, labels[each]))
        if each == "marks":
            return _marks(toggle(each, labels[each]))
        return toggle(each, labels[each])

    family = by_id("family")
    cells = {
        "site": Option(
            id="panels:site",
            label="Site",
            group="Site",
            children=[of_site(each) for each in _RINGS["site"]],
        ),
        # Part: Selected, the Part system's main window, and Motion; the part's own
        # sections are its ring's (Part › Edit, View, History, Variants).
        "part": Option(
            id="panels:part",
            label="Part",
            group="Part",
            children=[toggle("selected", labels["selected"]), toggle("motion", labels["motion"])],
        ),
        "pictures": Option(
            id="panels:pictures",
            label="Pictures",
            group="Pictures",
            children=[of_pictures(each) for each in _RINGS["pictures"]],
        ),
        # A board's Machine, and an armed printer's control pad in a loud window of its own
        # or put back in its Machine, as the pad's ⧉ Pop out and ⇥ Put back do
        # (widgets/machine.js); then the heater loops of the printer whose Machine is open.
        "machine": Option(
            id="panels:machine",
            label="Machine",
            group="Machine",
            children=[
                toggle("machine", labels["machine"]),
                Option(id="panel:pad", label="Control pad", action="panel:pad"),
                _loops(toggle("loops", labels["loops"])),
            ],
        ),
    }
    windows = Option(
        id="panel:windows",
        label="Windows",
        # The layout itself: the world alone (its window maximised) and every window
        # back, as the tilde key does; the page's own layout again, whatever was dragged,
        # split or closed; each view; and the Tour, after the views, so no cell before it
        # moves: its box over the page and its verbs.
        children=[
            Option(id="panel:world", label="World alone", action="panel:world:toggle"),
            Option(id="panel:layout:reset", label="Reset layout", action="panel:layout:reset"),
            *(
                Option(
                    id=f"panel:view:{vid}",
                    label=label,
                    group=(journey_by_id(vid) if vid in JOURNEY_IDS else by_id(vid)).group,
                    action=f"panel:view:{vid}",
                )
                for vid, label in VIEWS
            ),
            _tour(),
        ],
    )
    # Tools: the Bench and its verbs, Settings (View › Settings opens it too), the Deck
    # with the Stream Deck +'s knobs, and the documentation and the walkthrough in a tab of
    # the browser's own, as the header's Docs opens them.
    tools = Option(
        id="panels:tools",
        label="Tools",
        group="Tools",
        children=[
            _bench(toggle("bench", labels["bench"])),
            toggle("settings", labels["settings"]),
            _deck(toggle("deck", labels["deck"])),
            Option(id="panel:docs", label="Docs", action="panel:docs"),
        ],
    )
    # Family: the Procedure and its verbs, then the family system's sections (systems.py).
    family_cell = Option(
        id="panels:family",
        label="Family",
        group="Family",
        children=[
            _procedure(toggle("procedure", labels["procedure"])),
            *(
                Option(
                    id=f"panel:{family.id}-{section.id}",
                    label=section.title,
                    group=family.group,
                    action=f"panel:toggle:{family.id}-{section.id}",
                )
                for section in family.sections
            ),
        ],
    )
    return Option(
        id="panels",
        label="Panels",
        children=[
            *(cells[pid] for pid in _BEFORE_WINDOWS),
            windows,
            tools,
            family_cell,
            # The Airgap, a group of its own: the panel and its verbs. The eighth cell.
            _airgap(toggle("airgap", labels["airgap"])),
        ],
    )


def _view(
    site: Optional[Assembly] = None,
    part_category: Callable[[str], Optional[str]] = lambda _: None,
    under: str = "",
) -> Option:
    """View, cell 2 of the canvas ring: how the world is drawn.

    Its cells are the header's ⚙ View menu's items. Fit, first, frames the pieces
    at this level. Snap to grid snaps a dragged piece to the grid;
    Detail draws every subassembly in full, as a black box or as a dot; Outlines
    draws each subassembly's extent; Select walls (the menu's "Walls selectable")
    lets a click in the world pick a wall, which it otherwise passes through, for
    the page's session. Snap, Outlines and Select walls each turn what they name the
    other way, as their tick-boxes do, and the status line says which way it went;
    the ring is not told how they stand. Settings opens the Settings panel --
    the shortcuts and automatic zoom -- as the menu's Settings does, so no cell
    before it moves. Layers and Depth come after it, in the two cells left: Layers is
    a ring of the layers of what lies beneath the level in view (``under``), each a ring
    of its own acts (``_layers``), and Depth
    is how many levels below this one a click reaches and the world draws, one to four
    by name and one more or less, as the Layers window's stepper (to eight). Select
    walls is the wall layer's Selectable tick.
    """
    return Option(
        id="view",
        label="View",
        children=[
            Option(id="fit", label="Fit", action="fit"),
            Option(id="view:snap", label="Snap to grid", action="view:snap"),
            Option(
                id="view:detail",
                label="Detail",
                children=[
                    Option(id="view:detail:full", label="Full", action="view:detail:full"),
                    Option(id="view:detail:box", label="Black box", action="view:detail:box"),
                    Option(id="view:detail:dot", label="Dot", action="view:detail:dot"),
                ],
            ),
            Option(id="view:outlines", label="Outlines", action="view:outlines"),
            Option(id="view:walls", label="Select walls", action="view:walls"),
            Option(id="view:settings", label="Settings", action="view:settings"),
            # After Settings, which keeps its cell: the two cells still free.
            _layers(site, part_category, under),
            Option(
                id="view:depth",
                label="Depth",
                children=[
                    Option(
                        id=f"view:depth:{n}",
                        label=f"{n} level{'' if n == 1 else 's'}",
                        action=f"view:depth:{n}",
                    )
                    for n in range(1, 5)
                ]
                # The Layers window's stepper: a level more or less, up to eight.
                + [
                    Option(id="view:depth:less", label="One less", action="view:depth:less"),
                    Option(id="view:depth:more", label="One more", action="view:depth:more"),
                ],
            ),
        ],
    )


# The world's own layers, and the words their cells say. The grid, the machines'
# buttons and their bed readings are a set of their own, among which Only this and All
# act; the measurement is a mode, so it is only ever shown or not. The bed mesh comes
# last, so the cells before it keep theirs.
WORLD_LAYERS: Tuple[Tuple[str, str], ...] = (
    (GRID, "Grid"),
    (MACHINE_BUTTONS, "Buttons"),
    (MEASURE, "Measure"),
    (BED_MESH, "Bed mesh"),
)


def _layer_ring(layer: str, label: str) -> Option:
    """One layer's ring, in its colour: Shown, then Selectable where a click can pick
    what it draws (a shell's, a System's, a category's), then Only this and All -- this
    layer shown and the others of its set hidden, and every one of its set shown -- where
    it has a set (not the measurement): the shells, the pieces' layers, or the grid, the
    buttons and the bed mesh. Each does what its row of the Layers window does, or the same over its
    set (``layer:<verb>:<layer>``, the page's)."""
    colour = colour_of(layer)

    def act(verb: str, said: str) -> Option:
        return Option(
            id=f"layer:{verb}:{layer}", label=said, action=f"layer:{verb}:{layer}", colour=colour
        )

    acts = [act("shown", "Shown")]
    if layer.startswith((SHELL, SYSTEM_LAYER, CATEGORY)):
        acts.append(act("selectable", "Selectable"))
    if layer != MEASURE:
        acts += [act("only", "Only this"), act("all", "All")]
    return Option(id=f"layer:{layer}", label=label, colour=colour, children=acts)


def _in_order(prefix: str, label: str, rings: Sequence[Option]) -> Option:
    """A ring of rings, in the order given, cut in that order where they do not fit
    (``_fit``)."""
    return Option(id=prefix, label=label, children=_fit(prefix, rings, by_name=False))


def _kind_ring(kind: Dict[str, object]) -> Option:
    """A Kind's ring, in its colour: Shown and Selectable over every one of its categories
    at once, as its heading's ticks in the Layers window, then each category's ring
    (``_layer_ring``)."""
    layer, colour = str(kind["layer"]), str(kind["colour"])
    acts = [
        Option(
            id=f"layer:{verb}:{layer}", label=said, action=f"layer:{verb}:{layer}", colour=colour
        )
        for verb, said in (("shown", "Shown"), ("selectable", "Selectable"))
    ]
    words = [str(word["word"]) for word in kind["words"]]  # type: ignore[union-attr]
    rings = [
        _layer_ring(f"{CATEGORY}{word}", said)
        for word, said in zip(words, distinct(words), strict=True)
    ]
    return Option(
        id=f"layer:{layer}",
        label=str(kind["name"]),
        colour=colour,
        children=acts + _fit(f"layer:{layer}:in", rings, MOST_OPTIONS - len(acts), by_name=False),
    )


# What View › Layers names the layers of a level's pieces by, as the Layers window does.
LAYERS_SYSTEMS, LAYERS_KINDS, LAYERS_WORDS = "Systems", "Kinds", "Words"


def _layers(
    site: Optional[Assembly],
    part_category: Callable[[str], Optional[str]] = lambda _: None,
    under: str = "",
) -> Option:
    """View › Layers: the Layers window, the world's own layers, Reset (depth 1, every
    layer shown and selectable but walls, as the window's Reset), then the layers that
    come and go with what lies beneath the level in view, as the window lists them: the
    site's shells, then, as ``facets.facets_of`` lists them, its Systems, each a ring of
    its acts (``_layer_ring``); its Kinds, each a ring of its categories
    (``_kind_ring``); and the words neither holds. A layer's drawn ring in the world
    opens the ring of its acts here."""
    shells = shells_in(site) if site is not None else []
    children = [
        Option(id="view:layers:window", label="Window", action="view:layers"),
        Option(
            id="layers:world",
            label="World",
            children=[_layer_ring(layer, said) for layer, said in WORLD_LAYERS],
        ),
        Option(id="layer:reset", label="Reset", action="layer:reset"),
    ]
    if shells:
        children.append(
            _in_order(
                "layers:shells",
                "Shells",
                [_layer_ring(f"{SHELL}{n}", f"Shell {n}") for n in shells],
            )
        )
    sent = facets_of(site, part_category, under) if site is not None else None
    if sent is None:
        return Option(id="view:layers", label="Layers", children=children)
    by_kind = sent["by"] == KIND
    systems = [] if by_kind else list(sent["values"])  # type: ignore[arg-type]
    kinds = list(sent["values"] if by_kind else sent["kinds"])  # type: ignore[arg-type]
    if systems:
        children.append(
            _in_order(
                "layers:systems",
                LAYERS_SYSTEMS,
                [_layer_ring(str(value["layer"]), str(value["name"])) for value in systems],
            )
        )
    if kinds:
        children.append(
            _in_order("layers:kinds", LAYERS_KINDS, [_kind_ring(kind) for kind in kinds])
        )
    loose = [str(w["word"]) for w in sent["loose"]]  # type: ignore[index]
    if loose:
        children.append(
            _in_order(
                "layers:words",
                LAYERS_WORDS,
                [
                    _layer_ring(f"{CATEGORY}{word}", said)
                    for word, said in zip(loose, distinct(loose), strict=True)
                ],
            )
        )
    return Option(id="view:layers", label="Layers", children=children)


# The colours a lead, a plug or a part most often is, each a cell of Models › Colour;
# the rest of the basic colour words under More.
COMMON_COLOURS = ("black", "white", "grey", "red", "yellow", "green", "blue")


def _colours(words: Sequence[str]) -> List[Option]:
    """Models › Colour: the common colours a cell each, the rest under More, so no
    word sits under another's name."""

    def say(word: str) -> Option:
        return Option(
            id=f"models:say:colour:{word}", label=word, action=f"models:say:colour:{word}"
        )

    rest = [w for w in words if w not in COMMON_COLOURS]
    cells = [say(w) for w in COMMON_COLOURS if w in words]
    if rest:
        cells.append(Option(id="models:colour:more", label="More", children=[say(w) for w in rest]))
    return cells


def _procedure(toggle: Option) -> Option:
    """Panels › Family › Procedure: the window, then its verbs, which the page hands to it
    (widgets/procedure.js). Seated after the window's own cell."""
    return Option(
        id="panels:procedure",
        label="Procedure",
        children=[
            toggle,
            Option(id="procedure:go", label="GO", action="procedure:go"),
            Option(id="procedure:again", label="Start over", action="procedure:again"),
        ],
    )


def _deck(toggle: Option) -> Option:
    """Panels › Tools › Deck: the Deck window, then the Stream Deck +'s knobs, the server's
    layout on the deck (firmware/deck_control.py), which the page hands each verb to -- on
    or off, the machine they move, their step, and the machine of the Machine that is open
    -- and the screen the deck's strip shows."""
    from .firmware.deck_control import MACHINES, STEPS_MM

    return Option(
        id="panels:deck",
        label="Deck",
        group="Tools",
        children=[
            toggle,
            Option(id="deck:knobs", label="On / off", action="deck:knobs"),
            Option(
                id="deck:machine",
                label="Machine",
                children=[
                    Option(
                        id=f"deck:machine:{machine.name}",
                        label=shorten(machine.name),
                        action=f"deck:machine:{machine.name}",
                    )
                    for machine in MACHINES
                ],
            ),
            Option(
                id="deck:step",
                label="Step",
                children=[
                    Option(id=f"deck:step:{mm:g}", label=f"{mm:g} mm", action=f"deck:step:{mm:g}")
                    for mm in STEPS_MM
                ],
            ),
            Option(id="deck:here", label="Here", action="deck:here"),
            # The strip's screen, by its name or a step either way as a swipe along the
            # strip takes it (firmware/deck_screens.py).
            Option(
                id="deck:screen",
                label="Screen",
                children=[
                    Option(id=f"deck:screen:{name}", label=label, action=f"deck:screen:{name}")
                    for name, label in SCREEN_CELLS
                ],
            ),
        ],
    )


# The cells of Deck › Screen: each screen of the strip in its order, then a step back and on.
SCREEN_CELLS = (
    ("knobs", "Knobs"),
    ("progress", "Progress"),
    ("status", "Status"),
    ("previous", "Back"),
    ("next", "Next"),
)

# What a rule's cell says, where its title is longer than a cell holds; a rule this does
# not name is called by its title, shortened.
RULE_LABELS = {
    "zn_ultimate": "ZN ultimate",
    "zn_reaction": "ZN reaction",
    "tyreus_luyben": "Tyreus",
    "cohen_coon": "Cohen-Coon",
    "simc": "SIMC",
    "imc": "IMC",
    "amigo": "AMIGO",
}


def _loops(toggle: Option) -> Option:
    """Panels › Machine › Loops: the window, then the acts of the loop it shows, which the
    page hands to it (widgets/loops.js), on the printer whose Machine is open -- the board's
    gains read, an experiment started and cancelled, the designed gains set on the board
    (never saved to its memory: no cell asks for that) -- and the choices it makes: which
    loop, which experiment (``firmware.loops.KINDS``), and the rule and the kind of
    controller a design is made by (``control_loops.RULES``, each rule a ring of the kinds it
    gives). Seated after Knobs, so no cell of the Machine's moves."""
    from .control_loops import RULES
    from .firmware.loops import KINDS

    def act(verb: str, label: str) -> Option:
        return Option(id=f"loops:{verb}", label=label, action=f"loops:{verb}")

    return Option(
        id="panels:loops",
        label="Loops",
        group=PANEL_GROUPS["loops"],
        children=[
            toggle,
            act("read", "Read"),
            act("start", "Start"),
            act("cancel", "Cancel"),
            act("set", "Set gains"),
            Option(
                id="loops:loop",
                label="Loop",
                children=[act("loop:hotend", "Hotend 0"), act("loop:bed", "Bed")],
            ),
            Option(
                id="loops:kind",
                label="Experiment",
                children=[act(f"kind:{k.name}", k.name.capitalize()) for k in KINDS],
            ),
            Option(
                id="loops:rule",
                label="Rule",
                children=[
                    Option(
                        id=f"loops:rule:{rule.name}",
                        label=RULE_LABELS.get(rule.name) or shorten(rule.title),
                        children=[
                            act(f"rule:{rule.name}:{kind}", kind.upper()) for kind in rule.kinds
                        ],
                    )
                    for rule in RULES.values()
                ],
            ),
        ],
    )


def _models(toggle: Option) -> Option:
    """Panels › Pictures › Models: the window, then its verbs, which the page hands to it
    (widgets/models.js): Ask about the shape chosen on a mat, and a person's word on its
    colour or its material, each a word of the family's lists. Seated after the
    window's own cell, so no address moves."""
    from .evidence.words import COLOURS, MATERIALS

    return Option(
        id="panels:models",
        label="Models",
        children=[
            toggle,
            Option(id="models:ask", label="Ask", action="models:ask"),
            Option(
                id="models:colour",
                label="Colour",
                children=_colours(COLOURS),
            ),
            Option(
                id="models:material",
                label="Material",
                children=_listed(
                    "models:material", [(f"models:say:material:{w}", w) for w in MATERIALS]
                ),
            ),
        ],
    )


def _tour() -> Option:
    """Panels › Windows › Tour: the tour's box over the page, then its buttons, which
    the page hands to it (widgets/tour_popover.js): Back and Next through the journeys'
    stages, Works and Off saying how the stage is (Off with what the box's field says
    is off), Take me here, which takes the page to the stage, Its page, the first
    walkthrough page the stage names, in a tab of its own, and Who, the field for the
    name a word is kept under."""
    return Option(
        id="panels:tour",
        label="Tour",
        group="Tools",
        children=[
            Option(id="tour:toggle", label="Tour", action="tour:toggle"),
            Option(id="tour:back", label="Back", action="tour:back"),
            Option(id="tour:works", label="Works", action="tour:works"),
            Option(id="tour:off", label="Off", action="tour:off"),
            Option(id="tour:next", label="Next", action="tour:next"),
            Option(id="tour:page", label="Its page", action="tour:page"),
            Option(id="tour:put", label="Take me here", action="tour:put"),
            Option(id="tour:by", label="Who", action="tour:by"),
        ],
    )


def _marks(toggle: Option) -> Option:
    """Panels › Pictures › Marks: the window, then a person's word on the mark chosen
    in it, which the page hands to it (widgets/marks.js): a diagram's, writing, unsure,
    or nothing; then a whiteboard's history, Earlier and Later stepping its slider to
    the event before or after, and Place placing the moment at the selected place.
    Seated after the window's own cell, the history's after the kinds."""
    return Option(
        id="panels:marks",
        label="Marks",
        group=PANEL_GROUPS["marks"],
        children=[
            toggle,
            *(
                Option(id=f"marks:say:{kind}", label=kind.capitalize(), action=f"marks:say:{kind}")
                for kind in MARK_KINDS
            ),
            Option(id="marks:earlier", label="Earlier", action="marks:earlier"),
            Option(id="marks:later", label="Later", action="marks:later"),
            Option(id="marks:place", label="Place", action="marks:place"),
        ],
    )


def _airgap(show: Option) -> Option:
    """The Airgap's cell under Panels: the panel itself first, then its verbs.

    Each verb acts on the panel as its buttons do, where it has one: Play spins the
    rotor or plays the run and pauses it; Sweep maps the metric the panel's sweep
    line names over the two ranges it names. The rest have no button: To editor
    writes the panel's values into the airgap part's text in the SCAD editor (the
    text is the truth, so the panel then follows the text), From editor reads that
    text again (the part's own file while it is not being edited), Copy SCAD copies
    the part's text with the panel's values written in, Copy metrics copies the
    metrics document (airgap/metrics/1), and Reset puts the panel back on the
    part's own text with its rig and sweep as they start.
    """
    return Option(
        id="airgap",
        label="Airgap",
        group="Airgap",
        children=[
            show,
            Option(id="airgap:play", label="Play", action="airgap:play"),
            Option(id="airgap:sweep", label="Sweep", action="airgap:sweep"),
            Option(id="airgap:to-editor", label="To editor", action="airgap:to-editor"),
            Option(id="airgap:from-editor", label="From editor", action="airgap:from-editor"),
            Option(id="airgap:copy-scad", label="Copy SCAD", action="airgap:copy-scad"),
            Option(id="airgap:copy-metrics", label="Copy metrics", action="airgap:copy-metrics"),
            Option(id="airgap:reset", label="Reset", action="airgap:reset"),
        ],
    )


def _motion() -> Option:
    """Part › View › Motion: the Motion window opened on the part, then its controls,
    which the page hands to it (widgets/motion.js): Play plays the motion and pauses
    it, Back and Step move it a sample of its table at a time, Reset puts it back at
    the start of its range, Bought shows or hides what is bought (pins, inserts) in its
    own colour."""
    return Option(
        id="part:motion",
        label="Motion",
        children=[
            Option(id="part:motion:open", label="Motion", action="part:motion:open"),
            Option(id="part:motion:play", label="Play", action="part:motion:play"),
            Option(id="part:motion:back", label="Back", action="part:motion:back"),
            Option(id="part:motion:step", label="Step", action="part:motion:step"),
            Option(id="part:motion:reset", label="Reset", action="part:motion:reset"),
            Option(id="part:motion:bought", label="Bought", action="part:motion:bought"),
        ],
    )


def _feedback() -> Option:
    """Part › View › Feedback: the part's cabinet in Part › Feedback, a drawer for each
    piece made of it (apothecary/cabinet.py), then what is done to the piece chosen there
    (widgets/feedback.js): Measure files what is read or seen, Note a note, and Take turn
    and Undo turn the turn it makes in its printer's next slices."""
    return Option(
        id="feedback",
        label="Feedback",
        children=[
            Option(id="feedback:open", label="Feedback", action="feedback:open"),
            Option(id="feedback:measure", label="Measure", action="feedback:measure"),
            Option(id="feedback:note", label="Note", action="feedback:note"),
            Option(id="feedback:tune-apply", label="Take turn", action="feedback:tune-apply"),
            Option(id="feedback:tune-undo", label="Undo turn", action="feedback:tune-undo"),
        ],
    )


def _bench(show: Option) -> Option:
    """The Bench's cell under Panels: the panel itself first, then its verbs.

    Each verb is the Bench's button of the same name and acts on what the Bench has
    chosen -- the sketch, the board (FQBN) and the port in its boxes, the images in its
    raw-flash list, the libraries typed in its box -- as Control › Print › Send file
    prints what the Print card has chosen. Install is a ring of the toolchain modules,
    drawn from their registry (firmware/modules): Arduino installs or updates
    arduino-cli, Rust ESP32 fetches Rust for the ESP32, and a module added later is a
    cell of it with no change here; Cores installs one of the suggested cores; Cancel
    stops the running task. Upload and Raw flash overwrite what a board runs. The
    slicer's modules follow the toolchain modules in Install, from their own registry
    (apothecary/slicer/modules): OrcaSlicer installs the pinned release, as the Bench's
    toolchain card's button for it does; appended, so no cell before it moves.
    """
    from .firmware.modules import modules
    from .firmware.toolchains import SUGGESTED_CORES
    from .slicer.modules import modules as slicers

    return Option(
        id="bench",
        group="Tools",
        label="Bench",
        children=[
            show,
            Option(
                id="bench:install",
                label="Install",
                children=[
                    Option(
                        id=f"bench:install:{module.id}",
                        label=shorten(module.ring_label),
                        action=f"bench:install:{module.id}",
                    )
                    for module in modules()
                ]
                + [
                    Option(
                        id=f"bench:install:slicer:{slicer.id}",
                        label=shorten(slicer.label),
                        action=f"bench:install:slicer:{slicer.id}",
                    )
                    for slicer in slicers()
                ],
            ),
            Option(id="bench:compile", label="Compile", action="bench:compile"),
            Option(id="bench:upload", label="Upload", action="bench:upload", destructive=True),
            Option(id="bench:esptool", label="Raw flash", action="bench:esptool", destructive=True),
            Option(id="bench:cancel", label="Cancel", action="bench:cancel"),
            Option(
                id="bench:cores",
                label="Cores",
                # A core by its architecture: AVR, ESP32, RP2040 ...
                children=[
                    Option(
                        id=f"bench:core:{core}",
                        label=shorten(core.rsplit(":", 1)[-1].upper()),
                        action=f"bench:core:{core}",
                    )
                    for core, _ in SUGGESTED_CORES
                ],
            ),
            Option(id="bench:libraries", label="Libraries", action="bench:libraries"),
        ],
    )


# --- pictures and cameras -------------------------------------------------------------
#
# A picture is pinned at a *host* -- a root structure with a footprint that is
# neither a made piece nor a camera -- or at the site's floor, and a camera is
# added above one. A host's node ring appends Camera (Add here) and Picture; the
# floor's are reached from the canvas ring's Pictures › Floor, since the floor
# is a selection but not a node. A floor verb carries the floor in its action,
# as ``@floor`` after its last colon; a host's verb names its host by the ring's
# target. A verb about one view names the view, which knows its own host. A
# camera is a part, and its verbs are its own node ring's, naming it by the
# ring's target.

FLOOR_MARK = "@floor"
# A list of pictures or views shows the seven newest; the eighth cell acts on
# the one chosen in the panel that holds the rest, or opens that panel.
NEWEST = MOST_OPTIONS - 1
# Folder's eighth cell, for a picture chosen in Pictures older than the seven:
# the verb, then as much of its name as the label has room for.
PIN_CHOSEN = "Pin "


def _listed(
    group_id: str,
    leaves: Sequence[Tuple[str, str]],
    *,
    first: Sequence[Option] = (),
) -> List[Option]:
    """Options ``first``, then one leaf per ``(action, name)``, labelled so no two
    read the same, in the order given; cut in that order, each run named for its
    first, when they do not fit beside ``first`` in one ring (``_fit``)."""
    labels = distinct([name for _, name in leaves])
    made = [
        Option(id=action, label=label, action=action)
        for (action, _), label in zip(leaves, labels, strict=True)
    ]
    return [*first, *_fit(group_id, made, MOST_OPTIONS - len(first), by_name=False)]


def _stem(path: str) -> str:
    """A picture's name without its folder or its suffix, for a label."""
    name = path.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[0] if "." in name else name


def _is_host(site: Optional[Assembly], path: str, not_hosts: Sequence[str]) -> bool:
    """A root structure with a footprint that is neither a made piece nor a camera
    (``not_hosts``)."""
    if site is None or not path or "." in path or path in not_hosts:
        return False
    node = next((c for c in site.children if c.name == path), None)
    return node is not None and node.world_bounds() is not None


def _camera_group(floor: bool, printer: bool = False, machine: bool = False) -> Option:
    """Camera at a host or the floor: Add here, a camera part standing above the
    middle of this place, looking straight down. The server adds it. On a printer a
    board drives, Workspace too: the Workspace opened on it, where the frames its
    cameras keep with its polls are (widgets/working_space.js). On a machine -- a printer
    a board drives, or a router, planned or driven -- Projector last: the light that goes
    the other way from a camera's, the projector's page for this machine opened in a
    window of its own for a second display (routes/projector.py)."""
    tail = f":{FLOOR_MARK}" if floor else ""
    children = [
        Option(id=f"camera:add-here{tail}", label="Add here", action=f"camera:add-here{tail}")
    ]
    if printer:
        children.append(Option(id="working", label="Workspace", action="working:open"))
    if machine:
        children.append(Option(id="projector", label="Projector", action="projector:open"))
    return Option(id=f"camera{tail}", label="Camera", group="Pictures", children=children)


def _camera_options(picture: PictureContext) -> List[Option]:
    """A camera part's own verbs: Device › this browser's cameras (Allow until the
    browser has been asked; the camera's own device marked), Live or Still and
    Take picture -- only when its device is one of this browser's, since a device
    is one origin's -- and Remove. Take picture keeps a frame and makes it this
    camera's view, lying where the camera looks; Remove takes the camera away and
    leaves its pictures. The server removes it; the page does the rest."""
    here = picture.here
    mine = {c.id for c in picture.cameras}
    if picture.asked and picture.cameras:
        devices = _listed(
            "camera:device",
            [(f"camera:device:{c.id}", c.label or "camera") for c in picture.cameras],
        )
        if here.camera is not None:
            for leaf in [*devices, *(c for d in devices for c in d.children or [])]:
                if leaf.action == f"camera:device:{here.camera.id}":
                    leaf.marked = True
    else:
        devices = [Option(id="camera:allow", label="Allow", action="camera:allow")]
    options = [Option(id="camera:device", label="Device", children=devices)]
    if here.camera is not None and here.camera.id in mine:
        options.append(
            Option(id="camera:still", label="Still", action="camera:still")
            if here.live
            else Option(id="camera:live", label="Live", action="camera:live")
        )
        options.append(
            Option(id="camera:take-picture", label="Take picture", action="camera:take-picture")
        )
    options.append(
        Option(
            id="camera:remove", label="Remove", action="camera:remove", destructive=True, twice=True
        )
    )
    return options


def _picture_group(picture: PictureContext, floor: bool) -> Optional[Option]:
    """Picture at a host or the floor: Add (a host's; the floor's is Pictures ›
    Add), Folder › the seven newest pictures and, when there are more, Pin and
    the short name of the one chosen in Pictures when it is older than those,
    else More (the Pictures panel, where every picture is) -- the chosen one,
    among the seven, is marked in its own cell; and with a view drawn here, Size,
    Unpin, Forget for a picture the browser kept, Views › the newest views (once
    several are pinned here), Make › Make all and each found shape (once its shapes
    are found and it has a width), and Find shapes last: the step after a pin, with
    the finder that can read the picture (or Find shapes › each, when several
    can), and on a view already searched, Find shapes › the other finders. The
    cells a picture has from its pin on come first, so none moves as it is
    searched and sized, and Make takes the cell Find shapes had. Eight at the
    most."""
    tail = f":{FLOOR_MARK}" if floor else ""
    here = picture.here
    # The floor's Add is the canvas ring's Pictures › Add, one ring up: an action
    # has one address.
    options = [] if floor else [Option(id="picture:add", label="Add", action="picture:add")]

    pictures = list(picture.pictures)
    # A picture chosen in Pictures that is no longer there is not chosen.
    chosen = picture.chosen_picture if picture.chosen_picture in pictures else None
    if pictures:
        newest = pictures[:NEWEST]
        leaves = [(f"picture:pin:{p}{tail}", _stem(p)) for p in newest]
        if len(pictures) > NEWEST:
            if chosen is not None and chosen not in newest:
                short = shorten(_stem(chosen) or chosen, LONGEST_LABEL - len(PIN_CHOSEN))
                leaves.append((f"picture:pin:{chosen}{tail}", f"{PIN_CHOSEN}{short}"))
            else:
                leaves.append((f"picture:more{tail}", "More"))
        folder = _listed(f"picture:folder{tail}", leaves)
        if chosen in newest:
            for leaf in folder:
                if leaf.action == f"picture:pin:{chosen}{tail}":
                    leaf.marked = True
        options.append(Option(id=f"picture:folder{tail}", label="Folder", children=folder))

    drawn = next((vw for vw in here.views if vw.id == here.drawn), None)
    if drawn is None and here.views:
        drawn = here.views[0]
    if drawn is None:
        return (
            Option(id=f"picture{tail}", label="Picture", group="Pictures", children=options)
            if options
            else None
        )

    # The cells it always has first, so none moves as a picture goes from pinned to
    # found to sized: Size and Unpin, then Forget, which a kept picture has from its
    # pin on. Then Views, from a second view pinned here on, and Make, which comes
    # once its shapes are found and it has a width, in the cell Find shapes had.
    options.append(Option(id=f"picture:size{tail}", label="Size", action=f"picture:size{tail}"))
    options.append(Option(id=f"picture:unpin{tail}", label="Unpin", action=f"picture:unpin{tail}"))
    if drawn.kept:
        options.append(
            Option(
                id=f"picture:forget{tail}",
                label="Forget",
                action=f"picture:forget{tail}",
                destructive=True,
                twice=True,
            )
        )

    if len(here.views) > 1:
        leaves = [
            (f"picture:draw:{vw.id}", _stem(vw.picture) or vw.id) for vw in here.views[:NEWEST]
        ]
        if len(here.views) > NEWEST:
            chosen_view = next(
                (vw for vw in here.views[NEWEST:] if vw.id == here.chosen_view), None
            )
            leaves.append(
                (f"picture:draw:{chosen_view.id}", _stem(chosen_view.picture) or chosen_view.id)
                if chosen_view is not None
                else (f"picture:views{tail}", "In Selected")
            )
        options.append(
            Option(
                id=f"picture:views-group{tail}",
                label="Views",
                children=_listed(f"picture:views-group{tail}", leaves),
            )
        )

    found = [shape for shape in drawn.shapes if shape.status == "found"]
    if drawn.sized and found:
        make_all = Option(
            id=f"picture:make-all:{drawn.id}",
            label="Make all",
            action=f"picture:make-all:{drawn.id}",
        )
        options.append(
            Option(
                id=f"picture:make-group{tail}",
                label="Make",
                children=_listed(
                    f"picture:make-group{tail}",
                    [(f"picture:make:{drawn.id}:{s.index}", f"{s.word} {s.index}") for s in found],
                    first=[make_all],
                ),
            )
        )
    find = _find_shapes(drawn, picture.finders, tail)
    if find is not None:
        options.append(find)
    return Option(id=f"picture{tail}", label="Picture", group="Pictures", children=options)


def _find_shapes(drawn: ViewSeen, finders: Sequence[str], tail: str) -> Optional[Option]:
    """Find shapes on the drawn view: before it is searched, the one finder that can
    read its picture as a leaf, or each of several behind it; after, only the other
    finders, each making a view of its own; nothing when no finder has anything to
    do here."""
    offered = list(finders) if drawn.finder is None else [f for f in finders if f != drawn.finder]
    if not offered:
        return None
    if drawn.finder is None and len(offered) == 1:
        action = f"picture:find:{offered[0]}{tail}"
        return Option(id=action, label="Find shapes", action=action)
    return Option(
        id=f"picture:find-group{tail}",
        label="Find shapes",
        children=_listed(
            f"picture:find-group{tail}", [(f"picture:find:{f}{tail}", f) for f in offered]
        ),
    )


def _slice_option(printers: Sequence[str]) -> Option:
    """Slice on a made piece or a part from the parts folder: the pinned printer's
    Machine opened with it chosen under its Print from here's *makes*, and a slice of it
    started there for that printer: its log in the card, and the G-code chosen in the
    card's files when it ends, so Print follows. One printer pinned in the site is the
    cell itself; several are a cell each under Slice, as Print's are. The page carries
    it."""
    if len(printers) == 1:
        return Option(
            id="slice:piece", label="Slice", group="Machine", action=f"slice:piece:{printers[0]}"
        )
    return Option(
        id="slice:piece",
        label="Slice",
        group="Machine",
        children=_listed("slice:piece", [(f"slice:piece:{p}", p) for p in printers]),
    )


def _toolpath_option(routers: Sequence[str]) -> Option:
    """Toolpath on a part that says how it is cut: the pinned router's Machine opened
    with it chosen under its Cut from here's *makes*, and its toolpath written there
    for that router, kept and chosen, so Cut follows. One router pinned in the site
    is the cell itself; several are a cell each under Toolpath. The page carries it."""
    if len(routers) == 1:
        return Option(
            id="toolpath:piece",
            label="Toolpath",
            group="Machine",
            action=f"toolpath:piece:{routers[0]}",
        )
    return Option(
        id="toolpath:piece",
        label="Toolpath",
        group="Machine",
        children=_listed("toolpath:piece", [(f"toolpath:piece:{r}", r) for r in routers]),
    )


def _print_option(printers: Sequence[str]) -> Option:
    """Print on a made piece: the pinned printer's Machine opened with the piece chosen
    under its Print from here's *makes*. One printer pinned in the site is the cell
    itself; several are a cell each under Print. The page carries it."""
    if len(printers) == 1:
        return Option(
            id="print:piece", label="Print", group="Machine", action=f"print:piece:{printers[0]}"
        )
    return Option(
        id="print:piece",
        label="Print",
        group="Machine",
        children=_listed("print:piece", [(f"print:piece:{p}", p) for p in printers]),
    )


def _made_picture_group(picture: PictureContext) -> Option:
    """Picture on a made piece: Word › the vocabulary's words, and Drop (the piece
    goes; its shape reads as found again). Both change the site, so the server
    carries them."""
    options: List[Option] = []
    if picture.words:
        options.append(
            Option(
                id="picture:word-group",
                label="Word",
                children=_listed(
                    "picture:word-group", [(f"picture:word:{w}", w) for w in picture.words]
                ),
            )
        )
    options.append(
        Option(id="picture:drop", label="Drop", action="picture:drop", destructive=True, twice=True)
    )
    return Option(id="picture", label="Picture", group="Pictures", children=options)


def _pictures(picture: PictureContext) -> Option:
    """The canvas ring's Pictures, cell 9: Add (pinned at the floor), Floor › Fit,
    Camera, Picture (the floor's own verbs), Purge, and Gather, the gathering's
    report."""
    return Option(
        id="pictures",
        label="Pictures",
        group="Pictures",
        children=[
            Option(id="pictures:add", label="Add", action=f"picture:add:{FLOOR_MARK}"),
            Option(
                id="pictures:floor",
                label="Floor",
                children=[
                    option
                    for option in (
                        Option(id="floor:fit", label="Fit", action=f"fit:{FLOOR_MARK}"),
                        _camera_group(floor=True),
                        _picture_group(picture, floor=True),
                    )
                    if option is not None
                ],
            ),
            Option(
                id="picture:purge",
                label="Purge",
                action="picture:purge",
                destructive=True,
                twice=True,
            ),
            Option(id="camera:gather", label="Gather", action="camera:gather"),
        ],
    )


def _nothing_to_list(prefix: str, family: str, why: str) -> Option:
    """A cell of the canvas ring with nothing to list now, greyed and saying why, so that
    every cell keeps its address (``_canvas_ring``). Its action, ``<family>:none``, is
    never carried out: a greyed cell chosen does nothing (static/ring.js)."""
    return Option(id=prefix, label=shorten(prefix), action=f"{family}:none", enabled=False, why=why)


def _canvas_pieces(
    prefix: str,
    focus_path: str,
    focus: Optional[Assembly],
    made: Sequence[str],
    faceted: Dict[str, Tuple[Optional[str], Optional[str]]],
    universe: bool,
    site_name: Optional[str],
) -> Option:
    """Pieces at this level, more than fit cut by facet (``_pieces``). At the top, the
    pieces made from pictures are one Made cell after the code's own, so they cannot crowd
    the ring out; in the universe, Pieces lists its parts, and its sites are the canvas
    ring's Site cell's. Greyed, saying why, where there is nothing to list: no site, a
    target no longer in it, a level with nothing in it."""
    if focus is not None and focus_path and not focus.children:
        # A leaf stepped into is drawn as itself: the one piece at its level.
        return Option(
            id=prefix,
            label=shorten(prefix),
            children=[
                Option(
                    id=f"select:{focus_path}",
                    label=shorten(focus.name),
                    action=f"select:{focus_path}",
                )
            ],
        )
    if focus is None:
        return _nothing_to_list(
            prefix,
            "select",
            f"{focus_path} is not in {site_name}" if site_name else "no site is loaded",
        )
    at_top = not focus_path
    made_here = sorted({c.name for c in focus.children if c.name in set(made)}) if at_top else []
    names = sorted(
        {
            c.name
            for c in focus.children
            if c.name not in made_here and not (at_top and universe and c.site_ref)
        }
    )
    made_cell = _grouped("Made", made_here, lambda name: f"select:{name}")
    room = MOST_OPTIONS - (1 if made_cell is not None else 0)
    children = _pieces(prefix, focus_path, focus, faceted, names=names, room=room)
    if made_cell is not None:
        children.append(made_cell)
    if not children:
        here = focus_path or focus.name
        return _nothing_to_list(
            prefix,
            "select",
            f"nothing is in {here} but sites, which Site lists"
            if at_top and universe
            else f"nothing is in {here}",
        )
    return Option(id=prefix, label=shorten(prefix), children=children)


# The canvas ring's cell of the level's groups: what each is called where its site is
# grouped by it.
GROUPS_LABEL = {"kind": "Kinds", "system": "Systems"}


def _facet_cell(site: Optional[Assembly], part_category, under: str = "") -> Option:
    """Kinds in the universe, Systems in a site: a cell of each value what lies beneath
    the level in view (``under``) has (``facets.facets_of``), in its colour, each opening
    what its pieces hold in their places, as Site's chips do (``facet:<facet>:<value>``).
    Greyed, saying why, where there is none, so its address holds still."""
    if site is None:
        return Option(
            id="facets",
            label=GROUPS_LABEL["system"],
            action="facet:none",
            enabled=False,
            why="no site is loaded",
        )
    sent = facets_of(site, part_category, under)
    by = str(sent["by"])
    label = GROUPS_LABEL[by]
    values = [(str(value["name"]), str(value["colour"])) for value in sent["values"]]  # type: ignore[index]
    if not values:
        return Option(
            id="facets",
            label=label,
            action="facet:none",
            enabled=False,
            why=f"nothing {'beneath ' + under if under else 'in ' + site.name} is in one of the {label}",
        )
    return Option(
        id="facets",
        label=label,
        children=[
            Option(id=f"facet:{by}:{name}", label=name, action=f"facet:{by}:{name}", colour=colour)
            for name, colour in values
        ],
    )


def _canvas_ring(
    context: Context,
    site: Optional[Assembly],
    site_names: Sequence[str],
    part_category,
    picture: PictureContext,
    rig: bool = False,
) -> Ring:
    """The ring on empty canvas: the pieces at this level, the rest, and the way out.

    `context.targets[0]`, when given, is the path the viewer is stepped into;
    Pieces lists that piece's children -- at a leaf, the leaf itself, the one
    piece drawn -- and Step out steps back out. At the root there is no Step out,
    because there is nothing above. View is how the world is drawn, Fit first in
    it; Panels opens and closes what stands in front of it; Rebuild builds the
    site again from its factory, asked twice.

    Every cell is always there and keeps one address wherever the ring is opened: Pieces
    8, Site 6, View 2, Panels 4, Pictures 9, Rebuild 3, Step out 1 and the level's groups
    7, Kinds in the universe and Systems in a site (``_facet_cell``). A cell with nothing
    to do or list now is greyed, saying why, and holds its address: Pieces with no site, a
    target no longer in it or nothing at its level; Site with no site registered; the
    level's groups where none is beneath it. Step out at a site's own level goes to the
    universe, and is greyed at the universe's own, where there is nothing above.
    """
    focus_path = context.targets[0] if context.targets else ""
    focus = find_node_by_path(site, focus_path) if site and focus_path else site
    universe = site is not None and facet_of(site) == KIND
    faceted = kinds_and_systems(site, part_category) if site is not None else {}
    top_of_everything = universe and not focus_path
    site_name = site.name if site is not None else None
    options = [
        _canvas_pieces("Pieces", focus_path, focus, picture.made, faceted, universe, site_name),
        # The universe is listed with the sites, by the name the page gives it.
        _grouped(
            "Site",
            site_names,
            lambda name: f"site:{name}",
            shown={UNIVERSE: UNIVERSE_SHOWN},
        )
        or _nothing_to_list("Site", "site", "no site is registered"),
        _view(site, part_category, focus_path),
        _panels(rig),
        _pictures(picture),
        Option(id="reset", label="Rebuild", action="reset", destructive=True, twice=True),
        Option(
            id="up",
            label="Step out",
            action="zoom-out",
            enabled=not top_of_everything,
            why="the universe is the top: there is nothing to step out to"
            if top_of_everything
            else None,
        ),
        _facet_cell(site, part_category, focus_path),
    ]
    title = shorten(focus.name) if focus is not None else (shorten(site.name) if site else None)
    return Ring(title=title, options=options)


def _node_ring(
    context: Context,
    site: Optional[Assembly],
    device: Optional[Device],
    picture: PictureContext,
    sketch: Optional[str] = None,
    part_category=None,
) -> Ring:
    path = context.targets[0] if context.targets else ""
    node = find_node_by_path(site, path) if site and path else None
    camera = bool(path) and path in picture.camera_parts

    # Step in, Move and Why this are every piece's, and keep cells 8, 6 and 2 wherever
    # the ring is opened; what comes and goes with the piece follows them, and what
    # comes and goes with where it is -- a board pinned to it, a piece it is inside --
    # comes last.
    options: List[Option] = [
        Option(id="zoom", label="Step in", action="zoom-in"),
        Option(id="move", label="Move", action="move"),
        Option(id="why", label="Why this", action="explain"),
    ]

    # The pieces inside this one, a ring of them: selecting, not stepping in --
    # a chosen piece becomes the ring's next subject.
    inside = _pieces(
        "Inside",
        path,
        node,
        kinds_and_systems(site, part_category or _registered_category)
        if site is not None and node is not None and len(node.children) > MOST_OPTIONS
        else None,
    )
    if inside:
        options.append(Option(id="Inside", label="Inside", children=inside))

    # Appended after every cell the ring had, so none of them moves: a host
    # has a camera added above it and holds views; a made piece has its word and
    # can be dropped; a camera has its own verbs, its device first.
    if _is_host(site, path, [*picture.made, *picture.camera_parts]):
        options.append(
            _camera_group(
                floor=False,
                printer=path in picture.printers,
                machine=path in picture.printers or path in picture.routers,
            )
        )
        host_pictures = _picture_group(picture, floor=False)
        assert host_pictures is not None  # a host's always holds Add
        options.append(host_pictures)
    elif path and "." not in path and path in picture.made:
        options.append(_made_picture_group(picture))
    elif camera:
        options.extend(_camera_options(picture))
    # A part, or a piece made from a picture, is edited from Selected: Part › Edit opens
    # the one editor there and its Parameters window (systems.py's Part). Appended
    # last, so no cell above moves; a host with a board,
    # children and a part is the fullest node ring, eight, and so is a camera of this
    # browser's. A camera's editor edits its numbers -- its lens's position, its turn,
    # tilt and field of view (vision/camera_part.py,
    # GET /sites/{s}/cameras/{name}/params).
    made = bool(path and "." not in path and path in picture.made)
    in_a_printer = any(path == p or path.startswith(p + ".") for p in picture.printers)
    board = bool(node is not None and (node.sketch_ref or (picture.part and picture.part.board)))
    # A machine drawn as a part (the router) is no more sliced than a printer is.
    machine = bool(node is not None and node.build_volume is not None)
    part = bool(node is not None and node.part_ref and not camera and not board and not machine)
    if node is not None and (node.part_ref or camera or made):
        verbs = [Option(id="part:edit", label="Edit", action="part:edit")]
        # A part from the parts folder: Defaults stages the part's own numbers in its
        # editor, as the editor's Defaults does, so Apply draws the saved part again. A
        # camera's numbers and a made piece's are what was found and set, with no part's
        # own to go back to.
        if node.part_ref and not camera and not made:
            verbs.append(Option(id="part:defaults", label="Defaults", action="part:defaults"))
        # Apply and Revert act on what the editor has staged, as its buttons do,
        # for whatever it edits: the part's ring holds the whole loop.
        verbs.append(Option(id="part:apply", label="Apply", action="part:apply"))
        verbs.append(Option(id="part:revert", label="Revert", action="part:revert"))
        # Its SCAD, edited in Selected's editor: Save, a variant in git under the name
        # the editor shows; Variants, the saved ones, choosing one draws it. Told
        # by the server (``picture.part``); a part built by Python has no Save and
        # no Variants, and a part with none saved has no Variants. After Revert,
        # so the loop's cells keep their seats: eight at the most.
        part_of_the_folder = bool(node.part_ref and not camera and not made)
        seen = picture.part if part_of_the_folder else None
        if seen is not None and seen.editable:
            verbs.append(Option(id="part:save", label="Save", action="part:save"))
        # Two groups, so the ring holds eight at the most: View -- how the part
        # and its editor are seen: its SCAD window, beside the world, or the editor
        # over the whole page, the ghost of what was drawn before beside what is
        # drawn now, and the part framed with Selected kept open (f) -- and History,
        # the staged numbers' undo and redo (Ctrl+Z, Ctrl+Shift+Z).
        view = []
        if seen is not None:
            view.append(Option(id="part:scad", label="SCAD", action="part:scad"))
            view.append(Option(id="part:fullscreen", label="Fullscreen", action="part:fullscreen"))
        if part_of_the_folder:
            view.append(Option(id="part:ghost", label="Ghost", action="part:ghost"))
        view.append(Option(id="part:fit", label="Fit", action="part:fit"))
        # A part whose pieces move: its Motion window and the window's controls
        # (widgets/motion.js). After Fit, so no cell of View moves.
        if seen is not None and seen.motion:
            view.append(_motion())
        # The part's cabinet, Part › Feedback, on a part that is made -- not a camera, a
        # board, a machine, or anything inside a printer. After Motion, so no cell of View
        # moves.
        if part and not in_a_printer:
            view.append(_feedback())
        verbs.append(Option(id="part:view", label="View", children=view))
        verbs.append(
            Option(
                id="part:history",
                label="History",
                children=[
                    Option(id="part:undo", label="Undo", action="part:undo"),
                    Option(id="part:redo", label="Redo", action="part:redo"),
                ],
            )
        )
        if seen is not None and seen.editable:
            # Last, so the first save, which brings it, moves no cell.
            chosen = _variants_group(seen.variants, seen.deleted)
            if chosen is not None:
                verbs.append(chosen)
        # A part's presets and, on an end, the adapter between it and an end kept: after
        # the rest, where the ring has room (a part built by Python has no Save or
        # Variants), so no cell above moves.
        if seen is not None and seen.presets and len(verbs) < MOST_OPTIONS:
            verbs.append(
                Option(
                    id="part:presets",
                    label="Presets",
                    children=_fit(
                        "part:presets",
                        [
                            Option(
                                id=f"part:preset:{name}",
                                label=label,
                                action=f"part:preset:{name}",
                            )
                            for name, label in zip(
                                seen.presets,
                                distinct([seen.preset_labels.get(n) or n for n in seen.presets]),
                                strict=True,
                            )
                        ],
                        by_name=False,
                    ),
                )
            )
        if seen is not None and seen.end and len(verbs) < MOST_OPTIONS:
            verbs.append(Option(id="part:adapter", label="Adapter", action="part:adapter"))
        options.append(Option(id="part", label="Part", group="Part", children=verbs))
    # A made piece with a printer pinned in its site to print it on: Print,
    # appended after Part so no cell above moves. A piece with nowhere to be
    # printed has no Print rather than one greyed out.
    if made and picture.printers:
        options.append(_print_option(picture.printers))
    # Slice, beside Print: a made piece, or a part from the parts folder standing in
    # the site -- not a camera, nor a printer or anything inside one, nor a board (a
    # devkit is bought and flashed, never printed) -- sliced for a printer pinned
    # there. Appended last, so no cell above moves; with no printer pinned in the
    # site there is nothing to slice for, and no Slice.
    if (made or part) and picture.printers and not in_a_printer:
        options.append(_slice_option(picture.printers))
    # Toolpath, the same place for a part that says how it is cut, with a router
    # pinned in the site to cut it on.
    if part and picture.part and picture.part.cuts and picture.routers:
        options.append(_toolpath_option(picture.routers))
    # A piece with a board pinned to it can be watched, polled and, when the board is
    # a printer, driven. A piece with none gets no Device option at all rather than
    # one greyed out. A camera's Device is which browser camera it is, among its own
    # verbs above, and no board's.
    if device is not None and device.bound and not camera:
        options.append(
            Option(id="device", label="Device", group="Machine", children=_device_options(device))
        )
    # A part with a sketch of its own that no board connected runs: the Bench opened
    # on it, where a board running it would have its Device. Where Device would be,
    # so the cells before it stay.
    elif sketch and not camera:
        options.append(
            Option(id="device:flash-sketch", label="Flash sketch", action="device:flash-sketch")
        )
    # The piece it is inside, selected: Parent, after every cell of the piece's own.
    if "." in path:
        parent = path.rsplit(".", 1)[0]
        options.append(Option(id="up", label="Parent", action=f"select:{parent}"))
    # A Stream Deck +: the Deck window, the device as apothecary has drawn it and what it
    # has heard, as Open Deck in its Selected opens it. Last, where the ring has room, so
    # no cell before it moves: a deck on the floor fills it, a host's eight.
    if (
        picture.part is not None
        and picture.part.deck
        and not camera
        and len(options) < MOST_OPTIONS
    ):
        options.append(
            Option(
                id="panel:deck",
                label="Deck",
                group=PANEL_GROUPS["deck"],
                action="panel:toggle:deck",
            )
        )
    return Ring(title=shorten(path or (node.name if node else "")), options=options)


def _device_ring_on_top(context: Context, device: Optional[Device]) -> Ring:
    """The device ring as the top ring, opened on a port rather than a node: titled by
    the machine its board is pinned to, as the windows and a reason name it, else by
    the port."""
    if device is None:
        port = context.targets[0] if context.targets else ""
        if not port:
            raise ValueError("a device ring stands on a port, and none was given")
        device = Device(port=port)
    # The port's last path segment: /dev/ttyUSB0 is ttyUSB0 on the ring.
    leaf = device.port.rstrip("/").rsplit("/", 1)[-1] or device.port
    return Ring(title=shorten(device.name or leaf), options=_device_options(device))


def _device_options(device: Device) -> List[Option]:
    """What can be done with a board. The page's handlers do each one.

    Open is the board's Machine, the one place for it. Flash is the Machine opened
    at its Flashing card. A printer keeps its own firmware and is never flashed:
    its Flash holds the cell and cannot be chosen, so every cell after it is the
    same on a devkit and on a printer (Control at 7). Pin and Unpin
    are one cell, since a port is either pinned to this node or not. Control
    appears only for a printer: a board running a sketch has no G-code to be
    driven with. Told what the server would refuse of the port now (``device.can``),
    each act it refuses is greyed with its reason.
    """
    options = [
        Option(id="device:open", label="Open", action="device:open"),
        Option(id="device:poll", label="Poll", action="device:poll"),
        Option(
            id="device:flash",
            label="Flash",
            action="device:flash",
            enabled=not device.printer,
            why=keeps_its_firmware(device) if device.printer else None,
        ),
        Option(id="device:query", label="Query", action="device:query"),
        (
            Option(id="device:unpin", label="Unpin", action="device:unpin")
            if device.bound
            else Option(id="device:pin", label="Pin", action="device:pin")
        ),
        Option(id="device:rescan", label="Rescan", action="device:rescan"),
        # The link itself: reopen it, reboot the board on purpose, or hand the
        # port to another program. Before Control on purpose, so its cell is
        # the same on a devkit (no Control) and on a printer. A devkit's port is
        # opened only when asked: Listen opens it and streams what the board
        # says (opening it may reset the board), and Probe asks esptool what
        # the chip is (it resets the board). Both appended, so every cell
        # before them stays; a printer is polled over its held link, never
        # streamed or probed, and has neither.
        Option(
            id="device:link",
            label="Link",
            children=[
                Option(id="device:reconnect", label="Reconnect", action="device:reconnect"),
                Option(
                    id="device:reset",
                    label="Reboot",
                    action="device:reset",
                    destructive=True,
                    twice=True,
                ),
                Option(id="device:release", label="Release", action="device:release"),
            ]
            + (
                []
                if device.printer
                else [
                    Option(id="device:listen", label="Listen", action="device:listen"),
                    Option(id="device:probe", label="Probe", action="device:probe"),
                ]
            ),
        ),
    ]
    if device.printer:
        options.append(Option(id="control", label="Control", children=control_options(device)))
    if device.can is not None:
        judged(options, device.can)
    return options


def keeps_its_firmware(device: Device) -> str:
    """Why a machine's Flash, which holds its cell, is never chosen: the Machine's words."""
    return f"a {device.machine or 'printer'} keeps its own firmware; Apothecary polls it and never flashes it"


class ByJob(NamedTuple):
    """An act that is the job's while a job runs (its ``running`` command is ok) and the
    line's otherwise, as the page carries it: a print's Pause is the job paused while a
    print from the host runs on the port (``print.cancel`` ok, widgets/machine.js
    HOST_VERBS), else ``M25``; the knobs' On / off is their stop while they run on the deck
    (``knobs.machine`` ok), else their start."""

    job: str
    line: Optional[str]
    running: str = "print.cancel"


JOG_AXES = ("Y+", "X+", "Y-", "X-", "Z+", "Z-")
CORNERS = ("BR", "FR", "FL", "BL")

# Each act on a machine's ring, by the command the server answers for it (firmware/can.py
# can_now): the verb its button in the Machine names in data-can, or, for a line the pad
# sends, the verb static/can.js verbOfLine names that line by. None: nothing the server
# answers stands in its way -- the latch's own switch, what opens a window or a card, what
# the page alone does. tests/test_can_js.py holds it to the page act by act, and every
# act a machine's ring carries has an entry.
CanVerb = Union[str, ByJob, None]
CAN_VERBS: Dict[str, CanVerb] = {
    "device:open": None,
    "device:poll": None,
    "device:flash": None,  # it opens the Flashing card, whose own buttons answer for a flash
    "device:query": "identify",
    "device:pin": None,
    "device:unpin": None,
    "device:rescan": None,
    "device:reconnect": "reconnect",
    "device:reset": "reset",
    "device:release": "release",
    "device:listen": "listen",
    "device:probe": "probe",
    "control:arm": None,
    "control:disarm": None,
    "control:estop": "estop",
    "control:hotend-on": "heat",
    "control:hotend-off": "off",
    "control:bed-on": "heat",
    "control:bed-off": "off",
    "control:fan-on": "heat",
    "control:fan-off": "off",
    "control:home": "home",
    "control:home-xy": "home",
    "control:home-x": "home.X",
    "control:home-y": "home.Y",
    "control:home-z": "home.Z",
    **{f"control:jog:{axis}": "jog" for axis in JOG_AXES},
    "control:jog-cancel": "quickstop",
    "control:motors-off": "control",
    "control:quickstop": "quickstop",
    "control:break-wait": "interrupt",
    "control:mesh-on": "control",
    "control:mesh-off": "control",
    **{f"control:corner:{corner}": "control" for corner in CORNERS},
    "level:probe": "level.probe",
    "level:read": "level.read",
    "control:sd-resume": ByJob("print.resume", "control"),
    "control:sd-pause": ByJob("print.pause", "card.pause"),
    "control:sd-abort": ByJob("print.cancel", "control"),
    "control:job-resume": ByJob("print.resume", "resume"),
    "control:job-hold": ByJob("print.pause", "interrupt"),
    "control:job-abort": ByJob("print.cancel", "estop"),  # with no job, the soft reset: a stop
    "print:start": "print.start",
    "print:preview": None,
    "print:plan": None,
    "control:unlock": "unlock",
    "control:spindle-on": "spindle",
    "control:spindle-off": "off",
    "control:zero-xyz": "control",
    "control:zero-z": "control",
    "control:go-zero": "control",
    "control:top-z": "control",
    "control:probe-z": "control",
    "control:probe-plate": "control",
    # Panels › Machine on the canvas ring (_panels), told the page's ``can`` beside the
    # context: the open Machine's window and its pad, which the page alone opens; the
    # knobs, by the deck's answer (firmware/can.py deck_can, the Deck window's data-can),
    # On / off their stop while they run and their start otherwise; the heater loops, by the
    # open Machine's port's (the Loops window's data-can). A key ending in a colon is a
    # family: ``deck:machine:`` is every machine's cell. Choosing a loop, an experiment
    # or a rule is the window's choice, which nothing the server answers stands in the way of.
    "panel:toggle:machine": None,
    "panel:pad": None,
    "deck:knobs": ByJob("knobs.stop", "knobs.start", running="knobs.machine"),
    "deck:machine:": "knobs.machine",
    "deck:step:": "knobs.step",
    "deck:here": "here",
    "panel:toggle:deck": None,
    "deck:screen:": "knobs.screen",
    "panel:toggle:loops": None,
    "loops:read": "tune.read",
    "loops:start": "tune.start",
    "loops:cancel": "tune.cancel",
    "loops:set": "tune.set",
    "loops:loop:": None,
    "loops:kind:": None,
    "loops:rule:": None,
}
# What is never greyed, whatever an answer says: the stop, as can.js's NEVER.
NEVER_GREYED = frozenset({"estop"})


def can_entry(action: str) -> Tuple[bool, CanVerb]:
    """``action``'s entry in ``CAN_VERBS``: its own, else its family's (the key ending in a
    colon it starts with); ``(False, None)`` when it has none."""
    if action in CAN_VERBS:
        return True, CAN_VERBS[action]
    for key, verb in CAN_VERBS.items():
        if key.endswith(":") and action.startswith(key):
            return True, verb
    return False, None


def verdict_of(can: Dict[str, Verdict], verb: str) -> Optional[Verdict]:
    """The answer for ``verb``, else for the command before its dot (a printer's
    ``home.X`` is its ``home``), as static/can.js verdictOf reads it."""
    return can.get(verb) or can.get(verb.split(".")[0])


def refusal_of(action: str, can: Dict[str, Verdict]) -> Optional[str]:
    """Why the server would refuse the act ``action`` names, by ``can``; None when it
    would take it, or when nothing it answers stands in its way."""
    _, verb = can_entry(action)
    if isinstance(verb, ByJob):
        running = verdict_of(can, verb.running)
        verb = verb.job if running is not None and running.ok else verb.line
    if verb is None or verb in NEVER_GREYED:
        return None
    verdict = verdict_of(can, verb)
    if verdict is None or verdict.ok:
        return None
    return verdict.why or f"the server refuses {verb} now"


def judged(options: Sequence[Option], can: Dict[str, Verdict]) -> None:
    """Each act among ``options`` the answer refuses greyed with its reason; a ring of
    acts opens whatever its acts say, so the reasons can be read there."""
    for option in options:
        if option.children:
            judged(option.children, can)
        elif option.action:
            why = refusal_of(option.action, can)
            if why:
                option.enabled = False
                option.why = why


def control_options(device: Device) -> List[Option]:
    """The control ring: every allowlisted thing a printer can be told to do.

    Each leaf is one line from ``firmware.gcode.CONTROL_CODES``, sent by the
    Machine's control chain, which is where the latch is checked. Jog is
    seated so the keypad is the jog pad: Y+ up, X+ right, Y- down, X- left,
    and Z+ and Z- in the right-hand corners. Stop is E-STOP and is marked
    destructive, since the board halts until it is reset. A router's ring is
    ``router_control_options``.
    """
    if device.machine == "router":
        return router_control_options(device)
    return [
        Option(
            id="control:heat",
            label="Heat",
            children=[
                Option(id="control:hotend-on", label="Hotend on", action="control:hotend-on"),
                Option(id="control:hotend-off", label="Hotend off", action="control:hotend-off"),
                Option(id="control:bed-on", label="Bed on", action="control:bed-on"),
                Option(id="control:bed-off", label="Bed off", action="control:bed-off"),
                Option(id="control:fan-on", label="Fan on", action="control:fan-on"),
                Option(id="control:fan-off", label="Fan off", action="control:fan-off"),
            ],
        ),
        Option(
            id="control:home",
            label="Home",
            children=[
                Option(id="control:home:all", label="All", action="control:home"),
                Option(id="control:home-xy", label="XY", action="control:home-xy"),
                Option(id="control:home-z", label="Z", action="control:home-z"),
                Option(id="control:home-x", label="X", action="control:home-x"),
                Option(id="control:home-y", label="Y", action="control:home-y"),
            ],
        ),
        Option(
            id="control:jog",
            label="Jog",
            children=[
                Option(id=f"control:jog:{axis}", label=axis, action=f"control:jog:{axis}")
                for axis in ("Y+", "X+", "Y-", "X-", "Z+", "Z-")
            ],
        ),
        # The bed: read or probe it (a record is kept), switch the mesh, and
        # the four corners for a paper test, seated as they lie on the bed --
        # front left at 1, front right at 3, back left at 7, back right at 9.
        Option(
            id="control:level",
            label="Level",
            children=[
                Option(id="level:probe", label="Probe", action="level:probe"),
                Option(id="level:read", label="Read", action="level:read"),
                Option(id="control:mesh-on", label="Mesh on", action="control:mesh-on"),
                Option(id="control:mesh-off", label="Mesh off", action="control:mesh-off"),
                Option(id="control:corner:BR", label="Back right", action="control:corner:BR"),
                Option(id="control:corner:FR", label="Front right", action="control:corner:FR"),
                Option(id="control:corner:FL", label="Front left", action="control:corner:FL"),
                Option(id="control:corner:BL", label="Back left", action="control:corner:BL"),
            ],
        ),
        # The print, whichever is running: the card's (M24/M25/M524) or one
        # the host streams. The page knows which and carries the verb to it;
        # Send file starts a host print of the file the page has chosen.
        Option(
            id="control:sd",
            label="Print",
            children=[
                Option(id="control:sd-resume", label="Resume", action="control:sd-resume"),
                Option(id="control:sd-pause", label="Pause", action="control:sd-pause"),
                Option(id="control:sd-abort", label="Abort", action="control:sd-abort"),
                Option(id="print:start", label="Send file", action="print:start"),
                Option(id="print:preview", label="Preview", action="print:preview"),
                Option(id="print:plan", label="Keep as plan", action="print:plan"),
            ],
        ),
        Option(
            id="control:motors",
            label="Motors",
            children=[
                Option(id="control:motors-off", label="Off", action="control:motors-off"),
                Option(id="control:quickstop", label="Quickstop", action="control:quickstop"),
                Option(id="control:break-wait", label="Break wait", action="control:break-wait"),
            ],
        ),
        Option(id="control:estop", label="Stop", action="control:estop", destructive=True),
        (
            Option(id="control:disarm", label="Disarm", action="control:disarm")
            if device.armed
            else Option(id="control:arm", label="Arm", action="control:arm")
        ),
    ]


def router_control_options(device: Device) -> List[Option]:
    """A router's control ring: every allowlisted thing its controller can be told
    (``firmware.grbl.CONTROL_CODES`` and the realtime characters), sent by the
    Machine's control chain as a printer's are. Home, Unlock and Jog first, as a
    person homes before anything else; the spindle; work zero and the probe
    together, since a probe is how Z is zeroed; the cut's own verbs, the piece cut
    measured among them; Stop is the soft reset, destructive as E-STOP is. Eight, as
    a ring holds.
    """
    return [
        Option(
            id="control:home",
            label="Home",
            children=[
                Option(id="control:home:all", label="All", action="control:home"),
                Option(id="control:home-x", label="X", action="control:home-x"),
                Option(id="control:home-y", label="Y", action="control:home-y"),
                Option(id="control:home-z", label="Z", action="control:home-z"),
            ],
        ),
        Option(id="control:unlock", label="Unlock", action="control:unlock"),
        Option(
            id="control:jog",
            label="Jog",
            children=[
                Option(id=f"control:jog:{axis}", label=axis, action=f"control:jog:{axis}")
                for axis in ("Y+", "X+", "Y-", "X-", "Z+", "Z-")
            ]
            + [Option(id="control:jog-cancel", label="Stop jog", action="control:jog-cancel")],
        ),
        Option(
            id="control:spindle",
            label="Spindle",
            children=[
                Option(id="control:spindle-on", label="On", action="control:spindle-on"),
                Option(id="control:spindle-off", label="Off", action="control:spindle-off"),
            ],
        ),
        Option(
            id="control:zero",
            label="Zero",
            children=[
                Option(id="control:zero-xyz", label="XYZ here", action="control:zero-xyz"),
                Option(id="control:zero-z", label="Z here", action="control:zero-z"),
                Option(id="control:go-zero", label="Go to zero", action="control:go-zero"),
                Option(id="control:top-z", label="Top of Z", action="control:top-z"),
                Option(id="control:probe-z", label="Probe Z", action="control:probe-z"),
                Option(id="control:probe-plate", label="Probe plate", action="control:probe-plate"),
            ],
        ),
        # The cut, whichever is running: a hold and a resume reach the controller at
        # once and the stream with them; Send file starts a cut of the file chosen.
        Option(
            id="control:job",
            label="Cut",
            children=[
                Option(id="control:job-resume", label="Resume", action="control:job-resume"),
                Option(id="control:job-hold", label="Hold", action="control:job-hold"),
                Option(id="control:job-abort", label="Abort", action="control:job-abort"),
                Option(id="print:start", label="Send file", action="print:start"),
                Option(id="print:preview", label="Preview", action="print:preview"),
                Option(id="print:plan", label="Keep as plan", action="print:plan"),
            ],
        ),
        Option(id="control:estop", label="Stop", action="control:estop", destructive=True),
        (
            Option(id="control:disarm", label="Disarm", action="control:disarm")
            if device.armed
            else Option(id="control:arm", label="Arm", action="control:arm")
        ),
    ]


class Carries(str, Enum):
    """Who does the thing an option names: the intent route, or the page."""

    SERVER = "the server carries it out"
    VIEWER = "the viewer carries it out"


class UnknownAction(KeyError):
    """An action no ring should be producing, or one nobody has classified.

    Raised rather than defaulted. A default here would mean a new option added
    to a ring silently becomes whatever the default is, which is the failure
    this whole table exists to prevent.
    """


# Every action any ring can produce, and who carries it out. Actions that name a
# thing -- an arrangement, a group, a piece -- are written as their prefix, since
# `site:garage` and `site:bench` are one entry and not two.
#
# SERVER means the intent endpoint does it and the answer says what changed.
# VIEWER means the intent endpoint does nothing and says so, because the work
# is where the drawing is.
CARRIED_BY: Dict[str, Carries] = {
    # The viewer's own business: what is on screen, and where you are looking.
    "fit": Carries.VIEWER,
    "zoom-in": Carries.VIEWER,
    "zoom-out": Carries.VIEWER,
    # Choosing a piece from the ring is what a click on a row of Site's tree is.
    "select": Carries.VIEWER,
    "explain": Carries.VIEWER,
    # Taking hold of a piece happens under a finger. The commit that follows it
    # changes the arrangement through the site's layout route, not a ring.
    "move": Carries.VIEWER,
    # Choosing which arrangement to look at, and which pieces to show, are both
    # about what is on screen rather than what the arrangement is.
    "site": Carries.VIEWER,
    "facet": Carries.VIEWER,
    # Discarding every edit and rebuilding from the factory.
    "reset": Carries.SERVER,
    # A board's verbs. The pages already have a handler for each -- Selected's
    # Device line and the board's Machine -- and the ring hands the choice to
    # that handler. The server is reached through the firmware routes those
    # handlers already call, never through the intent route.
    "device": Carries.VIEWER,
    # Driving a printer. Each leaf is one allowlisted G-code line, sent by the
    # Machine's control chain, which is where the latch is checked and
    # where a refusal is shown. The intent route never opens a port.
    "control": Carries.VIEWER,
    # Reading or probing the bed: the page starts the job and shows the record.
    "level": Carries.VIEWER,
    # Streaming a file: the page starts the job with the file it has chosen.
    "print": Carries.VIEWER,
    # A made piece's Print: the page opens the printer's Machine with the piece
    # chosen under makes; nothing is sent until that card's Print.
    "print:piece": Carries.VIEWER,
    # Feedback on a part's piece: the page opens Part › Feedback on the part's cabinet and
    # files what is read, seen or noted through /cabinet; nothing is sent to a machine.
    "feedback": Carries.VIEWER,
    # Slice, on a made piece or a part: the page opens the printer's Machine with it
    # chosen under makes and starts the slice there (POST /slicer/slice), a task the
    # card follows; nothing is sent to the printer.
    "slice": Carries.VIEWER,
    "toolpath": Carries.VIEWER,
    # Opening and closing the windows beside the world (panels.js).
    "panel": Carries.VIEWER,
    # A printer's Workspace: the page opens the window on the printer, watches
    # its board and keeps frames with its polls (widgets/working_space.js).
    "working": Carries.VIEWER,
    # A machine's projector: the page opens the projector's page for it in a window of
    # its own, for a second display (static/projector.js); nothing is changed.
    "projector": Carries.VIEWER,
    # GO and Start over: the page hands each to the Procedure window, which fires
    # through the family's hub (widgets/procedure.js).
    "procedure": Carries.VIEWER,
    # The Stream Deck +'s knobs: the page hands each to the server's layout on the deck
    # (static/deck_knobs.js, PUT /firmware/decks/{id}/control).
    "deck": Carries.VIEWER,
    # A heater loop's acts and choices: the page hands each to the Loops window
    # (widgets/loops.js), which calls the loop routes for the printer whose Machine is
    # open (POST /firmware/printers/loops/read, start, cancel, set), never the intent
    # route, and greys what the server would refuse.
    "loops": Carries.VIEWER,
    # How the world is drawn: the header's View menu (snapping, detail, outlines,
    # whether a click picks a wall).
    "view": Carries.VIEWER,
    # A layer's acts, under View › Layers: the page's pick scope (static/pick_scope.js),
    # which the Layers window's ticks and the world read too.
    "layer": Carries.VIEWER,
    # The Bench's verbs: its buttons, each acting on what the Bench has chosen.
    # The tasks they start are the firmware routes' (POST /firmware/install,
    # /cores/install, /libraries/install, /sketches/{name}/compile and /upload,
    # /esptool/flash, /tasks/{id}/cancel), called by the page, never through
    # the intent route.
    "bench": Carries.VIEWER,
    # The Airgap panel's verbs: the page carries each to the panel (widgets/airgap.js).
    "airgap": Carries.VIEWER,
    # Models' verbs: the page carries each to the window (widgets/models.js), which
    # asks the server about the shape chosen on a mat.
    "models": Carries.VIEWER,
    # Marks' verbs: the page carries each to the window (widgets/marks.js), which
    # tells the server a person's word on the mark chosen there.
    "marks": Carries.VIEWER,
    # The Tour's verbs: the page carries each to its box (widgets/tour_popover.js), which
    # keeps a person's word on the stage it shows (POST /tour/feedback).
    "tour": Carries.VIEWER,
    # A camera's verbs: which of this browser's cameras it is (and Allow, to name
    # them), live, a picture taken and made its view, and the gathering's report
    # -- the page's: only the browser can open a camera, and the device and
    # picture routes are what the page calls.
    "camera": Carries.VIEWER,
    # A camera added above a place, or removed: a root structure added to the
    # arrangement or taken from it, as a make or a drop is, so the intent route
    # carries them, calling what the camera routes call
    # (apothecary/vision/cameras.py's add_here and remove).
    "camera:add-here": Carries.SERVER,
    "camera:remove": Carries.SERVER,
    # A picture's verbs that choose, draw, find shapes, size or pin: what is on
    # screen, or data attached to a host that no site sees.
    "picture": Carries.VIEWER,
    # Those that add, remove or rebuild a root structure change the arrangement,
    # as a reset does: the intent route carries them, calling the functions the
    # view routes call (apothecary/vision/views.py's make, drop and rebuild).
    "picture:make": Carries.SERVER,
    "picture:make-all": Carries.SERVER,
    "picture:drop": Carries.SERVER,
    "picture:word": Carries.SERVER,
    # The part editor is the page's: Part › Edit opens it in Selected and puts
    # the cursor in its first control, Part › Defaults opens it with the part's
    # own numbers staged, and Part › Apply and Revert do what its buttons do with
    # what is staged; Part › Save, Variants, Pop out and Fullscreen do what the SCAD
    # editor's own do. What Apply and Save change goes through the part, made,
    # camera and saved-variant routes the editor already calls, never the intent
    # route.
    "part": Carries.VIEWER,
}


def carried_by(action: str) -> Carries:
    """Who carries out this action; ``site:garage`` is looked up as ``site``.

    The longest classified prefix wins, so ``picture:make:view_1:2`` is
    ``picture:make``'s and ``picture:draw:view_1`` is ``picture``'s.

    Raises rather than guessing, so an action nobody has classified is an error
    rather than a wedge that does nothing.
    """
    parts = action.split(":")
    for n in range(len(parts), 0, -1):
        prefix = ":".join(parts[:n])
        if prefix in CARRIED_BY:
            return CARRIED_BY[prefix]
    raise UnknownAction(
        f"nothing says who carries out {action!r}. Add it to CARRIED_BY, as "
        "itself or as its prefix, and say which of the three it is -- a wedge "
        "nobody classified is a wedge that silently does nothing."
    )


__all__ = [
    "BACK",
    "CARRIED_BY",
    "CameraSeen",
    "FLOOR_MARK",
    "ViewSeen",
    "PictureContext",
    "Place",
    "ShapeSeen",
    "CELLS",
    "COMPASS",
    "Carries",
    "Context",
    "DIRECTIONS",
    "Device",
    "Intent",
    "LONGEST_LABEL",
    "MOST_OPTIONS",
    "NoSuchCell",
    "Option",
    "PartSeen",
    "PLACEMENT",
    "Pointing",
    "Ring",
    "RingTooFull",
    "UnknownAction",
    "carried_by",
    "check_ring",
    "control_options",
    "nearest",
    "place",
    "resolve",
    "shorten",
]
