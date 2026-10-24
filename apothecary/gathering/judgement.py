"""What a person tells the sorting, and why their word wins.

The sorting is careful and it is not very good. Measured on drawn pictures it
finds about a fifth of the groups that are there. A person glancing at two
photographs gets nearly all of them, in about a second, and could not explain how.

So this is not a machine with a person checking it. It is two of them doing the
parts each is actually better at:

**A person is better at**

- knowing at a glance that two photographs are of one thing
- knowing a photograph is useless — a thumb, a floor, a blur
- saying how big something really is, and what it is called
- being right about all of that without being able to say why

**The machine is better at**

- comparing every pair of two hundred photographs without getting bored
- giving the same answer today as it did last week
- saying how sure it is, and never rounding that up
- remembering what it was told and following it through
- working out which single question is worth asking next

The machine's job in this arrangement is not to decide. It is to **do the
counting, and then ask well** — to narrow two hundred photographs down to eight
questions worth a person's attention, and to carry each answer as far as it goes.

## And its half is arithmetic, on purpose

Nothing here asks anything else what it thinks. No model, no service, nothing
over a network, no randomness — the whole path from photographs to groups is
counting, comparing and sorting, and the same input gives the same output every
time. That is not what was to hand; it is the only thing that makes the rest of
this work:

- A person's word can only *win* over something that can be overruled. You can
  overrule arithmetic. You cannot overrule something that answers differently on
  two Tuesdays; you can only argue with it.
- A question is only worth asking if its worth is a number, and a number about a
  guess is a guess.
- An answer only scores the machine if the machine would have said the same thing
  tomorrow.
- A reason is only a reason if it is the actual sum, not a sentence that sounds
  like one.

Two tests read this package's own source and refuse it if it ever reaches for any
of that. See ``tests/test_working_together.py``.

## What a person writes

A plain file. Anything after a hash is a note. Blank lines are ignored. Every
other line is one of these sentences:

    bench_from_the_left and bench_from_the_right are the same thing
    shed_door and kitchen_wall are not related
    wall_left and wall_right are parts of one thing
    my_thumb is not worth using
    very_dark_one is worth using anyway

That is the whole language. It was chosen so that it can be read aloud to
somebody who does not do this work, which is the same test every page in this
project has to pass.

## Three rules about a person's word

1. **It wins.** Always, and without argument. The machine never overrules it,
   never averages with it, and never quietly weakens it to a suggestion.
2. **It carries.** Saying two photographs are of one thing joins everything
   already joined to either of them. One sentence can settle a dozen pairs.
3. **It is also a measurement.** Every answer is a case where the truth is known,
   so every answer scores the machine — see :meth:`Gathering.scorecard`. Helping
   and checking are the same act here, which is the point.

And one rule about people: **two people who disagree are refused, not averaged.**
If the file says two photographs are of one thing in one place and unrelated in
another, nothing is merged and both lines are named. A machine deciding which
person was right is exactly what this module exists to avoid.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field, model_validator

from .models import PARTS_OF_ONE, SAME_THING, UNRELATED

# What a person may say about a picture on its own.
NOT_WORTH_USING = "not worth using"
WORTH_USING = "worth using anyway"

ABOUT_A_PAIR = (SAME_THING, PARTS_OF_ONE, UNRELATED)
ABOUT_ONE = (NOT_WORTH_USING, WORTH_USING)

BY_A_PERSON = "you"
BY_THE_MACHINE = "the machine"

_PAIR = re.compile(
    r"^\s*(?P<left>\S+)\s+and\s+(?P<right>\S+)\s+are\s+(?P<verdict>.+?)\s*$",
    re.IGNORECASE,
)
_ONE = re.compile(r"^\s*(?P<who>\S+)\s+is\s+(?P<verdict>.+?)\s*$", re.IGNORECASE)


class CannotRead(ValueError):
    """A line in the answers file is not one of the sentences this understands."""


class PeopleDisagree(ValueError):
    """Two answers say different things about the same pictures.

    Refused rather than resolved. Picking one would mean a machine deciding which
    person was right, which is the one thing this module must never do.
    """


class Judgement(BaseModel):
    """One thing a person said."""

    left: str
    right: Optional[str] = None
    verdict: str
    note: str = ""
    line: int = Field(0, ge=0)

    @model_validator(mode="after")
    def _makes_sense(self) -> "Judgement":
        if self.right is None:
            if self.verdict not in ABOUT_ONE:
                raise ValueError(
                    f"{self.verdict!r} is something to say about two pictures, not "
                    f"one. Try: {self.left} and <another picture> are {self.verdict}."
                )
        else:
            if self.verdict not in ABOUT_A_PAIR:
                raise ValueError(
                    f"{self.verdict!r} is something to say about one picture, not "
                    f"two. Try: {self.left} is {self.verdict}."
                )
            if self.left == self.right:
                raise ValueError(f"{self.left!r} was compared with itself")
        return self

    @property
    def key(self) -> Tuple[str, ...]:
        if self.right is None:
            return (self.left,)
        return tuple(sorted((self.left, self.right)))

    def sentence(self) -> str:
        if self.right is None:
            return f"{self.left} is {self.verdict}"
        return f"{self.left} and {self.right} are {self.verdict}"


def _tidy(text: str) -> str:
    return " ".join(text.strip().split()).lower()


def _plainly(wrong: Exception) -> str:
    """The sentence out of a validation complaint, without the machinery."""
    for line in str(wrong).splitlines():
        stripped = line.strip()
        if stripped.startswith("Value error, "):
            return stripped[len("Value error, ") :].split(" [type=")[0]
    return str(wrong).splitlines()[0]


def read_answers(text: str, *, where: str = "the answers") -> List[Judgement]:
    """Turn what a person wrote into what the sorting can use.

    Every refusal names the line and says what would have worked, because a file
    a person types by hand will have typing in it, and a complaint that does not
    say what to type instead is no help at all.
    """
    said: List[Judgement] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line, _, note = raw.partition("#")
        if not line.strip():
            continue

        pair = _PAIR.match(line)
        if pair:
            verdict = _tidy(pair.group("verdict"))
            if verdict not in ABOUT_A_PAIR:
                raise CannotRead(
                    f"{where}, line {number}: {verdict!r} is not something this "
                    f"understands about two pictures. It knows: "
                    f"{', '.join(ABOUT_A_PAIR)}."
                )
            try:
                said.append(
                    Judgement(
                        left=pair.group("left"),
                        right=pair.group("right"),
                        verdict=verdict,
                        note=note.strip(),
                        line=number,
                    )
                )
            except ValueError as wrong:
                # Turned into the same shape of complaint as everything else
                # here. Left to itself this came out as a wall of internal
                # detail with no line number and nothing to act on.
                raise CannotRead(f"{where}, line {number}: {_plainly(wrong)}") from None
            continue

        one = _ONE.match(line)
        if one:
            verdict = _tidy(one.group("verdict"))
            if verdict not in ABOUT_ONE:
                raise CannotRead(
                    f"{where}, line {number}: {verdict!r} is not something this "
                    f"understands about one picture. It knows: "
                    f"{', '.join(ABOUT_ONE)}."
                )
            try:
                said.append(
                    Judgement(
                        left=one.group("who"),
                        verdict=verdict,
                        note=note.strip(),
                        line=number,
                    )
                )
            except ValueError as wrong:
                raise CannotRead(f"{where}, line {number}: {_plainly(wrong)}") from None
            continue

        raise CannotRead(
            f"{where}, line {number}: this is not a sentence it understands.\n"
            f"    {line.strip()}\n"
            "Every line looks like one of these:\n"
            "    one_picture and another_picture are the same thing\n"
            "    one_picture and another_picture are parts of one thing\n"
            "    one_picture and another_picture are not related\n"
            "    one_picture is not worth using\n"
            "    one_picture is worth using anyway\n"
            "Anything after a hash is a note, and blank lines are ignored."
        )
    return said


def read_answers_file(path: Path) -> List[Judgement]:
    """The same, from a file, so the refusals name the file.

    Read as ``utf-8-sig`` because a file saved by an ordinary text editor on
    Windows begins with three invisible bytes, and without this the first name in
    the file quietly became a name nothing answered to — reported as missing and
    present in the same sentence.
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as wrong:
        raise CannotRead(
            f"{path} is not text this can read ({wrong.reason} at byte "
            f"{wrong.start}). It has to be saved as plain text — UTF-8 if your "
            "editor asks."
        ) from None
    except OSError as wrong:
        raise CannotRead(f"{path} could not be read: {wrong}") from None
    return read_answers(text, where=str(path))


