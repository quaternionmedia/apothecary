"""Origins switched off: a list in the state folder, read before anything is asked.

An origin is a reader (``plain/colour``) or a model through qmcp
(``qmcp/<model>@<version>``). One switched off is not asked, and what it said
already leaves every view and stays in the record, marked. A person is never an
origin to switch off.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict

from ..firmware.devices import private_folder, state_dir

_lock = threading.Lock()


def path() -> Path:
    return state_dir() / "vision" / "switches.json"


def read() -> Dict[str, bool]:
    """Every origin a person has switched, on (True) or off (False)."""
    try:
        listed = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): bool(v) for k, v in listed.items()} if isinstance(listed, dict) else {}


def is_on(origin: str) -> bool:
    return read().get(origin, True)


def switch(origin: str, on: bool) -> Dict[str, bool]:
    """Switch one origin on or off, and give every switch."""
    if origin == "person":
        raise ValueError("a person's word is never switched off")
    with _lock:
        switched = read()
        switched[origin] = on
        where = path()
        private_folder(where.parent)
        where.write_text(json.dumps(switched, indent=2, sort_keys=True), encoding="utf-8")
    return switched
