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

from ..state_folder import state_dir, write_whole

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
        # Whole or not at all: a write that stops midway leaves the previous file.
        write_whole(path(), json.dumps(switched, indent=2, sort_keys=True))
    return switched
