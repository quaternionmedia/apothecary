"""Install Rust for the classic ESP32 into the tools dir, and vendor every Rust sketch's crates.

``apothecary firmware install --rust-esp32`` (and the Bench's toolchain card)
puts four things under ``tools_dir()/rust-esp32/``, each fetched once and kept:

1. **rustup**, from the Rust project's archive on ``static.rust-lang.org``
   (``rustup-init`` at a pinned version, checked against the ``.sha256``
   published beside it), run with ``CARGO_HOME`` and ``RUSTUP_HOME`` inside
   the tools dir -- never ``~/.cargo`` or ``~/.rustup`` -- and no toolchain
   of its own: the one it manages is the next one.
2. **espup's Xtensa toolchain**: espup itself from its GitHub release
   (checked against the SHA-256 digest GitHub publishes for the asset), run as
   ``espup install --targets esp32`` at a pinned Xtensa Rust version. It puts
   the ``esp`` toolchain (rustc, cargo, rust-src), Espressif's LLVM and the
   Xtensa GCC linker under ``RUSTUP_HOME``, and its export file -- the
   linker's folder -- beside them; its ``~/.espup`` is the tools dir's too
   (``HOME`` is pointed there for it). espup's own downloads (from
   Espressif's GitHub releases) are espup's to check; apothecary checks
   espup.
3. **espflash**, from its GitHub release, checked the same way.
4. **The crates**: ``cargo vendor`` of every Rust sketch's ``Cargo.lock``,
   with ``--sync`` of the ``esp`` toolchain's own library workspace -- what
   ``build-std`` builds ``core`` from -- into ``vendor/``, from crates.io
   (cargo checks each crate against the lockfile's checksum). From then on
   every build is ``cargo --offline`` with crates.io replaced by that folder
   (``modules/rust_esp32.py``): a build reaches no host.

The platforms are the ones Espressif publishes the Xtensa toolchain for, as
the OpenSCAD installer does it (``openscad_installer.host()``, the
machine's own architecture): Linux x86_64 and arm64, macOS on Apple Silicon,
Windows x64. An Intel Mac and Windows on ARM are refused, saying why.
What a build needs that is not fetched -- a C compiler and linker for the
build scripts that run on this machine -- is checked first, and refused with
what installs it; nothing here runs sudo.

Every fetch apothecary makes itself goes through the firmware installer's
``_fetch``, a ``tool_fetch`` to the hosts in ``stays_local.TOOL_SOURCES``;
rustup-init, espup and cargo are subprocesses, outside the socket guard,
told where to fetch from by the pinned versions and with no proxy, no
registry or source override and no GitHub token in their environment.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import stat
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .installer import _fetch
from .modules.rust_esp32 import (
    CARGO,
    RUST_ESP32,
    TOOLCHAIN,
    VENDOR_RECORD,
    RustEsp32Module,
    cargo_home,
    export_file,
    home,
    lock_sha256,
    rustup_home,
    vendor_dir,
)
from .tasks import stream
from .toolchains import ToolchainError

# Pinned: a sketch's Cargo.lock is resolved against these, and an install is
# the same install wherever it runs. Raised together, by hand.
RUSTUP_VERSION = "1.29.1"
ESPUP_VERSION = "0.17.1"
ESPFLASH_VERSION = "4.6.0"
XTENSA_RUST_VERSION = "1.99.0.0"

RUSTUP_ARCHIVE = "https://static.rust-lang.org/rustup/archive"
GITHUB_API = "https://api.github.com/repos"
GITHUB = "https://github.com"
ESPUP_REPO = "esp-rs/espup"
ESPFLASH_REPO = "esp-rs/espflash"
MANIFEST = "install.json"

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(\.\d+)?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ASSET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

Log = Callable[[str], None]
Fetch = Callable[[str], bytes]


class InstallError(ToolchainError):
    """The toolchain could not be fetched, verified or put in place here."""


# --- this machine ------------------------------------------------------------------

# (system, machine) -> the Rust host triple espup, espflash and rustup publish for.
TRIPLES = {
    ("Linux", "x86_64"): "x86_64-unknown-linux-gnu",
    ("Linux", "arm64"): "aarch64-unknown-linux-gnu",
    ("Darwin", "arm64"): "aarch64-apple-darwin",
    ("Windows", "x86_64"): "x86_64-pc-windows-msvc",
}
REFUSED = {
    ("Darwin", "x86_64"): (
        "macOS on Intel: Espressif publishes the Xtensa Rust toolchain for Apple "
        "Silicon only, so there is nothing to install on this Mac"
    ),
    ("Windows", "arm64"): (
        "Windows on ARM: espup and espflash publish no ARM64 Windows build, so "
        "there is nothing to install on this PC"
    ),
}


def _host() -> Tuple[str, str]:
    from ..openscad_installer import host

    return host()


def host_triple(system: Optional[str] = None, machine: Optional[str] = None) -> str:
    """This machine's Rust host triple, or InstallError saying why there is none."""
    if system is None or machine is None:
        here = _host()
        system, machine = system or here[0], machine or here[1]
    from ..openscad_installer import _machine_name

    key = (system, _machine_name(machine))
    if key in TRIPLES:
        return TRIPLES[key]
    if key in REFUSED:
        raise InstallError(REFUSED[key])
    raise InstallError(
        f"{system} {machine}: Espressif publishes the Xtensa Rust toolchain for Linux "
        "x86_64 and arm64, macOS on Apple Silicon and Windows x64 only"
    )


