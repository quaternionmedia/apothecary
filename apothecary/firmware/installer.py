"""Install ``arduino-cli`` from Arduino's GitHub releases into the tools dir.

Downloads the platform archive for a pinned or the latest release, verifies
it against the release's published SHA-256 checksums, extracts the single
binary, and checks that it runs. Stdlib only -- ``urllib``, ``hashlib``,
``tarfile``/``zipfile`` -- so the installer works in a bare environment.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import stat
import tarfile
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from .toolchains import ArduinoCli, ToolchainError, _exe, tools_dir

RELEASES_API = "https://api.github.com/repos/arduino/arduino-cli/releases"
RELEASES_DOWNLOAD = "https://github.com/arduino/arduino-cli/releases/download"

Log = Callable[[str], None]


@dataclass
class InstallSpec:
    version: str = "latest"  # "latest" or e.g. "1.5.1"
    force: bool = False
    cores: List[str] = field(default_factory=list)
    libraries: List[str] = field(default_factory=list)
    dest: Optional[Path] = None


def asset_name(version: str, system: Optional[str] = None, machine: Optional[str] = None) -> str:
    """The release asset for this platform, e.g. ``arduino-cli_1.5.1_Linux_64bit.tar.gz``."""
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()
    if system == "Linux":
        os_name, ext = "Linux", "tar.gz"
        arch = {
            "x86_64": "64bit",
            "amd64": "64bit",
            "i386": "32bit",
            "i686": "32bit",
            "aarch64": "ARM64",
            "arm64": "ARM64",
            "armv7l": "ARMv7",
            "armv6l": "ARMv6",
        }.get(machine)
    elif system == "Darwin":
        os_name, ext = "macOS", "tar.gz"
        arch = {"x86_64": "64bit", "arm64": "ARM64"}.get(machine)
    elif system == "Windows":
        os_name, ext = "Windows", "zip"
        arch = {"amd64": "64bit", "x86_64": "64bit", "x86": "32bit", "i386": "32bit"}.get(machine)
    else:
        raise ToolchainError(f"no arduino-cli release for {system}")
    if not arch:
        raise ToolchainError(f"no arduino-cli release for {system}/{machine}")
    return f"arduino-cli_{version}_{os_name}_{arch}.{ext}"


def _fetch(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "apothecary-firmware-installer"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https host
        return resp.read()


def resolve_version(version: str = "latest", fetch: Callable[[str], bytes] = _fetch) -> str:
    """Turn ``latest`` into a concrete ``X.Y.Z`` via the releases API."""
    if version != "latest":
        return version.lstrip("v")
    data = json.loads(fetch(f"{RELEASES_API}/latest").decode("utf-8"))
    tag = data.get("tag_name", "")
    if not tag:
        raise ToolchainError("could not resolve latest arduino-cli release")
    return tag.lstrip("v")


def expected_checksum(version: str, name: str, fetch: Callable[[str], bytes] = _fetch) -> str:
    text = fetch(f"{RELEASES_DOWNLOAD}/v{version}/{version}-checksums.txt").decode("utf-8")
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == name:
            return parts[0].lower()
    raise ToolchainError(f"no checksum published for {name}")


def extract_binary(archive: bytes, name: str, dest_dir: Path) -> Path:
    """Pull just the ``arduino-cli`` executable out of the release archive."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    exe = _exe("arduino-cli")
    target = dest_dir / exe
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            member = next((m for m in zf.namelist() if Path(m).name == exe), None)
            if member is None:
                raise ToolchainError(f"{exe} not found in {name}")
            target.write_bytes(zf.read(member))
    else:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tf:
            member = next(
                (m for m in tf.getmembers() if Path(m.name).name == exe and m.isfile()), None
            )
            if member is None:
                raise ToolchainError(f"{exe} not found in {name}")
            extracted = tf.extractfile(member)
            assert extracted is not None
            target.write_bytes(extracted.read())
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return target


class ArduinoCliInstaller:
    """Drives one install: resolve → download → verify → extract → smoke-test."""

    def __init__(
        self, spec: InstallSpec, log: Optional[Log] = None, fetch: Callable[[str], bytes] = _fetch
    ):
        self.spec = spec
        self.log = log or (lambda _line: None)
        self.fetch = fetch
        self.dest_dir = spec.dest or tools_dir() / "arduino-cli"

    @property
    def binary(self) -> Path:
        return self.dest_dir / _exe("arduino-cli")

    def install_binary(self) -> Path:
        existing = ArduinoCli(self.binary) if self.binary.is_file() else None
        if existing and not self.spec.force:
            self.log(
                f"arduino-cli already installed at {self.binary} "
                f"(version {existing.version()}); use --force to reinstall"
            )
            return self.binary

        version = resolve_version(self.spec.version, self.fetch)
        name = asset_name(version)
        url = f"{RELEASES_DOWNLOAD}/v{version}/{name}"
        self.log(f"Downloading {url}")
        archive = self.fetch(url)

        want = expected_checksum(version, name, self.fetch)
        got = hashlib.sha256(archive).hexdigest()
        if got != want:
            raise ToolchainError(f"checksum mismatch for {name}: expected {want}, got {got}")
        self.log(f"SHA-256 verified ({want[:12]}…)")

        path = extract_binary(archive, name, self.dest_dir)
        self.log(f"Installed {path}")

        cli = ArduinoCli(path)
        reported = cli.version()
        if not reported:
            raise ToolchainError(f"{path} was installed but does not run")
        self.log(f"arduino-cli {reported} OK")
        return path


def default_config_exists() -> bool:
    return ArduinoCli._default_config_file().is_file()


def env_for_arduino() -> dict:
    """Environment for arduino-cli subprocesses.

    Keeps ``HOME`` authoritative so arduino-cli's data dir (``~/.arduino15``)
    does not land in a sandboxed editor's per-revision XDG tree.
    """
    env = os.environ.copy()
    env.setdefault("HOME", str(Path.home()))
    return env
