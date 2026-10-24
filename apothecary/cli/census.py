"""Count what this asks of a person, from the command line.

Two meters, one command. How many controls the viewer puts on screen, and how
many things a person types when there is no control at all. They are the same
question asked of two surfaces, so they are answered in one place.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from ..census import NothingFound, Unclassified, report
from ..workflows import Undeclared
from ..workflows import report as typed_report


@click.command("census")
@click.option(
    "--page",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="A page to count instead of the viewer's own.",
)
@click.option(
    "--typed-only",
    is_flag=True,
    help="Only the count of what a person types, not the controls on screen.",
)
def census(page: Path | None, typed_only: bool) -> None:
    """Count what this asks of a person.

    Two numbers. How many controls of its own the viewer puts on screen, and how
    many things a person has to type to get a named job done. Both are baselines
    rather than budgets: a rise has to be explained rather than merely happening.

    If either has grown something nobody has decided about, this refuses to give
    a number and says which one.
    """
    try:
        if not typed_only:
            click.echo(report(page), nl=False)
            click.echo("")
        click.echo(typed_report(), nl=False)
    except (Unclassified, NothingFound, Undeclared) as refusal:
        click.echo(str(refusal), err=True)
        sys.exit(1)
