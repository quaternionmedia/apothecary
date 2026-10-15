"""Drive a running server's lighting from the command line, without a console."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

import click

from ..console_feedback import simulate_levels
from ..lighting import LightingRig


def _request(url: str, data: bytes | None = None, method: str = "GET") -> dict:
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=2) as resp:
        return json.loads(resp.read())


@click.group("lighting")
def lighting() -> None:
    """A lighting rig's live feedback: a sweep to demo the viewer without a console."""


@lighting.command("simulate")
@click.option("--site", default="echs_pac", show_default=True, help="The site whose rig to drive.")
@click.option("--url", default="http://127.0.0.1:8000", show_default=True, help="The running server.")
@click.option("--rate", default=10.0, show_default=True, help="Updates per second.")
@click.option("--seconds", default=0.0, show_default=True, help="Stop after this long; 0 runs until interrupted.")
def simulate(site: str, url: str, rate: float, seconds: float) -> None:
    """Sweep the site's fixtures' levels, as a console would, until interrupted."""
    base = f"{url.rstrip('/')}/sites/{site}/lighting"
    try:
        rig = LightingRig.model_validate(_request(base)["rig"])
    except urllib.error.HTTPError as exc:
        click.echo(f"{site}: {exc.code} from {base} (is there a rig for this site?)", err=True)
        sys.exit(1)
    except urllib.error.URLError as exc:
        click.echo(f"no server at {url} ({exc.reason}); start one with `apothecary serve`", err=True)
        sys.exit(1)
    start = time.monotonic()
    try:
        while True:
            t = time.monotonic() - start
            if seconds and t >= seconds:
                break
            body = json.dumps({"levels": simulate_levels(rig, t)}).encode()
            _request(f"{base}/state", data=body, method="PUT")
            time.sleep(1 / rate)
    except KeyboardInterrupt:
        pass
