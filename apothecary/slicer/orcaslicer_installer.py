"""Install a pinned OrcaSlicer release into the tools dir, natively on each platform.

``apothecary slicer install`` fetches the release pinned below from where its
publisher puts it -- the GitHub releases of OrcaSlicer/OrcaSlicer -- checks it
before it is opened, and puts it under ``tools_dir()/orcaslicer/<version>/``
with ``install.json`` beside it saying what it is, and
``tools_dir()/orcaslicer/current`` naming the release in use. What an install
does depends on the machine (``openscad_installer.host()``: its hardware, not
what an emulated Python says it is):

- **Linux x86_64 and arm64**: the release's AppImage, run as it is, as the
  OpenSCAD installer runs OpenSCAD's. Its printer profiles are read at every
  slice, and an AppImage cannot be read without mounting it, so its
  ``resources/profiles`` folder is extracted beside it (``--appimage-extract``,
  which needs no FUSE; the runtime's pattern matches a folder and takes it
  whole, while ``*`` stops at a ``/``, so a pattern of JSON files would take
  the vendors' indexes and none of their profiles).
  Where there is no FUSE the image cannot mount itself to run; that failure is
  known by what it prints, and the whole image is extracted and
  ``squashfs-root/AppRun`` run instead.
- **macOS**, Intel and Apple Silicon: the release's universal ``.dmg``, attached
  read-only with ``hdiutil``, ``OrcaSlicer.app`` copied out of it, and the image
  detached whatever happened.
- **Windows x64 and arm64**: the release's portable zip for the machine,
  unpacked (no installer, no admin): ``orca-slicer.exe`` with its files and its
  ``resources`` beside it.
- Anything else is refused, saying what is published; ``APOTHECARY_ORCASLICER``
  names an OrcaSlicer installed another way.

**Which version it is** is what ``--help`` names first (``OrcaSlicer-2.4.2:``).
On Windows ``orca-slicer.exe`` is a GUI-subsystem program (read from its PE
header), the only launcher the release ships, and one may print nothing through
a pipe; when it runs (exit 0) and prints nothing, its version resource is read
(``version_resource``) -- its ``ProductVersion`` or ``FileVersion`` string. The
2.4.2 release leaves both empty (its build id) and its fixed version numbers say
2.0.0.0 (``SLIC3R_VERSION``, never moved), so neither names the release: then,
for the release this installer put in place, the version is the pinned asset's,
which its digest vouches for (``identify``).

**Checked before it is opened.** The release publishes no checksum file, so a
download is checked against the SHA-256 GitHub publishes for the asset
(api.github.com's release record, its ``digest``), and that digest must be the
one pinned here for the asset, as it was when the pin was set: a release whose
asset was replaced since is refused, not trusted. Whatever the platform, the
result must run and report the pinned version before it is moved into place
(staged beside it, then renamed).

**The pin moves by hand.** ``ORCASLICER_VERSION`` and the digests in
``ASSETS`` move only together, in a commit that re-runs a real install and a
real slice in a scratch tools dir and says in its body what they did (the hosts
the install reached, the slice's G-code). The owner's decision of 2026-10-10
(docs/plans/slicer-2026-10-10.md).

Every fetch goes through the OpenSCAD installer's tool fetch (``_fetch``,
``_fetch_to``: ``stays_local.tool_fetch``, no proxy), to api.github.com,
github.com and the host GitHub redirects a release asset to -- all in
``stays_local.TOOL_SOURCES`` -- and nowhere else. Stdlib only.
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import shutil
import stat
import struct
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from ..firmware.toolchains import tools_dir
from ..openscad_installer import (
    _fetch,
    _fetch_to,
    _machine_name,
    _parts,
    _platform_label,
    _remove_empty,
    _rename,
    _run,
    binary_archs,
    host,
    needs_fuse,
    runs_here,
)

# Pinned: see the docstring. Each asset's SHA-256 is the digest GitHub published
# for it when the pin was set (api.github.com/repos/OrcaSlicer/OrcaSlicer/releases/
# tags/v2.4.2); the Linux x86_64 AppImage's was also read off the file itself.
ORCASLICER_VERSION = "2.4.2"
REPO = "OrcaSlicer/OrcaSlicer"
TAG = f"v{ORCASLICER_VERSION}"
GITHUB_API = "https://api.github.com/repos"
GITHUB = "https://github.com"
MANIFEST = "install.json"
AGENT = "apothecary-slicer-installer"

APPIMAGE, EXTRACTED, DMG, ZIP = "appimage", "appimage-extracted", "dmg", "zip"

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ASSET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
# What `orca-slicer --help` says first: "OrcaSlicer-2.4.2:".
REPORTED_RE = re.compile(r"OrcaSlicer[- ]v?(\d+\.\d+\.\d+)", re.I)

Log = Callable[[str], None]


class InstallError(RuntimeError):
    """The release could not be found, fetched, verified or put in place here."""


@dataclass(frozen=True)
class Asset:
    """One platform's file of the pinned release, and how it is installed."""

    name: str
    method: str
    sha256: str


