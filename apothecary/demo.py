"""``apothecary serve --demo``: every loop of the page, with nothing real.

The viewer as ``apothecary serve`` serves it, on a state folder of its own and
with every machine simulated:

- **printer_1's mainboard** is pinned to the simulated Ender
  (``firmware/gcode.py``'s ``SimulatedPrinter``), idle, on ``/dev/ttyFAKE1``;
- **an ESP32 devkit** on ``/dev/ttyFAKE2`` runs whatever was last flashed to it and
  says that sketch's hello (the scripted bench's ``FAKE_DEVKIT``);
- **arduino-cli, cargo and espflash** are the scripted ones the browser suites run
  (``firmware/scripted.py``), so a sketch is built and flashed with nothing real;
  esptool is none;
- **the slicer** is the person's own OrcaSlicer when one is installed, read where
  it is; with none, Slice says how to install it;
- **printing** goes to the simulated printer.

Every serial port is the simulated engine's (``APOTHECARY_SERIAL_ENGINE``), so no
real port is opened or even listed.

**Where its state lives.** ``.cache/demo/`` in the checkout -- under
``$APOTHECARY_CACHE_DIR`` when that is set -- beside the render caches, ignored by
git and never the person's ``~/.apothecary``: its firmware state and pins, its
cameras, kept prints and slices (``state/``), its pictures (``pictures/``), its
render cache (``cache/``), its builds (``builds/``), the scripted bench
(``bench/``), a tools folder of its own (``tools/``) and a clone of the checkout
its variants are saved into (``variants.git``). It is kept between runs, as a
person's own state is, so pictures taken and variants saved are there next time;
printer_1's mainboard is pinned again at every start. Deleting the folder starts
the demo afresh.

``prepare`` makes the folder and says the environment the server runs in; the
server's process applies it and builds the app with ``create_app`` (uvicorn's
factory, so ``--reload`` builds it the same way), which seeds the pin.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from .projects.parts.skeleton import ROOT

# Set in the demo server's environment, naming its folder: the page's banner and
# create_app read it.
DEMO_ENV = "APOTHECARY_DEMO"

SITE = "garage"
PRINTER = "/dev/ttyFAKE1"  # the scripted arduino-cli's unmatched board: the simulated Ender
BOARD = "printer_1.frame_system.mainboard"
DEVKIT = "/dev/ttyFAKE2"  # the scripted bench's devkit

log = logging.getLogger(__name__)


def demo_root() -> Path:
    """``$APOTHECARY_CACHE_DIR/demo``, by default the checkout's ``.cache/demo``."""
    return Path(os.environ.get("APOTHECARY_CACHE_DIR") or ROOT / ".cache") / "demo"


def running() -> Optional[Path]:
    """The demo's folder when this process serves the demo, else None."""
    named = os.environ.get(DEMO_ENV, "").strip()
    return Path(named) if named else None


