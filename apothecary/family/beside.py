"""The members beside the hub, kept running while it runs, by ``hearth.supervise``.

A member served alone is named in the table's ``start`` by how it is started, and the
hub starts it, knows it is up, and starts it again when it stops::

    {"start": {"carlos": {"command": ["carlos", "serve", "--port", "<its port>"],
                          "url": "http://127.0.0.1:<its port>",
                          "cwd": "<its checkout>", "ready": "/family/state"}}}

``url`` is where it answers, on this machine, and it is a push member at that address.
``ready`` is the path that answers 200 once it is up, a redirect not counting:
``/family/identity`` unless named, for a member that does not keep that route yet. The
supervisor starts again a member that does not answer it in time, so a wrong ``ready``
restarts a healthy member. ``cwd`` is optional. An entry that will not read is left out
and said. It is read when the server starts, and every member stops with the server.

A member is its own program, as the slicer is: this process's guard does not reach it,
and it is started without the variables that would redirect a fetch.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional, Set

from hearth.supervise import Spec, Supervisor

from ..state_folder import state_dir
from ..stays_local import PROXY_VARIABLES
from ..wiring.carlos import loopback_url

log = logging.getLogger(__name__)

# What a member is started without: this process's environment, which would point uv
# at this project's, and its proxies.
NOT_INHERITED = ("VIRTUAL_ENV", "PYTHONPATH", "UV_PROJECT_ENVIRONMENT")

_lock = threading.Lock()
_supervisor: Optional[Supervisor] = None
_said: Set[str] = set()


def say_once(words: str) -> None:
    """A table's problem, said once: the table is read at every look at the family."""
    if words not in _said:
        _said.add(words)
        log.warning("%s", words)


def _spec(name: str, entry: Any, table: str) -> Optional[Spec]:
    """One entry as hearth's supervisor takes it; None, and said, when it will not read."""
    try:
        command, url = entry["command"], loopback_url(entry["url"])
        if not (isinstance(command, list) and command and all(isinstance(c, str) for c in command)):
            raise TypeError("command is a list of words")
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        say_once(f"family: {table}.start {name} is left out: {exc}")
        return None
    unset = {key: None for key in os.environ if key.lower() in PROXY_VARIABLES}
    unset.update(dict.fromkeys(NOT_INHERITED))
    return Spec(
        name,
        command,
        url,
        cwd=entry.get("cwd"),
        env=unset,
        ready=entry.get("ready", "/family/identity"),
    )


def specs(start: Any, table: str) -> List[Spec]:
    if not isinstance(start, dict):
        return []
    made = (_spec(name, entry, table) for name, entry in start.items())
    return [spec for spec in made if spec is not None]


def start(wanted: Any, table: str) -> None:
    """Start what the table's ``start`` names, once."""
    global _supervisor
    with _lock:
        named = specs(wanted, table)
        if _supervisor is None and named:
            _supervisor = Supervisor(
                named, logs=state_dir() / "family-logs", log=lambda said: log.info("%s", said)
            )
            _supervisor.start()


def stop() -> None:
    global _supervisor
    with _lock:
        if _supervisor is not None:
            _supervisor.stop()
        _supervisor = None
        _said.clear()


def status() -> Dict[str, Dict[str, Any]]:
    """What each member beside the hub is doing now, as the supervisor says it."""
    with _lock:
        return _supervisor.status() if _supervisor is not None else {}
