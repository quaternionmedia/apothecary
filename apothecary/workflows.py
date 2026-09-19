"""How many things a person has to type to get one job done.

The other half of the census. `census.py` counts the controls the viewer puts on
screen; this counts the commands a person types when there is no control at all,
which is the same question asked of the other surface.

**Why a count.** A page of ordered commands is a workflow that nobody
implemented: the moment it exists its correctness depends on the reader, and
readers do not run in CI. The rule this answers puts its teeth in a number
rather than a prohibition — each named workflow records what it costs a person
to walk, kept beside the workflow, and **a rise without a stated reason is a
regression**. A command line is legitimate and often necessary; a command line
that is the *only* way through is a design that stopped before the part that was
hard.

**And a count creates work.** Doing a needed thing by typing is a diagnosis, not
a delivery. Where a workflow is carried by nothing but typing, that is written
down here as an open item naming the workflow — not a commitment to build it, a
fact about where the interface stops. Every workflow below with nothing in its
`carried_by` is one of those items, and :func:`only_typed` lists them.

**What this cannot see.** It reads a table written by hand. Nothing checks that
the steps listed are the steps a person actually types, or that a workflow
exists at all — only that the table and the recorded numbers agree with each
other. A workflow nobody wrote down is invisible to it, which is the failure to
watch for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

# What carries a workflow, other than a person typing it.
A_RING = "the ring"
A_PAGE = "a page in the viewer"
NOTHING = "nothing — only typing"

CARRIERS = (A_RING, A_PAGE, NOTHING)


@dataclass(frozen=True)
class Workflow:
    """One named job, and what it costs a person to get through it."""

    name: str
    what_for: str
    steps: Tuple[str, ...]
    carried_by: str
    why_so_many: str = ""

    @property
    def typed(self) -> int:
        return len(self.steps)

    @property
    def only_typed(self) -> bool:
        return self.carried_by == NOTHING


# Every named workflow this tool has, and what each costs.
#
# The numbers are the point. They are not a target and they are not a budget —
# they are a baseline, so that a rise has to be explained rather than merely
# happening.
WORKFLOWS: Tuple[Workflow, ...] = (
    Workflow(
        name="look at one picture",
        what_for="see what shapes are in a photograph before doing anything with it",
        steps=("apothecary photo look picture.png",),
        carried_by=NOTHING,
    ),
    Workflow(
        name="build one arrangement from one picture",
        what_for="turn a photograph into pieces you could print",
        steps=("apothecary photo build picture.png --width-mm 800 --out bench.scad",),
        carried_by=NOTHING,
    ),
    Workflow(
        name="look at one picture in the viewer",
        what_for="walk into the pieces a photograph produced",
        steps=("apothecary photo view picture.png --width-mm 800",),
        carried_by=A_PAGE,
    ),
    Workflow(
        name="sort a folder of photographs",
        what_for="find out which photographs are of the same thing",
        steps=("apothecary photo gather ~/pictures --map-to went.html",),
        carried_by=NOTHING,
    ),
    Workflow(
        name="answer what the sorting could not work out",
        what_for=(
            "tell it the things you can see and it cannot, and have your word "
            "carry through everything that follows"
        ),
        steps=(
            "apothecary photo gather ~/pictures --ask questions.txt",
            "(open questions.txt and answer it)",
            "apothecary photo gather ~/pictures --answers questions.txt --view",
        ),
        carried_by=NOTHING,
        why_so_many=(
            "the middle step is a person reading and deciding, which is the one "
            "step that should exist. The two around it are the interface that is "
            "missing: there is nowhere to be asked a question and answer it in "
            "the same place, so a file is carried out and back by hand"
        ),
    ),
    Workflow(
        name="see how well the sorting does",
        what_for="check the numbers any claim about it rests on",
        steps=("apothecary photo gather-check --each 3",),
        carried_by=NOTHING,
    ),
    Workflow(
        name="count what this asks of a person",
        what_for="the meter for both of these surfaces",
        steps=("apothecary census",),
        carried_by=NOTHING,
    ),
    Workflow(
        name="make the walkthrough and its pictures",
        what_for="produce the demonstration, out of a run that had to be correct",
        steps=("apothecary docs generate",),
        carried_by=NOTHING,
    ),
)


# What each workflow cost when it was last written down. A rise is a regression
# and has to be explained; a fall is an improvement and should move this table.
RECORDED: Dict[str, int] = {
    "look at one picture": 1,
    "build one arrangement from one picture": 1,
    "look at one picture in the viewer": 1,
    "sort a folder of photographs": 1,
    "answer what the sorting could not work out": 3,
    "see how well the sorting does": 1,
    "count what this asks of a person": 1,
    "make the walkthrough and its pictures": 1,
}


class Undeclared(Exception):
    """A workflow exists that nothing in the table accounts for, or the reverse."""


@dataclass
class Census:
    """What the whole set costs, and what it owes."""

    workflows: Tuple[Workflow, ...] = field(default_factory=tuple)

    @property
    def typed(self) -> int:
        return sum(one.typed for one in self.workflows)

    def only_typed(self) -> List[Workflow]:
        """The workflows nothing but typing carries.

        Each of these is an open item: a person doing a needed thing by typing
        that an interface could reasonably have carried. Listing them is the
        whole obligation — building them is a separate decision.
        """
        return [one for one in self.workflows if one.only_typed]

    def risen(self) -> List[Tuple[Workflow, int]]:
        """Workflows that now cost more than was written down."""
        return [
            (one, RECORDED[one.name])
            for one in self.workflows
            if one.name in RECORDED and one.typed > RECORDED[one.name]
        ]

    def sentence(self) -> str:
        return (
            f"{len(self.workflows)} named workflow(s), {self.typed} typed step(s) "
            f"between them. {len(self.only_typed())} of them are carried by "
            "nothing but typing."
        )


def take(workflows: Sequence[Workflow] = WORKFLOWS) -> Census:
    """Count what the named workflows cost, refusing a table that disagrees with itself."""
    named = [one.name for one in workflows]
    twice = sorted({name for name in named if named.count(name) > 1})
    if twice:
        raise Undeclared(
            f"more than one workflow is called {twice[0]!r}. Names are how the "
            "recorded costs are matched to workflows, so two sharing one makes "
            "the whole table ambiguous."
        )
    for one in workflows:
        if one.carried_by not in CARRIERS:
            raise Undeclared(
                f"{one.name!r} says it is carried by {one.carried_by!r}, which is "
                f"not one of {', '.join(CARRIERS)}."
            )
        if not one.steps:
            raise Undeclared(
                f"{one.name!r} lists no steps. A workflow that costs nothing to "
                "walk has not been described."
            )
    missing = sorted(set(named) - set(RECORDED))
    stale = sorted(set(RECORDED) - set(named))
    if missing or stale:
        raise Undeclared(
            (f"no cost is recorded for: {', '.join(missing)}. " if missing else "")
            + (
                f"a cost is recorded for workflows that do not exist: {', '.join(stale)}. "
                if stale
                else ""
            )
            + "The recorded costs are the baseline a rise is measured against, so "
            "a workflow missing from them is a workflow whose cost cannot rise."
        )
    return Census(workflows=tuple(workflows))


def report(workflows: Sequence[Workflow] = WORKFLOWS) -> str:
    """The typed-step count, as something to read."""
    census = take(workflows)
    lines = [census.sentence(), ""]

    lines.append("What a person types, per job")
    for one in sorted(census.workflows, key=lambda w: (-w.typed, w.name)):
        mark = "" if not one.only_typed else "   <- only typing"
        lines.append(f"  {one.typed}  {one.name}{mark}")
        for step in one.steps:
            lines.append(f"       {step}")
        if one.why_so_many:
            lines.append(f"       why: {one.why_so_many}")
    lines.append("")

    risen = census.risen()
    if risen:
        lines.append("Cost more than was written down — this is a regression")
        for one, was in risen:
            lines.append(f"  {one.name}: was {was}, now {one.typed}")
        lines.append("")

    owed = census.only_typed()
    if owed:
        lines.append("Carried by nothing but typing — one open item each")
        lines.append("  Not a commitment to build these. A fact about where the")
        lines.append("  interface stops, written down where it can be argued with.")
        for one in owed:
            lines.append(f"  {one.name} — {one.what_for}")
        lines.append("")

    lines.append("What this cannot see")
    lines.append("  It reads a table written by hand. A workflow nobody wrote down")
    lines.append("  is invisible to it, and nothing checks that the steps listed are")
    lines.append("  the steps a person actually types.")
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "A_PAGE",
    "A_RING",
    "CARRIERS",
    "Census",
    "NOTHING",
    "RECORDED",
    "Undeclared",
    "WORKFLOWS",
    "Workflow",
    "report",
    "take",
]