def shown(root: Path) -> str:
    """The folder as a person reads it: from the checkout when it is inside it."""
    try:
        return str(root.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(root)


@dataclass
class Demo:
    """The demo's folder, the environment its server runs in, and the tools of the
    person's own it found and uses where they are."""

    root: Path
    env: Dict[str, str] = field(default_factory=dict)
    orcaslicer: Optional[Path] = None
    openscad: Optional[Path] = None


def _orcaslicer() -> Optional[Path]:
    """The OrcaSlicer a slice would use: the one ``APOTHECARY_ORCASLICER`` names, the
    one ``apothecary slicer install`` put in the tools folder, or one on PATH."""
    from .slicer.modules.orcaslicer import TOOL

    return TOOL.find()[0]


def _openscad() -> Optional[Path]:
    """The OpenSCAD the person's own serve renders with: the one named, or the
    snapshot ``apothecary openscad install`` made current. None leaves the
    server to find one on PATH, as it would anyway."""
    from .projects.parts.stl_renderer import managed_openscad, openscad_override

    return openscad_override() or managed_openscad()


# How long a git call of the demo's may take: a local clone sharing its objects takes
# seconds; a git that waits on something (a prompt, a lock) is given up on.
GIT_TIMEOUT_S = 120


def _variants_repo(where: Path) -> Optional[Path]:
    """A bare clone of the checkout sharing its objects, made once: a variant saved in
    the demo is a ref there, never in the checkout. Its own identity, so a save is
    made whoever runs it, and nothing of the person's configuration signs it. None
    when git is missing, fails or does not answer in time: Save says so."""
    try:
        if not (where / "HEAD").exists():
            cloned = subprocess.run(
                ["git", "clone", "-q", "--bare", "--shared", str(ROOT), str(where)],
                capture_output=True,
                check=False,
                timeout=GIT_TIMEOUT_S,
            )
            if cloned.returncode != 0:  # a checkout git will not clone: an empty one
                made = subprocess.run(
                    ["git", "init", "-q", "--bare", str(where)],
                    capture_output=True,
                    check=False,
                    timeout=GIT_TIMEOUT_S,
                )
                if made.returncode != 0:
                    return None
        for key, value in (
            ("user.name", "Apothecary demo"),
            ("user.email", "demo@apothecary.invalid"),
            ("commit.gpgsign", "false"),
        ):
            subprocess.run(
                ["git", "config", key, value],
                cwd=where,
                capture_output=True,
                check=False,
                timeout=GIT_TIMEOUT_S,
            )
    except (OSError, subprocess.TimeoutExpired):  # no git, or none that answers: Save says so
        return None
    return where


def prepare(root: Optional[Path] = None) -> Demo:
    """Make the demo's folder (or find it, kept from the last run) and say the
    environment its server runs in. The person's OrcaSlicer and OpenSCAD are found
    first, as their own serve finds them, and named where they are: nothing is
    copied, and nothing is written outside the folder."""
    from .firmware.scripted import write_fake_arduino_cli, write_fake_cargo, write_fake_espflash

    root = (root or demo_root()).resolve()
    orcaslicer, openscad = _orcaslicer(), _openscad()
    folders = {
        name: root / name for name in ("state", "pictures", "tools", "cache", "builds", "bench")
    }
    for folder in folders.values():
        folder.mkdir(parents=True, exist_ok=True)
    bench = folders["bench"]
    env = {
        DEMO_ENV: str(root),
        "APOTHECARY_STATE_DIR": str(folders["state"]),
        "APOTHECARY_PICTURE_ROOT": str(folders["pictures"]),
        "APOTHECARY_TOOLS_DIR": str(folders["tools"]),
        "APOTHECARY_CACHE_DIR": str(folders["cache"]),
        # Every port is the simulated engine's: the printer answers as Marlin does,
        # and no real port is opened or listed.
        "APOTHECARY_SERIAL_ENGINE": "simulated",
        "APOTHECARY_SIMULATED_PRINTER": "idle",
        "APOTHECARY_SIMULATED_DEVKIT": "",  # the scripted arduino-cli finds the devkit
        "ARDUINO_CLI": str(write_fake_arduino_cli(bench / "arduino-cli")),
        "CARGO": str(write_fake_cargo(bench / "cargo")),
        "ESPFLASH": str(write_fake_espflash(bench / "espflash")),
        "ESPTOOL": "none",
        "FAKE_DEVKIT": "1",
    }
    variants = _variants_repo(root / "variants.git")
    if variants is not None:
        env["APOTHECARY_VARIANTS_REPO"] = str(variants)
    if orcaslicer is not None:
        env["APOTHECARY_ORCASLICER"] = str(orcaslicer)
    if openscad is not None:
        env["APOTHECARY_OPENSCAD"] = str(openscad)
    return Demo(root=root, env=env, orcaslicer=orcaslicer, openscad=openscad)


def seed() -> Optional[str]:
    """printer_1's mainboard pinned to the simulated Ender, identified (``M115``) as
    the bench's real board is: what it is pinned to, or None when it could not be
    (the page's Device section pins it by hand then). Refuses outside the demo's
    environment, where a port would be a real one."""
    from .firmware import devices
    from .firmware.gcode import serial_engine
    from .firmware.toolchains import ToolchainError

    if running() is None or serial_engine() != "simulated":
        raise RuntimeError("the demo's pin is seeded in the demo's environment only")
    try:
        devices.identify_printer(PRINTER)
        identity = devices.stable_identity(PRINTER)
        devices.get_state().set_binding(SITE, BOARD, identity)
    except (ToolchainError, OSError) as exc:
        log.warning("demo: printer_1's mainboard not pinned: %s", exc)
        return None
    return identity


def create_app():
    """The server's app in the demo's environment: its builds in its own folder, the
    simulated boards answering at once (as the suites' do), printer_1's mainboard
    pinned. uvicorn's factory, so ``--reload`` builds it the same way."""
    root = running()
    if root is None:
        raise RuntimeError(f"{DEMO_ENV} is not set: start the demo with apothecary serve --demo")
    from .firmware import bindings, service
    from .firmware.gcode import GcodeLink

    # A scripted build is not the checkout's, and a real flash record is never
    # compared with one.
    service.BUILD_ROOT = bindings.BUILD_ROOT = root / "builds"
    # A simulated board answers at once; a real board's silences (1.5 s after a link
    # opens) are nothing to wait for here.
    GcodeLink.time_scale = 0.02
    from .api import app

    seed()
    return app
