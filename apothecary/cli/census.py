"""Count the controls a page puts on screen, from the command line."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from ..census import NothingFound, report


@click.command("census")
@click.option(
    "--page",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="A page to count instead of the viewer's own.",
)
def census(page: Path | None) -> None:
    """Count the controls of its own the viewer puts on screen.

    A report, not a gate: anything in neither of the census's tables is
    counted as unclassified and listed with its line. Exits 1 only when the
    page yields nothing at all, since that means it could not be read.
    """
    try:
        click.echo(report(page), nl=False)
    except NothingFound as refusal:
        click.echo(str(refusal), err=True)
        sys.exit(1)
