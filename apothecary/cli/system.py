"""System-related CLI commands: system, check, install."""

import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import click

from ..projects.parts.skeleton import ROOT
from ..projects.parts.stl_renderer import OpenSCADRenderer
from ..projects.registry import scan_projects
from .utils import _safe_echo


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

    # Check JSCAD viewer assets
    click.secho("JSCAD Viewer:", bold=True)
    default_viewer = ROOT / "node_modules" / "@jscad" / "web" / "dist"
    env_viewer = os.getenv("APOTHECARY_VIEWER_PATH", "").strip()

    viewer_found = False
    if env_viewer:
        env_path = Path(env_viewer)
        if env_path.exists():
            _safe_echo(f"  ✓ Found via APOTHECARY_VIEWER_PATH: {env_path}")
            viewer_found = True
        else:
            _safe_echo(f"  ✗ APOTHECARY_VIEWER_PATH set but not found: {env_path}", fg="red")

    if default_viewer.exists():
        _safe_echo(f"  ✓ Found at default location: {default_viewer}")
        viewer_found = True
    elif not viewer_found:
        _safe_echo("  ✗ Not found at default location", fg="yellow")
        click.echo(f"     Expected: {default_viewer}")

    if not viewer_found:
        click.echo("")
        click.secho("  To install viewer assets:", fg="yellow")
        click.echo("    apothecary install")
        click.echo("    (or manually: npm install @jscad/web)")
        click.echo("  Or run server without viewer:")
        click.echo("    apothecary serve --no-viewer")

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


@click.command()
@click.option("--viewer/--no-viewer", default=True, help="Install JSCAD viewer assets")
@click.option("--force", is_flag=True, help="Force reinstall even if already present")
@click.option("--npm-cmd", default="npm", help="npm command to use (e.g., 'pnpm', 'yarn')")
def install(viewer: bool, force: bool, npm_cmd: str):
    """Install and setup dependencies for Apothecary."""
    click.secho("Apothecary Installation", bold=True)
    click.echo("")

    issues_found = False
    fixes_applied = False

    # Check for npm/package manager
    if viewer:
        npm_available = shutil.which(npm_cmd)
        if not npm_available:
            _safe_echo(f"✗ {npm_cmd} not found in PATH")
            click.echo(f"  Please install Node.js and {npm_cmd} to enable JSCAD viewer")
            click.echo("  Download from: https://nodejs.org/")
            issues_found = True
            viewer = False  # Skip viewer installation
        else:
            _safe_echo(f"✓ {npm_cmd} found: {npm_available}")

    # Check and install JSCAD viewer
    if viewer:
        click.echo("")
        click.secho("JSCAD Viewer Installation:", bold=True)

        default_viewer = ROOT / "node_modules" / "@jscad" / "web" / "dist"
        package_json = ROOT / "package.json"

        if default_viewer.exists() and not force:
            _safe_echo(f"  ✓ Already installed at: {default_viewer}")
            click.echo("    Use --force to reinstall")
        else:
            if not package_json.exists():
                _safe_echo("  ✗ package.json not found")
                click.echo(f"    Expected at: {package_json}")
                click.echo("    Creating minimal package.json...")
                package_data = {
                    "name": "apothecary-viewer",
                    "version": "0.0.0",
                    "private": True,
                    "description": "Local JSCAD web viewer assets for Apothecary",
                    "dependencies": {"@jscad/web": "^2.6.0"},
                }
                package_json.write_text(json.dumps(package_data, indent=2), encoding="utf-8")
                _safe_echo("  ✓ Created package.json")
                fixes_applied = True

            click.echo(f"  Installing JSCAD viewer with {npm_cmd}...")
            try:
                result = subprocess.run(
                    [npm_cmd, "install", "--ignore-scripts"],
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                    timeout=120,
                    shell=True,  # Required on Windows for .CMD files
                )

                if result.returncode == 0:
                    if default_viewer.exists():
                        click.secho("  Successfully installed JSCAD viewer", fg="green", bold=True)
                        click.echo(f"    Location: {default_viewer}")
                        fixes_applied = True
                    else:
                        _safe_echo(f"  ⚠️  {npm_cmd} install completed but viewer not found")
                        click.echo(f"    Expected at: {default_viewer}")
                        issues_found = True
                else:
                    _safe_echo(f"  ✗ {npm_cmd} install failed")
                    if result.stderr:
                        click.echo(f"    Error: {result.stderr[:200]}")
                    issues_found = True

            except subprocess.TimeoutExpired:
                _safe_echo(f"  ✗ {npm_cmd} install timed out after 120 seconds")
                issues_found = True
            except Exception as e:
                _safe_echo(f"  ✗ Error running {npm_cmd}: {e}")
                issues_found = True

    # Check repository structure
    click.echo("")
    click.secho("Repository Structure:", bold=True)

    essential_dirs = [
        (ROOT / "apothecary", "Python package directory"),
        (ROOT / "parts", "OpenSCAD parts directory"),
        (ROOT / "templates", "Jinja2 templates directory"),
        (ROOT / "tests", "Test suite directory"),
    ]

    for dir_path, description in essential_dirs:
        if dir_path.exists():
            _safe_echo(f"  ✓ {dir_path.name}/ - {description}")
        else:
            _safe_echo(f"  ✗ {dir_path.name}/ missing - {description}")
            issues_found = True

    # Summary
    click.echo("")
    click.secho("Installation Summary:", bold=True)
    if fixes_applied:
        click.secho("  Applied fixes and installed dependencies", fg="green")
    if issues_found:
        _safe_echo("  ⚠️  Some issues found - check output above")
        click.echo("")
        click.echo("  Run 'apothecary check' for detailed status")
    else:
        click.secho("  Everything looks good!", fg="green", bold=True)

    click.echo("")
    click.echo("Next steps:")
    _safe_echo("  • Run 'apothecary check' to verify installation")
    _safe_echo("  • Run 'apothecary serve' to start the API server")
    _safe_echo("  • Visit http://127.0.0.1:8000/viewer to use JSCAD viewer")