ASSETS: Dict[Tuple[str, str], Asset] = {
    ("Linux", "x86_64"): Asset(
        "OrcaSlicer_Linux_AppImage_Ubuntu2404_V2.4.2.AppImage",
        APPIMAGE,
        "d12fb8c8eac1aecd2dfb6377acd48f994f8fa439ed5292fa532dd82880f029fd",
    ),
    ("Linux", "arm64"): Asset(
        "OrcaSlicer_Linux_AppImage_Ubuntu2404_aarch64_V2.4.2.AppImage",
        APPIMAGE,
        "e1a07275a25f176626c55a5df39e91bc4476d8c28ee4a3192ff758e29dd5c3ba",
    ),
    ("Darwin", "x86_64"): Asset(
        "OrcaSlicer_Mac_universal_V2.4.2.dmg",
        DMG,
        "e15e7bb1b66214ec6e96b169b388004179c4f5f705effcdaf8c80d4992ee0366",
    ),
    ("Darwin", "arm64"): Asset(
        "OrcaSlicer_Mac_universal_V2.4.2.dmg",
        DMG,
        "e15e7bb1b66214ec6e96b169b388004179c4f5f705effcdaf8c80d4992ee0366",
    ),
    ("Windows", "x86_64"): Asset(
        "OrcaSlicer_Windows_V2.4.2_x64_portable.zip",
        ZIP,
        "feba3009dfb9d268779cca5758a1a5bc3b7d0722bf8fa48d5c57340de975d6be",
    ),
    ("Windows", "arm64"): Asset(
        "OrcaSlicer_Windows_V2.4.2_arm64_portable.zip",
        ZIP,
        "428a26878ca39dcd87f52fe3faea55aa76c9d477c369377f62e047194cdef06b",
    ),
}

WHAT_INSTALL_DOES = {
    APPIMAGE: "the release's AppImage, its printer profiles extracted beside it "
    "(the whole image extracted where there is no FUSE)",
    DMG: "OrcaSlicer.app copied out of the release's universal disk image",
    ZIP: "the release's portable zip for this machine, unpacked",
}

SERVED = (
    "OrcaSlicer publishes Linux x86_64 and arm64 AppImages, a universal macOS app and "
    "Windows x64 and arm64 portable zips"
)


def asset_for(system: Optional[str] = None, machine: Optional[str] = None) -> Asset:
    """This platform's asset of the pinned release (``host()`` unless given), or
    InstallError where none is published."""
    if system is None or machine is None:
        here = host()
        system, machine = system or here[0], machine or here[1]
    found = ASSETS.get((system, _machine_name(machine)))
    if found is None:
        raise InstallError(
            f"no OrcaSlicer for {_platform_label(system, _machine_name(machine))}: {SERVED}. "
            "Install it another way and set APOTHECARY_ORCASLICER to it"
        )
    return found


def what_install_does() -> str:
    """This machine, and what ``apothecary slicer install`` does on it."""
    system, machine = host()
    label = _platform_label(system, machine)
    try:
        return f"{label}: an install is {WHAT_INSTALL_DOES[asset_for(system, machine).method]}"
    except InstallError as exc:
        return f"{label}: {exc}"


def check_version(text: str) -> str:
    """A version spliced into a URL and a folder name is three numbers, or InstallError."""
    if not isinstance(text, str) or not VERSION_RE.match(text):
        raise InstallError(f"not an OrcaSlicer version: {text!r} (want X.Y.Z)")
    return text


def reported_version(said: str) -> Optional[str]:
    """The version OrcaSlicer's ``--help`` names, or None."""
    match = REPORTED_RE.search(said or "")
    return match.group(1) if match else None


