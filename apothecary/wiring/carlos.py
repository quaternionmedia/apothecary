"""Sending a site's wiring to carlos, which holds it and draws it.

Carlos holds and draws a rig from outside and judges none of it; what is in
the rig, and what state each part of it is in, is decided here. One action of
carlos's ``POST /family/cue`` carries it, beside the hub's ``patch`` and
``turn``::

    {"cue": {"number": "<site>", "name": "apothecary: <site>", "fired_at": "..."},
     "action": {"hold": {"patch": <carlos.patch>,
                         "devices": [<every entry the patch names>],
                         "states": {"modules": {<id>: {level, says}},
                                    "connections": [{source, target, level, says}]}}}}

Carlos answers ``200 {"ok": true, ...}`` or ``422 {"ok": false, "error"}``.
The devices travel with the rig because carlos's catalogue has no board and
no computer; carlos holds them for drawing that rig only.

Carlos is reached on this machine alone: its address is ``serve --carlos``'s
(``APOTHECARY_CARLOS``), a loopback URL, and stays_local's guard refuses any
other. ``Follower`` sends one site's wiring at the start and again whenever it
changes, so carlos's tabs follow the bench as apothecary sees it.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable, Dict, Optional
from urllib.parse import urlsplit

from . import catalogue

if TYPE_CHECKING:  # pragma: no cover - for readers and type checkers only
    from .patch import Wiring

log = logging.getLogger(__name__)

CARLOS_ENV = "APOTHECARY_CARLOS"  # carlos's base URL, as serve --carlos gives it
SITE_ENV = "APOTHECARY_CARLOS_SITE"  # the site it is sent; the garage when unset
DEFAULT_SITE = "garage"
TIMEOUT_SECONDS = 5  # carlos's own peers.json timeout for a call across the seam
EVERY_SECONDS = 2.0  # how often the follower looks at the bench


class CarlosError(RuntimeError):
    """Carlos refused what it was sent, or did not answer."""


def loopback_url(url: str) -> str:
    """``url`` without a trailing slash, when it is http on this machine; else ValueError."""
    parts = urlsplit(url)
    if parts.scheme != "http" or parts.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError(f"carlos is reached on this machine only, over http: not {url!r}")
    return url.rstrip("/")


def carlos_url() -> Optional[str]:
    url = os.environ.get(CARLOS_ENV)
    return loopback_url(url) if url else None


def hold_body(wiring: "Wiring", fired_at: Optional[datetime] = None) -> Dict[str, object]:
    """The cue that has carlos hold this wiring."""
    entries = catalogue.entries()
    named = sorted({module["type"] for module in wiring.patch["modules"]})
    return {
        "cue": {
            "number": wiring.site,
            "name": f"apothecary: {wiring.site}",
            "fired_at": (fired_at or datetime.now(timezone.utc)).isoformat(),
        },
        "action": {
            "hold": {
                "patch": wiring.patch,
                "devices": [entries[device] for device in named],
                "states": wiring.states.model_dump(mode="json"),
            }
        },
    }


def send(body: Dict[str, object], url: str) -> Dict[str, object]:
    """POST the cue to carlos; its answer, or CarlosError saying why not."""
    request = urllib.request.Request(
        f"{loopback_url(url)}/family/cue",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # No proxy: a loopback address is reached directly, whatever the environment says.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            said = json.loads(exc.read().decode("utf-8")).get("error")
        except (ValueError, AttributeError):
            said = None
        raise CarlosError(f"carlos refused the rig ({exc.code}): {said or exc.reason}") from None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise CarlosError(f"carlos did not answer at {url}: {exc}") from None


class Follower:
    """Sends one site's wiring to carlos at the start and whenever it changes.

    ``wiring`` makes the site's wiring afresh each look. What changed is the
    hold without its cue's time, so an unchanged bench is sent once; a send
    carlos did not take is tried again at the next look.
    """

    def __init__(self, url: str, wiring: Callable[[], "Wiring"], every: float = EVERY_SECONDS):
        self.url = loopback_url(url)
        self.wiring = wiring
        self.every = every
        self.last_sent: Optional[str] = None
        self.last_error: Optional[str] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def look(self) -> bool:
        """One look at the bench: True when it was sent."""
        body = hold_body(self.wiring())
        held = json.dumps(body["action"], sort_keys=True)
        if held == self.last_sent:
            return False
        try:
            send(body, self.url)
        except CarlosError as exc:
            if str(exc) != self.last_error:
                log.warning("wiring: %s", exc)
            self.last_error = str(exc)
            return False
        self.last_sent, self.last_error = held, None
        return True

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.look()
            except Exception:  # pragma: no cover - a look that fails is logged; the next one runs
                log.exception("wiring: a look at the bench failed")
            self._stop.wait(self.every)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="wiring-to-carlos", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.every + TIMEOUT_SECONDS)
