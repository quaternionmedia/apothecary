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

PROTOTYPE — not ratified. See ``docs/plans/edits/apothecary-surface.md``.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Sequence, Set, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .hierarchy import Assembly

MOST_OPTIONS = 8
LONGEST_LABEL = 12


class RingTooFull(ValueError):
    """More options than a ring holds. Group them instead of scrolling them."""


class Pointing(str, Enum):
    """What the ring was opened on."""

    NODE = "node"
    EDGE = "edge"
    CANVAS = "canvas"
    SELECTION = "selection"


class Where(BaseModel):
    """Where on the screen the ring was opened."""

    x: float = 0.0
    y: float = 0.0


class Context(BaseModel):
    """What the ring was opened on, and which things it applies to.

    ``targets`` are the same dotted paths everything else in this tool already
    uses to name a node — ``printer_1.gantry_system`` and so on. No new way of
    naming things was needed, which is worth knowing before anyone invents one.
    """

    pointing: Pointing
    targets: List[str] = Field(default_factory=list)
    where: Where = Field(default_factory=Where)


class Option(BaseModel):
    """One wedge of the ring."""

    id: str
    label: str
    action: Optional[str] = None
    enabled: bool = True
    destructive: bool = False
    children: Optional[List["Option"]] = None

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
        # number at all.
        if children is not None:
            check_ring(children)
        return children

    def model_post_init(self, _context) -> None:
        if (self.action is None) == (self.children is None):
            raise ValueError(
                f"option {self.id!r} must either do something or open a further "
                "ring, and not both or neither"
            )


Option.model_rebuild()


class Ring(BaseModel):
    """One ring of options."""

    model_config = ConfigDict(validate_assignment=True)

    title: Optional[str] = None
    options: List[Option]

    def model_post_init(self, _context) -> None:
        check_ring(self.options)


class Intent(BaseModel):
    """What was chosen. The one thing that reaches the rest of the program.

    Everything that changes anything arrives as one of these, from the ring or
    from anywhere else. One way in is what makes it possible to say that
    everything you can do is reachable from the ring.
    """

    action: str
    context: Context
    option_id: str


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
) -> Ring:
    """Work out which options belong on the ring, and hand them back.

    Nothing here changes anything. A chosen option becomes an intent, and the
    intent is what the rest of the program acts on.
    """
    if context.pointing is Pointing.CANVAS:
        return _canvas_ring(site, site_names, groups)
    if context.pointing is Pointing.NODE:
        return _node_ring(context, site, words)
    if context.pointing is Pointing.SELECTION:
        return _selection_ring(context)
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


def _canvas_ring(
    site: Optional[Assembly], site_names: Sequence[str], groups: Sequence[str]
) -> Ring:
    options = [
        option
        for option in (
            _grouped("Site", "site", site_names),
            _grouped("Group", "group", groups),
            Option(id="fit", label="Fit", action="fit"),
            Option(id="reset", label="Reset", action="reset", destructive=True),
        )
        if option is not None
    ]
    return Ring(title=shorten(site.name) if site else None, options=options)


def _node_ring(context: Context, site: Optional[Assembly], words: Sequence[str]) -> Ring:
    path = context.targets[0] if context.targets else ""
    node = _find(site, path) if site and path else None

    options: List[Option] = [
        Option(id="zoom", label="Zoom in", action="zoom-in"),
        Option(id="move", label="Move", action="move"),
    ]

    # A piece built from a picture can be swapped for a different word. Every
    # other node cannot, so the option is simply not there rather than there
    # and greyed out.
    if node is not None and node.role == "word":
        swap = _grouped("Word", "word", words)
        if swap is not None:
            options.append(swap)

    if node is not None and node.part_ref:
        options.append(Option(id="stl", label="Get shape", action="render-stl"))

    options.append(Option(id="why", label="Why this", action="explain"))
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


def every_action(rings: Sequence[Ring]) -> Dict[str, str]:
    """Every action any of these rings can produce, and the label it wore.

    Used to check the promise that everything the program can be told to do is
    reachable from the ring. A button that can do something the ring cannot is
    the thing that promise forbids.
    """
    found: Dict[str, str] = {}
    seen: Set[int] = set()

    def walk(options: Sequence[Option]) -> None:
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
                walk(option.children)

    for ring in rings:
        walk(ring.options)
    return found


__all__ = [
    "Context",
    "Intent",
    "LONGEST_LABEL",
    "MOST_OPTIONS",
    "Option",
    "Pointing",
    "Ring",
    "RingTooFull",
    "Where",
    "check_ring",
    "every_action",
    "resolve",
    "shorten",
]
