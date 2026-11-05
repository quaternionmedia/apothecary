"""A site's procedures: the steps that bring its blueprint into working order, fired
through the family's hub.

A procedure is one file under its site in the state folder,
``procedures/<site>/<name>.json``: its steps in order, each with its number, its name,
its discipline, the node it sits on, its notes, the evidence it waits for and its
family block, what each member is handed when it fires. A step whose block is empty
is a person's own: its GO says the person did it.

A hold of carlos's names the site whose wiring it holds, ``{"carlos": {"hold": {"wiring":
"garage"}}}``, and that wiring is read when the step fires.

A step stands by once the step before it has been fired and the evidence it names is
in, as the log last said it. Nothing fires itself: every step waits for GO. A step
refused or failed may be fired again, and ``again`` starts the procedure over.

Each delivery's outcome is kept in the evidence log, ``actions/<day>.jsonl``, where a
restart leaves it. What a member says later is read live, from the audit and from a
hosted member's own state, and is not kept: a page's read of its action, or how work
answered 202 ended.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..evidence import log
from ..firmware.devices import private_folder, state_dir
from ..wiring.carlos import CARLOS
from . import hub, members

Discipline = Literal[
    "mechanical", "electrical", "firmware", "network", "optical", "audio", "lighting"
]

WAITING = "waiting"
STANDING_BY = "standing by"
FIRED = "fired"
DONE = "done"
REFUSED = "refused"
FAILED = "failed"

# Every value in force is said again within a day (evidence/printers.py's REFRESH_S).
SAID_WITHIN = timedelta(days=1, hours=1)
REFUSAL = 422


class Unreadable(ValueError):
    """A procedure's file that is not a procedure, in words that say why."""


class NotStandingBy(RuntimeError):
    """A GO for a step that is not to be fired now: what it is waiting for."""


class Waits(BaseModel):
    """The evidence a step waits for: a subject's property at a value, as the log says it."""

    model_config = ConfigDict(extra="forbid")

    subject: str
    property: str
    value: Any


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: str = Field(min_length=1)
    name: str = Field(min_length=1)
    discipline: Discipline
    node: Optional[str] = None
    notes: str = ""
    waits: Optional[Waits] = None
    family: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class Procedure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: List[Step] = Field(min_length=1)

    @model_validator(mode="after")
    def _numbers_are_one_each(self) -> "Procedure":
        numbers = [step.number for step in self.steps]
        if len(set(numbers)) != len(numbers):
            raise ValueError("each step has a number of its own")
        return self


def _file(site: str, name: str) -> Path:
    return state_dir() / "procedures" / site / f"{name}.json"


def names(site: str) -> List[str]:
    return sorted(path.stem for path in _file(site, "any").parent.glob("*.json"))


