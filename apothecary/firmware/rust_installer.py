"""Install Rust for the classic ESP32 into the tools dir, and vendor every Rust sketch's crates.

``apothecary firmware install --rust-esp32`` (and the Bench's toolchain card)
puts these under ``tools_dir()/rust-esp32/``, each fetched once, checked and
kept:

1. **rustup**, from the Rust project's archive on ``static.rust-lang.org``
   (``rustup-init`` at a pinned version, checked against the ``.sha256``
   published beside it), run with ``CARGO_HOME`` and ``RUSTUP_HOME`` inside
   the tools dir -- never ``~/.cargo`` or ``~/.rustup`` -- and no toolchain
   of its own: the one it manages is the next one.
2. **The Xtensa toolchain**, four archives from where Espressif publishes
   them, each checked before it is opened, laid out as espup lays them out,
   and linked into the tools dir's rustup as the ``esp`` toolchain
   (``rustup toolchain link``):

   | Archive | From | Checked against |
   |---|---|---|
   | Xtensa Rust (rustc, cargo, the host's std) | esp-rs/rust-build's GitHub release ``v<XTENSA_RUST_VERSION>`` | the SHA-256 GitHub publishes for the asset (rust-build publishes no checksum file) |
   | rust-src (what build-std builds core from) | the same release | the same |
   | LLVM's libraries (libclang, for bindgen; a no_std build does not use them) | espressif/llvm-project's release ``<LLVM_VERSION>`` | the release's own ``libs-clang-<version>-checksum.sha256`` |
   | GCC, the Xtensa linker | espressif/crosstool-NG's release ``esp-<GCC_VERSION>`` | the release's own ``crosstool-NG-esp-<version>-checksum.sha256`` |

   The Rust archives are rust-installer dist tarballs: their components are
   copied as each component's ``manifest.in`` lists them, as their
   ``install.sh`` would, in Python, so no downloaded script is run. On Windows
   the Rust archive is one zip with rust-src inside, unpacked as espup unpacks
   it. The export file -- the linker's folder and LIBCLANG_PATH -- is written
   beside them, as espup writes it, and nothing outside the tools dir is
   touched: no ``~/.espup``, no variable set for the user.
3. **espflash**, from its GitHub release, checked against the SHA-256 GitHub
   publishes for the asset.
4. **The crates**: ``cargo vendor`` of every Rust sketch's ``Cargo.lock``,
   with ``--sync`` of the ``esp`` toolchain's own library workspace -- what
   ``build-std`` builds ``core`` from -- into ``vendor/``, from crates.io
   (cargo checks each crate against the lockfile's checksum). From then on
   every build is ``cargo --offline`` with crates.io replaced by that folder
   (``modules/rust_esp32.py``): a build reaches no host.

**The pins move by hand.** Every version below is pinned, and moves only in a
commit that bumps it -- one or several together -- and that commit re-runs a
real install and a real offline build of every Rust sketch in a scratch tools
dir and says what they did in its body (the hosts they reached, the build's
result). A sketch's ``Cargo.lock`` is resolved against the toolchain pinned
here, so a bump of the Xtensa Rust version is a bump of the lockfiles too,
when they need it. (The owner's decision of 2026-10-10,
docs/plans/rust-2026-10-08.md.)

The platforms are the ones Espressif publishes the Xtensa toolchain for, as
the OpenSCAD installer does it (``openscad_installer.host()``, the
machine's own architecture): Linux x86_64 and arm64, macOS on Apple Silicon,
Windows x64. An Intel Mac and Windows on ARM are refused, saying why.
What a build needs that is not fetched -- a C compiler and linker for the
build scripts that run on this machine -- is checked first, and refused with
what installs it; nothing here runs sudo.

Every fetch apothecary makes goes through the firmware installer's tool
fetch (``_fetch``, ``_fetch_to``) to the hosts in ``stays_local.TOOL_SOURCES``;
rustup-init and cargo are subprocesses, outside the socket guard, told where
to fetch from by the pinned versions and with no proxy, no registry or
source override and no GitHub token in their environment.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import stat
import tarfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .installer import _fetch, _fetch_to
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
# the same install wherever it runs. They move only by hand, in a commit that
# re-runs a real install and an offline build and says so (the docstring).
RUSTUP_VERSION = "1.29.1"  # static.rust-lang.org/rustup/archive/<this>/
ESPFLASH_VERSION = "4.6.0"  # esp-rs/espflash release v<this>
XTENSA_RUST_VERSION = "1.99.0.0"  # esp-rs/rust-build release v<this>
# The LLVM and GCC espup 0.17.1 pairs with Xtensa Rust 1.99 (its llvm.rs and gcc.rs).
LLVM_VERSION = "esp-20.1.1_20250829"  # espressif/llvm-project release <this>
GCC_VERSION = "15.2.0_20250920"  # espressif/crosstool-NG release esp-<this>

RUSTUP_ARCHIVE = "https://static.rust-lang.org/rustup/archive"
GITHUB_API = "https://api.github.com/repos"
GITHUB = "https://github.com"
ESPFLASH_REPO = "esp-rs/espflash"
RUST_BUILD_REPO = "esp-rs/rust-build"
LLVM_REPO = "espressif/llvm-project"
GCC_REPO = "espressif/crosstool-NG"
CLANG_NAME = "xtensa-esp32-elf-clang"  # espup's names for where LLVM and GCC go
XTENSA_GCC = "xtensa-esp-elf"
MANIFEST = "install.json"

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(\.\d+)?$")
ESP_VERSION_RE = re.compile(r"^(esp-)?\d+\.\d+\.\d+_\d{8}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ASSET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

Log = Callable[[str], None]
Fetch = Callable[[str], bytes]


class InstallError(ToolchainError):
    """The toolchain could not be fetched, verified or put in place here."""


# --- this machine ------------------------------------------------------------------

# (system, machine) -> the Rust host triple rust-build, espflash and rustup publish for.
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
        "Windows on ARM: Espressif publishes no ARM64 Windows Xtensa Rust, nor espflash a build, so "
        "there is nothing to install on this PC"
    ),
}


# Espressif's name for each host, in its LLVM and GCC archives.
ESPRESSIF_ARCHES = {
    "x86_64-unknown-linux-gnu": "x86_64-linux-gnu",
    "aarch64-unknown-linux-gnu": "aarch64-linux-gnu",
    "aarch64-apple-darwin": "aarch64-apple-darwin",
    "x86_64-pc-windows-msvc": "x86_64-w64-mingw32",
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


def check_esp_version(text: str) -> str:
    """An Espressif release (``esp-20.1.1_20250829``, ``15.2.0_20250920``), or InstallError."""
    if not isinstance(text, str) or not ESP_VERSION_RE.match(text):
        raise InstallError(f"not an Espressif release: {text!r}")
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


def listed_sha256(text: str, name: str) -> str:
    """The SHA-256 a checksum file lists for ``name`` (``<hex> *<name>`` lines;
    ``#`` lines are comments), or InstallError."""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and not line.startswith("#") and parts[1].lstrip("*") == name:
            if SHA256_RE.match(parts[0].lower()):
                return parts[0].lower()
    raise InstallError(f"no SHA-256 listed for {name}")


def github_digest(
    repo: str, version: str, asset: str, fetch: Fetch, tag: Optional[str] = None
) -> str:
    """The SHA-256 GitHub publishes for one asset of a tagged release (``v<version>``,
    or ``tag`` as given)."""
    if not ASSET_RE.match(asset):
        raise InstallError(f"not an asset name: {asset!r}")
    tag = tag if tag is not None else f"v{check_version(version)}"
    if not ASSET_RE.match(tag):
        raise InstallError(f"not a release tag: {tag!r}")
    data = json.loads(fetch(f"{GITHUB_API}/{repo}/releases/tags/{tag}").decode("utf-8"))
    for item in data.get("assets") or []:
        if item.get("name") == asset:
            digest = str(item.get("digest") or "")
            algo, _, value = digest.partition(":")
            if algo == "sha256" and SHA256_RE.match(value.lower()):
                return value.lower()
            raise InstallError(f"{repo} {tag}: no SHA-256 published for {asset}")
    raise InstallError(f"{repo} {tag} publishes no {asset}")


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


@dataclass(frozen=True)
class Archive:
    """One archive of the Xtensa toolchain: where it is, and what checks it."""

    part: str  # rust, rust-src, llvm, gcc
    name: str  # the release asset's file name
    base: str  # the release's download URL, the folder the asset is in
    github: Optional[Tuple[str, str]] = None  # (repo, tag): GitHub's published digest
    checksums: Optional[str] = None  # a checksum file the release itself publishes

    @property
    def url(self) -> str:
        return f"{self.base}/{self.name}"


def _plain_member(name: str) -> bool:
    parts = Path(name).parts
    return bool(parts) and not Path(name).is_absolute() and ".." not in parts


def unpack(archive: Path, into: Path, strip: int = 0) -> None:
    """A .tar.xz or .zip, unpacked into ``into``; ``strip`` leading folders dropped,
    as espup drops them. A member that would land outside ``into`` is refused."""
    into.mkdir(parents=True, exist_ok=True)
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                if not _plain_member(info.filename):
                    raise InstallError(f"{archive.name}: {info.filename!r} leaves its folder")
                rel = Path(*Path(info.filename).parts[strip:]) if strip else Path(info.filename)
                if not rel.parts:
                    continue
                target = into / rel
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                mode = info.external_attr >> 16
                if mode & stat.S_IXUSR:
                    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return
    with tarfile.open(archive, mode="r:*") as tf:
        members = []
        for member in tf.getmembers():
            if not _plain_member(member.name):
                raise InstallError(f"{archive.name}: {member.name!r} leaves its folder")
            if strip:
                parts = Path(member.name).parts[strip:]
                if not parts:
                    continue
                member.name = str(Path(*parts))
            members.append(member)
        if hasattr(tarfile, "data_filter"):
            tf.extractall(into, members=members, filter="data")
        else:  # pragma: no cover - Python before 3.11.4
            tf.extractall(into, members=members)


def install_components(root: Path, dest: Path) -> List[str]:
    """What a rust-installer dist's ``install.sh --prefix=''`` does, without running it:
    each component in ``components`` (but the docs) moved into ``dest`` as its
    ``manifest.in`` lists it -- ``file:`` a file, ``dir:`` a folder."""
    names = [c.strip() for c in (root / "components").read_text("utf-8").splitlines()]
    done = []
    for component in (c for c in names if c and not c.startswith("rust-docs")):
        if not _plain_member(component):
            raise InstallError(f"not a component: {component!r}")
        for line in (root / component / "manifest.in").read_text("utf-8").splitlines():
            kind, _, rel = line.strip().partition(":")
            if not rel:
                continue
            if kind not in ("file", "dir") or not _plain_member(rel):
                raise InstallError(f"{component}: cannot install {line!r}")
            src, dst = root / component / rel, dest / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if kind == "file":
                os.replace(src, dst)
            elif dst.exists():
                shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True)
            else:
                shutil.move(str(src), str(dst))
        done.append(component)
    rustlib = dest / "lib" / "rustlib"
    rustlib.mkdir(parents=True, exist_ok=True)
    listed = rustlib / "components"
    before = listed.read_text("utf-8").split() if listed.is_file() else []
    listed.write_text("\n".join(dict.fromkeys([*before, *done])) + "\n", encoding="utf-8")
    return done


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
        fetch_to: Callable[[str, Path], str] = _fetch_to,
    ):
        self.log = log or (lambda _line: None)
        self.force = force
        self.fetch = fetch
        self.fetch_to = fetch_to
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
        """The installers' environment: the build's -- no fetch redirects, no
        wrapper, homes in the tools dir."""
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

    # 2. the Xtensa toolchain: four archives, checked, laid out as espup lays them out
    def toolchain_dir(self) -> Path:
        """Where this pin of the Xtensa toolchain lives; rustup's ``esp`` links to it."""
        return home() / "xtensa" / check_version(XTENSA_RUST_VERSION)

    def archives(self) -> List[Archive]:
        """The archives this machine needs, each with what checks it."""
        triple, windows = self.triple, _windows(self.triple)
        arch = ESPRESSIF_ARCHES[triple]
        rust = check_version(XTENSA_RUST_VERSION)
        llvm, gcc = check_esp_version(LLVM_VERSION), check_esp_version(GCC_VERSION)
        rust_build = f"{GITHUB}/{RUST_BUILD_REPO}/releases/download/v{rust}"
        out = [
            Archive(
                "rust",
                f"rust-{rust}-{triple}.{'zip' if windows else 'tar.xz'}",
                rust_build,
                github=(RUST_BUILD_REPO, f"v{rust}"),
            )
        ]
        if not windows:  # Windows' zip carries rust-src inside it
            out.append(
                Archive(
                    "rust-src",
                    f"rust-src-{rust}.tar.xz",
                    rust_build,
                    github=(RUST_BUILD_REPO, f"v{rust}"),
                )
            )
        out.append(
            Archive(
                "llvm",
                f"libs-clang-{llvm}-{arch}.tar.xz",
                f"{GITHUB}/{LLVM_REPO}/releases/download/{llvm}",
                checksums=f"libs-clang-{llvm}-checksum.sha256",
            )
        )
        out.append(
            Archive(
                "gcc",
                f"{XTENSA_GCC}-{gcc.removeprefix('esp-')}-{arch}.{'zip' if windows else 'tar.xz'}",
                f"{GITHUB}/{GCC_REPO}/releases/download/esp-{gcc.removeprefix('esp-')}",
                checksums=f"crosstool-NG-esp-{gcc.removeprefix('esp-')}-checksum.sha256",
            )
        )
        return out

    def expected(self, archive: Archive) -> str:
        """The SHA-256 the archive's source publishes for it."""
        if archive.checksums:
            text = self.fetch(f"{archive.base}/{archive.checksums}").decode("utf-8")
            return listed_sha256(text, archive.name)
        repo, tag = archive.github
        return github_digest(repo, "", archive.name, self.fetch, tag=tag)

    def download(self, archive: Archive) -> Path:
        """The archive, downloaded and checked; refused, and removed, if it is not
        what its source publishes."""
        want = self.expected(archive)
        path = home() / "downloads" / archive.name
        self.log(f"Downloading {archive.url}")
        got = self.fetch_to(archive.url, path)
        if got != want:
            path.unlink(missing_ok=True)
            raise InstallError(f"checksum mismatch for {archive.name}: expected {want}, got {got}")
        self.log(f"SHA-256 verified ({want[:12]}…) {archive.name}")
        return path

    def lay_out(self, archive: Archive, path: Path, dest: Path) -> None:
        """One archive into the toolchain's folder, where espup puts it."""
        windows = _windows(self.triple)
        llvm, gcc = LLVM_VERSION, GCC_VERSION.removeprefix("esp-")
        if archive.part in ("rust", "rust-src") and not windows:
            scratch = home() / "tmp" / archive.part
            if scratch.exists():
                shutil.rmtree(scratch)
            unpack(path, scratch)
            roots = [d for d in scratch.iterdir() if (d / "components").is_file()]
            if len(roots) != 1:
                raise InstallError(f"{archive.name}: not a rust-installer dist")
            done = install_components(roots[0], dest)
            self.log(f"Installed {', '.join(done)} into {dest}")
            shutil.rmtree(scratch)
        elif archive.part == "rust":  # Windows: one zip, rust-src inside, its folder dropped
            unpack(path, dest, strip=1)
        elif archive.part == "llvm":
            if windows:
                unpack(path, dest / CLANG_NAME)
                (dest / CLANG_NAME / llvm).touch()
            else:
                unpack(path, dest / CLANG_NAME / llvm)
        elif archive.part == "gcc":
            if windows:
                unpack(path, dest)
                (dest / XTENSA_GCC / gcc).touch()
            else:
                unpack(path, dest / XTENSA_GCC / f"esp-{gcc}")

    def export_lines(self, dest: Path) -> List[str]:
        """espup's export file for this layout: the linker's folder and libclang."""
        llvm, gcc = LLVM_VERSION, GCC_VERSION.removeprefix("esp-")
        if _windows(self.triple):
            clang = dest / CLANG_NAME / "esp-clang" / "bin"
            return [
                f'$Env:LIBCLANG_PATH = "{clang / "libclang.dll"}"',
                f'$Env:PATH = "{clang};" + $Env:PATH',
                f'$Env:PATH = "{dest / XTENSA_GCC / "bin"};" + $Env:PATH',
            ]
        return [
            f'export LIBCLANG_PATH="{dest / CLANG_NAME / llvm / "esp-clang" / "lib"}"',
            f'export PATH="{dest / XTENSA_GCC / f"esp-{gcc}" / XTENSA_GCC / "bin"}:$PATH"',
        ]

    def pins(self) -> dict:
        return {"version": XTENSA_RUST_VERSION, "llvm": LLVM_VERSION, "gcc": GCC_VERSION}

    def install_toolchain(self, had: Optional[dict]) -> dict:
        dest = self.toolchain_dir()
        rustc = dest / "bin" / _exe("rustc", self.triple)
        rustup = self.cargo_bin("rustup")
        if rustc.is_file() and had and had.get("archives") and not self.force:
            if {k: had.get(k) for k in self.pins()} == self.pins():
                self.log(f"Xtensa Rust {XTENSA_RUST_VERSION} already installed ({dest})")
                self.link(rustup, dest)
                return had
        staged = dest.with_name(f".{dest.name}.new")
        if staged.exists():
            shutil.rmtree(staged)
        checked = {}
        for archive in self.archives():
            path = self.download(archive)
            self.lay_out(archive, path, staged)
            checked[archive.name] = self._sha(path)
            path.unlink(missing_ok=True)  # kept no longer than it takes to unpack
        if dest.exists():
            shutil.rmtree(dest)
        os.replace(staged, dest)
        export = export_file(_windows(self.triple))
        export.write_text("\n".join(self.export_lines(dest)) + "\n", encoding="utf-8")
        self.log(f"Wrote {export}")
        self.link(rustup, dest)
        return {**self.pins(), "archives": checked}

    @staticmethod
    def _sha(path: Path) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def link(self, rustup: Path, dest: Path) -> None:
        """The toolchain, as rustup's ``esp``: linked, and the default -- nothing fetched.

        A link to another pin is let go (the folder it named is left); an ``esp``
        that is a folder of its own -- espup's install, before there was this --
        is uninstalled by rustup first.
        """
        env = self.env()
        existing = rustup_home() / "toolchains" / TOOLCHAIN
        linked = existing.is_symlink() and existing.resolve() == dest.resolve()
        if existing.is_symlink() and not linked:
            existing.unlink()
        elif existing.exists() and not existing.is_symlink():
            self._check(
                self.run([str(rustup), "toolchain", "uninstall", TOOLCHAIN], env=env),
                "rustup toolchain uninstall",
            )
        if not linked:
            self._check(
                self.run([str(rustup), "toolchain", "link", TOOLCHAIN, str(dest)], env=env),
                "rustup toolchain link",
            )
        self._check(self.run([str(rustup), "default", TOOLCHAIN], env=env), "rustup default")

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
        f"{triple}: rustup {RUSTUP_VERSION}, Xtensa Rust {XTENSA_RUST_VERSION} with its "
        f"rust-src, LLVM {LLVM_VERSION} and GCC {GCC_VERSION}, and espflash "
        f"{ESPFLASH_VERSION} into {home()}, and every Rust sketch's crates vendored beside them"
    )
