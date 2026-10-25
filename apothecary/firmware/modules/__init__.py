"""Toolchain modules: one interface, one module per way of building a board's firmware.

A module says what it builds (its languages and board families), finds its
tools, reports their status, installs them, and builds and flashes a sketch
as *steps* -- argv lists the task runner (or the CLI) runs in order, stopping
at the first failure. Apothecary itself compiles and flashes nothing; a
module only turns a sketch into steps for the engines it drives, as the
*Firmware toolchain seam* record has it.

Two modules today:

- ``arduino`` (``modules/arduino.py``): arduino-cli builds and uploads,
  esptool flashes raw images. Its routes, messages and sketches are the ones
  the seam had before there were modules.
- ``rust-esp32`` (``modules/rust_esp32.py``): cargo builds a Cargo project
  for the classic ESP32 on Espressif's Xtensa Rust toolchain, offline, from
  crates vendored at install time; espflash flashes it.

**Ports, too.** A module may find ports and listen to a board itself
(``ports``, ``monitor_argv``, ``probe``): Arduino through arduino-cli's
``board list`` and ``monitor`` and esptool, Rust through pyserial
(``firmware/serial_monitor.py``) and espflash's ``board-info`` -- so Rust works
with no arduino-cli at all. A port two modules find is the first one's, and is
listened to by it (devices.scan_ports).

**Where a new one plugs in.** A board family or a language added later -- the
ESP32-C3 on stable Rust, AVR in Rust, the RP2040 -- is a new module, not a
redesign: a subclass of ``ToolchainModule`` in a file of its own under this
package, its tools described as ``Tool``s (an environment variable naming the
one to run, its place in the tools dir, its name on ``PATH``), registered in
``MODULES`` below. Sketch discovery asks every registered module whether a
folder under ``parts/`` is one of its sketches (``sketch_in``); the status
route, the Bench's toolchain card, the build form, the compile and upload
routes and the CLI all go through this interface, so none of them changes.
A module whose sketches share a target with another's (a C3 Rust module
beside this one) names its own ``id`` and its sketches say which they want
in their ``firmware.json``'s ``toolchain``.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, ClassVar, Dict, Iterable, List, Optional, Tuple

from ...stays_local import subprocess_env
from ..models import ARDUINO, BoardInfo, ModuleStatus, SketchInfo, ToolStatus
from ..toolchains import ToolchainError, tools_dir

Log = Callable[[str], None]

# Never part of a sketch's sources, whatever the module: the sidecar is
# settings, not code, and these are what a build leaves behind.
NOT_SOURCES = {"firmware.json"}
BUILD_SUFFIXES = {".bin", ".elf", ".map"}


def exe(name: str) -> str:
    return f"{name}.exe" if platform.system() == "Windows" else name


@dataclass(frozen=True)
class Tool:
    """One program a module runs, found as ``ArduinoCli.detect`` finds arduino-cli:
    the environment variable naming it, then its place in the tools dir, then
    ``PATH``. The variable set to ``none`` means none (the browser suites'
    servers, so they never find a person's own)."""

    name: str
    env: str
    managed: str  # its path under tools_dir(), "/"-separated, without .exe
    command: str  # its name on PATH

    def managed_path(self) -> Path:
        return (
            tools_dir()
            .joinpath(*self.managed.split("/"))
            .with_name(exe(self.managed.rsplit("/", 1)[-1]))
        )

    def find(self) -> Tuple[Optional[Path], Optional[str]]:
        """Where it is, and what found it: the variable, ``tools dir`` or ``PATH``."""
        named = os.environ.get(self.env, "").strip()
        if named.lower() == "none":
            return None, None
        if named and Path(named).is_file():
            return Path(named), self.env
        managed = self.managed_path()
        if managed.is_file():
            return managed, "tools dir"
        found = shutil.which(self.command)
        return (Path(found), "PATH") if found else (None, None)

    def detect(self) -> Optional[Path]:
        return self.find()[0]


@dataclass
class Plan:
    """What a module hands the task runner or the CLI: argv lists run in order,
    stopping at the first failure, in one environment and one folder."""

    steps: List[List[str]]
    env: Dict[str, str] = field(default_factory=dict)
    cwd: Optional[Path] = None


def run_quietly(
    argv: List[str], env: Optional[dict] = None, cwd: Optional[Path] = None, timeout: int = 30
) -> Tuple[int, str]:
    """``argv``'s exit code and what it printed (stdout, then stderr), or (-1, why)."""
    try:
        done = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=subprocess_env(env),
            cwd=cwd,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return -1, str(exc)
    return done.returncode, ((done.stdout or "") + (done.stderr or "")).strip()


class ToolchainModule(ABC):
    """One way of building and flashing firmware. Subclasses fill in the class
    attributes and the abstract methods; see the package docstring."""

    id: ClassVar[str]
    label: ClassVar[str]  # what a person reads: "Arduino", "Rust for the ESP32"
    ring_label: ClassVar[str]  # its cell of Panels › Bench › Install: twelve characters
    short: ClassVar[str]  # a word for a sketch's row: "Arduino", "Rust"
    languages: ClassVar[Tuple[str, ...]]
    families: ClassVar[Tuple[str, ...]]  # the board families it builds for
    needs_board: ClassVar[bool] = False  # a build names a board (an Arduino FQBN)
    install_command: ClassVar[str]
    can: ClassVar[Tuple[str, ...]] = ("build", "flash")  # said by `check` and the Bench

    # -- sketches -----------------------------------------------------------------

    @abstractmethod
    def sketch_in(self, folder: Path, meta: dict, parts_dir: Path) -> Optional[SketchInfo]:
        """The sketch ``folder`` is, for this module, or None. ``meta`` is its
        ``firmware.json`` (``{}`` when there is none)."""

    def source_files(self, sketch: SketchInfo, nested: Iterable[Path] = ()) -> List[Path]:
        """The files a sketch is built from, sorted: every file in its folder but
        its sidecar, build output and the folders of ``nested`` sketches."""
        skip = [Path(p) for p in nested if Path(p) != sketch.path]
        files = []
        for f in sketch.path.rglob("*"):
            if not f.is_file() or f.name in NOT_SOURCES or f.suffix in BUILD_SUFFIXES:
                continue
            if any(f.is_relative_to(n) for n in skip):
                continue
            files.append(f)
        return sorted(files)

    # -- tools --------------------------------------------------------------------

    @abstractmethod
    def status(self) -> ModuleStatus:
        """What is installed and whether it runs; never raises -- problems are listed."""

    @abstractmethod
    def install(self, log: Log, force: bool = False) -> ModuleStatus:
        """Fetch and put in place what the module runs, then say where it stands."""

    def env(self) -> dict:
        """The environment the module's steps run in."""
        return subprocess_env()

    def _base_status(self) -> ModuleStatus:
        return ModuleStatus(
            id=self.id,
            label=self.label,
            languages=list(self.languages),
            families=list(self.families),
            install=self.install_command,
            needs_board=self.needs_board,
            can=list(self.can),
        )

    @staticmethod
    def tool_status(tool: Tool, version_argv: List[str], env=None) -> ToolStatus:
        path, found_by = tool.find()
        out = ToolStatus(name=tool.name, path=str(path) if path else None, found_by=found_by)
        if path is None:
            return out
        code, text = run_quietly([str(path), *version_argv], env=env)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if code == 0 and lines:
            out.version, out.ok = lines[0], True
        return out

    # -- ports: finding them, listening, asking the chip ----------------------------

    def ports(self) -> Optional[List["BoardInfo"]]:
        """The serial ports this module finds, none of them opened; None when it
        finds none (it does not, or is not installed). May raise ToolchainError."""
        return None

    def monitor_argv(self, port: str, baud: int) -> Optional[List[str]]:
        """A process that writes what the board on ``port`` says to its output until
        stopped; None when this module does not listen."""
        return None

    def probe(self, port: str) -> Optional[dict]:
        """The chip on ``port`` -- its type, revision, MAC, flash size -- asked of the
        board (this resets it); None when this module does not ask."""
        return None

    # -- build and flash ----------------------------------------------------------

    def board(self, sketch: SketchInfo, given: Optional[str]) -> Optional[str]:
        """The board a build names: the one given, else the sketch's default.
        A module that takes none refuses one."""
        if given:
            raise ValueError(
                f"{sketch.name} is built by {self.label} for {sketch.target or 'what its project names'}; "
                "it takes no FQBN"
            )
        return None

    def target_words(self, sketch: SketchInfo, board: Optional[str]) -> str:
        """What a build is for, as a task's title says it: an FQBN, or a chip."""
        return board or sketch.target or ""

    @abstractmethod
    def build(self, sketch: SketchInfo, board: Optional[str], out: Path) -> Plan:
        """Steps that build ``sketch`` into ``out``; nothing is sent to a board."""

    @abstractmethod
    def flash(self, sketch: SketchInfo, board: Optional[str], port: str, out: Path) -> Plan:
        """Steps that build ``sketch`` and write that fresh build to the board on
        ``port`` -- never a stale one."""

    @abstractmethod
    def artifact(self, sketch: SketchInfo, out: Path) -> Optional[Path]:
        """The file a build in ``out`` wrote to flash, if there is one."""


def _registry() -> Dict[str, ToolchainModule]:
    from .arduino import ArduinoModule
    from .rust_esp32 import RustEsp32Module

    return {m.id: m for m in (ArduinoModule(), RustEsp32Module())}


_MODULES: Optional[Dict[str, ToolchainModule]] = None


def modules() -> List[ToolchainModule]:
    """Every registered module, Arduino's first."""
    global _MODULES
    if _MODULES is None:
        _MODULES = _registry()
    return list(_MODULES.values())


def get_module(module_id: str) -> ToolchainModule:
    for m in modules():
        if m.id == module_id:
            return m
    raise ToolchainError(
        f"no toolchain module {module_id!r} (there are: {', '.join(m.id for m in modules())})"
    )


def module_for(sketch: SketchInfo) -> ToolchainModule:
    return get_module(sketch.toolchain or ARDUINO)


def reset_modules() -> None:
    """Forget the modules' cached tools; after an install, or between tests."""
    global _MODULES
    _MODULES = None
