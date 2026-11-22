"""``apothecary cabinet``: each part's drawers, a piece made of it each, and what was filed
about them (``apothecary/cabinet.py``).

``cabinet`` lists the parts with a drawer, ``cabinet PART`` its drawers, the newest first,
and ``cabinet PART DRAWER`` one drawer: what made the piece, and each filing in order.
It reads the state folder: no browser, no server.
"""

from __future__ import annotations

from typing import Optional

import click

from .. import cabinet as cab


@click.command("cabinet")
@click.argument("part", required=False)
@click.argument("drawer", required=False)
def cabinet(part: Optional[str], drawer: Optional[str]):
    """What was made of a part, and what was said of each piece: the parts, a part's
    drawers, or one drawer."""
    try:
        if part is None:
            for name in cab.parts():
                n = len(cab.drawers(name))
                click.echo(f"{name}: {n} drawer{'' if n == 1 else 's'}")
            return
        if drawer is None:
            for d in cab.drawers(part):
                click.echo(f"{d.id}  {d.said()}")
            return
        found = cab.get(part, drawer)
    except cab.Refused as exc:
        raise click.ClickException(str(exc)) from exc
    if found is None:
        raise click.ClickException(f"{part} has no drawer {drawer}")
    click.echo(f"{part} {found.id}: {found.said()}")
    click.echo(f"file: {found.file.name} ({found.file.file_id})")
    if found.variant:
        click.echo(f"variant: {found.variant}")
    for key, value in sorted(found.params.items()):
        click.echo(f"  {key} = {value}")
    if found.stl_sha256:
        click.echo(f"stl: sha256 {found.stl_sha256}")
    if found.job is not None:
        ended = f", {found.job.reason}" if found.job.reason else ""
        click.echo(f"job: {found.job.id}, {found.job.outcome}{ended}")
    for f in found.filed:
        undone = " (undone)" if f.undone else ""
        click.echo(f"{f.at:%Y-%m-%d %H:%M} {f.id} {f.kind}{undone}: {f.said}")
        # A check alone says its checks in its line; a turn's or an allowance's under it.
        for check in f.checked if f.made else ():
            click.echo(f"  {check.said()}")
