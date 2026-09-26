"""System-related CLI commands: system, check, install, submodules."""

import importlib.metadata
import shutil
import subprocess
import sys
from pathlib import Path

import click

from ..projects.parts.skeleton import ROOT
from ..projects.parts.stl_renderer import OpenSCADRenderer
from ..projects.registry import scan_projects
from .retired import retired
from .utils import _safe_echo


def _get_submodule_status(root: Path) -> list[dict]:
    """Get status of git submodules in the repository."""
    submodules = []
    gitmodules = root / ".gitmodules"

    if not gitmodules.exists():
        return submodules

    # Parse .gitmodules file
    current_submodule = {}
    with open(gitmodules, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("[submodule"):
                if current_submodule:
                    submodules.append(current_submodule)
                current_submodule = {"name": line.split('"')[1]}
            elif "=" in line:
                key, value = line.split("=", 1)
                current_submodule[key.strip()] = value.strip()

    if current_submodule:
        submodules.append(current_submodule)

    # Check initialization status for each
    for sub in submodules:
        sub_path = root / sub.get("path", "")
        # Check if the submodule directory has content (not just .git)
        if sub_path.exists():
            contents = list(sub_path.iterdir())
            # Filter out .git file/directory
            non_git = [c for c in contents if c.name != ".git"]
            sub["initialized"] = len(non_git) > 0
            sub["full_path"] = sub_path
        else:
            sub["initialized"] = False
            sub["full_path"] = sub_path

    return submodules


@click.command()
def system():
    """Show system / environment information."""
    click.echo(f"Python {sys.version.split()[0]}")
    click.echo(f"Executable: {sys.executable}")


@click.command()
def check():
    """Check installation and dependencies."""
    click.secho("Apothecary Installation Check", bold=True)
    click.echo("")

    # Check Python version
    py_version = sys.version.split()[0]
    _safe_echo(f"✓ Python: {py_version}")
    click.echo(f"  Executable: {sys.executable}")
    click.echo("")

    # Check required packages
    click.secho("Required packages:", bold=True)
    required = ["fastapi", "jinja2", "pydantic", "click", "uvicorn"]
    for pkg in required:
        try:
            __import__(pkg)
            version = importlib.metadata.version(pkg)
            _safe_echo(f"  ✓ {pkg}: {version}")
        except ImportError:
            _safe_echo(f"  ✗ {pkg}: NOT FOUND", fg="red")
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


install = retired("install", "nothing to install: three.js is vendored")


@click.command()
@click.option("--init/--no-init", default=True, help="Initialize submodules (git submodule init)")
@click.option("--update/--no-update", default=True, help="Update submodules to latest")
@click.option("--recursive", is_flag=True, default=True, help="Process submodules recursively")
@click.option(
    "--status",
    "show_status",
    is_flag=True,
    help="Only show submodule status without making changes",
)
def submodules(init: bool, update: bool, recursive: bool, show_status: bool):
    """Initialize and update git submodules.

    Apothecary uses git submodules to include external OpenSCAD libraries
    like gridfinity-rebuilt-openscad. This command helps set them up.

    Examples:

        # Initialize and update all submodules
        apothecary submodules

        # Just show status
        apothecary submodules --status

        # Only initialize without updating
        apothecary submodules --no-update
    """
    click.secho("Git Submodules", bold=True)
    click.echo("")

    # Check for git
    git_available = shutil.which("git")
    if not git_available:
        _safe_echo("✗ git not found in PATH")
        click.echo("  Please install Git to manage submodules")
        click.echo("  Download from: https://git-scm.com/")
        raise SystemExit(1)

    # Get submodule status
    subs = _get_submodule_status(ROOT)

    if not subs:
        click.echo("No submodules configured in this repository.")
        click.echo("")
        click.echo("To add a submodule:")
        click.echo("  git submodule add <url> <path>")
        return

    # Display current status
    click.secho("Configured Submodules:", bold=True)
    for sub in subs:
        status = "initialized" if sub.get("initialized") else "not initialized"
        status_icon = "✓" if sub.get("initialized") else "○"
        _safe_echo(f"  {status_icon} {sub['name']}")
        click.echo(f"      Path: {sub.get('path', 'unknown')}")
        click.echo(f"      URL: {sub.get('url', 'unknown')}")
        click.echo(f"      Status: {status}")

    if show_status:
        return

    click.echo("")

    # Initialize submodules
    if init:
        click.secho("Initializing submodules...", bold=True)
        try:
            cmd = ["git", "submodule", "init"]

            result = subprocess.run(
                cmd,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                _safe_echo("  ✓ Submodules initialized")
            else:
                _safe_echo(f"  ✗ Init failed: {result.stderr.strip()}")
                raise SystemExit(1)

        except subprocess.TimeoutExpired:
            _safe_echo("  ✗ Init timed out")
            raise SystemExit(1) from None
        except Exception as e:
            _safe_echo(f"  ✗ Error: {e}")
            raise SystemExit(1) from None

    # Update submodules
    if update:
        click.secho("Updating submodules...", bold=True)
        try:
            cmd = ["git", "submodule", "update"]
            if recursive:
                cmd.append("--recursive")
            # Use --init to handle first-time setup
            cmd.append("--init")

            result = subprocess.run(
                cmd,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=300,  # Cloning can take time
            )

            if result.returncode == 0:
                _safe_echo("  ✓ Submodules updated")
                if result.stdout.strip():
                    click.echo(f"    {result.stdout.strip()}")
            else:
                _safe_echo(f"  ✗ Update failed: {result.stderr.strip()}")
                raise SystemExit(1)

        except subprocess.TimeoutExpired:
            _safe_echo("  ✗ Update timed out (network issue?)")
            raise SystemExit(1) from None
        except Exception as e:
            _safe_echo(f"  ✗ Error: {e}")
            raise SystemExit(1) from None

    # Verify final status
    click.echo("")
    click.secho("Final Status:", bold=True)
    subs = _get_submodule_status(ROOT)
    all_good = True
    for sub in subs:
        if sub.get("initialized"):
            _safe_echo(f"  ✓ {sub['name']} - ready")
        else:
            _safe_echo(f"  ✗ {sub['name']} - still not initialized")
            all_good = False

    if all_good:
        click.echo("")
        click.secho("All submodules ready!", fg="green", bold=True)
        click.echo("")
        click.echo("Available submodule parts:")
        _safe_echo("  • gridfinity - Modular storage bins (gridfinity-rebuilt-openscad)")
        click.echo("")
        click.echo("Use 'apothecary parts list' to see all available parts.")