# --- a Windows program's version resource ----------------------------------------------

RT_VERSION = 16
FIXED_SIGNATURE = 0xFEEF04BD
_VERSION_IN = re.compile(r"(\d+)\.(\d+)\.(\d+)")


@dataclass
class VersionResource:
    """What a Windows program's version resource says: its strings (``ProductVersion``,
    ``FileVersion`` and the rest) and its fixed version numbers."""

    strings: Dict[str, str]
    fixed_file: Optional[str] = None
    fixed_product: Optional[str] = None

    def named(self) -> Optional[str]:
        """The version its ``ProductVersion`` or ``FileVersion`` string names, X.Y.Z."""
        for key in ("ProductVersion", "FileVersion"):
            match = _VERSION_IN.search(self.strings.get(key, ""))
            if match:
                return ".".join(str(int(n)) for n in match.groups())
        return None


def _u16(data: bytes, at: int) -> int:
    return struct.unpack_from("<H", data, at)[0]


def _u32(data: bytes, at: int) -> int:
    return struct.unpack_from("<I", data, at)[0]


def _align(at: int) -> int:
    return (at + 3) & ~3


def _node(block: bytes, at: int) -> Tuple[str, bytes, int, int]:
    """One structure of a version resource: its key, its value's bytes, where its
    children start and where it ends."""
    length, value_length, kind = struct.unpack_from("<HHH", block, at)
    key_end = at + 6
    while block[key_end : key_end + 2] != b"\x00\x00":
        key_end += 2
        if key_end >= len(block):
            raise ValueError("a version resource key without its end")
    key = block[at + 6 : key_end].decode("utf-16-le")
    value_at = _align(key_end + 2)
    size = value_length * 2 if kind == 1 else value_length
    return key, block[value_at : value_at + size], _align(value_at + size), at + length


def _version_info(block: bytes) -> VersionResource:
    key, value, child, end = _node(block, 0)
    if key != "VS_VERSION_INFO":
        raise ValueError("not a version resource")
    found = VersionResource(strings={})
    if len(value) >= 24 and _u32(value, 0) == FIXED_SIGNATURE:
        file_ms, file_ls, product_ms, product_ls = struct.unpack_from("<4I", value, 8)
        found.fixed_file = f"{file_ms >> 16}.{file_ms & 0xFFFF}.{file_ls >> 16}.{file_ls & 0xFFFF}"
        found.fixed_product = (
            f"{product_ms >> 16}.{product_ms & 0xFFFF}.{product_ls >> 16}.{product_ls & 0xFFFF}"
        )
    while child < end:
        name, _value, tables, child_end = _node(block, child)
        if child_end <= child:
            break
        if name == "StringFileInfo":
            while tables < child_end:
                _lang, _v, entry, table_end = _node(block, tables)
                if table_end <= tables:
                    break
                while entry < table_end:
                    string_key, string_value, _c, entry_end = _node(block, entry)
                    if entry_end <= entry:
                        break
                    found.strings[string_key] = string_value.decode("utf-16-le").rstrip("\x00")
                    entry = _align(entry_end)
                tables = _align(table_end)
        child = _align(child_end)
    return found


