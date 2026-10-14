"""Server-related CLI commands: serve, dev."""

import os
import socket
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


def port_in_use(host: str, port: int) -> bool:
    """Whether something already listens on ``host:port``, asked as uvicorn binds: a
    port left in TIME_WAIT by a server that just stopped is free."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    for family, kind, proto, _name, address in infos:
        with socket.socket(family, kind, proto) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(address)
            except OSError:
                return True
    return False


def _port_free_or_die(host: str, port: int) -> None:
    """Refuse, before anything is printed or built, a port another server holds --
    `apothecary serve` and `photo view` both default to 8000."""
    if port_in_use(host, port):
        raise click.ClickException(
            f"{host}:{port}: port in use (is apothecary serve running?) -- pass --port"
        )


def run_server(
    target: object,
    host: str,
    port: int,
    reload: bool = False,
    log_level: str = "info",
    factory: bool = False,
) -> None:
    """Run uvicorn on this machine only. `target` is an app, or an import string for
    reload; with ``factory``, the import string names a function that builds the app.

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
        factory=factory,
    )


DEMO_HELP = (
    "Serve the demo: every loop of the page with nothing real. printer_1's mainboard "
    "is pinned to a simulated Ender, idle; a simulated ESP32 devkit says the hello of "
    "what is flashed to it; arduino-cli, cargo and espflash are scripted. It slices "
    "with your OrcaSlicer when one is installed (else Slice says how to install it) "
    "and prints to the simulated printer. No real serial port is opened. Its state is "
    "a folder of its own, .cache/demo in the checkout (under $APOTHECARY_CACHE_DIR when "
    "set), never ~/.apothecary or your pins; it is kept between runs, and deleting it "
    "starts the demo afresh. Serve without --demo to leave it."
)


@click.command()
@click.option(
    "--host",
    default="127.0.0.1",
    show_default=True,
    help="Address to listen on: this machine only (127.0.0.1, localhost, ::1)",
)
@click.option("--port", default=8000, type=int, show_default=True, help="Port to bind to")
@click.option("--reload/--no-reload", default=False, help="Enable auto-reload on code changes")
# `--viewer-path` and `--no-viewer` are accepted and ignored, hidden, for one
# release, so scripts that pass them keep working: no route serves a JSCAD
# viewer.
@click.option("--viewer-path", hidden=True, expose_value=False)
@click.option("--no-viewer", is_flag=True, hidden=True, expose_value=False)
@click.option(
    "--refresh-docs/--no-refresh-docs",
    default=False,
    help="Also regenerate docs/generated/ in the background (a headless browser run, "
    "a minute or two). Off by default: starting a server is not a test run.",
)
@click.option("--demo", is_flag=True, help=DEMO_HELP)
def serve(host: str, port: int, reload: bool, refresh_docs: bool, demo: bool):
    """Run the viewer's server: the viewer at /viewer, the docs at /docs, the API at
    /openapi.json. It listens on this machine only (see apothecary/stays_local.py).

    With --demo, every loop goes round with a simulated printer and devkit and
    scripted firmware tools, on a state folder of its own."""
    host = _loopback_or_die(host)
    _port_free_or_die(host, port)
    if refresh_docs:  # before the demo's environment is this process's
        refresh_docs_in_background()
    target, factory = "apothecary.api:app", False
    if demo:
        target, factory = "apothecary.demo:create_app", True
        _start_the_demo()
    click.echo(f"Starting server on http://{host}:{port}")
    click.echo(f"  Viewer: http://{host}:{port}/viewer")
    click.echo(f"  Docs:   http://{host}:{port}/docs")
    run_server(target, host, port, reload=reload, factory=factory)


def _start_the_demo() -> None:
    """The demo's folder made or found, its environment this process's (and a
    reload's), and what it is said in a few lines."""
    from ..demo import BOARD, DEVKIT, PRINTER, prepare, shown

    made = prepare()
    os.environ.update(made.env)
    slicer = (
        f"OrcaSlicer at {made.orcaslicer}"
        if made.orcaslicer
        else "no OrcaSlicer installed: Slice says how (apothecary slicer install)"
    )
    _safe_echo("The demo: nothing real is touched.", fg="cyan")
    click.echo(f"  State:    {shown(made.root)} (kept between runs; delete it to start afresh)")
    click.echo(f"  Printer:  {BOARD} pinned to a simulated Ender on {PRINTER}, idle")
    click.echo(f"  Devkit:   a simulated ESP32 on {DEVKIT}; arduino-cli, cargo, espflash scripted")
    click.echo(f"  Slicer:   {slicer}")
    click.echo("  To leave: stop it, and run apothecary serve without --demo")


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
