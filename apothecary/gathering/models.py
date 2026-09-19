"""What a gathering of pictures is made of.

Three different things get called "resolved" in ordinary speech, and keeping
them apart is most of the work here:

1. **A picture resolves on its own** — enough was found in it, clearly enough,
   to be worth placing at all. A picture of a blank wall does not.
2. **Two pictures resolve to the same thing** — the same object, from a
   different angle, distance or light. Their pieces are one set of pieces.
3. **Two pictures resolve into one larger thing** — neighbouring parts of
   something bigger, sharing an edge. Their pieces sit side by side; they are
   not the same pieces.

A fourth outcome matters as much as the three: **cannot tell**. It is a real
answer, it is recorded with a reason, and nothing is merged on the strength of
it.

PROTOTYPE — not ratified.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, model_validator

from ..models.vectors import Vector2D
from ..vision.models import ShapeKind

# --- what one picture can be said to be of another ------------------------
SAME_THING = "the same thing"
PARTS_OF_ONE = "parts of one thing"
UNRELATED = "not related"
CANNOT_TELL = "cannot tell"

VERDICTS = (SAME_THING, PARTS_OF_ONE, UNRELATED, CANNOT_TELL)

# --- what a group of pictures can be --------------------------------------
ALONE = "on its own"

CLUSTER_KINDS = (SAME_THING, PARTS_OF_ONE, ALONE)


class ShapeMark(BaseModel):
    """One shape, described in a way that survives moving the camera.

    Not where it is in the picture and not how many pixels across — those change
    the moment you step sideways. What is kept is what it looks like: its kind,
    how many times longer than wide it is, and how much of the picture it takes
    up. A photograph taken from twice as far away halves every size but leaves
    every proportion alone, which is why proportion carries most of the weight.
    """

    kind: ShapeKind
    proportion: float = Field(ge=1.0, description="long side divided by short side")
    area: float = Field(ge=0.0, le=1.0, description="share of the picture it covers")
    centre: Vector2D
    confidence: float = Field(ge=0.0, le=1.0)
    cut_off: bool = Field(
        False,
        description="it runs off the edge of the picture, so this is not its whole shape",
    )


class Signature(BaseModel):
    """Everything about a picture that is used to compare it with another.

    Held separately from the picture so that comparing is cheap, repeatable, and
    obviously not looking at anything else.
    """

    picture: str
    marks: List[ShapeMark] = Field(default_factory=list)
    tone: List[float] = Field(default_factory=list, description="how light and dark it is")
    wideness: float = Field(gt=0.0, description="pixels across divided by pixels down")

    @model_validator(mode="after")
    def _tone_is_a_share(self) -> "Signature":
        if self.tone:
            total = sum(self.tone)
            if not 0.99 <= total <= 1.01:
                raise ValueError(
                    f"the light-and-dark profile of {self.picture!r} adds up to {total:.3f}, "
                    "not 1. It is a share of the picture, so it has to."
                )
            if any(part < 0 for part in self.tone):
                raise ValueError(f"{self.picture!r} has a negative share of light")
        return self


class Reading(BaseModel):
    """Whether one picture, on its own, was worth anything.

    A picture that gives nothing readable is not a failure of the gathering; it
    is a fact about that picture, and it is said out loud rather than quietly
    dropped.
    """

    picture: str
    path: Optional[Path] = None
    shapes_found: int = Field(ge=0)
    surest: float = Field(0.0, ge=0.0, le=1.0)
    typical: float = Field(0.0, ge=0.0, le=1.0)
    readable: bool
    because: str
    said_by: str = "the machine"

    @property
    def from_a_person(self) -> bool:
        return self.said_by != "the machine"

    def summary(self) -> str:
        if self.readable:
            return (
                f"{self.picture}: {self.shapes_found} shape(s), "
                f"typically {self.typical:.0%} sure — {self.because}"
            )
        return f"{self.picture}: not readable — {self.because}"


class Kinship(BaseModel):
    """What two pictures were judged to be of, and why.

    Both sides of the argument are kept. A verdict with only the reasons for it
    is an assertion; a verdict that also lists what argued against it can be
    disagreed with, which is the point.
    """

    left: str
    right: str
    verdict: str
    strength: float = Field(ge=0.0, le=1.0)
    shared: int = Field(0, ge=0, description="shapes matched between the two")
    covers_left: float = Field(0.0, ge=0.0, le=1.0)
    covers_right: float = Field(0.0, ge=0.0, le=1.0)
    tone_alike: float = Field(0.0, ge=0.0, le=1.0)
    because: List[str] = Field(default_factory=list)
    against: List[str] = Field(default_factory=list)
    pairs: List[Tuple[int, int]] = Field(
        default_factory=list, description="which shape in the left goes with which in the right"
    )
    said_by: str = Field(
        "the machine", description="who decided this — a person's word is never overruled"
    )
    machine_said: Optional[str] = Field(
        None,
        description="what the machine would have said, kept when a person overruled it",
    )
    note: str = Field("", description="what the person wrote beside their answer")
    bounded: bool = Field(
        False,
        description="a limit fired while comparing these two, so this is a partial answer",
    )

    @property
    def from_a_person(self) -> bool:
        return self.said_by != "the machine"

    @model_validator(mode="after")
    def _verdict_is_one_of_the_four(self) -> "Kinship":
        if self.verdict not in VERDICTS:
            raise ValueError(
                f"{self.verdict!r} is not one of the four answers "
                f"({', '.join(VERDICTS)}). A fifth answer invented in passing is "
                "how a maybe becomes a yes."
            )
        if self.left == self.right:
            raise ValueError(f"{self.left!r} was compared with itself")
        return self

    @property
    def key(self) -> Tuple[str, str]:
        return tuple(sorted((self.left, self.right)))  # type: ignore[return-value]

    def summary(self) -> str:
        if self.from_a_person:
            was = ""
            if self.machine_said and self.machine_said != self.verdict:
                was = f", where the machine had said {self.machine_said}"
            note = f" — {self.note}" if self.note else ""
            return (
                f"{self.left} + {self.right} — {self.verdict}, "
                f"because {self.said_by} said so{was}{note}"
            )
        reasons = "; ".join(self.because) or "nothing in particular"
        doubts = f" (against: {'; '.join(self.against)})" if self.against else ""
        return (
            f"{self.left} + {self.right} — {self.verdict} at {self.strength:.0%}: {reasons}{doubts}"
        )


class Cluster(BaseModel):
    """A group of pictures that were judged to belong together."""

    name: str
    kind: str
    pictures: List[str] = Field(min_length=1)
    because: List[str] = Field(default_factory=list)
    contested: bool = False
    strength: float = Field(
        1.0,
        ge=0.0,
        le=1.0,
        description="the weakest judgement holding this group together",
    )
    made_of: List[List[str]] = Field(
        default_factory=list,
        description="for a larger thing, the groups of pictures each part was seen in",
    )

    @model_validator(mode="after")
    def _kind_is_known(self) -> "Cluster":
        if self.kind not in CLUSTER_KINDS:
            raise ValueError(f"{self.kind!r} is not a kind of group ({', '.join(CLUSTER_KINDS)})")
        if self.made_of:
            if self.kind != PARTS_OF_ONE:
                raise ValueError(
                    f"{self.name!r} is {self.kind!r} but says what it is made of. "
                    "Only a larger thing has parts."
                )
            listed = [picture for part in self.made_of for picture in part]
            if sorted(listed) != sorted(self.pictures):
                raise ValueError(
                    f"{self.name!r} holds {sorted(self.pictures)} but its parts "
                    f"account for {sorted(listed)}. A picture cannot be in the "
                    "group and in none of its parts, or in two of them."
                )
        elif self.kind == PARTS_OF_ONE:
            raise ValueError(f"{self.name!r} is a larger thing but does not say what its parts are")
        if self.kind == ALONE and len(self.pictures) != 1:
            raise ValueError(f"{self.name!r} is on its own but holds {len(self.pictures)} pictures")
        if self.kind != ALONE and len(self.pictures) < 2:
            raise ValueError(
                f"{self.name!r} claims to be {self.kind!r} but holds one picture. "
                "A group of one is on its own; say so."
            )
        return self


class Gathering(BaseModel):
    """Many pictures taken in at once, and what came of them."""

    readings: List[Reading] = Field(default_factory=list)
    kinships: List[Kinship] = Field(default_factory=list)
    clusters: List[Cluster] = Field(default_factory=list)
    set_aside: Dict[str, str] = Field(
        default_factory=dict, description="picture name to why it was not placed"
    )
    ignored: Dict[str, str] = Field(
        default_factory=dict,
        description="things a person said that could not be used, and why",
    )
    overruled: List[str] = Field(
        default_factory=list,
        description="places a person's word was taken over the machine's",
    )
    told_about_pictures: int = Field(
        0, ge=0, description="how many single-picture answers a person gave"
    )

    def readable(self) -> List[Reading]:
        return [r for r in self.readings if r.readable]

    def between(self, one: str, other: str) -> Optional[Kinship]:
        wanted = tuple(sorted((one, other)))
        for kinship in self.kinships:
            if kinship.key == wanted:
                return kinship
        return None

    def cluster_holding(self, picture: str) -> Optional[Cluster]:
        for cluster in self.clusters:
            if picture in cluster.pictures:
                return cluster
        return None

    def resolved_share(self) -> float:
        """How much of what was handed in ended up joined to something else."""
        if not self.readings:
            return 0.0
        joined = sum(len(c.pictures) for c in self.clusters if c.kind != ALONE)
        return joined / len(self.readings)

    def shakiest(self, below: float = 0.7) -> List[Cluster]:
        """The groups held together by the weakest evidence, weakest first.

        A group is only as good as the flimsiest judgement in it, so that is what
        is reported. This is the shortlist of what to look at by eye — and it is
        needed, because the sorting is measurably conservative but not
        infallible: on made-up pictures with known answers it has never joined
        photographs that were plainly unrelated, and it has occasionally joined
        two that merely looked alike.
        """
        weak = [c for c in self.clusters if c.kind != ALONE and c.strength < below]
        return sorted(weak, key=lambda c: c.strength)

    def undecided(self) -> List[Kinship]:
        return [k for k in self.kinships if k.verdict == CANNOT_TELL]

    def bounded(self) -> List[Kinship]:
        """Every answer where a limit fired part-way through the comparing.

        A limit makes an endless question answerable at a stated cost: you learn
        "did not finish inside this much", never "there is no answer". That trade
        only holds while the firing is visible, so it is carried on the answer
        itself and said out loud in the report. A limit that fires and is
        swallowed is worse than no limit, because it turns not finishing into a
        plausible answer.
        """
        return [k for k in self.kinships if k.bounded]

    def told(self) -> List[Kinship]:
        """Everything a person decided rather than the machine."""
        return [k for k in self.kinships if k.from_a_person]

    def scorecard(self) -> Dict[str, int]:
        """How the machine did, on the pairs a person has since ruled on.

        Every answer a person gives is a case where the truth is known, so
        helping and checking are the same act. This is what that adds up to.

        - **agreed** — the machine had said the same thing.
        - **overruled** — the machine had said something else, and was wrong.
        - **silent** — the machine had declined; the person supplied the answer.
        """
        agreed = overruled = silent = 0
        for said in self.told():
            if said.machine_said is None or said.machine_said == CANNOT_TELL:
                silent += 1
            elif said.machine_said == said.verdict:
                agreed += 1
            else:
                overruled += 1
        return {
            "you answered": len(self.told()) + self.told_about_pictures,
            "about a pair": len(self.told()),
            "about one picture": self.told_about_pictures,
            "agreed": agreed,
            "overruled": overruled,
            "silent": silent,
        }


__all__ = [
    "ALONE",
    "CANNOT_TELL",
    "CLUSTER_KINDS",
    "Cluster",
    "Gathering",
    "Kinship",
    "PARTS_OF_ONE",
    "Reading",
    "SAME_THING",
    "ShapeMark",
    "Signature",
    "UNRELATED",
    "VERDICTS",
]
