"""Server-related CLI commands: serve, dev."""

import subprocess
import sys

import click
import uvicorn

from ..projects.parts.skeleton import ROOT
from ..stays_local import require_loopback
from .retired import retired
from .utils import _safe_echo


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


dev = retired("dev", "use `apothecary parts generate-stl --all && apothecary serve --reload`")


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
