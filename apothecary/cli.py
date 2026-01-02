import json
import os
import shutil
import subprocess
import sys
from importlib import import_module
from pathlib import Path

import click
import uvicorn

from .example import create_example_scene
from .projects.parts.skeleton import ROOT
from .projects.registry import scan_projects, scan_templates, summarize_structure
from .scene import SceneLoadError, load_scene_from_json
from .templates import TemplateRenderer


def _safe_echo(message: str):
    """Echo message with safe encoding handling for Windows."""
    try:
        click.echo(message)
    except UnicodeEncodeError:
        # Fallback: replace special characters with ASCII equivalents
        message = message.replace("✓", "[OK]").replace("✗", "[X]").replace("⚠️", "[!]")
        click.echo(message)


@click.group()
def cli():
    """Apothecary OpenSCAD framework CLI."""


@cli.command()
def system():
    """Show system / environment information."""
    click.echo(f"Python {sys.version.split()[0]}")
    click.echo(f"Executable: {sys.executable}")


@cli.command()
def check():
    """Check installation and dependencies."""
    click.secho("Apothecary Installation Check", bold=True)
    click.echo("")

    # Check Python version
    py_version = sys.version.split()[0]
    click.echo(f"✓ Python: {py_version}")
    click.echo(f"  Executable: {sys.executable}")
    click.echo("")

    # Check required packages
    click.secho("Required packages:", bold=True)
    required = ["fastapi", "jinja2", "pydantic", "click", "uvicorn"]
    for pkg in required:
        try:
            mod = __import__(pkg)
            version = getattr(mod, "__version__", "unknown")
            click.echo(f"  ✓ {pkg}: {version}")
        except ImportError:
            click.secho(f"  ✗ {pkg}: NOT FOUND", fg="red")
    click.echo("")

    # Check JSCAD viewer assets
    click.secho("JSCAD Viewer:", bold=True)
    default_viewer = ROOT / "node_modules" / "@jscad" / "web" / "dist"
    env_viewer = os.getenv("APOTHECARY_VIEWER_PATH", "").strip()

    viewer_found = False
    if env_viewer:
        env_path = Path(env_viewer)
        if env_path.exists():
            click.echo(f"  ✓ Found via APOTHECARY_VIEWER_PATH: {env_path}")
            viewer_found = True
        else:
            click.secho(f"  ✗ APOTHECARY_VIEWER_PATH set but not found: {env_path}", fg="red")

    if default_viewer.exists():
        click.echo(f"  ✓ Found at default location: {default_viewer}")
        viewer_found = True
    elif not viewer_found:
        click.secho("  ✗ Not found at default location", fg="yellow")
        click.echo(f"     Expected: {default_viewer}")

    if not viewer_found:
        click.echo("")
        click.secho("  To install viewer assets:", fg="yellow")
        click.echo("    apothecary install")
        click.echo("    (or manually: npm install @jscad/web)")
        click.echo("  Or run server without viewer:")
        click.echo("    apothecary serve --no-viewer")

    click.echo("")

    # Check for parts
    click.secho("Parts:", bold=True)
    items = [p for p in scan_projects(ROOT) if p.kind == "part"]
    click.echo(f"  Found {len(items)} part(s)")
    if items:
        for item in items[:5]:
            status = "✓" if item.wrapper else "•"
            click.echo(f"    {status} {item.name}")
        if len(items) > 5:
            click.echo(f"    ... and {len(items) - 5} more")


@cli.command()
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
    click.echo("  • Run 'apothecary check' to verify installation")
    click.echo("  • Run 'apothecary serve' to start the API server")
    click.echo("  • Visit http://127.0.0.1:8000/viewer to use JSCAD viewer")


@cli.command()
@click.option(
    "--output", "-o", type=click.Path(dir_okay=False, writable=True), default="example.scad"
)
def testrun(output: str):
    """Render the built-in example scene to a file."""
    scene = create_example_scene()
    code = scene.render()
    Path(output).write_text(code, encoding="utf-8")
    click.echo(f"Wrote {output} ({len(code.splitlines())} lines)")


@cli.command("render")
@click.option(
    "--scene-file",
    type=click.Path(exists=True, dir_okay=False),
    help="JSON file describing a Scene model",
)
@click.option("--scene-json", type=str, help="Inline JSON string describing a Scene model")
@click.option("--output", "-o", type=click.Path(dir_okay=False), default="scene.scad")
def render_scene(scene_file: str | None, scene_json: str | None, output: str):
    """Render a Scene from JSON into SCAD code."""
    try:
        scene = load_scene_from_json(
            scene_file=Path(scene_file) if scene_file else None,
            scene_json=scene_json,
            allow_example_fallback=True,
        )
    except SceneLoadError as e:
        raise click.ClickException(str(e))
    code = scene.render()
    Path(output).write_text(code, encoding="utf-8")
    click.echo(f"Rendered scene '{scene.name}' -> {output}")


@cli.command("render-jscad")
@click.option(
    "--scene-file",
    type=click.Path(exists=True, dir_okay=False),
    help="JSON file describing a Scene model",
)
@click.option("--scene-json", type=str, help="Inline JSON string describing a Scene model")
@click.option("--output", "-o", type=click.Path(dir_okay=False), default="scene.jscad.js")
def render_scene_jscad(scene_file: str | None, scene_json: str | None, output: str):
    """Render a Scene from JSON into a JSCAD JS module."""
    try:
        scene = load_scene_from_json(
            scene_file=Path(scene_file) if scene_file else None,
            scene_json=scene_json,
            allow_example_fallback=True,
        )
    except SceneLoadError as e:
        raise click.ClickException(str(e))

    code = scene.render_jscad()
    Path(output).write_text(code, encoding="utf-8")
    click.echo(f"Rendered JSCAD scene '{scene.name}' -> {output}")


