"""``apothecary rig``: a rig of synths photographed, its controls read, held in carlos.

The rig is one of carlos's examples, asked of carlos on this machine
(``--carlos``, or ``APOTHECARY_CARLOS``) or read from a carlos checkout's
``catalogue`` folder (``--catalogue``); or a ``carlos.patch`` file (``--rig``),
whose devices are apothecary's own where it has them and carlos's otherwise.
Nothing here reaches past this machine, and it writes only where it is
pointed.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Optional

import click
from pydantic import ValidationError

from ..rig import concert as concert_
from ..rig import panels, reading, simulated
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


def _rig(url: Optional[str], catalogue: Optional[Path], example: str, rig_file: Optional[Path]):
    try:
        if rig_file is not None:
            more = None
            if catalogue is not None:
                more = partial(reading.device_in, catalogue)
            elif (found := _carlos_or_env(url)) is not None:
                more = partial(reading.device_from_carlos, found)
            return reading.rig_from_file(rig_file, more)
        if catalogue is not None:
            return reading.rig_in(catalogue, example)
        url = _carlos_or_env(url)
        if url is None:
            raise click.UsageError(
                "name carlos (--carlos URL), a carlos catalogue folder (--catalogue) or a rig (--rig)"
            )
        return reading.rig_from_carlos(url, example)
    except (carlos.CarlosError, ValueError, OSError, KeyError) as exc:
        raise click.ClickException(f"no rig {rig_file or example!r}: {exc}") from None


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
    click.option(
        "--rig",
        "rig_file",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        help="The rig as a carlos.patch file instead, e.g. examples/rigs/uno-power-and-usb.json.",
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
@click.option("--songs", default=6, show_default=True, type=click.IntRange(1, 50))
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
def simulate_cmd(url, catalogue, example, rig_file, out, songs, frames, every, seed):
    """Draw a concert: frames of the rig through a camera above it, with its setup and their truth.

    Each song moves a few controls; between songs a plug is pushed where no
    lead names one, and a lead's plug is pulled and pushed back; from the fifth
    song on, one of a lead's plugs is moved to another socket, as a rig is
    re-patched."""
    rig_doc, devices = _rig(url, catalogue, example, rig_file)
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


def _face(given: str, size: Optional[tuple]) -> tuple:
    """``MODULE=SIDE:x1,y1,x2,y2,x3,y3,x4,y4``: a module, its side, its four corners."""
    try:
        module, rest = given.split("=", 1)
        side, numbers = rest.split(":", 1)
        values = [float(n) for n in numbers.split(",")]
    except ValueError:
        values = []
    if len(values) != 8:
        raise click.BadParameter(
            f"{given!r}: a face is MODULE=SIDE:x1,y1,x2,y2,x3,y3,x4,y4", param_hint="--face"
        )
    corners = list(zip(values[0::2], values[1::2], strict=True))
    if size is not None:
        corners = [(x / size[0], y / size[1]) for x, y in corners]
    return module, side, corners


@rig.command("setup")
@rig_options
@click.option(
    "--face",
    "faces",
    multiple=True,
    required=True,
    help="MODULE=SIDE:x1,y1,...,x4,y4, a face's corners top left, top right, bottom right, "
    "bottom left; once for each face in the picture.",
)
@click.option(
    "--picture",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="The photograph the corners were read off; the corners are then its pixels, "
    "else fractions across and down.",
)
@click.option(
    "--out",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="The setup written.",
)
def setup_cmd(url, catalogue, example, rig_file, faces, picture, out):
    """Pin each face a photograph shows by its four corners, and write the setup it is read through."""
    rig_doc, devices = _rig(url, catalogue, example, rig_file)
    size = None
    if picture is not None:
        from PIL import Image, ImageOps

        with Image.open(picture) as opened:
            size = ImageOps.exif_transpose(opened).size
    pinned = {}
    for given in faces:
        module, side, corners = _face(given, size)
        pinned[module] = {"side": side, "corners": corners}
    try:
        setup = reading.Setup(rig=rig_doc, devices=devices, faces=pinned)
    except ValidationError as exc:
        raise click.ClickException(f"not a setup: {exc.errors()[0]['msg']}") from None
    types = {m["id"]: m["type"] for m in rig_doc.get("modules", [])}
    for module, face in setup.faces.items():
        panel = panels.panel(setup.entry(types[module]), face.side)
        things = (
            [c.label for c in panel.controls] + [s.label for s in panel.sockets] if panel else []
        )
        if not things:
            raise click.ClickException(f"{module}'s {face.side} has nothing on it to read")
        click.echo(f"{module}, its {face.side}: {', '.join(things)}")
    out.write_text(setup.model_dump_json(indent=2), encoding="utf-8")
    click.echo(f"the setup is {out}")


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
def check_cmd(url, catalogue, example, rig_file, count, seed):
    """How well the reader does on drawn pictures of the rig, whose every answer is known."""
    rig_doc, devices = _rig(url, catalogue, example, rig_file)
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
