"""Install an OpenSCAD development snapshot into the tools dir, natively on each platform.

A snapshot is named by its date, and the date is its version: three numbers,
``YYYY.MM.DD``, checked before it is spliced into anything. What an install
does depends on the machine -- its hardware, not what an emulated Python says
it is (``host()``):

- **Linux x86_64**: the night's AppImage, run as it is. Where there is no FUSE
  the AppImage cannot mount itself; that failure is known by what it prints,
  and the image is extracted (``--appimage-extract``) and
  ``squashfs-root/AppRun`` is run instead.
- **macOS**, Intel and Apple Silicon: the night's ``.dmg``, attached read-only
  with ``hdiutil``, ``OpenSCAD.app`` copied out of it, and the image detached
  whatever happened. The app is universal (x86_64 and arm64; read from its
  Mach-O header, and ``openscad status`` says which), so it runs natively on both.
- **Windows x64**: the night's portable ``-x86-64.zip`` (no installer, no
  admin), unpacked: ``openscad.exe`` with its files beside it.
- **Linux arm64**: files.openscad.org publishes no current build for it, so it
  is built here from source at the snapshot's date: the last commit on
  OpenSCAD's default branch at or before that date (api.github.com), its
  tarball and each submodule's at the commit it pins (codeload.github.com),
  configured headless with Manifold and built with cmake. What the build needs
  is checked first; anything missing is refused with the ``apt install`` line
  that adds it, and nothing here runs sudo.
- **Windows on ARM** is not supported yet (a planned item), nor is anything
  else; ``APOTHECARY_OPENSCAD`` names an OpenSCAD installed another way.

Every fetch goes through ``tool_fetch`` (apothecary/stays_local.py), to those
hosts alone, with no proxy. A download from files.openscad.org is checked
against the size its listing gives and the ``.sha256`` published beside it; a
commit spliced into a GitHub URL is 40 hex characters. Whatever the platform,
the result must run and report the date it was asked for before it is moved
into place (staged beside it, then renamed); a source build must also have
Manifold and render a cube with it. (The host also publishes a detached
``.asc`` signature for the AppImage and the zip; checking it needs GnuPG and a
key this program does not carry, so it is not checked.)

Where it goes: ``tools_dir()/openscad/<date>/``, with ``install.json`` in it
saying what was installed (how, the executable, the platform, its
architectures, a source build's commits), and ``tools_dir()/openscad/current``
a text file naming the date in use. The resolver in
apothecary/projects/parts/stl_renderer.py reads it. Stdlib only.
"""

from __future__ import annotations

import base64
import collections
import hashlib
import io
import json
import os
import platform
import plistlib
import posixpath
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import quote

from .firmware.toolchains import tools_dir

SNAPSHOTS = "https://files.openscad.org/snapshots/"
GITHUB_API = "https://api.github.com"
CODELOAD = "https://codeload.github.com"
OPENSCAD_REPO = "openscad/openscad"
MANIFEST = "install.json"

# Snapshots from this date on take ``--backend=manifold``. (``--enable=manifold``
# is the older spelling, which later snapshots accept and then render with CGAL.)
MANIFOLD_SINCE = (2024, 9, 28)

# Manifold's CMakeLists asks for 3.18 (OpenSCAD's own, 3.13).
CMAKE_AT_LEAST = (3, 18)

