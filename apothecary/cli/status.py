"""One vocabulary for how this CLI reports state.

Colour and glyphs were being chosen per command, so the same outcome looked
different depending on which one you ran. These are the marks every command
uses, and the progress bar every long loop uses.

Built on Click, which is in the blessed set and already a dependency. `rich`
would be an out-of-state addition needing an org-level record, and buys little
here: Click has a progress bar and styling, and this CLI has to survive a
cp1252 console, where the fancier glyph sets are exactly what breaks.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterable, Optional

import click

from .utils import _safe_echo

# state -> (mark, colour). The marks are ASCII on purpose: Windows still
# defaults to cp1252 and this CLI has already died once on a check mark.
MARKS = {
    "pass": ("OK  ", "green"),
    "ok": ("OK  ", "green"),
    "blocked": ("STOP", "red"),
    "fail": ("FAIL", "red"),
    "unknown": ("????", "yellow"),
    "skip": ("SKIP", "yellow"),
    "info": ("    ", None),
}


def mark(state: str) -> str:
    """The bracketed mark for a state, coloured."""
    text, colour = MARKS.get(state, MARKS["info"])
    return click.style(f"[{text}]", fg=colour, bold=colour is not None)


def line(state: str, message: str, indent: int = 2) -> None:
    """One status line: a coloured mark, then the message."""
    _safe_echo(f"{' ' * indent}{mark(state)} {message}")


def detail(message: str, indent: int = 11) -> None:
    """A dimmed continuation under a status line."""
    _safe_echo(f"{' ' * indent}{click.style(message, dim=True)}")


def fix(message: str, indent: int = 11) -> None:
    """What to do about a state that is not a pass."""
    _safe_echo(f"{' ' * indent}{click.style('-> ' + message, fg='cyan')}")


def verdict(ok: bool, message: str, warn: bool = False) -> None:
    """The single line a reader looks at first."""
    colour = "green" if ok else ("yellow" if warn else "red")
    _safe_echo("  " + click.style(message, fg=colour, bold=True))


def heading(text: str) -> None:
    _safe_echo(click.style(text, bold=True))


@contextmanager
def progress(items: Iterable, label: str, show: Optional[bool] = None):
    """A progress bar over a slow loop.

    Suppressed when the output is not a terminal -- a bar redrawing itself
    into a CI log is noise, and the per-item lines are the record there.
    """
    items = list(items)
    if show is None:
        show = click.get_text_stream("stdout").isatty() and len(items) > 1

    if not show:
        yield items
        return

    with click.progressbar(
        items,
        label=click.style(label, bold=True),
        item_show_func=lambda i: (str(i) if i else ""),
        show_eta=True,
    ) as bar:
        yield bar


def iterate(items: Iterable, label: str):
    """Iterate with a progress bar, or plainly when there is no terminal.

    The context-manager form suits a block; this suits a `for` that has to
    keep printing per-item lines as it goes.
    """
    items = list(items)
    if not click.get_text_stream("stdout").isatty() or len(items) < 2:
        yield from items
        return
    with click.progressbar(items, label=click.style(label, bold=True), show_eta=True) as bar:
        yield from bar

