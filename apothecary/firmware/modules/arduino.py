"""The Arduino module: arduino-cli builds and uploads, esptool flashes raw images.

What the seam was before there were modules, moved behind the interface and
otherwise unchanged: a sketch is ``<folder>/<folder>.ino`` with an optional
``firmware.json``; a build names a board (its FQBN); an upload compiles first
and uploads that build; arduino-cli always runs with the managed config
(``toolchains.managed_config_file``) in ``env_for_arduino()``.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pydantic import ValidationError

from ..installer import ArduinoCliInstaller, InstallSpec, env_for_arduino
from ..models import ARDUINO, DisplaySpec, ModuleStatus, SketchInfo, ToolchainStatus, ToolStatus
from ..tasks import stream
from ..toolchains import (
    ArduinoCli,
    Esptool,
    ToolchainError,
    get_arduino_cli,
    get_esptool,
    reset_toolchains,
    tools_dir,
)
from . import Log, Plan, ToolchainModule

DEFAULT_BAUD = 115200


def sidecar_display(meta: dict) -> Optional[DisplaySpec]:
    """A malformed ``display`` is dropped, like any other bad sidecar value."""
    raw = meta.get("display")
    if not isinstance(raw, dict):
        return None
    try:
        return DisplaySpec(**raw)
    except ValidationError:
        return None


def sidecar_baud(meta: dict) -> int:
    raw = meta.get("baud")
    return raw if isinstance(raw, int) and 300 <= raw <= 2_000_000 else DEFAULT_BAUD


def part_of(folder: Path, parts_dir: Path) -> Optional[str]:
    rel = folder.relative_to(parts_dir)
    return rel.parts[0] if rel.parts else None


def _check(rc: int, what: str) -> None:
    if rc != 0:
        raise ToolchainError(f"{what} failed (exit {rc})")


class ArduinoModule(ToolchainModule):
    id = ARDUINO
    label = "Arduino"
    short = "Arduino"
    languages = ("arduino",)
    # The families the suggested cores build for; any core arduino-cli installs adds its own.
    families = ("avr", "esp32", "esp8266", "rp2040", "samd")
    needs_board = True
    install_command = "apothecary firmware install"

    # -- sketches -----------------------------------------------------------------

    def sketch_in(self, folder: Path, meta: dict, parts_dir: Path) -> Optional[SketchInfo]:
        if meta.get("toolchain", ARDUINO) != ARDUINO:
            return None
        ino = folder / f"{folder.name}.ino"
        if not ino.is_file():
            return None
        return SketchInfo(
            name=folder.name,
            path=folder,
            ino=ino,
            toolchain=ARDUINO,
            language="arduino",
            part=part_of(folder, parts_dir),
            fqbn=meta.get("fqbn") or None,
            cores=[str(c) for c in meta.get("cores", [])],
            libraries=[str(lib) for lib in meta.get("libraries", [])],
            note=meta.get("note") or None,
            baud=sidecar_baud(meta),
            display=sidecar_display(meta),
        )

    # -- tools --------------------------------------------------------------------

    def legacy_status(
        self, cli: Optional[ArduinoCli] = None, esptool: Optional[Esptool] = None
    ) -> ToolchainStatus:
        """Everything ``validate`` reports of arduino-cli and esptool, in the shape
        ``GET /firmware/status`` has always had; never raises."""
        cli = cli or get_arduino_cli()
        esptool = esptool or get_esptool()
        status = ToolchainStatus(tools_dir=str(tools_dir()))

        if cli.is_available:
            status.arduino_cli_path = str(cli.path)
            try:
                status.arduino_cli_version = cli.version()
                status.arduino_cli_ok = bool(status.arduino_cli_version)
            except ToolchainError as exc:
                status.problems.append(f"arduino-cli does not run: {exc}")
            if status.arduino_cli_ok:
                status.config_file = str(cli.config_file)
                try:
                    status.cores = cli.core_list()
                except ToolchainError as exc:
                    status.problems.append(f"could not list cores: {exc}")
                if not any(c.installed for c in status.cores):
                    status.problems.append(
                        "no board cores installed -- nothing can be compiled yet"
                    )
        else:
            status.problems.append("arduino-cli not found (run `apothecary firmware install`)")

        if esptool.is_available:
            status.esptool_path = esptool.describe()
            status.esptool_version = esptool.version()
            status.esptool_ok = bool(status.esptool_version)
        else:
            status.problems.append(
                "esptool not found -- raw ESP binary flashing unavailable "
                "(arduino-cli uploads to ESP32 still work once the esp32 core is installed)"
            )
        return status

    def from_legacy(self, legacy: ToolchainStatus) -> ModuleStatus:
        out = self._base_status()
        out.ok = legacy.arduino_cli_ok
        out.tools = [
            ToolStatus(
                name="arduino-cli",
                path=legacy.arduino_cli_path,
                version=legacy.arduino_cli_version,
                ok=legacy.arduino_cli_ok,
            ),
            ToolStatus(
                name="esptool",
                path=legacy.esptool_path,
                version=legacy.esptool_version,
                ok=legacy.esptool_ok,
            ),
        ]
        out.problems = list(legacy.problems)
        return out

    def status(self) -> ModuleStatus:
        return self.from_legacy(self.legacy_status())

    def install(
        self, log: Log, force: bool = False, spec: Optional[InstallSpec] = None
    ) -> ModuleStatus:
        self.install_spec(spec or InstallSpec(force=force), log)
        return self.status()

    def install_spec(self, spec: InstallSpec, log: Log) -> ToolchainStatus:
        """Install or refresh arduino-cli, then any requested cores and libraries."""
        ArduinoCliInstaller(spec, log=log).install_binary()
        reset_toolchains()
        cli = get_arduino_cli()
        env = env_for_arduino()
        if spec.cores:
            _check(stream(cli.core_update_index_argv(spec.cores), log, env), "core update-index")
            for core in spec.cores:
                _check(stream(cli.core_install_argv(core), log, env), f"core install {core}")
        if spec.libraries:
            _check(stream(cli.lib_install_argv(spec.libraries), log, env), "lib install")
        return self.legacy_status(cli)

    def env(self) -> dict:
        return env_for_arduino()

    # -- build and flash ----------------------------------------------------------

    def board(self, sketch: SketchInfo, given: Optional[str]) -> Optional[str]:
        chosen = given or sketch.fqbn
        if not chosen:
            raise ToolchainError(
                f"no FQBN for sketch '{sketch.name}': pass --fqbn, "
                f'or set "fqbn" in {sketch.path / "firmware.json"}'
            )
        return chosen

    def target_words(self, sketch: SketchInfo, board: Optional[str]) -> str:
        return board or ""

    def build(self, sketch: SketchInfo, board: Optional[str], out: Path) -> Plan:
        cli = get_arduino_cli()
        return Plan([cli.compile_argv(sketch.path, board, out)], env=self.env())

    def flash(self, sketch: SketchInfo, board: Optional[str], port: str, out: Path) -> Plan:
        cli = get_arduino_cli()
        steps: List[List[str]] = [
            cli.compile_argv(sketch.path, board, out),
            cli.upload_argv(sketch.path, board, port, out),
        ]
        return Plan(steps, env=self.env())

    def artifact(self, sketch: SketchInfo, out: Path) -> Optional[Path]:
        candidate = out / f"{sketch.name}.ino.bin"
        if candidate.is_file():
            return candidate
        hexfile = out / f"{sketch.name}.ino.hex"  # AVR
        return hexfile if hexfile.is_file() else None
