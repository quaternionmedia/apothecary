"""`apothecary check`, and the retired system, install and submodules."""

import importlib.metadata
import sys
from importlib import import_module

import click

from ..projects.parts.base import BasePart
from ..projects.parts.skeleton import ROOT
from ..projects.parts.stl_renderer import (
    OpenSCADRenderer,
    get_renderer,
    has_manifold,
    openscad_version,
)
from ..projects.registry import scan_projects
from .retired import retired
from .utils import _safe_echo

system = retired("system", "use `apothecary check`")


def _parts():
    """(name, part) for every registered part; part is None where its wrapper
    does not import."""
    found = []
    for item in scan_projects(ROOT):
        if item.kind != "part":
            continue
        if not item.wrapper:
            found.append((item.name, BasePart(name=item.name, source_file=item.path)))
            continue
        try:
            found.append((item.name, import_module(item.wrapper).DEFAULT))
        except Exception:
            found.append((item.name, None))
    return sorted(found, key=lambda pair: pair[0])


def _openscad_for(name: str, part) -> str:
    """One line: the OpenSCAD this part renders with and whether it has Manifold,
    or why it cannot be built here."""
    if part is None:
        return f"  ✗ {name}: its wrapper does not import"
    can_build, reason = part.can_generate_stl()
    if not can_build:
        return f"  ✗ {name}: {reason}"
    renderer = get_renderer()
    exe = part.get_openscad_path() or renderer.openscad_path
    if exe is None or not exe.exists():
        return f"  ✗ {name}: no OpenSCAD"
    version = openscad_version(exe) or "unknown version"
    manifold = "Manifold" if has_manifold(exe) else "no Manifold"
    return f"  ✓ {name}: {exe} ({version}; {manifold})"


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
        if not has_manifold(renderer.openscad_path):
            _safe_echo(
                "  • No Manifold: renders use CGAL (slow); "
                "`apothecary openscad install` fetches a snapshot that has it",
                fg="yellow",
            )
    else:
        _safe_echo("  ✗ OpenSCAD not found", fg="yellow")
        click.echo("     STL rendering endpoints and commands will be unavailable")
        click.echo("     `apothecary openscad install` fetches a snapshot (Linux x86_64)")

    click.echo("")

    click.secho("OpenSCAD by part:", bold=True)
    for name, part in _parts():
        _safe_echo(_openscad_for(name, part))

    click.echo("")

    # The slicer (optional: only needed to slice a part for a printer here)
    click.secho("Slicer:", bold=True)
    from ..slicer.modules import modules as slicer_modules

    for module in slicer_modules():
        found = module.status()
        if found.ok:
            _safe_echo(f"  ✓ {found.label} {found.tool.version}: {found.tool.path}")
        else:
            _safe_echo(
                f"  • {found.label} not installed (optional: {found.install}, "
                f"pinned {found.pinned})",
                fg="yellow",
            )
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
