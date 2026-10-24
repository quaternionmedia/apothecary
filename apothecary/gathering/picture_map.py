"""A picture of the gathering itself: which photographs went with which.

Not a picture of the object — a picture of the *sorting*. Every photograph is a
dot; every judgement that two belong together is a line between two dots; a
photograph nothing could be read from sits apart at the bottom, still shown,
because a photograph that quietly vanished would be the one thing this whole
module exists to prevent.

One self-contained page, drawn from a layout worked out here rather than by
anything that moves, so the same gathering always draws the same picture and a
test can say so. Nothing is fetched from anywhere. It reads in light and in dark,
carries a legend and direct labels rather than relying on colour alone, and ends
with the same information as a table for anyone the drawing does not serve.
"""

from __future__ import annotations

import html
import math
from typing import Dict, List, Tuple

from .models import ALONE, CANNOT_TELL, PARTS_OF_ONE, SAME_THING, Cluster, Gathering

# Two hues and a neutral. Checked with the validator on the all-pairs list in
# both light and dark: worst pair well clear of both floors. "Cannot tell" is
# deliberately not a third hue — it is the absence of an answer, and a dashed
# grey line reads as that where a colour would read as a third kind of answer.
SAME_HUE_LIGHT = "#2a78d6"
SAME_HUE_DARK = "#3987e5"
PARTS_HUE_LIGHT = "#eb6834"
PARTS_HUE_DARK = "#d95926"

LANE_WIDE = 240.0
LANE_TALL = 200.0
ALONE_WIDE = 150.0
ALONE_TALL = 74.0
DOT = 9.0
PAD = 60.0


def _places(cluster: Cluster, centre: Tuple[float, float]) -> Dict[str, Tuple[float, float]]:
    """Where each picture in one group sits, worked out the same way every time."""
    cx, cy = centre
    members = list(cluster.pictures)
    if len(members) == 1:
        return {members[0]: (cx, cy)}
    if len(members) == 2:
        return {members[0]: (cx - 46.0, cy), members[1]: (cx + 46.0, cy)}
    radius = 34.0 + 8.0 * len(members)
    spots: Dict[str, Tuple[float, float]] = {}
    for index, name in enumerate(members):
        angle = -math.pi / 2 + index * (2 * math.pi / len(members))
        spots[name] = (cx + radius * math.cos(angle), cy + radius * math.sin(angle))
    return spots


