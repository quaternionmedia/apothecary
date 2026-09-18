"""Subprocess seams over the bought engines: ``arduino-cli`` and ``esptool``.

Nothing here knows how to compile or flash. Each class turns a typed request
into an argv list, runs the engine, and parses its documented output
(``--json`` for arduino-cli). Swapping an engine -- a different Arduino
build tool, a different flasher -- is a new class with the same methods, not
a redesign; see the *Firmware toolchain seam* decision record.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, List, Optional

from .models import BoardInfo, CoreInfo, KnownBoard

# Board-manager indexes for the popular third-party cores. arduino-cli only
# knows the official arduino:* cores out of the box; installing one of these
# needs its index URL passed alongside.
ADDITIONAL_URLS = {
    "esp32": "https://espressif.github.io/arduino-esp32/package_esp32_index.json",
    "esp8266": "https://arduino.esp8266.com/stable/package_esp8266com_index.json",
    "rp2040": "https://github.com/earlephilhower/arduino-pico/releases/download/global/package_rp2040_index.json",
}

# Cores the GUI offers one-click installs for: (core id, human label).
SUGGESTED_CORES = [
    ("arduino:avr", "Arduino AVR (Uno, Nano, Mega, Leonardo)"),
    ("esp32:esp32", "Espressif ESP32 (all variants)"),
    ("esp8266:esp8266", "Espressif ESP8266"),
    ("rp2040:rp2040", "Raspberry Pi Pico / RP2040"),
    ("arduino:samd", "Arduino SAMD (Zero, MKR)"),
]


class ToolchainError(RuntimeError):
    """The engine is missing, or returned an error we could not act on."""


def tools_dir() -> Path:
    """Where Apothecary keeps toolchains it installed itself.

    ``APOTHECARY_TOOLS_DIR`` overrides; the default is under ``$HOME`` on
    purpose rather than an XDG data dir, because sandboxed editors (the VS
    Code snap, for one) point ``XDG_DATA_HOME`` at a per-revision directory
    that vanishes on the next editor update.
    """
    override = os.environ.get("APOTHECARY_TOOLS_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".apothecary" / "tools"


def _exe(name: str) -> str:
    return f"{name}.exe" if platform.system() == "Windows" else name


def _run(
    argv: List[str], timeout: int = 60, env: Optional[dict] = None
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, env=env, check=False
        )
    except FileNotFoundError as exc:
        raise ToolchainError(f"{argv[0]} not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolchainError(f"{argv[0]} timed out after {timeout}s") from exc


def _json_or_error(result: subprocess.CompletedProcess, what: str):
    if result.returncode != 0:
        msg = (result.stderr or result.stdout or "").strip()
        raise ToolchainError(f"{what} failed (exit {result.returncode}): {msg}")
    text = result.stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ToolchainError(f"{what}: unparseable JSON from arduino-cli: {text[:200]}") from exc


class ArduinoCli:
    """The ``arduino-cli`` engine, found on PATH or in Apothecary's tools dir."""

    def __init__(self, path: Optional[Path] = None, config_file: Optional[Path] = None):
        self._path = Path(path) if path else None
        self.config_file = config_file

    # -- location -----------------------------------------------------------

    @property
    def path(self) -> Optional[Path]:
        if self._path is None:
            self._path = self.detect()
        return self._path

    @staticmethod
    def detect() -> Optional[Path]:
        """Explicit ``ARDUINO_CLI`` env, then our tools dir, then PATH."""
        env = os.environ.get("ARDUINO_CLI", "").strip()
        if env and Path(env).is_file():
            return Path(env)
        managed = tools_dir() / "arduino-cli" / _exe("arduino-cli")
        if managed.is_file():
            return managed
        found = shutil.which("arduino-cli")
        return Path(found) if found else None

    @property
    def is_available(self) -> bool:
        return self.path is not None and self.path.is_file()

    def argv(self, *args: str) -> List[str]:
        if not self.is_available:
            raise ToolchainError("arduino-cli is not installed. Run `apothecary firmware install`.")
        argv = [str(self.path)]
        if self.config_file:
            argv += ["--config-file", str(self.config_file)]
        return argv + list(args)

    # -- queries --------------------------------------------------------------

    def version(self) -> Optional[str]:
        if not self.is_available:
            return None
        result = _run(self.argv("version", "--json"), timeout=20)
        data = _json_or_error(result, "version")
        return (data or {}).get("VersionString") or (data or {}).get("version")

    def config_path(self) -> Optional[Path]:
        """The config file arduino-cli is actually using (``config dump``)."""
        if not self.is_available:
            return None
        result = _run(self.argv("config", "dump", "--json"), timeout=20)
        if result.returncode != 0:
            return None
        # `config dump --json` has no path field; ask where the default lives.
        return self.config_file or self._default_config_file()

    @staticmethod
    def _default_config_file() -> Path:
        home = Path.home()
        if platform.system() == "Windows":
            base = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local")) / "Arduino15"
        elif platform.system() == "Darwin":
            base = home / "Library" / "Arduino15"
        else:
            base = home / ".arduino15"
        return base / "arduino-cli.yaml"

    def board_list(self) -> List[BoardInfo]:
        data = _json_or_error(_run(self.argv("board", "list", "--json"), timeout=30), "board list")
        # v1.x wraps under detected_ports; 0.x returned a bare list.
        entries = data.get("detected_ports", []) if isinstance(data, dict) else (data or [])
        boards: List[BoardInfo] = []
        for entry in entries:
            port = entry.get("port", {}) or {}
            props = port.get("properties", {}) or {}
            matched = entry.get("matching_boards") or []
            first = matched[0] if matched else {}
            boards.append(
                BoardInfo(
                    port=port.get("address", ""),
                    protocol=port.get("protocol", "serial"),
                    label=port.get("label", "") or port.get("address", ""),
                    board_name=first.get("name"),
                    fqbn=first.get("fqbn"),
                    vid=props.get("vid"),
                    pid=props.get("pid"),
                )
            )
        return [b for b in boards if b.port]

    def board_listall(self) -> List[KnownBoard]:
        data = _json_or_error(
            _run(self.argv("board", "listall", "--json"), timeout=60), "board listall"
        )
        entries = data.get("boards", []) if isinstance(data, dict) else (data or [])
        return sorted(
            (
                KnownBoard(name=b.get("name", ""), fqbn=b.get("fqbn", ""))
                for b in entries
                if b.get("fqbn")
            ),
            key=lambda b: b.name.lower(),
        )

    def core_list(self) -> List[CoreInfo]:
        data = _json_or_error(_run(self.argv("core", "list", "--json"), timeout=60), "core list")
        entries = data.get("platforms", []) if isinstance(data, dict) else (data or [])
        cores: List[CoreInfo] = []
        for p in entries:
            installed = p.get("installed_version") or p.get("installed")
            latest = p.get("latest_version") or p.get("latest")
            name = p.get("name") or ""
            releases = p.get("releases") or {}
            if not name and installed and installed in releases:
                name = releases[installed].get("name", "")
            cores.append(
                CoreInfo(id=p.get("id", ""), name=name, installed=installed, latest=latest)
            )
        return [c for c in cores if c.id]

    # -- long-running commands: return argv for the task runner ---------------

    @staticmethod
    def additional_urls_for(core_ids: Iterable[str]) -> List[str]:
        urls = []
        for cid in core_ids:
            vendor = cid.split(":", 1)[0]
            if vendor in ADDITIONAL_URLS and ADDITIONAL_URLS[vendor] not in urls:
                urls.append(ADDITIONAL_URLS[vendor])
        return urls

    def _with_urls(self, argv: List[str], core_ids: Iterable[str]) -> List[str]:
        urls = self.additional_urls_for(core_ids)
        return argv + (["--additional-urls", ",".join(urls)] if urls else [])

    def config_init_argv(self) -> List[str]:
        return self.argv("config", "init", "--overwrite")

    def core_update_index_argv(self, core_ids: Iterable[str] = ()) -> List[str]:
        return self._with_urls(self.argv("core", "update-index"), core_ids)

    def core_install_argv(self, core_id: str) -> List[str]:
        return self._with_urls(self.argv("core", "install", core_id), [core_id])

    def lib_install_argv(self, names: Iterable[str]) -> List[str]:
        return self.argv("lib", "install", *names)

    def monitor_argv(self, port: str, baud: int = 115200) -> List[str]:
        """Quiet serial monitor; the caller bounds it with a timeout."""
        return self.argv("monitor", "--port", port, "--config", f"baudrate={baud}", "--quiet")

    def compile_argv(
        self, sketch_dir: Path, fqbn: str, build_path: Optional[Path] = None
    ) -> List[str]:
        argv = self.argv("compile", "--fqbn", fqbn, "--warnings", "default")
        if build_path:
            argv += ["--build-path", str(build_path)]
        return argv + [str(sketch_dir)]

    def upload_argv(
        self, sketch_dir: Path, fqbn: str, port: str, build_path: Optional[Path] = None
    ) -> List[str]:
        argv = self.argv("upload", "--fqbn", fqbn, "--port", port)
        if build_path:
            argv += ["--input-dir", str(build_path)]
        return argv + [str(sketch_dir)]


