"""What is known about each piece, kept beside the arrangement.

An arrangement is a tree of pieces, and a piece is an ordinary node — the same
node everything else in this tool is made of. None of it has anywhere to record
*how* a piece came to be there: which finder saw it, how sure that finder was,
which word it was matched to and why, whether anything about it was measured or
guessed.

That could have been added to the node. It is deliberately not. The shape of a
node is still being decided and is not this feature's to change, and the same
argument was already made for links: a fact *about* a piece belongs beside the
tree, not inside it, so the tree keeps rendering exactly as it did.

The join between the two is the dotted path — ``plate_1``,
``bench.plate_1.relief`` — which is already how every other part of this tool
names a node. Nothing new was needed.

PROTOTYPE — not ratified.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from ..hierarchy import Assembly


class Provenance(BaseModel):
    """How one piece came to be, and how much of it is guessed."""

    word: str
    reason: str
    finder: str
    confidence: float = Field(ge=0.0, le=1.0)
    origin: str
    sized: bool
    turned_degrees: float = 0.0
    thickness_guessed: bool = True
    seen_in: List[str] = Field(default_factory=list)

    @property
    def sightings(self) -> int:
        """In how many pictures this piece was seen.

        One unless several pictures were taken in together and judged to be of
        the same thing. A piece seen twice is not twice as certain — see the way
        the number is combined in ``gathering/combine.py`` — but it is better
        evidence than a piece seen once, and the difference is worth showing.
        """
        return max(1, len(self.seen_in))

    @property
    def shape_was_guessed(self) -> bool:
        """True when a machine decided what this is, rather than a person saying."""
        return self.origin != "stated"

    def summary(self) -> str:
        """One line a person can read."""
        size = "real size" if self.sized else "no real size"
        turn = f", turned {self.turned_degrees:g}°" if self.turned_degrees else ""
        return (
            f"{self.word} — {self.reason}; seen by {self.finder} "
            f"at {self.confidence:.0%} confidence; {size}{turn}"
        )


class Album(BaseModel):
    """One picture, the arrangement built from it, and what is known about each piece."""

    site_name: str
    picture_name: str
    picture_path: Optional[Path] = None
    pixel_width: int
    pixel_height: int
    finder: str
    millimetres_across: Optional[float] = None
    provenance: Dict[str, Provenance] = Field(default_factory=dict)

    @property
    def sized(self) -> bool:
        return self.millimetres_across is not None

    def groups(self) -> Dict[str, List[str]]:
        """Pieces gathered by the word they were matched to, biggest group first.

        This is the grouping the viewer already knows how to show: each piece
        carries its word as its category, so the filter it already has becomes a
        filter by word without a line of new drawing code.
        """
        gathered: Dict[str, List[str]] = {}
        for path, about in self.provenance.items():
            gathered.setdefault(about.word, []).append(path)
        for paths in gathered.values():
            paths.sort()
        return dict(sorted(gathered.items(), key=lambda pair: (-len(pair[1]), pair[0])))

    def unsure(self, below: float = 0.6) -> List[str]:
        """The pieces whose naming should not be trusted, least sure first.

        The finder is measurably less confident when it is wrong, so this is a
        real shortlist of what to look at rather than a decorative one.
        """
        weak = [(a.confidence, p) for p, a in self.provenance.items() if a.confidence < below]
        return [path for _, path in sorted(weak)]

    def seen_in_several(self) -> Dict[str, List[str]]:
        """The pieces more than one picture saw, and which pictures those were.

        Only ever filled in when several pictures were taken in together and
        judged to be of the same thing. It is the difference between a piece one
        camera angle happened to catch and a piece that is really there, so it
        is worth being able to ask for on its own.
        """
        return {
            path: sorted(about.seen_in)
            for path, about in sorted(self.provenance.items())
            if about.sightings > 1
        }

    def guessed_share(self) -> float:
        """How much of this a machine decided the shape of, from 0 to 1.

        Separate from whether it has a real size. A piece can be correctly sized
        in millimetres and still be a machine's guess about what it is, and
        those two doubts want keeping apart.
        """
        if not self.provenance:
            return 0.0
        guessed = sum(1 for about in self.provenance.values() if about.shape_was_guessed)
        return guessed / len(self.provenance)


class Built(BaseModel):
    """An arrangement and what is known about it, handed back together."""

    site: Assembly
    album: Album


__all__ = ["Album", "Built", "Provenance"]
