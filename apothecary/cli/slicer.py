"""`apothecary slicer`: install the slicer, say where it stands, and slice a part for a printer."""

from __future__ import annotations

from typing import Optional

import click

from .utils import _safe_echo


def _status_lines(chosen: Optional[str] = None) -> None:
    from ..slicer import orcaslicer_installer as oi
    from ..slicer.modules import chosen_id, modules

    picked = chosen_id(chosen)
    _safe_echo(f"This machine: {oi.what_install_does()}")
    for module in modules():
        status = module.status()
        mark = " (used)" if module.id == picked else ""
        click.secho(f"{module.label}{mark}:", bold=True)
        click.echo(
            f"  slices {', '.join(status.inputs)} into {', '.join(status.writes)} "
            f"for {status.technology} printers; pinned {status.pinned}"
        )
        if status.tool.path:
            version = status.tool.version or "does not say its version"
            _safe_echo(
                f"  {'✓' if status.tool.ok else '✗'} {status.tool.path} ({status.tool.found_by}): {version}"
            )
        if status.profiles:
            click.echo(f"  its printer profiles: {status.profiles}")
        for note in status.notes:
            _safe_echo(f"  • {note}", fg="yellow")
        for problem in status.problems:
            _safe_echo(f"  ✗ {problem}", fg="yellow")
    versions = oi.installed_versions()
    if versions:
        click.secho("Installed releases:", bold=True)
        current = oi.current_version()
        for version in versions:
            found = oi.describe(version)
            mark = " (current)" if version == current else ""
            _safe_echo(f"  • OrcaSlicer {version}{mark}: {found.executable}")
            _safe_echo(f"      {found.platform} · {found.how} · {found.runs}")


@click.group()
def slicer():
    """Install the slicer and slice a part or a made piece for a printer."""


@slicer.command("install")
@click.option("--force", is_flag=True, help="Download it again even if it is installed")
def slicer_install(force: bool):
    """Install the pinned OrcaSlicer release from its publisher's GitHub releases.

    \b
    Linux          the release's AppImage; its printer profiles extracted beside
                   it, the whole image extracted where there is no FUSE
    macOS          OrcaSlicer.app copied out of the universal disk image
    Windows        the portable zip for x64 or arm64, unpacked
    anything else  refused, saying what is published

    The download is checked against the SHA-256 GitHub publishes for it, which
    must be the one pinned; the release must run and say its version before it
    goes under the tools dir (~/.apothecary/tools/orcaslicer/<version>/, or
    $APOTHECARY_TOOLS_DIR) and is made current.
    """
    from ..slicer.modules import SlicerError, get_module, reset_modules

    try:
        get_module("orcaslicer").install(click.echo, force=force)
    except SlicerError as exc:
        raise click.ClickException(str(exc)) from exc
    reset_modules()
    click.echo("")
    _status_lines()


@slicer.command("status")
def slicer_status():
    """Each slicer: what it slices, where it is, its version, and the pinned one."""
    _status_lines()
