"""A site's lighting rig and its live console state, over HTTP.

- ``GET /sites/{s}/lighting``: the rig (types, patches, universes) and its checks.
- ``GET /sites/{s}/lighting/state``: the latest levels, by channel, how old they are,
  each channel's colour (``rgb``, 0-255), and the console's own status (``status``: the
  latest arguments of each OSC ``/eos/out/...`` message it sent).
- ``PUT /sites/{s}/lighting/state`` ``{levels?, dmx?}``: levels by channel number
  (``{"9": {"Pan": 0.25}}``, 0-1), and/or a universe's 512 slots as base64
  (``{"dmx": {"1": "..."}}``). A bridge or the simulator writes here.

A site has a rig only if a loader is registered for it in ``RIG_LOADERS``; the
loader returns ``None`` when the venue's files are not on this machine, and the
site then answers 404 for lighting. Plain ``def``: the state has its own lock.
"""

from __future__ import annotations

import base64
import binascii
import os
import threading
from typing import Callable, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..console_feedback import ConsoleState, OscReceiver, SacnReceiver
from ..lighting import DMX_CHANNELS, LightingRig, fixture_color, validate_rig

router = APIRouter()

RIG_LOADERS: Dict[str, Callable[[], Optional[LightingRig]]] = {}
_states: Dict[str, ConsoleState] = {}
_lock = threading.Lock()


class LevelsIn(BaseModel):
    levels: Dict[int, Dict[str, float]] = {}
    dmx: Dict[int, str] = {}


CONSOLE_SACN_ENV = "APOTHECARY_CONSOLE_SACN"  # set by `apothecary serve --console-sacn`
CONSOLE_OSC_ENV = "APOTHECARY_CONSOLE_OSC"  # set by `apothecary serve --console-osc`
_receivers: list = []


def start_console_feeds() -> None:
    """Listen for a console's sACN and OSC, as ``serve --console-sacn`` and ``--console-osc`` asked, for every site with a rig.

    shortcut: the ports are shared, so a second site with a rig would split packets with
    the first (SO_REUSEPORT); upgrade to one receiver routing by universe when there is one.
    """
    for name in RIG_LOADERS:
        state = _rig_state(name)
        if state is None:
            continue
        if os.environ.get(CONSOLE_SACN_ENV):
            _receivers.append(SacnReceiver(state, state.rig.universes))
        if os.environ.get(CONSOLE_OSC_ENV):
            _receivers.append(OscReceiver(state))
    for receiver in _receivers:
        receiver.start()


def stop_console_feeds() -> None:
    while _receivers:
        _receivers.pop().stop()


def _rig_state(name: str) -> Optional[ConsoleState]:
    with _lock:
        if name not in _states:
            loader = RIG_LOADERS.get(name)
            rig = loader() if loader else None
            if rig is None:
                return None
            _states[name] = ConsoleState(rig)
        return _states[name]


def _state(name: str) -> ConsoleState:
    state = _rig_state(name)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Site '{name}' has no lighting rig")
    return state


@router.get("/sites/{name}/lighting")
def site_lighting(name: str) -> dict:
    # A site with no rig answers 200 with none: the viewer asks every site, and a 404 is a console error on each.
    state = _rig_state(name)
    if state is None:
        return {"rig": None, "universes": [], "unplaced": 0, "violations": []}
    rig = state.rig
    report = validate_rig(rig)
    return {
        "rig": rig.model_dump(mode="json"),
        "universes": rig.universes,
        "unplaced": len(rig.unplaced()),
        "violations": [v.model_dump(mode="json") for v in report.violations],
    }


@router.get("/sites/{name}/lighting/state")
def site_lighting_state(name: str) -> dict:
    snap = _state(name).snapshot()
    # The colour each fixture shows, so the page does not repeat the rig's colour rules.
    snap["rgb"] = {str(ch): list(fixture_color(levels)) for ch, levels in snap["channels"].items()}
    return snap


@router.put("/sites/{name}/lighting/state")
def put_site_lighting_state(name: str, body: LevelsIn) -> dict:
    state = _state(name)
    try:
        if body.levels:
            state.set_levels(body.levels)
        for universe, encoded in body.dmx.items():
            if universe not in state.rig.universes:
                raise ValueError(f"universe {universe} is not in this rig")
            try:
                slots = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError):
                raise ValueError(f"universe {universe}: slots are not base64") from None
            if len(slots) > DMX_CHANNELS:
                raise ValueError(f"universe {universe}: more than {DMX_CHANNELS} slots")
            state.apply_universe(universe, slots)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"channel {exc.args[0]} is not in this rig") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return state.snapshot()