def version_resource(path: Path) -> Optional[VersionResource]:
    """The version resource of a Windows program (a PE file), read from its
    resource section: the first language of the first ``RT_VERSION`` entry. None
    for a file that is not one or has none."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    try:
        if data[:2] != b"MZ":
            return None
        pe = _u32(data, 0x3C)
        if data[pe : pe + 4] != b"PE\x00\x00":
            return None
        count, optional_size = _u16(data, pe + 6), _u16(data, pe + 20)
        optional = pe + 24
        directories = optional + (96 if _u16(data, optional) == 0x10B else 112)
        resources_rva = _u32(data, directories + 2 * 8)
        if not resources_rva:
            return None
        sections = []
        for i in range(count):
            at = optional + optional_size + 40 * i
            virtual_size, address, raw_size, raw = struct.unpack_from("<4I", data, at + 8)
            sections.append((address, max(virtual_size, raw_size), raw))

        def offset(rva: int) -> int:
            for address, size, raw in sections:
                if address <= rva < address + size:
                    return raw + rva - address
            raise ValueError("an address outside every section")

        root = offset(resources_rva)

        def entries(directory: int) -> List[Tuple[int, int]]:
            listed = _u16(data, directory + 12) + _u16(data, directory + 14)
            return [
                (_u32(data, directory + 16 + 8 * i), _u32(data, directory + 20 + 8 * i))
                for i in range(listed)
            ]

        found = next(
            (to for name, to in entries(root) if name == RT_VERSION and to & 0x80000000), None
        )
        if found is None:
            return None
        names = root + (found & 0x7FFFFFFF)
        languages = root + (entries(names)[0][1] & 0x7FFFFFFF)
        entry = root + (entries(languages)[0][1] & 0x7FFFFFFF)
        start, size = offset(_u32(data, entry)), _u32(data, entry + 4)
        return _version_info(data[start : start + size])
    except (struct.error, ValueError, IndexError, UnicodeDecodeError, StopIteration):
        return None


def identify(
    program: Path, code: int, said: str, vouched: Optional[str] = None
) -> Tuple[Optional[str], str]:
    """Which version ``program`` is, from what its ``--help`` printed (``code``,
    ``said``), and how that is known: what ``--help`` names; else -- when it ran
    and printed nothing through the pipe, as a Windows GUI program may -- what its
    version resource names; else ``vouched``, the version of the pinned asset an
    install verified by its digest."""
    named = reported_version(said)
    if named:
        return named, "--help"
    if code != 0 or (said or "").strip():
        return None, "--help"
    found = version_resource(program)
    if found is not None and found.named():
        return found.named(), "its version resource"
    if vouched:
        return vouched, (
            "the pinned asset's digest: it ran and printed nothing through a pipe, and its "
            "version resource names no version"
        )
    return None, "nothing: it printed nothing through a pipe, and its version resource names none"


# --- where it lives ------------------------------------------------------------------


def home() -> Path:
    return tools_dir() / "orcaslicer"


def _plain(rel: object) -> Optional[str]:
    """A relative path that stays inside the folder it is joined to, or None."""
    if not isinstance(rel, str) or not rel or rel.startswith(("/", "\\")):
        return None
    parts = rel.split("/")
    if any(part in ("", ".", "..") for part in parts) or re.match(r"^[A-Za-z]:", rel):
        return None
    return rel


def read_manifest(version: str) -> dict:
    """What ``install.json`` of an installed release says, or {}."""
    try:
        data = json.loads((home() / check_version(version) / MANIFEST).read_text("utf-8"))
    except (OSError, ValueError, InstallError):
        return {}
    return data if isinstance(data, dict) else {}


def _in_install(version: str, key: str) -> Optional[Path]:
    rel = _plain(read_manifest(version).get(key))
    return home() / version / rel if rel else None


def executable_for(version: str) -> Optional[Path]:
    """The program an install of ``version`` runs, where its ``install.json`` says."""
    return _in_install(version, "executable")


def resources_for(version: str) -> Optional[Path]:
    """The ``resources`` folder of an install of ``version`` (its printer profiles)."""
    return _in_install(version, "resources")


def current_version() -> Optional[str]:
    """The release ``current`` names, if it is a version; anything else names nothing."""
    try:
        text = (home() / "current").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text if VERSION_RE.match(text) else None


def current_executable() -> Optional[Path]:
    """The installed release in use, or None."""
    version = current_version()
    if version is None:
        return None
    path = executable_for(version)
    return path if path is not None and path.is_file() else None


def _write_current(version: str) -> None:
    folder = home()
    tmp = folder / f".current.{os.getpid()}.tmp"
    tmp.write_text(check_version(version) + "\n", encoding="utf-8")
    os.replace(tmp, folder / "current")


# --- the published digest --------------------------------------------------------------


def published_digest(asset: str, fetch: Callable[[str], bytes]) -> str:
    """The SHA-256 GitHub publishes for one asset of the pinned release."""
    if not ASSET_RE.match(asset):
        raise InstallError(f"not an asset name: {asset!r}")
    url = f"{GITHUB_API}/{REPO}/releases/tags/{TAG}"
    try:
        data = json.loads(fetch(url).decode("utf-8"))
    except ValueError as exc:
        raise InstallError(f"{url} did not answer JSON") from exc
    listed = data.get("assets") if isinstance(data, dict) else None
    for item in listed if isinstance(listed, list) else []:
        if isinstance(item, dict) and item.get("name") == asset:
            algo, _, value = str(item.get("digest") or "").partition(":")
            if algo == "sha256" and SHA256_RE.match(value.lower()):
                return value.lower()
            raise InstallError(f"{REPO} {TAG}: GitHub publishes no SHA-256 for {asset}")
    raise InstallError(f"{REPO} {TAG} publishes no {asset}")


# --- unpacking, held inside its folder ----------------------------------------------


def unpack_zip(archive: Path, dest: Path) -> int:
    """Every member of a zip into ``dest``; a member that would land outside refuses
    the whole zip before anything is written. The members written."""
    with zipfile.ZipFile(archive) as zf:
        members = []
        for info in zf.infolist():
            parts = _parts(info.filename)
            if parts is None:
                raise InstallError(f"the zip names a path outside its folder: {info.filename!r}")
            if parts:
                members.append((info, parts))
        for info, parts in members:
            target = dest.joinpath(*parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    return len(members)


# What an AppImage install extracts beside the image: the folder of profiles, whole.
PROFILES_PATTERN = "resources/profiles/*"


def has_profiles(resources: Path) -> bool:
    """Whether ``resources`` holds OrcaSlicer's printer profiles: a vendor's index
    and its machine profiles in the vendor's folder."""
    profiles = resources / "profiles"
    return profiles.is_dir() and any(
        (index.with_suffix("") / "machine").is_dir() for index in profiles.glob("*.json")
    )


