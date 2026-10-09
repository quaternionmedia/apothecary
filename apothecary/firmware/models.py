"""Pydantic models shared by the firmware CLI, API and GUI."""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, List, Optional

from pydantic import AfterValidator, BaseModel, Field, field_validator, model_validator

# vendor:arch:board[:menu=value,...] -- e.g. arduino:avr:uno, esp32:esp32:esp32:FlashMode=qio
FQBN_RE = re.compile(r"^[A-Za-z0-9_.\-]+:[A-Za-z0-9_.\-]+:[A-Za-z0-9_.\-]+(:[A-Za-z0-9_.\-=,]+)?$")
# Serial device names on the platforms arduino-cli/esptool support.
PORT_RE = re.compile(r"^(/dev/[A-Za-z0-9_.\-/]+|COM[0-9]+)$")
# vendor:arch  (a platform/core id)
CORE_ID_RE = re.compile(r"^[A-Za-z0-9_.\-]+:[A-Za-z0-9_.\-]+$")


def validate_fqbn(value: str) -> str:
    if not FQBN_RE.match(value):
        raise ValueError(f"not a valid FQBN (vendor:arch:board): {value!r}")
    return value


def validate_port(value: str) -> str:
    if not PORT_RE.match(value):
        raise ValueError(f"not a serial port path: {value!r}")
    return value


# A serial port as a request field or query parameter: refused with a 422 by shape.
Port = Annotated[str, AfterValidator(validate_port)]


def validate_core_id(value: str) -> str:
    if not CORE_ID_RE.match(value):
        raise ValueError(f"not a core id (vendor:arch): {value!r}")
    return value


class BoardInfo(BaseModel):
    """A serial port arduino-cli detected, with any board it matched to it."""

    port: str
    protocol: str = "serial"
    label: str = ""
    board_name: Optional[str] = None
    fqbn: Optional[str] = None
    vid: Optional[str] = None
    pid: Optional[str] = None
    serial_number: Optional[str] = None  # USB iSerial; generic on some bridges (CP2102: "0001")


class KnownBoard(BaseModel):
    """A board an installed core knows how to target (``board listall``)."""

    name: str
    fqbn: str


class CoreInfo(BaseModel):
    """An installed or installable platform core (``core list``)."""

    id: str
    name: str = ""
    installed: Optional[str] = None
    latest: Optional[str] = None


class DisplaySpec(BaseModel):
    """Where a sketch's screen sits on its part, for the viewer's screen-emulation mode.

    Coordinates are in the part's own OpenSCAD frame (millimetres, z-up), so
    a viewer places the screen at ``node.position + position`` in world
    space. ``normal`` is the direction the screen faces; ``up`` orients its
    text; ``size`` is width × height.
    """

    position: List[float] = Field(min_length=3, max_length=3)
    normal: List[float] = Field(default=[0.0, 0.0, 1.0], min_length=3, max_length=3)
    up: List[float] = Field(default=[0.0, 1.0, 0.0], min_length=3, max_length=3)
    size: List[float] = Field(min_length=2, max_length=2)


