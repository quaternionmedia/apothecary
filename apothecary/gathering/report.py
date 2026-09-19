"""The gathering, written out as something a person can read.

Plain sentences, no jargon, and every refusal said out loud. A report that only
listed what worked would be a report you could not act on: the useful half is
which pictures could not be placed and what to do about each.
"""

from __future__ import annotations

from typing import List

from .models import ALONE, CANNOT_TELL, PARTS_OF_ONE, SAME_THING, UNRELATED, Gathering
from .questions import worth_asking


def _rule(title: str) -> List[str]:
    return [title, "-" * len(title)]


def as_text(gathering: Gathering, *, everything: bool = False) -> str:
    """One page about what happened to a pile of pictures.

    Set ``everything`` to also list every pair judged unrelated. Off by default
    because on twenty pictures that is a hundred and ninety lines saying nothing
    happened.
    """
    total = len(gathering.readings)
    readable = gathering.readable()
    joined = [c for c in gathering.clusters if c.kind != ALONE]
    lines: List[str] = []

    lines.append(
        f"{total} picture(s) taken in. {len(readable)} could be read. "
        f"{len(joined)} group(s) came out of them."
    )
    if total:
        lines.append(
            f"{gathering.resolved_share():.0%} of the pictures ended up joined to "
            "at least one other."
        )
    told = gathering.told()
    if told:
        lines.append(
            f"{len(told)} of those pairs you decided yourself, and your word was "
            "taken as it stands."
        )
    lines.append("")

    lines += _rule("What went together")
    if not joined:
        lines.append("  Nothing. Every picture stands on its own.")
    for cluster in joined:
        kind = "of the same thing" if cluster.kind == SAME_THING else "parts of one larger thing"
        lines.append(
            f"  {cluster.name} — {len(cluster.pictures)} pictures, {kind}, "
            f"held together at {cluster.strength:.0%}"
        )
        for picture in cluster.pictures:
            lines.append(f"      {picture}")
        if cluster.kind == PARTS_OF_ONE:
            for part in cluster.made_of:
                lines.append(f"      part: {', '.join(part)}")
        for why in cluster.because[:4]:
            lines.append(f"      because {why}")
    lines.append("")

    alone = [c for c in gathering.clusters if c.kind == ALONE]
    if alone:
        lines += _rule("On its own")
        for cluster in alone:
            mark = " (contested)" if cluster.contested else ""
            lines.append(f"  {cluster.pictures[0]}{mark}")
            for why in cluster.because[:2]:
                lines.append(f"      {why}")
        lines.append("")

    unreadable = [r for r in gathering.readings if not r.readable]
    if unreadable:
        lines += _rule("Could not be read at all")
        for reading in unreadable:
            lines.append(f"  {reading.picture} — {reading.because}")
        lines.append("")

    if told:
        card = gathering.scorecard()
        lines += _rule("What you told it, and how the machine did")
        lines.append(
            "  Every answer you give is a case where the answer is known, so it " "checks the"
        )
        lines.append("  machine at the same time as it improves the result.")
        lines.append("")
        lines.append(
            f"  you answered   {card['you answered']}   "
            f"({card['about a pair']} about a pair, "
            f"{card['about one picture']} about one picture)"
        )
        lines.append(f"  agreed         {card['agreed']}   the machine had said the same")
        lines.append(f"  overruled      {card['overruled']}   the machine had said otherwise")
        lines.append(f"  silent         {card['silent']}   the machine had no answer")
        lines.append("")
        for said in told:
            lines.append(f"  {said.summary()}")
        lines.append("")

    if gathering.ignored:
        lines += _rule("Things you said that could not be used")
        lines.append("  Not ignored quietly. Each of these needs something from you.")
        for sentence, why in sorted(gathering.ignored.items()):
            lines.append(f"  {sentence}")
            lines.append(f"      {why}")
        lines.append("")

    if gathering.overruled:
        lines += _rule("Where your word beat the machine's")
        for note in gathering.overruled:
            lines.append(f"  {note}")
        lines.append("")

    undecided = gathering.undecided()
    if undecided:
        lines += _rule("Could not be decided either way")
        lines.append("  These are not failures. They are pairs where the honest answer is")
        lines.append("  that there is not enough to go on, so nothing was merged.")
        for kinship in undecided:
            lines.append(f"  {kinship.left} + {kinship.right}")
            for why in kinship.because:
                lines.append(f"      {why}")
            for doubt in kinship.against:
                lines.append(f"      against: {doubt}")
        lines.append("")

    if everything:
        apart = [k for k in gathering.kinships if k.verdict == UNRELATED]
        if apart:
            lines += _rule("Judged unrelated")
            for kinship in apart:
                lines.append(f"  {kinship.left} + {kinship.right} — {kinship.strength:.0%} sure")
            lines.append("")

    shaky = gathering.shakiest()
    if shaky:
        lines += _rule("Worth checking by eye")
        lines.append("  These groups were formed on the flimsiest evidence in the run.")
        for cluster in shaky:
            lines.append(
                f"  {cluster.name} at {cluster.strength:.0%} — " f"{', '.join(cluster.pictures)}"
            )
        lines.append("")

    asking = worth_asking(gathering, most=5)
    if asking:
        lines += _rule("What would help most")
        lines.append("  You are better at this than the machine is, and it knows which")
        lines.append("  questions are worth your minute. Best first:")
        lines.append("")
        for number, question in enumerate(asking, start=1):
            lines.append(f"  {number}. {question.sentence()}")
            lines.append(f"     {question.worth()}")
        lines.append("")
        lines.append("  Write the answers in a file and hand it back with --answers,")
        lines.append("  or pass --ask to have one written out for you to fill in.")
        lines.append("")

    decided = [k for k in gathering.kinships if k.verdict != CANNOT_TELL]
    lines += _rule("How sure any of this is")
    lines.append(
        f"  {len(gathering.kinships)} pair(s) were compared. {len(decided)} got an "
        f"answer; {len(undecided)} did not."
    )
    lines.append(
        "  Every answer comes from shapes and from how light the pictures are. " "Nothing here"
    )
    lines.append("  was trained on real photographs, and it will be beaten by anything that was.")
    return "\n".join(lines).rstrip() + "\n"


__all__ = ["as_text"]
