"""Who the family's hub names, as a person lists and changes them.

The table is ``family.json`` in the state folder (``hub.py`` reads it). This module
reads it for a person -- each member, where it is reached, what it is for, whether it
holds a token (``tokens.py``) -- and writes it as the hub does: whole, under one lock,
and never over a file that does not read. Nothing here opens a connection: a member's
``capabilities`` are what the hub itself offers of a hosted one, and what a member said
of itself the last time the running hub heard it.
"""

from __future__ import annotations

import json
import re
import threading
from typing import Any, Dict, List, Optional, Tuple

from ..state_folder import write_whole
from ..wiring.carlos import CARLOS, loopback_url
from . import hub, tokens
from . import members as hosted

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")  # surfaces.MEMBER's

_lock = threading.Lock()


class Refused(ValueError):
    """What was asked of the table cannot be done, and why."""


def _strict() -> Dict[str, Any]:
    """The table as written; ``Refused`` for one that does not read, which is never
    written over."""
    path = hub.table_file()
    try:
        table = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise Refused(f"{path} does not read ({exc}): it is left as it is") from None
    if not isinstance(table, dict):
        raise Refused(f"{path} is not a table: it is left as it is")
    return table


def _reserved(name: str) -> Optional[str]:
    if name in hub.PAGE_MEMBERS or hosted.hosted(name) is not None:
        return f"{name} is one of the hub's own members: the table does not name it"
    if name == CARLOS:
        return "carlos is named by `serve --carlos`, or in the table by hand"
    return None


def listing() -> List[Dict[str, Any]]:
    """Every member the hub names: ``name``, ``address`` (its URL, or what it is), ``via``
    (``push``, ``pull``, ``start``, ``local`` or ``page``), ``capabilities`` and ``token``
    (whether it holds one; never the token)."""
    table = hub.table()
    pushed = table.get("members") if isinstance(table.get("members"), dict) else {}
    pulled = table.get("pull") if isinstance(table.get("pull"), list) else []
    started = table.get("start") if isinstance(table.get("start"), dict) else {}
    heard = hub.running().snapshot().get("members", {})
    rows: List[Dict[str, Any]] = []
    for name in sorted({*pushed, *pulled, *started, *hub.members()}):
        own = hosted.hosted(name)
        if own is not None:
            via, address, caps = "local", "this server", list(own.verbs)
        elif name in hub.PAGE_MEMBERS:
            via, address, caps = "page", "the viewer's page", []
        else:
            url = pushed.get(name) or (started.get(name) or {}).get("url")
            via = "start" if name in started else ("push" if name in pushed else "pull")
            address = url if isinstance(url, str) else "-"
            said = (heard.get(name) or {}).get("identity")
            caps = list(said.get("capabilities") or []) if isinstance(said, dict) else []
        rows.append(
            {
                "name": name,
                "address": address,
                "via": via,
                "capabilities": caps,
                "token": tokens.has(name),
            }
        )
    return rows


def _check_name(name: str) -> None:
    if not NAME.match(name):
        raise Refused(f"{name!r} is no member name: letters, digits, _ . - and at most 64")
    if (why := _reserved(name)) is not None:
        raise Refused(why)


def add(name: str, url: str) -> Tuple[str, str]:
    """``name`` named in the table as a push member at ``url`` (on this machine), and
    given a token: ``(url as kept, token)``, the token shown here and never again.
    A member already named at that address is given a new token and left in the table."""
    _check_name(name)
    try:
        kept = loopback_url(url)
    except ValueError:
        raise Refused(
            f"{url!r} is not on this machine: a member is http://127.0.0.1:<port>"
        ) from None
    with _lock:
        table = _strict()
        members = table.get("members") if isinstance(table.get("members"), dict) else {}
        if name in (table.get("pull") or []) or name in (table.get("start") or {}):
            raise Refused(f"{name} is named in the table's pull or start already: remove it first")
        table["members"] = {**members, name: kept}
        write_whole(hub.table_file(), json.dumps(table, indent=2))
        token = tokens.make(name)
    return kept, token


def remove(name: str) -> bool:
    """``name`` out of the table's members, pull and start, and its token revoked; whether
    it was named. A member the hub hosts is not removable."""
    if (why := _reserved(name)) is not None and name != CARLOS:
        raise Refused(why)
    with _lock:
        table = _strict()
        was = False
        if isinstance(table.get("members"), dict) and name in table["members"]:
            del table["members"][name]
            was = True
        if isinstance(table.get("pull"), list) and name in table["pull"]:
            table["pull"] = [n for n in table["pull"] if n != name]
            was = True
        if isinstance(table.get("start"), dict) and name in table["start"]:
            del table["start"][name]
            was = True
        if was:
            write_whole(hub.table_file(), json.dumps(table, indent=2))
        return tokens.revoke(name) or was


def rekey(name: str) -> str:
    """A new token for a member the table names; ``Refused`` for one it does not."""
    if name not in {row["name"] for row in listing()} or hosted.hosted(name) is not None:
        raise Refused(f"{name} is no member the table names: `apothecary family members`")
    return tokens.make(name)
