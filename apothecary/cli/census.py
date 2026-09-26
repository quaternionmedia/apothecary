"""Count the controls a page puts on screen, from the command line."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from ..census import NothingFound, Unclassified, report


@click.command("census")
@click.option(
    "--page",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="A page to count instead of the viewer's own.",
)
def census(page: Path | None) -> None:
    """Count the controls of its own the viewer puts on screen.

    If the page has grown something nobody has decided about, this refuses to
    give a number and says which one.
    """
    try:
        click.echo(report(page), nl=False)
    except (Unclassified, NothingFound) as refusal:
        click.echo(str(refusal), err=True)
        sys.exit(1)