def _help(program: Path) -> Tuple[int, str]:
    """``program --help``, run in a folder of its own: OrcaSlicer writes a
    ``result.json`` wherever it is run, even to say how it is used."""
    with tempfile.TemporaryDirectory(prefix="apothecary-orcaslicer-") as aside:
        return _run(program, "--help", timeout=180, cwd=aside)


def _executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _bundle_executable(app: Path) -> str:
    """The executable a macOS bundle names in its Info.plist (OrcaSlicer's: OrcaSlicer)."""
    try:
        with open(app / "Contents" / "Info.plist", "rb") as f:
            name = plistlib.load(f).get("CFBundleExecutable")
    except (OSError, ValueError, plistlib.InvalidFileException):
        name = None
    return name if isinstance(name, str) and ASSET_RE.match(name) else "OrcaSlicer"


# --- one install ---------------------------------------------------------------------


class OrcaSlicerInstaller:
    """Pinned asset → GitHub's digest, which must be the pinned one → download, checked
    → unpacked → it runs and says its version → moved in → current."""

    def __init__(
        self,
        force: bool = False,
        log: Optional[Log] = None,
        fetch: Optional[Callable[[str], bytes]] = None,
        fetch_to: Optional[Callable[[str, Path], str]] = None,
        system: Optional[str] = None,
        machine: Optional[str] = None,
    ):
        self.force = force
        self.log = log or (lambda _line: None)
        self._fetch = fetch
        self._fetch_to = fetch_to
        self.system, self.machine = system, machine

    def fetch(self, url: str) -> bytes:
        return self._fetch(url) if self._fetch else _fetch(url, agent=AGENT)

    def fetch_to(self, url: str, path: Path) -> str:
        return self._fetch_to(url, path) if self._fetch_to else _fetch_to(url, path, agent=AGENT)

    def install(self) -> Path:
        version = check_version(ORCASLICER_VERSION)
        asset = asset_for(self.system, self.machine)
        installed = executable_for(version)
        if not self.force and installed is not None and installed.is_file():
            self.log(
                f"OrcaSlicer {version} already installed at {installed}; --force to fetch it again"
            )
            _write_current(version)
            return installed
        want = published_digest(asset.name, self.fetch)
        if want != asset.sha256:
            raise InstallError(
                f"GitHub publishes {want} for {asset.name}, not {asset.sha256}, the digest "
                f"pinned for it: the release has changed since it was pinned, and is not trusted"
            )
        self.log(f"{asset.name}: GitHub publishes SHA-256 {want[:12]}…, the pinned digest")
        folder = home()
        folder.mkdir(parents=True, exist_ok=True)
        url = f"{GITHUB}/{REPO}/releases/download/{TAG}/{asset.name}"
        fd, held = tempfile.mkstemp(prefix=".download.", suffix=".tmp", dir=folder)
        os.close(fd)
        download = Path(held)
        try:
            self.log(f"Downloading {url}")
            got = self.fetch_to(url, download)
            if got != want:
                raise InstallError(
                    f"checksum mismatch for {asset.name}: expected {want}, got {got}"
                )
            self.log(f"SHA-256 verified ({want[:12]}…)")
            populate = {APPIMAGE: self._appimage, DMG: self._disk_image, ZIP: self._portable_zip}
            return self._put_in_place(version, asset, populate[asset.method](asset, download))
        finally:
            download.unlink(missing_ok=True)

    def _put_in_place(self, version: str, asset: Asset, populate: Callable[[Path], dict]) -> Path:
        """Stage the install beside where it goes, check it runs and says the pinned
        version, record what it is, then rename it into place."""
        folder = home()
        staging = Path(tempfile.mkdtemp(prefix=f".{version}.", suffix=".tmp", dir=folder))
        staging.chmod(0o755)  # mkdtemp makes it the owner's alone; it is a tools directory
        try:
            record = populate(staging)
            exe = staging / record["executable"]
            code, said = _help(exe)
            reported, how = identify(exe, code, said, vouched=version)
            if reported != version:
                raise InstallError(
                    f"OrcaSlicer {version} does not run here or reports "
                    f"{reported or 'no version'} (exit {code}): {said.strip()[-400:]}"
                )
            self.log(f"OrcaSlicer {reported} runs" + ("" if how == "--help" else f" ({how})"))
            record["identified_by"] = how
            if not has_profiles(staging / record["resources"]):
                raise InstallError(f"no printer profiles in {record['resources']}")
            record.setdefault("archs", binary_archs(exe))
            record.update(
                version=version,
                asset=asset.name,
                sha256=asset.sha256,
                platform=_platform_label(*host()),
            )
            if record["archs"]:
                self.log(f"On this machine: {runs_here(record['archs'])}")
            (staging / MANIFEST).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
            final = folder / version
            if final.exists():
                aside = Path(tempfile.mkdtemp(prefix=f".{version}.old.", suffix=".tmp", dir=folder))
                _rename(final, aside / version)
                _rename(staging, final)
                shutil.rmtree(aside, ignore_errors=True)
            else:
                _rename(staging, final)
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
        _write_current(version)
        path = executable_for(version)
        assert path is not None
        self.log(f"Installed {path}; current -> {version}")
        return path

    # Linux ----------------------------------------------------------------------------

    def _appimage(self, asset: Asset, download: Path) -> Callable[[Path], dict]:
        def populate(staging: Path) -> dict:
            image = staging / "OrcaSlicer.AppImage"
            shutil.move(str(download), image)
            _executable(image)
            archs = binary_archs(image)
            self.log("Extracting its printer profiles (they are read at every slice)")
            code, said = _run(
                image, "--appimage-extract", PROFILES_PATTERN, timeout=900, cwd=staging
            )
            extracted = staging / "squashfs-root"
            if code != 0 or not has_profiles(extracted / "resources"):
                raise InstallError(
                    f"{asset.name}: its profiles could not be extracted: {said[-400:]}"
                )
            extracted.chmod(0o755)  # the runtime makes it the owner's alone
            code, said = _help(image)
            if code == 0 or not needs_fuse(said):
                return {
                    "method": APPIMAGE,
                    "executable": image.name,
                    "resources": "squashfs-root/resources",
                    "archs": archs,
                }
            self.log("The AppImage cannot mount itself here (no FUSE); extracting it whole instead")
            shutil.rmtree(extracted)
            code, said = _run(image, "--appimage-extract", timeout=900, cwd=staging)
            if code != 0 or not (extracted / "AppRun").exists():
                raise InstallError(f"{asset.name} could not be extracted: {said.strip()[-500:]}")
            extracted.chmod(0o755)
            image.unlink()
            return {
                "method": EXTRACTED,
                "executable": "squashfs-root/AppRun",
                "resources": "squashfs-root/resources",
                "archs": archs,
            }

        return populate

    # macOS ----------------------------------------------------------------------------

    def _disk_image(self, asset: Asset, download: Path) -> Callable[[Path], dict]:
        def populate(staging: Path) -> dict:
            image = staging.parent / f"{staging.name}.dmg"
            shutil.move(str(download), image)
            try:
                self._copy_app_out(image, asset.name, staging / "OrcaSlicer.app")
            finally:
                image.unlink(missing_ok=True)
            app = staging / "OrcaSlicer.app"
            rel = f"OrcaSlicer.app/Contents/MacOS/{_bundle_executable(app)}"
            return {
                "method": DMG,
                "executable": rel,
                "resources": "OrcaSlicer.app/Contents/Resources",
                "archs": binary_archs(staging / rel),
            }

        return populate

    def _copy_app_out(self, image: Path, name: str, dest: Path) -> None:
        """Attach the disk image read-only, copy its app to ``dest``, and detach it
        whatever happened."""
        hdiutil = shutil.which("hdiutil")
        if hdiutil is None:
            raise InstallError("hdiutil is not on PATH; it comes with macOS")
        mount = Path(tempfile.mkdtemp(prefix="apothecary-orcaslicer-"))
        code, said = _run(
            Path(hdiutil),
            "attach",
            "-nobrowse",
            "-readonly",
            "-noautoopen",
            "-mountpoint",
            str(mount),
            str(image),
        )
        if code != 0:
            _remove_empty(mount)
            raise InstallError(f"hdiutil could not attach {name}: {said.strip()}")
        try:
            apps = [p for p in mount.iterdir() if p.suffix == ".app" and p.is_dir()]
            app = mount / "OrcaSlicer.app" if (mount / "OrcaSlicer.app").is_dir() else None
            if app is None:
                if len(apps) != 1:
                    raise InstallError(f"no OrcaSlicer.app in {name}")
                app = apps[0]
            self.log(f"Copying {app.name} out of {name}")
            ditto = shutil.which("ditto")
            if ditto:
                code, said = _run(Path(ditto), str(app), str(dest), timeout=900)
                if code != 0:
                    raise InstallError(f"ditto could not copy {app.name}: {said.strip()}")
            else:
                shutil.copytree(app, dest, symlinks=True)
        finally:
            for extra in ((), ("-force",)):
                code, said = _run(Path(hdiutil), "detach", str(mount), *extra)
                if code == 0:
                    break
            else:
                self.log(f"hdiutil could not detach {mount}: {said.strip()}")
            _remove_empty(mount)

    # Windows --------------------------------------------------------------------------

    def _portable_zip(self, asset: Asset, download: Path) -> Callable[[Path], dict]:
        def populate(staging: Path) -> dict:
            self.log(f"Unpacking {asset.name}")
            unpack_zip(download, staging)
            exe = staging / "orca-slicer.exe"
            if not exe.is_file():
                raise InstallError(f"no orca-slicer.exe in {asset.name}")
            _executable(exe)  # nothing on Windows; a zip keeps no mode bits elsewhere
            return {
                "method": ZIP,
                "executable": "orca-slicer.exe",
                "resources": "resources",
                "archs": binary_archs(exe),
            }

        return populate


