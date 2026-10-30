"""A picture of a rig read through its setup, and held in carlos as the rig it shows.

A setup (``apothecary.rig-setup`` version 1) says what a picture shows: the
rig, a ``carlos.patch``; the catalogue entries of its devices, as carlos had
them when the faces were pinned; and, for each module the camera sees, the side
facing it and that face's four corners in the picture, fractions across and
down. The entries travel with the setup because the faces were pinned against
that drawing of each device: a layout changed in carlos since is a setup to
make again, not one to read against a drawing it was not pinned on.

``read`` reads every face a setup pins; ``held`` turns a reading into what
carlos holds -- the rig at the values read, drawn ``irl``, and a state for each
module and each lead, in the levels ``wiring.patch`` has (``none``, ``ok``,
``warn``, ``fault``):

- a module: how many of its controls were read, and each that was not, with
  why; a plug seen in a socket no lead names; a face not in the picture;
- a lead: a plug seen at both ends, nothing in one end, or an end on a face
  the camera does not see.

A control not read keeps the rig's own value, so carlos draws what the rig says
there, and the module's state says it was not read.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..wiring.patch import LeadState, State, States
from . import look, panels
from .look import Plug, Seen

SETUP_FORMAT = "apothecary.rig-setup"
SETUP_VERSION = 1


class FaceInPicture(BaseModel):
    """One module's face, where it lies in the picture."""

    model_config = ConfigDict(extra="forbid")

    side: str = "front"
    corners: List[Tuple[float, float]]

    @field_validator("corners")
    @classmethod
    def _four(cls, corners: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        if len(corners) != 4:
            raise ValueError("a face lies in a picture by its four corners")
        return corners


class Setup(BaseModel):
    """What a camera's pictures of a rig show."""

    model_config = ConfigDict(extra="forbid")

    format: str = SETUP_FORMAT
    version: int = SETUP_VERSION
    rig: Dict[str, Any]
    devices: List[Dict[str, Any]]
    faces: Dict[str, FaceInPicture] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _says_what_it_shows(self) -> "Setup":
        if self.format != SETUP_FORMAT or self.version != SETUP_VERSION:
            raise ValueError(f"not an {SETUP_FORMAT} version {SETUP_VERSION} document")
        modules = {module["id"]: module["type"] for module in self.rig.get("modules", [])}
        have = {entry["id"] for entry in self.devices}
        for module_id, device in modules.items():
            if device not in have:
                raise ValueError(
                    f"module {module_id} is a {device}, and the setup has no entry for it"
                )
        for module_id in self.faces:
            if module_id not in modules:
                raise ValueError(f"a face is pinned for {module_id}, which the rig does not have")
        return self

    def entry(self, device: str) -> Dict[str, Any]:
        return next(entry for entry in self.devices if entry["id"] == device)

    @classmethod
    def load(cls, path: Path) -> "Setup":
        return cls.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


class ModuleReading(BaseModel):
    module: str
    device: str
    side: Optional[str] = None  # the face read; None when none is pinned
    seen: List[Seen] = Field(default_factory=list)
    plugs: List[Plug] = Field(default_factory=list)
    why: Optional[str] = None  # why nothing was read


class Reading(BaseModel):
    """One picture of the rig, read."""

    picture: str
    at: Optional[str] = None  # when it was taken, as its name or its file says
    modules: List[ModuleReading] = Field(default_factory=list)

    def values(self) -> Dict[str, Dict[str, float]]:
        """Each module's values read, as carlos is sent them."""
        return {
            m.module: {s.name: _number(s.value) for s in m.seen if s.value is not None}
            for m in self.modules
        }

    def plugged(self) -> Dict[str, Dict[str, bool]]:
        return {
            m.module: {p.name: p.plugged for p in m.plugs if p.plugged is not None}
            for m in self.modules
        }


def read(
    setup: Setup, picture: Path, grey: Optional[look.Grey] = None, at: Optional[str] = None
) -> Reading:
    """Every face the setup pins, read off one picture."""
    grey = grey if grey is not None else look.Grey.open(picture)
    reading = Reading(picture=Path(picture).name, at=at)
    for module in setup.rig.get("modules", []):
        found = ModuleReading(module=module["id"], device=module["type"])
        face = setup.faces.get(module["id"])
        if face is None:
            found.why = "not in the picture: no face of it is pinned"
        else:
            found.side = face.side
            panel = panels.panel(setup.entry(module["type"]), face.side)
            if panel is None:
                found.why = "its entry has no measured panel to read it against"
            else:
                found.seen, found.plugs = look.read_face(grey, panel, face.corners)
        reading.modules.append(found)
    return reading


def _labels(entry: Dict[str, Any]) -> Dict[str, str]:
    return {jack["name"]: jack.get("label") or jack["name"] for jack in entry.get("jacks", [])}


def _number(value: float) -> float:
    """A value as carlos keeps it: whole when it is near enough whole."""
    rounded = round(value, 1)
    return float(int(rounded)) if rounded == int(rounded) else rounded


def held(setup: Setup, reading: Reading) -> Tuple[Dict[str, Any], States]:
    """The rig at the values read, drawn irl, and each module's and lead's state."""
    patch = copy.deepcopy(setup.rig)
    patch["display"] = {**patch.get("display", {}), "mode": "irl"}
    by_id = {m.module: m for m in reading.modules}
    states = States()
    plugged: Dict[Tuple[str, str], Optional[bool]] = {}
    named = set()
    for connection in patch.get("connections", []):
        for end in (connection["source"], connection["target"]):
            named.add((end["module"], end["jack"]))

    for module in patch.get("modules", []):
        found = by_id[module["id"]]
        entry = setup.entry(module["type"])
        state = State()
        if found.side is None or found.why:
            state.says.append(found.why or "not in the picture")
            states.modules[module["id"]] = state
            continue
        module["view"] = found.side
        values = dict(module.get("parameters", {}))
        unread = [s for s in found.seen if s.value is None]
        for seen in found.seen:
            if seen.value is not None:
                values[seen.name] = _number(seen.value)
        module["parameters"] = values
        state.at_least("ok")
        state.says.append(
            f"read: {len(found.seen) - len(unread)} of {len(found.seen)} controls on its {found.side}"
        )
        for seen in unread:
            if seen.kind != "encoder":
                state.at_least("warn")
            state.says.append(f"not read: {seen.name}, {seen.why}")
        labels = _labels(entry)
        for plug in found.plugs:
            plugged[(module["id"], plug.name)] = plug.plugged
            if plug.plugged and (module["id"], plug.name) not in named:
                state.at_least("warn")
                state.says.append(
                    f"a plug in {labels.get(plug.name, plug.name)} that no lead names"
                )
        states.modules[module["id"]] = state

    for connection in patch.get("connections", []):
        lead = LeadState(source=connection["source"], target=connection["target"])
        seen_in, empty, unseen = [], [], []
        for end in (connection["source"], connection["target"]):
            module = next(m for m in patch["modules"] if m["id"] == end["module"])
            label = _labels(setup.entry(module["type"])).get(end["jack"], end["jack"])
            where = f"{label} on {end['module']}"
            state_of_end = plugged.get((end["module"], end["jack"]))
            (seen_in if state_of_end else empty if state_of_end is False else unseen).append(where)
        if empty:
            lead.at_least("fault")
            lead.says.extend(f"declared: nothing plugged into {where}" for where in empty)
        elif seen_in and not unseen:
            lead.at_least("ok")
        lead.says.extend(f"seen: a plug in {where}" for where in seen_in)
        lead.says.extend(f"not seen: {where} is not in the picture" for where in unseen)
        states.connections.append(lead)
    return patch, states


# --- the rig, as carlos has it ------------------------------------------------------------


def _example_name(example: str) -> Tuple[str, str]:
    """``<device>.<kind>``, as carlos's menu names an example, split at its last dot."""
    device, _, kind = example.rpartition(".")
    if not device or kind not in ("simple", "complex"):
        raise ValueError(f"an example is <device>.simple or <device>.complex: not {example!r}")
    return device, kind


def rig_from_carlos(url: str, example: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """One of carlos's examples, and the entry of every device in it, asked of carlos."""
    from ..wiring import carlos

    device, kind = _example_name(example)
    rig = carlos.fetch(url, f"/api/catalogue/devices/{device}/examples")["examples"][kind]
    types = sorted({module["type"] for module in rig.get("modules", [])})
    return rig, [carlos.fetch(url, f"/api/catalogue/devices/{name}") for name in types]


def rig_in(catalogue: Path, example: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """The same, read from a carlos checkout's ``catalogue`` folder."""
    _example_name(example)
    rig = json.loads((Path(catalogue) / "examples" / f"{example}.json").read_text(encoding="utf-8"))
    types = sorted({module["type"] for module in rig.get("modules", [])})
    return rig, [
        json.loads((Path(catalogue) / "devices" / f"{name}.json").read_text(encoding="utf-8"))
        for name in types
    ]
