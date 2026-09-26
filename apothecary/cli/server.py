"""Server-related CLI commands: serve, dev."""

import shutil
import subprocess
import sys

import click
import uvicorn

from ..projects.parts.skeleton import ROOT
from ..projects.registry import scan_projects, stl_output_for
from ..stays_local import require_loopback
from .utils import _get_stl_bounding_box, _safe_echo


def _loopback_or_die(host: str) -> str:
    """Every server this CLI starts listens on this machine only; not a choice."""
    try:
        return require_loopback(host)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from None


def run_server(
    target: object, host: str, port: int, reload: bool = False, log_level: str = "info"
) -> None:
    """Run uvicorn on this machine only. `target` is an app, or an import string for reload.

    An SSE response such as /firmware/devices/stream ends only when the browser
    leaves; without the shutdown timeout, Ctrl-C or a reload waits on it forever.
    """
    uvicorn.run(
        target,
        host=_loopback_or_die(host),
        port=port,
        reload=reload,
        log_level=log_level,
        timeout_graceful_shutdown=3,
    )


@click.command()
@click.option(
    "--host",
    default="127.0.0.1",
    help="Address to listen on: this machine only (127.0.0.1, localhost, ::1)",
)
@click.option("--port", default=8000, type=int, help="Port to bind to")
@click.option("--reload/--no-reload", default=False, help="Enable auto-reload on code changes")
# The JSCAD viewer these named is served by no route; the flags do nothing
# and stay, hidden, for one release so scripts that pass them keep working.
@click.option("--viewer-path", hidden=True, expose_value=False)
@click.option("--no-viewer", is_flag=True, hidden=True, expose_value=False)
@click.option(
    "--refresh-docs/--no-refresh-docs",
    default=False,
    help="Also regenerate docs/generated/ in the background (a headless browser run, "
    "a minute or two). Off by default: starting a server is not a test run.",
)
def serve(host: str, port: int, reload: bool, refresh_docs: bool):
    """Run the FastAPI server. It listens on this machine only (see apothecary/stays_local.py)."""
    host = _loopback_or_die(host)
    click.echo(f"Starting server on http://{host}:{port}")
    click.echo(f"  Viewer: http://{host}:{port}/viewer")
    click.echo(f"  Docs:   http://{host}:{port}/docs")
    if refresh_docs:
        refresh_docs_in_background()
    run_server("apothecary.api:app", host, port, reload=reload)


