"""Pydantic models shared by the firmware CLI, API and GUI."""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

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


class SketchInfo(BaseModel):
    """An Arduino sketch discovered under ``parts/``.

    A sketch is a folder holding ``<folder>.ino`` -- arduino-cli's own layout
    rule. An optional ``firmware.json`` sidecar in that folder supplies
    defaults (``fqbn``, ``cores``, ``libraries``, ``note``) so the GUI and CLI
    can offer them without the user re-typing them for every build.
    """

    name: str
    path: Path
    ino: Path
    part: Optional[str] = None
    fqbn: Optional[str] = None
    cores: List[str] = Field(default_factory=list)
    libraries: List[str] = Field(default_factory=list)
    note: Optional[str] = None

    def to_json(self) -> dict:
        d = self.model_dump()
        d["path"] = str(self.path)
        d["ino"] = str(self.ino)
        return d


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
    fqbn: str

    @field_validator("fqbn")
    @classmethod
    def _fqbn(cls, v: str) -> str:
        return validate_fqbn(v)


class UploadRequest(CompileRequest):
    port: str

    @field_validator("port")
    @classmethod
    def _port(cls, v: str) -> str:
        return validate_port(v)


class FlashImage(BaseModel):
    offset: str = Field(pattern=r"^0x[0-9A-Fa-f]+$")
    path: str  # relative to the repository root; resolved and bounds-checked by the API


class EsptoolFlashRequest(BaseModel):
    port: str
    chip: str = "auto"
    baud: int = Field(460800, ge=9600, le=2000000)
    erase: bool = False
    images: List[FlashImage] = Field(min_length=1)

    @field_validator("port")
    @classmethod
    def _port(cls, v: str) -> str:
        return validate_port(v)

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

    @property
    def identity(self) -> str:
        """Stable key for flash records: the MAC when known, else the port."""
        return self.mac or self.port


class FlashRecord(BaseModel):
    """What Apothecary last put on a device -- the code that *should* be running."""

    identity: str  # DeviceInfo.identity at flash time
    port: str
    mac: Optional[str] = None
    sketch: Optional[str] = None  # None for a raw esptool flash
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
    port: str

    @field_validator("port")
    @classmethod
    def _port(cls, v: str) -> str:
        return validate_port(v)


class ListenRequest(ProbeRequest):
    seconds: float = Field(3.0, ge=0.5, le=15)
    baud: int = Field(115200, ge=300, le=2000000)
    reset: bool = False  # probe first so the boot banner is captured
