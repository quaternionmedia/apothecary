"""`apothecary problems` and `apothecary solutions`.

The two indexes on the command line. Same source as the API routes, so the
terminal and the viewer cannot disagree about what is open.
"""

from __future__ import annotations

from typing import Optional

import click

from . import status


def _volume(raw: Optional[str]):
    if not raw:
        return None
    try:
        parsed = tuple(float(v) for v in raw.split(","))
    except ValueError:
        raise click.ClickException("--build-volume wants three numbers: X,Y,Z") from None
    if len(parsed) != 3:
        raise click.ClickException("--build-volume wants three numbers: X,Y,Z")
    return parsed


# Owners, in the order a reader should work them: what needs deciding, then
# what needs measuring, then what this repository can simply fix.
OWNER_STATE = {
    "human": "blocked",
    "datum": "unknown",
    "measurement": "unknown",
    "apothecary": "info",
}


@click.command()
@click.option("--owner", default=None, help="apothecary | datum | human | measurement")
@click.option("--kind", default=None, help="contested | drift | unbounded | unprintable | ...")
@click.option("--build-volume", default=None, metavar="X,Y,Z")
@click.option("--detail/--no-detail", default=False, help="Show provenance and the fix.")
def problems(owner, kind, build_volume, detail):
    """Everything open here, and who can close it.

    Derived from the parts, the build checklist, the layout validators and the
    black-box seam. Nothing is entered by hand, so nothing goes stale.
    """
    from ..spaces import problems as open_problems

    found = open_problems(build_volume=_volume(build_volume))
    if owner:
        found = [p for p in found if p.owner == owner]
    if kind:
        found = [p for p in found if p.kind == kind]

    if not found:
        status.verdict(True, "nothing open matches that")
        return

    current = None
    for problem in found:
        if problem.owner != current:
            current = problem.owner
            click.echo("")
            status.heading(f"{current} can close these")
        status.line(OWNER_STATE.get(problem.owner, "info"), f"{problem.kind:11} {problem.summary}")
        if detail:
            if problem.detail:
                status.detail(problem.detail)
            status.fix(problem.closes_with)
            for source in problem.sources:
                status.detail(f"source: {source}")

    click.echo("")
    by_owner: dict = {}
    for problem in found:
        by_owner[problem.owner] = by_owner.get(problem.owner, 0) + 1
    status.verdict(
        False,
        f"{len(found)} open: " + ", ".join(f"{n} {o}" for o, n in sorted(by_owner.items())),
        warn=True,
    )


@click.command()
@click.option("--kind", default=None, help="part | assembly | provider | gate | tool")
def solutions(kind):
    """What this repository offers against those problems."""
    from ..spaces import capabilities
    from ..spaces import problems as open_problems

    found = capabilities()
    if kind:
        found = [c for c in found if c.kind == kind]

    current = None
    for capability in sorted(found, key=lambda c: (c.kind, c.name)):
        if capability.kind != current:
            current = capability.kind
            click.echo("")
            status.heading(current)
        status.line("pass" if capability.addresses else "info", capability.name)
        status.detail(capability.summary)
        if capability.addresses:
            status.detail("closes: " + ", ".join(capability.addresses))

    # A problem kind nothing addresses is the one worth naming.
    addressable = {k for c in capabilities() for k in c.addresses}
    open_kinds = {p.kind for p in open_problems()}
    unaddressed = sorted(open_kinds - addressable)
    click.echo("")
    if unaddressed:
        status.verdict(False, "nothing here closes: " + ", ".join(unaddressed))
    else:
        status.verdict(True, f"{len(found)} capabilities; every open kind has one")
