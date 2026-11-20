"""A whiteboard's history: what happened to it, in order, and how it stood at a moment.

Every photograph pinned at a whiteboard, every word a person gave on one of its
marks or notes, and every piece made from one, is an event on one timeline. A
moment of it is the whiteboard as it stood then: the newest photograph pinned
by then, with the words given by then. A moment can be placed elsewhere, as a
picture pinned at another place with its words.

Read from what the views keep, in the server's memory: nothing here is stored.

A prototype: no ratified record governs it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Sequence

from pydantic import BaseModel

from .marks import Answers
from .views import Made, View


class Event(BaseModel):
    """One thing that happened to a whiteboard."""

    at: str
    # "photograph", "word" (a mark's kind), "note" (what writing says), "made" or
    # "dropped".
    kind: str
    view: str
    says: str


def photographs(views: Sequence[View], host: str) -> List[View]:
    """The photographs pinned at a whiteboard, oldest first."""
    return sorted(
        (v for v in views if v.host == host and v.squared is not None),
        key=lambda v: datetime.fromisoformat(v.taken_at),
    )


def timeline(
    pictures: Sequence[View],
    kept: Dict[str, Answers],
    made: Dict[str, Made],
    dropped: Sequence[Made] = (),
) -> List[Event]:
    """Every event of a whiteboard's photographs, oldest first: each pinned, each
    word given on it, each piece made from it, and each of those dropped since. A
    word kept with no time is left off, since it has no place on the line."""
    ids = {view.id for view in pictures}
    found: List[Event] = []
    for number, view in enumerate(pictures, start=1):
        found.append(
            Event(
                at=view.taken_at,
                kind="photograph",
                view=view.id,
                says=f"photograph {number} pinned: {len(view.shapes)} shape(s) found"
                if view.found
                else f"photograph {number} pinned",
            )
        )
        answers = kept.get(view.id)
        for example in answers.examples if answers else []:
            if example.at:
                found.append(
                    Event(
                        at=example.at,
                        kind="word",
                        view=view.id,
                        says=f"a mark said to be {example.word.value}, where the sorter said {example.guess.value}",
                    )
                )
        for words in answers.words if answers else []:
            if words.at:
                found.append(
                    Event(
                        at=words.at, kind="note", view=view.id, says=f'a note says "{words.text}"'
                    )
                )
    for record in [*made.values(), *dropped]:
        if record.view in ids and record.made_at:
            found.append(
                Event(
                    at=record.made_at,
                    kind="made",
                    view=record.view,
                    says=f"{record.piece} made, a {record.word}",
                )
            )
        if record.view in ids and record.dropped_at:
            found.append(
                Event(
                    at=record.dropped_at,
                    kind="dropped",
                    view=record.view,
                    says=f"{record.piece} dropped",
                )
            )
    found.sort(key=lambda e: datetime.fromisoformat(e.at))
    return found


def layer_at(pictures: Sequence[View], when: Optional[str]) -> Optional[View]:
    """The photograph the whiteboard stood as at a moment: the newest pinned by
    then, the first before any, the newest when no moment is named."""
    if not pictures:
        return None
    if not when:
        return pictures[-1]
    until = datetime.fromisoformat(when)
    by_then = [v for v in pictures if datetime.fromisoformat(v.taken_at) <= until]
    return by_then[-1] if by_then else pictures[0]


__all__ = ["Event", "layer_at", "photographs", "timeline"]