def refusal(system: Optional[str] = None, machine: Optional[str] = None) -> Optional[str]:
    """Why an install cannot go on this machine, or None."""
    try:
        host_triple(system, machine)
    except InstallError as exc:
        return f"no install here: {exc}"
    return None


def _windows(triple: str) -> bool:
    return "windows" in triple


def _exe(name: str, triple: str) -> str:
    return f"{name}.exe" if _windows(triple) else name


def check_version(text: str) -> str:
    """A version spliced into a URL is numbers and dots, or InstallError."""
    if not isinstance(text, str) or not VERSION_RE.match(text):
        raise InstallError(f"not a version: {text!r}")
    return text


def linker_problem(triple: str) -> Optional[str]:
    """What the build scripts need to link on this machine, if it is missing.

    Crates' build scripts are compiled for this machine and linked with its C
    linker: ``cc`` on Linux and macOS, the MSVC build tools on Windows.
    """
    if _windows(triple):
        root = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        vswhere = root / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
        if vswhere.is_file() or shutil.which("link.exe"):
            return None
        return (
            "no MSVC linker: install Visual Studio Build Tools with the "
            "'Desktop development with C++' workload, then install again"
        )
    if shutil.which("cc"):
        return None
    if "apple" in triple:
        return "no C compiler: run `xcode-select --install`, then install again"
    return "no C compiler (cc): `sudo apt install build-essential` adds one; then install again"


# --- fetching ------------------------------------------------------------------------


def published_sha256(text: str) -> str:
    """The SHA-256 in a ``.sha256`` file (``<hex> *./rustup-init``)."""
    first = (text.split() or [""])[0].lower()
    if not SHA256_RE.match(first):
        raise InstallError("no SHA-256 published beside the download")
    return first


def github_digest(repo: str, version: str, asset: str, fetch: Fetch) -> str:
    """The SHA-256 GitHub publishes for one asset of a tagged release."""
    if not ASSET_RE.match(asset):
        raise InstallError(f"not an asset name: {asset!r}")
    data = json.loads(
        fetch(f"{GITHUB_API}/{repo}/releases/tags/v{check_version(version)}").decode("utf-8")
    )
    for item in data.get("assets") or []:
        if item.get("name") == asset:
            digest = str(item.get("digest") or "")
            algo, _, value = digest.partition(":")
            if algo == "sha256" and SHA256_RE.match(value.lower()):
                return value.lower()
            raise InstallError(f"{repo} v{version}: no SHA-256 published for {asset}")
    raise InstallError(f"{repo} v{version} publishes no {asset}")


def verified(data: bytes, want: str, what: str, log: Log) -> bytes:
    got = hashlib.sha256(data).hexdigest()
    if got != want:
        raise InstallError(f"checksum mismatch for {what}: expected {want}, got {got}")
    log(f"SHA-256 verified ({want[:12]}…) {what}")
    return data


