"""``apothecary serve --demo``: every loop of the page, with nothing real.

The viewer as ``apothecary serve`` serves it, on a state folder of its own and
with every machine simulated:

- **printer_1's mainboard** is pinned to the simulated Ender
  (``firmware/gcode.py``'s ``SimulatedPrinter``), idle, on ``/dev/ttyFAKE1``;
- **cnc_router's controller** is pinned to the simulated GRBL router
  (``firmware/grbl.py``'s ``SimulatedRouter``), idle with its tool over the middle
  of the table, on ``/dev/ttyFAKE3``;
- **a Stream Deck +**, ``DEMODECK`` (``firmware/deck.py``), keeps the images it is sent and
  hears the events the page or a route gives it, and its knobs jog the simulated printer and
  router (``firmware/deck_control.py``); no HID device is listed or opened;
- **an ESP32 devkit** on ``/dev/ttyFAKE2`` runs whatever was last flashed to it and
  says that sketch's hello (the scripted bench's ``FAKE_DEVKIT``);
- **arduino-cli, cargo and espflash** are the scripted ones the browser suites run
  (``firmware/scripted.py``), so a sketch is built and flashed with nothing real;
  esptool is none;
- **the slicer** is the person's own OrcaSlicer when one is installed, read where
  it is; with none, Slice says how to install it;
- **printing** goes to the simulated printer;
- **a procedure**, ``bring-up``, stands under the garage: a person's check of a lead,
  the devkit flashed and heard, each machine homed, each step fired through the
  family's hub on GO (``family/procedures.py``); written once and kept;
- **a lighting console** sweeps every site's rig -- the theatre's -- as
  ``apothecary lighting simulate`` does (``console_feedback.simulate_levels``), ten
  times a second, set in the server's own state with nothing sent anywhere; not
  while a real console is listened for (``--console-sacn``, ``--console-osc``).

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
import threading
import time
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
ROUTER = "/dev/ttyFAKE3"  # the scripted bench's router controller: the simulated Grbl_ESP32
CONTROLLER = "cnc_router.frame_system.controller"
DECK = "DEMODECK"  # the simulated Stream Deck +
CONSOLE_HZ = 10  # the simulated console's levels a second, as `lighting simulate` sends them

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
        "APOTHECARY_SIMULATED_ROUTER": ROUTER,  # that port answers as the simulated router
        "APOTHECARY_SIMULATED_DEVKIT": "",  # the scripted arduino-cli finds the devkit
        "APOTHECARY_SIMULATED_DECK": DECK,  # the Stream Deck + that keeps what it is sent
        "APOTHECARY_DECK_CONTROL": "1",  # and whose knobs jog the two simulated machines
        "ARDUINO_CLI": str(write_fake_arduino_cli(bench / "arduino-cli")),
        "CARGO": str(write_fake_cargo(bench / "cargo")),
        "ESPFLASH": str(write_fake_espflash(bench / "espflash")),
        "ESPTOOL": "none",
        # The image models' qmcp is the simulated one, answering in process, unless
        # the person named another (simulated:slow, simulated:down, ...).
        "APOTHECARY_QMCP": os.environ.get("APOTHECARY_QMCP", "").strip() or "simulated",
        "FAKE_DEVKIT": "1",
        "FAKE_ROUTER": "1",  # the scripted arduino-cli lists the router's port too
    }
    variants = _variants_repo(root / "variants.git")
    if variants is not None:
        env["APOTHECARY_VARIANTS_REPO"] = str(variants)
    if orcaslicer is not None:
        env["APOTHECARY_ORCASLICER"] = str(orcaslicer)
    if openscad is not None:
        env["APOTHECARY_OPENSCAD"] = str(openscad)
    return Demo(root=root, env=env, orcaslicer=orcaslicer, openscad=openscad)


def _work_zero_on_the_coupon() -> None:
    """The router's work zero at the coupon's stock, wherever the tool stands, as a person
    touching off at its corner would leave it: so the coupon's toolpath is drawn on the
    coupon, and its cut stays within the travel."""
    from .example_hierarchy import ROUTER_COUPON_WORK_ZERO as zero
    from .firmware import gcode, grbl
    from .projects.parts.anolex_4060_evo_ultra_2 import WORK

    link = gcode.get_printer_links().get(ROUTER)
    at = grbl.poll_router(link).position
    x, y, z = (
        at["x"] + WORK.x - zero.x,
        at["y"] + WORK.y - zero.y,
        at["z"] + WORK.z - zero.z,
    )
    link.command(f"G10 L20 P1 X{x:g} Y{y:g} Z{z:g}", origin="control")


def _bring_up():
    """The procedure the demo's garage starts with, on its simulated bench."""
    from .family.procedures import Procedure

    devkit = f"{SITE}:esp32_blink"
    printer, router = f"{SITE}:{BOARD}", f"{SITE}:{CONTROLLER}"
    arm = "Arm its control in the Machine window first: GO never does."
    return Procedure(
        steps=[
            {
                "number": "1",
                "name": "Check the devkit's lead",
                "discipline": "electrical",
                "node": devkit,
                "notes": "A person's own step: its GO says the person did it.",
            },
            {
                "number": "2",
                "name": "Flash the devkit",
                "discipline": "firmware",
                "node": devkit,
                "family": {"board": {"flash": {"port": DEVKIT, "sketch": "esp32_blink@arduino"}}},
            },
            {
                "number": "3",
                "name": "Hear its hello",
                "discipline": "firmware",
                "node": devkit,
                "family": {"board": {"expect": {"node": devkit}}},
            },
            {
                "number": "4",
                "name": "Home the printer",
                "discipline": "mechanical",
                "node": printer,
                "notes": arm,
                "family": {"machine": {"home": {"node": printer}}},
            },
            {
                "number": "5",
                "name": "Home the router",
                "discipline": "mechanical",
                "node": router,
                "notes": arm,
                "waits": {"subject": f"{SITE}:printer_1", "property": "state", "value": "idle"},
                "family": {"machine": {"home": {"node": router}}},
            },
        ]
    )