@cli.command("templategenerate")
@click.option(
    "--template", "-t", required=True, help="Jinja2 template string or @path/to/template.j2"
)
@click.option("--scene-file", type=click.Path(exists=True, dir_okay=False), help="Scene JSON file")
@click.option("--scene-json", type=str, help="Inline JSON string describing a Scene model")
@click.option("--output", "-o", type=click.Path(dir_okay=False), default="templated.scad")
def template_generate(template: str, scene_file: str | None, scene_json: str | None, output: str):
    """Render a scene with a Jinja2 template."""
    template_content = (
        Path(template[1:]).read_text(encoding="utf-8") if template.startswith("@") else template
    )

    try:
        scene = load_scene_from_json(
            scene_file=Path(scene_file) if scene_file else None,
            scene_json=scene_json,
            allow_example_fallback=True,
        )
    except SceneLoadError as e:
        raise click.ClickException(str(e))

    renderer = TemplateRenderer()
    code = renderer.render_scene_template(scene, template_content)
    Path(output).write_text(code, encoding="utf-8")
    click.echo(f"Templated scene '{scene.name}' -> {output}")


@cli.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8000, type=int, help="Port to bind to")
@click.option("--reload/--no-reload", default=False, help="Enable auto-reload on code changes")
@click.option(
    "--viewer-path",
    type=click.Path(file_okay=False, dir_okay=True, resolve_path=True, exists=True),
    help="Serve the JSCAD web viewer from this directory (defaults to node_modules/@jscad/web if present)",
)
@click.option("--no-viewer", is_flag=True, help="Disable the JSCAD viewer even if assets exist")
def serve(host: str, port: int, reload: bool, viewer_path: str | None, no_viewer: bool):
    """Run the FastAPI server."""
    # CRITICAL: Set environment variables BEFORE importing the app,
    # because the app module initializes the viewer mount at import time

    # Check for viewer assets and warn if missing
    viewer_available = False
    if no_viewer:
        os.environ["APOTHECARY_VIEWER_PATH"] = ""
        click.echo("⚠️  JSCAD viewer disabled via --no-viewer")
    elif viewer_path:
        os.environ["APOTHECARY_VIEWER_PATH"] = viewer_path
        viewer_available = True
        click.echo(f"✓ Using JSCAD viewer from: {viewer_path}")
    else:
        # Check default location
        default_viewer = ROOT / "node_modules" / "@jscad" / "web"
        env_viewer = os.getenv("APOTHECARY_VIEWER_PATH")

        if env_viewer and env_viewer.strip():
            viewer_check = Path(env_viewer.strip())
            if viewer_check.exists():
                viewer_available = True
                click.echo(f"✓ Using JSCAD viewer from environment: {viewer_check}")
            else:
                click.secho(
                    "⚠️  Warning: APOTHECARY_VIEWER_PATH set but path doesn't exist", fg="yellow"
                )
        elif default_viewer.exists():
            viewer_available = True
            # Set the environment variable so the app mount will work
            os.environ["APOTHECARY_VIEWER_PATH"] = str(default_viewer)
            click.echo(f"✓ JSCAD viewer found at: {default_viewer}")
        else:
            # Even if assets not found, still try to set it to the expected path
            # in case they get installed later
            os.environ["APOTHECARY_VIEWER_PATH"] = str(default_viewer)
            click.secho("⚠️  Warning: JSCAD viewer assets not found", fg="yellow", bold=True)
            click.echo("   The /viewer endpoints will return 503 errors.")
            click.echo("")
            click.secho("   To enable the viewer:", fg="yellow")
            click.echo("   • Run: apothecary install")
            click.echo("   • Or manually: npm install @jscad/web")
            click.echo("   • Or pass: --viewer-path /path/to/viewer/dist")
            click.echo("   • Or use: --no-viewer to suppress this warning")
            click.echo("")

    # NOW import the app after environment variables are set
    from .api import app as fastapi_app

    # Start the server
    click.echo(f"Starting server on http://{host}:{port}")
    if not viewer_available and not no_viewer:
        click.echo("(API endpoints will work, but viewer endpoints are unavailable)")

    if reload:
        # When reload is enabled, uvicorn needs an import string
        uvicorn.run("apothecary.api:app", host=host, port=port, reload=reload)
    else:
        # Without reload, we can pass the app directly
        uvicorn.run(fastapi_app, host=host, port=port, reload=False)