class SketchInfo(BaseModel):
    """A sketch discovered under ``parts/``, and the toolchain module that builds it.

    An Arduino sketch is a folder holding ``<folder>.ino`` -- arduino-cli's own
    layout rule. Another module's sketch is the folder its module recognises
    (a Cargo project, for Rust), with a ``firmware.json`` naming the module in
    ``toolchain``. The sidecar supplies defaults (``fqbn``, ``cores``,
    ``libraries``, ``note``) so the GUI and CLI can offer them without the
    user re-typing them for every build, plus what the viewer needs to show
    the board's console in the scene (``baud``, ``display``).

    ``name`` is what the sketch announces (``apothecary <name>: hello``) and
    what a scene node's ``sketch_ref`` names; two implementations of one
    sketch -- the Arduino ``esp32_blink`` and the Rust one -- share it. ``id``
    tells them apart: an Arduino sketch's is its name, as it always was;
    another module's is ``<name>@<toolchain>``.
    """

    name: str
    path: Path
    ino: Optional[Path] = None  # an Arduino sketch's .ino; None for another module's
    toolchain: str = "arduino"  # the module that builds it (firmware/modules)
    id: str = ""  # unique among the sketches: the name, or <name>@<toolchain>
    language: str = "arduino"
    target: Optional[str] = None  # what a sketch with no FQBN builds for: its chip ("esp32")
    part: Optional[str] = None
    fqbn: Optional[str] = None
    cores: List[str] = Field(default_factory=list)
    libraries: List[str] = Field(default_factory=list)
    note: Optional[str] = None
    baud: int = 115200
    display: Optional[DisplaySpec] = None

    @model_validator(mode="after")
    def _id(self) -> "SketchInfo":
        if not self.id:
            self.id = sketch_id(self.name, self.toolchain)
        return self

    def to_json(self) -> dict:
        d = self.model_dump()
        d["path"] = str(self.path)
        d["ino"] = str(self.ino) if self.ino else None
        return d


ARDUINO = "arduino"


def sketch_id(name: str, toolchain: str) -> str:
    """An Arduino sketch is known by its name; another module's by ``name@module``."""
    return name if toolchain == ARDUINO else f"{name}@{toolchain}"


class ToolStatus(BaseModel):
    """One program a toolchain module runs, as found: where, and what it says it is."""

    name: str
    path: Optional[str] = None
    found_by: Optional[str] = None  # the env variable that named it, "tools dir", or "PATH"
    version: Optional[str] = None
    ok: bool = False


class ModuleStatus(BaseModel):
    """What a toolchain module says of itself: what it builds, its tools, its problems."""

    id: str
    label: str
    languages: List[str] = Field(default_factory=list)
    families: List[str] = Field(default_factory=list)  # the board families it builds for
    ok: bool = False  # it can build and flash a sketch
    tools: List[ToolStatus] = Field(default_factory=list)
    problems: List[str] = Field(default_factory=list)
    install: Optional[str] = None  # the command that installs it
    needs_board: bool = False  # a build names a board (an Arduino FQBN)
    installable: bool = True  # whether that command can install it on this machine


class ToolchainStatus(BaseModel):
    """What ``apothecary firmware validate`` and ``GET /firmware/status`` report."""

    tools_dir: str
    arduino_cli_path: Optional[str] = None
    arduino_cli_version: Optional[str] = None
    arduino_cli_ok: bool = False
    config_file: Optional[str] = None
    cores: List[CoreInfo] = Field(default_factory=list)
    esptool_path: Optional[str] = None
    esptool_version: Optional[str] = None
    esptool_ok: bool = False
    problems: List[str] = Field(default_factory=list)
    # Every toolchain module, Arduino's first; the fields above are Arduino's, as
    # they were before there were modules.
    toolchains: List[ModuleStatus] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.arduino_cli_ok


class TaskStatus(str, Enum):
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class FirmwareTask(BaseModel):
    """A background toolchain invocation whose output the GUI polls for."""

    id: str
    kind: str
    title: str
    command: List[str]
    port: Optional[str] = None  # the serial port it writes to (upload, flash); None holds none
    status: TaskStatus = TaskStatus.running
    returncode: Optional[int] = None
    started: datetime
    finished: Optional[datetime] = None
    lines: List[str] = Field(default_factory=list)

    def snapshot(self, since: int = 0) -> dict:
        """JSON view carrying only log lines from index ``since`` on."""
        d = self.model_dump(mode="json", exclude={"lines"})
        d["lines"] = self.lines[since:]
        d["next"] = len(self.lines)
        return d


# --- request bodies for the API --------------------------------------------


class ModuleInstallRequest(BaseModel):
    force: bool = False


class InstallRequest(BaseModel):
    version: str = "latest"
    force: bool = False
    cores: List[str] = Field(default_factory=list)
    libraries: List[str] = Field(default_factory=list)

    @field_validator("cores")
    @classmethod
    def _cores(cls, v: List[str]) -> List[str]:
        return [validate_core_id(c) for c in v]


