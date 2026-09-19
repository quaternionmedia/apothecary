"""Firmware CLI: install/validate the toolchain and program boards from sketches under parts/."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional, Tuple

import click

from ..firmware import devices, service
from ..firmware.installer import InstallSpec, env_for_arduino
from ..firmware.models import validate_core_id, validate_fqbn, validate_port
from ..firmware.sketches import discover_sketches, find_sketch
from ..firmware.tasks import stream
from ..firmware.toolchains import SUGGESTED_CORES, ToolchainError, get_arduino_cli, get_esptool


def _die(exc: Exception) -> None:
    raise click.ClickException(str(exc))


def _require_sketch(name: str):
    sketch = find_sketch(name)
    if sketch is None:
        raise click.ClickException(
            f"unknown sketch '{name}'. Sketches are parts/<name>/<name>.ino -- "
            "see `apothecary firmware sketches`."
        )
    return sketch


@click.group()
def firmware():
    """Install the firmware toolchain and program Arduinos, ESP32s and similar."""


@firmware.command("install")
@click.option(
    "--version",
    "version",
    default="latest",
    show_default=True,
    help="arduino-cli release to install",
)
@click.option("--force", is_flag=True, help="Reinstall even if already present")
@click.option(
    "--core", "cores", multiple=True, help="Core to install, e.g. arduino:avr (repeatable)"
)
@click.option("--esp32", is_flag=True, help="Shortcut for --core esp32:esp32")
@click.option("--avr", is_flag=True, help="Shortcut for --core arduino:avr")
@click.option(
    "--library", "libraries", multiple=True, help="Library to install by name (repeatable)"
)
def firmware_install(
    version: str,
    force: bool,
    cores: Tuple[str, ...],
    esp32: bool,
    avr: bool,
    libraries: Tuple[str, ...],
):
    """Download arduino-cli (checksum-verified), then install cores and libraries."""
    wanted = list(cores) + (["esp32:esp32"] if esp32 else []) + (["arduino:avr"] if avr else [])
    try:
        for c in wanted:
            validate_core_id(c)
        spec = InstallSpec(
            version=version,
            force=force,
            cores=list(dict.fromkeys(wanted)),
            libraries=list(libraries),
        )
        status = service.install(spec, click.echo)
    except (ToolchainError, ValueError) as exc:
        _die(exc)
    click.echo("")
    _print_status(status)


@firmware.command("validate")
@click.option("--json-out/--text", default=False)
def firmware_validate(json_out: bool):
    """Check that arduino-cli (and optionally esptool) are installed and usable. Exit 1 if not."""
    status = service.toolchain_status()
    if json_out:
        click.echo(json.dumps(status.model_dump(), indent=2))
    else:
        _print_status(status)
    if not status.arduino_cli_ok:
        sys.exit(1)


def _print_status(status) -> None:
    click.secho("Firmware toolchain", bold=True)
    click.echo(f"  tools dir: {status.tools_dir}")
    if status.arduino_cli_ok:
        click.echo(f"  ✓ arduino-cli {status.arduino_cli_version}: {status.arduino_cli_path}")
        if status.config_file:
            click.echo(f"    config: {status.config_file}")
        installed = [c for c in status.cores if c.installed]
        if installed:
            click.echo("    cores: " + ", ".join(f"{c.id}@{c.installed}" for c in installed))
    else:
        click.secho("  ✗ arduino-cli: not installed", fg="red")
    if status.esptool_ok:
        click.echo(f"  ✓ esptool {status.esptool_version}: {status.esptool_path}")
    else:
        click.secho("  • esptool: not found (optional)", fg="yellow")
    for problem in status.problems:
        click.secho(f"  ! {problem}", fg="yellow")


@firmware.command("boards")
@click.option(
    "--all",
    "list_all",
    is_flag=True,
    help="List every board the installed cores can target, not just connected ones",
)
@click.option("--json-out/--text", default=False)
def firmware_boards(list_all: bool, json_out: bool):
    """List connected boards (or, with --all, every known FQBN)."""
    try:
        cli = get_arduino_cli()
        if list_all:
            rows = [b.model_dump() for b in cli.board_listall()]
        else:
            rows = [b.model_dump() for b in cli.board_list()]
    except ToolchainError as exc:
        _die(exc)
    if json_out:
        click.echo(json.dumps(rows, indent=2))
        return
    if not rows:
        click.echo(
            "No boards detected." if not list_all else "No cores installed -- no boards known."
        )
        return
    for r in rows:
        if list_all:
            click.echo(f"{r['fqbn']:40s} {r['name']}")
        else:
            board = r.get("board_name") or "(unknown board)"
            click.echo(f"{r['port']:18s} {board:30s} {r.get('fqbn') or ''}")


@firmware.command("cores")
@click.option("--install", "install_id", default=None, help="Install a core, e.g. esp32:esp32")
@click.option("--json-out/--text", default=False)
def firmware_cores(install_id: Optional[str], json_out: bool):
    """List installed cores, or install one (third-party index URLs are added automatically)."""
    try:
        if install_id:
            validate_core_id(install_id)
            service.install_core(install_id, click.echo)
        cores = get_arduino_cli().core_list()
    except (ToolchainError, ValueError) as exc:
        _die(exc)
    if json_out:
        click.echo(json.dumps([c.model_dump() for c in cores], indent=2))
        return
    if not cores:
        click.echo("No cores installed. Suggested:")
        for cid, label in SUGGESTED_CORES:
            click.echo(f"  apothecary firmware cores --install {cid:18s} # {label}")
        return
    for c in cores:
        click.echo(f"{c.id:24s} {c.installed or '-':10s} {c.name}")


@firmware.command("libraries")
@click.option("--install", "names", multiple=True, help="Library name to install (repeatable)")
def firmware_libraries(names: Tuple[str, ...]):
    """Install Arduino libraries by name (e.g. --install FastLED --install "Control Surface")."""
    if not names:
        raise click.UsageError("pass at least one --install NAME")
    try:
        service.install_libraries(list(names), click.echo)
    except ToolchainError as exc:
        _die(exc)


@firmware.command("sketches")
@click.option("--json-out/--text", default=False)
def firmware_sketches(json_out: bool):
    """List sketches found under parts/ (a folder holding <folder>.ino)."""
    sketches = discover_sketches()
    if json_out:
        click.echo(json.dumps([s.to_json() for s in sketches], indent=2))
        return
    if not sketches:
        click.echo("No sketches found under parts/.")
        return
    for s in sketches:
        extra = f" fqbn={s.fqbn}" if s.fqbn else ""
        libs = f" libraries={','.join(s.libraries)}" if s.libraries else ""
        ino = s.ino.relative_to(Path.cwd()) if s.ino.is_relative_to(Path.cwd()) else s.ino
        click.echo(f"{s.name:20s} {ino}{extra}{libs}")


@firmware.command("compile")
@click.argument("sketch")
@click.option("--fqbn", default=None, help="Board FQBN (defaults to the sketch's firmware.json)")
def firmware_compile(sketch: str, fqbn: Optional[str]):
    """Compile a sketch for a board."""
    s = _require_sketch(sketch)
    try:
        chosen = validate_fqbn(service.resolve_fqbn(s, fqbn))
        for argv in service.compile_steps(s, chosen):
            rc = stream(argv, click.echo, env_for_arduino())
            if rc != 0:
                sys.exit(rc)
    except (ToolchainError, ValueError) as exc:
        _die(exc)
    click.secho(f"Compiled {s.name} for {chosen} -> {service.build_dir(s)}", fg="green")


@firmware.command("upload")
@click.argument("sketch")
@click.option("--fqbn", default=None, help="Board FQBN (defaults to the sketch's firmware.json)")
@click.option(
    "--port",
    "-p",
    default=None,
    help="Serial port (auto-detected when exactly one board is connected)",
)
def firmware_upload(sketch: str, fqbn: Optional[str], port: Optional[str]):
    """Compile and upload a sketch to a connected board."""
    s = _require_sketch(sketch)
    try:
        chosen = validate_fqbn(service.resolve_fqbn(s, fqbn))
        chosen_port = validate_port(service.resolve_port(port))
        for argv in service.upload_steps(s, chosen, chosen_port):
            rc = stream(argv, click.echo, env_for_arduino())
            if rc != 0:
                sys.exit(rc)
    except (ToolchainError, ValueError) as exc:
        _die(exc)
    service.record_upload(chosen_port, s, chosen)
    click.secho(f"Uploaded {s.name} ({chosen}) to {chosen_port}", fg="green")


@firmware.command("flash-bin")
@click.argument("port")
@click.argument("images", nargs=-1, required=True)
@click.option(
    "--chip", default="auto", show_default=True, help="esptool chip, e.g. esp32, esp32s3, esp8266"
)
@click.option("--baud", default=460800, show_default=True, type=int)
@click.option("--erase", is_flag=True, help="Erase flash first")
def firmware_flash_bin(port: str, images: Tuple[str, ...], chip: str, baud: int, erase: bool):
    """Flash raw binaries to an Espressif chip with esptool.

    IMAGES are OFFSET:FILE pairs, e.g. 0x1000:bootloader.bin 0x10000:firmware.bin
    """
    esptool = get_esptool()
    pairs = []
    try:
        validate_port(port)
        for item in images:
            if ":" not in item:
                raise click.UsageError(f"image must be OFFSET:FILE, got {item!r}")
            offset, file = item.split(":", 1)
            p = Path(file).expanduser()
            if not p.is_file():
                raise click.UsageError(f"image not found: {file}")
            pairs.append((offset, p))
        steps = []
        if erase:
            steps.append(esptool.erase_argv(port, chip))
        steps.append(esptool.write_flash_argv(port, pairs, chip, baud))
        for argv in steps:
            rc = stream(argv, click.echo)
            if rc != 0:
                sys.exit(rc)
    except (ToolchainError, ValueError) as exc:
        _die(exc)
    service.record_raw_flash(port, [f"{off}:{p}" for off, p in pairs])
    click.secho(f"Flashed {len(pairs)} image(s) to {port}", fg="green")


def _print_device(d, expected=None) -> None:
    ident = d.board_name or "(unmatched)"
    click.secho(f"{d.port}", bold=True, nl=False)
    click.echo(
        f"  {d.label if d.label != d.port else ''} vid={d.vid or '?'} pid={d.pid or '?'}  {ident}"
    )
    if d.chip:
        feats = ", ".join(d.features[:3])
        click.echo(f"    chip: {d.chip} rev {d.revision or '?'}  mac {d.mac}")
        click.echo(f"    flash: {d.flash_size or '?'}  {feats}")
    if expected is not None:
        rec = expected.record
        if rec is None:
            click.secho("    expected: nothing flashed from apothecary yet", fg="yellow")
        else:
            what = rec.sketch or ("raw images " + ", ".join(rec.images))
            when = f"{rec.flashed_at:%Y-%m-%d %H:%M}"
            click.echo(f"    expected: {what} ({rec.fqbn or 'esptool'}) flashed {when}")
            if expected.source_changed:
                click.secho("      ! sketch source edited since that upload", fg="yellow")
            if expected.build_changed:
                click.secho("      ! a newer build exists that was never uploaded", fg="yellow")
            if expected.sketch_missing:
                click.secho("      ! that sketch no longer exists under parts/", fg="red")


@firmware.command("devices")
@click.option("--json-out/--text", default=False)
def firmware_devices(json_out: bool):
    """Connected devices with cached chip identity and the firmware each should be running."""
    try:
        found = devices.detected_devices()
    except ToolchainError as exc:
        _die(exc)
    rows = [(d, devices.expected_firmware(d, service.BUILD_ROOT)) for d in found]
    if json_out:
        click.echo(
            json.dumps(
                [
                    {"device": d.model_dump(mode="json"), "expected": e.model_dump(mode="json")}
                    for d, e in rows
                ],
                indent=2,
            )
        )
        return
    if not rows:
        click.echo("No devices detected.")
        return
    for d, e in rows:
        _print_device(d, e)


@firmware.command("probe")
@click.argument("port")
def firmware_probe(port: str):
    """Identify the chip on PORT with esptool (resets the board afterwards)."""
    try:
        validate_port(port)
        d = devices.probe_device(port)
    except (ToolchainError, ValueError) as exc:
        _die(exc)
    _print_device(d)


@firmware.command("listen")
@click.argument("port")
@click.option("--seconds", default=3.0, show_default=True, type=float)
@click.option("--baud", default=115200, show_default=True, type=int)
@click.option(
    "--reset", is_flag=True, help="Probe first (resets the board) so the boot banner is captured"
)
def firmware_listen(port: str, seconds: float, baud: int, reset: bool):
    """Print a few seconds of serial output and say which sketch announced itself."""
    try:
        validate_port(port)
        if reset:
            devices.probe_device(port)
        result = devices.listen(port, seconds, baud)
    except (ToolchainError, ValueError) as exc:
        _die(exc)
    for line in result.lines:
        click.echo(line)
    if result.running_sketch:
        click.secho(f"running: {result.running_sketch}", fg="green")
    else:
        click.secho("no `apothecary <sketch>: hello` banner seen (try --reset)", fg="yellow")