class Esptool:
    """The ``esptool`` engine for raw flashing of Espressif chips.

    Found on PATH (``esptool`` / ``esptool.py``), inside the esp32 Arduino
    core's bundled copy, or as a Python module -- in that order.
    """

    def __init__(self, argv_prefix: Optional[List[str]] = None):
        self._prefix = argv_prefix

    @property
    def argv_prefix(self) -> Optional[List[str]]:
        if self._prefix is None:
            self._prefix = self.detect()
        return self._prefix

    @staticmethod
    def detect() -> Optional[List[str]]:
        for name in ("esptool", "esptool.py"):
            found = shutil.which(name)
            if found:
                return [found]
        bundled = sorted(
            (
                ArduinoCli._default_config_file().parent
                / "packages"
                / "esp32"
                / "tools"
                / "esptool_py"
            ).glob("*/esptool*")
        )
        for candidate in bundled:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return [str(candidate)]
        try:
            import esptool  # noqa: F401  (optional; never a declared dependency)
        except ImportError:
            return None
        import sys

        return [sys.executable, "-m", "esptool"]

    @property
    def is_available(self) -> bool:
        return bool(self.argv_prefix)

    def describe(self) -> Optional[str]:
        return " ".join(self.argv_prefix) if self.argv_prefix else None

    def version(self) -> Optional[str]:
        if not self.is_available:
            return None
        result = _run(self.argv_prefix + ["version"], timeout=20)
        if result.returncode != 0:
            return None
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return lines[-1] if lines else None

    def _base(self, port: str, chip: str, baud: Optional[int] = None) -> List[str]:
        if not self.is_available:
            raise ToolchainError(
                "esptool is not installed (pip install esptool, or install the esp32 core)."
            )
        argv = self.argv_prefix + ["--chip", chip, "--port", port]
        if baud:
            argv += ["--baud", str(baud)]
        return argv

    def flash_id_argv(self, port: str, chip: str = "auto") -> List[str]:
        return self._base(port, chip) + ["flash_id"]

    def probe(self, port: str, chip: str = "auto", timeout: int = 40) -> dict:
        """Identify the chip behind ``port`` (``esptool flash_id``); resets it afterwards.

        Returns the parsed fields (chip, revision, features, crystal, mac,
        flash_size, flash_manufacturer) plus ``raw`` output.
        """
        result = _run(self.flash_id_argv(port, chip), timeout=timeout)
        text = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            tail = [ln for ln in text.splitlines() if ln.strip()][-3:]
            raise ToolchainError("esptool could not talk to the chip: " + " | ".join(tail))
        return parse_esptool_probe(text)

    def chip_id_argv(self, port: str, chip: str = "auto") -> List[str]:
        return self._base(port, chip) + ["chip_id"]

    def erase_argv(self, port: str, chip: str = "auto") -> List[str]:
        return self._base(port, chip) + ["erase_flash"]

    def write_flash_argv(
        self, port: str, images: List[tuple[str, Path]], chip: str = "auto", baud: int = 460800
    ) -> List[str]:
        argv = self._base(port, chip, baud) + ["write_flash"]
        for offset, path in images:
            argv += [offset, str(path)]
        return argv