def settle(said: Sequence[Judgement]) -> Dict[Tuple[str, ...], Judgement]:
    """Gather the answers, refusing rather than choosing when two disagree."""
    settled: Dict[Tuple[str, ...], Judgement] = {}
    for one in said:
        already = settled.get(one.key)
        if already is not None and already.verdict != one.verdict:
            raise PeopleDisagree(
                f"line {already.line} says {already.sentence()!r} and line "
                f"{one.line} says {one.sentence()!r}. Both cannot be true, and "
                "picking one would mean a machine deciding which person was "
                "right. Nothing was merged. Delete or correct one of the two."
            )
        settled[one.key] = one

    # Throwing a picture out and then saying something about it are two things
    # that cannot both be meant. Left unchecked the second one simply vanished.
    thrown_out = {
        one.left: one for one in said if one.right is None and one.verdict == NOT_WORTH_USING
    }
    for one in said:
        if one.right is None:
            continue
        for name in (one.left, one.right):
            gone = thrown_out.get(name)
            if gone is not None:
                raise PeopleDisagree(
                    f"line {gone.line} says {gone.sentence()!r}, and line "
                    f"{one.line} says {one.sentence()!r}. A picture that is not "
                    "worth using cannot also be the same thing as something else. "
                    "Delete or correct one of the two."
                )
    return settled


def about_pictures(said: Sequence[Judgement]) -> Dict[str, Judgement]:
    """Only the answers about one picture on its own."""
    return {one.left: one for one in said if one.right is None}


def unknown_names(said: Sequence[Judgement], known: Sequence[str]) -> List[str]:
    """Names a person used that no picture answers to.

    Almost always a typo or a renamed file, and almost always the reason an
    answer appears to have been ignored. Never silently dropped.
    """
    have = set(known)
    used = {name for one in said for name in ((one.left, one.right) if one.right else (one.left,))}
    return sorted(name for name in used if name and name not in have)


__all__ = [
    "ABOUT_A_PAIR",
    "ABOUT_ONE",
    "BY_A_PERSON",
    "BY_THE_MACHINE",
    "CannotRead",
    "Judgement",
    "NOT_WORTH_USING",
    "PeopleDisagree",
    "WORTH_USING",
    "about_pictures",
    "read_answers",
    "read_answers_file",
    "settle",
    "unknown_names",
]