def seed() -> Optional[str]:
    """printer_1's mainboard pinned to the simulated Ender, identified (``M115``) as
    the bench's real board is, and cnc_router's controller to the simulated router,
    identified (``$I``): what the printer's is pinned to, or None when it could not
    be (the page's Device section pins it by hand then; the router's the same, said
    in the log). The garage's procedure is written once, then kept. Refuses outside the
    demo's environment, where a port would be a real one."""
    from .family import procedures
    from .firmware import devices
    from .firmware.gcode import serial_engine
    from .firmware.toolchains import ToolchainError

    if running() is None or serial_engine() != "simulated":
        raise RuntimeError("the demo's pin is seeded in the demo's environment only")
    if procedures.load(SITE, "bring-up") is None:
        procedures.save(SITE, "bring-up", _bring_up())
    try:
        devices.identify_printer(ROUTER)
        devices.get_state().set_binding(SITE, CONTROLLER, devices.stable_identity(ROUTER))
        _work_zero_on_the_coupon()
    except (ToolchainError, OSError) as exc:
        log.warning("demo: cnc_router's controller not pinned: %s", exc)
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
    if not (os.environ.get("APOTHECARY_CONSOLE_SACN") or os.environ.get("APOTHECARY_CONSOLE_OSC")):
        threading.Thread(target=sweep_the_rigs, name="demo-console", daemon=True).start()
    return app


def sweep_the_rigs_once(t: float) -> int:
    """Every site's rig given the simulated console's levels at ``t`` seconds, as a
    PUT of them would set them; how many rigs were swept."""
    from .console_feedback import simulate_levels
    from .routes.lighting import RIG_LOADERS, _rig_state

    swept = 0
    for name in list(RIG_LOADERS):
        state = _rig_state(name)
        if state is not None:
            state.set_levels(simulate_levels(state.rig, t))
            swept += 1
    return swept


def sweep_the_rigs(stop: Optional[threading.Event] = None) -> None:
    """The simulated console, CONSOLE_HZ times a second until ``stop`` is set (never,
    in the demo's server: its thread ends with the process)."""
    stop = stop or threading.Event()
    started = time.monotonic()
    while not stop.wait(1 / CONSOLE_HZ):
        try:
            sweep_the_rigs_once(time.monotonic() - started)
        except Exception:  # a rig's files changed under it: the next sweep tries again
            log.exception("the demo's console could not sweep a rig")
