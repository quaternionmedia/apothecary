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
  why, which is also that control's own state (``ModuleState.controls``) so
  that carlos draws it unread; a plug seen in a socket no lead names; a face
  not in the picture;
- a lead: a plug seen at both ends, nothing in one end, or an end on a face
  the camera does not see.

A control not read keeps the rig's own value, so carlos draws what the rig says
there, and the module's state says it was not read.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..wiring.patch import LeadState, ModuleState, State, States
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


def held(
    setup: Setup, reading: Reading, leads: Optional[List[Dict[str, Any]]] = None
) -> Tuple[Dict[str, Any], States]:
    """The rig at the values read, drawn irl, and each module's, socket's and lead's state.

    ``leads`` are the rig's leads as they were last held, the setup's when none
    are given: a plug moved in one frame is where it was moved to in the next,
    so a rig re-patched a plug at a time is followed a plug at a time.

    Every socket read has a state of its own when it has something to say: a plug
    in it, a lead's plug that is not, one too small in the picture to read. A lead
    with one plug out, where the picture has a plug in a socket no lead names that
    takes the same plug the same way round, is held moved there, as a warning: a
    hand moved that plug. Only where the pairing is the one there is, one such
    lead and one such socket, since two of each could be paired either way."""
    patch = copy.deepcopy(setup.rig)
    patch["display"] = {**patch.get("display", {}), "mode": "irl"}
    if leads is not None:
        patch["connections"] = copy.deepcopy(leads)
    by_id = {m.module: m for m in reading.modules}
    types = {m["id"]: m["type"] for m in patch.get("modules", [])}
    states = States()
    plugged: Dict[Tuple[str, str], Plug] = {}

    for module in patch.get("modules", []):
        found = by_id[module["id"]]
        state = ModuleState()
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
            # An encoder has no position to read; any other control could have.
            level = "none" if seen.kind == "encoder" else "warn"
            state.at_least(level)
            state.says.append(f"not read: {seen.name}, {seen.why}")
            state.controls[seen.name] = State(level=level, says=[f"not read: {seen.why}"])
        for plug in found.plugs:
            plugged[(module["id"], plug.name)] = plug
        states.modules[module["id"]] = state

    def where(module: str, jack: str) -> str:
        return f"{_labels(setup.entry(types[module])).get(jack, jack)} on {module}"

    connections = patch.get("connections", [])
    moves = _moves(setup, connections, types, plugged)
    moved_from, moved_into = {}, {}
    for (index, role), socket in moves.items():
        old = connections[index][role]
        moved_from[(old["module"], old["jack"])] = where(*socket)
        moved_into[socket] = where(old["module"], old["jack"])
        connections[index][role] = {"module": socket[0], "jack": socket[1]}
    named = {
        (end["module"], end["jack"]) for c in connections for end in (c["source"], c["target"])
    }

    for module in patch.get("modules", []):
        found, state = by_id[module["id"]], states.modules[module["id"]]
        if found.side is None or found.why:
            continue
        labels = _labels(setup.entry(module["type"]))
        unread = [plug for plug in found.plugs if plug.plugged is None]
        if unread:
            state.says.append(
                f"not read: {len(unread)} of {len(found.plugs)} sockets on its {found.side}"
            )
        for plug in found.plugs:
            key, label = (module["id"], plug.name), labels.get(plug.name, plug.name)
            if plug.plugged is None:
                # A lead drawn to a socket not read is drawn on the rig's word alone.
                level = "warn" if key in named else "none"
                state.at_least(level)
                state.jacks[plug.name] = State(level=level, says=[f"not read: {plug.why}"])
            elif plug.plugged and key in moved_into:
                state.jacks[plug.name] = State(
                    level="warn",
                    says=[
                        f"a plug in it: the lead's from {moved_into[key]}, as the picture has it"
                    ],
                )
            elif plug.plugged and key not in named:
                state.at_least("warn")
                state.says.append(f"a plug in {label} that no lead names")
                state.jacks[plug.name] = State(
                    level="warn", says=["a plug in it that no lead names"]
                )
            elif plug.plugged:
                state.jacks[plug.name] = State(level="ok", says=["seen: a plug in it"])
            elif key in named:
                state.jacks[plug.name] = State(
                    level="fault", says=["declared: a lead's plug, and nothing in it"]
                )
            elif key in moved_from:
                state.jacks[plug.name] = State(
                    level="none", says=[f"empty: its lead's plug is in {moved_from[key]}"]
                )

    for index, connection in enumerate(connections):
        lead = LeadState(source=connection["source"], target=connection["target"])
        seen_in, empty, unseen, unread = [], [], [], []
        for role in ("source", "target"):
            end = connection[role]
            at = where(end["module"], end["jack"])
            plug = plugged.get((end["module"], end["jack"]))
            if plug is None:
                unseen.append(at)
            elif plug.plugged is None:
                unread.append(f"{at}, {plug.why}")
            else:
                (seen_in if plug.plugged else empty).append(at)
            if (index, role) in moves:
                lead.says.append(
                    f"moved: its plug in {moved_into[(end['module'], end['jack'])]} "
                    f"is in {at} now, as the picture has it"
                )
        if empty:
            lead.at_least("fault")
            lead.says.extend(f"declared: nothing plugged into {at}" for at in empty)
        elif seen_in and not unseen and not unread:
            lead.at_least("ok")
        if any((index, role) in moves for role in ("source", "target")):
            lead.at_least("warn")
        lead.says.extend(f"seen: a plug in {at}" for at in seen_in)
        lead.says.extend(f"not read: {at}" for at in unread)
        lead.says.extend(f"not seen: {at} is not in the picture" for at in unseen)
        states.connections.append(lead)
    return patch, states


