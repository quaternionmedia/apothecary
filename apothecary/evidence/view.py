"""The view: what the log says of a space, as one document, ``apothecary.evidence``.

Pure: the observations and polls are its arguments, and it opens no file, port
or socket. For a space, a moment ``at`` and a span from ``since``:

- ``subjects``: every subject something has said of, each property with its
  latest value at ``at``, every source's own value beside it, and how they
  stand: ``one kind`` (one kind of source says), ``agreed`` (sources of two
  kinds or more give the same value), ``disagreed`` (they differ; both are
  kept, neither is the state), or ``unknown``;
- ``current``: whether a property's source is still heard. A poll's value
  holds until a poll changes it, and is current while its board has answered
  within ``HEARD_S``; past that it is *last known at* its moment;
- ``transitions``: in the span, each word that changed (a printer's state, a
  board present or not), with the evidence on either side;
- ``series``: in the span, each number as it moved, for a timeline's strips,
  each point ``[at, value, poll]``;
- ``polls``: the polls in the span, by id, so a line opens its evidence;
- ``frames``: the frames kept with polls in the span, each with its camera,
  its poll and the subjects that poll speaks of, and ``frame_sizes``: per
  subject, what its kept frames take and the budget they live under.

Every value names the observations it rests on; the document shows nothing
that cannot.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .observation import Observation

FORMAT = "apothecary.evidence"
VERSION = 1
# A board that has not answered for this long is not heard: its values are last known.
HEARD_S = 90.0
# Numbers this close are the same value when two sources are compared.
SAME = {"temperature": 1.0, "target": 0.0, "progress": 0.01}
NUMBERS = ("temperature", "target", "progress")


def _same(prop: str, a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= SAME.get(prop, 0.0)
    return a == b


def _ref(each: Observation, kind: str) -> Optional[str]:
    return next((ref.id for ref in each.evidence if ref.kind == kind), None)


def _line(each: Observation) -> dict:
    return {
        "value": each.value,
        "unit": each.unit,
        "why": each.why,
        "confidence": each.confidence,
        "origin": each.origin.model_dump(),
        "at": each.at.isoformat(),
        "evidence": [ref.model_dump() for ref in each.evidence],
    }


def document(
    space: str,
    observations: List[Observation],
    polls: List[dict],
    at: datetime,
    since: datetime,
    unreadable: int = 0,
    frames: Optional[List[dict]] = None,
    frame_sizes: Optional[Dict[str, dict]] = None,
) -> dict:
    """The space as the log has it at ``at``, and what moved since ``since``."""
    upto = sorted((o for o in observations if o.at <= at), key=lambda o: o.at)
    poll_by_id = {p["id"]: p for p in polls}
    heard: Dict[str, datetime] = {}
    for poll in polls:
        moment = datetime.fromisoformat(poll["polled_at"])
        if moment <= at and poll.get("state") != "offline":
            identity = poll.get("identity") or poll.get("port")
            heard[identity] = max(heard.get(identity, moment), moment)

    # The newest of each source, per subject and property.
    latest: Dict[Tuple[str, str], Dict[Tuple[str, str], Observation]] = {}
    for each in upto:
        source = (each.origin.kind, each.origin.by)
        latest.setdefault((each.subject, each.property), {})[source] = each

    subjects: Dict[str, List[dict]] = {}
    for (subject, prop), sources in sorted(latest.items()):
        said = sorted(sources.values(), key=lambda o: o.at)
        newest = said[-1]
        kinds = {o.origin.kind for o in said if o.value is not None}
        values = [o for o in said if o.value is not None]
        if not values:
            standing = "unknown"
        elif all(_same(prop, values[0].value, o.value) for o in values):
            standing = "agreed" if len(kinds) > 1 else "one kind"
        else:
            standing = "disagreed"
        poll = poll_by_id.get(_ref(newest, "poll") or "")
        identity = (poll or {}).get("identity") or (poll or {}).get("port")
        last_heard = heard.get(identity) if identity else None
        current = last_heard is not None and (at - last_heard).total_seconds() <= HEARD_S
        subjects.setdefault(subject, []).append(
            {
                "property": prop,
                **_line(newest),
                "standing": standing,
                "current": current,
                "heard_at": last_heard.isoformat() if last_heard else None,
                "sources": [_line(o) for o in said] if len(said) > 1 else [],
            }
        )

    span = [o for o in upto if o.at >= since]
    transitions: List[dict] = []
    series: Dict[str, List[list]] = {}
    before: Dict[Tuple[str, str], Observation] = {}
    for each in upto:
        key = (each.subject, each.property)
        if each.property in NUMBERS:
            if each.at >= since and isinstance(each.value, (int, float)):
                series.setdefault(f"{each.subject}|{each.property}", []).append(
                    [each.at.isoformat(), each.value, _ref(each, "poll")]
                )
            continue
        if each.property == "position":
            if each.at >= since and isinstance(each.value, dict) and "z" in each.value:
                series.setdefault(f"{each.subject}|z", []).append(
                    [each.at.isoformat(), each.value["z"], _ref(each, "poll")]
                )
            continue
        prior = before.get(key)
        if (
            each.at >= since
            and prior is not None
            and not _same(each.property, prior.value, each.value)
        ):
            transitions.append(
                {
                    "subject": each.subject,
                    "property": each.property,
                    "from": prior.value,
                    "to": each.value,
                    "at": each.at.isoformat(),
                    "was_at": prior.at.isoformat(),
                    "before": [ref.model_dump() for ref in prior.evidence],
                    "after": [ref.model_dump() for ref in each.evidence],
                }
            )
        before[key] = each

    in_span = [
        {k: p.get(k) for k in ("id", "port", "identity", "polled_at", "state")}
        for p in polls
        if since <= datetime.fromisoformat(p["polled_at"]) <= at
    ]
    return {
        "format": FORMAT,
        "version": VERSION,
        "space": space,
        "at": at.isoformat(),
        "since": since.isoformat(),
        "subjects": [{"subject": s, "properties": props} for s, props in subjects.items()],
        "transitions": transitions,
        "series": series,
        "polls": in_span,
        "frames": [
            {k: f.get(k) for k in ("id", "camera", "poll", "at", "size", "subjects")}
            for f in frames or []
            if since <= datetime.fromisoformat(f["at"]) <= at
        ],
        "frame_sizes": frame_sizes or {},
        "observations": len(span),
        "unreadable": unreadable,
    }


def default_since(at: datetime) -> datetime:
    return at - timedelta(hours=1)