@dataclass
class Installed:
    """One installed release, as ``slicer status`` says it."""

    version: str
    executable: Path
    resources: Optional[Path]
    platform: str
    how: str
    runs: str


HOW = {
    APPIMAGE: "AppImage, run through FUSE; its profiles extracted beside it",
    EXTRACTED: "AppImage extracted (no FUSE here), run as squashfs-root/AppRun",
    DMG: "OrcaSlicer.app from the disk image",
    ZIP: "portable zip, unpacked",
}


def installed_versions() -> List[str]:
    folder = home()
    if not folder.is_dir():
        return []
    found = []
    for p in folder.iterdir():
        if VERSION_RE.match(p.name):
            exe = executable_for(p.name)
            if exe is not None and exe.is_file():
                found.append(p.name)
    return sorted(found, key=lambda v: tuple(int(n) for n in v.split(".")))


def describe(version: str) -> Installed:
    record = read_manifest(version)
    exe = executable_for(version) or home() / version
    archs = record.get("archs")
    if not isinstance(archs, list) or not all(isinstance(a, str) for a in archs):
        archs = binary_archs(exe)
    label = record.get("platform") if isinstance(record.get("platform"), str) else "?"
    method = record.get("method") if record.get("method") in HOW else None
    return Installed(
        version=version,
        executable=exe,
        resources=resources_for(version),
        platform=label,
        how=HOW.get(method, "installed by an older apothecary"),
        runs=runs_here(archs) if archs else "architecture not known",
    )
