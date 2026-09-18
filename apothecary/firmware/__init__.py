"""Firmware toolchain seam: program Arduinos, ESP32s and similar from Apothecary.

Apothecary owns only the control plane here -- discovering sketches under
``parts/``, locating/installing the toolchain, validating inputs, and
streaming task output to the CLI and the web GUI. The engines that actually
compile and flash are bought, not built: ``arduino-cli`` (boards, cores,
libraries, compile, upload) and ``esptool`` (raw binary flashing for
Espressif chips). Both are invoked over a subprocess seam with a stable CLI
and JSON output contract, never linked or vendored -- the same disposition as
the ``openscad`` binary.
"""

from .devices import (
    FirmwareState,
    detected_devices,
    expected_firmware,
    get_state,
    listen,
    probe_device,
    stream_lines,
)
from .installer import ArduinoCliInstaller, InstallSpec
from .models import (
    BoardInfo,
    CoreInfo,
    DeviceInfo,
    ExpectedFirmware,
    FirmwareTask,
    FlashRecord,
    KnownBoard,
    ListenResult,
    SketchInfo,
    TaskStatus,
    ToolchainStatus,
)
from .sketches import discover_sketches, find_sketch
from .tasks import TaskRunner, get_task_runner
from .toolchains import (
    ArduinoCli,
    Esptool,
    ToolchainError,
    get_arduino_cli,
    get_esptool,
    tools_dir,
)

__all__ = [
    "ArduinoCli",
    "ArduinoCliInstaller",
    "BoardInfo",
    "CoreInfo",
    "DeviceInfo",
    "Esptool",
    "ExpectedFirmware",
    "FirmwareState",
    "FirmwareTask",
    "FlashRecord",
    "InstallSpec",
    "KnownBoard",
    "ListenResult",
    "SketchInfo",
    "TaskRunner",
    "TaskStatus",
    "ToolchainError",
    "ToolchainStatus",
    "detected_devices",
    "discover_sketches",
    "expected_firmware",
    "find_sketch",
    "get_arduino_cli",
    "get_esptool",
    "get_state",
    "get_task_runner",
    "listen",
    "probe_device",
    "stream_lines",
    "tools_dir",
]
