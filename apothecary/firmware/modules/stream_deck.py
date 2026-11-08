"""The Elgato Stream Deck +: found, drawn and heard, through ``python-elgato-streamdeck``.

A module beside Arduino's and Rust's that builds and flashes nothing: its sketches
are none, its ``can`` says what it does instead, and the Bench, ``apothecary check``
and ``GET /firmware/toolchains`` draw it as they draw the others. Its two tools are
not programs but a Python package (the optional dependency ``deck``) and the system's
hidapi, which the package loads with ctypes; neither is fetched by apothecary, so
its Install is refused and names what installs each. The device itself is
``firmware/deck.py``.
"""

from __future__ import annotations

import ctypes.util
import importlib.metadata
import importlib.util
from pathlib import Path
from typing import List, Optional

from ..models import ModuleStatus, SketchInfo, ToolStatus
from ..toolchains import ToolchainError
from . import Log, Plan, ToolchainModule

STREAM_DECK = "stream-deck"
PACKAGE = "streamdeck"  # python-elgato-streamdeck's name on PyPI; it imports as StreamDeck
INSTALL_PACKAGE = "uv sync --extra deck"
HIDAPI_NAMES = ("hidapi-libusb", "hidapi")  # what ctypes.util.find_library looks for


def package_version() -> Optional[str]:
    """The Stream Deck library's version, or None when it is not installed."""
    if importlib.util.find_spec("StreamDeck") is None:
        return None
    try:
        return importlib.metadata.version(PACKAGE)
    except importlib.metadata.PackageNotFoundError:
        return "installed"


def hidapi() -> Optional[str]:
    """Where the system's hidapi is, as the loader finds it, or None."""
    for name in HIDAPI_NAMES:
        found = ctypes.util.find_library(name)
        if found:
            return found
    return None


class StreamDeckModule(ToolchainModule):
    id = STREAM_DECK
    label = "Stream Deck +"
    ring_label = "Stream Deck"
    short = "Deck"
    languages = ("python",)
    families = ("stream-deck-plus",)
    needs_board = False
    install_command = INSTALL_PACKAGE
    can = ("find decks", "draw keys and strip", "hear keys, knobs and touches")

    def sketch_in(self, folder: Path, meta: dict, parts_dir: Path) -> Optional[SketchInfo]:
        return None  # a deck runs no sketch of ours

    def status(self) -> ModuleStatus:
        out = self._base_status()
        out.installable = False  # a package and a system library: nothing here fetches either
        version = package_version()
        library = hidapi()
        out.tools = [
            ToolStatus(name="python-elgato-streamdeck", version=version, ok=version is not None),
            ToolStatus(name="hidapi", path=library, ok=library is not None),
        ]
        if version is None:
            out.problems.append(
                f"python-elgato-streamdeck is not installed (run `{INSTALL_PACKAGE}`)"
            )
        if library is None:
            out.problems.append(
                "hidapi is not installed (on Debian and Ubuntu: `sudo apt install libhidapi-libusb0`)"
            )
        out.ok = version is not None and library is not None
        return out

    def install(self, log: Log, force: bool = False) -> ModuleStatus:
        raise ToolchainError(
            f"nothing here installs the Stream Deck's tools: run `{INSTALL_PACKAGE}` for the Python "
            "package and, on Debian and Ubuntu, `sudo apt install libhidapi-libusb0` for hidapi"
        )

    def build(self, sketch: SketchInfo, board: Optional[str], out: Path) -> Plan:
        raise ToolchainError("a Stream Deck builds nothing: it is drawn and heard from here")

    def flash(self, sketch: SketchInfo, board: Optional[str], port: str, out: Path) -> Plan:
        raise ToolchainError("a Stream Deck is never flashed from here")

    def artifact(self, sketch: SketchInfo, out: Path) -> Optional[Path]:
        return None

    def problems(self) -> List[str]:
        return self.status().problems
