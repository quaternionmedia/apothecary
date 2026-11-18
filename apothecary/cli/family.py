"""``apothecary family``: who the family's hub names, and the token each writes with.

Reads and writes the state folder's ``family.json`` and ``family-tokens.json``
(``apothecary/family/roster.py``); opens no connection and starts nothing. The hub of a
running server reads its table afresh at each use.
"""

from __future__ import annotations

import json

import click

from ..family import roster


@click.group()
def family():
    """The family's hub: its members, and the token each writes with."""


def _refused(exc: roster.Refused) -> click.ClickException:
    return click.ClickException(str(exc))


@family.command("members")
@click.option("--json", "as_json", is_flag=True, help="The list as JSON, for a program.")
def members(as_json: bool):
    """List each member: its name, address, what it is for, and whether it holds a token.

    The token itself is never shown here: it was shown once, when it was made."""
    rows = roster.listing()
    if as_json:
        click.echo(json.dumps(rows, indent=2))
        return
    width = max((len(r["name"]) for r in rows), default=4)
    click.echo(f"{'NAME':<{width}}  {'VIA':<5}  {'TOKEN':<5}  ADDRESS  [CAPABILITIES]")
    for r in rows:
        caps = f"  [{', '.join(r['capabilities'])}]" if r["capabilities"] else ""
        token = "yes" if r["token"] else "no"
        click.echo(f"{r['name']:<{width}}  {r['via']:<5}  {token:<5}  {r['address']}{caps}")


@family.command("add")
@click.argument("name")
@click.argument("url")
def add(name: str, url: str):
    """Name a member in the table at URL (on this machine) and make it a token.

    The token is shown once, here: hand it to the member, which sends it as
    `Authorization: Bearer <token>` when it posts to /surfaces/contributed."""
    try:
        kept, token = roster.add(name, url)
    except roster.Refused as exc:
        raise _refused(exc) from None
    click.echo(f"{name} is a member of the family's hub, at {kept}")
    click.echo(f"its token, shown once: {token}")


@family.command("token")
@click.argument("name")
def token(name: str):
    """Make NAME a new token, replacing the one it has (shown once, here)."""
    try:
        made = roster.rekey(name)
    except roster.Refused as exc:
        raise _refused(exc) from None
    click.echo(f"{name}'s token, shown once: {made}")


@family.command("remove")
@click.argument("name")
def remove(name: str):
    """Take NAME out of the table, and revoke its token."""
    try:
        was = roster.remove(name)
    except roster.Refused as exc:
        raise _refused(exc) from None
    if not was:
        raise click.ClickException(
            f"{name} is named nowhere in the table: `apothecary family members`"
        )
    click.echo(f"{name} is no longer a member, and holds no token")
