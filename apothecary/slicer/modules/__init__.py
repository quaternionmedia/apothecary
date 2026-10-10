"""Slicer modules: one interface, one module per slicer apothecary drives.

A module says what it slices (the kind of printer, the model files it takes, the
files it writes), finds its program, reports its status, installs it, and turns
a slice into *steps* -- argv lists run in order in one environment and one
folder, the way a firmware toolchain module turns a build into steps. It also
says which value of a slice came from where (``settings``) and reads what its
program wrote (``result``). Apothecary itself slices nothing; a module only
turns a part, a printer's profile and the part's declared print settings into
a run of the slicer it drives.

One module today:

- ``orcaslicer`` (``modules/orcaslicer.py``): OrcaSlicer's command line, a
  pinned release installed by ``apothecary slicer install``.

**Where another plugs in.** A second slicer -- PrusaSlicer's command line,
CuraEngine, a slicer of resin printers -- is a subclass of ``SlicerModule`` in a
file of its own under this package, its program described as a ``Tool`` (the
environment variable naming the one to run, the one its install put in the
tools dir, its names on ``PATH``), registered in ``_registry`` below. The
routes, the CLI and the slice task go through this interface, so none of them
changes. A printer's profile -- the ``slicer.json`` kept with its part (see
``apothecary/slicer/profiles.py``) -- has a section per module, since each
slicer names its own base profiles.

**Switching.** Which module a slice uses is, in order: the ``slicer`` a request
or ``apothecary slicer slice --slicer`` names; else ``APOTHECARY_SLICER``; else
the ``slicer`` the printer's profile names (``"orcaslicer"`` in
``parts/ender3/slicer.json``). The owner switches by changing that one line --
a reviewed change, kept with the printer -- or for one process by the variable.
"""

from __future__ import annotations

import os
import platform
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable, ClassVar, Dict, List, Optional, Tuple

from ..models import Setting, SlicerStatus

if TYPE_CHECKING:  # pragma: no cover
    from ..profiles import Declared, PrinterProfile

Log = Callable[[str], None]

DEFAULT_SLICER = "orcaslicer"


class SlicerError(RuntimeError):
    """The slicer is missing, the printer's profile cannot be read, or a part
    asks for what the printer cannot do."""


class NotInstalled(SlicerError):
    """The slicer a slice would use is not installed, or does not run."""


def exe(name: str) -> str:
    return f"{name}.exe" if platform.system() == "Windows" else name


@dataclass(frozen=True)
class Tool:
    """The program a module runs, found as the firmware toolchains find theirs: the
    environment variable naming it, then the one its install put in the tools dir,
    then ``PATH``. The variable set to ``none`` means none (the browser suites'
    servers, so they never find a person's own)."""

    name: str
    env: str
    managed: Callable[[], Optional[Path]]  # the installed one, if there is one
    commands: Tuple[str, ...]  # its names on PATH

    def find(self) -> Tuple[Optional[Path], Optional[str]]:
        """Where it is, and what found it: the variable, ``tools dir`` or ``PATH``."""
        named = os.environ.get(self.env, "").strip()
        if named.lower() == "none":
            return None, None
        if named and Path(named).expanduser().is_file():
            return Path(named).expanduser(), self.env
        managed = self.managed()
        if managed is not None and managed.is_file():
            return managed, "tools dir"
        for command in self.commands:
            found = shutil.which(command)
            if found:
                return Path(found), "PATH"
        return None, None


@dataclass
class Plan:
    """What a module hands the slice task or the CLI: argv lists run in order,
    stopping at the first failure, in one environment and one folder."""

    steps: List[List[str]]
    env: Dict[str, str] = field(default_factory=dict)
    cwd: Optional[Path] = None


@dataclass
class Resolved:
    """A slice's values: each with where it came from (what the answer shows), and
    the module's own form of them (what it writes for its program)."""

    settings: List[Setting]
    configs: Dict[str, dict] = field(default_factory=dict)


@dataclass
class Output:
    """What the slicer wrote -- the G-code, None when it wrote none -- and what it
    said: its estimate, and its errors and warnings (``level``, ``line``, ``text``)."""

    gcode: Optional[Path]
    estimate: Optional[dict] = None
    messages: List[dict] = field(default_factory=list)


class SlicerModule(ABC):
    """One slicer. Subclasses fill in the class attributes and the abstract
    methods; see the package docstring."""

    id: ClassVar[str]
    label: ClassVar[str]  # what a person reads: "OrcaSlicer"
    technology: ClassVar[str]  # the kind of printer it slices for: "FFF"
    inputs: ClassVar[Tuple[str, ...]]  # the model files it takes
    writes: ClassVar[Tuple[str, ...]]  # the files a slice writes
    install_command: ClassVar[str]
    pinned: ClassVar[str]  # the release an install fetches

    @abstractmethod
    def status(self) -> SlicerStatus:
        """What is installed and whether it runs; never raises -- problems are listed."""

    @abstractmethod
    def install(self, log: Log, force: bool = False) -> SlicerStatus:
        """Fetch and put in place the pinned release, then say where it stands."""

    @abstractmethod
    def settings(self, profile: "PrinterProfile", declared: "Declared") -> Resolved:
        """Every value a slice of ``declared``'s part on ``profile``'s printer uses
        that the answer shows, with where it came from: the part's declared print
        settings, the printer's profile filling the rest. Raises SlicerError for a
        part that asks what the printer cannot do."""

    @abstractmethod
    def slice(self, model: Path, resolved: Resolved, work: Path) -> Plan:
        """Steps that slice ``model`` with ``resolved`` into ``work``; what they
        need written first (the slicer's own configuration files) is written into
        ``work`` here. Nothing is sent to a printer."""

    @abstractmethod
    def result(self, work: Path, said: List[str]) -> Output:
        """The G-code the steps wrote into ``work``, if they wrote one, the slicer's
        estimate, and its errors and warnings (``said`` is what it printed, one line
        each, each error or warning numbered by its line there)."""


def _registry() -> Dict[str, SlicerModule]:
    from .orcaslicer import OrcaSlicerModule

    return {m.id: m for m in (OrcaSlicerModule(),)}


_MODULES: Optional[Dict[str, SlicerModule]] = None


def modules() -> List[SlicerModule]:
    """Every registered module."""
    global _MODULES
    if _MODULES is None:
        _MODULES = _registry()
    return list(_MODULES.values())


def get_module(module_id: str) -> SlicerModule:
    for m in modules():
        if m.id == module_id:
            return m
    raise SlicerError(f"no slicer {module_id!r} (there are: {', '.join(m.id for m in modules())})")


def chosen_id(named: Optional[str] = None, profile: Optional["PrinterProfile"] = None) -> str:
    """The module a slice uses: the one named, else ``APOTHECARY_SLICER``, else the
    one the printer's profile names, else OrcaSlicer."""
    return (
        (named or "").strip()
        or os.environ.get("APOTHECARY_SLICER", "").strip()
        or (profile.slicer if profile is not None else "")
        or DEFAULT_SLICER
    )


def reset_modules() -> None:
    """Forget the modules; after an install, or between tests."""
    global _MODULES
    _MODULES = None
