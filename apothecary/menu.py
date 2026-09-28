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
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

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


class CameraSeen(BaseModel):
    """A camera as the page names it: this browser's device, or a pin's record."""

    id: str
    label: str = "camera"


class ShapeSeen(BaseModel):
    """One shape of a drawn look: its index, its word, and whether it is made."""

    index: int
    word: str = "shape"
    status: str = "found"  # found | made | already_made


class LookSeen(BaseModel):
    """A look at the place the ring stands on, as the page has it drawn."""

    id: str
    picture: str = ""
    finder: str = "plain"
    sized: bool = False
    kept: bool = False  # its picture is one the browser kept, so it can be forgotten
    shapes: List[ShapeSeen] = Field(default_factory=list)


class Place(BaseModel):
    """The place the ring stands on -- a host, or on the canvas ring the floor:
    its camera's pin, whether that camera is live, and its looks, newest first."""

    camera: Optional[CameraSeen] = None
    live: bool = False
    looks: List[LookSeen] = Field(default_factory=list)
    drawn: Optional[str] = None
    chosen_look: Optional[str] = None


class PictureContext(BaseModel):
    """What the resolver is told about pictures, as it is told a Device.

    Told rather than looked up: ``cameras`` are this browser's (``asked`` once
    the browser has been allowed to name them), ``pictures`` the ones under the
    picture root, newest first, and ``here`` the place the ring stands on. The
    intent route fills in ``made`` (the site's made pieces), ``words`` (the
    vocabulary) and ``finders`` (those that can read the drawn look's picture)
    from what the server knows, so a page cannot claim them."""

    cameras: List[CameraSeen] = Field(default_factory=list)
    asked: bool = False
    pictures: List[str] = Field(default_factory=list)
    chosen_picture: Optional[str] = None
    finders: List[str] = Field(default_factory=list)
    made: List[str] = Field(default_factory=list)
    words: List[str] = Field(default_factory=list)
    here: Place = Field(default_factory=Place)


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


