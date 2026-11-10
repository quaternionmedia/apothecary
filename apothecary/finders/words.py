"""A whiteboard's words sent out: to looksatwords as a transcript, and a note's
region to qmcp.

Both are on this machine and reached over loopback
(``apothecary/stays_local.py``), each only when a person asks, and each that is
not there is said so. What a model answers is kept beside a person's words and
never over them.

A prototype: no ratified record governs it.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ..stays_local import is_loopback
from ..vision.notes import Note, transcript

LOOKSATWORDS_ENV = "APOTHECARY_LOOKSATWORDS"
LOOKSATWORDS = "http://127.0.0.1:1414"
ANALYZE = "/api/conversations/analyze"


class NotServing(ConnectionError):
    """Where the words were to go is not there, or is not on this machine."""


Post = Callable[[str, Dict[str, str]], Dict[str, object]]


def _post(address: str, body: Dict[str, str]) -> Dict[str, object]:
    request = urllib.request.Request(
        address,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as answered:  # noqa: S310 - loopback, checked
        return json.loads(answered.read().decode("utf-8"))


def send_to_looksatwords(
    notes: Sequence[Note], title: str, address: Optional[str] = None, post: Post = _post
) -> Tuple[str, Dict[str, object]]:
    """A whiteboard's words to looksatwords as one transcript: where it was sent,
    and what looksatwords answered. Refused when nothing has words, when the
    address is not on this machine, and when nothing answers there."""
    from urllib.parse import urlsplit

    text = transcript(notes)
    if not text:
        raise ValueError('no note has words yet: `photo notes --say m5="..."` types one')
    base = (address or os.environ.get(LOOKSATWORDS_ENV, "") or LOOKSATWORDS).rstrip("/")
    host = urlsplit(base).hostname
    if not is_loopback(host):
        raise NotServing(
            f"{base} is not on this machine: a whiteboard's words go to looksatwords over "
            "loopback and nowhere else"
        )
    try:
        answer = post(base + ANALYZE, {"text": text, "title": title})
    except (urllib.error.URLError, OSError, ValueError) as down:
        raise NotServing(
            f"looksatwords is not answering at {base} ({down}): `uv run looksatwords serve` "
            "in its checkout starts it"
        ) from None
    return base, answer


def ask_qmcp(
    image: Path,
    notes: Sequence[Note],
    among: Sequence[str],
    ask: Optional[Callable] = None,
) -> Tuple[List[Note], str]:
    """Ask qmcp which of some words each note holds, and keep what it says beside
    a person's own: the notes, and what happened in a sentence. qmcp's vision
    contract answers a label among words it is given, so ``among`` is asked for;
    a note a person has typed is not asked about."""
    from datetime import datetime, timezone

    from ..vision.cache import picture_hash
    from . import qmcp

    wanted = [note for note in notes if not note.words]
    words = sorted({word.strip() for word in among if word.strip()})
    if not wanted:
        return list(notes), "every note has a person's words: nothing was asked"
    if not words:
        raise ValueError(
            "qmcp says which of some words a note holds: give the words it may be with --among"
        )
    request = qmcp.request(
        Path(image),
        picture_hash(Path(image)),
        datetime.now(timezone.utc).isoformat(),
        [(note.id, (note.min[0], note.min[1], note.max[0], note.max[1])) for note in wanted],
        ["label"],
        labels=words,
    )
    seen, happened = (ask or qmcp.ask)(request)
    held = {}
    for observation in seen:
        region = getattr(getattr(observation.subject, "sighting", None), "region", None)
        if observation.property == "label" and observation.value is not None and region:
            held[region] = str(observation.value)
    return [
        note.model_copy(update={"read": held[note.id]}) if note.id in held else note
        for note in notes
    ], happened


__all__ = [
    "ANALYZE",
    "LOOKSATWORDS",
    "LOOKSATWORDS_ENV",
    "NotServing",
    "ask_qmcp",
    "send_to_looksatwords",
]
