"""What was asked about a shape in a view, and what each origin said: in memory.

A shape found in a view is a region of a picture, so what is said about it is
said of a sighting. Asking reads the shape's colour with the plain reader and
asks qmcp, each unless its origin is switched off; a person's word on a property
is kept as stated, and overrules a guess about the same property, which is kept
and marked. Nothing here is written to disk: what is kept lasts as long as the
server, and at most ``KEPT_MOST`` shapes' worth of it.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..evidence.observation import Observation, Origin, Region, Sighting, model_key, now
from ..evidence.words import COLOUR_UNIT, COLOURS, MATERIAL_UNIT, MATERIALS
from . import qmcp, switches

ASKABLE = ("colour", "material", "label")

Key = Tuple[str, str, int]  # site, view, shape index

# The most shapes kept about; the least recently used go first.
KEPT_MOST = 2048

_lock = threading.Lock()
_kept: "OrderedDict[Key, List[Observation]]" = OrderedDict()


def forget_all() -> None:
    with _lock:
        _kept.clear()


def region(index: int) -> str:
    return f"shape {index}"


def box_of(shape: Any) -> Tuple[float, float, float, float]:
    return (shape.min_point.x, shape.min_point.y, shape.max_point.x, shape.max_point.y)


def labels_for(site: Any) -> List[str]:
    """The words a label is asked among: the names of the things in the site."""
    names = set()
    stack = list(site.children)
    while stack:
        node = stack.pop()
        names.add(node.name)
        stack.extend(node.children)
    return sorted(names)


def _keep(key: Key, seen: Sequence[Observation]) -> None:
    """Keep what was said: a later saying from the same origin about the same
    property takes the place of the earlier, and a person's word marks every
    guess about its property overruled."""
    with _lock:
        held = _kept.setdefault(key, [])
        _kept.move_to_end(key)
        while len(_kept) > KEPT_MOST:
            _kept.popitem(last=False)
        for new in seen:
            held[:] = [
                o
                for o in held
                if not (o.property == new.property and o.origin.key() == new.origin.key())
            ]
            held.append(new)
        stated = {o.property for o in held if o.origin.kind == "stated" and not o.unread}
        for i, o in enumerate(held):
            should = o.origin.kind == "guessed" and o.property in stated
            if bool(o.block.overruled) != should:
                held[i] = o.model_copy(
                    update={"apothecary": o.block.model_copy(update={"overruled": should})}
                )


def ask_about(
    key: Key,
    picture: Path,
    taken: str,
    shape: Any,
    site: Any,
    asked: Sequence[str],
    path: Optional[str] = None,
) -> Dict[str, Any]:
    """Ask about one shape: the plain reader's colour, and qmcp's guesses, each
    unless switched off. What is said is what happened, in a sentence. ``path`` is
    the picture's path under the picture root, as the evidence names it."""
    from ..vision.colour import READER, digest, read_colour

    for prop in asked:
        if prop not in ASKABLE:
            raise ValueError(f"no property {prop!r} to ask about; have {list(ASKABLE)}")
    box = box_of(shape)
    said: List[str] = []
    seen: List[Observation] = []
    if "colour" in asked:
        if switches.is_on(READER):
            seen.extend(read_colour(picture, box, region(key[2]), taken, path=path))
        else:
            said.append(f"{READER} is switched off")
    status = qmcp.status()
    origins = [model_key(m.get("name"), m.get("version")) for m in status["models"]]
    off = [m for m in origins if not switches.is_on(m)]
    if status["state"] == qmcp.NOT_ANSWERING:
        # status has used the deadline: asking again would cost it twice.
        said.append(f"{status['says']}: no model answered")
    elif origins and len(off) == len(origins):
        said.append("every model is switched off: qmcp was not asked")
    else:
        req = qmcp.request(
            picture, digest(picture), taken, [(region(key[2]), box)], asked, labels=labels_for(site)
        )
        guessed, told = qmcp.ask(req)
        seen.extend(o for o in guessed if o.origin.key() not in off)
        said.append(told)
    _keep(key, seen)
    return {"said": "; ".join(said), "about": about(key)}


def say(key: Key, prop: str, value: str, picture_digest: str, shape: Any) -> Dict[str, Any]:
    """A person's word on one property of a shape: kept as stated, first over every
    guess about it."""
    if prop not in ASKABLE:
        raise ValueError(f"no property {prop!r} to say; have {list(ASKABLE)}")
    word = value.strip()
    if not word:
        raise ValueError("a person's word is a word")
    if prop == "colour" and word not in COLOURS:
        raise ValueError(f"a colour is one of {', '.join(COLOURS)}")
    if prop == "material" and word not in MATERIALS:
        raise ValueError(f"a material is one of {', '.join(MATERIALS)}")
    unit = {"colour": COLOUR_UNIT, "material": MATERIAL_UNIT}.get(prop)
    stated = Observation(
        subject=Sighting(
            sighting=Region(picture=picture_digest, region=region(key[2]), box=box_of(shape))
        ),
        property=prop,
        value=word,
        unit=unit,
        origin=Origin(kind="stated", by={"name": "a person, on the page"}),
        at=now(),
        recorded_at=now(),
    )
    _keep(key, [stated])
    return {"said": f"a person says its {prop} is {word}", "about": about(key)}


def about(key: Key) -> Dict[str, Any]:
    """What is kept about a shape, a row for each property that can be asked or
    said, empty until something is: the plain reader's reading, each model's guess
    and the person's word, each with its origin, and whether the guess agrees with
    the reading. An origin switched off is left out of the row and counted."""
    with _lock:
        held = list(_kept.get(key, []))
        if key in _kept:
            _kept.move_to_end(key)
    switched = switches.read()
    rows = []
    for prop in ASKABLE:
        of = [o for o in held if o.property == prop or (prop == "colour" and o.property == "rgb")]
        hidden = [o for o in of if switched.get(o.origin.key(), True) is False]
        shown = [o for o in of if o not in hidden]
        reading = next((o for o in shown if o.origin.kind == "read" and o.property == prop), None)
        rgb = next((o for o in shown if o.property == "rgb"), None)
        person = next((o for o in shown if o.origin.kind == "stated"), None)
        guesses = [o for o in shown if o.origin.kind == "guessed"]
        rows.append(
            {
                "property": prop,
                "reading": _seen(reading, rgb=rgb),
                "guesses": [_seen(g, against=reading) for g in guesses],
                "person": _seen(person),
                "hidden": sum(1 for o in hidden if o.origin.kind == "guessed"),
                "words": list(COLOURS)
                if prop == "colour"
                else list(MATERIALS)
                if prop == "material"
                else None,
            }
        )
    return {"rows": rows}


def _seen(
    o: Optional[Observation],
    rgb: Optional[Observation] = None,
    against: Optional[Observation] = None,
) -> Optional[Dict[str, Any]]:
    if o is None:
        return None
    out: Dict[str, Any] = {
        "value": o.value,
        "why": o.why,
        "confidence": o.confidence,
        "origin": o.origin.key(),
        "kind": o.origin.kind,
        "trusted": o.block.trusted,
        "overruled": bool(o.block.overruled),
        "recorded_at": o.recorded_at.isoformat(),
        "observation": o.model_dump(mode="json"),
    }
    if rgb is not None and not rgb.unread:
        out["rgb"] = rgb.value
    if against is not None and not against.unread and not o.unread:
        out["agrees"] = o.value == against.value
    return out