def shorten(text: str) -> str:
    """Make a label fit, without trailing it off.

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
    device: Optional[Device] = None,
    picture: Optional[PictureContext] = None,
) -> Ring:
    """Work out which options belong on the ring, and hand them back.

    ``device`` is what the page knows about the board under the ring: for a
    node ring, the board pinned to that node, if any; for a device ring, the
    board itself. ``picture`` is what it knows about pictures and cameras
    (``PictureContext``); without one, a host still offers Camera and Picture,
    with nothing pinned, drawn or listed.
    """
    picture = picture or PictureContext()
    if context.pointing is Pointing.CANVAS:
        return _canvas_ring(context, site, site_names, groups, picture)
    if context.pointing is Pointing.NODE:
        return _node_ring(context, site, device, picture)
    if context.pointing is Pointing.DEVICE:
        return _device_ring_on_top(context, device)
    raise ValueError(f"no ring is built for {context.pointing!r}")


def _grouped(
    prefix: str, names: Sequence[str], action_of: Callable[[str], str]
) -> Optional[Option]:
    """One option that opens a ring of names, or nothing when there are none.

    Each name is a leaf whose id and action are ``action_of(name)``, labelled
    so that no two read the same. A list of things is not a list of verbs, so
    more than eight are split into groups of at most eight -- one more press,
    nothing hidden -- and more than two levels of eight can hold is refused.
    """
    ordered = list(names)
    if not ordered:
        return None

    def leaves(members: Sequence[str]) -> List[Option]:
        return [
            Option(id=action_of(name), label=label, action=action_of(name))
            for name, label in zip(members, distinct(members), strict=True)
        ]

    if len(ordered) <= MOST_OPTIONS:
        return Option(id=prefix, label=shorten(prefix), children=leaves(ordered))
    if len(ordered) > MOST_OPTIONS * MOST_OPTIONS:
        raise RingTooFull(
            f"{len(ordered)} to choose between under {prefix!r}, and two levels "
            f"of grouping hold {MOST_OPTIONS * MOST_OPTIONS}. This needs "
            "searching, not a bigger menu."
        )
    return Option(
        id=prefix,
        label=shorten(prefix),
        children=[
            Option(id=f"{prefix}:group{index}", label=head, children=leaves(members))
            for index, (head, members) in enumerate(_bucket(ordered))
        ],
    )


def _pieces(prefix: str, parent: str, node: Optional[Assembly]) -> Optional[Option]:
    """The pieces directly inside a node; choosing one is ``select:<its dotted path>``."""
    names = sorted({child.name for child in node.children}) if node is not None else []
    return _grouped(
        prefix, names, lambda name: f"select:{parent}.{name}" if parent else f"select:{name}"
    )


def _bucket(names: Sequence[str]) -> List[Tuple[str, List[str]]]:
    """Split a long list into groups of at most eight, in order.

    Each group is named for the first thing in it, so a person can guess where
    to look. A list rather than a dictionary keyed by that name, so two groups
    that would share a name cannot swallow each other.
    """
    ordered = sorted(names)
    per = -(-len(ordered) // MOST_OPTIONS)
    chunks = [ordered[start : start + per] for start in range(0, len(ordered), per)]
    heads = distinct([chunk[0] for chunk in chunks])
    return list(zip(heads, chunks, strict=True))


# The panels the world's page registers, in the order the ring seats them
# (cardinals first): what stands in front of the world, each a cell away.
# The page registers exactly these; a test holds the two lists to each other.
PANELS: Sequence[Tuple[str, str]] = (
    ("contents", "Contents"),
    ("selected", "Selected"),
    ("jobs", "Jobs"),
    ("validation", "Validation"),
    ("scad", "OpenSCAD"),
    # Registered by the page's script rather than marked in its markup: Kept
    # (every pin and kept picture, each taken back from its row) and what is
    # left of the camera panel, the gathering, at start; the machine and its
    # comms log when a printer is opened. Each pair shares one cell, since a
    # ring holds eight.
    ("kept", "Kept"),
    ("camera", "Gather"),
    ("machine", "Machine"),
    ("log", "Comms log"),
)
# The cells that hold two panels each, in the order they are seated after the
# plain ones: (id, label, the panels behind it).
PANEL_GROUPS: Sequence[Tuple[str, str, Tuple[str, ...]]] = (
    ("panel:pictures-group", "Pictures", ("kept", "camera")),
    ("panel:machine-group", "Machine", ("machine", "log")),
)
GROUPED_PANELS = tuple(pid for _, _, pids in PANEL_GROUPS for pid in pids)


def _panels() -> Option:
    def toggle(pid: str, label: str) -> Option:
        return Option(id=f"panel:{pid}", label=label, action=f"panel:toggle:{pid}")

    labels = dict(PANELS)
    plain = [toggle(pid, label) for pid, label in PANELS if pid not in GROUPED_PANELS]
    groups = [
        Option(id=gid, label=glabel, children=[toggle(pid, labels[pid]) for pid in pids])
        for gid, glabel, pids in PANEL_GROUPS
    ]
    return Option(
        id="panels",
        label="Panels",
        children=plain
        + groups
        # The rail itself: hidden and shown, as the tilde key does.
        + [Option(id="panel:rail", label="Rail", action="panel:rail:toggle")],
    )


# --- pictures and cameras -------------------------------------------------------------
#
# A camera and a picture are pinned at a *host* -- a root structure with a
# footprint that is not a made piece -- or at the site's floor. A host's node
# ring appends Camera and Picture; the floor's are reached from the canvas
# ring's Pictures › Floor, since the floor is a selection but not a node. A
# floor verb carries the floor in its action, as ``@floor`` after its last
# colon; a host's verb names its host by the ring's target. A verb about one
# look names the look, which knows its own host.

FLOOR_MARK = "@floor"
# A list of pictures or looks shows the seven newest; the eighth cell acts on
# the one chosen in the panel that holds the rest, or opens that panel.
NEWEST = MOST_OPTIONS - 1


def _chunks(items: Sequence, most_groups: int) -> List[List]:
    """Split a list, in order, into at most ``most_groups`` groups of at most eight."""
    per = max(-(-len(items) // most_groups), 1)
    if per > MOST_OPTIONS:
        raise RingTooFull(
            f"{len(items)} to choose between, and {most_groups} groups of "
            f"{MOST_OPTIONS} hold {most_groups * MOST_OPTIONS}. This needs searching, "
            "not a bigger menu."
        )
    return [list(items[start : start + per]) for start in range(0, len(items), per)]


def _listed(
    group_id: str,
    leaves: Sequence[Tuple[str, str]],
    *,
    first: Sequence[Option] = (),
) -> List[Option]:
    """Options ``first``, then one leaf per ``(action, name)``, labelled so no two
    read the same; grouped, each group named for its first, when the leaves do
    not fit beside ``first`` in one ring."""
    room = MOST_OPTIONS - len(first)
    labels = distinct([name for _, name in leaves])
    made = [
        Option(id=action, label=label, action=action)
        for (action, _), label in zip(leaves, labels, strict=True)
    ]
    if len(made) <= room:
        return [*first, *made]
    groups = _chunks(made, room)
    heads = distinct([group[0].label for group in groups])
    return [
        *first,
        *(
            Option(id=f"{group_id}:group{i}", label=head, children=group)
            for i, (head, group) in enumerate(zip(heads, groups, strict=True))
        ),
    ]


def _stem(path: str) -> str:
    """A picture's name without its folder or its suffix, for a label."""
    name = path.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[0] if "." in name else name


