"""The family's members' tokens: what a member shows to write to this server as itself.

A name in the hub's table (``hub.py``) is a claim, not a proof: anything on this
machine can post as ``joe``. So the hub makes each member a secret (``make``), shown
once to whoever adds the member and never again. Only its SHA-256 is kept, in
``family-tokens.json`` in the state folder, written whole under one lock and readable by
this account alone, like the table beside it. A member shows its token as
``Authorization: Bearer <token>`` (``HEADER``); ``check`` compares in constant time
and answers a bool. Nothing here logs, returns or raises a token after ``make``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from ..state_folder import state_dir, write_whole

log = logging.getLogger(__name__)

FILE = "family-tokens.json"
FORMAT = "apothecary.family-tokens/1"
# The request header a token travels in, and the scheme it is sent under.
HEADER = "Authorization"
SCHEME = "Bearer"

_lock = threading.Lock()


def tokens_file() -> Path:
    return state_dir() / FILE


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _read() -> Dict[str, Dict[str, str]]:
    """The tokens kept, by member name: none when the file is missing or will not read
    (every member is then refused, which fails closed)."""
    path = tokens_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data["tokens"]
        if not isinstance(rows, dict) or not all(
            isinstance(v, dict) and isinstance(v.get("sha256"), str) for v in rows.values()
        ):
            raise ValueError("not a table of tokens")
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        log.warning(
            "family: %s does not read, so no member has a token: %s", path, type(exc).__name__
        )
        return {}
    return rows


def _write(rows: Dict[str, Dict[str, str]]) -> None:
    write_whole(tokens_file(), json.dumps({"format": FORMAT, "tokens": rows}, indent=2))


def make(name: str) -> str:
    """A new token for ``name``, replacing any it had. The only time it is held in clear:
    it is returned to the person who adds or re-keys the member, and is not kept."""
    token = secrets.token_urlsafe(32)
    with _lock:
        rows = _read()
        rows[name] = {
            "sha256": _hash(token),
            "made_at": datetime.now(timezone.utc).isoformat(),
        }
        _write(rows)
    return token


def fixed(name: str, token: str) -> None:
    """``name``'s token set to the one given: for the simulated server's own state folder,
    whose members' tokens are documented so a sibling can be tried against it."""
    with _lock:
        rows = _read()
        rows[name] = {"sha256": _hash(token), "made_at": datetime.now(timezone.utc).isoformat()}
        _write(rows)


def revoke(name: str) -> bool:
    """``name`` has no token any more; whether it had one."""
    with _lock:
        rows = _read()
        had = rows.pop(name, None) is not None
        if had:
            _write(rows)
    return had


def has(name: str) -> bool:
    return name in _read()


def named() -> List[str]:
    """The members that hold a token."""
    return sorted(_read())


def check(name: str, presented: str) -> bool:
    """Whether ``presented`` is ``name``'s token; False for a member with none."""
    row = _read().get(name)
    if row is None or not presented:
        return False
    return hmac.compare_digest(row["sha256"], _hash(presented))


def bearer(header: str | None) -> str:
    """The token in an ``Authorization`` header's value: empty when it holds none."""
    scheme, _, token = (header or "").partition(" ")
    return token.strip() if scheme.lower() == SCHEME.lower() else ""
