"""`apothecary check`, and the retired system, install and submodules."""

import importlib.metadata
import sys

import click

from ..projects.parts.skeleton import ROOT
from ..projects.parts.stl_renderer import OpenSCADRenderer
from ..projects.registry import scan_projects
from .retired import retired
from .utils import _safe_echo

system = retired("system", "use `apothecary check`")


@click.command()
def check():
    """Check installation and dependencies; exit 1 if a required package is missing."""
    click.secho("Apothecary Installation Check", bold=True)
    click.echo("")

    # Check Python version
    py_version = sys.version.split()[0]
    _safe_echo(f"✓ Python: {py_version}")
    click.echo(f"  Executable: {sys.executable}")
    click.echo("")

    # Check required packages
    click.secho("Required packages:", bold=True)
    missing = []
    for pkg in ("fastapi", "jinja2", "pydantic", "click", "uvicorn"):
        try:
            __import__(pkg)
            version = importlib.metadata.version(pkg)
            _safe_echo(f"  ✓ {pkg}: {version}")
        except ImportError:
            _safe_echo(f"  ✗ {pkg}: NOT FOUND", fg="red")
            missing.append(pkg)
    click.echo("")

    # The fractal viewer's 3D library. Without it the viewer page loads,
    # renders nothing, and still shows its static "Layout valid" chip -- so
    # the absence has to be reported somewhere a person will look.
    click.secho("3D library (three.js):", bold=True)
    three_build = ROOT / "apothecary" / "static" / "vendor" / "three" / "three.module.js"
    if three_build.is_file():
        _safe_echo(f"  ✓ Vendored: {three_build.parent}")
    else:
        _safe_echo("  ✗ three.js missing", fg="yellow")
        click.echo("     The fractal viewer will render nothing. It is checked in under")
        click.echo(f"     {three_build.parent}; restore it from the repository.")

    click.echo("")

    # Check OpenSCAD availability for STL generation workflows
    click.secho("OpenSCAD:", bold=True)
    renderer = OpenSCADRenderer()
    if renderer.is_available:
        _safe_echo(f"  ✓ Available: {renderer.openscad_path}")
        version = renderer.get_version()
        if version:
            _safe_echo(f"  ✓ Version: {version}")
    else:
        _safe_echo("  ✗ OpenSCAD not found", fg="yellow")
        click.echo("     STL rendering endpoints and commands will be unavailable")

    click.echo("")

    # Firmware toolchain (optional: only needed to program boards)
    click.secho("Firmware toolchain:", bold=True)
    from ..firmware import service as firmware_service

    fw = firmware_service.toolchain_status()
    if fw.arduino_cli_ok:
        cores = ", ".join(c.id for c in fw.cores if c.installed) or "no cores"
        _safe_echo(f"  ✓ arduino-cli {fw.arduino_cli_version} ({cores})")
    else:
        _safe_echo(
            "  • arduino-cli not installed (optional: apothecary firmware install)", fg="yellow"
        )
    click.echo("")

    # Check for parts
    click.secho("Parts:", bold=True)
    items = [p for p in scan_projects(ROOT) if p.kind == "part"]
    click.echo(f"  Found {len(items)} part(s)")
    if items:
        for item in items[:5]:
            status = "✓" if item.wrapper else "•"
            _safe_echo(f"    {status} {item.name}")
        if len(items) > 5:
            click.echo(f"    ... and {len(items) - 5} more")

    if missing:
        raise click.ClickException(
            f"required packages missing: {', '.join(missing)}; run `uv sync`"
        )


install = retired("install", "nothing to install: three.js is vendored")


submodules = retired("submodules", "use `git submodule update --init --recursive`")