def _layout(
    gathering: Gathering, per_row: int = 3
) -> Tuple[Dict[str, Tuple[float, float]], List[Tuple[Cluster, float, float]], float, float]:
    joined = [c for c in gathering.clusters if c.kind != ALONE]
    alone = [c for c in gathering.clusters if c.kind == ALONE]

    spots: Dict[str, Tuple[float, float]] = {}
    boxes: List[Tuple[Cluster, float, float]] = []
    for index, cluster in enumerate(joined):
        column = index % per_row
        row = index // per_row
        cx = PAD + LANE_WIDE / 2 + column * LANE_WIDE
        cy = PAD + LANE_TALL / 2 + row * LANE_TALL
        boxes.append((cluster, cx, cy))
        spots.update(_places(cluster, (cx, cy)))

    rows = math.ceil(len(joined) / per_row) if joined else 0
    width = PAD * 2 + LANE_WIDE * min(per_row, max(1, len(joined) or per_row))
    height = PAD * 2 + LANE_TALL * rows

    # Pictures that stand on their own are packed tight, several to a row. They
    # are usually most of a folder, and giving each the room a whole group needs
    # pushed the groups off the top of the screen.
    if alone:
        per_alone = max(per_row, int((width - PAD * 2) // ALONE_WIDE))
        top = height + (36.0 if joined else 0.0)
        for index, cluster in enumerate(alone):
            column = index % per_alone
            row = index // per_alone
            spots[cluster.pictures[0]] = (
                PAD + ALONE_WIDE / 2 + column * ALONE_WIDE,
                top + ALONE_TALL / 2 + row * ALONE_TALL,
            )
            boxes.append((cluster, 0.0, 0.0))
        height = top + ALONE_TALL * math.ceil(len(alone) / per_alone)

    unreadable = [r.picture for r in gathering.readings if not r.readable]
    if unreadable:
        base = height + 34.0
        per_unread = max(1, int((width - PAD * 2) // ALONE_WIDE))
        for index, name in enumerate(unreadable):
            spots[name] = (
                PAD + ALONE_WIDE / 2 + (index % per_unread) * ALONE_WIDE,
                base + (index // per_unread) * ALONE_TALL,
            )
        height = base + ALONE_TALL * math.ceil(len(unreadable) / per_unread)

    return spots, boxes, width, height


def _line(
    one: Tuple[float, float],
    other: Tuple[float, float],
    kind: str,
    title: str,
    *,
    by_a_person: bool = False,
) -> str:
    (x1, y1), (x2, y2) = one, other
    if kind == SAME_THING:
        classes = "edge same"
    elif kind == PARTS_OF_ONE:
        classes = "edge parts"
    else:
        classes = "edge unsure"
    # A join a person made is drawn heavier. Which of these somebody knew and
    # which the machine worked out is the most useful thing on this page, and it
    # must not be something you have to hover over to find out.
    if by_a_person:
        classes += " told"
    return (
        f'<line class="{classes}" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}">'
        f"<title>{html.escape(title)}</title></line>"
    )


def _dot(at: Tuple[float, float], name: str, readable: bool, sightings: str, unsure: int) -> str:
    x, y = at
    kind = "dot" if readable else "dot unread"
    shape = f'<circle class="{kind}" cx="{x:.1f}" cy="{y:.1f}" r="{DOT}"/>'
    halo = (
        f'<circle class="unsure-halo" cx="{x:.1f}" cy="{y:.1f}" r="{DOT + 5:.1f}"/>'
        if unsure
        else ""
    )
    label = html.escape(name)
    tail = f" — {unsure} pair(s) could not be decided" if unsure else ""
    return (
        f'<g class="node"><title>{label} — {html.escape(sightings)}{html.escape(tail)}</title>'
        f"{halo}{shape}"
        f'<text class="label" x="{x:.1f}" y="{y + DOT + 15:.1f}">{label}</text></g>'
    )


def as_html(gathering: Gathering, *, title: str = "Which pictures went together") -> str:
    """The whole gathering as one page that needs nothing from anywhere."""
    spots, boxes, width, height = _layout(gathering)
    readable = {r.picture for r in gathering.readings if r.readable}

    edges: List[str] = []
    for cluster, _, _ in boxes:
        if cluster.kind == ALONE:
            continue
        for index, one in enumerate(cluster.pictures):
            for other in cluster.pictures[index + 1 :]:
                kinship = gathering.between(one, other)
                if kinship is None or kinship.verdict in (CANNOT_TELL,):
                    continue
                if kinship.verdict not in (SAME_THING, PARTS_OF_ONE):
                    continue
                edges.append(
                    _line(
                        spots[one],
                        spots[other],
                        kinship.verdict,
                        kinship.summary(),
                        by_a_person=kinship.from_a_person,
                    )
                )
    # Undecided pairs are deliberately *not* drawn as lines. On eighteen
    # photographs there were a hundred and four of them, and drawing each as a
    # line turned the whole picture into a ball of string that hid the four
    # answers it existed to show. They are counted on the picture they touch,
    # named in the table underneath, and that is enough.
    unsure_about: Dict[str, int] = {}
    for kinship in gathering.undecided():
        for side in (kinship.left, kinship.right):
            unsure_about[side] = unsure_about.get(side, 0) + 1

    rings: List[str] = []
    for cluster, cx, cy in boxes:
        if cluster.kind == ALONE:
            continue
        wide = 62.0 + 12.0 * len(cluster.pictures)
        kind = "same" if cluster.kind == SAME_THING else "parts"
        rings.append(
            f'<ellipse class="ring {kind}" cx="{cx:.1f}" cy="{cy:.1f}" '
            f'rx="{wide:.1f}" ry="{wide * 0.78:.1f}"/>'
            f'<text class="ring-label {kind}" x="{cx:.1f}" y="{cy - wide * 0.78 - 10:.1f}">'
            f"{html.escape(cluster.kind)}</text>"
        )

    dots: List[str] = []
    for name, at in spots.items():
        cluster = gathering.cluster_holding(name)
        if name not in readable:
            note = gathering.set_aside.get(name, "nothing could be read from it")
        elif cluster is not None and cluster.kind != ALONE:
            note = f"{cluster.kind}, with {len(cluster.pictures) - 1} other picture(s)"
        else:
            note = "on its own"
        dots.append(_dot(at, name, name in readable, note, unsure_about.get(name, 0)))

    rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(r.picture),
            "yes" if r.readable else "no",
            html.escape(
                (lambda c: c.kind if c else "not placed")(gathering.cluster_holding(r.picture))
            ),
        )
        for r in gathering.readings
    )
    # Only the pairs that got an answer. The undecided ones are counted, not
    # listed: on eighteen photographs they ran to a hundred and four rows, all
    # of them saying the same thing.
    answered = [k for k in gathering.kinships if k.verdict != CANNOT_TELL]
    pairs = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(k.left),
            html.escape(k.right),
            html.escape(k.verdict),
            "you said so" if k.from_a_person else f"{k.strength:.0%}",
            html.escape("; ".join(k.because)[:160]),
        )
        for k in answered
    )

    joined = len([c for c in gathering.clusters if c.kind != ALONE])
    told = gathering.told()
    yours = f" · {len(told)} you decided" if told else ""
    headline = (
        f"{len(gathering.readings)} pictures · {len(readable)} readable · "
        f"{joined} group(s) · {len(gathering.undecided())} pair(s) undecided{yours}"
    )

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  .viz-root {{
    color-scheme: light;
    --surface-1: #fcfcfb;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --muted: #8c8b84;
    --hair: #d9d8d2;
    --same: {SAME_HUE_LIGHT};
    --parts: {PARTS_HUE_LIGHT};
  }}
  @media (prefers-color-scheme: dark) {{
    :root:where(:not([data-theme="light"])) .viz-root {{
      color-scheme: dark;
      --surface-1: #1a1a19;
      --text-primary: #ffffff;
      --text-secondary: #c3c2b7;
      --muted: #8a897f;
      --hair: #3a3a37;
      --same: {SAME_HUE_DARK};
      --parts: {PARTS_HUE_DARK};
    }}
  }}
  :root[data-theme="dark"] .viz-root {{
    color-scheme: dark;
    --surface-1: #1a1a19;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --muted: #8a897f;
    --hair: #3a3a37;
    --same: {SAME_HUE_DARK};
    --parts: {PARTS_HUE_DARK};
  }}
  body {{ margin: 0; background: var(--surface-1); }}
  .viz-root {{
    background: var(--surface-1); color: var(--text-primary);
    font: 14px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 24px;
  }}
  h1 {{ font-size: 19px; margin: 0 0 2px; font-weight: 600; }}
  .headline {{ color: var(--text-secondary); margin: 0 0 18px; }}
  .legend {{ display: flex; flex-wrap: wrap; gap: 18px; margin: 0 0 14px; }}
  .legend span {{ display: inline-flex; align-items: center; gap: 7px;
                  color: var(--text-secondary); }}
  .swatch {{ width: 22px; height: 2px; border-radius: 1px; }}
  .swatch.same {{ background: var(--same); }}
  .swatch.parts {{ background: var(--parts); }}
  .swatch.unsure {{ height: 12px; width: 12px; border-radius: 50%;
                    background: transparent;
                    border: 2px dotted var(--muted); }}
  .swatch.told {{ height: 5px; border-radius: 3px;
                  background: var(--text-secondary); }}
  .swatch.unread {{ height: 10px; width: 10px; border-radius: 50%;
                    background: var(--surface-1);
                    border: 2px dashed var(--muted); }}
  svg {{ max-width: 100%; height: auto; display: block; }}
  .edge {{ stroke-width: 2; fill: none; }}
  .edge.same {{ stroke: var(--same); }}
  .edge.parts {{ stroke: var(--parts); }}
  .edge.unsure {{ stroke: var(--muted); stroke-dasharray: 4 4; }}
  .edge.told {{ stroke-width: 5; stroke-linecap: round; }}
  .unsure-halo {{ fill: none; stroke: var(--muted); stroke-width: 1.5;
                  stroke-dasharray: 2 3; }}
  .ring {{ fill: none; stroke: var(--hair); stroke-width: 1.5; }}
  .ring.same {{ stroke: var(--same); stroke-opacity: 0.35; }}
  .ring.parts {{ stroke: var(--parts); stroke-opacity: 0.35; }}
  .ring-label {{ text-anchor: middle; font-size: 11px; letter-spacing: 0.02em; }}
  .ring-label.same {{ fill: var(--same); }}
  .ring-label.parts {{ fill: var(--parts); }}
  .dot {{ fill: var(--text-primary); stroke: var(--surface-1); stroke-width: 2; }}
  .dot.unread {{ fill: var(--surface-1); stroke: var(--muted);
                 stroke-width: 2; stroke-dasharray: 3 3; }}
  .label {{ text-anchor: middle; font-size: 12px; fill: var(--text-primary); }}
  .node:hover .dot {{ stroke: var(--same); }}
  table {{ border-collapse: collapse; margin-top: 26px; font-size: 13px; }}
  caption {{ text-align: left; padding-bottom: 6px; color: var(--text-secondary); }}
  th, td {{ text-align: left; padding: 5px 16px 5px 0;
            border-bottom: 1px solid var(--hair); }}
  th {{ color: var(--text-secondary); font-weight: 500; }}
</style></head>
<body><div class="viz-root">
<h1>{html.escape(title)}</h1>
<p class="headline">{html.escape(headline)}</p>
<div class="legend">
  <span><i class="swatch same"></i>of the same thing</span>
  <span><i class="swatch parts"></i>parts of one larger thing</span>
  <span><i class="swatch unsure"></i>ring: some pair could not be decided</span>
  <span><i class="swatch told"></i>thick line: you said so, not the machine</span>
  <span><i class="swatch unread"></i>nothing could be read from it</span>
</div>
<svg viewBox="0 0 {width:.0f} {height:.0f}" width="{width:.0f}" height="{height:.0f}"
     role="img" aria-label="{html.escape(headline)}">
  <g>{''.join(rings)}</g>
  <g>{''.join(edges)}</g>
  <g>{''.join(dots)}</g>
</svg>
<table><caption>Every picture handed in</caption>
<thead><tr><th>Picture</th><th>Readable</th><th>Ended up</th></tr></thead>
<tbody>{rows}</tbody></table>
<table><caption>Every pair that got an answer — {len(answered)} of
{len(gathering.kinships)} compared.
The other {len(gathering.kinships) - len(answered)} could not be decided either
way, which is a real answer and not a gap; each one is counted on the
pictures it touches.</caption>
<thead><tr><th>One</th><th>The other</th><th>Judged</th>
<th>How sure</th><th>Because</th></tr></thead>
<tbody>{pairs}</tbody></table>
</div></body></html>
"""


__all__ = ["as_html"]
