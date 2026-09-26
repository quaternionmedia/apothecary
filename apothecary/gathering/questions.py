"""Working out which questions are worth a person's attention.

Two hundred photographs is nineteen thousand nine hundred pairs. Nobody is going
to look at those. But a person does not need to: most pairs are obviously
unrelated, most of the rest the machine can settle on its own, and what is left
is a short list of genuinely hard ones — and among those, a handful whose answers
would settle all the others.

Finding that handful is arithmetic, which is the machine's half of this
arrangement. Answering them is looking at two photographs and knowing, which is
the person's half.

## What makes one question worth more than another

**How much it settles.** If four photographs are already grouped together and
three others are, then one answer joining the two groups settles twelve pairs at
once. An answer about two photographs that are each on their own settles one.
That number is worked out here and put in front of the person, because "this one
question is worth twelve" is the difference between a chore and a good use of a
minute.

**Whether there is anything to look at.** A pair with nothing in common is not a
hard question, it is an easy no, and asking it wastes the person's attention. So
pairs where the machine found *something* and could not make up its mind come
first — those are the ones where a person's glance beats every sum in this
package.

**How close the machine came.** Where two pairs settle the same amount, the one
the machine nearly answered is asked first: it is more likely to be a real
relationship, and it is the one where the answer teaches the most about where the
machine's judgement gives out.

## What it deliberately does not do

It does not rank by how *confident* the machine is that the answer is yes. That
would ask the easy ones first and leave a person confirming what the machine
already knew, which is checking rather than cooperating, and the whole point here
is that a person is not a rubber stamp for arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from .models import CANNOT_TELL, Gathering, Kinship

# Asking about a pair with nothing at all in common is asking a person to confirm
# a machine's easy no. Those go to the back of the queue.
NOTHING_IN_COMMON = 0


@dataclass(frozen=True)
class Question:
    """One thing worth asking a person."""

    left: str
    right: str
    settles: int
    shared: int
    because: str
    against: str

    def sentence(self) -> str:
        return f"Are {self.left} and {self.right} photographs of the same thing?"

    def worth(self) -> str:
        if self.settles <= 1:
            return "Answering this settles this pair and nothing else."
        return f"Answering this settles {self.settles} pairs at once."

    def answer_lines(self) -> List[str]:
        """The sentences a person could write, ready to uncomment."""
        return [
            f"# {self.left} and {self.right} are the same thing",
            f"# {self.left} and {self.right} are parts of one thing",
            f"# {self.left} and {self.right} are not related",
        ]


def _same_thing_groups(gathering: Gathering) -> Dict[str, Tuple[str, ...]]:
    """Which pictures each picture is already *the same thing* as.

    Not which cluster it is in. A cluster can be a larger thing built out of
    several separate groups, and answering "these two are the same thing" merges
    the groups, not the whole composite. Reading the composite size here made the
    valuable questions look worthless and the cheap ones look valuable — it
    reported a question worth four as worth one and sorted it last.
    """
    belongs: Dict[str, Tuple[str, ...]] = {}
    for cluster in gathering.clusters:
        parts = cluster.made_of or [cluster.pictures]
        for part in parts:
            for picture in part:
                belongs[picture] = tuple(part)
    for reading in gathering.readable():
        belongs.setdefault(reading.picture, (reading.picture,))
    return belongs


def _how_much_it_settles(belongs: Dict[str, Tuple[str, ...]], said: Kinship) -> int:
    here = belongs.get(said.left, (said.left,))
    there = belongs.get(said.right, (said.right,))
    if said.right in here:
        # Already known to be the same thing; the answer follows from what is
        # already settled and there is nothing to gain by asking.
        return 0
    return len(here) * len(there)


def worth_asking(gathering: Gathering, *, most: int = 8) -> List[Question]:
    """The questions a person should be asked, best first.

    Only pairs the machine could not decide. A pair it decided is not a question;
    if a person disagrees with one of those they can simply say so, and their
    word wins without being asked.
    """
    if most < 1:
        raise ValueError(
            f"asked for {most} question(s). One is the fewest worth writing out; "
            "to ask nothing, do not ask."
        )
    # Worked out once, not once per pair. Recomputing it inside the loop made
    # this take twenty-two seconds on two hundred photographs — longer than
    # everything else in the run put together.
    belongs = _same_thing_groups(gathering)

    asked: List[Question] = []
    for said in gathering.kinships:
        # Only what the machine could not decide. A person's answer is never
        # "cannot tell", so a pair they have ruled on is already excluded by the
        # verdict alone — an extra guard on who said it read as protection and
        # was dead code, which a reviewer showed by deleting it with no effect.
        if said.verdict != CANNOT_TELL:
            continue
        if said.shared <= NOTHING_IN_COMMON:
            # Nothing to look at. Not a hard question — an easy no, and asking it
            # spends the one thing this is trying not to waste.
            continue
        settles = _how_much_it_settles(belongs, said)
        if settles < 1:
            # It follows from what is already settled. A person must never be
            # asked for something they have in effect already said.
            continue
        asked.append(
            Question(
                left=said.left,
                right=said.right,
                settles=settles,
                shared=said.shared,
                because="; ".join(said.because) or "nothing in particular",
                against="; ".join(said.against),
            )
        )
    asked.sort(key=lambda q: (-q.settles, -q.shared, q.left, q.right))
    return asked[:most]


def how_many_worth_asking(gathering: Gathering) -> int:
    """How many there are in total, so truncation can be admitted rather than hidden."""
    return len(worth_asking(gathering, most=len(gathering.kinships) or 1))


# Everything below this line in an answers file was written by the machine and
# is replaced each time. Everything above it is the person's and is never touched.
THE_LINE = "# ---- below here is the machine's, and is rewritten each time ----"


def theirs(already: str) -> str:
    """Only the part of an answers file a person wrote.

    Splitting on the line above is what stops two things happening. The sheet was
    appending its whole question block every run, so a file answered three times
    held the same question three times over and answering two copies differently
    was reported as two people disagreeing. And a sheet written to a file that
    was not also passed in as answers replaced it outright — a person's notes,
    gone, with no warning.
    """
    if THE_LINE not in already:
        return already
    return already.split(THE_LINE)[0]


def as_sheet(
    gathering: Gathering, questions: Sequence[Question], *, already: str = "", withheld: int = 0
) -> str:
    """A file a person can answer in, with the questions written into it as notes.

    Their own words are kept at the top exactly as they wrote them. Nothing here
    rewrites what somebody said — a tool that tidied a person's own words would
    be the last time they trusted it with them.
    """
    kept = theirs(already)
    lines: List[str] = []
    if kept.strip():
        lines.append(kept.rstrip())
        lines.append("")
    lines.append(THE_LINE)
    lines.append("")

    lines += [
        "# What the machine could not work out, and would like you to say.",
        "#",
        "# Delete the hash in front of whichever line is true and leave the rest.",
        "# Add anything else you know, in the same shape of sentence. Your word",
        "# wins outright — the machine never argues with it — and it carries: one",
        "# answer can settle a dozen pairs it was stuck on.",
        "#",
        "# The whole language is these five sentences:",
        "#",
        # Written with the gaps marked so that they cannot themselves be read as
        # answers. Spelled out as ordinary names, uncommenting the instructions
        # by accident fed the sheet its own examples back and the run stopped
        # with a complaint about pictures called 'one' and 'another'.
        "#     <a picture> and <another picture> are the same thing",
        "#     <a picture> and <another picture> are parts of one thing",
        "#     <a picture> and <another picture> are not related",
        "#     <a picture> is not worth using",
        "#     <a picture> is worth using anyway",
        "",
    ]

    unreadable = [r for r in gathering.readings if not r.readable and not r.from_a_person]
    if unreadable:
        lines.append("# Nothing could be read from these. If one of them is fine really,")
        lines.append("# say so and it will be used anyway.")
        for reading in unreadable:
            lines.append(f"#   {reading.picture}: {reading.because}")
            lines.append(f"# {reading.picture} is worth using anyway")
        lines.append("")

    if not questions:
        lines.append("# Nothing else is in doubt. Nothing to ask.")
        return "\n".join(lines).rstrip() + "\n"

    if withheld > 0:
        lines.append(f"# {withheld} more question(s) are not written here. Ask for more with")
        lines.append("# --most, once these are answered.")
        lines.append("")

    for number, question in enumerate(questions, start=1):
        lines.append(f"# {number}. {question.sentence()}")
        lines.append(f"#    {question.worth()}")
        lines.append(f"#    The machine found: {question.because}")
        if question.against:
            lines.append(f"#    And against it: {question.against}")
        lines += question.answer_lines()
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


__all__ = ["Question", "as_sheet", "worth_asking"]
