"""Rust for the classic ESP32: cargo builds, espflash flashes.

A sketch is a Cargo project in a part's folder whose ``firmware.json`` says
``"toolchain": "rust-esp32"``; its name is its Cargo package's, which is what
it announces (``apothecary <name>: hello``), so the Rust ``esp32_blink`` and
the Arduino one are one sketch to the Machine and the scene, two
implementations to the Bench (``esp32_blink`` and ``esp32_blink@rust-esp32``).
The project says what it builds for -- its ``rust-toolchain.toml`` names the
``esp`` toolchain, its ``.cargo/config.toml`` the ``xtensa-esp32-none-elf``
target and ``build-std`` -- so a build is ``cargo build --release`` in its
folder, and names no board.

**Offline.** ``apothecary firmware install --rust-esp32`` (``rust_installer``)
puts rustup, Espressif's Xtensa toolchain (Rust, rust-src, LLVM and GCC,
fetched and checked by apothecary itself) and espflash in the tools dir and
vendors every Rust sketch's crates, with what ``build-std`` needs, into
``vendor/`` there. Every build after that is ``cargo --offline`` with
crates.io replaced by that folder, rustup told not to install a toolchain it
lacks, and espflash told not to look for updates, so a build or a flash
reaches no host.

**No build path in the image.** rustc is told to write every folder the
build is made in -- the person's home, the repository, the tools dir, the
toolchain, the vendored crates, the build's own -- another way
(``--remap-path-prefix``), and the build's last step reads the ELF and fails
it if any of those folders is still in it (``firmware/image_paths.py``), so
no user name reaches a board.

**Its tools** are found as arduino-cli is: ``CARGO`` (or ``ESPFLASH``) naming
the one to run (``none`` for none), then the tools dir, then ``PATH``. The
tools dir's cargo runs with ``CARGO_HOME`` and ``RUSTUP_HOME`` inside it,
never ``~/.cargo`` or ``~/.rustup``; one named or found on ``PATH`` is a
person's own install and runs with their homes.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sys
import tomllib
from pathlib import Path
from typing import List, Optional, Tuple

from ...stays_local import subprocess_env
from ..models import BoardInfo, ModuleStatus, SketchInfo
from ..toolchains import ToolchainError, tools_dir
from . import Log, Plan, Tool, ToolchainModule
from .arduino import part_of, sidecar_baud, sidecar_display

RUST_ESP32 = "rust-esp32"
TOOLCHAIN = "esp"  # the name espup gives the Xtensa Rust toolchain; rust-toolchain.toml says it
# The chips this module builds for, and each one's Rust target. A RISC-V chip
# (the C3 on stable Rust) is another module's: see modules/__init__.py.
TARGETS = {"esp32": "xtensa-esp32-none-elf"}
FLASH_BAUD = 460800
VENDOR_SOURCE = "apothecary-vendored"
VENDOR_RECORD = ".apothecary-vendored.json"

# What a build's environment does not inherit: anything that would point cargo
# or rustup somewhere to fetch from, or wrap the compiler in another program.
NOT_INHERITED = (
    "CARGO_REGISTRIES_",
    "CARGO_REGISTRY_",
    "CARGO_SOURCE_",
    "CARGO_HTTP_",
    "CARGO_NET_",
    "CARGO_BUILD_RUSTC_WRAPPER",
    "CARGO_BUILD_RUSTC_WORKSPACE_WRAPPER",
    "RUSTC_WRAPPER",
    "RUSTC_WORKSPACE_WRAPPER",
    "RUSTUP_DIST_",
    "RUSTUP_UPDATE_ROOT",
    "RUSTUP_TOOLCHAIN",
    "GITHUB_TOKEN",
)


def home() -> Path:
    """Everything this module installs: ``tools_dir()/rust-esp32``."""
    return tools_dir() / RUST_ESP32


def cargo_home() -> Path:
    return home() / "cargo"


def rustup_home() -> Path:
    return home() / "rustup"


def vendor_dir() -> Path:
    return home() / "vendor"


def export_file(windows: Optional[bool] = None) -> Path:
    """espup's export file: where the Xtensa linker and LLVM are."""
    windows = platform.system() == "Windows" if windows is None else windows
    return home() / ("export-esp.ps1" if windows else "export-esp.sh")