def _put(path: Path, data: bytes) -> Path:
    """``data`` at ``path``, executable, staged beside it and renamed into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(data)
    tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.replace(tmp, path)
    return path


def from_zip(archive: bytes, name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        member = next((m for m in zf.namelist() if Path(m).name == name), None)
        if member is None:
            raise InstallError(f"{name} not found in the archive")
        return zf.read(member)


# --- the install ---------------------------------------------------------------------


class RustEsp32Installer:
    """Drives one install: check the machine, then rustup, the Xtensa toolchain,
    espflash and the crates, each skipped when it is already in place (``force``
    fetches the tools again)."""

    def __init__(
        self,
        log: Optional[Log] = None,
        force: bool = False,
        fetch: Fetch = _fetch,
        run: Optional[Callable[..., int]] = None,
        triple: Optional[str] = None,
    ):
        self.log = log or (lambda _line: None)
        self.force = force
        self.fetch = fetch
        self.run = run or (lambda argv, env=None, cwd=None: stream(argv, self.log, env, cwd))
        self._triple = triple
        self.module = RustEsp32Module()

    @property
    def triple(self) -> str:
        if self._triple is None:
            self._triple = host_triple()
        return self._triple

    # where things go
    def bin(self, name: str) -> Path:
        return home() / "bin" / _exe(name, self.triple)

    def cargo_bin(self, name: str) -> Path:
        return cargo_home() / "bin" / _exe(name, self.triple)

    def env(self) -> Dict[str, str]:
        """The installers' environment: the build's (no fetch redirects, no wrapper,
        homes in the tools dir), espup's ``~/.espup`` in the tools dir too."""
        env = self.module.env(cargo=CARGO.managed_path())
        env["CARGO_HOME"] = str(cargo_home())
        env["RUSTUP_HOME"] = str(rustup_home())
        env["RUSTUP_INIT_SKIP_PATH_CHECK"] = "yes"
        env["PATH"] = os.pathsep.join([str(cargo_home() / "bin"), env.get("PATH", "")])
        return env

    def _check(self, rc: int, what: str) -> None:
        if rc != 0:
            raise InstallError(f"{what} failed (exit {rc})")

    def manifest(self) -> dict:
        try:
            data = json.loads((home() / MANIFEST).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_manifest(self, record: dict) -> None:
        home().mkdir(parents=True, exist_ok=True)
        path = home() / MANIFEST
        tmp = path.with_name(f".{MANIFEST}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, path)

    def install(self) -> dict:
        triple = self.triple  # refuses an unserved platform before anything is fetched
        problem = linker_problem(triple)
        if problem:
            raise InstallError(problem)
        self.log(f"Rust for the ESP32 into {home()} ({triple})")
        record = {**self.manifest(), "triple": triple}
        record["rustup"] = self.install_rustup(record.get("rustup"))
        record["xtensa_rust"] = self.install_toolchain(record.get("xtensa_rust"))
        record["espflash"] = self.install_espflash(record.get("espflash"))
        record["vendored"] = self.vendor()
        record["installed_at"] = datetime.now(timezone.utc).isoformat()
        self._write_manifest(record)
        self.log("Rust for the ESP32: installed")
        return record

    # 1. rustup
    def install_rustup(self, had: Optional[dict]) -> dict:
        rustup = self.cargo_bin("rustup")
        if rustup.is_file() and not self.force:
            self.log(f"rustup already installed at {rustup}; use force to reinstall")
            return had or {"version": RUSTUP_VERSION}
        name = _exe("rustup-init", self.triple)
        url = f"{RUSTUP_ARCHIVE}/{check_version(RUSTUP_VERSION)}/{self.triple}/{name}"
        self.log(f"Downloading {url}")
        data = self.fetch(url)
        want = published_sha256(self.fetch(url + ".sha256").decode("utf-8"))
        init = _put(home() / "downloads" / name, verified(data, want, name, self.log))
        self._check(
            self.run(
                [
                    str(init),
                    "-y",
                    "--no-modify-path",
                    "--default-toolchain",
                    "none",
                    "--profile",
                    "minimal",
                ],
                env=self.env(),
            ),
            "rustup-init",
        )
        return {"version": RUSTUP_VERSION, "sha256": want}

    # 2. espup, and the Xtensa toolchain it installs
    def install_toolchain(self, had: Optional[dict]) -> dict:
        rustc = rustup_home() / "toolchains" / TOOLCHAIN / "bin" / _exe("rustc", self.triple)
        same = bool(had) and had.get("version") == XTENSA_RUST_VERSION
        if rustc.is_file() and same and not self.force:
            self.log(f"Xtensa Rust {XTENSA_RUST_VERSION} already installed ({rustc.parent.parent})")
            return had
        espup = self.fetch_release_binary(
            ESPUP_REPO, ESPUP_VERSION, _exe(f"espup-{self.triple}", self.triple), "espup"
        )
        env = self.env()
        # espup keeps a link to its LLVM in ~/.espup: the tools dir's, not the person's.
        env["HOME"] = str(home() / "home")
        (home() / "home").mkdir(parents=True, exist_ok=True)
        self._check(
            self.run(
                [
                    str(espup),
                    "install",
                    "--targets",
                    "esp32",
                    "--name",
                    TOOLCHAIN,
                    "--toolchain-version",
                    check_version(XTENSA_RUST_VERSION),
                    "--export-file",
                    str(export_file(_windows(self.triple))),
                ],
                env=env,
            ),
            "espup install",
        )
        rustup = self.cargo_bin("rustup")
        # The toolchain rustup hands a bare `cargo` from the tools dir: nothing to fetch.
        self._check(self.run([str(rustup), "default", TOOLCHAIN], env=self.env()), "rustup default")
        return {"version": XTENSA_RUST_VERSION, "espup": ESPUP_VERSION}

    def fetch_release_binary(self, repo: str, version: str, asset: str, name: str) -> Path:
        """A release asset that is the binary itself, verified, at ``bin/<name>``."""
        url = f"{GITHUB}/{repo}/releases/download/v{check_version(version)}/{asset}"
        want = github_digest(repo, version, asset, self.fetch)
        self.log(f"Downloading {url}")
        return _put(self.bin(name), verified(self.fetch(url), want, asset, self.log))

    # 3. espflash
    def install_espflash(self, had: Optional[dict]) -> dict:
        target = self.bin("espflash")
        same = bool(had) and had.get("version") == ESPFLASH_VERSION
        if target.is_file() and same and not self.force:
            self.log(f"espflash {ESPFLASH_VERSION} already installed at {target}")
            return had
        asset = f"espflash-{self.triple}.zip"
        url = (
            f"{GITHUB}/{ESPFLASH_REPO}/releases/download/v{check_version(ESPFLASH_VERSION)}/{asset}"
        )
        want = github_digest(ESPFLASH_REPO, ESPFLASH_VERSION, asset, self.fetch)
        self.log(f"Downloading {url}")
        archive = verified(self.fetch(url), want, asset, self.log)
        _put(target, from_zip(archive, _exe("espflash", self.triple)))
        self.log(f"Installed {target}")
        return {"version": ESPFLASH_VERSION, "sha256": want}

    # 4. the crates
    def sysroot(self) -> Path:
        rustc = self.cargo_bin("rustc")
        from .modules import run_quietly

        code, text = run_quietly(
            [str(rustc), f"+{TOOLCHAIN}", "--print", "sysroot"], env=self.env(), cwd=home()
        )
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if code != 0 or not lines:
            raise InstallError(f"rustc +{TOOLCHAIN} --print sysroot failed: {text[-300:]}")
        return Path(lines[-1])

    def library_manifest(self) -> Path:
        """The ``esp`` toolchain's own library workspace, what build-std builds core from."""
        manifest = self.sysroot() / "lib" / "rustlib" / "src" / "rust" / "library" / "Cargo.toml"
        if not manifest.is_file():
            raise InstallError(f"no rust-src in the {TOOLCHAIN} toolchain: {manifest} is missing")
        return manifest

    def vendor(self) -> List[str]:
        from .sketches import discover_sketches

        sketches = [s for s in discover_sketches() if s.toolchain == RUST_ESP32]
        if not sketches:
            self.log("No Rust sketches under parts/: nothing to vendor")
            return []
        missing = [s.id for s in sketches if lock_sha256(s) is None]
        if missing:
            raise InstallError(
                "no Cargo.lock for " + ", ".join(missing) + ": a sketch's crates are vendored "
                "from its lockfile, so its versions are the ones written down"
            )
        cargo = self.cargo_bin("cargo")
        library = self.library_manifest()
        manifests = [s.path / "Cargo.toml" for s in sketches]
        staged = home() / ".vendor.new"
        if staged.exists():
            shutil.rmtree(staged)
        argv = [str(cargo), f"+{TOOLCHAIN}", "vendor", "--versioned-dirs", "--locked"]
        argv += ["--manifest-path", str(manifests[0])]
        for extra in [*manifests[1:], library]:
            argv += ["--sync", str(extra)]
        argv.append(str(staged))
        self.log(f"Vendoring the crates of {', '.join(s.id for s in sketches)} and build-std's")
        self._check(self.run(argv, env=self.env(), cwd=home()), "cargo vendor")
        record = {
            "sketches": {s.id: lock_sha256(s) for s in sketches},
            "toolchain": XTENSA_RUST_VERSION,
        }
        (staged / VENDOR_RECORD).write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        old = home() / ".vendor.old"
        if old.exists():
            shutil.rmtree(old)
        if vendor_dir().exists():
            os.replace(vendor_dir(), old)
        os.replace(staged, vendor_dir())
        if old.exists():
            shutil.rmtree(old)
        self.log(f"Vendored into {vendor_dir()}: every build from here on is offline")
        return [s.id for s in sketches]


def what_install_does() -> str:
    """This machine, and what ``firmware install --rust-esp32`` does on it."""
    try:
        triple = host_triple()
    except InstallError as exc:
        return str(exc)
    return (
        f"{triple}: rustup {RUSTUP_VERSION}, espup {ESPUP_VERSION}'s Xtensa Rust "
        f"{XTENSA_RUST_VERSION} and espflash {ESPFLASH_VERSION} into {home()}, and every "
        "Rust sketch's crates vendored beside them"
    )
