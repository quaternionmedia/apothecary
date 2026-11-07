"""A machine's plan: what it will make, made ready before its board is connected.

A machine in a site is a node drawn from a part that is one (``BasePart.machine``: a
printer or a router). Nothing that prepares a job asks its board anything -- the part
it will make, the slice or the toolpath that makes it, the file kept and its path
drawn -- so a machine is prepared with nothing plugged in, and what was chosen is
kept as its plan: the part, and a kept file of the machine's own kind. A plan is kept
per site and machine node in the state folder (``plans/<site>/<node>.json``). The
machine's Machine, opened with its board connected, chooses its plan's part and file;
nothing in a plan is sent anywhere, and ▶ is the board's.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from .firmware import devices
from .projects.parts.skeleton import ROOT
from .projects.registry import PartLoadError, part_named
from .site_names import current
from .state_folder import state_dir, write_whole

NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,199}$")


class MachinePlan(BaseModel):
    site: str
    path: str  # the machine's node
    kind: str  # "printer" or "router"
    part: Optional[str] = None  # the piece of the site it will make, by its path there
    file_id: Optional[str] = None  # the kept file, kept for this kind of machine, that makes it
    planned_at: datetime


@lru_cache(maxsize=None)
def kind_of_part(part_ref: str) -> Optional[str]:
    """The kind of machine a registered part is, or None for a part that is none (or
    none that loads). A wrapper's kind does not change while the server runs."""
    try:
        return part_named(part_ref, ROOT).machine
    except (KeyError, PartLoadError):
        return None


def _kept_at(site: str, path: str) -> Path:
    if not NAME.match(site) or not NAME.match(path):
        raise ValueError(f"no plan can be kept for {site!r}, {path!r}")
    return state_dir() / "plans" / current(site) / f"{path}.json"


def load(site: str, path: str) -> Optional[MachinePlan]:
    kept = _kept_at(site, path)
    try:
        return MachinePlan(**json.loads(kept.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return None


def save(
    site: str, path: str, kind: str, part: Optional[str], file_id: Optional[str]
) -> MachinePlan:
    """Keep the plan of the ``kind`` machine at ``path``: ValueError for a file that is
    not kept, or was kept for another kind of machine than this one."""
    if file_id:
        file = devices.print_file(file_id)
        if file is None:
            raise ValueError(f"no file {file_id!r} is kept")
        if file.machine != kind:
            kept_for = f"a {file.machine}" if file.machine else "no kind of machine"
            raise ValueError(
                f"{file.name} was kept for {kept_for}: a {kind}'s plan names a file kept for a {kind}"
            )
    plan = MachinePlan(
        site=current(site),
        path=path,
        kind=kind,
        part=part or None,
        file_id=file_id or None,
        planned_at=datetime.now(timezone.utc),
    )
    kept = _kept_at(site, path)
    write_whole(kept, plan.model_dump_json(indent=2))
    return plan


def clear(site: str, path: str) -> bool:
    kept = _kept_at(site, path)
    if not kept.is_file():
        return False
    kept.unlink()
    return True
