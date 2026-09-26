"""Orchestration shared by the ``apothecary firmware`` CLI and the ``/firmware`` API."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from ..projects.parts.skeleton import ROOT
from .devices import get_state, make_flash_record
from .installer import ArduinoCliInstaller, InstallSpec, env_for_arduino
from .models import FlashRecord, SketchInfo, ToolchainStatus
from .tasks import stream
from .toolchains import (
    ArduinoCli,
    Esptool,
    ToolchainError,
    get_arduino_cli,
    get_esptool,
    reset_toolchains,
    tools_dir,
)

Log = Callable[[str], None]


def toolchain_status(
    cli: Optional[ArduinoCli] = None, esptool: Optional[Esptool] = None
) -> ToolchainStatus:
    """Everything ``validate`` reports; never raises -- problems are listed."""
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
            cfg = cli.config_path()
            status.config_file = str(cfg) if cfg else None
            try:
                status.cores = cli.core_list()
            except ToolchainError as exc:
                status.problems.append(f"could not list cores: {exc}")
            if not any(c.installed for c in status.cores):
                status.problems.append("no board cores installed -- nothing can be compiled yet")
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


def _check(rc: int, what: str) -> None:
    if rc != 0:
        raise ToolchainError(f"{what} failed (exit {rc})")


def install(spec: InstallSpec, log: Log) -> ToolchainStatus:
    """Install/refresh arduino-cli, then any requested cores and libraries."""
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
    return toolchain_status(cli)


def install_core(core_id: str, log: Log) -> None:
    cli = get_arduino_cli()
    env = env_for_arduino()
    _check(stream(cli.core_update_index_argv([core_id]), log, env), "core update-index")
    _check(stream(cli.core_install_argv(core_id), log, env), f"core install {core_id}")


def install_libraries(names: List[str], log: Log) -> None:
    cli = get_arduino_cli()
    _check(stream(cli.lib_install_argv(names), log, env_for_arduino()), "lib install")


# Out-of-tree build output, so ``parts/`` never fills with object files.
BUILD_ROOT = ROOT / "build" / "firmware"


def build_dir(sketch: SketchInfo) -> Path:
    return BUILD_ROOT / sketch.name


def compile_steps(sketch: SketchInfo, fqbn: str) -> List[List[str]]:
    cli = get_arduino_cli()
    return [cli.compile_argv(sketch.path, fqbn, build_dir(sketch))]


def upload_steps(sketch: SketchInfo, fqbn: str, port: str) -> List[List[str]]:
    """Compile first, then upload the fresh build -- never flash a stale binary."""
    cli = get_arduino_cli()
    out = build_dir(sketch)
    return [cli.compile_argv(sketch.path, fqbn, out), cli.upload_argv(sketch.path, fqbn, port, out)]


def resolve_fqbn(sketch: SketchInfo, fqbn: Optional[str]) -> str:
    chosen = fqbn or sketch.fqbn
    if not chosen:
        raise ToolchainError(
            f"no FQBN for sketch '{sketch.name}': pass --fqbn, "
            f'or set "fqbn" in {sketch.path / "firmware.json"}'
        )
    return chosen


def resolve_port(port: Optional[str]) -> str:
    """Use the given port, or the single detected board's port; refuse to guess."""
    if port:
        return port
    boards = get_arduino_cli().board_list()
    if len(boards) == 1:
        return boards[0].port
    if not boards:
        raise ToolchainError("no boards detected -- plug one in or pass --port")
    raise ToolchainError(
        "several boards detected -- pass --port: " + ", ".join(b.port for b in boards)
    )


def resolve_image_path(path: str, root: Path = ROOT) -> Path:
    """A flash image path from the API, confined to the repository tree."""
    candidate = (root / path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ToolchainError(f"image path must be inside the repository: {path}") from exc
    if not candidate.is_file():
        raise ToolchainError(f"image not found: {path}")
    return candidate


def record_upload(
    port: str, sketch: SketchInfo, fqbn: str, task_id: Optional[str] = None
) -> FlashRecord:
    """Persist what was just put on the board so the GUI can show what *should* run."""
    record = make_flash_record(port, sketch, fqbn, build_dir(sketch), task_id=task_id)
    get_state().record_flash(record)
    return record


def record_raw_flash(port: str, images: List[str], task_id: Optional[str] = None) -> FlashRecord:
    record = make_flash_record(port, None, None, images=images, task_id=task_id)
    get_state().record_flash(record)
    return record
