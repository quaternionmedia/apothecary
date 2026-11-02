"""Frames kept with polls, and the budget they live under.

The page keeps a frame set with a printer's poll: a frame from each camera that
looks at the printer, posted with the poll's id (``POST
/photos/pictures?site=&camera=&poll=``). The picture route keeps the frame
under ``captures/`` as it keeps any camera's, and records it here, in the
space's ``frames/`` files: its path under the picture root, its camera, its
size, the poll it was kept with and the subjects that poll speaks of. The poll
is written to the log if it was not yet, so the frame's evidence resolves.

Each printer's kept frames live under a size budget, ``DEFAULT_BUDGET`` unless
the space's ``budgets.json`` names another for it. Past it the oldest are
forgotten first, a timelapse's frames only when no other kept frame is left;
a picture a person took by hand is not a kept frame, and is never counted or
forgotten. A forgotten frame is a record too, so the log says where it went.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import log

DEFAULT_BUDGET = 5 * 10**9  # bytes a printer's kept frames may take: 5 GB
BUDGETS = "budgets.json"


class NotHeld(LookupError):
    """A frame named a poll this server no longer holds, or one of another space."""


def _collector():
    # Looked up at each call, so a test's fresh collector is the one asked.
    from . import printers

    return printers.COLLECTOR


def holds(site: str, poll: str) -> bool:
    """Whether ``poll`` is one of ``site``'s this server still holds, so a frame can
    be kept with it."""
    held = _collector().held(poll)
    return held is not None and site in held["spaces"]


def keep(
    site: str, camera: str, path: str, size: int, poll: str, at: Optional[datetime] = None
) -> dict:
    """``path`` (under the picture root) recorded as kept with ``poll``; the record."""
    held = _collector().held(poll)
    if held is None or site not in held["spaces"]:
        raise NotHeld(f"poll {poll} is not one of {site}'s this server still holds")
    _collector().keep(poll)
    at = at or datetime.now(timezone.utc)
    record = {
        "id": path,
        "camera": camera,
        "poll": poll,
        "at": at.isoformat(),
        "size": size,
        "subjects": [s for s in held["subjects"] if s.startswith(f"{site}:")],
    }
    log.append(site, log.FRAMES, record, at)
    return record


def forgotten(site: str, path: str, why: str, at: Optional[datetime] = None) -> None:
    at = at or datetime.now(timezone.utc)
    log.append(site, log.FRAMES, {"id": path, "at": at.isoformat(), "forgotten": why}, at)


# The frames a space keeps, as last read, and the files (name, mtime, size) they were read
# from: the files are read again only when one has changed or another has come.
_READ: Dict[str, Tuple[tuple, List[dict]]] = {}
_READING = threading.Lock()


def _files(site: str) -> tuple:
    folder = log.space_dir(site) / log.FRAMES
    try:
        found = sorted(folder.glob("*.jsonl"))
        return (str(folder), *((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in found))
    except OSError:
        return (str(folder),)


def kept(site: str) -> List[dict]:
    """Every kept frame of a space not since forgotten, oldest first."""
    signature = _files(site)
    with _READING:
        held = _READ.get(signature[0])
        if held is not None and held[0] == signature:
            return [dict(r) for r in held[1]]
    found = _read_kept(site)
    with _READING:
        _READ[signature[0]] = (signature, found)
    return [dict(r) for r in found]


def _read_kept(site: str) -> List[dict]:
    live: Dict[str, dict] = {}
    for record in log.read(site, log.FRAMES).records:
        if record.get("forgotten"):
            live.pop(record["id"], None)
        else:
            live[record["id"]] = record
    return sorted(live.values(), key=lambda r: r["at"])


def budget(site: str, subject: str) -> int:
    try:
        named = json.loads((log.space_dir(site) / BUDGETS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        named = {}
    value = named.get(subject) if isinstance(named, dict) else None
    return int(value) if isinstance(value, (int, float)) and value > 0 else DEFAULT_BUDGET


def set_budget(site: str, subject: str, size: int) -> None:
    path = log.space_dir(site) / BUDGETS
    try:
        named = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        named = {}
    named[subject] = int(size)
    from ..firmware.devices import private_folder

    private_folder(path.parent)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".budgets.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(json.dumps(named, indent=2) + "\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def sizes(site: str) -> Dict[str, dict]:
    """Per subject: how much its kept frames take, and its budget."""
    out: Dict[str, dict] = {}
    for record in kept(site):
        for subject in record.get("subjects", []):
            entry = out.setdefault(
                subject, {"bytes": 0, "frames": 0, "budget": budget(site, subject)}
            )
            entry["bytes"] += int(record.get("size", 0))
            entry["frames"] += 1
    return out


def over_budget(site: str, subject: str) -> List[dict]:
    """The kept frames to forget so ``subject``'s fit its budget, in the order they go:
    the oldest first, a timelapse's after every other."""
    mine = [r for r in kept(site) if subject in r.get("subjects", [])]
    total = sum(int(r.get("size", 0)) for r in mine)
    limit = budget(site, subject)
    going: List[dict] = []
    for record in sorted(mine, key=lambda r: (r.get("kept_for") == "timelapse", r["at"])):
        if total <= limit:
            break
        going.append(record)
        total -= int(record.get("size", 0))
    return going
