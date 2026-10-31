"""Where observations are kept: the state folder, one folder a space.

``<state>/evidence/<space>/`` holds a JSON-lines file a day of each kind,
named for the day its records held (UTC), appended to and never rewritten:

- ``observations/2026-10-31.jsonl``, one ``apothecary.observation`` a line;
- ``polls/2026-10-31.jsonl``, the polls observations rest on, each with its id
  and every line the printer sent.

A space is a site, by its name; what no pin attributes to a site goes to
``_sightings``, a name no site can have. The folder is private, as the firmware
state's is: what the person's machines did, and when, is theirs. Nothing here
is committed or sent anywhere.
"""

from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, List, NamedTuple, Optional

from ..firmware.devices import private_folder, state_dir
from .observation import Observation

SIGHTINGS = "_sightings"
OBSERVATIONS = "observations"
POLLS = "polls"
KINDS = (OBSERVATIONS, POLLS)

# One writer at a time in this process; the server is the one process that writes.
_WRITING = threading.Lock()


def root() -> Path:
    return state_dir() / "evidence"


def space_dir(space: str) -> Path:
    if not space or "/" in space or "\\" in space or space.startswith("."):
        raise ValueError(f"{space!r} is not a space")
    return root() / space


def _day_file(space: str, kind: str, day: date) -> Path:
    return space_dir(space) / kind / f"{day.isoformat()}.jsonl"


def _day_of(at: datetime) -> date:
    return at.astimezone(timezone.utc).date()


def append(space: str, kind: str, record: dict, at: datetime) -> Path:
    """One record, as one line, at the end of its day's file."""
    if kind not in KINDS:
        raise ValueError(f"{kind!r} is not a kind of record the log keeps")
    path = _day_file(space, kind, _day_of(at))
    line = json.dumps(record, separators=(",", ":"), default=str) + "\n"
    with _WRITING:
        private_folder(path.parent)
        with path.open("a", encoding="utf-8") as out:
            out.write(line)
    return path


def write(space: str, observations: List[Observation]) -> None:
    for each in observations:
        append(space, OBSERVATIONS, each.model_dump(mode="json", exclude_none=True), each.at)


class Read(NamedTuple):
    records: List[dict]
    unreadable: int  # lines that were not JSON: a disk filled mid-line, an edit by hand


def _days(
    space: str, kind: str, since: Optional[datetime], until: Optional[datetime]
) -> Iterator[Path]:
    folder = space_dir(space) / kind
    if not folder.is_dir():
        return
    first = _day_of(since) if since else None
    last = _day_of(until) if until else None
    for path in sorted(folder.glob("*.jsonl")):
        try:
            day = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if (first and day < first) or (last and day > last):
            continue
        yield path


def read(
    space: str,
    kind: str,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    at_field: str = "at",
) -> Read:
    """Every record of a kind in a space whose moment is in ``[since, until]``, in
    the order written."""
    records: List[dict] = []
    unreadable = 0
    for path in _days(space, kind, since, until):
        with path.open(encoding="utf-8") as lines:
            for line in lines:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    moment = datetime.fromisoformat(record[at_field])
                except (ValueError, KeyError, TypeError):
                    unreadable += 1
                    continue
                if (since and moment < since) or (until and moment > until):
                    continue
                records.append(record)
    return Read(records, unreadable)


def find_poll(space: str, poll_id: str) -> Optional[dict]:
    """The poll record ``poll_id`` names, read from the day its id begins with."""
    try:
        day = datetime.strptime(poll_id[:8], "%Y%m%d").date()
    except ValueError:
        return None
    path = _day_file(space, POLLS, day)
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as lines:
        for line in lines:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("id") == poll_id:
                return record
    return None


def spaces() -> List[str]:
    """Every space the log has a folder for."""
    folder = root()
    return sorted(p.name for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []


def document(space: str, at: Optional[datetime] = None, since: Optional[datetime] = None) -> dict:
    """The view's document for a space, from what the log holds up to ``at``."""
    from . import view

    at = at or datetime.now(timezone.utc)
    since = since or view.default_since(at)
    # Every value in force is said again within a day (printers.REFRESH_S).
    back = since - timedelta(days=1)
    observations = read(space, OBSERVATIONS, since=back, until=at)
    polls = read(space, POLLS, since=back, until=at, at_field="polled_at")
    parsed = []
    unreadable = observations.unreadable + polls.unreadable
    for record in observations.records:
        try:
            parsed.append(Observation.model_validate(record))
        except ValueError:
            unreadable += 1
    return view.document(space, parsed, polls.records, at, since, unreadable)
