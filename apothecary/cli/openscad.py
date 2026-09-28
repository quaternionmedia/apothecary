"""`apothecary openscad`: install an OpenSCAD development snapshot, and say which is in use."""

from __future__ import annotations

from importlib import import_module
from typing import Optional, Tuple

import click

from .. import openscad_installer as oi
from .utils import _safe_echo


def parts_floor() -> Tuple[Optional[str], Optional[str]]:
    """The highest ``openscad_min_version`` any registered part declares, and
    that part's name: ``(None, None)`` when none declares one."""
    from ..projects.parts.skeleton import ROOT
    from ..projects.parts.stl_renderer import parse_openscad_version
    from ..projects.registry import scan_projects

    best: Tuple[Optional[str], Optional[str]] = (None, None)
    for item in scan_projects(ROOT):
        if item.kind != "part" or not item.wrapper:
            continue
        try:
            part = import_module(item.wrapper).DEFAULT
        except Exception:  # a broken wrapper is `apothecary check`'s to report
            continue
        wanted = getattr(part, "openscad_min_version", None)
        if wanted and (
            best[0] is None or parse_openscad_version(wanted) > parse_openscad_version(best[0])
        ):
            best = (wanted, item.name)
    return best


@click.group()
def openscad():
    """Install an OpenSCAD development snapshot (it has Manifold), and say which is in use."""


@openscad.command("install")
@click.option("--latest", is_flag=True, help="The newest snapshot (the default)")
@click.option("--snapshot", "snapshot", metavar="YYYY.MM.DD", help="The snapshot of that date")
@click.option(
    "--min",
    "minimum",
    metavar="VERSION",
    help="Refuse a snapshot older than this; defaults to the highest any part declares",
)
@click.option("--force", is_flag=True, help="Download it again even if it is installed")
def openscad_install(latest: bool, snapshot: Optional[str], minimum: Optional[str], force: bool):
    """Download an OpenSCAD snapshot from files.openscad.org and nowhere else.

    It reads the host's listing for this platform's file, downloads it, checks
    its size and published SHA-256 and that it runs and reports its date, puts
    it under the tools dir (~/.apothecary/tools/openscad/<date>/, or
    $APOTHECARY_TOOLS_DIR) and makes it current: every render then uses it,
    with Manifold. Linux x86_64 only.
    """
    if latest and snapshot:
        raise click.UsageError("--latest or --snapshot DATE: one or the other")
    why = ""
    if minimum is None:
        minimum, part = parts_floor()
        why = f" ({part} needs it)" if part else ""
    if minimum:
        click.echo(f"Oldest OpenSCAD asked for: {minimum}{why}")
    try:
        oi.SnapshotInstaller(
            snapshot=snapshot, minimum=minimum, force=force, log=click.echo
        ).install()
    except (oi.InstallError, OSError) as exc:
        raise click.ClickException(f"{exc}{why}") from exc
    from ..projects.parts import stl_renderer

    stl_renderer._renderer = None  # the default renderer is found again
    click.echo("")
    _status()


def _status() -> None:
    from ..projects.parts.stl_renderer import get_renderer, has_manifold, openscad_override

    home = oi.openscad_dir()
    current = oi.current_version()
    versions = oi.installed_versions()
    click.secho("Installed snapshots:", bold=True)
    click.echo(f"  {home}")
    if not versions:
        click.echo("  none (apothecary openscad install)")
    for date in versions:
        exe = oi.executable_for(date)
        mark = " (current)" if date == current else ""
        _safe_echo(f"  • {date}{mark}: {exe}")
    override = openscad_override()
    if override is not None:
        click.echo(f"APOTHECARY_OPENSCAD names {override}; it is used instead of any of these.")
    renderer = get_renderer()
    exe = renderer.openscad_path
    click.secho("Renders use:", bold=True)
    if exe is None or not renderer.is_available:
        _safe_echo("  ✗ no OpenSCAD", fg="yellow")
        return
    version = renderer.get_version() or "unknown version"
    manifold = "Manifold" if has_manifold(exe) else "no Manifold (CGAL)"
    _safe_echo(f"  ✓ {exe}: {version}, {manifold}")


@openscad.command("status")
def openscad_status():
    """What is installed, which is current, and whether it has Manifold."""
    _status()
