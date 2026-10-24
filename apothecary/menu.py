"""The ring's options, built here rather than in the browser.

rad — the shared ring of options that appears under your finger — says the part
that decides *which* options to show is a plain function over data: given what
you are pointing at, hand back a list. It never changes anything itself. That
makes it ordinary Python, which is the point of putting it here: the two rules
that are easiest to break by accident, at most eight options and at most twelve
characters a label, become ordinary tests instead of something you notice in a
screenshot.

What stays in the browser: how the ring is drawn, how a press becomes a choice,
and the geometry of where your finger is. Rewriting those here would make this a
second implementation of the ring, which is somebody else's job and a different
piece of work.

Two rules from the shared contract are enforced below rather than described:

- **Eight options to a ring, no more.** Overflow is a design problem, not a
  scrolling problem. Too many options means the ring needs grouping, so this
  refuses to build one rather than quietly showing nine.
- **Twelve characters to a label, and never trailed off with dots.** Shortening
  is this function's job. A label that has run out of room has to be made
  shorter, not hidden behind an ellipsis nobody can read.

## The ring addresses nine cells

rad's nine-cells record (``DRAFT-the-menu-addresses-nine-cells``) adds a third
rule, and it is the one that makes the ring repeatable: **a ring is nine cells
numbered as a numeric keypad**, and geometry is a rendering of the cells rather
than the other way round.

    7 8 9        up-left     up    up-right
    4 5 6   =    left       BACK   right
    1 2 3        down-left  down   down-right

Eight cells hold options; cell 5 never does. It backs out one level, and closes
at the top. Options are seated cardinals first — ``8, 6, 2, 4`` and only then
the corners ``9, 3, 1, 7`` — so a four-option ring sits at up, right, down and
left, where a ring would put it anyway. Every cell has one number and one
direction and they are the same thing, so a digit chooses a cell from anywhere,
an arrow moves to the nearest occupied cell in that direction, and the digits
pressed to reach an option through nested rings are its **address**: ``"86"``
is cell 8 (a submenu) and then cell 6. Given the same context the same address
reaches the same option, which is what the numbering buys.

The browser draws the eight cells as fixed compass wedges, up being cell 8 and
clockwise from there ``8 9 6 3 2 1 4 7``; ``COMPASS`` is that mapping, so the
polar arithmetic rad already has still names the same option this file does.

PROTOTYPE — not ratified. See ``docs/plans/edits/apothecary-surface.md``.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .hierarchy import Assembly

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
    EDGE = "edge"
    CANVAS = "canvas"
    SELECTION = "selection"
    DEVICE = "device"


class Where(BaseModel):
    """Where on the screen the ring was opened."""

    x: float = 0.0
    y: float = 0.0


class Context(BaseModel):
    """What the ring was opened on, and which things it applies to.

    ``targets`` are the same dotted paths everything else in this tool already
    uses to name a node — ``printer_1.gantry_system`` and so on. No new way of
    naming things was needed, which is worth knowing before anyone invents one.
    A ring opened on a device names its port instead.
    """

    pointing: Pointing
    targets: List[str] = Field(default_factory=list)
    where: Where = Field(default_factory=Where)


class Device(BaseModel):
    """What the resolver is told about a board, so it can offer the right verbs.

    Told rather than looked up: the resolver stays a plain function over data,
    and the page already knows all four of these about the port it is standing
    on. ``bound`` says the port is pinned to the node the ring was opened on;
    ``printer`` says it speaks G-code, so control is on offer; ``armed`` is the
    control latch, which decides whether the ring says Arm or Disarm.
    """

    port: str
    printer: bool = False
    armed: bool = False
    bound: bool = False


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
    destructive: bool = False
    children: Optional[List["Option"]] = None
    cell: Optional[int] = None

    model_config = ConfigDict(validate_assignment=True)

    @field_validator("label")
    @classmethod
    def _label_is_readable(cls, label: str) -> str:
        """Checked on the field, so it still holds when a label is assigned later.

        As a check run after the whole thing is built, it held only at the
        moment of building: assigning a forty-character label afterwards sailed
        straight past it.
        """
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
        # Only the outermost ring was ever counted, so a submenu could hold any
        # number at all. Seating the children here also gives each its cell.
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


def walk(ring: Ring, address: str) -> Option:
    """Follow an address down through nested rings to the option it names.

    Every digit but the last must open a further ring. An address that runs
    into an option that does something, or into an empty cell, is refused
    with the cell that stopped it rather than answered with the nearest thing.
    """
    if not address:
        raise NoSuchCell("an empty address reaches nothing; press at least one cell")
    if not ADDRESS.match(address):
        raise NoSuchCell(f"address {address!r} is not a run of cells: digits 1 to 9, never {BACK}")
    here = ring
    option: Optional[Option] = None
    for depth, digit in enumerate(address):
        if option is not None:
            if not option.children:
                raise NoSuchCell(
                    f"cell {option.cell} ({option.label}) does something rather than "
                    f"opening a ring, so {address[depth:]!r} after it goes nowhere"
                )
            here = Ring(title=option.label, options=option.children)
        option = here.at(int(digit))
    assert option is not None
    return option


def address_of(ring: Ring, option_id: str) -> str:
    """The digits that reach an option, searching in placement order."""

    def search(options: Sequence[Option], so_far: str) -> Optional[str]:
        for option in options:
            path = f"{so_far}{option.cell}"
            if option.id == option_id:
                return path
            if option.children:
                found = search(option.children, path)
                if found is not None:
                    return found
        return None

    found = search(ring.options, "")
    if found is None:
        raise NoSuchCell(
            f"no option called {option_id!r} on {ring.title or 'this ring'} or under it"
        )
    return found


def every_address(ring: Ring) -> Dict[str, str]:
    """Every address that does something, and the action it does.

    Submenus are not listed; they are the way to a leaf, not a thing to do.
    """
    found: Dict[str, str] = {}

    def search(options: Sequence[Option], so_far: str) -> None:
        for option in options:
            path = f"{so_far}{option.cell}"
            if option.children:
                search(option.children, path)
            elif option.action:
                found[path] = option.action

    search(ring.options, "")
    return found


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


def shorten(text: str) -> str:
    """Make a label fit, without trailing it off.

    **Nothing is taken away from a label that already fits.** That rule came
    from a real fault: every dot used to be treated as a path separator before
    the length was even checked, so ``M3.5_bolt`` became ``5 bolt`` and
    ``nozzle_0.4mm`` became ``4mm``. In a tool for making parts, silently
    turning a 0.4 mm nozzle into "4mm" is about the worst thing a label can do.

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
    if 0 < len(whole) <= LONGEST_LABEL:
        return whole

    label = whole.rsplit(".", 1)[-1].replace("_", " ").replace("-", " ").replace(".", " ").strip()
    label = " ".join(label.split())

    if not label:
        # Nothing but separators. Fall back to what was actually passed in, so
        # the wedge says something rather than nothing.
        stripped = "".join(ch for ch in whole if not ch.isspace())
        return (stripped or "unnamed")[:LONGEST_LABEL]

    if len(label) <= LONGEST_LABEL:
        return label

    words = label.split()
    if len(words) == 1:
        return label[:LONGEST_LABEL].rstrip()

    for keep in (6, 5, 4, 3):
        shortened = " ".join(word[:keep] for word in words)
        if len(shortened) <= LONGEST_LABEL:
            return shortened

    ends = f"{words[0][:5]} {words[-1][:5]}"
    return ends[:LONGEST_LABEL].rstrip() or words[0][:LONGEST_LABEL]


