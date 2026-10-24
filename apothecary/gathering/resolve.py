"""Working out which pictures are of the same thing.

The rules are written here, in one place, as numbers with names. That is
deliberate: the failure this whole module is guarding against is a judgement
that sounds reasonable and cannot be argued with. Every threshold below can be
disagreed with, and every verdict says which of them it turned on.

**Nothing is merged on a maybe.** Four answers are possible and one of them is
"cannot tell". A picture that matches two pictures which do not match each other
is a contradiction, and a contradiction stops the merge rather than being
averaged into one.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from ..vision.models import Picture
from .arrangement import DRIFT_ALLOWED, arrangement_agrees
from .judgement import (
    BY_A_PERSON,
    WORTH_USING,
    Judgement,
    about_pictures,
    settle,
)
from .models import (
    ALONE,
    CANNOT_TELL,
    PARTS_OF_ONE,
    SAME_THING,
    UNRELATED,
    Cluster,
    Gathering,
    Kinship,
    Reading,
    ShapeMark,
    Signature,
)
from .signature import signature_of, tone_alike

# --- when one picture is worth placing at all -----------------------------

# Fewer shapes than this and there is not enough in the picture to place or to
# compare. One shape is not an arrangement.
ENOUGH_SHAPES = 2

# Below this, the finder is saying it does not really know. Measured: the plain
# finder's confidence is reliably lower when it is wrong, so this is a real
# threshold rather than a decorative one.
ENOUGH_CONFIDENCE = 0.45

# --- when two shapes are the same shape -----------------------------------

# Two shapes count as the same shape at or above this. Made of how alike their
# proportions are and how alike their sizes are relative to their own picture.
SAME_SHAPE_AT = 0.72

# --- when two pictures are of the same thing ------------------------------

# Most of what is in each has to be in the other.
SAME_THING_AT = 0.7

# One picture can be a close-up of part of another. Then nearly everything in
# the smaller one is in the bigger one, and much of the bigger one is missing
# from the smaller. That is still the same thing, seen closer.
CLOSE_UP_AT = 0.85

# Below this many shapes looking alike, their failing to line up is not enough
# to call two pictures unrelated. It is enough to refuse to join them.
ENOUGH_TO_REFUTE = 4

# Light this different means a different place or a different day. On its own it
# settles nothing — it is only ever reached after every reason to join the two
# has already failed — but at that point it is the difference between "no" and
# "I have no idea", and saying "I have no idea" about two obviously unconnected
# photographs is its own kind of wrong.
TONE_APART_AT = 0.35

# --- when two pictures are parts of one larger thing ----------------------

# Two neighbouring parts of one thing are photographed from about the same
# distance — you sweep sideways, you do not walk in and out. So if lining the
# shared shapes up needs one picture blown up well past the other, that is a
# photographer who stepped closer, and stepping closer means it is the same
# thing again rather than the next part of it.
SEAM_SCALE_RANGE = (0.7, 1.45)

# How many shared shapes it takes before the size difference between two
# pictures is worth believing.
STEADY_FIT = 3

# And they must have been taken in similar light. Without that, two pictures of
# different things that happen to share a couple of ordinary shapes would be
# joined into one object, which is the worst mistake available here.
SEAM_TONE_AT = 0.7


def _relative_areas(marks: Sequence[ShapeMark]) -> List[float]:
    """Each shape's size against the biggest shape in its own picture.

    Compared this way, stepping back from the subject changes nothing: every
    size shrinks together, so every ratio holds.
    """
    if not marks:
        return []
    # Measured against the biggest *whole* shape. The biggest shape in a
    # close-up is very often the one hanging off the edge, and measuring
    # everything against a shape that is only half in the picture moved every
    # size at once and lost the real matches.
    whole = [mark.area for mark in marks if not mark.cut_off]
    biggest = max(whole) if whole else max(mark.area for mark in marks)
    if biggest <= 0:
        return [0.0 for _ in marks]
    return [mark.area / biggest for mark in marks]


def _covers(marks: Sequence[ShapeMark], matched: Sequence[int]) -> float:
    """What share of a picture's whole shapes were found in the other picture.

    Shapes running off the edge are left out of the count. They are not whole
    shapes, so failing to find them elsewhere says nothing — and counting them
    is what made a close-up look like a different object, because cropping turns
    a square into a rectangle nobody else has.
    """
    whole = [index for index, mark in enumerate(marks) if not mark.cut_off]
    if not whole:
        # Everything is at the edge. Fall back to counting all of them rather
        # than dividing by nothing, and let the caller's other checks decide.
        return min(1.0, len(matched) / len(marks)) if marks else 0.0
    found = sum(1 for index in matched if index in set(whole))
    return min(1.0, found / len(whole))


# When nearly every shape in one picture could stand in for nearly every shape in
# the other, matching three of them says very little — a room of identical boxes
# will always produce a match. This is how many pairings-that-looked-alike there
# may be for each one that actually fitted, before the whole match is treated as
# too flimsy to join anything on.
#
# The number was measured, not chosen. Across fifteen folders of twenty-seven
# drawn photographs:
#
#     none of this      67 groups found,  9 of them mixing unrelated pictures
#     3.5               62 found,         5 mixed
#     2.5               58 found,         3 mixed
#     2.0               50 found,         1 mixed
#     1.8               41 found,         0 mixed
#
# and on seventeen further folders never used while choosing it, 41 more groups
# and again none mixed. It is a deliberate trade: roughly a fifth of the groups
# that were there to find, in exchange for never having built one out of
# photographs that did not belong together.
TOO_ALIKE_TO_TELL = 1.8


# How far each shape's own size may sit from the size the fitted step-and-zoom
# says it should be. A ratio, so 0.35 means "within about a third either way".
SIZE_AGREES_WITHIN = 0.35


def _sizes_agree(
    left: Sequence[ShapeMark],
    right: Sequence[ShapeMark],
    kept: Sequence[Tuple[int, int]],
    scale: Optional[float],
) -> Tuple[bool, str]:
    """Do the shapes' own sizes agree with how far apart the pictures are?

    A separate question from where the shapes sit, and one the fit never asks.
    If lining the middles up needs one picture blown up by half, then every
    shared shape should also be about half again as big — that follows from it
    being the same object. Three shapes can land in the same relative places by
    luck; three shapes landing in the same places *and* each being the right size
    for that arrangement is much harder to do by accident.

    Checked only where both shapes are whole. A shape running off the edge is
    the wrong size by definition and has nothing to say here.
    """
    if scale is None or scale <= 0:
        return True, "how far apart the pictures are was never worked out"
    ratios = [
        math.sqrt(right[j].area / left[i].area)
        for i, j in kept
        if left[i].area > 0 and right[j].area > 0 and not left[i].cut_off and not right[j].cut_off
    ]
    if not ratios:
        return True, "every shared shape runs off an edge, so their sizes say nothing"
    ratios.sort()
    middle = (
        ratios[len(ratios) // 2]
        if len(ratios) % 2
        else (ratios[len(ratios) // 2 - 1] + ratios[len(ratios) // 2]) / 2
    )
    off = abs(middle - scale) / scale
    if off > SIZE_AGREES_WITHIN:
        return False, (
            f"the shared shapes are {middle:.2f} times the size from one picture "
            f"to the other, but lining them up needs {scale:.2f} — the sizes and "
            "the places disagree, which is what a coincidence looks like"
        )
    return True, (
        f"and the shared shapes are the right size for that ({middle:.2f} against " f"{scale:.2f})"
    )


def _closeness(one: float, other: float) -> float:
    """How alike two positive numbers are, from 0 to 1."""
    if one <= 0 or other <= 0:
        return 1.0 if one == other else 0.0
    return min(one, other) / max(one, other)


# Above this many possible pairings the arrangement search gets expensive, so
# only the best are carried forward.
#
# **The firing is reported, never absorbed.** Searching every arrangement of
# every pairing does not finish in a useful time on a crowded picture, and a
# limit is what makes the question answerable at all. What it buys is "did not
# look past the best sixty", which is a different sentence from "there is no
# match" — and while the limit is silent those two are indistinguishable, so the
# answer carries a mark and the report names it.
MOST_CANDIDATES = 60


def _shape_pairs(left: Signature, right: Signature) -> Tuple[List[Tuple[int, int, float]], int]:
    """Every pairing of shapes that could be the same shape.

    Deliberately **not** one-to-one. An earlier version picked the best partner
    for each shape here, by how alike the two looked; when a coincidence looked
    slightly more alike than the real match, it took the place and locked the
    real one out, and whole overlapping pictures came back as unrelated. Which
    pairing is real is a question about the arrangement, so it is answered where
    the arrangement is known and not before.
    """
    left_areas = _relative_areas(left.marks)
    right_areas = _relative_areas(right.marks)
    candidates: List[Tuple[float, int, int]] = []
    for i, one in enumerate(left.marks):
        for j, other in enumerate(right.marks):
            if one.kind != other.kind:
                continue
            # Proportion carries most of the weight and size carries the rest.
            # Size is the weaker signal by far: it is measured against the
            # biggest shape in its own picture, and the biggest shape is often
            # the one that walked out of frame. Weighting the two equally lost
            # genuine matches, which the meter showed as overlapping pictures
            # being called unrelated. Being generous here is safe because the
            # arrangement check downstream throws out what does not fit.
            score = 0.7 * _closeness(one.proportion, other.proportion) + 0.3 * _closeness(
                left_areas[i], right_areas[j]
            )
            if score >= SAME_SHAPE_AT:
                candidates.append((score, i, j))
    candidates.sort(key=lambda entry: (-entry[0], entry[1], entry[2]))
    kept = candidates[:MOST_CANDIDATES]
    return [(i, j, score) for score, i, j in kept], len(candidates) - len(kept)


def read_one(picture: Picture, *, path: Optional[Path] = None) -> Reading:
    """Say whether one picture, on its own, gave enough to be worth placing."""
    confidences = sorted(shape.confidence for shape in picture.shapes)
    surest = max(confidences) if confidences else 0.0
    # A real middle, not the upper one. Picking the upper of two reported a
    # picture holding one certainty and one blank guess as "typically 100% sure".
    if not confidences:
        typical = 0.0
    elif len(confidences) % 2:
        typical = confidences[len(confidences) // 2]
    else:
        middle = len(confidences) // 2
        typical = (confidences[middle - 1] + confidences[middle]) / 2

    if len(picture.shapes) < ENOUGH_SHAPES:
        because = (
            f"only {len(picture.shapes)} shape(s) were found, and {ENOUGH_SHAPES} "
            "is the fewest that makes an arrangement"
        )
        readable = False
    elif typical < ENOUGH_CONFIDENCE:
        because = (
            f"the finder was typically only {typical:.0%} sure, below the "
            f"{ENOUGH_CONFIDENCE:.0%} it has to reach to be worth trusting"
        )
        readable = False
    else:
        because = f"{len(picture.shapes)} shapes, typically {typical:.0%} sure"
        readable = True

    return Reading(
        picture=picture.name,
        path=path,
        shapes_found=len(picture.shapes),
        surest=surest,
        typical=typical,
        readable=readable,
        because=because,
    )


def kinship_between(left: Signature, right: Signature) -> Kinship:
    """Judge what two pictures are of, and say why."""
    matched, left_out = _shape_pairs(left, right)
    looked_alike = [(i, j) for i, j, _ in matched]
    # Shapes that look alike one at a time include coincidences. The arrangement
    # is what tells them apart, so everything below counts only the matches it
    # kept — not the ones that merely looked right on their own.
    fit = arrangement_agrees(left.marks, right.marks, looked_alike)
    pairs = list(fit.kept) if fit.agrees else ([] if fit.refutes else looked_alike)
    shared = len(pairs)
    # A shape running off the edge of the picture is not the whole shape, so it
    # is not held against the picture it is cut off in. It may still match.
    covers_left = _covers(left.marks, [i for i, _ in pairs])
    covers_right = _covers(right.marks, [j for _, j in pairs])
    alike = tone_alike(left.tone, right.tone)

    because: List[str] = []
    against: List[str] = []

    if left_out:
        against.append(
            f"{left_out} further pairing(s) were never looked at — these two "
            f"pictures produced more than {MOST_CANDIDATES} shapes that could "
            "have gone together, and only the closest were followed up. This "
            "answer is what was found inside that limit, not everything there is"
        )

    def finish(verdict: str, strength: float) -> Kinship:
        return Kinship(
            left=left.picture,
            right=right.picture,
            verdict=verdict,
            strength=max(0.0, min(1.0, strength)),
            shared=shared,
            covers_left=covers_left,
            covers_right=covers_right,
            tone_alike=alike if alike is not None else 0.0,
            because=because,
            against=against,
            pairs=pairs,
            bounded=bool(left_out),
        )

    if not left.marks or not right.marks:
        empty = left.picture if not left.marks else right.picture
        because.append(f"nothing was found in {empty}, so there is nothing to compare")
        return finish(CANNOT_TELL, 0.0)

    if alike is None:
        against.append("nobody measured how light or dark either picture is")

    if not looked_alike:
        because.append("not one shape in either picture looks like a shape in the other")
        # Two rich pictures sharing nothing is strong evidence. Two sparse ones
        # sharing nothing could easily be an accident of a poor finder.
        weight = min(len(left.marks), len(right.marks))
        return finish(UNRELATED, min(1.0, 0.4 + 0.15 * weight))

    if fit.refutes:
        # Shapes matched one at a time, and the arrangement says that was luck.
        # This is the check that stopped two unrelated pictures being merged.
        because.append(f"{len(looked_alike)} shape(s) look alike one by one, but {fit.because}")
        if alike is not None and alike >= SEAM_TONE_AT:
            # Same light, so they were probably taken together, and something
            # about them simply could not be lined up. Not being able to line
            # two photographs up is a reason to leave them apart; it is not a
            # reason to say they have nothing to do with each other.
            against.append(
                f"but the light is {alike:.0%} alike, so they were probably taken "
                "together and calling them unrelated would be too strong"
            )
            return finish(CANNOT_TELL, 0.3)
        if len(looked_alike) >= ENOUGH_TO_REFUTE:
            return finish(UNRELATED, 0.75)
        # Two or three shapes failing to line up is thin. It is a reason not to
        # join them; it is not a reason to declare them unrelated, and saying so
        # anyway was this module's most common mistake when it was first
        # measured.
        against.append(
            f"only {len(looked_alike)} shape(s) looked alike at all, which is too "
            f"few for their not lining up to settle anything"
        )
        return finish(CANNOT_TELL, 0.25)

    if fit.agrees:
        sizes_ok, sizes_said = _sizes_agree(left.marks, right.marks, pairs, fit.scale)
        if not sizes_ok:
            because.append(f"{len(looked_alike)} shape(s) look alike, but {sizes_said}")
            if alike is not None and alike >= SEAM_TONE_AT:
                against.append(
                    f"the light is {alike:.0%} alike, so they may still have been " "taken together"
                )
                return finish(CANNOT_TELL, 0.3)
            return finish(UNRELATED, 0.7)
        because.append(fit.because)
        because.append(sizes_said)
        muddle = len(looked_alike) / max(1, shared)
        if muddle > TOO_ALIKE_TO_TELL:
            because.append(
                f"but {len(looked_alike)} pairings looked alike and only {shared} "
                f"fitted — the shapes in these two pictures are too alike to tell "
                "apart, so matching some of them is not evidence of much"
            )
            return finish(CANNOT_TELL, 0.3)
    else:
        against.append(fit.because)

    lesser, greater = sorted((covers_left, covers_right))

    # Three shapes lined up. Always three — there used to be an exception for
    # "every single shape in both is accounted for", and a reviewer walked
    # straight through it: two photographs with one uncropped shape each score
    # 100% coverage on a single match, the arrangement check never runs at all
    # because one point cannot be checked, and two unrelated photographs were
    # declared the same thing at full confidence. An exception to the rule that
    # makes the rule unreachable is not an exception.
    if lesser >= SAME_THING_AT and shared >= STEADY_FIT:
        because.append(
            f"{covers_left:.0%} of one and {covers_right:.0%} of the other are the same shapes"
        )
        if alike is not None and alike >= SEAM_TONE_AT:
            because.append(f"and they were taken in similar light ({alike:.0%} alike)")
        elif alike is not None:
            against.append(f"the light is not much alike ({alike:.0%})")
        return finish(SAME_THING, min(1.0, lesser))

    if greater >= CLOSE_UP_AT and shared >= STEADY_FIT:
        # Everything one picture shows is in the other, which shows more. That
        # is one thing photographed twice, once from closer in — not two things.
        because.append(
            f"everything in one of them ({greater:.0%}) is in the other, which "
            "shows more besides — the same thing, photographed from closer in"
        )
        if fit.scale is not None:
            because.append(f"and it is {fit.scale:.1f} times the size in one of them")
        return finish(SAME_THING, greater)

    if (
        # Three, not two. How much bigger one picture is than the other is worked
        # out from the shapes they share, and two shapes give a number that moves
        # with every wobble in the finder. Trusting it at two turned one honest
        # refusal into three confident mistakes, one of them the bad kind.
        shared >= STEADY_FIT
        and fit.agrees
        and fit.scale is not None
        and fit.drift is not None
        and fit.drift <= DRIFT_ALLOWED / 2
        and not SEAM_SCALE_RANGE[0] <= fit.scale <= SEAM_SCALE_RANGE[1]
    ):
        because.append(
            f"what they share is {fit.scale:.1f} times the size in one of them, "
            "so one was taken from much closer in — that is the same thing again, "
            "not the next part of it"
        )
        return finish(SAME_THING, min(0.9, 0.5 + 0.1 * shared))

    if shared >= STEADY_FIT and alike is not None and alike >= SEAM_TONE_AT:
        because.append(
            f"{shared} shapes are in both, but only {covers_left:.0%} and "
            f"{covers_right:.0%} of each — they overlap at an edge rather than being the same"
        )
        because.append(f"and the light is {alike:.0%} alike, so they were taken together")
        return finish(PARTS_OF_ONE, min(1.0, 0.4 + 0.1 * shared))

    if shared >= STEADY_FIT and alike is None:
        because.append(f"{shared} shapes are in both, but only part of each")
        against.append(
            "without knowing whether they were taken in the same light, sharing a "
            "few ordinary shapes is not enough to join two pictures into one thing"
        )
        return finish(CANNOT_TELL, 0.3)

    because.append(
        f"only {shared} shape(s) match, covering {covers_left:.0%} and {covers_right:.0%}"
    )

    if alike is not None and alike < TONE_APART_AT:
        because.append(
            f"and the light is only {alike:.0%} alike, which is a different place "
            "or a different day"
        )
        return finish(UNRELATED, min(0.8, 0.5 + (TONE_APART_AT - alike)))

    against.append(
        f"too much for {UNRELATED} and too little for {SAME_THING} — the answer is "
        "genuinely unclear, not narrowly one or the other"
    )
    return finish(CANNOT_TELL, 0.2)


class _Grouper:
    """Union-find, kept small and local."""

    def __init__(self, names: Sequence[str]) -> None:
        self.parent: Dict[str, str] = {name: name for name in names}

    def find(self, name: str) -> str:
        while self.parent[name] != name:
            self.parent[name] = self.parent[self.parent[name]]
            name = self.parent[name]
        return name

    def join(self, one: str, other: str) -> None:
        a, b = self.find(one), self.find(other)
        if a != b:
            self.parent[b] = a

    def groups(self) -> List[List[str]]:
        gathered: Dict[str, List[str]] = {}
        for name in self.parent:
            gathered.setdefault(self.find(name), []).append(name)
        return [sorted(members) for members in gathered.values()]


def gather(
    pictures: Sequence[Picture],
    *,
    paths: Optional[Sequence[Optional[Path]]] = None,
    answers: Optional[Sequence[Judgement]] = None,
) -> Gathering:
    """Take in many pictures and work out which belong with which.

    ``answers`` is what a person has already said. Their word wins outright, and
    it carries: saying two photographs are of one thing joins everything already
    joined to either of them, because the grouping below runs on the settled
    verdicts and cannot tell which of them came from where.

    What the machine would have said is kept alongside, not thrown away — that
    is what turns every answer into a measurement of the machine as well as an
    improvement to the result.
    """
    told = settle(answers or [])
    about_each = about_pictures(answers or [])
    where = list(paths) if paths is not None else [None] * len(pictures)
    if len(where) != len(pictures):
        raise ValueError(
            f"{len(pictures)} picture(s) but {len(where)} place(s) they came from. "
            "Every picture needs its own, or none of them should have one."
        )

    seen: Dict[str, int] = {}
    for picture in pictures:
        seen[picture.name] = seen.get(picture.name, 0) + 1
    repeated = sorted(name for name, count in seen.items() if count > 1)
    if repeated:
        raise ValueError(
            f"more than one picture is called {repeated[0]!r}"
            + (f" (and {len(repeated) - 1} other name(s))" if len(repeated) > 1 else "")
            + ". Names are how every answer here refers to a picture, so two "
            "pictures sharing one would make every answer ambiguous."
        )

    readings = []
    for picture, place in zip(pictures, where, strict=True):
        reading = read_one(picture, path=place)
        told_about = about_each.get(picture.name)
        if told_about is not None:
            wanted = told_about.verdict == WORTH_USING
            readings.append(
                reading.model_copy(
                    update={
                        "readable": wanted,
                        "said_by": BY_A_PERSON,
                        "because": (
                            f"you said it is {told_about.verdict}"
                            + (f" — {told_about.note}" if told_about.note else "")
                            + f" (the machine had said: {reading.because})"
                        ),
                    }
                )
            )
            continue
        readings.append(reading)
    usable = sorted(
        ((p, w) for p, w, r in zip(pictures, where, readings, strict=True) if r.readable),
        key=lambda pair: pair[0].name,
    )
    # Sorted by name, always. The answer must not depend on the order the
    # pictures happened to arrive in — and it did: a reviewer handed the same
    # folder in nine different orders and got five different results, some of
    # them merging a photograph that did not belong. Every pairwise judgement is
    # symmetric now, and comparing in a fixed order is what makes the grouping
    # built on top of them symmetric too.
    signatures = [signature_of(p, path=w) for p, w in usable]

    kinships: List[Kinship] = []
    for i in range(len(signatures)):
        for j in range(i + 1, len(signatures)):
            worked_out = kinship_between(signatures[i], signatures[j])
            person = told.get(worked_out.key)
            if person is None:
                kinships.append(worked_out)
                continue
            # A person's word wins outright. What the machine thought is kept so
            # that the answer also scores the machine — see Gathering.scorecard.
            kinships.append(
                worked_out.model_copy(
                    update={
                        "verdict": person.verdict,
                        "strength": 1.0,
                        "said_by": BY_A_PERSON,
                        "machine_said": worked_out.verdict,
                        "note": person.note,
                        "because": ["you said so"]
                        + ([person.note] if person.note else [])
                        + [f"the machine had said: {said}" for said in worked_out.because[:1]],
                    }
                )
            )

    names = [s.picture for s in signatures]
    set_aside: Dict[str, str] = {r.picture: r.because for r in readings if not r.readable}

    # Pass one: pictures of the same thing.
    identity = _Grouper(names)
    for kinship in kinships:
        if kinship.verdict == SAME_THING:
            identity.join(kinship.left, kinship.right)

    said = {k.key: k for k in kinships}

    def verdict_for(one: str, other: str) -> str:
        found = said.get(tuple(sorted((one, other))))  # type: ignore[arg-type]
        return found.verdict if found else CANNOT_TELL

    def said_about(one: str, other: str) -> Optional[Kinship]:
        return said.get(tuple(sorted((one, other))))  # type: ignore[arg-type]

    def is_a_quarrel(one: str, other: str, group: Sequence[str]) -> bool:
        """Does this pair genuinely contradict the group it is in?

        A person's word outranks the machine's, and that has to hold here or it
        holds nowhere: this check destroys groups, and it was destroying groups a
        person had built on the strength of a machine's guess — while the report
        printed "your word was taken as it stands" in the same breath.

        So a machine's disagreement is only a quarrel in a group the machine
        built. If any part of this group came from a person, only another
        person's word can break it.
        """
        between = said_about(one, other)
        if between is None:
            return False
        if between.verdict not in (UNRELATED, PARTS_OF_ONE):
            return False
        if between.verdict == PARTS_OF_ONE and not between.from_a_person:
            # The machine calling two things parts of one larger thing is not a
            # denial that they are the same thing; a person saying it is.
            return False
        if between.from_a_person:
            return True
        joined_by_a_person = any(
            (k := said_about(a, b)) is not None and k.from_a_person and k.verdict == SAME_THING
            for index, a in enumerate(group)
            for b in group[index + 1 :]
        )
        return not joined_by_a_person

    overruled: List[str] = []

    def note_overruling(group: Sequence[str]) -> None:
        for index, a in enumerate(group):
            for b in group[index + 1 :]:
                between = said_about(a, b)
                if (
                    between is not None
                    and between.verdict == UNRELATED
                    and not between.from_a_person
                ):
                    overruled.append(
                        f"the machine had said {a} and {b} were {UNRELATED}; your "
                        "word outranks it, so they were kept together"
                    )

    groups: List[List[str]] = []
    for members in identity.groups():
        quarrel = [
            (a, b)
            for index, a in enumerate(members)
            for b in members[index + 1 :]
            if is_a_quarrel(a, b, members)
        ]
        if not quarrel and len(members) > 1:
            note_overruling(members)
        if quarrel:
            a, b = quarrel[0]
            between = said_about(a, b)
            whose = "you" if (between and between.from_a_person) else "the machine"
            what = between.verdict if between else UNRELATED
            for picture in members:
                set_aside[picture] = (
                    f"it was joined into a group with {len(members) - 1} other "
                    f"picture(s), but {whose} said {a} and {b} are {what}. A group "
                    "that disagrees with itself is not a group, so nothing was "
                    f"merged. To keep them together, say: {a} and {b} are "
                    f"{SAME_THING}."
                )
            groups.extend([[picture] for picture in members])
            continue
        groups.append(members)

    contested = {picture for picture in set_aside if picture in names}

    # Pass two: groups that are parts of one larger thing.
    def group_key(members: Sequence[str]) -> str:
        return members[0]

    by_key = {group_key(g): g for g in groups}
    composition = _Grouper(list(by_key))
    seams: Dict[Tuple[str, str], Kinship] = {}
    for kinship in kinships:
        if kinship.verdict != PARTS_OF_ONE:
            continue
        # Deliberately *not* skipped for a picture caught up in some other
        # quarrel. A group falling apart somewhere else says nothing about
        # whether these two overlap at an edge, and dropping the answer on those
        # grounds threw away a person's own words with a reason that was simply
        # untrue. If this seam is itself part of a contradiction, the check below
        # catches it.
        left_key = next(k for k, g in by_key.items() if kinship.left in g)
        right_key = next(k for k, g in by_key.items() if kinship.right in g)
        if left_key == right_key:
            continue
        composition.join(left_key, right_key)
        seams[tuple(sorted((left_key, right_key)))] = kinship  # type: ignore[index]

    clusters: List[Cluster] = []
    for keys in composition.groups():
        parts = [by_key[key] for key in keys]
        # The same check the identity groups get, for the same reason. A larger
        # thing is built by chaining overlaps, and a chain will happily run from
        # one photograph to another that has nothing to do with it. If any two
        # pictures inside the chain were judged unrelated, the chain is wrong
        # somewhere and there is no way to know where, so it is not built.
        inside = [p for part in parts for p in part]
        quarrel = [
            (a, b)
            for index, a in enumerate(inside)
            for b in inside[index + 1 :]
            if verdict_for(a, b) == UNRELATED
        ]
        if len(parts) > 1 and quarrel:
            a, b = quarrel[0]
            refusal = (
                f"these were chained into one larger thing with "
                f"{len(inside) - 1} other picture(s), but {a} and {b} in that "
                f"same chain were judged {UNRELATED}. A chain that runs through "
                "two unrelated pictures is joined in the wrong place and there "
                "is no way to tell where, so the larger thing was not built."
            )
            for part in parts:
                if len(part) == 1:
                    # Nothing survives for this one, so it really is set aside.
                    set_aside[part[0]] = refusal
                    clusters.append(
                        Cluster(
                            name=part[0],
                            kind=ALONE,
                            pictures=part,
                            because=[refusal],
                            contested=True,
                        )
                    )
                    continue
                # This group of pictures is still perfectly good on its own —
                # only the larger thing they were chained into is refused. An
                # earlier version wrote every one of them into the set-aside list
                # while also reporting them as a group held together at 100%, so
                # the report said "held together at 100%" and "nothing was built"
                # about the same pictures in the same run.
                holding = [
                    k
                    for k in kinships
                    if k.verdict == SAME_THING and k.left in part and k.right in part
                ]
                clusters.append(
                    Cluster(
                        name=f"same_{part[0]}",
                        kind=SAME_THING,
                        pictures=part,
                        because=[refusal] + [k.summary() for k in holding],
                        strength=min((k.strength for k in holding), default=0.0),
                    )
                )
            continue
        pictures_here = sorted(p for part in parts for p in part)
        if len(parts) > 1:
            because = [
                f"{k.left} and {k.right} overlap at an edge: {k.because[0]}"
                for k in seams.values()
                if any(k.left in part for part in parts)
            ]
            holding = [
                k
                for k in seams.values()
                if any(k.left in part for part in parts) and any(k.right in p for p in parts)
            ]
            clusters.append(
                Cluster(
                    name=f"larger_{keys[0]}",
                    kind=PARTS_OF_ONE,
                    pictures=pictures_here,
                    made_of=[sorted(part) for part in parts],
                    because=because or ["they overlap at an edge"],
                    strength=min((k.strength for k in holding), default=0.0),
                )
            )
            continue
        only = parts[0]
        if len(only) == 1:
            clusters.append(
                Cluster(
                    name=only[0],
                    kind=ALONE,
                    pictures=only,
                    because=(
                        [set_aside[only[0]]]
                        if only[0] in contested
                        else ["nothing else was judged to be of the same thing"]
                    ),
                    contested=only[0] in contested,
                )
            )
            continue
        holding = [
            k for k in kinships if k.verdict == SAME_THING and k.left in only and k.right in only
        ]
        clusters.append(
            Cluster(
                name=f"same_{only[0]}",
                kind=SAME_THING,
                pictures=only,
                because=[k.summary() for k in holding],
                strength=min((k.strength for k in holding), default=0.0),
            )
        )

    clusters.sort(key=lambda c: (c.kind == ALONE, -len(c.pictures), c.name))
    # An answer that was never applied has to be said out loud. Every one of
    # these was silently dropped once: a person names a picture nothing could be
    # read from, their sentence goes nowhere, and no output mentions it at all.
    reached = {k.key for k in kinships}
    ignored: Dict[str, str] = {}
    for key, person in told.items():
        if len(key) != 2 or key in reached:
            continue
        missing = [name for name in key if name not in names]
        if missing:
            ignored[person.sentence()] = (
                f"nothing could be read from {missing[0]}, so it was never "
                "compared with anything and your answer could not be used. If "
                f"{missing[0]} is fine really, say: {missing[0]} is {WORTH_USING}."
            )
        else:
            ignored[person.sentence()] = (
                "these two were never compared, so your answer could not be used"
            )

    return Gathering(
        readings=readings,
        kinships=kinships,
        clusters=clusters,
        set_aside=set_aside,
        ignored=ignored,
        overruled=sorted(set(overruled)),
        told_about_pictures=len(about_each),
    )


__all__ = [
    "CLOSE_UP_AT",
    "ENOUGH_CONFIDENCE",
    "ENOUGH_SHAPES",
    "SAME_SHAPE_AT",
    "SAME_THING_AT",
    "SEAM_TONE_AT",
    "gather",
    "kinship_between",
    "read_one",
]
