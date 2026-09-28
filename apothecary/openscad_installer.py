"""Install an OpenSCAD development snapshot from files.openscad.org into the tools dir.

A snapshot is named by its date, and the date is its version: three numbers,
``YYYY.MM.DD``, checked before it is spliced into anything. The host's own
directory listing (``https://files.openscad.org/snapshots/``) names each
night's file for each platform and its size; the file beside it with
``.sha256`` appended is its published SHA-256. An install fetches the listing,
the snapshot and its checksum -- through ``tool_fetch`` (apothecary/stays_local.py),
to that host alone, with no proxy -- and verifies the size the listing gives,
the checksum, and that the binary runs and reports the date it was asked for,
before it is moved into place. (The host also publishes a detached ``.asc``
signature; checking it needs GnuPG and a key this program does not carry, so
it is not checked.)

Where it goes: ``tools_dir()/openscad/<date>/openscad``, and
``tools_dir()/openscad/current`` is a text file naming the date in use. The
resolver in apothecary/projects/parts/stl_renderer.py reads it.

Linux x86_64 only: the snapshot there is one AppImage that runs as it is.
macOS snapshots are a ``.dmg`` and Windows ones a ``.zip`` (or an installer);
both would need unpacking this module does not do, so they are refused by
name. Stdlib only.
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import stat
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from .firmware.toolchains import tools_dir

SNAPSHOTS = "https://files.openscad.org/snapshots/"

# Snapshots from this date on take ``--backend=manifold``. (``--enable=manifold``
# is the older spelling, which later snapshots accept and then render with CGAL.)
MANIFOLD_SINCE = (2024, 9, 28)

DATE_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")

Log = Callable[[str], None]
Fetch = Callable[[str], bytes]


class InstallError(RuntimeError):
    """The snapshot could not be found, fetched, verified or put in place."""


def _fetch(url: str, timeout: int = 300) -> bytes:
    """A tool fetch: a GET from files.openscad.org, and nowhere else.

    ``tool_fetch`` refuses a URL whose host is not a tool source before
    anything is opened, and holds the sockets under this call to those hosts.
    """
    from .stays_local import tool_fetch

    req = urllib.request.Request(url, headers={"User-Agent": "apothecary-openscad-installer"})
    # No proxy from the environment: a proxy is a place the fetch would go instead.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with tool_fetch(url), opener.open(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


def check_date(text: str) -> str:
    """A snapshot date, ``YYYY.MM.DD``, or InstallError: it becomes part of a URL
    and a directory name, so it is three numbers and nothing else."""
    if not isinstance(text, str) or not DATE_RE.match(text):
        raise InstallError(f"not an OpenSCAD snapshot date: {text!r} (want YYYY.MM.DD)")
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


# --- where it lives ------------------------------------------------------------------


def openscad_dir() -> Path:
    return tools_dir() / "openscad"


def _exe_name() -> str:
    return "openscad"


def executable_for(date: str) -> Path:
    return openscad_dir() / check_date(date) / _exe_name()


def installed_versions() -> list[str]:
    """The snapshot dates installed, oldest first."""
    home = openscad_dir()
    if not home.is_dir():
        return []
    return sorted(
        p.name for p in home.iterdir() if DATE_RE.match(p.name) and (p / _exe_name()).is_file()
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


# --- the host's listing --------------------------------------------------------------


def snapshot_pattern(system: Optional[str] = None, machine: Optional[str] = None) -> re.Pattern:
    """How this platform's snapshot is named in the listing; InstallError where
    this module does not install one."""
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()
    if system == "Linux" and machine in ("x86_64", "amd64"):
        # OpenSCAD-2026.09.27-x86_64.AppImage; in 2025, OpenSCAD-2025.10.02.ai27993-x86_64.AppImage
        return re.compile(r"^OpenSCAD-(\d{4}\.\d{2}\.\d{2})(?:\.ai(\d+))?-x86_64\.AppImage$")
    if system == "Linux":
        raise InstallError(
            f"no OpenSCAD snapshot for Linux {machine}: files.openscad.org publishes "
            "nightly AppImages for x86_64 only"
        )
    if system == "Darwin":
        raise InstallError(
            "installing a snapshot on macOS is not built: files.openscad.org publishes it "
            "as OpenSCAD-<date>.dmg, a disk image to mount and copy OpenSCAD.app from. "
            "Install it by hand, then set APOTHECARY_OPENSCAD to "
            "<where>/OpenSCAD.app/Contents/MacOS/OpenSCAD"
        )
    if system == "Windows":
        raise InstallError(
            "installing a snapshot on Windows is not built: files.openscad.org publishes it "
            "as OpenSCAD-<date>-x86-64.zip (or an -Installer.exe). Unpack it by hand, then "
            "set APOTHECARY_OPENSCAD to its openscad.exe"
        )
    raise InstallError(f"no OpenSCAD snapshot for {system}/{machine}")


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


def reported_version(executable: Path) -> Optional[str]:
    """What ``executable --version`` prints (OpenSCAD writes it to stderr)."""
    try:
        done = subprocess.run(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in f"{done.stderr}\n{done.stdout}".splitlines():
        if re.search(r"version\s+\d{4}\.", line, re.I):
            return line.strip()
    return None


# --- one install ---------------------------------------------------------------------


class SnapshotInstaller:
    """Find → download → verify (size, SHA-256, it runs and says its date) → move in → current.

    ``snapshot`` is a date, or None for the newest; ``minimum`` an OpenSCAD
    version the snapshot must be at least (``2021.08.24``, ``2021.01``).
    """

    def __init__(
        self,
        snapshot: Optional[str] = None,
        minimum: Optional[str] = None,
        force: bool = False,
        log: Optional[Log] = None,
        fetch: Optional[Fetch] = None,
    ):
        self.snapshot = snapshot
        self.minimum = minimum
        self.force = force
        self.log = log or (lambda _line: None)
        self._fetch = fetch

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
        pattern = snapshot_pattern()
        if self.snapshot is not None:
            self._refuse_below_floor(self.snapshot, floor)
            if not self.force and executable_for(self.snapshot).is_file():
                return self._already(self.snapshot)

        self.log(f"Reading {SNAPSHOTS}")
        listing = parse_listing(self.fetch(SNAPSHOTS).decode("utf-8", "replace"), pattern)
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
        return self._put_in_place(date, body)

    def _already(self, date: str) -> Path:
        path = executable_for(date)
        self.log(f"OpenSCAD snapshot {date} already installed at {path}; --force to fetch it again")
        _write_current(date)
        self.log(f"current -> {date}")
        return path

    def _put_in_place(self, date: str, body: bytes) -> Path:
        home = openscad_dir()
        home.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{date}.", suffix=".tmp", dir=home))
        staging.chmod(0o755)  # mkdtemp makes it the owner's alone; it is a tools directory
        try:
            exe = staging / _exe_name()
            exe.write_bytes(body)
            exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            reported = reported_version(exe)
            if _numbers(reported) != _numbers(date):
                raise InstallError(
                    f"the snapshot for {date} does not run here or reports "
                    f"{reported or 'no version'}"
                )
            self.log(reported)
            final = home / date
            if final.exists():
                aside = Path(tempfile.mkdtemp(prefix=f".{date}.old.", suffix=".tmp", dir=home))
                os.replace(final, aside / date)
                os.replace(staging, final)
                shutil.rmtree(aside, ignore_errors=True)
            else:
                os.replace(staging, final)
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
        _write_current(date)
        path = final / _exe_name()
        self.log(f"Installed {path}; current -> {date}")
        return path