def _is_host(site: Optional[Assembly], path: str, made: Sequence[str]) -> bool:
    """A root structure with a footprint that is not a made piece."""
    if site is None or not path or "." in path or path in made:
        return False
    node = next((c for c in site.children if c.name == path), None)
    return node is not None and node.world_bounds() is not None


def _camera_group(picture: PictureContext, floor: bool) -> Option:
    """Camera: Pin here › this browser's cameras (Allow until it has been asked),
    Live or Still, Look, Keep, Unpin. Live, Look and Keep only when the camera
    pinned here is one of this browser's: a pin is a device of one origin."""
    tail = f":{FLOOR_MARK}" if floor else ""
    here = picture.here
    mine = {c.id for c in picture.cameras}
    if picture.asked and picture.cameras:
        pin = _listed(
            f"camera:pin{tail}",
            [(f"camera:pin:{c.id}{tail}", c.label or "camera") for c in picture.cameras],
        )
    else:
        pin = [Option(id=f"camera:allow{tail}", label="Allow", action=f"camera:allow{tail}")]
    options = [Option(id=f"camera:pin{tail}", label="Pin here", children=pin)]
    if here.camera is not None and here.camera.id in mine:
        options.append(
            Option(id=f"camera:still{tail}", label="Still", action=f"camera:still{tail}")
            if here.live
            else Option(id=f"camera:live{tail}", label="Live", action=f"camera:live{tail}")
        )
        options.append(Option(id=f"camera:look{tail}", label="Look", action=f"camera:look{tail}"))
        options.append(Option(id=f"camera:keep{tail}", label="Keep", action=f"camera:keep{tail}"))
    if here.camera is not None:
        options.append(
            Option(id=f"camera:unpin{tail}", label="Unpin", action=f"camera:unpin{tail}")
        )
    return Option(id=f"camera{tail}", label="Camera", children=options)