DATE_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
# A GitHub owner or repository, a path inside a source tree, a branch: plain names.
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
PATH_RE = re.compile(r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$")

Log = Callable[[str], None]
Fetch = Callable[[str], bytes]


class InstallError(RuntimeError):
    """The snapshot could not be found, fetched, verified, built or put in place."""


def _fetch(url: str, timeout: int = 300, agent: str = "apothecary-openscad-installer") -> bytes:
    """A tool fetch: a GET from files.openscad.org, api.github.com or
    codeload.github.com, and nowhere else.

    ``tool_fetch`` refuses a URL whose host is not a tool source before
    anything is opened, and holds the sockets under this call to those hosts.
    The slicer installer (apothecary/slicer/orcaslicer_installer.py) fetches
    through this one and ``_fetch_to``, naming itself in ``agent``.
    """
    from .stays_local import tool_fetch

    req = urllib.request.Request(url, headers={"User-Agent": agent})
    # No proxy from the environment: a proxy is a place the fetch would go instead.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with tool_fetch(url), opener.open(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


def _fetch_to(
    url: str, path: Path, timeout: int = 300, agent: str = "apothecary-openscad-installer"
) -> str:
    """``_fetch``, written to ``path`` as it arrives rather than held in memory: the
    SHA-256 of what arrived. For a download too large to hold whole (an
    OrcaSlicer release is a quarter of a gigabyte on macOS)."""
    from .stays_local import tool_fetch

    req = urllib.request.Request(url, headers={"User-Agent": agent})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    digest = hashlib.sha256()
    with tool_fetch(url), opener.open(req, timeout=timeout) as resp:  # noqa: S310
        with open(path, "wb") as out:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                digest.update(chunk)
                out.write(chunk)
    return digest.hexdigest()


def check_date(text: str) -> str:
    """A snapshot date, ``YYYY.MM.DD``, or InstallError: it becomes part of a URL
    and a directory name, so it is three numbers and nothing else."""
    if not isinstance(text, str) or not DATE_RE.match(text):
        raise InstallError(f"not an OpenSCAD snapshot date: {text!r} (want YYYY.MM.DD)")
    return text


def check_sha(text: object) -> str:
    """A commit, 40 lowercase hex characters, or InstallError: it becomes part of
    a URL, so it is a commit and nothing else."""
    if not isinstance(text, str) or not SHA_RE.match(text):
        raise InstallError(f"not a commit SHA: {text!r} (want 40 hex characters)")
    return text


def _numbers(text: Optional[str]) -> Optional[Tuple[int, ...]]:
    """``2021.08.24`` or ``OpenSCAD version 2021.01`` as (2021, 8, 24) / (2021, 1)."""
    match = re.search(r"(\d{4})\.(\d{1,2})(?:\.(\d{1,2}))?", text or "")
    if match is None:
        return None
    return tuple(int(g) for g in match.groups() if g is not None)


def has_manifold(version_line: Optional[str]) -> bool:
    """Whether an OpenSCAD that reports ``version_line`` takes ``--backend=manifold``."""
    have = _numbers(version_line)
    return have is not None and have >= MANIFOLD_SINCE


# --- this machine ------------------------------------------------------------------

_MACHINES = {"amd64": "x86_64", "x64": "x86_64", "x86_64": "x86_64", "aarch64": "arm64"}
SYSTEM_NAMES = {"Darwin": "macOS"}


def _machine_name(raw: str) -> str:
    return _MACHINES.get(raw.lower(), raw.lower())


def _rosetta_translated() -> bool:
    """Whether this process is an x86_64 one that Rosetta 2 runs on Apple Silicon:
    then ``platform.machine()`` says x86_64 on an arm64 Mac."""
    if sys.platform != "darwin":
        return False
    try:
        done = subprocess.run(
            ["sysctl", "-n", "sysctl.proc_translated"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.stdout.strip() == "1"


def _windows_native_machine() -> Optional[str]:
    """The PC's own architecture: an x64 Python emulated on an ARM64 PC says AMD64."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        process, native = ctypes.c_ushort(), ctypes.c_ushort()
        ok = kernel32.IsWow64Process2(
            kernel32.GetCurrentProcess(), ctypes.byref(process), ctypes.byref(native)
        )
    except (AttributeError, OSError):  # before Windows 10 1709
        return None
    if not ok:
        return None
    return {0x8664: "x86_64", 0xAA64: "arm64", 0x014C: "x86"}.get(native.value)


def host() -> Tuple[str, str]:
    """This machine: ``platform.system()`` and its hardware's architecture,
    ``x86_64`` or ``arm64`` (anything else as the platform names it)."""
    system = platform.system()
    machine = _machine_name(platform.machine())
    if system == "Windows":
        machine = _windows_native_machine() or machine
    elif system == "Darwin" and machine == "x86_64" and _rosetta_translated():
        machine = "arm64"
    return system, machine


def _platform_label(system: str, machine: str) -> str:
    return f"{SYSTEM_NAMES.get(system, system)} {machine}"


# --- how this machine installs -------------------------------------------------------

APPIMAGE, EXTRACTED, DMG, ZIP, SOURCE = "appimage", "appimage-extracted", "dmg", "zip", "source"

# How each platform's snapshot is named in the listing. In 2025 the AppImage
# carried a build number: OpenSCAD-2025.10.02.ai27993-x86_64.AppImage.
_PATTERNS = {
    APPIMAGE: re.compile(r"^OpenSCAD-(\d{4}\.\d{2}\.\d{2})(?:\.ai(\d+))?-x86_64\.AppImage$"),
    DMG: re.compile(r"^OpenSCAD-(\d{4}\.\d{2}\.\d{2})(?:\.ai(\d+))?\.dmg$"),
    ZIP: re.compile(r"^OpenSCAD-(\d{4}\.\d{2}\.\d{2})(?:\.ai(\d+))?-x86-64\.zip$"),
}
# Any platform's file of a night: the newest names the night a source build takes.
NIGHT = re.compile(
    r"^OpenSCAD-(\d{4}\.\d{2}\.\d{2})(?:\.ai(\d+))?(?:-x86_64\.AppImage|\.dmg|-x86-64\.zip)$"
)

WINDOWS_ON_ARM = (
    "Windows on ARM is not supported yet (a planned item); set APOTHECARY_OPENSCAD "
    "to an OpenSCAD you installed"
)

WHAT_INSTALL_DOES = {
    APPIMAGE: "the night's AppImage from files.openscad.org (extracted where there is no FUSE)",
    DMG: "OpenSCAD.app from the night's disk image on files.openscad.org",
    ZIP: "the night's portable zip from files.openscad.org, unpacked",
    SOURCE: "OpenSCAD built here from its source on GitHub at the night's date (cmake; long)",
}


def install_method(system: Optional[str] = None, machine: Optional[str] = None) -> str:
    """How an install goes on this platform (``host()`` unless given), or
    InstallError where it does not."""
    if system is None or machine is None:
        here = host()
        system, machine = system or here[0], machine or here[1]
    machine = _machine_name(machine)
    if system == "Linux" and machine == "x86_64":
        return APPIMAGE
    if system == "Linux" and machine == "arm64":
        return SOURCE
    if system == "Darwin" and machine in ("x86_64", "arm64"):
        return DMG
    if system == "Windows" and machine == "x86_64":
        return ZIP
    if system == "Windows" and machine == "arm64":
        raise InstallError(WINDOWS_ON_ARM)
    raise InstallError(
        f"no OpenSCAD for {system} {machine}: files.openscad.org publishes Linux x86_64, "
        "macOS and Windows x64 builds, and a source build here is for Linux arm64. Install "
        "OpenSCAD another way and set APOTHECARY_OPENSCAD to it"
    )


def what_install_does() -> str:
    """This machine, and what ``apothecary openscad install`` does on it."""
    system, machine = host()
    label = _platform_label(system, machine)
    try:
        return f"{label}: an install is {WHAT_INSTALL_DOES[install_method(system, machine)]}"
    except InstallError as exc:
        return f"{label}: {exc}"


def snapshot_pattern(system: Optional[str] = None, machine: Optional[str] = None) -> re.Pattern:
    """How this platform's snapshot is named in the listing; InstallError where
    there is none to download."""
    method = install_method(system, machine)
    if method == SOURCE:
        raise InstallError(
            "files.openscad.org publishes no current snapshot for Linux arm64; "
            "it is built from source"
        )
    return _PATTERNS[method]


# --- where it lives ------------------------------------------------------------------

# Before install.json, an install was the AppImage itself, at <date>/openscad.
LEGACY_EXECUTABLE = "openscad"


def openscad_dir() -> Path:
    return tools_dir() / "openscad"


def _plain(rel: object) -> Optional[str]:
    """A relative path that stays inside the directory it is joined to, or None."""
    if not isinstance(rel, str) or not PATH_RE.match(rel):
        return None
    if any(part in (".", "..") for part in rel.split("/")):
        return None
    return rel


def read_manifest(date: str) -> dict:
    """What ``install.json`` in a snapshot's directory says, or {}."""
    try:
        data = json.loads((openscad_dir() / check_date(date) / MANIFEST).read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def executable_for(date: str) -> Path:
    """The executable of the snapshot of ``date``: where ``install.json`` says it
    is, else the AppImage an install made before there was one."""
    rel = _plain(read_manifest(date).get("executable")) or LEGACY_EXECUTABLE
    return openscad_dir() / check_date(date) / rel


def installed_versions() -> list[str]:
    """The snapshot dates installed, oldest first."""
    home = openscad_dir()
    if not home.is_dir():
        return []
    return sorted(
        p.name for p in home.iterdir() if DATE_RE.match(p.name) and executable_for(p.name).is_file()
    )


def current_version() -> Optional[str]:
    """The date ``current`` names, if it is a date; anything else names nothing."""
    try:
        text = (openscad_dir() / "current").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text if DATE_RE.match(text) else None


def current_executable() -> Optional[Path]:
    """The installed snapshot in use, or None."""
    date = current_version()
    if date is None:
        return None
    path = executable_for(date)
    return path if path.is_file() else None


def _write_current(date: str) -> None:
    home = openscad_dir()
    tmp = home / f".current.{os.getpid()}.tmp"
    tmp.write_text(check_date(date) + "\n", encoding="utf-8")
    os.replace(tmp, home / "current")


# --- what an executable is built for -------------------------------------------------

_ELF = {3: "x86", 40: "arm", 62: "x86_64", 183: "arm64"}
_MACH_O = {7: "x86", 12: "arm", 0x01000007: "x86_64", 0x0100000C: "arm64"}
_PE = {0x014C: "x86", 0x8664: "x86_64", 0xAA64: "arm64"}


def binary_archs(path: Path) -> List[str]:
    """The architectures an executable is built for, from its header: ELF,
    Mach-O (one, or universal) or PE. [] for anything else (a script) or a file
    that cannot be read."""
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
            if head[:2] == b"MZ" and len(head) >= 0x40:
                (offset,) = struct.unpack_from("<I", head, 0x3C)
                f.seek(offset)
                pe = f.read(6)
                if pe[:4] == b"PE\x00\x00" and len(pe) == 6:
                    (machine,) = struct.unpack_from("<H", pe, 4)
                    return [_PE.get(machine, f"pe-{machine:#x}")]
                return []
    except OSError:
        return []
    if head[:4] == b"\x7fELF" and len(head) >= 20:
        (machine,) = struct.unpack_from("<H" if head[5] == 1 else ">H", head, 18)
        return [_ELF.get(machine, f"elf-{machine}")]
    if head[:4] in (b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf") and len(head) >= 8:
        (count,) = struct.unpack_from(">I", head, 4)
        if not 0 < count < 20:  # a Java class file starts the same way
            return []
        size = 20 if head[3] == 0xBE else 32
        cpus = [
            struct.unpack_from(">I", head, 8 + i * size)[0]
            for i in range(count)
            if 8 + i * size + 4 <= len(head)
        ]
        return [_MACH_O.get(cpu, f"mach-o-{cpu:#x}") for cpu in cpus]
    if head[:4] in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe") and len(head) >= 8:
        (cpu,) = struct.unpack_from("<I", head, 4)
        return [_MACH_O.get(cpu, f"mach-o-{cpu:#x}")]
    return []


def runs_here(
    archs: List[str],
    system: Optional[str] = None,
    machine: Optional[str] = None,
    translated: Optional[bool] = None,
) -> str:
    """Whether an executable built for ``archs`` runs natively on this machine
    (``host()`` unless given), emulated, or not at all."""
    if system is None or machine is None:
        here = host()
        system, machine = system or here[0], machine or here[1]
    if translated is None:
        translated = system == "Darwin" and _rosetta_translated()
    archs = list(archs)
    if not archs:
        return "architecture not known"
    if system == "Darwin" and translated and "x86_64" in archs:
        return (
            "emulated: x86_64 under Rosetta 2 (this Python is an x86_64 process, and "
            "what it starts runs as x86_64 too)"
        )
    if machine in archs:
        return "native" if len(archs) == 1 else f"native (universal: {', '.join(archs)})"
    if system == "Darwin" and machine == "arm64" and "x86_64" in archs:
        return "emulated: x86_64 under Rosetta 2"
    if system == "Windows" and machine == "arm64" and "x86_64" in archs:
        return "emulated: x64 on Windows on ARM"
    return f"does not run here: built for {', '.join(archs)}"


# --- what is installed, said ---------------------------------------------------------

HOW = {
    APPIMAGE: "AppImage, run through FUSE",
    EXTRACTED: "AppImage extracted (no FUSE here), run as squashfs-root/AppRun",
    DMG: "OpenSCAD.app from the disk image",
    ZIP: "portable zip, unpacked",
    SOURCE: "built from source at {commit}",
}


@dataclass
class Installed:
    """One installed snapshot, as ``openscad status`` says it."""

    date: str
    executable: Path
    platform: str
    how: str
    runs: str
    version: Optional[str]
    manifold: str

    def line(self) -> str:
        return " · ".join((self.platform, self.how, self.runs, self.manifold))


def describe(date: str) -> Installed:
    """The snapshot of ``date``: the platform it was installed for, how, whether
    it runs natively here, and whether it has Manifold."""
    record = read_manifest(date)
    exe = executable_for(date)
    method = record.get("method") if record.get("method") in HOW else APPIMAGE
    archs = record.get("archs")
    if not isinstance(archs, list) or not all(isinstance(a, str) for a in archs):
        archs = binary_archs(exe)
    system, machine = host()
    label = record.get("platform")
    if not isinstance(label, str):
        label = _platform_label(system, archs[0] if archs else machine)
    commit = record.get("commit")
    how = HOW[method].format(
        commit=commit if isinstance(commit, str) and SHA_RE.match(commit) else "an unknown commit"
    )
    version = record.get("version") if isinstance(record.get("version"), str) else None
    version = version or reported_version(exe)
    built_with = record.get("manifold")
    if method == SOURCE and isinstance(built_with, str):
        manifold = f"Manifold {built_with}"
    else:
        manifold = "Manifold" if has_manifold(version) else "no Manifold (CGAL)"
    return Installed(date, exe, label, how, runs_here(archs), version, manifold)


# --- the host's listing --------------------------------------------------------------

_ROW = re.compile(r'<a href="([^"/?#]+)">[^<]*</a>\s+\S+\s+\S+\s+(\d+)\s*$', re.M)


def parse_listing(html: str, pattern: re.Pattern) -> Dict[str, Tuple[str, int]]:
    """``{date: (file name, size)}`` for this platform's snapshots in the listing.

    Where one night has two builds, the later is kept: a plain name over an
    ``.ai`` build number, else the higher number.
    """
    found: Dict[str, Tuple[str, int, int]] = {}
    for name, size in _ROW.findall(html):
        match = pattern.match(name)
        if match is None:
            continue
        date, build = match.group(1), match.group(2)
        rank = int(build) if build else 1 << 62
        if date not in found or rank > found[date][2]:
            found[date] = (name, int(size), rank)
    return {date: (name, size) for date, (name, size, _) in found.items()}


def _published_sha256(text: str, name: str) -> str:
    for line in text.splitlines():
        parts = line.split()
        if (
            len(parts) == 2
            and parts[1].lstrip("*") == name
            and re.match(r"^[0-9a-f]{64}$", parts[0].lower())
        ):
            return parts[0].lower()
    raise InstallError(f"no SHA-256 published for {name}")


def _run(executable: Path, *args: str, timeout: int = 120, cwd=None) -> Tuple[int, str]:
    """Run ``executable`` with ``args``: its exit code and what it printed (stderr
    first; OpenSCAD writes its version there), or (-1, why it did not start)."""
    try:
        done = subprocess.run(
            [str(executable), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=cwd,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return -1, str(exc)
    return done.returncode, f"{done.stderr}\n{done.stdout}"


def reported_version(executable: Path) -> Optional[str]:
    """What ``executable --version`` prints (OpenSCAD writes it to stderr)."""
    _code, said = _run(executable, "--version")
    for line in said.splitlines():
        if re.search(r"version\s+\d{4}\.", line, re.I):
            return line.strip()
    return None


_FUSE = re.compile(r"fuse|--appimage-extract", re.I)


def needs_fuse(said: str) -> bool:
    """Whether an AppImage that failed failed for want of FUSE: the runtime says
    so (``libfuse``, ``fusermount``, ``FUSE setup``, ``--appimage-extract``)."""
    return bool(_FUSE.search(said or ""))


# --- unpacking, held inside its folder ----------------------------------------------


def _parts(name: str) -> Optional[List[str]]:
    """An archive member's name as its parts, or None where it would land outside
    the folder it is unpacked into: absolute, on a drive, or through ``..``."""
    if name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name):
        return None
    parts = [part for part in re.split(r"[\\/]", name) if part not in ("", ".")]
    return None if ".." in parts else parts


def unpack_portable_zip(body: bytes, dest: Path) -> str:
    """Unpack the folder of the Windows zip that holds ``openscad.exe`` into
    ``dest``, its files beside it; returns the executable's name there. A member
    that would land outside refuses the whole zip before anything is written."""
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        members = []
        for info in zf.infolist():
            parts = _parts(info.filename)
            if parts is None:
                raise InstallError(f"the zip names a path outside its folder: {info.filename!r}")
            if parts:
                members.append((info, parts))
        exes = [p for info, p in members if p[-1].lower() == "openscad.exe" and not info.is_dir()]
        if not exes:
            raise InstallError("no openscad.exe in the zip")
        exe = min(exes, key=len)
        root = exe[:-1]
        for info, parts in members:
            rel = parts[len(root) :] if parts[: len(root)] == root else []
            if not rel:
                continue
            target = dest.joinpath(*rel)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    path = dest / exe[-1]
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return exe[-1]


def unpack_tarball(body: bytes, dest: Path) -> None:
    """Unpack a GitHub source tarball (one top folder, ``<repo>-<sha>/``) into
    ``dest``, the top folder dropped. A member that would land outside -- an
    absolute name, a ``..``, a link that points out -- refuses the whole tarball
    before anything is written; a device or a pipe is not source and is skipped."""
    with tarfile.open(fileobj=io.BytesIO(body), mode="r:gz") as tf:
        chosen = []
        for member in tf.getmembers():
            parts = _parts(member.name)
            if parts is None:
                raise InstallError(f"the tarball names a path outside its folder: {member.name!r}")
            rel = parts[1:]
            if not rel:
                continue
            if member.issym():
                target = posixpath.normpath(posixpath.join(*rel[:-1], member.linkname))
                if member.linkname.startswith("/") or target == ".." or target.startswith("../"):
                    raise InstallError(
                        f"the tarball links outside its folder: {member.name} -> {member.linkname}"
                    )
            elif member.islnk():
                link = _parts(member.linkname)
                if link is None or len(link) < 2:
                    raise InstallError(
                        f"the tarball links outside its folder: {member.name} -> {member.linkname}"
                    )
                member.linkname = "/".join(link[1:])
            elif not (member.isfile() or member.isdir()):
                continue
            member.name = "/".join(rel)
            chosen.append(member)
        # The standard library's own guard as well, where this Python has it.
        guard = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
        tf.extractall(dest, members=chosen, **guard)


def _executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _rename(src: Path, dst: Path, tries: int = 5) -> None:
    for attempt in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            # Windows: a virus scanner holds a file just written for a moment.
            if os.name != "nt" or attempt == tries - 1:
                raise
            time.sleep(0.5 * (attempt + 1))


# --- what a source build needs --------------------------------------------------------


@dataclass(frozen=True)
class Need:
    """Something a source build needs, how it is found, and the Debian/Ubuntu
    package that has it."""

    what: str
    package: str
    programs: Tuple[str, ...] = ()  # any of these on PATH
    headers: Tuple[str, ...] = ()  # any of these under an include directory
    libraries: Tuple[str, ...] = ()  # each of these (lib<name>.so or .a) under a lib directory


# From OpenSCAD's README ("Prerequisites") and scripts/uni-get-dependencies.sh,
# less what a headless build does without (Qt, QScintilla, GLX and X11) and
# what comes from its submodules (Manifold, Clipper2, OpenCSG, mimalloc).
BUILD_NEEDS = (
    Need("cmake", "cmake", programs=("cmake",)),
    Need("make", "make", programs=("make",)),
    Need("a C++ compiler", "g++", programs=("c++", "g++", "clang++")),
    Need("pkg-config", "pkg-config", programs=("pkg-config", "pkgconf")),
    Need("bison", "bison", programs=("bison",)),
    Need("flex", "flex", programs=("flex",)),
    Need(
        "Boost.Regex",
        "libboost-regex-dev",
        headers=("boost/regex.hpp",),
        libraries=("boost_regex",),
    ),
    Need(
        "Boost.Program_options",
        "libboost-program-options-dev",
        headers=("boost/program_options.hpp",),
        libraries=("boost_program_options",),
    ),
    Need("CGAL", "libcgal-dev", headers=("CGAL/version.h",)),
    Need("GMP", "libgmp-dev", headers=("gmp.h",)),
    Need("MPFR", "libmpfr-dev", headers=("mpfr.h",)),
    Need("Eigen", "libeigen3-dev", headers=("eigen3/Eigen/Core",)),
    Need("HarfBuzz", "libharfbuzz-dev", headers=("harfbuzz/hb.h",)),
    Need("FreeType", "libfreetype-dev", headers=("freetype2/ft2build.h",)),
    Need("Fontconfig", "libfontconfig-dev", headers=("fontconfig/fontconfig.h",)),
    Need("GLib", "libglib2.0-dev", headers=("glib-2.0/glib.h",)),
    Need(
        "double-conversion",
        "libdouble-conversion-dev",
        headers=("double-conversion/double-conversion.h",),
    ),
    Need("libzip", "libzip-dev", headers=("zip.h",)),
    Need("libxml2", "libxml2-dev", headers=("libxml2/libxml/parser.h",)),
    Need("OpenSSL", "libssl-dev", headers=("openssl/ssl.h",)),
    Need("oneTBB", "libtbb-dev", headers=("tbb/tbb.h", "oneapi/tbb.h")),
    Need("OpenGL", "libgl-dev", headers=("GL/gl.h",)),
    Need("EGL", "libegl-dev", headers=("EGL/egl.h",)),
)

# How the build is configured: OpenSCAD's own snapshot build (.circleci/config.yml),
# headless, with nothing fetched while it builds.
CMAKE_FLAGS = (
    "-DCMAKE_BUILD_TYPE=Release",
    "-DHEADLESS=ON",  # the command line alone: no Qt
    "-DENABLE_TESTS=OFF",
    "-DENABLE_MANIFOLD=ON",
    "-DEXPERIMENTAL=ON",  # as the published snapshots are built
    "-DSNAPSHOT=ON",
    "-DUSE_BUILTIN_MANIFOLD=ON",  # each from its submodule, at the commit pinned
    "-DUSE_BUILTIN_CLIPPER2=ON",
    "-DUSE_BUILTIN_OPENCSG=ON",
    "-DMANIFOLD_DOWNLOADS=OFF",  # a missing dependency stops the build; nothing is fetched
    "-DFETCHCONTENT_FULLY_DISCONNECTED=ON",
    "-DENABLE_GLX=OFF",  # offscreen OpenGL through EGL: no X11 needed
    "-DUSE_CCACHE=OFF",
)


def _include_dirs() -> List[Path]:
    usr = Path("/usr/include")
    return [Path("/usr/local/include"), usr, *sorted(usr.glob("*-linux-gnu*"))]


def _lib_dirs() -> List[Path]:
    usr = Path("/usr/lib")
    return [Path("/usr/local/lib"), usr, Path("/usr/lib64"), *sorted(usr.glob("*-linux-gnu*"))]


def _cmake_version(cmake: str) -> Optional[Tuple[int, ...]]:
    _code, said = _run(Path(cmake), "--version", timeout=30)
    match = re.search(r"cmake version (\d+)\.(\d+)(?:\.(\d+))?", said)
    return tuple(int(g) for g in match.groups() if g is not None) if match else None


def _dotted(numbers: Tuple[int, ...]) -> str:
    return ".".join(str(n) for n in numbers)


def missing_build_deps() -> Tuple[List[Need], Dict[str, str]]:
    """What a source build needs that this machine does not have, and for some
    of it why (a cmake that is there but too old)."""
    includes, libs = _include_dirs(), _lib_dirs()
    missing: List[Need] = []
    why: Dict[str, str] = {}
    for need in BUILD_NEEDS:
        found = (
            (not need.programs or any(shutil.which(p) for p in need.programs))
            and (not need.headers or any((d / h).is_file() for d in includes for h in need.headers))
            and all(
                any((d / f"lib{lib}{ext}").exists() for d in libs for ext in (".so", ".a"))
                for lib in need.libraries
            )
        )
        if found and need.what == "cmake":
            version = _cmake_version(shutil.which("cmake") or "cmake")
            if version is None or version < CMAKE_AT_LEAST:
                found = False
                here = _dotted(version) if version else "one of unknown version"
                why[need.what] = f"{here} is here; the build needs {_dotted(CMAKE_AT_LEAST)}"
        if not found:
            missing.append(need)
    return missing, why


def _missing_refusal(missing: List[Need], why: Dict[str, str]) -> str:
    names = ", ".join(f"{n.what} ({why[n.what]})" if n.what in why else n.what for n in missing)
    packages = " ".join(dict.fromkeys(n.package for n in missing))
    return (
        f"building OpenSCAD from source needs what this machine does not have: {names}.\n"
        "On Debian, Ubuntu or Raspberry Pi OS, install it with:\n"
        f"  sudo apt install {packages}\n"
        "then run this again. Nothing was downloaded, and nothing here runs sudo."
    )


def _memory_bytes() -> Optional[int]:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, ValueError, OSError):
        return None


def default_jobs() -> int:
    """Compilers a source build runs at once: one a core, and no more than one
    for each 2 GiB of memory, since a board that runs out of memory swaps for
    hours or kills the build."""
    cores = os.cpu_count() or 1
    memory = _memory_bytes()
    if memory is None:
        return cores
    return max(1, min(cores, memory // (2 * 1024**3)))


@dataclass(frozen=True)
class Submodule:
    path: str
    owner: str
    repo: str
    sha: str


def parse_gitmodules(text: str) -> List[Tuple[str, str]]:
    """``[(path, url)]`` from a ``.gitmodules``; a path that is not a plain path
    inside the source tree is refused."""
    sections: List[Dict[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("["):
            sections.append({})
            continue
        key, sep, value = line.partition("=")
        if sep and sections:
            sections[-1][key.strip()] = value.strip()
    found = []
    for section in sections:
        path, url = section.get("path", ""), section.get("url", "")
        if _plain(path) is None:
            raise InstallError(f"a submodule path that is not a plain path in the source: {path!r}")
        found.append((path, url))
    return found


def github_repo(url: str) -> Tuple[str, str]:
    """``(owner, repo)`` of a submodule's URL, which must be a repository on
    github.com (a relative ``../name`` is one beside OpenSCAD's)."""
    if url.startswith("../"):
        url = f"https://github.com/{OPENSCAD_REPO.split('/')[0]}/{url[3:]}"
    match = re.match(r"^https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if match is None or not all(NAME_RE.match(name) for name in match.groups()):
        raise InstallError(f"a submodule's URL is not a repository on github.com: {url!r}")
    return match.group(1), match.group(2)


# --- one install ---------------------------------------------------------------------


class SnapshotInstaller:
    """Find → download → verify (size, SHA-256) or build → it runs and says its
    date → move in → current.

    ``snapshot`` is a date, or None for the newest; ``minimum`` an OpenSCAD
    version the snapshot must be at least (``2021.08.24``, ``2021.01``);
    ``jobs`` the compilers a source build runs at once.
    """

    def __init__(
        self,
        snapshot: Optional[str] = None,
        minimum: Optional[str] = None,
        force: bool = False,
        log: Optional[Log] = None,
        fetch: Optional[Fetch] = None,
        jobs: Optional[int] = None,
    ):
        self.snapshot = snapshot
        self.minimum = minimum
        self.force = force
        self.log = log or (lambda _line: None)
        self._fetch = fetch
        self.jobs = jobs

    def fetch(self, url: str) -> bytes:
        # Looked up at call time, so a test's stand-in for _fetch is the one used.
        return (self._fetch or _fetch)(url)

    def _floor(self) -> Optional[Tuple[int, ...]]:
        if not self.minimum:
            return None
        floor = _numbers(self.minimum)
        if floor is None:
            raise InstallError(f"--min {self.minimum!r} is not an OpenSCAD version such as 2021.01")
        return floor

    def _refuse_below_floor(self, date: str, floor: Optional[Tuple[int, ...]]) -> None:
        if floor is not None and _numbers(date) < floor:
            raise InstallError(
                f"snapshot {date} is older than {self.minimum}, the oldest OpenSCAD asked for"
            )

    def install(self) -> Path:
        if self.snapshot is not None:
            check_date(self.snapshot)
        floor = self._floor()
        method = install_method()
        if self.snapshot is not None:
            self._refuse_below_floor(self.snapshot, floor)
            if not self.force and executable_for(self.snapshot).is_file():
                return self._already(self.snapshot)
        if method == SOURCE:
            return self._from_source(floor)

        self.log(f"Reading {SNAPSHOTS}")
        listing = parse_listing(self.fetch(SNAPSHOTS).decode("utf-8", "replace"), _PATTERNS[method])
        if not listing:
            raise InstallError(f"{SNAPSHOTS} lists no snapshot for this platform")
        newest = max(listing)
        date = self.snapshot or newest
        if date not in listing:
            raise InstallError(
                f"no snapshot for {date} on files.openscad.org for this platform "
                f"(the listing keeps about a year; newest is {newest})"
            )
        self._refuse_below_floor(date, floor)
        if not self.force and executable_for(date).is_file():
            return self._already(date)

        name, size = listing[date]
        url = SNAPSHOTS + name
        self.log(f"Downloading {url} ({size} bytes)")
        body = self.fetch(url)
        if len(body) != size:
            raise InstallError(f"{name}: the listing says {size} bytes, {len(body)} arrived")
        want = _published_sha256(self.fetch(url + ".sha256").decode("utf-8", "replace"), name)
        got = hashlib.sha256(body).hexdigest()
        if got != want:
            raise InstallError(f"checksum mismatch for {name}: expected {want}, got {got}")
        self.log(f"SHA-256 verified ({want[:12]}…)")
        place = {APPIMAGE: self._appimage, DMG: self._disk_image, ZIP: self._portable_zip}
        return self._put_in_place(date, place[method](date, name, body))

    def _already(self, date: str) -> Path:
        path = executable_for(date)
        self.log(f"OpenSCAD snapshot {date} already installed at {path}; --force to fetch it again")
        _write_current(date)
        self.log(f"current -> {date}")
        return path

    def _put_in_place(self, date: str, populate: Callable[[Path], dict]) -> Path:
        """Stage the install beside where it goes, check it runs and reports its
        date, record what it is, then rename it into place."""
        home = openscad_dir()
        home.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{date}.", suffix=".tmp", dir=home))
        staging.chmod(0o755)  # mkdtemp makes it the owner's alone; it is a tools directory
        try:
            record = populate(staging)
            exe = staging / record["executable"]
            reported = reported_version(exe)
            if _numbers(reported) != _numbers(date):
                raise InstallError(
                    f"the snapshot for {date} does not run here or reports "
                    f"{reported or 'no version'}"
                )
            self.log(reported)
            record.setdefault("archs", binary_archs(exe))
            record.update(date=date, version=reported, platform=_platform_label(*host()))
            self.log(f"On this machine: {runs_here(record['archs'])}")
            (staging / MANIFEST).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
            final = home / date
            if final.exists():
                aside = Path(tempfile.mkdtemp(prefix=f".{date}.old.", suffix=".tmp", dir=home))
                _rename(final, aside / date)
                _rename(staging, final)
                shutil.rmtree(aside, ignore_errors=True)
            else:
                _rename(staging, final)
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
        _write_current(date)
        path = executable_for(date)
        self.log(f"Installed {path}; current -> {date}")
        return path

    # Linux x86_64 ---------------------------------------------------------------------

    def _appimage(self, date: str, name: str, body: bytes) -> Callable[[Path], dict]:
        def populate(staging: Path) -> dict:
            image = staging / LEGACY_EXECUTABLE
            image.write_bytes(body)
            _executable(image)
            archs = binary_archs(image)
            code, said = _run(image, "--version")
            if code == 0 or not needs_fuse(said):
                return {"method": APPIMAGE, "executable": LEGACY_EXECUTABLE, "archs": archs}
            self.log("The AppImage cannot mount itself here (no FUSE); extracting it instead")
            code, said = _run(image, "--appimage-extract", timeout=900, cwd=staging)
            if code != 0 or not (staging / "squashfs-root" / "AppRun").exists():
                raise InstallError(f"{name} could not be extracted: {said.strip()[-500:]}")
            (staging / "squashfs-root").chmod(0o755)  # the runtime makes it the owner's alone
            image.unlink()
            return {"method": EXTRACTED, "executable": "squashfs-root/AppRun", "archs": archs}

        return populate

    # macOS ----------------------------------------------------------------------------

    def _disk_image(self, date: str, name: str, body: bytes) -> Callable[[Path], dict]:
        def populate(staging: Path) -> dict:
            fd, held = tempfile.mkstemp(prefix=f".{date}.", suffix=".dmg", dir=staging.parent)
            image = Path(held)
            try:
                with os.fdopen(fd, "wb") as out:
                    out.write(body)
                self._copy_app_out(image, name, staging / "OpenSCAD.app")
            finally:
                image.unlink(missing_ok=True)
            rel = f"OpenSCAD.app/Contents/MacOS/{_bundle_executable(staging / 'OpenSCAD.app')}"
            archs = binary_archs(staging / rel)
            if {"x86_64", "arm64"} <= set(archs):
                self.log("A universal app (x86_64 and arm64): native on Apple Silicon and on Intel")
            elif archs == ["x86_64"] and host()[1] == "arm64":
                self.log(
                    "An Intel-only app: this Mac runs it under Rosetta 2 "
                    "(softwareupdate --install-rosetta, if it is not installed)"
                )
            return {"method": DMG, "executable": rel, "archs": archs}

        return populate

    def _copy_app_out(self, image: Path, name: str, dest: Path) -> None:
        """Attach the disk image read-only, copy its app to ``dest``, and detach
        it whatever happened."""
        hdiutil = shutil.which("hdiutil")
        if hdiutil is None:
            raise InstallError("hdiutil is not on PATH; it comes with macOS")
        mount = Path(tempfile.mkdtemp(prefix="apothecary-openscad-"))
        code, said = _run(
            Path(hdiutil),
            "attach",
            "-nobrowse",  # not shown in the Finder
            "-readonly",
            "-noautoopen",  # no Finder window opens on it
            "-mountpoint",
            str(mount),
            str(image),
        )
        if code != 0:
            _remove_empty(mount)
            raise InstallError(f"hdiutil could not attach {name}: {said.strip()}")
        try:
            app = mount / "OpenSCAD.app"
            if not app.is_dir():
                apps = [p for p in mount.iterdir() if p.suffix == ".app" and p.is_dir()]
                if len(apps) != 1:
                    raise InstallError(f"no OpenSCAD.app in {name}")
                app = apps[0]
            self.log(f"Copying {app.name} out of {name}")
            ditto = shutil.which("ditto")
            if ditto:
                # ditto keeps what a bundle is made of: links, attributes, its signature.
                code, said = _run(Path(ditto), str(app), str(dest), timeout=600)
                if code != 0:
                    raise InstallError(f"ditto could not copy {app.name}: {said.strip()}")
            else:
                shutil.copytree(app, dest, symlinks=True)
        finally:
            self._detach(Path(hdiutil), mount)

    def _detach(self, hdiutil: Path, mount: Path) -> None:
        for extra in ((), ("-force",)):
            code, said = _run(hdiutil, "detach", str(mount), *extra)
            if code == 0:
                break
        else:
            self.log(f"hdiutil could not detach {mount}: {said.strip()}")
        _remove_empty(mount)

    # Windows --------------------------------------------------------------------------

    def _portable_zip(self, date: str, name: str, body: bytes) -> Callable[[Path], dict]:
        def populate(staging: Path) -> dict:
            self.log(f"Unpacking {name}")
            return {"method": ZIP, "executable": unpack_portable_zip(body, staging)}

        return populate

    # Linux arm64 ----------------------------------------------------------------------

    def _from_source(self, floor: Optional[Tuple[int, ...]]) -> Path:
        missing, why = missing_build_deps()
        if missing:
            raise InstallError(_missing_refusal(missing, why))
        date = self.snapshot
        if date is None:
            self.log(f"Reading {SNAPSHOTS}")
            nights = parse_listing(self.fetch(SNAPSHOTS).decode("utf-8", "replace"), NIGHT)
            if not nights:
                raise InstallError(f"{SNAPSHOTS} lists no snapshot")
            date = max(nights)
            self._refuse_below_floor(date, floor)
            if not self.force and executable_for(date).is_file():
                return self._already(date)
        self.log(
            "files.openscad.org publishes no current OpenSCAD for Linux arm64; "
            f"building {date} from source"
        )
        commit = self._commit_at(date)
        submodules = self._submodules(commit)
        return self._put_in_place(
            date, lambda staging: self._build(date, commit, submodules, staging)
        )

    def _api(self, url: str):
        try:
            body = self.fetch(url)
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429):
                raise InstallError(
                    f"GitHub's API refused {url} ({exc.code}): it answers 60 requests an hour "
                    "from one address without an account; try again later"
                ) from exc
            raise
        try:
            return json.loads(body.decode("utf-8"))
        except ValueError as exc:
            raise InstallError(f"{url} did not answer JSON") from exc

    def _commit_at(self, date: str) -> str:
        """The last commit on OpenSCAD's default branch at or before ``date``."""
        repo = self._api(f"{GITHUB_API}/repos/{OPENSCAD_REPO}")
        branch = repo.get("default_branch") if isinstance(repo, dict) else None
        if not isinstance(branch, str) or not BRANCH_RE.match(branch) or ".." in branch:
            raise InstallError(f"GitHub names no usable default branch for OpenSCAD: {branch!r}")
        until = f"{check_date(date).replace('.', '-')}T23:59:59Z"
        commits = self._api(
            f"{GITHUB_API}/repos/{OPENSCAD_REPO}/commits"
            f"?sha={quote(branch, safe='')}&until={until}&per_page=1"
        )
        if not isinstance(commits, list) or not commits or not isinstance(commits[0], dict):
            raise InstallError(f"no commit on OpenSCAD's {branch} at or before {date}")
        commit = check_sha(commits[0].get("sha"))
        self.log(f"{date}: the last commit on {OPENSCAD_REPO} {branch} by then is {commit}")
        return commit

    def _submodules(self, commit: str) -> List[Submodule]:
        """Each submodule ``.gitmodules`` names at ``commit``, at the commit it pins."""
        answer = self._api(f"{GITHUB_API}/repos/{OPENSCAD_REPO}/contents/.gitmodules?ref={commit}")
        try:
            text = base64.b64decode(answer["content"]).decode("utf-8")
        except (KeyError, TypeError, ValueError) as exc:
            raise InstallError(f"no .gitmodules in OpenSCAD at {commit}") from exc
        named = [(path, *github_repo(url)) for path, url in parse_gitmodules(text)]
        found = []
        for path, owner, repo in named:
            info = self._api(f"{GITHUB_API}/repos/{OPENSCAD_REPO}/contents/{path}?ref={commit}")
            if not isinstance(info, dict) or info.get("type") != "submodule":
                raise InstallError(f"{path} is not a submodule of OpenSCAD at {commit}")
            found.append(Submodule(path, owner, repo, check_sha(info.get("sha"))))
            self.log(f"  {path}: {owner}/{repo} at {found[-1].sha}")
        return found

    def _source(self, owner: str, repo: str, commit: str, dest: Path) -> None:
        url = f"{CODELOAD}/{owner}/{repo}/tar.gz/{check_sha(commit)}"
        self.log(f"Downloading {url}")
        unpack_tarball(self.fetch(url), dest)

    def _build(self, date: str, commit: str, submodules: List[Submodule], staging: Path) -> dict:
        """Download the source and its submodules, configure, build and install
        into ``staging``; the source and the build tree are removed whatever
        happened, and a failed build's log is kept beside the installs."""
        home = openscad_dir()
        work = Path(tempfile.mkdtemp(prefix=f".build.{date}.", suffix=".tmp", dir=home))
        log_path, kept = work / "build.log", home / f"build-{date}.log"
        try:
            src = work / "src"
            src.mkdir()
            owner, repo = OPENSCAD_REPO.split("/")
            self._source(owner, repo, commit, src)
            for sub in submodules:
                dest = src.joinpath(*sub.path.split("/"))
                dest.mkdir(parents=True, exist_ok=True)
                if any(dest.iterdir()):
                    raise InstallError(f"{sub.path} is not empty in OpenSCAD's tarball")
                self._source(sub.owner, sub.repo, sub.sha, dest)
            self._compile(date, commit, src, work / "build", staging, log_path, kept)
            manifold = self._check_manifold(staging / "bin" / "openscad")
            shutil.copy2(log_path, staging / "build.log")
        except BaseException:
            if log_path.exists():
                shutil.copy2(log_path, kept)
            raise
        finally:
            shutil.rmtree(work, ignore_errors=True)
        kept.unlink(missing_ok=True)
        return {
            "method": SOURCE,
            "executable": "bin/openscad",
            "commit": commit,
            "submodules": {sub.path: sub.sha for sub in submodules},
            "manifold": manifold,
        }

    def _compile(
        self,
        date: str,
        commit: str,
        src: Path,
        build: Path,
        prefix: Path,
        log_path: Path,
        kept: Path,
    ) -> None:
        cmake = shutil.which("cmake") or "cmake"
        jobs = self.jobs or default_jobs()
        configure = [
            cmake,
            "-S",
            str(src),
            "-B",
            str(build),
            *CMAKE_FLAGS,
            f"-DCMAKE_INSTALL_PREFIX={prefix}",
            f"-DOPENSCAD_VERSION={date}",
            f"-DOPENSCAD_COMMIT={commit[:12]}",
        ]
        self.log("Configuring (cmake)")
        self._run_logged(configure, log_path, kept, "cmake could not configure the build")
        self.log(
            f"Building with {jobs} jobs (--jobs N to change it); on a small board this "
            "takes an hour or more"
        )
        started = time.monotonic()
        self._run_logged(
            [cmake, "--build", str(build), "-j", str(jobs)],
            log_path,
            kept,
            "the build failed",
            progress=True,
        )
        self.log(f"Built in {round((time.monotonic() - started) / 60)} min")
        self._run_logged([cmake, "--install", str(build)], log_path, kept, "cmake --install failed")

    _PERCENT = re.compile(r"^\[\s*(\d+)%\]")

    def _run_logged(
        self, cmd: List[str], log_path: Path, kept: Path, failed: str, progress: bool = False
    ) -> None:
        """Run a build step, every line it prints into the build log, and each step
        of ``[ NN%]`` progress to the log here as it comes."""
        from .stays_local import subprocess_env

        tail: collections.deque = collections.deque(maxlen=25)
        last = None
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"$ {' '.join(cmd)}\n")
            log_file.flush()
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=subprocess_env(),
                )
            except OSError as exc:
                raise InstallError(f"{failed}: {exc}") from exc
            with proc:
                try:
                    assert proc.stdout is not None
                    for line in proc.stdout:
                        log_file.write(line)
                        tail.append(line.rstrip())
                        match = self._PERCENT.match(line) if progress else None
                        if match and match.group(1) != last:
                            last = match.group(1)
                            self.log(line.rstrip())
                    code = proc.wait()
                except BaseException:
                    proc.kill()
                    raise
        if code != 0:
            shown = "\n".join(tail)
            raise InstallError(f"{failed} (exit {code}); the whole log is kept at {kept}:\n{shown}")

    def _check_manifold(self, exe: Path) -> str:
        """Manifold's version as the build reports it, once a cube renders with it."""
        _code, said = _run(exe, "--info")
        match = re.search(r"Manifold version:\s*(\S[^\r\n]*)", said)
        if match is None or not re.match(r"\d", match.group(1)):
            named = match.group(1).strip() if match else "its --info names no Manifold"
            raise InstallError(f"OpenSCAD was built without Manifold ({named})")
        with tempfile.TemporaryDirectory() as tmp:
            cube, stl = Path(tmp) / "cube.scad", Path(tmp) / "cube.stl"
            cube.write_text("cube(1);\n")
            code, said = _run(exe, "--backend=manifold", "-o", str(stl), str(cube), timeout=300)
            if code != 0 or not stl.is_file() or stl.stat().st_size == 0:
                raise InstallError(
                    f"the build does not render with Manifold: {said.strip()[-500:]}"
                )
        version = match.group(1).strip()
        self.log(f"Manifold {version}: a cube renders with it")
        return version


def _bundle_executable(app: Path) -> str:
    """The executable a macOS bundle names in its Info.plist (OpenSCAD's: OpenSCAD)."""
    try:
        with open(app / "Contents" / "Info.plist", "rb") as f:
            name = plistlib.load(f).get("CFBundleExecutable")
    except (OSError, ValueError, plistlib.InvalidFileException):
        name = None
    return name if isinstance(name, str) and NAME_RE.match(name) else "OpenSCAD"


def _remove_empty(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        pass