@cli.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8000, type=int, help="Port to bind to")
@click.option(
    "--install", is_flag=True, help="Run uv sync before starting (usually not needed with uv run)"
)
@click.option("--skip-stl", is_flag=True, help="Skip STL generation")
@click.option("--skip-elephant", is_flag=True, help="Skip elephant walk regeneration")
def dev(host: str, port: int, install: bool, skip_stl: bool, skip_elephant: bool):
    """Development workflow: regenerate files and start server.

    This convenience command runs the full dev setup:
    1. Optionally syncs dependencies (--install flag)
    2. Generates any missing STL files from SCAD sources
    3. Regenerates the elephant walk file
    4. Starts the dev server with auto-reload

    Example:
        apothecary dev
        apothecary dev --install --port 3000
    """
    import shutil

    import uvicorn

    click.secho("🧪 Apothecary Dev Mode", bold=True)
    click.echo("")

    # Step 1: Sync dependencies (optional)
    if install:
        click.secho("Step 1: Syncing dependencies...", fg="cyan")

        uv_path = shutil.which("uv")
        if uv_path:
            result = subprocess.run(
                ["uv", "sync"],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
        else:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-e", ".", "-q"],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )

        if result.returncode == 0:
            click.secho("  ✓ Dependencies synced", fg="green")
        else:
            click.secho(f"  ✗ Sync failed: {result.stderr}", fg="red")
            raise SystemExit(1)
    else:
        click.echo("Step 1: Skipped (use --install to sync)")

    # Step 2: Generate STL files
    if not skip_stl:
        click.secho("Step 2: Generating STL files...", fg="cyan")
        from .projects.parts.stl_renderer import get_renderer

        renderer = get_renderer()

        if renderer.is_available:
            items = [p for p in scan_projects(ROOT) if p.kind == "part"]
            generated = 0
            skipped = 0

            for item in items:
                if "elephant" in item.name.lower():
                    continue  # Skip elephant_walk, regenerated separately
                stl_path = item.path.with_suffix(".stl")
                if stl_path.exists():
                    skipped += 1
                    continue
                click.echo(f"  Generating {item.name}...", nl=False)
                result = renderer.render_stl(item.path, stl_path, timeout=120)
                if result.success:
                    click.secho(" ✓", fg="green")
                    generated += 1
                else:
                    click.secho(" ✗", fg="red")

            click.secho(f"  ✓ {generated} generated, {skipped} already exist", fg="green")
        else:
            click.secho("  ⚠ OpenSCAD not found, skipping STL generation", fg="yellow")
    else:
        click.echo("Step 2: Skipped (--skip-stl)")

    # Step 3: Regenerate elephant walk
    if not skip_elephant:
        click.secho("Step 3: Regenerating elephant walk...", fg="cyan")
        elephant_path = ROOT / "parts" / "elephant_walk.scad"

        # Use the parts elephant-walk command logic
        from .projects.parts.stl_renderer import get_renderer

        renderer = get_renderer()

        items = [
            p for p in scan_projects(ROOT) if p.kind == "part" and "elephant" not in p.name.lower()
        ]

        if items and renderer.is_available:
            # Calculate bounding boxes
            part_data = []
            for item in items:
                stl_path = item.path.with_suffix(".stl")
                bbox = _get_stl_bounding_box(stl_path)
                if bbox:
                    min_x, max_x, min_y, max_y, min_z, max_z = bbox
                    part_data.append(
                        {
                            "item": item,
                            "width": max_x - min_x,
                            "depth": max_y - min_y,
                            "height": max_z - min_z,
                            "center_x": (min_x + max_x) / 2,
                            "center_y": (min_y + max_y) / 2,
                            "min_y": min_y,
                            "max_y": max_y,
                        }
                    )
                else:
                    part_data.append(
                        {
                            "item": item,
                            "width": 50,
                            "depth": 50,
                            "height": 50,
                            "center_x": 0,
                            "center_y": 0,
                            "min_y": -25,
                            "max_y": 25,
                        }
                    )

            # Calculate positions
            gap = 10
            x_positions = []
            current_x = 0
            for i, data in enumerate(part_data):
                half_width = data["width"] / 2
                if i == 0:
                    x_positions.append(half_width)
                    current_x = half_width + data["width"] / 2
                else:
                    x_positions.append(current_x + gap + half_width)
                    current_x = x_positions[-1] + half_width

            # Generate SCAD content
            lines = [
                "// Elephant Walk - Auto-generated by apothecary dev",
                f"// Parts: {len(items)}, Gap: {gap}mm",
                "",
            ]

            for i, (data, x_pos) in enumerate(zip(part_data, x_positions, strict=False)):
                item = data["item"]
                rel_path = item.path.relative_to(ROOT / "parts").with_suffix(".stl")
                translate_x = x_pos - data["center_x"]
                translate_y = -data["center_y"]
                lines.append(f"// {item.name}")
                lines.append(f"translate([{translate_x:.2f}, {translate_y:.2f}, 0])")
                lines.append(f'    import("{rel_path.as_posix()}");')
                lines.append("")

            elephant_path.write_text("\n".join(lines), encoding="utf-8")

            # Generate STL
            stl_path = elephant_path.with_suffix(".stl")
            click.echo("  Rendering elephant_walk.stl...", nl=False)
            result = renderer.render_stl(elephant_path, stl_path, timeout=180)
            if result.success:
                click.secho(f" ✓ ({result.render_time_seconds:.1f}s)", fg="green")
            else:
                click.secho(f" ✗ {result.error_message}", fg="red")
        else:
            click.secho("  ⚠ Skipped (no parts or OpenSCAD not found)", fg="yellow")
    else:
        click.echo("Step 3: Skipped (--skip-elephant)")

    # Step 4: Start dev server
    click.echo("")
    click.secho(f"Step 4: Starting dev server on http://{host}:{port}", fg="cyan")
    click.secho("  → Viewer: http://" + host + ":" + str(port) + "/viewer", fg="green")
    click.echo("")

    uvicorn.run("apothecary.api:app", host=host, port=port, reload=True)


@cli.command()
@click.option("--scene-file", type=click.Path(exists=True, dir_okay=False))
@click.option("--scene-json", type=str, help="Inline JSON string describing a Scene model")
def validate(scene_file: str | None, scene_json: str | None):
    """Validate a scene JSON file."""
    try:
        scene = load_scene_from_json(
            scene_file=Path(scene_file) if scene_file else None,
            scene_json=scene_json,
            allow_example_fallback=False,
        )
    except SceneLoadError as e:
        raise click.ClickException(str(e))
    click.echo(f"Valid scene '{scene.name}' with {len(scene.objects)} top-level objects")


@cli.group()
def inventory():
    """Inventory projects, templates, and structure."""


@inventory.command("projects")
@click.option("--root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--json-out/--text", default=False)
def inventory_projects(root: str, json_out: bool):
    """List detected projects and parts in the repository."""
    root_path = Path(root).resolve()
    items = scan_projects(root_path)
    if json_out:
        click.echo(json.dumps([i.to_json() for i in items], indent=2))
        return
    for p in items:
        if p.kind == "part":
            suffix = f" [wrapper={p.wrapper}]" if p.wrapper else ""
            click.echo(f"part: {p.name} -> {p.path}{suffix}")
        else:
            click.echo(f"project: {p.name} (kind={p.kind}, readme={'yes' if p.readme else 'no'})")


@inventory.command("templates")
@click.option("--root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--json-out/--text", default=False)
def inventory_templates_cmd(root: str, json_out: bool):
    """List Jinja templates if a 'templates/' dir exists."""
    root_path = Path(root).resolve()
    templates = [str(p) for p in scan_templates(root_path)]
    if json_out:
        click.echo(json.dumps(templates, indent=2))
        return
    if not templates:
        click.echo("No templates found.")
        return
    for t in templates:
        click.echo(f"template: {t}")


@inventory.command("structure")
@click.option("--root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--json-out/--text", default=False)
def inventory_structure(root: str, json_out: bool):
    """Summarize repository structure: projects, parts, templates, missing READMEs."""
    root_path = Path(root).resolve()
    summary = summarize_structure(root_path)
    if json_out:
        click.echo(json.dumps(summary, indent=2))
        return
    click.echo(f"root: {summary['root']}")
    click.echo(f"projects: {summary['projects']}")
    click.echo(f"parts: {summary['parts']}")
    click.echo(f"templates: {summary['templates']}")
    click.echo(
        "missing READMEs: "
        + (", ".join(summary["missing_readmes"]) if summary["missing_readmes"] else "none")
    )


def _load_part_wrapper(name: str):
    """Import a part wrapper by part name (stem)."""
    module_name = name.lower().replace("-", "_").replace(" ", "_").replace(".", "_")
    full = f"apothecary.projects.parts.{module_name}"
    try:
        mod = import_module(full)
    except ModuleNotFoundError as e:
        raise click.ClickException(
            f"No wrapper module found for part '{name}'. Tried module '{full}'. "
            "Run 'apothecary parts list' to see available parts."
        ) from e
    if not hasattr(mod, "DEFAULT"):
        raise click.ClickException(f"Wrapper module '{full}' has no DEFAULT instance")
    return mod


@cli.group()
def parts():
    """Commands for part wrappers."""


@parts.command("list")
@click.option("--json-out/--text", default=False)
def parts_list(json_out: bool):
    items = [p for p in scan_projects(Path(".").resolve()) if p.kind == "part"]
    if json_out:
        click.echo(json.dumps([p.to_json() for p in items], indent=2))
        return
    for p in items:
        click.echo(f"{p.name} (wrapper={p.wrapper})")


@parts.command("info")
@click.argument("name")
@click.option("--json-out/--text", default=False)
def parts_info(name: str, json_out: bool):
    mod = _load_part_wrapper(name)
    part = mod.DEFAULT
    data = {
        "name": part.name,
        "source_file": str(part.source_file),
        "exists": part.exists,
        "category": part.category,
        "tags": part.tags,
        "description": part.description,
        "readme": str(part.readme_path) if part.readme_path and part.readme_path.exists() else None,
        "params_model": list(part.params_model.model_fields.keys()) if part.params_model else [],
    }
    if json_out:
        click.echo(json.dumps(data, indent=2))
    else:
        for k, v in data.items():
            click.echo(f"{k}: {v}")


@parts.command("render")
@click.argument("name")
@click.option("--params-json", type=str, help="JSON string of parameter overrides")
@click.option(
    "--template",
    type=click.Path(exists=True, dir_okay=False),
    help="Jinja2 template file for include",
)
@click.option("--output", "-o", type=click.Path(dir_okay=False), default="part.scad")
def parts_render(name: str, params_json: str | None, template: str | None, output: str):
    mod = _load_part_wrapper(name)
    part = mod.DEFAULT
    params_data = {}
    if params_json:
        try:
            params_data = json.loads(params_json)
        except Exception as e:
            raise click.ClickException(f"Invalid JSON for --params-json: {e}")
    if part.params_model:
        params = part.params_model(**params_data)
        params_json_out = params.model_dump_json()
    else:
        params_json_out = "{}"
    # Choose template
    if template:
        tpl_str = Path(template).read_text(encoding="utf-8")
    else:
        default_tpl = Path("templates/part.include.scad.j2")
        tpl_str = (
            default_tpl.read_text(encoding="utf-8")
            if default_tpl.exists()
            else "// {{ part.name }}\ninclude <{{ source_posix }}>"
        )
    # Render
    renderer = TemplateRenderer()
    ctx = {
        "part": part,
        "params_json": params_json_out,
        "source_posix": part.source_file.as_posix(),
    }
    code = renderer.render_template(tpl_str, ctx)
    Path(output).write_text(code, encoding="utf-8")
    click.echo(f"Rendered part '{part.name}' -> {output}")


@parts.command("generate-stl")
@click.argument("name", required=False)
@click.option("--all", "generate_all", is_flag=True, help="Generate STL for all parts")
@click.option("--force", is_flag=True, help="Regenerate even if STL exists")
@click.option("--timeout", default=120, type=int, help="Timeout per part in seconds")
def parts_generate_stl(name: str | None, generate_all: bool, force: bool, timeout: int):
    """Generate STL files from SCAD sources.

    STL files are not committed to git (they're in .gitignore).
    This command regenerates them from the source SCAD files.

    Examples:
        apothecary parts generate-stl calibration_cube
        apothecary parts generate-stl --all
        apothecary parts generate-stl --all --force
    """
    from .projects.parts.stl_renderer import get_renderer

    renderer = get_renderer()

    if not renderer.is_available:
        raise click.ClickException(
            "OpenSCAD not found. Please install OpenSCAD to generate STL files.\n"
            "Download from: https://openscad.org/downloads.html"
        )

    click.echo(f"Using OpenSCAD: {renderer.openscad_path}")
    click.echo("")

    if generate_all:
        # Generate for all parts
        items = [p for p in scan_projects(ROOT) if p.kind == "part"]
        click.echo(f"Generating STL for {len(items)} parts...")
        click.echo("")

        success_count = 0
        fail_count = 0
        skip_count = 0

        for item in items:
            scad_path = item.path
            stl_path = scad_path.with_suffix(".stl")

            # Check if we should skip
            if stl_path.exists() and not force:
                _safe_echo(f"  • {item.name}: STL exists (use --force to regenerate)")
                skip_count += 1
                continue

            click.echo(f"  Generating {item.name}...", nl=False)

            # Try to load part wrapper for display_rotation
            rotation = None
            try:
                mod = _load_part_wrapper(item.name)
                if hasattr(mod, "DEFAULT") and hasattr(mod.DEFAULT, "display_rotation"):
                    rot = mod.DEFAULT.display_rotation
                    if rot and rot.to_list() != [0, 0, 0]:
                        rotation = rot.to_list()
            except Exception:
                pass  # Fall back to no rotation

            if rotation:
                result = renderer.render_stl_with_rotation(
                    scad_path, stl_path, rotation=rotation, timeout=timeout
                )
            else:
                result = renderer.render_stl(scad_path, stl_path, timeout=timeout)

            if result.success:
                click.secho(f" ✓ ({result.render_time_seconds:.1f}s)", fg="green")
                success_count += 1
            else:
                click.secho(f" ✗ {result.error_message}", fg="red")
                fail_count += 1

        click.echo("")
        click.echo(f"Results: {success_count} generated, {skip_count} skipped, {fail_count} failed")

        if fail_count > 0:
            raise SystemExit(1)

    elif name:
        # Generate for a single part
        mod = _load_part_wrapper(name)
        part = mod.DEFAULT

        if not part.source_file.exists():
            raise click.ClickException(f"Source file not found: {part.source_file}")

        stl_path = part.source_file.with_suffix(".stl")

        if stl_path.exists() and not force:
            click.echo(f"STL already exists: {stl_path}")
            click.echo("Use --force to regenerate")
            return

        click.echo(f"Generating STL for {part.name}...")

        # Apply display rotation if defined
        rotation = part.display_rotation.to_list() if part.display_rotation else None
        if rotation and rotation != [0, 0, 0]:
            click.echo(f"  Applying display rotation: {rotation}")
            result = renderer.render_stl_with_rotation(
                part.source_file, stl_path, rotation=rotation, timeout=timeout
            )
        else:
            result = renderer.render_stl(part.source_file, stl_path, timeout=timeout)

        if result.success:
            _safe_echo(f"✓ Generated: {stl_path} ({result.render_time_seconds:.1f}s)")
        else:
            raise click.ClickException(f"Generation failed: {result.error_message}")

    else:
        raise click.ClickException("Specify a part name or use --all")


def _get_stl_bounding_box(stl_path: Path) -> tuple[float, float, float, float, float, float] | None:
    """Parse an STL file and return its bounding box (min_x, max_x, min_y, max_y, min_z, max_z)."""
    import struct

    if not stl_path.exists():
        return None

    min_x = min_y = min_z = float("inf")
    max_x = max_y = max_z = float("-inf")

    try:
        with open(stl_path, "rb") as f:
            # Check if binary or ASCII STL
            header = f.read(80)
            num_triangles = struct.unpack("<I", f.read(4))[0]

            # Binary STL: 80 byte header + 4 byte count + 50 bytes per triangle
            expected_size = 84 + (num_triangles * 50)
            f.seek(0, 2)  # Seek to end
            actual_size = f.tell()

            if actual_size == expected_size:
                # Binary STL
                f.seek(84)  # Skip header and count
                for _ in range(num_triangles):
                    # Skip normal (12 bytes), read 3 vertices (36 bytes), skip attribute (2 bytes)
                    f.read(12)  # normal
                    for _ in range(3):  # 3 vertices
                        x, y, z = struct.unpack("<fff", f.read(12))
                        min_x, max_x = min(min_x, x), max(max_x, x)
                        min_y, max_y = min(min_y, y), max(max_y, y)
                        min_z, max_z = min(min_z, z), max(max_z, z)
                    f.read(2)  # attribute byte count
            else:
                # ASCII STL - parse text
                f.seek(0)
                content = f.read().decode("utf-8", errors="ignore")
                import re

                for match in re.finditer(
                    r"vertex\s+([-\d.e+]+)\s+([-\d.e+]+)\s+([-\d.e+]+)", content, re.IGNORECASE
                ):
                    x, y, z = float(match.group(1)), float(match.group(2)), float(match.group(3))
                    min_x, max_x = min(min_x, x), max(max_x, x)
                    min_y, max_y = min(min_y, y), max(max_y, y)
                    min_z, max_z = min(min_z, z), max(max_z, z)

        if min_x == float("inf"):
            return None

        return (min_x, max_x, min_y, max_y, min_z, max_z)
    except Exception:
        return None


@parts.command("elephant-walk")
@click.option("--output", "-o", type=click.Path(dir_okay=False), default=None)
@click.option("--gap", default=10, type=int, help="Gap between parts in mm")
@click.option("--ensure-stl/--no-ensure-stl", default=True, help="Generate missing STLs first")
def parts_elephant_walk(output: str, gap: int, ensure_stl: bool):
    # Default output to parts/elephant_walk.scad
    if output is None:
        output = str(ROOT / "parts" / "elephant_walk.scad")
    """Generate an 'elephant walk' file showing all parts in a line.

    Creates an OpenSCAD file that imports STL files and arranges them
    in a single row along the X axis, using bounding boxes to prevent
    parts from overlapping.

    Note: This imports STL files, not SCAD modules, for reliable rendering
    regardless of how individual parts define their modules.

    Example:
        apothecary parts elephant-walk -o preview.scad
        apothecary parts elephant-walk --gap 20
    """
    # Per-part rotation overrides (rotate before calculating bounds)
    # Format: name -> (rx, ry, rz) rotation in degrees
    ROTATIONS = {
        # fifel is already tall in Z, no rotation needed
        # footpedal and solderfan are already flat
    }

    # Filter out elephant_walk itself and only include parts in subdirs
    items = [
        p for p in scan_projects(ROOT) if p.kind == "part" and "elephant" not in p.name.lower()
    ]

    if not items:
        raise click.ClickException("No parts found")

    # Ensure STL files exist
    if ensure_stl:
        from .projects.parts.stl_renderer import get_renderer

        renderer = get_renderer()

        if renderer.is_available:
            missing = []
            for item in items:
                stl_path = item.path.with_suffix(".stl")
                if not stl_path.exists():
                    missing.append(item)

            if missing:
                click.echo(f"Generating {len(missing)} missing STL files...")
                for item in missing:
                    stl_path = item.path.with_suffix(".stl")
                    click.echo(f"  {item.name}...", nl=False)
                    result = renderer.render_stl(item.path, stl_path, timeout=120)
                    if result.success:
                        click.secho(" ✓", fg="green")
                    else:
                        click.secho(f" ✗ {result.error_message}", fg="red")
                click.echo("")

    # Calculate bounding boxes and positions
    click.echo("Calculating bounding boxes...")
    part_data = []
    for item in items:
        stl_path = item.path.with_suffix(".stl")
        bbox = _get_stl_bounding_box(stl_path)
        if bbox:
            min_x, max_x, min_y, max_y, min_z, max_z = bbox
            width = max_x - min_x
            depth = max_y - min_y
            height = max_z - min_z
            # Center offset to place part's center at origin
            center_x = (min_x + max_x) / 2
            center_y = (min_y + max_y) / 2
            part_data.append(
                {
                    "item": item,
                    "width": width,
                    "depth": depth,
                    "height": height,
                    "center_x": center_x,
                    "center_y": center_y,
                    "min_y": min_y,
                    "max_y": max_y,
                }
            )
            click.echo(f"  {item.name}: {width:.1f} x {depth:.1f} x {height:.1f} mm")
        else:
            # Fallback for parts without valid STL
            part_data.append(
                {
                    "item": item,
                    "width": 50,
                    "depth": 50,
                    "height": 50,
                    "center_x": 0,
                    "center_y": 0,
                    "min_y": -25,
                    "max_y": 25,
                }
            )
            click.echo(f"  {item.name}: (using default size)")

    # Calculate cumulative X positions (no overlap)
    x_positions = []
    current_x = 0
    for i, data in enumerate(part_data):
        half_width = data["width"] / 2
        if i == 0:
            x_positions.append(half_width)
            current_x = half_width + data["width"] / 2
        else:
            # Position so left edge is gap away from previous right edge
            x_positions.append(current_x + gap + half_width)
            current_x = x_positions[-1] + half_width

    lines = [
        "// Elephant Walk - All parts laid out in a line",
        "// Auto-generated by: apothecary parts elephant-walk",
        "//",
        "// Parts are positioned using bounding boxes to prevent overlap.",
        f"// Parts: {len(items)}, Gap: {gap}mm",
        "",
        "// Import STL files - positioned to avoid collisions",
    ]

    # Generate import statements with calculated positions
    for i, (data, x_pos) in enumerate(zip(part_data, x_positions, strict=False)):
        item = data["item"]
        rel_path = item.path.relative_to(ROOT / "parts").with_suffix(".stl")
        # Translate to center the part at x_pos, and center Y at 0
        translate_x = x_pos - data["center_x"]
        translate_y = -data["center_y"]
        lines.append(
            f"// {item.name} ({data['width']:.1f} x {data['depth']:.1f} x {data['height']:.1f} mm)"
        )
        lines.append(f"translate([{translate_x:.2f}, {translate_y:.2f}, 0])")
        lines.append(f'    import("{rel_path.as_posix()}");')
        lines.append("")

    content = "\n".join(lines)
    Path(output).write_text(content, encoding="utf-8")
    total_width = x_positions[-1] + part_data[-1]["width"] / 2 if x_positions else 0
    click.echo(
        f"Generated elephant walk: {len(items)} parts, {total_width:.1f}mm total width -> {output}"
    )


@cli.group()
def test():
    """Commands for testing and test setup."""


@test.command("setup-e2e")
def test_setup_e2e():
    """Set up Playwright browsers for E2E testing."""
    click.secho("Playwright E2E Test Setup", bold=True)
    click.echo("")

    # Check if playwright is installed
    try:
        import playwright

        try:
            from importlib.metadata import version

            pw_version = version("playwright")
            _safe_echo(f"✓ Playwright installed (version {pw_version})")
        except Exception:
            _safe_echo("✓ Playwright installed")
    except ImportError:
        click.secho("✗ Playwright not installed", fg="red")
        click.echo("  Run: uv sync")
        return 1

    click.echo("")
    click.echo("Installing Playwright browsers (chromium)...")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode == 0:
            click.secho("✓ Chromium browser installed successfully", fg="green", bold=True)
            click.echo("")
            click.echo("Setup complete! Run E2E tests with:")
            click.echo("  apothecary test run-e2e")
            click.echo("  or: pytest tests/e2e/ -v")
        else:
            click.secho("✗ Browser installation failed", fg="red")
            if result.stderr:
                click.echo(f"  Error: {result.stderr[:200]}")
            return 1
    except subprocess.TimeoutExpired:
        click.secho("✗ Installation timed out after 5 minutes", fg="red")
        return 1
    except Exception as e:
        click.secho(f"✗ Error: {e}", fg="red")
        return 1


@test.command("validate-e2e")
def test_validate_e2e():
    """Validate E2E test setup."""
    click.secho("Validating E2E Test Setup", bold=True)
    click.echo("=" * 50)
    click.echo("")

    all_checks_passed = True

    # Check files
    click.echo("Checking required files...")
    required_files = [
        "tests/e2e/conftest.py",
        "tests/e2e/test_viewer.py",
        "tests/e2e/test_api.py",
    ]

    missing_files = []
    for file in required_files:
        file_path = ROOT / file
        if not file_path.exists():
            missing_files.append(file)

    if missing_files:
        click.secho("✗ Missing files:", fg="red")
        for f in missing_files:
            click.echo(f"   - {f}")
        all_checks_passed = False
    else:
        _safe_echo("✓ All required files present")
    click.echo("")

    # Check Playwright dependency
    click.echo("Checking Playwright installation...")
    try:
        import playwright

        try:
            from importlib.metadata import version

            pw_version = version("playwright")
            _safe_echo(f"✓ Playwright installed (version {pw_version})")
        except Exception:
            _safe_echo("✓ Playwright installed")
    except ImportError:
        click.secho("✗ Playwright not installed", fg="red")
        click.echo("   Run: uv sync")
        all_checks_passed = False
    click.echo("")

    # Check browsers
    click.echo("Checking Playwright browsers...")
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
                browser.close()
                _safe_echo("✓ Chromium browser installed")
            except Exception as e:
                click.secho(f"✗ Chromium not installed: {e}", fg="red")
                click.echo("   Run: apothecary test:setup-e2e")
                all_checks_passed = False
    except Exception as e:
        click.secho(f"✗ Error checking browsers: {e}", fg="red")
        all_checks_passed = False
    click.echo("")

    # Summary
    click.echo("=" * 50)
    if all_checks_passed:
        click.secho("✓ All checks passed!", fg="green", bold=True)
        click.echo("")
        click.echo("Run E2E tests with:")
        click.echo("  apothecary test run-e2e")
        return 0
    else:
        click.secho("✗ Some checks failed", fg="red", bold=True)
        click.echo("")
        click.echo("Run setup with:")
        click.echo("  apothecary test setup-e2e")
        return 1


@test.command("run-e2e")
@click.option("--headed", is_flag=True, help="Run tests with visible browser")
@click.option("--slowmo", type=int, default=0, help="Slow down operations by N milliseconds")
@click.option("--browser", default="chromium", help="Browser to use (chromium, firefox, webkit)")
@click.option("--base-url", default="http://127.0.0.1:8765", help="Base URL for test server")
def test_run_e2e(headed: bool, slowmo: int, browser: str, base_url: str):
    """Run E2E tests with Playwright.

    Note: Server must be running before tests. Start with:
        apothecary serve --port 8765
    """
    click.secho("Running E2E Tests", bold=True)
    click.echo(f"Server URL: {base_url}")
    click.echo("")

    # Build pytest command
    cmd = [sys.executable, "-m", "pytest", "tests/e2e/", "-v", f"--base-url={base_url}"]

    if headed:
        cmd.append("--headed")

    if slowmo > 0:
        cmd.append(f"--slowmo={slowmo}")

    if browser != "chromium":
        cmd.append(f"--browser={browser}")

    click.echo(f"Running: {' '.join(cmd)}")
    click.echo("")

    try:
        result = subprocess.run(cmd, cwd=ROOT)
        return result.returncode
    except Exception as e:
        click.secho(f"✗ Error running tests: {e}", fg="red")
        return 1


@test.command("run")
@click.option("--e2e", is_flag=True, help="Include E2E tests")
@click.option("--coverage", is_flag=True, help="Run with coverage report")
def test_run(e2e: bool, coverage: bool):
    """Run unit tests (and optionally E2E tests)."""
    click.secho("Running Tests", bold=True)
    click.echo("")

    # Build pytest command
    cmd = [sys.executable, "-m", "pytest", "-v"]

    if not e2e:
        cmd.extend(["tests/", "--ignore=tests/e2e"])
        click.echo("Running unit tests only...")
    else:
        cmd.append("tests/")
        click.echo("Running all tests (unit + E2E)...")

    if coverage:
        cmd.extend(["--cov=apothecary", "--cov-report=html"])

    click.echo("")

    try:
        result = subprocess.run(cmd, cwd=ROOT)

        if coverage and result.returncode == 0:
            click.echo("")
            click.echo("Coverage report generated: htmlcov/index.html")

        return result.returncode
    except Exception as e:
        click.secho(f"✗ Error running tests: {e}", fg="red")
        return 1


@test.command("all")
@click.option("--port", default=8765, type=int, help="Port for test server")
@click.option("--coverage", is_flag=True, help="Run with coverage report")
@click.option("--headed", is_flag=True, help="Run E2E tests with visible browser")
@click.option("--fail-fast", "-x", is_flag=True, help="Stop on first failure")
def test_all(port: int, coverage: bool, headed: bool, fail_fast: bool):
    """Run full test suite (unit + E2E) with aggregate summary.

    Automatically starts a test server, runs all tests, and produces
    a combined report for velocity review.
    """
    import time
    from datetime import datetime

    click.secho("=" * 60, fg="cyan", bold=True)
    click.secho("  APOTHECARY FULL TEST SUITE", fg="cyan", bold=True)
    click.secho("=" * 60, fg="cyan", bold=True)
    click.echo(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    click.echo(f"  Test server port: {port}")
    click.echo("")

    results = {
        "unit": {"passed": 0, "failed": 0, "skipped": 0, "time": 0},
        "e2e": {"passed": 0, "failed": 0, "skipped": 0, "time": 0},
    }
    server_proc = None
    overall_start = time.time()

    try:
        # ─────────────────────────────────────────────────────────────
        # Phase 1: Unit Tests
        # ─────────────────────────────────────────────────────────────
        click.secho("─" * 60, fg="blue")
        click.secho("  PHASE 1: Unit Tests", fg="blue", bold=True)
        click.secho("─" * 60, fg="blue")
        click.echo("")

        unit_start = time.time()
        unit_cmd = [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "--ignore=tests/e2e",
            "-v",
            "--tb=short",
            "-q",  # Quieter output
        ]
        if fail_fast:
            unit_cmd.append("-x")
        if coverage:
            unit_cmd.extend(["--cov=apothecary", "--cov-report=term-missing:skip-covered"])

        unit_result = subprocess.run(unit_cmd, cwd=ROOT, capture_output=True, text=True)
        results["unit"]["time"] = time.time() - unit_start

        # Parse pytest output for counts
        for line in unit_result.stdout.split("\n"):
            if "passed" in line or "failed" in line or "error" in line:
                click.echo(line)
            # Parse summary line like "55 passed in 0.97s"
            if " passed" in line:
                import re

                match = re.search(r"(\d+) passed", line)
                if match:
                    results["unit"]["passed"] = int(match.group(1))
                match = re.search(r"(\d+) failed", line)
                if match:
                    results["unit"]["failed"] = int(match.group(1))
                match = re.search(r"(\d+) skipped", line)
                if match:
                    results["unit"]["skipped"] = int(match.group(1))

        unit_ok = unit_result.returncode == 0

        if unit_ok:
            _safe_echo(f"\n✓ Unit tests PASSED ({results['unit']['time']:.1f}s)")
        else:
            click.secho(f"\n✗ Unit tests FAILED ({results['unit']['time']:.1f}s)", fg="red")
            if fail_fast:
                click.echo("\nStopping due to --fail-fast")
                raise SystemExit(1)

        click.echo("")

        # ─────────────────────────────────────────────────────────────
        # Phase 2: Start Test Server
        # ─────────────────────────────────────────────────────────────
        click.secho("─" * 60, fg="blue")
        click.secho("  PHASE 2: Starting Test Server", fg="blue", bold=True)
        click.secho("─" * 60, fg="blue")
        click.echo("")

        # Set environment for viewer
        env = os.environ.copy()
        env["APOTHECARY_VIEWER_PATH"] = ""  # Disable viewer for faster startup

        server_cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "apothecary.api:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ]

        server_proc = subprocess.Popen(
            server_cmd,
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for server to be ready
        import urllib.request

        base_url = f"http://127.0.0.1:{port}"
        for attempt in range(30):
            try:
                urllib.request.urlopen(f"{base_url}/health", timeout=1)
                _safe_echo(f"✓ Server ready at {base_url}")
                break
            except Exception:
                time.sleep(0.5)
        else:
            click.secho("✗ Server failed to start", fg="red")
            raise SystemExit(1)

        click.echo("")

        # ─────────────────────────────────────────────────────────────
        # Phase 3: E2E Tests
        # ─────────────────────────────────────────────────────────────
        click.secho("─" * 60, fg="blue")
        click.secho("  PHASE 3: E2E Tests", fg="blue", bold=True)
        click.secho("─" * 60, fg="blue")
        click.echo("")

        e2e_start = time.time()
        e2e_cmd = [
            sys.executable,
            "-m",
            "pytest",
            "tests/e2e/",
            "-v",
            "--tb=short",
            f"--base-url={base_url}",
        ]
        if fail_fast:
            e2e_cmd.append("-x")
        if headed:
            e2e_cmd.append("--headed")

        e2e_result = subprocess.run(e2e_cmd, cwd=ROOT, capture_output=True, text=True)
        results["e2e"]["time"] = time.time() - e2e_start

        # Parse E2E results
        for line in e2e_result.stdout.split("\n"):
            if "passed" in line or "failed" in line or "PASSED" in line or "FAILED" in line:
                click.echo(line)
            if " passed" in line:
                import re

                match = re.search(r"(\d+) passed", line)
                if match:
                    results["e2e"]["passed"] = int(match.group(1))
                match = re.search(r"(\d+) failed", line)
                if match:
                    results["e2e"]["failed"] = int(match.group(1))

        e2e_ok = e2e_result.returncode == 0

        if e2e_ok:
            _safe_echo(f"\n✓ E2E tests PASSED ({results['e2e']['time']:.1f}s)")
        else:
            click.secho(f"\n✗ E2E tests FAILED ({results['e2e']['time']:.1f}s)", fg="red")
            click.echo(e2e_result.stderr[-500:] if e2e_result.stderr else "")

    finally:
        # Cleanup server
        if server_proc:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_proc.kill()

    # ─────────────────────────────────────────────────────────────
    # Aggregate Summary
    # ─────────────────────────────────────────────────────────────
    total_time = time.time() - overall_start
    total_passed = results["unit"]["passed"] + results["e2e"]["passed"]
    total_failed = results["unit"]["failed"] + results["e2e"]["failed"]
    total_skipped = results["unit"]["skipped"] + results["e2e"]["skipped"]

    click.echo("")
    click.secho("=" * 60, fg="cyan", bold=True)
    click.secho("  AGGREGATE TEST SUMMARY", fg="cyan", bold=True)
    click.secho("=" * 60, fg="cyan", bold=True)
    click.echo("")
    click.echo(f"  {'Test Suite':<15} {'Passed':>10} {'Failed':>10} {'Time':>10}")
    click.echo(f"  {'-'*15} {'-'*10} {'-'*10} {'-'*10}")
    click.echo(
        f"  {'Unit':<15} {results['unit']['passed']:>10} {results['unit']['failed']:>10} {results['unit']['time']:>9.1f}s"
    )
    click.echo(
        f"  {'E2E':<15} {results['e2e']['passed']:>10} {results['e2e']['failed']:>10} {results['e2e']['time']:>9.1f}s"
    )
    click.echo(f"  {'-'*15} {'-'*10} {'-'*10} {'-'*10}")
    click.echo(f"  {'TOTAL':<15} {total_passed:>10} {total_failed:>10} {total_time:>9.1f}s")
    click.echo("")

    if total_failed == 0:
        click.secho(f"  ✓ ALL {total_passed} TESTS PASSED", fg="green", bold=True)
        click.echo("")
        return 0
    else:
        click.secho(f"  ✗ {total_failed} TEST(S) FAILED", fg="red", bold=True)
        click.echo("")
        return 1


def main():  # pragma: no cover - entry point
    cli()


if __name__ == "__main__":  # pragma: no cover
    main()