def _picture_group(picture: PictureContext, floor: bool) -> Optional[Option]:
    """Picture at a host or the floor: Add (a host's; the floor's is Pictures ›
    Add), Folder › the newest pictures, and with
    a look drawn here, Looks › the newest looks, Make › Make all and each found
    shape (once the look has a width), Size, Find › another finder, Unpin, and
    Forget for a picture the browser kept. Eight at the most."""
    tail = f":{FLOOR_MARK}" if floor else ""
    here = picture.here
    # The floor's Add is the canvas ring's Pictures › Add, one ring up: an action
    # has one address.
    options = [] if floor else [Option(id="picture:add", label="Add", action="picture:add")]

    pictures = list(picture.pictures)
    if pictures:
        leaves = [(f"picture:pin:{p}{tail}", _stem(p)) for p in pictures[:NEWEST]]
        if len(pictures) > NEWEST:
            chosen = picture.chosen_picture
            if chosen and chosen not in pictures[:NEWEST]:
                leaves.append((f"picture:pin:{chosen}{tail}", _stem(chosen)))
            else:
                leaves.append((f"picture:kept{tail}", "More"))
        options.append(
            Option(
                id=f"picture:folder{tail}",
                label="Folder",
                children=_listed(f"picture:folder{tail}", leaves),
            )
        )

    drawn = next((lk for lk in here.looks if lk.id == here.drawn), None)
    if drawn is None and here.looks:
        drawn = here.looks[0]
    if drawn is None:
        return Option(id=f"picture{tail}", label="Picture", children=options) if options else None

    if len(here.looks) > 1:
        leaves = [
            (f"picture:draw:{lk.id}", _stem(lk.picture) or lk.id) for lk in here.looks[:NEWEST]
        ]
        if len(here.looks) > NEWEST:
            chosen_look = next(
                (lk for lk in here.looks[NEWEST:] if lk.id == here.chosen_look), None
            )
            leaves.append(
                (f"picture:draw:{chosen_look.id}", _stem(chosen_look.picture) or chosen_look.id)
                if chosen_look is not None
                else (f"picture:looks{tail}", "In Selected")
            )
        options.append(
            Option(
                id=f"picture:looks-group{tail}",
                label="Looks",
                children=_listed(f"picture:looks-group{tail}", leaves),
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
    options.append(Option(id=f"picture:size{tail}", label="Size", action=f"picture:size{tail}"))
    others = [f for f in picture.finders if f != drawn.finder]
    if len(picture.finders) > 1 and others:
        options.append(
            Option(
                id=f"picture:find-group{tail}",
                label="Find",
                children=_listed(
                    f"picture:find-group{tail}", [(f"picture:find:{f}{tail}", f) for f in others]
                ),
            )
        )
    options.append(Option(id=f"picture:unpin{tail}", label="Unpin", action=f"picture:unpin{tail}"))
    if drawn.kept:
        options.append(
            Option(
                id=f"picture:forget{tail}",
                label="Forget",
                action=f"picture:forget{tail}",
                destructive=True,
            )
        )
    return Option(id=f"picture{tail}", label="Picture", children=options)


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
    options.append(Option(id="picture:drop", label="Drop", action="picture:drop", destructive=True))
    return Option(id="picture", label="Picture", children=options)


def _pictures(picture: PictureContext) -> Option:
    """The canvas ring's Pictures, in the seat its Camera had: Add (pinned at the
    floor), Floor › Fit, Camera, Picture (the floor's own verbs), Purge, and
    Gather, the gathering's report, until gathering leaves core."""
    return Option(
        id="pictures",
        label="Pictures",
        children=[
            Option(id="pictures:add", label="Add", action=f"picture:add:{FLOOR_MARK}"),
            Option(
                id="pictures:floor",
                label="Floor",
                children=[
                    option
                    for option in (
                        Option(id="floor:fit", label="Fit", action=f"fit:{FLOOR_MARK}"),
                        _camera_group(picture, floor=True),
                        _picture_group(picture, floor=True),
                    )
                    if option is not None
                ],
            ),
            Option(id="picture:purge", label="Purge", action="picture:purge", destructive=True),
            Option(id="camera:gather", label="Gather", action="camera:gather"),
        ],
    )


def _canvas_pieces(
    prefix: str, focus_path: str, focus: Optional[Assembly], made: Sequence[str]
) -> Optional[Option]:
    """Pieces at this level. At the top, the pieces made from pictures are one
    grouped Made cell after the code's own, so they cannot crowd the ring out."""
    made_here = sorted(
        {c.name for c in focus.children if c.name in set(made)} if focus is not None else set()
    )
    if focus_path or focus is None or not made_here:
        return _pieces(prefix, focus_path, focus)
    names = sorted({c.name for c in focus.children if c.name not in set(made_here)})
    made_cell = _grouped("Made", made_here, lambda name: f"select:{name}")
    assert made_cell is not None
    children = _listed(prefix, [(f"select:{n}", n) for n in names], first=[])
    if len(children) >= MOST_OPTIONS:
        groups = _chunks(names, MOST_OPTIONS - 1)
        heads = distinct([group[0] for group in groups])
        children = [
            Option(
                id=f"{prefix}:group{i}",
                label=head,
                children=_listed(f"{prefix}:group{i}", [(f"select:{n}", n) for n in group]),
            )
            for i, (head, group) in enumerate(zip(heads, groups, strict=True))
        ]
    return Option(id=prefix, label=shorten(prefix), children=[*children, made_cell])


def _canvas_ring(
    context: Context,
    site: Optional[Assembly],
    site_names: Sequence[str],
    groups: Sequence[str],
    picture: PictureContext,
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
            _canvas_pieces("Pieces", focus_path, focus, picture.made),
            Option(id="up", label="Up", action="zoom-out") if focus_path else None,
            _grouped("Site", site_names, lambda name: f"site:{name}"),
            _grouped("Group", groups, lambda name: f"group:{name}"),
            Option(id="fit", label="Fit", action="fit"),
            _panels(),
            _pictures(picture),
            Option(id="reset", label="Reset", action="reset", destructive=True),
        )
        if option is not None
    ]
    title = shorten(focus.name) if focus is not None else (shorten(site.name) if site else None)
    return Ring(title=title, options=options)


def _node_ring(
    context: Context,
    site: Optional[Assembly],
    device: Optional[Device],
    picture: PictureContext,
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

    options.append(Option(id="why", label="Why this", action="explain"))

    # Navigation: the pieces inside this one, and the one it is inside.
    # Selecting, not zooming -- a chosen piece becomes the ring's next subject.
    into = _pieces("Into", path, node)
    if into is not None:
        options.append(into)
    if "." in path:
        parent = path.rsplit(".", 1)[0]
        options.append(Option(id="up", label="Up", action=f"select:{parent}"))

    # Appended after every cell the ring had, so none of them moves: a host
    # holds a camera and looks; a made piece has its word and can be dropped.
    if _is_host(site, path, picture.made):
        options.append(_camera_group(picture, floor=False))
        host_pictures = _picture_group(picture, floor=False)
        assert host_pictures is not None  # a host's always holds Add
        options.append(host_pictures)
    elif path and "." not in path and path in picture.made:
        options.append(_made_picture_group(picture))
    # A part, or a piece made from a picture, is edited in Selected: Part › Edit
    # opens the one editor there (the part-editing spike's decision). Appended
    # last, so no cell above moves; a host with a board, children and a part
    # is the fullest node ring, eight.
    if node is not None and (node.part_ref or (path and "." not in path and path in picture.made)):
        options.append(
            Option(
                id="part",
                label="Part",
                children=[Option(id="part:edit", label="Edit", action="part:edit")],
            )
        )
    return Ring(title=shorten(path or (node.name if node else "")), options=options)


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
    # A camera's verbs: this browser's device pinned, live, a frame kept or
    # looked at, and the gathering's report -- all of it the page's: the pin
    # and the picture routes are what the page calls.
    "camera": Carries.VIEWER,
    # A picture's verbs that choose, draw, find, size or pin: what is on screen,
    # or data attached to a host that no site sees.
    "picture": Carries.VIEWER,
    # Those that add, remove or rebuild a root structure change the arrangement,
    # as a reset does: the intent route carries them, calling the functions the
    # look routes call (apothecary/vision/looks.py's make, drop and rebuild).
    "picture:make": Carries.SERVER,
    "picture:make-all": Carries.SERVER,
    "picture:drop": Carries.SERVER,
    "picture:word": Carries.SERVER,
    # The part editor is the page's: Part › Edit opens it in Selected and puts
    # the cursor in its first control. What Apply then changes goes through the
    # part and made routes the editor already calls, never the intent route.
    "part": Carries.VIEWER,
}


def carried_by(action: str) -> Carries:
    """Who carries out this action; ``site:garage`` is looked up as ``site``.

    The longest classified prefix wins, so ``picture:make:look_1:2`` is
    ``picture:make``'s and ``picture:draw:look_1`` is ``picture``'s.

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
    "LookSeen",
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
