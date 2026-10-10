"""`apothecary slicer`: install the slicer, say where it stands, and slice a part for a printer."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
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
    from ..slicer import compose

    click.secho("A slice is composed from:", bold=True)
    for kind in (compose.START, compose.FILAMENT, compose.DECLARED):
        for piece in compose.pieces(kind):
            mark = " (a stub)" if piece.stub else ""
            _safe_echo(f"  • {kind} {piece.id}{mark}: {piece.does}")
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


@slicer.command("slice")
@click.argument("part")
@click.option(
    "--printer",
    default=None,
    help="The printer: its part (default: the one that keeps a slicer profile); for "
    "SITE/PATH, its node in the site (default: the site's one printer)",
)
@click.option(
    "--slicer", "slicer_id", default=None, help="The slicer module (default: the printer's)"
)
@click.option(
    "--host",
    default="127.0.0.1",
    show_default=True,
    help="For SITE/PATH: the running server's address, this machine only (apothecary serve's)",
)
@click.option("--port", default=8000, show_default=True, type=int, help="For SITE/PATH: its port")
@click.option("--json-out/--text", default=False)
def slicer_slice(
    part: str,
    printer: Optional[str],
    slicer_id: Optional[str],
    host: str,
    port: int,
    json_out: bool,
):
    """Slice PART for a printer, and keep the G-code where the Print card's file
    box keeps a file.

    \b
    PART        a registered part, sliced here
    SITE/PATH   a node of a site -- a piece made from a picture, or a part
                standing there -- sliced by the running server (apothecary
                serve, on this machine), where made pieces live

    The part's declared print settings are used, the printer's profile filling
    the rest; each value is listed with where it came from. Nothing is sent to
    a printer.
    """
    if "/" in part:
        site, path = part.split("/", 1)
        record = _slice_through_server(host, port, site, path, printer, slicer_id, json_out)
    else:
        record = _slice_here(part, printer, slicer_id, json_out)
    if json_out:
        click.echo(json.dumps(record, indent=2))
        return
    _print_record(record)


def _slice_here(part: str, printer: Optional[str], slicer_id: Optional[str], json_out: bool):
    from ..slicer.modules import SlicerError
    from ..slicer.service import Here, resolve, slice_into

    log = (lambda _line: None) if json_out else click.echo
    try:
        target, chosen = resolve(part, printer=printer)
        return slice_into(target, chosen, Here(log), slicer=slicer_id).model_dump(mode="json")
    except SlicerError as exc:
        raise click.ClickException(str(exc)) from exc


SITE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
NODE_PATH = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,199}$")
POLL_SECONDS = 0.5


def _slice_through_server(
    host: str,
    port: int,
    site: str,
    path: str,
    printer: Optional[str],
    slicer_id: Optional[str],
    json_out: bool,
) -> dict:
    """Slice a node of a site through the running server's route, as the page will:
    a made piece lives in the server's memory. Its log is echoed as it arrives."""
    from .server import _loopback_or_die

    if not SITE_NAME.match(site) or not NODE_PATH.match(path):
        raise click.ClickException(
            f"{site}/{path}: want SITE/PATH, a site's name and a node's path"
        )
    if printer is not None and not NODE_PATH.match(printer):
        raise click.ClickException(f"{printer}: not a node's path")
    host = _loopback_or_die(host)
    base = f"http://[{host}]:{port}" if ":" in host else f"http://{host}:{port}"
    try:
        _call(base, "GET", "/health")
    except click.ClickException as exc:
        raise click.ClickException(
            f"no apothecary server at {base} ({exc.message}): a made piece lives in the "
            "running server -- start it with `apothecary serve`, or name its --host and --port"
        ) from None
    body = {"part": path, "site": site}
    if printer:
        body["printer"] = printer
    if slicer_id:
        body["slicer"] = slicer_id
    task = _call(base, "POST", "/slicer/slice", body)
    seen = 0
    while True:
        task = _call(base, "GET", f"/slicer/tasks/{task['id']}?since={seen}")
        if not json_out:
            for line in task.get("lines") or []:
                click.echo(line)
        seen = task.get("next", seen)
        if task.get("status") != "running":
            break
        time.sleep(POLL_SECONDS)
    answer = task.get("slice") or {}
    if answer.get("ok"):
        return answer["record"]
    for message in answer.get("messages") or []:
        where = f"line {message['line']}: " if message.get("line") else ""
        _safe_echo(f"  • {message['level']}: {where}{message['text']}", fg="yellow", err=True)
    raise click.ClickException(answer.get("error") or f"the slice {task.get('status')}")


def _call(base: str, method: str, path: str, body: Optional[dict] = None) -> dict:
    """One request to this machine's server, with no proxy in the way; its JSON."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=30) as response:  # noqa: S310 - this machine's own
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("detail")
        except ValueError:
            detail = None
        raise click.ClickException(f"{detail or exc.reason} ({exc.code})") from None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise click.ClickException(str(getattr(exc, "reason", exc))) from None


def _print_record(record: dict) -> None:
    click.echo("")
    click.secho(f"{record['name']}: kept as {record['file_id']}", bold=True)
    e = record.get("estimate")
    if e:
        click.echo(
            f"  {record['slicer']} estimates {e.get('time') or '?'}, "
            f"{e.get('filament_g') or '?'} g ({e.get('filament_mm') or '?'} mm) of filament, "
            f"{e.get('layers') or '?'} layers"
        )
    bounds = record.get("bounds")
    if bounds:
        lo, hi = bounds["min"], bounds["max"]
        click.echo(f"  extrudes from ({lo[0]}, {lo[1]}, {lo[2]}) to ({hi[0]}, {hi[1]}, {hi[2]})")
    for message in record.get("messages") or []:
        where = f"line {message['line']}: " if message.get("line") else ""
        _safe_echo(f"  • {message['level']}: {where}{message['text']}", fg="yellow")
    for problem in record.get("problems") or []:
        _safe_echo(f"  ✗ the Print card would refuse it: {problem}", fg="red")
