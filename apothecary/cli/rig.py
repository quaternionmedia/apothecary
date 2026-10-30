"""``apothecary rig``: a rig of synths photographed, its controls read, held in carlos.

The rig and its devices are carlos's: an example asked of carlos on this
machine (``--carlos``, or ``APOTHECARY_CARLOS``), or read from a carlos
checkout's ``catalogue`` folder (``--catalogue``). Nothing here reaches past
this machine, and it writes only where it is pointed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click
from pydantic import ValidationError

from ..rig import concert as concert_
from ..rig import reading, simulated
from ..wiring import carlos

DEFAULT_EXAMPLE = "moog.subharmonicon.complex"


@click.group()
def rig():
    """A rig of synths photographed: each control read off the picture, and held in carlos."""


def _carlos_or_env(url: Optional[str]) -> Optional[str]:
    url = url or carlos.carlos_url()
    if not url:
        return None
    try:
        return carlos.loopback_url(url)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="--carlos") from None


def _rig(url: Optional[str], catalogue: Optional[Path], example: str):
    try:
        if catalogue is not None:
            return reading.rig_in(catalogue, example)
        url = _carlos_or_env(url)
        if url is None:
            raise click.UsageError(
                "name carlos (--carlos URL) or a carlos catalogue folder (--catalogue)"
            )
        return reading.rig_from_carlos(url, example)
    except (carlos.CarlosError, ValueError, OSError, KeyError) as exc:
        raise click.ClickException(f"no rig {example!r}: {exc}") from None


def _setup(path: Path) -> reading.Setup:
    try:
        return reading.Setup.load(path)
    except (OSError, ValueError, ValidationError) as exc:
        raise click.ClickException(f"{path} is not a setup: {exc}") from None


_rig_options = [
    click.option(
        "--carlos", "url", help="Carlos on this machine, asked for the rig (or APOTHECARY_CARLOS)."
    ),
    click.option(
        "--catalogue",
        type=click.Path(exists=True, file_okay=False, path_type=Path),
        help="A carlos checkout's catalogue folder, read instead of asking carlos.",
    ),
    click.option(
        "--example",
        default=DEFAULT_EXAMPLE,
        show_default=True,
        help="The rig: one of carlos's examples, <device>.simple or <device>.complex.",
    ),
]


def rig_options(command):
    for option in reversed(_rig_options):
        command = option(command)
    return command


@rig.command("simulate")
@rig_options
@click.option(
    "--out",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="The folder the concert is drawn into.",
)
@click.option("--songs", default=4, show_default=True, type=click.IntRange(1, 50))
@click.option(
    "--frames", default=6, show_default=True, type=click.IntRange(1, 200), help="Frames per song."
)
@click.option(
    "--every",
    default=5.0,
    show_default=True,
    type=click.FloatRange(0.1),
    help="Seconds between frames.",
)
@click.option("--seed", default=1, show_default=True, type=int)
def simulate_cmd(url, catalogue, example, out, songs, frames, every, seed):
    """Draw a concert: frames of the rig through a camera above it, with its setup and their truth.

    Each song moves a few controls; between songs a plug is pushed where no
    lead names one, and a lead's plug is pulled and pushed back."""
    rig_doc, devices = _rig(url, catalogue, example)
    setup = simulated.scene(rig_doc, devices)
    if not setup.faces:
        raise click.ClickException(
            f"{example}: no device in it shows a face with controls to the camera"
        )
    count = simulated.write_concert(setup, out, songs=songs, frames=frames, every=every, seed=seed)
    click.echo(
        f"{count} frames of {rig_doc.get('name', example)!r} in {out}, with setup.json and truth.jsonl"
    )
    click.echo(f"faces in the picture: {', '.join(setup.faces)}")


@rig.command("read")
@click.argument("picture", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--setup",
    "setup_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="The setup saying what the picture shows.",
)
@click.option(
    "--format", "fmt", type=click.Choice(["summary", "json"]), default="summary", show_default=True
)
def read_cmd(picture, setup_path, fmt):
    """Read every control and socket the setup pins, off one picture."""
    setup = _setup(setup_path)
    try:
        found = concert_.read_frame(setup, picture)
    except OSError as exc:
        raise click.ClickException(f"{picture} could not be read as a picture ({exc})") from None
    if fmt == "json":
        click.echo(found.model_dump_json(indent=2))
        return
    for module in found.modules:
        if module.why:
            click.echo(f"{module.module} ({module.device}): {module.why}")
            continue
        click.echo(f"{module.module} ({module.device}), its {module.side}:")
        for seen in module.seen:
            said = (
                f"{round(seen.value, 1):g}" if seen.value is not None else f"not read: {seen.why}"
            )
            click.echo(f"  {seen.name:<16} {seen.kind:<8} {said}")
        plugged = [plug.name for plug in module.plugs if plug.plugged]
        click.echo(f"  plugs in: {', '.join(plugged) or 'none'}")


@rig.command("follow")
@click.argument("folder", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--setup",
    "setup_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="The setup saying what the frames show (default: setup.json in the folder).",
)
@click.option(
    "--carlos", "url", help="Carlos on this machine, to hold each frame (or APOTHECARY_CARLOS)."
)
@click.option(
    "--pace",
    default=0.0,
    show_default=True,
    type=click.FloatRange(0),
    help="Seconds each frame is held.",
)
@click.option(
    "--watch", is_flag=True, help="Keep following new frames as they come, until stopped."
)
@click.option(
    "--every",
    default=2.0,
    show_default=True,
    type=click.FloatRange(0.1),
    help="Seconds between looks, watching.",
)
def follow_cmd(folder, setup_path, url, pace, watch, every):
    """Read a concert's frames in order, hold each in carlos, and keep the record beside them."""
    if setup_path is None and not (folder / concert_.SETUP).exists():
        raise click.UsageError(f"{folder} has no {concert_.SETUP}; name one with --setup")
    _setup(setup_path or folder / concert_.SETUP)
    following = concert_.Concert(folder, setup_path, _carlos_or_env(url), say=click.echo)
    try:
        count = following.follow(pace=pace, watch=watch, every=every)
    except KeyboardInterrupt:
        count = len(following.seen)
    click.echo(f"{count} frames read; the record is {folder / concert_.RECORD}")


@rig.command("check")
@rig_options
@click.option(
    "--count", default=8, show_default=True, type=click.IntRange(1), help="Pictures drawn and read."
)
@click.option("--seed", default=1, show_default=True, type=int)
def check_cmd(url, catalogue, example, count, seed):
    """How well the reader does on drawn pictures of the rig, whose every answer is known."""
    rig_doc, devices = _rig(url, catalogue, example)
    setup = simulated.scene(rig_doc, devices)
    if not setup.faces:
        raise click.ClickException(
            f"{example}: no device in it shows a face with controls to the camera"
        )
    click.echo(f"the reader on {count} drawn pictures of {rig_doc.get('name', example)!r}:")
    for row in simulated.measure(setup, count=count, seed=seed):
        if row.kind == "socket":
            off = f"{row.mean:.1%} called wrong"
        elif row.read:
            off = f"off by {row.mean:.1%} of the range on average, {row.worst:.1%} at worst"
        else:
            off = "none can be read"
        click.echo(f"  {row.kind:<8} {row.read} of {row.looked} read; {off}")
    click.echo(
        "drawn pictures prove the plumbing, not the eyes: the same rules draw them and read them"
    )