def distinct(names: Sequence[str]) -> List[str]:
    """Shorten a set of names so that no two come out the same.

    Two wedges reading the same thing and doing different things is exactly
    what the twelve-character rule was meant to prevent, and shortening alone
    causes it: ``gantry_system_leftmost`` and ``gantry_system_leftish`` both
    become ``gan sys lef``.

    A repeat gets a number, and the number is made room for rather than pushing
    the label over the limit.
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


def _find(node: Assembly, path: str) -> Optional[Assembly]:
    """Walk a dotted path down from a node, as the rest of the tool does."""
    here = node
    for step in path.split("."):
        nxt = None
        for child in [*here.children, *here.additions, *here.subtractions]:
            if child.name == step:
                nxt = child
                break
        if nxt is None:
            return None
        here = nxt
    return here


def resolve(
    context: Context,
    site: Optional[Assembly] = None,
    *,
    site_names: Sequence[str] = (),
    groups: Sequence[str] = (),
    words: Sequence[str] = (),
    device: Optional[Device] = None,
) -> Ring:
    """Work out which options belong on the ring, and hand them back.

    Nothing here changes anything. A chosen option becomes an intent, and the
    intent is what the rest of the program acts on.

    ``device`` is what the page knows about the board under the ring: for a
    node ring, the board pinned to that node, if any; for a device ring, the
    board itself.
    """
    if context.pointing is Pointing.CANVAS:
        return _canvas_ring(context, site, site_names, groups)
    if context.pointing is Pointing.NODE:
        return _node_ring(context, site, words, device)
    if context.pointing is Pointing.SELECTION:
        return _selection_ring(context)
    if context.pointing is Pointing.DEVICE:
        return _device_ring_on_top(context, device)
    return _edge_ring(context)


def _grouped(prefix: str, action: str, names: Sequence[str]) -> Optional[Option]:
    """One option that opens a further ring, or nothing when there is nothing.

    A list of *things* is not a list of verbs. The eight-to-a-ring rule exists
    because nine verbs means the menu was designed wrong, and that argument does
    not carry over to nine arrangements a person happens to have. So a long list
    is split into lettered groups — real grouping, one more press, nothing
    hidden — rather than refused or quietly cut.
    """
    ordered = list(names)
    if not ordered:
        return None
    if len(ordered) <= MOST_OPTIONS:
        return Option(id=prefix, label=shorten(prefix), children=_leaves(action, ordered))

    if len(ordered) > MOST_OPTIONS * MOST_OPTIONS:
        # Two levels of eight hold sixty-four. A third level would just move the
        # problem one press further away; say so instead of pretending.
        raise RingTooFull(
            f"{len(ordered)} things to choose between under {prefix!r}, and two "
            f"levels of grouping hold {MOST_OPTIONS * MOST_OPTIONS}. This needs "
            "searching, not a bigger menu."
        )
    buckets = _bucket(ordered)
    return Option(
        id=prefix,
        label=shorten(prefix),
        children=[
            Option(id=f"{prefix}:group{index}", label=head, children=_leaves(action, members))
            for index, (head, members) in enumerate(buckets)
        ],
    )


def _leaves(action: str, names: Sequence[str]) -> List[Option]:
    """One option per thing, with labels no two of which read the same."""
    return [
        Option(id=f"{action}:{name}", label=label, action=f"{action}:{name}")
        for name, label in zip(names, distinct(names), strict=True)
    ]


def _bucket(names: Sequence[str]) -> List[Tuple[str, List[str]]]:
    """Split a long list into groups of at most eight, in order.

    Each group is named for the first thing in it, so a person can guess where
    to look. A list, not a dictionary keyed by that name: an earlier attempt
    keyed on the first letter, every name began with the same letter, and
    eighteen of twenty things silently vanished into one another. Losing things
    quietly is the failure this whole function exists to avoid.
    """
    ordered = sorted(names)
    per = -(-len(ordered) // MOST_OPTIONS)
    chunks = [ordered[start : start + per] for start in range(0, len(ordered), per)]
    heads = distinct([chunk[0] for chunk in chunks])
    return list(zip(heads, chunks, strict=True))


def _pieces(prefix: str, parent: str, nodes: Sequence[Assembly]) -> Optional[Option]:
    """One option that opens the pieces beneath a node, each choosable by digit.

    The same grouping rule as `_grouped`, but a piece is named by its dotted
    path -- the identity everything else in this tool already uses -- so
    choosing one is `select:<path>`, and the label is the name alone,
    shortened, with no two reading the same. Nothing here is a verb: this is
    the Contents list, reachable from the ring.
    """
    if not nodes:
        return None
    by_name = {node.name: node for node in nodes}
    names = sorted(by_name)
    path_of = {name: f"{parent}.{name}" if parent else name for name in names}

    def leaves(members: Sequence[str]) -> List[Option]:
        return [
            Option(id=f"select:{path_of[name]}", label=label, action=f"select:{path_of[name]}")
            for name, label in zip(members, distinct(members), strict=True)
        ]

    if len(names) <= MOST_OPTIONS:
        return Option(id=prefix, label=shorten(prefix), children=leaves(names))
    if len(names) > MOST_OPTIONS * MOST_OPTIONS:
        raise RingTooFull(
            f"{len(names)} pieces under {parent or 'the root'!r}, and two levels of "
            f"grouping hold {MOST_OPTIONS * MOST_OPTIONS}. This needs searching, not "
            "a bigger menu."
        )
    return Option(
        id=prefix,
        label=shorten(prefix),
        children=[
            Option(id=f"{prefix}:group{index}", label=head, children=leaves(members))
            for index, (head, members) in enumerate(_bucket(names))
        ],
    )


# The panels the world's page registers, in the order the ring seats them
# (cardinals first): what stands in front of the world, each a cell away.
# The page registers exactly these; a test holds the two lists to each other.
PANELS: Sequence[Tuple[str, str]] = (
    ("contents", "Contents"),
    ("selected", "Selected"),
    ("jobs", "Jobs"),
    ("validation", "Validation"),
    ("scad", "OpenSCAD"),
    # Registered by the page's script rather than marked in its markup: the
    # camera panel at start; the machine and its comms log when a printer is
    # opened. The last two share one cell, since a ring holds eight.
    ("camera", "Camera"),
    ("machine", "Machine"),
    ("log", "Comms log"),
)
GROUPED_PANELS = ("machine", "log")


def _panels() -> Option:
    def toggle(pid: str, label: str) -> Option:
        return Option(id=f"panel:{pid}", label=label, action=f"panel:toggle:{pid}")

    plain = [toggle(pid, label) for pid, label in PANELS if pid not in GROUPED_PANELS]
    grouped = [toggle(pid, label) for pid, label in PANELS if pid in GROUPED_PANELS]
    return Option(
        id="panels",
        label="Panels",
        children=plain
        + [Option(id="panel:machine-group", label="Machine", children=grouped)]
        # The rail itself: hidden and shown, as the tilde key does.
        + [Option(id="panel:rail", label="Rail", action="panel:rail:toggle")],
    )


# The camera's verbs, in the order the ring seats them (cardinals first):
# what the camera panel's buttons do, each a cell away from empty canvas.
CAMERA_VERBS: Sequence[Tuple[str, str]] = (
    ("capture", "Capture"),
    ("look", "Look"),
    ("place", "Place"),
    ("gather", "Gather"),
    ("open", "Open as one"),
    ("allow", "Allow"),
    ("unplace", "Unplace"),
)
# What the browser put on this machine, taken back: behind the eighth cell,
# since a ring holds eight. Add opens the file picker; Purge forgets every
# kept picture (captures and uploads, never the folder's own).
KEPT_VERBS: Sequence[Tuple[str, str, bool]] = (
    ("add", "Add", False),
    ("purge", "Purge", True),
)


def _camera() -> Option:
    return Option(
        id="camera",
        label="Camera",
        children=[
            Option(id=f"camera:{verb}", label=label, action=f"camera:{verb}")
            for verb, label in CAMERA_VERBS
        ]
        + [
            Option(
                id="camera:kept",
                label="Kept",
                children=[
                    Option(
                        id=f"camera:{verb}",
                        label=label,
                        action=f"camera:{verb}",
                        destructive=destructive,
                    )
                    for verb, label, destructive in KEPT_VERBS
                ],
            )
        ],
    )


def _canvas_ring(
    context: Context,
    site: Optional[Assembly],
    site_names: Sequence[str],
    groups: Sequence[str],
) -> Ring:
    """The ring on empty canvas: the pieces at this level, the way back up, and the rest.

    `context.targets[0]`, when given, is the path the viewer is zoomed into;
    Pieces lists that node's children and Up steps back out. At the root
    there is no Up, because there is nothing above. Panels opens and closes
    what stands in front of the world.
    """
    focus_path = context.targets[0] if context.targets else ""
    focus = _find(site, focus_path) if site and focus_path else site
    options = [
        option
        for option in (
            _pieces("Pieces", focus_path, focus.children if focus else []),
            Option(id="up", label="Up", action="zoom-out") if focus_path else None,
            _grouped("Site", "site", site_names),
            _grouped("Group", "group", groups),
            Option(id="fit", label="Fit", action="fit"),
            _panels(),
            _camera(),
            Option(id="reset", label="Reset", action="reset", destructive=True),
        )
        if option is not None
    ]
    title = shorten(focus.name) if focus is not None else (shorten(site.name) if site else None)
    return Ring(title=title, options=options)


def _node_ring(
    context: Context,
    site: Optional[Assembly],
    words: Sequence[str],
    device: Optional[Device],
) -> Ring:
    path = context.targets[0] if context.targets else ""
    node = _find(site, path) if site and path else None

    options: List[Option] = [
        Option(id="zoom", label="Zoom in", action="zoom-in"),
        Option(id="move", label="Move", action="move"),
    ]

    # A node with a board pinned to it can be watched, polled and, when the
    # board is a printer, driven. A node with none gets no Device option at
    # all rather than one greyed out.
    if device is not None and device.bound:
        options.append(Option(id="device", label="Device", children=_device_options(device)))

    # A piece built from a picture can be swapped for a different word. Every
    # other node cannot, so the option is simply not there rather than there
    # and greyed out.
    if node is not None and node.role == "word":
        swap = _grouped("Word", "word", words)
        if swap is not None:
            options.append(swap)

    # A part leaf's shape is a thing to get; a machine that is a part with
    # things inside it (a printer holding its board) keeps the ring it had.
    if node is not None and node.part_ref and not node.children:
        options.append(Option(id="stl", label="Get shape", action="render-stl"))

    options.append(Option(id="why", label="Why this", action="explain"))

    # Navigation: the pieces inside this one, and the one it is inside.
    # Selecting, not zooming -- a chosen piece becomes the ring's next subject.
    if node is not None:
        into = _pieces("Into", path, node.children)
        if into is not None:
            options.append(into)
    if "." in path:
        parent = path.rsplit(".", 1)[0]
        options.append(Option(id="up", label="Up", action=f"select:{parent}"))
    return Ring(title=shorten(path or (node.name if node else "")), options=options)


def _selection_ring(context: Context) -> Ring:
    return Ring(
        title=f"{len(context.targets)} chosen",
        options=[
            Option(id="fit", label="Fit to all", action="fit-selection"),
            Option(id="why", label="Why these", action="explain"),
        ],
    )


def _edge_ring(context: Context) -> Ring:
    # Links between arrangements do not exist yet, so an edge can only be
    # explained. When they arrive this ring grows; until then it says what it
    # can rather than pretending.
    return Ring(
        title="Link",
        options=[Option(id="why", label="Why this", action="explain")],
    )


def _device_ring_on_top(context: Context, device: Optional[Device]) -> Ring:
    """The device ring as the top ring, opened on a port rather than a node."""
    if device is None:
        port = context.targets[0] if context.targets else ""
        if not port:
            raise ValueError("a device ring stands on a port, and none was given")
        device = Device(port=port)
    # The port's last path segment: /dev/ttyUSB0 is ttyUSB0 on the ring.
    leaf = device.port.rstrip("/").rsplit("/", 1)[-1] or device.port
    return Ring(title=shorten(leaf), options=_device_options(device))


def _device_options(device: Device) -> List[Option]:
    """What can be done with a board. The pages' existing handlers do each one.

    Pin and Unpin are one cell, since a port is either pinned to this node or
    not. Control appears only for a printer: a board running a sketch has no
    G-code to be driven with.
    """
    options = [
        Option(id="device:watch", label="Watch", action="device:watch"),
        Option(id="device:poll", label="Poll", action="device:poll"),
        Option(id="device:monitor", label="Monitor", action="device:monitor"),
        Option(id="device:query", label="Query", action="device:query"),
        (
            Option(id="device:unpin", label="Unpin", action="device:unpin")
            if device.bound
            else Option(id="device:pin", label="Pin", action="device:pin")
        ),
        Option(id="device:rescan", label="Rescan", action="device:rescan"),
        # The link itself: reopen it, reboot the board on purpose, or hand the
        # port to another program. Before Control on purpose, so its cell is
        # the same on a devkit (no Control) and on a printer.
        Option(
            id="device:link",
            label="Link",
            children=[
                Option(id="device:reconnect", label="Reconnect", action="device:reconnect"),
                Option(id="device:reset", label="Reset", action="device:reset", destructive=True),
                Option(id="device:release", label="Release", action="device:release"),
            ],
        ),
    ]
    if device.printer:
        options.append(Option(id="control", label="Control", children=control_options(device)))
    return options


def control_options(device: Device) -> List[Option]:
    """The control ring: every allowlisted thing a printer can be told to do.

    Each leaf is one line from ``firmware.gcode.CONTROL_CODES``, sent by the
    monitor page's control chain, which is where the latch is checked. Jog is
    seated so the keypad is the jog pad: Y+ up, X+ right, Y- down, X- left,
    and Z+ and Z- in the right-hand corners. Stop is E-STOP and is marked
    destructive, since the board halts until it is reset.
    """
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


def every_action(rings: Sequence[Ring]) -> Dict[str, str]:
    """Every action any of these rings can produce, and the label it wore.

    Used to check the promise that everything the program can be told to do is
    reachable from the ring. A button that can do something the ring cannot is
    the thing that promise forbids.
    """
    found: Dict[str, str] = {}
    seen: Set[int] = set()

    def walk_options(options: Sequence[Option]) -> None:
        for option in options:
            # Options can hold each other, and a ring built by hand can be made
            # to hold itself. Walking that without remembering where you have
            # been runs out of stack rather than reporting anything.
            if id(option) in seen:
                continue
            seen.add(id(option))
            if option.action and option.action not in found:
                found[option.action] = option.label
            if option.children:
                walk_options(option.children)

    for ring in rings:
        walk_options(ring.options)
    return found


class Carries(str, Enum):
    """Who does the thing an option names.

    Written down rather than inferred, because the three are easy to confuse and
    the confusion is silent. An action nobody carries out looks exactly like an
    action the viewer handles: the ring shows a wedge, the wedge can be pressed,
    and nothing happens. Saying which of the three an action is makes "not built
    yet" a report rather than a shrug.
    """

    SERVER = "the server carries it out"
    VIEWER = "the viewer carries it out"
    UNBUILT = "nothing carries it out yet"


class UnknownAction(KeyError):
    """An action no ring should be producing, or one nobody has classified.

    Raised rather than defaulted. A default here would mean a new option added
    to a ring silently becomes whatever the default is, which is the failure
    this whole table exists to prevent.
    """


# Every action any ring can produce, and who carries it out. Actions that name a
# thing -- an arrangement, a word, a group -- are written as their prefix, since
# `site:garage` and `site:bench` are one entry and not two.
#
# The rule for reading this: SERVER means the intent endpoint does it and the
# answer says what changed. VIEWER means the intent endpoint does nothing and
# says so, because the work is where the drawing is. UNBUILT means the option is
# on the ring and there is nothing behind it, which is refused loudly.
CARRIED_BY: Dict[str, Carries] = {
    # The viewer's own business: what is on screen, and where you are looking.
    "fit": Carries.VIEWER,
    "fit-selection": Carries.VIEWER,
    "zoom-in": Carries.VIEWER,
    "zoom-out": Carries.VIEWER,
    # Choosing a piece from the ring is what a click on the Contents list is.
    "select": Carries.VIEWER,
    "explain": Carries.VIEWER,
    # Taking hold of a piece happens under a finger. The commit that follows it
    # is a change to the arrangement and is not on any ring yet -- when it
    # arrives it is its own action, carried by the server.
    "move": Carries.VIEWER,
    # Choosing which arrangement to look at, and which pieces to show, are both
    # about what is on screen rather than what the arrangement is.
    "site": Carries.VIEWER,
    "group": Carries.VIEWER,
    # Discarding every edit and rebuilding from the factory.
    "reset": Carries.SERVER,
    # Turning one node's subtree into a shape.
    "render-stl": Carries.SERVER,
    # A piece built from a picture can be swapped for a different word. The ring
    # offers it because the vocabulary is real; nothing acts on the choice.
    "word": Carries.UNBUILT,
    # A board's verbs. The pages already have a handler for each -- the Device
    # section, the serial overlay and the monitor -- and the ring hands the
    # choice to that handler. The server is reached through the firmware
    # routes those handlers already call, never through the intent route.
    "device": Carries.VIEWER,
    # Driving a printer. Each leaf is one allowlisted G-code line, sent by the
    # monitor page's control chain, which is where the latch is checked and
    # where a refusal is shown. The intent route never opens a port.
    "control": Carries.VIEWER,
    # Reading or probing the bed: the page starts the job and shows the record.
    "level": Carries.VIEWER,
    # Streaming a file: the page starts the job with the file it has chosen.
    "print": Carries.VIEWER,
    # Opening, closing, floating what stands in front of the world (panels.js).
    "panel": Carries.VIEWER,
    # The camera panel's verbs: the browser's cameras, a frame kept here, the
    # pictures gathered -- all of it the page's, none of it the server's alone.
    "camera": Carries.VIEWER,
}


def carried_by(action: str) -> Carries:
    """Who carries out this action. Raises rather than guessing.

    ``site:garage`` is looked up as ``site``. An action nobody has classified is
    an error here rather than a wedge that does nothing.
    """
    if action in CARRIED_BY:
        return CARRIED_BY[action]
    head = action.split(":", 1)[0]
    if head in CARRIED_BY:
        return CARRIED_BY[head]
    raise UnknownAction(
        f"nothing says who carries out {action!r}. Add it to CARRIED_BY, as "
        "itself or as its prefix, and say which of the three it is -- a wedge "
        "nobody classified is a wedge that silently does nothing."
    )


__all__ = [
    "BACK",
    "CARRIED_BY",
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
    "PLACEMENT",
    "Pointing",
    "Ring",
    "RingTooFull",
    "UnknownAction",
    "Where",
    "address_of",
    "carried_by",
    "check_ring",
    "control_options",
    "every_action",
    "every_address",
    "nearest",
    "place",
    "resolve",
    "shorten",
    "walk",
]