CARGO = Tool("cargo", env="CARGO", managed=f"{RUST_ESP32}/cargo/bin/cargo", command="cargo")
ESPFLASH = Tool(
    "espflash", env="ESPFLASH", managed=f"{RUST_ESP32}/bin/espflash", command="espflash"
)


def _toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def lock_sha256(sketch: SketchInfo) -> Optional[str]:
    lock = sketch.path / "Cargo.lock"
    try:
        return hashlib.sha256(lock.read_bytes()).hexdigest()
    except OSError:
        return None


def vendored() -> dict:
    """What the last install vendored: ``{sketch id: its Cargo.lock's SHA-256}``."""
    try:
        data = json.loads((vendor_dir() / VENDOR_RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    sketches = data.get("sketches") if isinstance(data, dict) else None
    return sketches if isinstance(sketches, dict) else {}


def export_paths(text: str) -> List[str]:
    """The folders espup's export file puts before ``PATH`` (the Xtensa linker's):
    ``export PATH="<dir>:$PATH"`` in the shell's, ``$Env:PATH = "<dir>;..."`` in
    PowerShell's."""
    found: List[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("export PATH="):
            parts = line.split("=", 1)[1].strip().strip('"').split(":")
        elif line.lower().startswith("$env:path"):
            quoted = re.findall(r'"([^"]*)"', line)
            parts = [p for q in quoted for p in q.split(";")]
        else:
            continue
        for part in parts:
            if part and "$" not in part and part not in found:
                found.append(part)
    return found


def parse_board_info(text: str) -> dict:
    """The identity fields of ``espflash board-info``'s answer, as an esptool probe's are
    named: ``Chip type:  esp32 (revision v3.1)``, ``Crystal frequency: 40 MHz``,
    ``Flash size: 4MB``, ``Features: ...``, ``MAC address: aa:bb:...``."""
    info: dict = {}
    m = re.search(r"^Chip type:\s+(\S+)(?:\s+\(revision\s+([^)]+)\))?", text, re.M)
    if m:
        info["chip"] = m.group(1)
        if m.group(2):
            info["revision"] = m.group(2).strip()
    m = re.search(r"^Crystal frequency:\s+(.+?)\s*$", text, re.M)
    if m:
        info["crystal"] = m.group(1).replace(" ", "")
    m = re.search(r"^Flash size:\s+(\S+)", text, re.M)
    if m:
        info["flash_size"] = m.group(1)
    m = re.search(r"^Features:\s+(.+)$", text, re.M)
    if m:
        info["features"] = [f.strip() for f in m.group(1).split(",") if f.strip()]
    m = re.search(r"^MAC address:\s+([0-9a-fA-F:]{17})", text, re.M)
    if m:
        info["mac"] = m.group(1).lower()
    return info


class RustEsp32Module(ToolchainModule):
    id = RUST_ESP32
    label = "Rust for the ESP32"
    ring_label = "Rust ESP32"
    short = "Rust"
    languages = ("rust",)
    families = tuple(TARGETS)
    needs_board = False
    install_command = "apothecary firmware install --rust-esp32"
    can = ("build", "flash", "find ports", "listen", "probe with espflash")

    # -- sketches -----------------------------------------------------------------

    def sketch_in(self, folder: Path, meta: dict, parts_dir: Path) -> Optional[SketchInfo]:
        if meta.get("toolchain") != self.id:
            return None
        manifest = _toml(folder / "Cargo.toml")
        name = (manifest.get("package") or {}).get("name")
        if not isinstance(name, str) or not name:
            return None
        chip = meta.get("chip") if meta.get("chip") in TARGETS else next(iter(TARGETS))
        return SketchInfo(
            name=name,
            path=folder,
            toolchain=self.id,
            language="rust",
            target=chip,
            part=part_of(folder, parts_dir),
            note=meta.get("note") or None,
            baud=sidecar_baud(meta),
            display=sidecar_display(meta),
        )

    def source_files(self, sketch: SketchInfo, nested=()) -> List[Path]:
        # What cargo leaves in the project when run by hand is not a source.
        target = sketch.path / "target"
        return [f for f in super().source_files(sketch, nested) if not f.is_relative_to(target)]

    # -- tools --------------------------------------------------------------------

    def managed(self, cargo: Optional[Path]) -> bool:
        """Whether ``cargo`` is the one in the tools dir, which runs with its homes there."""
        return cargo is not None and cargo == CARGO.managed_path()

    def env(self, cargo: Optional[Path] = None) -> dict:
        cargo = cargo if cargo is not None else CARGO.detect()
        env = {
            k: v
            for k, v in subprocess_env().items()
            if not any(k.upper().startswith(p) for p in NOT_INHERITED)
        }
        # A toolchain rustup lacks is refused, never fetched; espflash asks nobody
        # whether there is a newer espflash.
        env["RUSTUP_AUTO_INSTALL"] = "0"
        env["ESPFLASH_SKIP_UPDATE_CHECK"] = "true"
        path = [str(p) for p in ([cargo.parent] if cargo else [])]
        if self.managed(cargo):
            env["CARGO_HOME"] = str(cargo_home())
            env["RUSTUP_HOME"] = str(rustup_home())
            try:
                path += export_paths(export_file().read_text(encoding="utf-8"))
            except OSError:
                pass
        env["PATH"] = os.pathsep.join([*path, env.get("PATH", "")])
        return env

    def status(self) -> ModuleStatus:
        out = self._base_status()
        from ..rust_installer import refusal

        refused = refusal()
        out.installable = refused is None
        cargo, _ = CARGO.find()
        env = self.env(cargo)
        cargo_status = self.tool_status(CARGO, [f"+{TOOLCHAIN}", "--version"], env=env)
        espflash_status = self.tool_status(ESPFLASH, ["--version"], env=env)
        out.tools = [cargo_status, espflash_status]
        if cargo_status.path is None:
            out.problems.append(f"cargo not found (run `{self.install_command}`)")
        elif not cargo_status.ok:
            out.problems.append(
                f"cargo has no `{TOOLCHAIN}` toolchain (Xtensa Rust): run `{self.install_command}`"
            )
        if espflash_status.path is None:
            out.problems.append(f"espflash not found (run `{self.install_command}`)")
        elif not espflash_status.ok:
            out.problems.append("espflash does not run")
        if cargo_status.ok and self.managed(cargo):
            done = vendored()
            from ..sketches import discover_sketches

            for sketch in discover_sketches():
                if sketch.toolchain != self.id:
                    continue
                if sketch.id not in done:
                    out.problems.append(
                        f"{sketch.id}: its crates are not vendored, so it cannot build offline "
                        f"(run `{self.install_command}`)"
                    )
                elif done[sketch.id] != lock_sha256(sketch):
                    out.problems.append(
                        f"{sketch.id}: its Cargo.lock changed since its crates were vendored "
                        f"(run `{self.install_command}`)"
                    )
        if refused and not (cargo_status.ok and espflash_status.ok):
            out.problems.append(refused)
        out.ok = cargo_status.ok and espflash_status.ok
        return out

    # -- ports: pyserial finds and listens (serial_monitor.py), espflash asks the chip

    def installed(self) -> bool:
        return CARGO.detect() is not None or ESPFLASH.detect() is not None

    def ports(self) -> Optional[List[BoardInfo]]:
        if not self.installed():
            return None
        from ..serial_monitor import list_ports

        return list_ports()

    def monitor_argv(self, port: str, baud: int) -> Optional[List[str]]:
        if not self.installed():
            return None
        from ..serial_monitor import monitor_argv

        return monitor_argv(port, baud)

    def probe_argv(self, port: str) -> Optional[List[str]]:
        espflash = ESPFLASH.detect()
        if espflash is None:
            return None
        return [
            str(espflash),
            "board-info",
            "--skip-update-check",
            "--non-interactive",
            "--port",
            port,
        ]

    def probe(self, port: str) -> Optional[dict]:
        argv = self.probe_argv(port)
        if argv is None:
            return None
        from . import run_quietly

        code, text = run_quietly(argv, env=self.env(), timeout=40)
        if code != 0:
            tail = [ln for ln in text.splitlines() if ln.strip()][-3:]
            raise ToolchainError("espflash could not talk to the chip: " + " | ".join(tail))
        return parse_board_info(text)

    def install(self, log: Log, force: bool = False) -> ModuleStatus:
        from ..rust_installer import RustEsp32Installer

        RustEsp32Installer(log=log, force=force).install()
        return self.status()

    # -- build and flash ----------------------------------------------------------

    def _cargo(self) -> Path:
        cargo = CARGO.detect()
        if cargo is None:
            raise ToolchainError(f"cargo is not installed. Run `{self.install_command}`.")
        return cargo

    def triple(self, sketch: SketchInfo) -> str:
        return TARGETS[sketch.target or next(iter(TARGETS))]

    def remaps(self, sketch: SketchInfo, out: Path) -> List[Tuple[str, str]]:
        """Each folder a build is made in, and what the image says instead. rustc
        uses the last that matches, so the most particular come last."""
        from ...projects.parts.skeleton import ROOT

        pairs = [
            (Path.home(), "/home"),
            (ROOT, "/apothecary"),
            (tools_dir(), "/tools"),
            (home(), "/tools/rust-esp32"),
            (cargo_home(), "/cargo"),
            (rustup_home(), "/rustup"),
            (vendor_dir(), "/vendor"),
            (out, "/build"),
            (sketch.path, f"/sketch/{sketch.name}"),
        ]
        seen, out_pairs = set(), []
        for folder, said in pairs:
            for form in (str(folder), str(Path(folder).resolve())):
                if form not in seen:
                    seen.add(form)
                    out_pairs.append((form, said))
        return out_pairs

    def refused(self, sketch: SketchInfo, out: Path) -> List[str]:
        """The folders the image-path check refuses: every one remapped."""
        return list(dict.fromkeys(folder for folder, _ in self.remaps(sketch, out)))

    def build_argv(self, sketch: SketchInfo, out: Path, cargo: Path) -> List[str]:
        argv = [str(cargo), "build", "--release", "--offline", "--target-dir", str(out)]
        flags = [
            f"--remap-path-prefix={folder}={said}" for folder, said in self.remaps(sketch, out)
        ]
        if any("'" in flag for flag in flags):
            raise ToolchainError("a build folder has a quote in its name; move it")
        literals = ", ".join("'" + flag + "'" for flag in flags)
        # Cargo joins a target's rustflags from every config, so these go beside the
        # project's own link arguments rather than in their place.
        argv += [
            "--config",
            # TOML literal strings: a Windows path's backslashes are what they are.
            f"target.{self.triple(sketch)}.rustflags=[{literals}]",
        ]
        vendor = vendor_dir()
        if self.managed(cargo) and vendor.is_dir():
            # crates.io is the vendored folder; a TOML literal string, so a Windows
            # path's backslashes are what they are.
            argv += [
                "--config",
                f'source.crates-io.replace-with="{VENDOR_SOURCE}"',
                "--config",
                f"source.{VENDOR_SOURCE}.directory='{vendor}'",
            ]
        return argv

    def check_argv(self, sketch: SketchInfo, out: Path) -> List[str]:
        """The build's last step: no build path in the image (firmware/image_paths.py)."""
        argv = [sys.executable, "-m", "apothecary.firmware.image_paths", str(self.elf(sketch, out))]
        for folder in self.refused(sketch, out):
            argv += ["--refuse", folder]
        return argv

    def build(self, sketch: SketchInfo, board: Optional[str], out: Path) -> Plan:
        cargo = self._cargo()
        steps = [self.build_argv(sketch, out, cargo), self.check_argv(sketch, out)]
        return Plan(steps, env=self.env(cargo), cwd=sketch.path)

    def flash(self, sketch: SketchInfo, board: Optional[str], port: str, out: Path) -> Plan:
        cargo = self._cargo()
        espflash = ESPFLASH.detect()
        if espflash is None:
            raise ToolchainError(f"espflash is not installed. Run `{self.install_command}`.")
        elf = self.elf(sketch, out)
        steps = [
            self.build_argv(sketch, out, cargo),
            self.check_argv(sketch, out),
            [
                str(espflash),
                "flash",
                "--skip-update-check",
                "--non-interactive",
                "--chip",
                sketch.target or next(iter(TARGETS)),
                "--port",
                port,
                "--baud",
                str(FLASH_BAUD),
                str(elf),
            ],
        ]
        return Plan(steps, env=self.env(cargo), cwd=sketch.path)

    def elf(self, sketch: SketchInfo, out: Path) -> Path:
        return out / self.triple(sketch) / "release" / sketch.name

    def artifact(self, sketch: SketchInfo, out: Path) -> Optional[Path]:
        elf = self.elf(sketch, out)
        return elf if elf.is_file() else None
