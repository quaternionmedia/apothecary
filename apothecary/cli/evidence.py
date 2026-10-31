"""`apothecary evidence`: a working space as its evidence log has it.

Reads the log in the state folder (``apothecary/evidence/``) as the server's
``GET /sites/{s}/evidence`` does, and touches no port, camera or server.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import click

from ..evidence import log


def _ago(raw: str) -> datetime:
    """``90s``, ``15m``, ``2h`` or ``1d`` before now."""
    units = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
    try:
        amount, unit = float(raw[:-1]), units[raw[-1]]
    except (ValueError, KeyError, IndexError):
        raise click.BadParameter("a span like 90s, 15m, 2h or 1d") from None
    return datetime.now(timezone.utc) - timedelta(**{unit: amount})


def _value(prop: dict) -> str:
    if prop.get("value") is None:
        return f"unread: {prop.get('why')}"
    value = prop["value"]
    if isinstance(value, dict):
        value = " ".join(f"{k}={v}" for k, v in value.items())
    unit = prop.get("unit")
    return f"{value}{'' if unit in (None, 'fraction') else ' ' + unit}"


@click.group()
def evidence():
    """A working space seen from every kind of evidence: what the log holds."""


@evidence.command("show")
@click.option(
    "--site", "space", default="garage", show_default=True, help="The space: a site's name."
)
@click.option("--as-json", is_flag=True, help="The apothecary.evidence document itself.")
def show(space: str, as_json: bool):
    """Every subject, each property's value now, how it is known, and whether it is still heard."""
    document = log.document(space)
    if as_json:
        click.echo(json.dumps(document, indent=2))
        return
    if not document["subjects"]:
        click.echo(f"nothing is said of {space} yet: a printer pinned there says it once polled")
        return
    for subject in document["subjects"]:
        click.echo(subject["subject"])
        for prop in subject["properties"]:
            heard = "" if prop["current"] else f", last known at {prop['at']}"
            how = f"{prop['origin']['kind']}, {prop['standing']}"
            click.echo(f"  {prop['property']:<12} {_value(prop):<28} {how}{heard}")
    if document["unreadable"]:
        click.echo(f"{document['unreadable']} line(s) of the log could not be read")


@evidence.command("changed")
@click.option(
    "--site", "space", default="garage", show_default=True, help="The space: a site's name."
)
@click.option(
    "--since", "since", default="1h", show_default=True, help="How far back: 90s, 15m, 2h, 1d."
)
def changed(space: str, since: str):
    """What changed: each word that moved in the span, with what it rests on either side."""
    document = log.document(space, since=_ago(since))
    if not document["transitions"]:
        click.echo(f"nothing changed in {space} since {document['since']}")
        return
    for each in document["transitions"]:
        after = ", ".join(f"{ref['kind']} {ref['id']}" for ref in each["after"])
        click.echo(
            f"{each['at']}  {each['subject']} {each['property']}: "
            f"{each['from']} -> {each['to']}  ({after})"
        )
