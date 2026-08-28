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
- `ring` — the one ring of options. The destination. **Nothing is filed here
  yet**, which is the honest state of the work.
- `automatic` — the page reacting to itself. Nobody told it anything.

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
- The drawing library brings its own listeners — turning and sliding the view by
  dragging are real and are not in this count and cannot be.
- It is one page. Anything a person can command from elsewhere — the command
  line, a request made straight to the machine — is not in this number.
- It refuses when it finds nothing, because a page it failed to read and a page
  with no controls must not produce the same answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

VIEWER = Path(__file__).resolve().parents[1] / "templates" / "fractal_viewer.html.j2"

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
    "job-submit": (WIDGET, WHAT_IS_THERE, "the button that makes the job"),
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
    # Made by the page as it goes, rather than written into it. Found by the
    # listening scan below, and named here so both scans agree on what exists.
    "category-chip": (LIST, WHAT_YOU_SEE, "a row of buttons, one per word, that fold and unfold"),
    "tree-caret": (LIST, WHAT_YOU_SEE, "the arrow that opens a branch of the list"),
    "contents-item": (LIST, WHAT_YOU_SEE, "a row of the list of pieces"),
    "breadcrumb": (LIST, WHAT_YOU_SEE, "the trail back to where you came from"),
}

MARKUP = re.compile(
    r"<(select|input|button|textarea|form|a)\b([^>]*)>",
    re.IGNORECASE,
)
HAS_ID = re.compile(r"\bid=[\"']([\w-]+)[\"']")
HAS_CLASS = re.compile(r"\bclass=[\"']([^\"']+)[\"']")
IS_SUBMIT = re.compile(r"\btype=[\"']submit[\"']")
HAS_HREF = re.compile(r"\bhref=")

# A markup control with neither an id nor a class this file knows is named by
# hand, because there is nothing else to call it.
BY_SHAPE: Sequence[Tuple[re.Pattern, str]] = (
    (IS_SUBMIT, "job-submit"),
    (HAS_HREF, "part-scad-download"),
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
    # the page reacting to itself
    "window:resize:onResize": (AUTOMATIC, NOTHING, "the window changed size on its own"),
}

LISTENS = re.compile(r"addEventListener\s*\(\s*['\"]([\w-]+)['\"]\s*,")

# Fetched by the label they carry in the page rather than by a plain name.
# Searched only within the current statement, never across one, so a mention in
# the line above cannot claim a listener that is not its own.
FETCHED_BY_LABEL: Sequence[Tuple[str, str]] = (
    (r"\.job-(assign|complete)-btn", "jobBtn"),
    (r"pos-\$\{axis\}", "posAxis"),
    (r"part-regenerate-btn", "regenerateBtn"),
    (r"\.zoom-in-btn", "zoomInLink"),
)

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

    def sentence(self) -> str:
        own = len(self.controls_of_its_own())
        listening = [f for f in self.found if f.how == "listening"]
        return (
            f"{own} controls of its own. "
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
    found = LAST_WORD.search(trimmed)
    return found.group(1) if found else "?"


def _verb_in(handler: str) -> str:
    """The first thing the handler actually does."""
    for call in A_CALL.finditer(handler):
        word = call.group(1)
        if word not in PLUMBING:
            return word
    return NO_CALL


def _name_in_markup(attributes: str) -> Optional[str]:
    found = HAS_ID.search(attributes)
    if found:
        return found.group(1)
    for pattern, name in BY_SHAPE:
        if pattern.search(attributes):
            return name
    found = HAS_CLASS.search(attributes)
    if found:
        return found.group(1).split()[0]
    return None


def _line_of(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def _from_markup(text: str) -> Tuple[List[Found], List[str]]:
    found: List[Found] = []
    unknown: List[str] = []
    for match in MARKUP.finditer(text):
        tag, attributes = match.group(1).lower(), match.group(2)
        name = _name_in_markup(attributes)
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
            )
        )
    return found, unknown


def take(page: Path | None = None) -> Census:
    """Count what a person can operate, from the page itself."""
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
                lines.append(f"    line {entry.line:>5}  {entry.effect:<14}  {entry.description}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