def _moves(
    setup: Setup,
    connections: List[Dict[str, Any]],
    types: Dict[str, str],
    plugged: Dict[Tuple[str, str], Plug],
) -> Dict[Tuple[int, str], Tuple[str, str]]:
    """Which lead's plug a hand moved, and into which socket, by the lead's
    index and the end: a lead with that end's socket empty and the other end's
    plugged, paired with a socket no lead names that has a plug in it and takes
    the same plug the same way round -- the one lead and the one socket of
    their kind, or none. And none where a plug no lead names is in a socket of
    the other way round: the two could be a new lead's ends."""

    def kind(module: str, jack: str) -> Tuple[Any, Any]:
        entry = next(
            (j for j in setup.entry(types[module]).get("jacks", []) if j["name"] == jack), {}
        )
        return entry.get("type"), entry.get("connector")

    named = {
        (end["module"], end["jack"]) for c in connections for end in (c["source"], c["target"])
    }
    out: Dict[Tuple[Any, Any], List[Tuple[int, str]]] = {}
    for index, connection in enumerate(connections):
        for role, other in (("source", "target"), ("target", "source")):
            here = plugged.get((connection[role]["module"], connection[role]["jack"]))
            there = plugged.get((connection[other]["module"], connection[other]["jack"]))
            if here is not None and here.plugged is False and there is not None and there.plugged:
                out.setdefault(
                    kind(connection[role]["module"], connection[role]["jack"]), []
                ).append((index, role))
    into: Dict[Tuple[Any, Any], List[Tuple[str, str]]] = {}
    for socket, plug in plugged.items():
        if plug.plugged and socket not in named:
            into.setdefault(kind(*socket), []).append(socket)
    other_way = {"input": "output", "output": "input"}
    return {
        ends[0]: into[found][0]
        for found, ends in out.items()
        if len(ends) == 1
        and len(into.get(found, [])) == 1
        and (other_way.get(found[0]), found[1]) not in into
    }


# --- the rig, as carlos has it ------------------------------------------------------------


def _example_name(example: str) -> Tuple[str, str]:
    """``<device>.<kind>``, as carlos's menu names an example, split at its last dot."""
    device, _, kind = example.rpartition(".")
    if not device or kind not in ("simple", "complex"):
        raise ValueError(f"an example is <device>.simple or <device>.complex: not {example!r}")
    return device, kind


def device_from_carlos(url: str, name: str) -> Dict[str, Any]:
    """One device's entry, asked of carlos."""
    from ..wiring import carlos

    return carlos.fetch(url, f"/api/catalogue/devices/{name}")


def rig_from_carlos(url: str, example: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """One of carlos's examples, and the entry of every device in it, asked of carlos."""
    from ..wiring import carlos

    device, kind = _example_name(example)
    rig = carlos.fetch(url, f"/api/catalogue/devices/{device}/examples")["examples"][kind]
    types = sorted({module["type"] for module in rig.get("modules", [])})
    return rig, [device_from_carlos(url, name) for name in types]


def rig_from_file(
    path: Path, more: Optional[Callable[[str], Dict[str, Any]]] = None
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """A rig written as a ``carlos.patch`` file, and the entry of every device in
    it: apothecary's own (``wiring/catalogue``) first, then what ``more`` gives
    for the rest -- carlos's, asked of carlos or read from its catalogue."""
    from ..wiring import catalogue as own

    rig = json.loads(Path(path).read_text(encoding="utf-8"))
    devices = []
    for name in sorted({module["type"] for module in rig.get("modules", [])}):
        if name in own.entries():
            devices.append(own.entries()[name])
        elif more is not None:
            devices.append(more(name))
        else:
            raise ValueError(
                f"{name} is not one of apothecary's devices: name carlos, or its catalogue, for it"
            )
    return rig, devices


def device_in(catalogue: Path, name: str) -> Dict[str, Any]:
    """One device's entry, read from a carlos checkout's ``catalogue`` folder."""
    return json.loads((Path(catalogue) / "devices" / f"{name}.json").read_text(encoding="utf-8"))


def rig_in(catalogue: Path, example: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """The same, read from a carlos checkout's ``catalogue`` folder."""
    _example_name(example)
    rig = json.loads((Path(catalogue) / "examples" / f"{example}.json").read_text(encoding="utf-8"))
    types = sorted({module["type"] for module in rig.get("modules", [])})
    return rig, [device_in(catalogue, name) for name in types]
