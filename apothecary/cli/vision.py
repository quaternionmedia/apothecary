"""``apothecary vision``: image models asked through qmcp, and the origins switched.

qmcp is ``--qmcp`` or ``APOTHECARY_QMCP``: an address on this machine, or
``simulated`` (``simulated:slow``, ``:empty``, ``:broken``, ``:down``) for the
in-process qmcp. With neither, nothing is asked. A guess is shown as one, with
its origin and confidence, and is never trusted until a check has passed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, Tuple

import click

from ..finders import qmcp, switches


@click.group()
def vision():
    """Image models through qmcp, only when asked: what qmcp has, a region asked about, origins switched."""


def _use(address: Optional[str]) -> None:
    if address is not None:
        os.environ[qmcp.ENV] = address


@vision.command("status")
@click.option(
    "--qmcp",
    "address",
    default=None,
    help="qmcp's address, or simulated[:mode] (default: $APOTHECARY_QMCP)",
)
def status_cmd(address):
    """Whether qmcp is there, its models, and every origin switched off."""
    _use(address)
    status = qmcp.status()
    click.echo(status["says"])
    for model in status["models"]:
        click.echo(
            f"  {model['name']} {model['version']}  answers {', '.join(sorted(model.get('answers') or {}))}  not checked"
        )
    off = [o for o, on in switches.read().items() if not on]
    click.echo(f"switched off: {', '.join(off)}" if off else "nothing switched off")


def _box(text: str) -> Tuple[float, float, float, float]:
    try:
        left, top, right, bottom = (float(p) for p in text.split(","))
    except ValueError:
        raise click.BadParameter(
            "four fractions, left,top,right,bottom", param_hint="--box"
        ) from None
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        raise click.BadParameter(
            "each from 0 to 1, left before right and top before bottom", param_hint="--box"
        )
    return left, top, right, bottom


@vision.command("ask")
@click.argument("picture", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--box",
    default="0,0,1,1",
    show_default=True,
    help="The region, in fractions of the picture: left,top,right,bottom",
)
@click.option(
    "--property",
    "properties",
    multiple=True,
    type=click.Choice(["colour", "material", "label"]),
    help="What to ask (repeatable; default: all three)",
)
@click.option("--label", "labels", multiple=True, help="A word a label is asked among (repeatable)")
@click.option(
    "--qmcp",
    "address",
    default=None,
    help="qmcp's address, or simulated[:mode] (default: $APOTHECARY_QMCP)",
)
@click.option("--json", "as_json", is_flag=True, help="The observations as JSON, one a line")
def ask_cmd(picture, box, properties, labels, address, as_json):
    """Ask about one region of a picture: the plain reader's colour, and qmcp's guesses."""
    from datetime import datetime, timezone

    from ..vision.colour import READER, digest, read_colour

    _use(address)
    region = _box(box)
    asked = list(properties) or ["colour", "material", "label"]
    taken = datetime.fromtimestamp(picture.stat().st_mtime, timezone.utc).isoformat(
        timespec="seconds"
    )
    seen = []
    if "colour" in asked and switches.is_on(READER):
        seen.extend(read_colour(picture, region, "region", taken))
    req = qmcp.request(
        picture.resolve(), digest(picture), taken, [("region", region)], asked, labels=labels
    )
    os.environ.setdefault("APOTHECARY_PICTURE_ROOT", str(picture.resolve().parent))
    guessed, said = qmcp.ask(req)
    seen.extend(o for o in guessed if switches.is_on(o.origin.key()))
    if as_json:
        for o in seen:
            click.echo(json.dumps(o.model_dump(mode="json")))
        return
    click.echo(said)
    for o in seen:
        kind = o.origin.kind
        if o.unread:
            click.echo(f"  {o.property:<9} unread: {o.why}  ({o.origin.key()}, {kind})")
            continue
        sure = f", {o.confidence:.2f} sure" if o.confidence is not None else ""
        trust = ", not checked" if kind == "guessed" and not o.block.trusted else ""
        click.echo(f"  {o.property:<9} {o.value}  ({o.origin.key()}, {kind}{sure}{trust})")


@vision.command("off")
@click.argument("origin")
def off_cmd(origin):
    """Switch an origin off (plain/colour, or qmcp/<model>@<version>): it is not asked, and what it said leaves every view."""
    _switch(origin, False)
    click.echo(f"{origin} is switched off")


@vision.command("on")
@click.argument("origin")
def on_cmd(origin):
    """Switch an origin back on."""
    _switch(origin, True)
    click.echo(f"{origin} is switched on")


def _switch(origin: str, on: bool) -> None:
    try:
        switches.switch(origin, on)
    except ValueError as refused:
        raise click.UsageError(str(refused)) from None