class CoreInstallRequest(BaseModel):
    id: str

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        return validate_core_id(v)


class LibraryInstallRequest(BaseModel):
    names: List[str] = Field(min_length=1)

    @field_validator("names")
    @classmethod
    def _names(cls, v: List[str]) -> List[str]:
        for n in v:
            if not n.strip() or n.startswith("-"):
                raise ValueError(f"not a library name: {n!r}")
        return [n.strip() for n in v]


class CompileRequest(BaseModel):
    # The board an Arduino sketch is built for. A sketch of another module builds
    # for what its project names (a Rust sketch, its chip), and takes none.
    fqbn: Optional[str] = None

    @field_validator("fqbn")
    @classmethod
    def _fqbn(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else validate_fqbn(v)


class UploadRequest(CompileRequest):
    port: Port


class FlashImage(BaseModel):
    offset: str = Field(pattern=r"^0x[0-9A-Fa-f]+$")
    path: str  # relative to the repository root; resolved and bounds-checked by the API


class EsptoolFlashRequest(BaseModel):
    port: Port
    chip: str = "auto"
    baud: int = Field(460800, ge=9600, le=2000000)
    erase: bool = False
    images: List[FlashImage] = Field(min_length=1)

    @field_validator("chip")
    @classmethod
    def _chip(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9\-]+$", v):
            raise ValueError(f"not a chip name: {v!r}")
        return v


# --- devices: what is plugged in, what it is, and what should be running --------


class DeviceInfo(BaseModel):
    """One detected serial port, enriched by an esptool probe when available."""

    port: str
    label: str = ""
    vid: Optional[str] = None
    pid: Optional[str] = None
    board_name: Optional[str] = None  # arduino-cli's match, if any
    fqbn: Optional[str] = None
    chip: Optional[str] = None  # e.g. ESP32-D0WD-V3
    revision: Optional[str] = None
    features: List[str] = Field(default_factory=list)
    crystal: Optional[str] = None
    mac: Optional[str] = None
    flash_size: Optional[str] = None
    flash_manufacturer: Optional[str] = None
    probed_at: Optional[datetime] = None
    serial_number: Optional[str] = None
    printer: Optional["PrinterInfo"] = None  # a G-code firmware answered M115 on this port

    @property
    def identity(self) -> str:
        """Stable key for flash records and pins: the MAC, else the bridge's USB
        serial number, else the port.

        A port name is the socket, not the board: the same printer came back
        as ``/dev/ttyUSB0`` after a night as ``/dev/ttyUSB1``. Its FTDI's
        serial number did not change.
        """
        return self.mac or self.serial_number or self.port


class FlashRecord(BaseModel):
    """What Apothecary last put on a device -- the code that *should* be running."""

    identity: str  # DeviceInfo.identity at flash time
    port: str
    mac: Optional[str] = None
    sketch: Optional[str] = None  # its name, what it announces; None for a raw esptool flash
    sketch_id: Optional[str] = None  # which implementation of it (SketchInfo.id)
    toolchain: Optional[str] = None  # the module that built and flashed it
    target: Optional[str] = None  # what a sketch with no FQBN was built for (its chip)
    fqbn: Optional[str] = None
    images: List[str] = Field(default_factory=list)  # esptool: offset:path pairs
    build_sha256: Optional[str] = None  # of the uploaded .bin
    source_sha256: Optional[str] = None  # of the sketch sources at upload time
    flashed_at: datetime
    task_id: Optional[str] = None


class ExpectedFirmware(BaseModel):
    """A FlashRecord compared with the repository as it is now."""

    record: Optional[FlashRecord] = None
    source_changed: bool = False  # sketch edited since it was flashed
    build_changed: bool = False  # a newer build exists that was never uploaded
    sketch_missing: bool = False  # the recorded sketch is no longer under parts/


class ListenResult(BaseModel):
    port: str
    baud: int
    seconds: float
    lines: List[str] = Field(default_factory=list)
    running_sketch: Optional[str] = None  # from an `apothecary <name>: hello` banner
    chip_line: Optional[str] = None  # from the blink sketch's `chip: ...` line


class ProbeRequest(BaseModel):
    port: Port


class ListenRequest(ProbeRequest):
    seconds: float = Field(3.0, ge=0.5, le=15)
    baud: int = Field(115200, ge=300, le=2000000)
    reset: bool = False  # probe first so the boot banner is captured


# --- printers: a G-code firmware (Marlin and kin) on a serial port ----------------


class PrinterInfo(BaseModel):
    """What ``M115`` says a board is: firmware, machine, capabilities.

    Parsed from the ``KEY:value`` line and the ``Cap:NAME:0|1`` lines Marlin
    prints after it. ``uuid`` is the build's compiled-in id, shared by every
    board running the same build -- an identity of the firmware, not the
    board, so ``DeviceInfo.identity`` does not use it.
    """

    firmware_name: str
    machine_type: Optional[str] = None
    protocol_version: Optional[str] = None
    source_code_url: Optional[str] = None
    extruder_count: int = 1
    uuid: Optional[str] = None
    capabilities: dict = Field(default_factory=dict)  # Cap:AUTOREPORT_TEMP -> True
    baud: int = 115200
    boot_lines: List[str] = Field(default_factory=list)  # banner captured after the DTR reset
    identified_at: Optional[datetime] = None


class Heater(BaseModel):
    actual: float
    target: float = 0.0
    power: Optional[int] = None  # PWM duty from the `@:` field


class PrinterStatus(BaseModel):
    """One poll of a printer: temperatures, position, endstops, SD progress.

    ``state`` is drawn from the garage site's ``PRINTER_STATUSES`` (idle,
    printing, offline, maintenance) so a node bound to this port can take
    it verbatim; ``heating`` is folded into ``printing``/``idle`` by whether
    an SD print is in progress.
    """

    port: str
    polled_at: datetime
    state: str = "idle"
    hotends: List[Heater] = Field(default_factory=list)
    bed: Optional[Heater] = None
    position: Optional[dict] = None  # {"x":..,"y":..,"z":..,"e":..} from M114
    endstops: dict = Field(default_factory=dict)  # x_min -> "open" | "TRIGGERED"
    filament_present: Optional[bool] = None  # M119's `filament:` line, when a runout sensor exists
    sd_printing: bool = False
    sd_progress: Optional[float] = None  # 0..1, from M27
    print_time_s: Optional[int] = None  # from M31
    raw: List[str] = Field(default_factory=list)  # every line the poll received, for the log
    synced: List[dict] = Field(default_factory=list)  # scene nodes this poll updated (api.py)
    job: Optional[dict] = None  # a long exchange holding the port (a bed probe): kind, stage, since

    @property
    def heating(self) -> bool:
        return any(h.target > 0 and h.actual < h.target - 3 for h in [*self.hotends, self.bed] if h)


class PrinterQueryRequest(ProbeRequest):
    command: str = Field(min_length=2, max_length=16)


class PrinterControlArmRequest(ProbeRequest):
    armed: bool = True
    ttl_s: float = Field(300.0, ge=10, le=3600)


class PrinterControlRequest(ProbeRequest):
    command: str = Field(min_length=2, max_length=80)


class PrinterQueryResult(BaseModel):
    port: str
    command: str
    lines: List[str] = Field(default_factory=list)
    queried_at: datetime


class LevelingRecord(BaseModel):
    """One reading of a printer's bed: the mesh, what it means, and the conditions."""

    id: str
    port: str
    at: datetime
    method: str  # "probe" (G29 then read) or "read" (M420 V only)
    mesh: List[List[float]] = Field(default_factory=list)
    subdivided: Optional[List[List[float]]] = None
    stats: dict = Field(default_factory=dict)
    leveling_on: Optional[bool] = None
    probe_offset: Optional[dict] = None
    hotend_c: Optional[float] = None
    bed_c: Optional[float] = None
    firmware: Optional[str] = None
    note: Optional[str] = None
    lines: List[str] = Field(default_factory=list)  # everything the firmware said, for the log


class LevelingRequest(ProbeRequest):
    probe: bool = True  # False: read the stored mesh without probing
    note: Optional[str] = Field(None, max_length=200)


class PrintFile(BaseModel):
    """A G-code file kept on the host, ready to stream to a printer."""

    id: str
    name: str
    size: int
    sha256: Optional[str] = None  # of its bytes; None for a file kept before it was recorded
    lines: int  # the lines that would be sent: comments and blanks dropped
    uploaded_at: datetime
    problems: List[str] = Field(default_factory=list)  # why it may not be sent, if it may not


class PrintRecord(BaseModel):
    """One print streamed from the host, as it was kept before a print was a job.

    Nothing writes one any more; ``apothecary/jobs.py`` reads the ones kept under
    ``prints/records/`` once, and carries each over as a print job.
    """

    id: str
    port: str
    file_id: str
    name: str
    at: datetime
    finished: Optional[datetime] = None
    outcome: str  # done | cancelled | failed
    sent: int = 0
    total: int = 0
    error: Optional[str] = None
    firmware: Optional[str] = None
    lines: List[str] = Field(default_factory=list)  # the tail of what the firmware said


class PrintRequest(ProbeRequest):
    file_id: str = Field(..., pattern=r"^[A-Za-z0-9_.\-]{1,120}$")
    # The part or piece the print makes: a node's path in the printer's site.
    part: Optional[str] = Field(None, pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,199}$")


class PrinterIdentifyRequest(ProbeRequest):
    baud: int = Field(115200, ge=300, le=2000000)
    reset: bool = False  # reboot the board to capture its banner -- never mid-print


# --- bindings: which board is which scene node -----------------------------------

MAC_RE = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")
USB_SERIAL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{2,63}$")  # an FTDI's A106ZTEU, a CP210x's


def validate_identity(value: str) -> str:
    """A ``DeviceInfo.identity``: a MAC (normalised to lower case), a serial port,
    or a USB bridge's serial number."""
    v = value.strip()
    if MAC_RE.match(v.lower()):
        return v.lower()
    if PORT_RE.match(v):
        return v
    if USB_SERIAL_RE.match(v):
        return v
    raise ValueError(f"not a device identity (MAC, serial port or USB serial number): {value!r}")


class ManualBinding(BaseModel):
    """A device the user pinned to a scene node, overriding the by-sketch rule."""

    site: str
    path: str  # dotted node path, as GET /sites/{name}/nodes/{path}/stl addresses it
    identity: str  # DeviceInfo.identity: MAC or port
    bound_at: datetime


class NodeBinding(BaseModel):
    """One scene node that (could) have a board, and which board that is right now.

    ``binding_source`` says how ``device`` was chosen: ``manual`` (pinned by
    the user), ``sketch`` (the last board Apothecary flashed this node's
    sketch onto), or ``None`` when nothing has been flashed yet. ``device``
    is ``None`` when the chosen board is not currently plugged in;
    ``note`` says why.
    """

    path: str
    name: str
    part_ref: Optional[str] = None
    sketch_ref: Optional[str] = None
    sketch: Optional[str] = None  # resolved sketch name
    baud: int = 115200
    display: Optional[DisplaySpec] = None
    binding_source: Optional[str] = None  # "manual" | "sketch" | None
    identity: Optional[str] = None
    device: Optional[DeviceInfo] = None
    expected: Optional[ExpectedFirmware] = None
    candidates: List[str] = Field(default_factory=list)  # other ports running the same sketch
    printer_status: Optional[PrinterStatus] = None  # last poll of a bound printer, if any
    note: Optional[str] = None


class DeviceAttachRequest(BaseModel):
    identity: str

    @field_validator("identity")
    @classmethod
    def _identity(cls, v: str) -> str:
        return validate_identity(v)


# DeviceInfo names PrinterInfo before it is defined; finish the model now that it is.
DeviceInfo.model_rebuild()
