"""Orchestration shared by the ``apothecary firmware`` CLI and the ``/firmware`` API.

Every build and flash goes through the sketch's toolchain module
(``firmware/modules``): it names the board or takes none, and hands back the
steps, the environment and the folder they run in.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from ..projects.parts.skeleton import ROOT
from .devices import get_state, make_flash_record
from .installer import InstallSpec
from .models import FlashRecord, SketchInfo, ToolchainStatus
from .modules import Plan, get_module, module_for, modules, reset_modules
from .modules.arduino import ArduinoModule
from .toolchains import (
    ArduinoCli,
    Esptool,
    ToolchainError,
    get_arduino_cli,
)

Log = Callable[[str], None]


def toolchain_status(
    cli: Optional[ArduinoCli] = None, esptool: Optional[Esptool] = None
) -> ToolchainStatus:
    """Everything ``validate`` reports; never raises -- problems are listed.

    The top-level fields are the Arduino module's, as they always were;
    ``toolchains`` holds every module's status, Arduino's first.
    """
    arduino = ArduinoModule()
    status = arduino.legacy_status(cli, esptool)
    status.toolchains = [
        arduino.from_legacy(status) if m.id == arduino.id else m.status() for m in modules()
    ]
    return status


def install(spec: InstallSpec, log: Log) -> ToolchainStatus:
    """Install/refresh arduino-cli, then any requested cores and libraries."""
    status = ArduinoModule().install_spec(spec, log)
    reset_modules()
    return status


def install_module(module_id: str, log: Log, force: bool = False):
    """Install one toolchain module's tools; its status afterwards."""
    module = get_module(module_id)
    done = module.install(log, force=force)
    reset_modules()
    return done


def install_core(core_id: str, log: Log) -> None:
    from .installer import env_for_arduino
    from .tasks import stream

    cli = get_arduino_cli()
    env = env_for_arduino()
    _check(stream(cli.core_update_index_argv([core_id]), log, env), "core update-index")
    _check(stream(cli.core_install_argv(core_id), log, env), f"core install {core_id}")


def install_libraries(names: List[str], log: Log) -> None:
    from .installer import env_for_arduino
    from .tasks import stream

    cli = get_arduino_cli()
    _check(stream(cli.lib_install_argv(names), log, env_for_arduino()), "lib install")


def _check(rc: int, what: str) -> None:
    if rc != 0:
        raise ToolchainError(f"{what} failed (exit {rc})")


# Out-of-tree build output, so ``parts/`` never fills with object files. Not
# build/: that is setuptools' staging directory, and clearing it must not
# throw away compiled firmware.
BUILD_ROOT = ROOT / ".cache" / "firmware"


def build_dir(sketch: SketchInfo) -> Path:
    """Where a sketch is built: one folder per sketch id, so two implementations
    of one sketch never share a build."""
    return BUILD_ROOT / sketch.id


def resolve_board(sketch: SketchInfo, given: Optional[str]) -> Optional[str]:
    """The board a build of ``sketch`` names: an Arduino sketch's FQBN (the one
    given, else its default), or None for a module that builds for what the
    sketch's project names."""
    return module_for(sketch).board(sketch, given)


def build_plan(sketch: SketchInfo, board: Optional[str]) -> Plan:
    return module_for(sketch).build(sketch, board, build_dir(sketch))


def flash_plan(sketch: SketchInfo, board: Optional[str], port: str) -> Plan:
    """Build first, then write that fresh build -- never flash a stale binary."""
    return module_for(sketch).flash(sketch, board, port, build_dir(sketch))


def compile_steps(sketch: SketchInfo, fqbn: Optional[str]) -> List[List[str]]:
    return build_plan(sketch, fqbn).steps


def upload_steps(sketch: SketchInfo, fqbn: Optional[str], port: str) -> List[List[str]]:
    """Compile first, then upload the fresh build -- never flash a stale binary."""
    return flash_plan(sketch, fqbn, port).steps


def target_words(sketch: SketchInfo, board: Optional[str]) -> str:
    """What a build is for, as a title says it: ``arduino:avr:uno``, ``Rust, esp32``."""
    return module_for(sketch).target_words(sketch, board)


def compile_title(sketch: SketchInfo, board: Optional[str]) -> str:
    return f"Compile {sketch.name} ({target_words(sketch, board)})"


def upload_title(sketch: SketchInfo, port: str) -> str:
    module = module_for(sketch)
    how = "" if module.needs_board else f" ({module.short})"
    return f"Upload {sketch.name}{how} → {port}"


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
    port: str, sketch: SketchInfo, fqbn: Optional[str], task_id: Optional[str] = None
) -> FlashRecord:
    """Persist what was just put on the board so the GUI can show what *should* run."""
    record = make_flash_record(port, sketch, fqbn, build_dir(sketch), task_id=task_id)
    get_state().record_flash(record)
    return record


def record_raw_flash(port: str, images: List[str], task_id: Optional[str] = None) -> FlashRecord:
    record = make_flash_record(port, None, None, images=images, task_id=task_id)
    get_state().record_flash(record)
    return record