@click.command()
@click.option(
    "--host",
    default="127.0.0.1",
    help="Address to listen on: this machine only (127.0.0.1, localhost, ::1)",
)
@click.option("--port", default=8000, type=int, help="Port to bind to")
@click.option(
    "--install", is_flag=True, help="Run uv sync before starting (usually not needed with uv run)"
)
@click.option("--skip-stl", is_flag=True, help="Skip STL generation")
@click.option("--elephant", is_flag=True, help="Force regeneration of elephant walk file")
@click.option(
    "--refresh-docs", is_flag=True, help="Also regenerate docs/generated/ in the background"
)
def dev(host: str, port: int, install: bool, skip_stl: bool, elephant: bool, refresh_docs: bool):
    """Development workflow: regenerate files and start server.

    This convenience command runs the full dev setup:
    1. Optionally syncs dependencies (--install flag)
    2. Generates any missing STL files from SCAD sources
    3. Regenerates the elephant walk file if missing or --elephant flag is set
    4. Starts the dev server with auto-reload

    Example:
        apothecary dev
        apothecary dev --install --port 3000
    """
    host = _loopback_or_die(host)
    _safe_echo("🧪 Apothecary Dev Mode", bold=True)
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
            _safe_echo("  ✓ Dependencies synced", fg="green")
        else:
            _safe_echo(f"  ✗ Sync failed: {result.stderr}", fg="red")
            raise SystemExit(1)
    else:
        click.echo("Step 1: Skipped (use --install to sync)")

    # Step 2: Generate STL files
    if not skip_stl:
        click.secho("Step 2: Generating STL files...", fg="cyan")
        from ..projects.parts.stl_renderer import get_renderer

        renderer = get_renderer()

        if renderer.is_available:
            items = [p for p in scan_projects(ROOT) if p.kind == "part"]
            generated = 0
            skipped = 0

            for item in items:
                if "elephant" in item.name.lower():
                    continue  # Skip elephant_walk, regenerated separately
                stl_path = stl_output_for(item)
                if stl_path.exists():
                    skipped += 1
                    continue
                click.echo(f"  Generating {item.name}...", nl=False)
                result = renderer.render_stl(item.path, stl_path, timeout=120)
                if result.success:
                    _safe_echo(" ✓", fg="green")
                    generated += 1
                else:
                    _safe_echo(" ✗", fg="red")

            _safe_echo(f"  ✓ {generated} generated, {skipped} already exist", fg="green")
        else:
            _safe_echo("  ⚠ OpenSCAD not found, skipping STL generation", fg="yellow")
    else:
        click.echo("Step 2: Skipped (--skip-stl)")

    # Step 3: Regenerate elephant walk
    if elephant or not (ROOT / "parts" / "elephant_walk.stl").exists():
        click.secho("Step 3: Regenerating elephant walk...", fg="cyan")
        elephant_path = ROOT / "parts" / "elephant_walk.scad"

        # Use the parts elephant-walk command logic
        from ..projects.parts.stl_renderer import get_renderer

        renderer = get_renderer()

        items = [
            p for p in scan_projects(ROOT) if p.kind == "part" and "elephant" not in p.name.lower()
        ]

        if items and renderer.is_available:
            # Calculate bounding boxes
            part_data = []
            for item in items:
                stl_path = stl_output_for(item)
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

            for _i, (data, x_pos) in enumerate(zip(part_data, x_positions, strict=False)):
                item = data["item"]
                rel_path = stl_output_for(item).relative_to(ROOT / "parts")
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
                _safe_echo(f" ✓ ({result.render_time_seconds:.1f}s)", fg="green")
            else:
                _safe_echo(f" ✗ {result.error_message}", fg="red")
        else:
            _safe_echo("  ⚠ Skipped (no parts or OpenSCAD not found)", fg="yellow")
    else:
        click.echo("Step 3: Skipped (--skip-elephant)")

    # Step 4: Start dev server
    click.echo("")
    click.secho(f"Step 4: Starting dev server on http://{host}:{port}", fg="cyan")
    _safe_echo("  → Viewer: http://" + host + ":" + str(port) + "/viewer", fg="green")
    _safe_echo("  → Docs:   http://" + host + ":" + str(port) + "/docs", fg="green")
    click.echo("")
    if refresh_docs:
        refresh_docs_in_background()

    uvicorn.run("apothecary.api:app", host=host, port=port, reload=True)


def refresh_docs_in_background() -> subprocess.Popen | None:
    """Regenerate docs/generated/ while the server runs, so /docs is current after a restart.

    `apothecary docs generate` runs the doc-workflow browser tests against a
    scripted server of its own (port 8766) and takes a minute or two; the
    pages it rewrites are served as they land, and the bar on every docs
    page says whether the run is still going or how it ended. Its output goes
    to docs/generated/refresh.log. A missing browser or a failing test is
    reported there and in the bar, never here.
    """
    from ..docs_site import GENERATED_ROOT, note_refresh

    GENERATED_ROOT.mkdir(parents=True, exist_ok=True)
    log = GENERATED_ROOT / "refresh.log"
    try:
        handle = log.open("w", encoding="utf-8")
        proc = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "from apothecary.cli.main import main; main()",
                "docs",
                "generate",
            ],
            cwd=ROOT,
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
    except OSError as exc:
        note_refresh(finished=None, ok=False, error=f"could not start docs generate: {exc}")
        _safe_echo(f"  (docs refresh not started: {exc})", fg="yellow")
        return None
    _safe_echo(f"  Docs refresh running in the background (log: {log.relative_to(ROOT)})")
    return proc