def parse_esptool_probe(text: str) -> dict:
    """Pull the identity fields out of ``esptool flash_id`` / ``chip_id`` output."""
    info: dict = {"raw": text.strip()}
    m = re.search(
        r"^Chip (?:type|is):?\s+(.+?)\s*(?:\((?:revision|rev)\s*([^)]+)\))?\s*$", text, re.M
    )
    if m:
        info["chip"] = m.group(1).strip()
        if m.group(2):
            info["revision"] = m.group(2).strip()
    m = re.search(r"^Features:\s+(.+)$", text, re.M)
    if m:
        info["features"] = [f.strip() for f in m.group(1).split(",") if f.strip()]
    m = re.search(r"^Crystal (?:frequency|is):?\s+(\S+)", text, re.M)
    if m:
        info["crystal"] = m.group(1)
    m = re.search(r"^MAC:\s+([0-9a-fA-F:]{17})", text, re.M)
    if m:
        info["mac"] = m.group(1).lower()
    m = re.search(r"^Detected flash size:\s+(\S+)", text, re.M)
    if m:
        info["flash_size"] = m.group(1)
    m = re.search(r"^Manufacturer:\s+(\S+)", text, re.M)
    if m:
        info["flash_manufacturer"] = m.group(1)
    return info


_ARDUINO: Optional[ArduinoCli] = None
_ESPTOOL: Optional[Esptool] = None


def get_arduino_cli() -> ArduinoCli:
    """Process-wide arduino-cli handle; ``reset_toolchains()`` after an install."""
    global _ARDUINO
    if _ARDUINO is None:
        _ARDUINO = ArduinoCli()
    return _ARDUINO


def get_esptool() -> Esptool:
    global _ESPTOOL
    if _ESPTOOL is None:
        _ESPTOOL = Esptool()
    return _ESPTOOL


def reset_toolchains() -> None:
    global _ARDUINO, _ESPTOOL
    _ARDUINO = None
    _ESPTOOL = None