def save(site: str, name: str, procedure: Procedure) -> None:
    """Written whole or not at all."""
    path = _file(site, name)
    private_folder(path.parent)
    fresh = path.with_suffix(".writing")
    fresh.write_text(procedure.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(fresh, path)


def load(site: str, name: str) -> Optional[Procedure]:
    """The procedure, None when there is none, ``Unreadable`` when its file will not read."""
    try:
        return Procedure.model_validate(json.loads(_file(site, name).read_text(encoding="utf-8")))
    except FileNotFoundError:
        return None
    except ValueError as exc:  # a hand's edit: not JSON, or not a procedure
        raise Unreadable(f"{site}'s procedure {name} does not read: {exc}") from None


def _standing(outcome: Dict[str, Any]) -> str:
    """How one delivery stands, as its answer and, for work answered 202, as its member says."""
    if outcome.get("status") == REFUSAL:
        return REFUSED
    if outcome.get("error"):
        return FAILED
    if not outcome.get("done"):
        return FIRED
    if outcome.get("status") == 202:
        member = members.hosted(outcome["member"])
        ended = member.ended(outcome["cue"]) if member is not None else None
        if ended is None:
            return FIRED
        if not ended["ok"]:
            outcome["error"] = ended.get("error")
            return FAILED
    return DONE


def _worst(standings: List[str]) -> str:
    return next(each for each in (FAILED, REFUSED, FIRED, DONE) if each in standings)


def _fires(site: str, name: str) -> Dict[str, List[Dict[str, Any]]]:
    """Each step's last fire since the procedure last started over: its outcomes."""
    fires: Dict[str, List[Dict[str, Any]]] = {}
    for record in log.read(site, log.ACTIONS).records:
        if record.get("procedure") != name:
            continue
        if record.get("again"):
            fires.clear()
            continue
        same = fires.get(record["step"], [])
        if same and same[0]["cue"] != record["cue"]:
            same = []
        fires[record["step"]] = [*same, record]
    return fires


def _live(fires: Dict[str, List[Dict[str, Any]]]) -> None:
    """Each kept outcome as the audit has it now, while the audit still holds it."""
    audit = hub.running().snapshot()["last"]
    for outcomes in fires.values():
        for outcome in outcomes:
            for said in audit:
                if said["member"] == outcome["member"] and said["cue"] == outcome["cue"]:
                    outcome.update(done=said["done"], status=said["status"], error=said["error"])


def _said(site: str, now: datetime) -> Dict[Any, Any]:
    """What the log last said of each subject's property."""
    records = log.read(site, log.OBSERVATIONS, since=now - SAID_WITHIN).records
    return {(each.get("subject"), each.get("property")): each.get("value") for each in records}


def _waiting_for(waits: Optional[Waits], said: Dict[Any, Any]) -> Optional[str]:
    """Why the evidence a step names is not in yet; None once it is."""
    if waits is None:
        return None
    now = said.get((waits.subject, waits.property), "nothing yet")
    if now == waits.value:
        return None
    return f"waiting for {waits.subject}'s {waits.property} to be {waits.value}: it is {now}"


def board(site: str, name: str) -> Optional[Dict[str, Any]]:
    """A procedure as it stands: each step, how it stands, why, and whether GO will fire it."""
    procedure = load(site, name)
    if procedure is None:
        return None
    now = datetime.now(timezone.utc)
    fires = _fires(site, name)
    _live(fires)
    said = _said(site, now) if any(step.waits for step in procedure.steps) else {}
    steps = []
    behind: Optional[str] = None  # the step this one waits on, once one is unfinished
    for step in procedure.steps:
        outcomes = fires.get(step.number, [])
        why = None
        if outcomes:
            status = _worst([_standing(outcome) for outcome in outcomes])
            why = next((o["error"] for o in outcomes if o.get("error")), None)
        else:
            why = f"waiting for step {behind}" if behind else _waiting_for(step.waits, said)
            status = WAITING if why else STANDING_BY
        steps.append(
            {
                **step.model_dump(mode="json"),
                "status": status,
                "why": why,
                "can_go": behind is None and status in (STANDING_BY, REFUSED, FAILED),
                "outcomes": outcomes,
            }
        )
        if behind is None and status not in (FIRED, DONE):
            behind = step.number
    return {"site": site, "name": name, "steps": steps}


def _append(site: str, record: Dict[str, Any], at: datetime) -> None:
    log.append(site, log.ACTIONS, {"at": at.isoformat(), **record}, at)


def _handed(family: Dict[str, Any]) -> Dict[str, Any]:
    """A step's block as its members are handed it: a wiring is read when it is held."""
    from ..routes.wiring import hold_action

    handed = {}
    for member, action in family.items():
        hold = action.get("hold")
        named = member == CARLOS and isinstance(hold, dict) and set(hold) == {"wiring"}
        handed[member] = hold_action(hold["wiring"]) if named else action
    return handed


_going = threading.Lock()


def go(site: str, name: str, number: str) -> Dict[str, Any]:
    """Fire one step through the hub, keep each delivery's outcome; the procedure after it."""
    with _going:
        standing = board(site, name)
        if standing is None:
            raise KeyError(name)
        step = next((each for each in standing["steps"] if each["number"] == number), None)
        if step is None:
            raise KeyError(number)
        if not step["can_go"]:
            raise NotStandingBy(step["why"] or f"step {number} is {step['status']}")
        at = datetime.now(timezone.utc)
        cue = {"number": number, "name": step["name"], "fired_at": at.isoformat()}
        running = hub.running()
        running.fire(cue, _handed(step["family"]))
        running.wait(running.timeout + hub.GRACE_SECONDS)
        audit = [each for each in running.snapshot()["last"] if each["cue"] == cue]
        person = {"member": None, "via": None, "status": None, "ms": None}
        kept = audit or [{"cue": cue, **person, "done": True, "error": None, "instance": None}]
        for outcome in kept:
            outcome.pop("answer", None)
            _append(site, {"procedure": name, "step": number, "node": step["node"], **outcome}, at)
    return board(site, name)


def again(site: str, name: str) -> Optional[Dict[str, Any]]:
    """The procedure started over: what came before stays in the log, and counts no more."""
    if load(site, name) is None:
        return None
    _append(site, {"procedure": name, "again": True}, datetime.now(timezone.utc))
    return board(site, name)
