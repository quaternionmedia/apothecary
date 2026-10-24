"""The OpenSCAD snapshot installer (apothecary/openscad_installer.py), against a
fake files.openscad.org: a listing, an AppImage that is a shell script, and its
published SHA-256; a disk image mounted by a fake ``hdiutil``; a real zip with
a stand-in ``openscad.exe``; an AppImage that fails like a machine without
FUSE; and, for Linux arm64, a fake GitHub (its API and its tarballs) and a fake
``cmake``. The platform is patched in. Nothing here reaches the network."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import plistlib
import stat
import struct
import sys
import tarfile
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from click.testing import CliRunner

from apothecary import openscad_installer as oi

BASE = "https://files.openscad.org/snapshots/"


def _appimage(version: str) -> bytes:
    """A stand-in snapshot: reports ``version`` the way OpenSCAD does (stderr)."""
    return f'#!/bin/sh\necho "OpenSCAD version {version}" >&2\n'.encode()


def _row(name: str, size: int) -> str:
    return f'<a href="{name}">{name}</a>{" " * 8}27-Sep-2026 20:35{" " * 12}{size}\n'


class Host:
    """A files.openscad.org of fixed files; records every URL asked for."""

    def __init__(self, dates=("2026.09.22", "2026.09.27"), ai=None, reports=None):
        self.files: dict[str, bytes] = {}
        self.urls: list[str] = []
        for date in dates:
            self.add(f"OpenSCAD-{date}-x86_64.AppImage", _appimage((reports or {}).get(date, date)))
            # The other platforms' files of the same night, which are not ours.
            self.files[f"OpenSCAD-{date}.dmg"] = b"dmg"
            self.files[f"OpenSCAD-{date}-x86-64.zip"] = b"zip"
            self.files[f"OpenSCAD-{date}-WebAssembly-web.zip"] = b"wasm"
        for name in ai or ():
            self.add(name, _appimage(name.split("-")[1]))
        self.files["OpenSCAD-2021.11.28.ai-aarch64.AppImage"] = b"arm"
        self.sizes: dict[str, int] = {}

    def add(self, name: str, body: bytes) -> None:
        self.files[name] = body
        self.files[name + ".sha256"] = f"{hashlib.sha256(body).hexdigest()}  {name}\n".encode()

    def listing(self) -> bytes:
        rows = "".join(
            _row(name, self.sizes.get(name, len(body))) for name, body in sorted(self.files.items())
        )
        return (
            "<html>\n<head><title>Index of /snapshots/</title></head>\n<body>\n"
            f'<h1>Index of /snapshots/</h1><hr><pre><a href="../">../</a>\n'
            f'<a href="Win7/">Win7/</a>          16-Dec-2021 19:11       -\n{rows}</pre><hr></body>\n'
            "</html>\n"
        ).encode()

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        assert url.startswith(BASE), url
        name = url[len(BASE) :]
        if name == "":
            return self.listing()
        return self.files[name]


@pytest.fixture
def tools(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.setattr(oi.platform, "system", lambda: "Linux")
    monkeypatch.setattr(oi.platform, "machine", lambda: "x86_64")
    # This machine's own answers stay out of it: a Mac's Rosetta, a PC's hardware.
    monkeypatch.setattr(oi, "_rosetta_translated", lambda: False)
    monkeypatch.setattr(oi, "_windows_native_machine", lambda: None)
    # The default renderer is found again inside the test, and forgotten after it.
    from apothecary.projects.parts import stl_renderer

    monkeypatch.setattr(stl_renderer, "_renderer", None)
    return tmp_path / "tools" / "openscad"


def _left_in(tools: Path) -> list:
    return sorted(p.name for p in tools.iterdir()) if tools.exists() else []


def _install(host, **kwargs) -> Path:
    return oi.SnapshotInstaller(fetch=host, **kwargs).install()


def test_the_newest_snapshot_is_installed_verified_and_made_current(tools):
    host = Host()
    log = []
    path = oi.SnapshotInstaller(fetch=host, log=log.append).install()
    assert path == tools / "2026.09.27" / "openscad"
    assert path.stat().st_mode & 0o111
    assert path.parent.stat().st_mode & 0o777 == 0o755
    assert (tools / "current").read_text().strip() == "2026.09.27"
    assert oi.current_executable() == path
    assert host.urls == [
        BASE,
        BASE + "OpenSCAD-2026.09.27-x86_64.AppImage",
        BASE + "OpenSCAD-2026.09.27-x86_64.AppImage.sha256",
    ]
    assert any("SHA-256 verified" in line for line in log)
    assert any("OpenSCAD version 2026.09.27" in line for line in log)
    # Nothing half-made is left beside it.
    assert _left_in(tools) == ["2026.09.27", "current"]


def test_a_snapshot_is_pinned_by_its_date(tools):
    path = _install(Host(), snapshot="2026.09.22")
    assert path == tools / "2026.09.22" / "openscad"
    assert oi.current_version() == "2026.09.22"


def test_a_night_published_under_its_build_number_is_found_by_its_date(tools):
    host = Host(dates=(), ai=["OpenSCAD-2025.10.02.ai27993-x86_64.AppImage"])
    assert _install(host, snapshot="2025.10.02") == tools / "2025.10.02" / "openscad"
    assert BASE + "OpenSCAD-2025.10.02.ai27993-x86_64.AppImage" in host.urls


@pytest.mark.parametrize(
    "bad", ["../../x", "2026.9.27", "2026.09.27/../x", "latest;rm", "2026.09", "v2026.09.27", ""]
)
def test_a_date_that_is_not_three_numbers_is_refused_before_anything_is_fetched(tools, bad):
    host = Host()
    with pytest.raises(oi.InstallError, match="not an OpenSCAD snapshot date"):
        _install(host, snapshot=bad)
    assert host.urls == []


def test_a_date_with_no_snapshot_is_refused_naming_the_newest(tools):
    with pytest.raises(oi.InstallError, match=r"no .*2026\.09\.26.*newest is 2026\.09\.27"):
        _install(Host(), snapshot="2026.09.26")
    assert _left_in(tools) == []


def test_a_snapshot_older_than_the_floor_is_refused(tools):
    with pytest.raises(oi.InstallError, match="older than 2026.09.25"):
        _install(Host(), snapshot="2026.09.22", minimum="2026.09.25")
    with pytest.raises(oi.InstallError, match="older than 2027.01"):
        _install(Host(), minimum="2027.01")
    assert _install(Host(), minimum="2021.08.24") == tools / "2026.09.27" / "openscad"


def test_a_checksum_that_does_not_match_installs_nothing(tools):
    host = Host()
    name = "OpenSCAD-2026.09.27-x86_64.AppImage"
    host.files[name + ".sha256"] = f"{'0' * 64}  {name}\n".encode()
    with pytest.raises(oi.InstallError, match="checksum mismatch"):
        _install(host)
    assert not (tools / "current").exists()
    assert _left_in(tools) == []


def test_a_download_of_another_size_than_listed_installs_nothing(tools):
    host = Host()
    host.sizes["OpenSCAD-2026.09.27-x86_64.AppImage"] = 999
    with pytest.raises(oi.InstallError, match="999"):
        _install(host)
    assert _left_in(tools) == []


def test_a_binary_that_reports_another_version_installs_nothing(tools):
    host = Host(reports={"2026.09.27": "2021.01"})
    with pytest.raises(oi.InstallError, match="reports .*2021.01"):
        _install(host)
    assert _left_in(tools) == []


def test_a_failed_install_leaves_the_current_one_current(tools):
    _install(Host(), snapshot="2026.09.22")
    host = Host()
    host.files["OpenSCAD-2026.09.27-x86_64.AppImage.sha256"] = b"0" * 64
    with pytest.raises(oi.InstallError):
        _install(host)
    assert oi.current_version() == "2026.09.22"
    assert _left_in(tools) == ["2026.09.22", "current"]


def test_an_installed_snapshot_is_not_fetched_again_unless_forced(tools):
    _install(Host())
    _install(Host(), snapshot="2026.09.22")
    host = Host()
    log = []
    oi.SnapshotInstaller(fetch=host, log=log.append, snapshot="2026.09.27").install()
    assert host.urls == []  # a pinned date already here needs nothing fetched
    assert oi.current_version() == "2026.09.27"
    assert any("already installed" in line for line in log)
    latest = Host()
    _install(latest)
    assert latest.urls == [BASE]  # the listing says which is newest; that one is here
    forced = Host()
    _install(forced, snapshot="2026.09.27", force=True)
    assert BASE + "OpenSCAD-2026.09.27-x86_64.AppImage" in forced.urls


@pytest.mark.parametrize(
    "system,machine,says",
    [
        (
            "Windows",
            "ARM64",
            "Windows on ARM is not supported yet (a planned item); set APOTHECARY_OPENSCAD "
            "to an OpenSCAD you installed",
        ),
        ("Linux", "riscv64", "APOTHECARY_OPENSCAD"),
        ("Plan9", "mips", "Plan9"),
    ],
)
def test_a_platform_it_does_not_install_for_is_refused_saying_what_there_is(
    tools, monkeypatch, system, machine, says
):
    monkeypatch.setattr(oi.platform, "system", lambda: system)
    monkeypatch.setattr(oi.platform, "machine", lambda: machine)
    host = Host()
    with pytest.raises(oi.InstallError, match=re_escape(says)):
        _install(host)
    assert host.urls == []


def re_escape(text: str) -> str:
    import re

    return re.escape(text)


@pytest.mark.parametrize("written", ["../../../bin", "2026.09.27/../../x", "", "latest"])
def test_a_current_that_is_not_a_date_names_no_openscad(tools, written):
    _install(Host())
    (tools / "current").write_text(written)
    assert oi.current_version() is None
    assert oi.current_executable() is None


def test_the_listing_is_read_for_this_platform_alone():
    host = Host(ai=["OpenSCAD-2025.09.28.ai27902-x86_64.AppImage"])
    found = oi.parse_listing(host.listing().decode(), oi.snapshot_pattern("Linux", "x86_64"))
    assert sorted(found) == ["2025.09.28", "2026.09.22", "2026.09.27"]
    assert found["2026.09.27"] == (
        "OpenSCAD-2026.09.27-x86_64.AppImage",
        len(_appimage("2026.09.27")),
    )


def test_manifold_is_known_by_version():
    assert oi.has_manifold("OpenSCAD version 2024.09.28")
    assert oi.has_manifold("OpenSCAD version 2026.09.27")
    assert oi.has_manifold("OpenSCAD version 2025.10.02.ai27993")
    assert not oi.has_manifold("OpenSCAD version 2024.09.27")
    assert not oi.has_manifold("OpenSCAD version 2021.01")
    assert not oi.has_manifold(None)


# --- the command line -------------------------------------------------------------


def test_openscad_install_and_status(tools, monkeypatch):
    from apothecary.cli import cli

    host = Host()
    monkeypatch.setattr(oi, "_fetch", host)
    result = CliRunner().invoke(cli, ["openscad", "install", "--latest"])
    assert result.exit_code == 0, result.output
    assert "OpenSCAD version 2026.09.27" in result.output
    assert oi.current_version() == "2026.09.27"

    result = CliRunner().invoke(cli, ["openscad", "status"])
    assert result.exit_code == 0, result.output
    assert "2026.09.27 (current)" in result.output and "Manifold" in result.output


def test_openscad_install_takes_the_parts_floor_by_default(tools, monkeypatch):
    from apothecary.cli import cli
    from apothecary.cli import openscad as cmd

    host = Host()
    monkeypatch.setattr(oi, "_fetch", host)
    monkeypatch.setattr(cmd, "parts_floor", lambda: ("2026.09.25", "gridfinity"))
    result = CliRunner().invoke(cli, ["openscad", "install", "--snapshot", "2026.09.22"])
    assert result.exit_code != 0
    assert "older than 2026.09.25" in result.output and "gridfinity" in result.output
    result = CliRunner().invoke(
        cli, ["openscad", "install", "--snapshot", "2026.09.22", "--min", "2021.01"]
    )
    assert result.exit_code == 0, result.output


def test_the_parts_floor_is_the_highest_any_part_declares():
    from apothecary.cli.openscad import parts_floor
    from apothecary.projects.parts.gridfinity import OPENSCAD_MIN_VERSION

    assert parts_floor() == (OPENSCAD_MIN_VERSION, "gridfinity")


def test_openscad_install_says_where_it_downloads_from():
    from apothecary.cli import cli

    result = CliRunner().invoke(cli, ["openscad", "install", "--help"])
    said = " ".join(result.output.split())
    assert "files.openscad.org (on Linux arm64, its source from GitHub) and nowhere else" in said


def test_latest_and_a_pinned_date_are_one_or_the_other(tools, monkeypatch):
    from apothecary.cli import cli

    monkeypatch.setattr(oi, "_fetch", Host())
    result = CliRunner().invoke(
        cli, ["openscad", "install", "--latest", "--snapshot", "2026.09.22"]
    )
    assert result.exit_code != 0 and "one or the other" in result.output


def test_check_says_which_openscad_each_part_uses_and_whether_it_has_manifold(tools, monkeypatch):
    from apothecary.cli import cli

    monkeypatch.delenv("APOTHECARY_OPENSCAD", raising=False)
    _install(Host())
    result = CliRunner().invoke(cli, ["check"])
    assert result.exit_code == 0, result.output
    snapshot = tools / "2026.09.27" / "openscad"
    lines = result.output.splitlines()
    uses = [
        line for line in lines if line.strip().startswith(("✓ calibration_cube", "✓ gridfinity"))
    ]
    assert len(uses) == 2, result.output
    for line in uses:
        assert str(snapshot) in line and "Manifold" in line and "no Manifold" not in line


# --- what an install is, read back ------------------------------------------------


def test_binary_archs_reads_elf_mach_o_universal_and_pe_headers(tmp_path):
    def write(name: str, data: bytes) -> Path:
        path = tmp_path / name
        path.write_bytes(data)
        return path

    elf = bytearray(64)
    elf[:6] = b"\x7fELF\x02\x01"
    elf[18:20] = (183).to_bytes(2, "little")
    assert oi.binary_archs(write("arm64.elf", bytes(elf))) == ["arm64"]
    elf[18:20] = (62).to_bytes(2, "little")
    assert oi.binary_archs(write("x86_64.elf", bytes(elf))) == ["x86_64"]
    thin = struct.pack("<II", 0xFEEDFACF, 0x01000007) + bytes(24)
    assert oi.binary_archs(write("thin", thin)) == ["x86_64"]
    fat = (
        struct.pack(">II", 0xCAFEBABE, 2)
        + struct.pack(">IIIII", 0x01000007, 3, 4096, 10, 12)
        + struct.pack(">IIIII", 0x0100000C, 0, 8192, 10, 14)
    )
    assert oi.binary_archs(write("universal", fat)) == ["x86_64", "arm64"]
    pe = bytearray(256)
    pe[:2] = b"MZ"
    pe[0x3C:0x40] = (128).to_bytes(4, "little")
    pe[128:134] = b"PE\x00\x00" + (0x8664).to_bytes(2, "little")
    assert oi.binary_archs(write("openscad.exe", bytes(pe))) == ["x86_64"]
    pe[132:134] = (0xAA64).to_bytes(2, "little")
    assert oi.binary_archs(write("arm.exe", bytes(pe))) == ["arm64"]
    assert oi.binary_archs(write("script", b"#!/bin/sh\n")) == []
    assert oi.binary_archs(tmp_path / "missing") == []


def test_runs_here_says_native_universal_rosetta_or_emulated():
    assert oi.runs_here(["x86_64"], "Linux", "x86_64") == "native"
    assert oi.runs_here(["arm64"], "Linux", "arm64") == "native"
    assert oi.runs_here(["x86_64", "arm64"], "Darwin", "arm64") == (
        "native (universal: x86_64, arm64)"
    )
    assert oi.runs_here(["x86_64"], "Darwin", "arm64") == "emulated: x86_64 under Rosetta 2"
    # A universal app started from an x86_64 Python (itself under Rosetta) runs as x86_64.
    assert "under Rosetta 2" in oi.runs_here(
        ["x86_64", "arm64"], "Darwin", "arm64", translated=True
    )
    assert oi.runs_here(["x86_64"], "Linux", "arm64") == "does not run here: built for x86_64"
    assert oi.runs_here([], "Linux", "x86_64") == "architecture not known"


@pytest.mark.parametrize(
    "said,needs",
    [
        ("dlopen(): error loading libfuse.so.2\n\nAppImages require FUSE to run.", True),
        ("fuse: device not found, try 'modprobe fuse' first", True),
        ("Error: No suitable fusermount binary found on the $PATH", True),
        ("Cannot mount AppImage, please check your FUSE setup.", True),
        ("Segmentation fault", False),
        ("", False),
    ],
)
def test_a_missing_fuse_is_known_by_what_the_appimage_says(said, needs):
    assert oi.needs_fuse(said) is needs


def test_default_jobs_leave_each_compiler_two_gigabytes(monkeypatch):
    monkeypatch.setattr(oi.os, "cpu_count", lambda: 8)
    monkeypatch.setattr(oi, "_memory_bytes", lambda: 4 * 1024**3)
    assert oi.default_jobs() == 2
    monkeypatch.setattr(oi, "_memory_bytes", lambda: 1024**3)
    assert oi.default_jobs() == 1
    monkeypatch.setattr(oi, "_memory_bytes", lambda: None)
    assert oi.default_jobs() == 8


# --- fakes for the other platforms -------------------------------------------------


def _script(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _on_path(monkeypatch, bin_dir: Path, keep: bool = True) -> None:
    rest = os.environ.get("PATH", "") if keep else ""
    monkeypatch.setenv("PATH", os.pathsep.join(p for p in (str(bin_dir), rest) if p))


def _tar_gz(entries) -> bytes:
    """A .tar.gz of ``entries``: (name, bytes) a file, (name, None) a directory,
    (name, "->target") a symlink."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, body in entries:
            info = tarfile.TarInfo(name)
            if body is None:
                info.type, info.mode = tarfile.DIRTYPE, 0o755
                tf.addfile(info)
            elif isinstance(body, str):
                info.type, info.linkname = tarfile.SYMTYPE, body[2:]
                tf.addfile(info)
            else:
                info.size, info.mode = len(body), 0o755
                tf.addfile(info, io.BytesIO(body))
    return buf.getvalue()


# macOS: the fake hdiutil "mounts" a disk image that is a tar, and logs each call.
HDIUTIL = """#!{python}
import os, shutil, sys, tarfile
args = sys.argv[1:]
with open(os.environ["FAKE_HDIUTIL_LOG"], "a") as log:
    log.write(" ".join(args) + "\\n")
if args[0] == "attach":
    mount = args[args.index("-mountpoint") + 1]
    os.makedirs(mount, exist_ok=True)
    trusted = {"filter": "fully_trusted"} if hasattr(tarfile, "fully_trusted_filter") else {}
    with tarfile.open(args[-1]) as tf:
        tf.extractall(mount, **trusted)
elif args[0] == "detach":
    mount = args[1]
    for name in os.listdir(mount):
        path = os.path.join(mount, name)
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
else:
    sys.exit(2)
"""

DITTO = '#!/bin/sh\necho "$@" >> "$FAKE_DITTO_LOG"\nexec cp -a "$1" "$2"\n'


def _disk_image(version: str) -> bytes:
    """OpenSCAD-<date>.dmg as the fake hdiutil mounts it: the app, whose
    executable reports ``version``, a framework link inside it, and the
    Applications link a disk image carries beside the app."""
    app = "OpenSCAD.app/Contents"
    plist = plistlib.dumps({"CFBundleExecutable": "OpenSCAD"})
    return _tar_gz(
        [
            ("OpenSCAD.app", None),
            (f"{app}/Info.plist", plist),
            (f"{app}/MacOS/OpenSCAD", _appimage(version)),
            (f"{app}/Frameworks/QtCore.framework/Versions/A/QtCore", b"lib"),
            (f"{app}/Frameworks/QtCore.framework/QtCore", "->Versions/A/QtCore"),
            ("Applications", "->/Applications"),
        ]
    )


@pytest.fixture
def mac(tools, tmp_path, monkeypatch):
    """An Apple Silicon Mac whose hdiutil is the fake; returns its call log."""
    monkeypatch.setattr(oi.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(oi.platform, "machine", lambda: "arm64")
    _script(tmp_path / "bin" / "hdiutil", HDIUTIL.replace("{python}", sys.executable))
    _on_path(monkeypatch, tmp_path / "bin")
    monkeypatch.setenv("FAKE_HDIUTIL_LOG", str(tmp_path / "hdiutil.log"))
    return tmp_path / "hdiutil.log"


def _calls(log: Path) -> list:
    return log.read_text().splitlines() if log.exists() else []


@pytest.mark.parametrize("with_ditto", [True, False])
def test_macos_copies_the_app_out_of_the_disk_image_and_detaches_it(
    tools, mac, tmp_path, monkeypatch, with_ditto
):
    if with_ditto:
        _script(tmp_path / "bin" / "ditto", DITTO)
        monkeypatch.setenv("FAKE_DITTO_LOG", str(tmp_path / "ditto.log"))
    host = Host()
    host.add("OpenSCAD-2026.09.27.dmg", _disk_image("2026.09.27"))
    log = []
    path = oi.SnapshotInstaller(fetch=host, log=log.append).install()
    app = tools / "2026.09.27" / "OpenSCAD.app"
    assert path == app / "Contents" / "MacOS" / "OpenSCAD"
    assert oi.current_executable() == path
    assert host.urls == [
        BASE,
        BASE + "OpenSCAD-2026.09.27.dmg",
        BASE + "OpenSCAD-2026.09.27.dmg.sha256",
    ]
    calls = _calls(mac)
    assert calls[0].startswith("attach -nobrowse -readonly -noautoopen -mountpoint ")
    mount = calls[0].split()[5]
    assert calls[1:] == [f"detach {mount}"]
    assert not Path(mount).exists()
    if with_ditto:
        source, dest = (tmp_path / "ditto.log").read_text().split()
        assert source == f"{mount}/OpenSCAD.app" and dest.endswith("/OpenSCAD.app")
    # The bundle's links stay links; only the app is copied, not the image's other entries.
    assert (app / "Contents" / "Frameworks" / "QtCore.framework" / "QtCore").is_symlink()
    assert not (tools / "2026.09.27" / "Applications").exists()
    assert oi.read_manifest("2026.09.27")["method"] == "dmg"
    assert any("OpenSCAD version 2026.09.27" in line for line in log)
    assert _left_in(tools) == ["2026.09.27", "current"]


def test_a_disk_image_with_no_app_in_it_is_detached_and_installs_nothing(tools, mac):
    host = Host()
    host.add("OpenSCAD-2026.09.27.dmg", _tar_gz([("README.txt", b"no app here")]))
    with pytest.raises(oi.InstallError, match="no OpenSCAD.app"):
        _install(host)
    assert [call.split()[0] for call in _calls(mac)] == ["attach", "detach"]
    assert _left_in(tools) == []


def test_an_app_that_reports_another_version_installs_nothing(tools, mac):
    host = Host()
    host.add("OpenSCAD-2026.09.27.dmg", _disk_image("2021.01"))
    with pytest.raises(oi.InstallError, match="reports .*2021.01"):
        _install(host)
    assert [call.split()[0] for call in _calls(mac)] == ["attach", "detach"]
    assert _left_in(tools) == []


# Windows: the portable zip, unpacked, openscad.exe with its files beside it.


def _portable_zip(version: str, extra=()) -> bytes:
    top = "OpenSCAD-2026.09.27-x86-64"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{top}/openscad.exe", _appimage(version))
        zf.writestr(f"{top}/openscad.com", b"MZ console wrapper")
        zf.writestr(f"{top}/libraries/MCAD/gears.scad", b"// gears\n")
        zf.writestr(f"{top}/fonts/Liberation.ttf", b"font")
        for name, body in extra:
            zf.writestr(name, body)
    return buf.getvalue()


@pytest.fixture
def windows(tools, monkeypatch):
    monkeypatch.setattr(oi.platform, "system", lambda: "Windows")
    monkeypatch.setattr(oi.platform, "machine", lambda: "AMD64")


def test_windows_unpacks_the_portable_zip_with_its_files_beside_the_exe(tools, windows):
    host = Host()
    host.add("OpenSCAD-2026.09.27-x86-64.zip", _portable_zip("2026.09.27"))
    path = _install(host)
    home = tools / "2026.09.27"
    assert path == home / "openscad.exe"
    assert oi.current_executable() == path
    assert (home / "libraries" / "MCAD" / "gears.scad").read_bytes() == b"// gears\n"
    assert (home / "openscad.com").is_file() and (home / "fonts" / "Liberation.ttf").is_file()
    assert host.urls[1:] == [
        BASE + "OpenSCAD-2026.09.27-x86-64.zip",
        BASE + "OpenSCAD-2026.09.27-x86-64.zip.sha256",
    ]
    assert oi.read_manifest("2026.09.27")["method"] == "zip"
    assert _left_in(tools) == ["2026.09.27", "current"]


@pytest.mark.parametrize(
    "bad",
    [
        "OpenSCAD-2026.09.27-x86-64/../../escaped.txt",
        "/escaped.txt",
        "C:/escaped.txt",
        "OpenSCAD-2026.09.27-x86-64\\..\\..\\escaped.txt",
    ],
)
def test_a_zip_with_a_path_that_leaves_its_folder_installs_nothing(tools, windows, tmp_path, bad):
    host = Host()
    host.add("OpenSCAD-2026.09.27-x86-64.zip", _portable_zip("2026.09.27", [(bad, b"x")]))
    with pytest.raises(oi.InstallError, match="outside"):
        _install(host)
    assert _left_in(tools) == []
    assert not list(tmp_path.rglob("escaped.txt"))


def test_windows_on_arm_is_refused_even_from_an_emulated_python(tools, windows, monkeypatch):
    # An x64 Python on an ARM64 PC says AMD64; the hardware is asked instead.
    monkeypatch.setattr(oi, "_windows_native_machine", lambda: "arm64")
    host = Host()
    with pytest.raises(oi.InstallError, match=r"Windows on ARM is not supported yet \(a planned"):
        _install(host)
    assert host.urls == []


# Linux x86_64 without FUSE: the AppImage cannot mount itself; it is extracted.


def _appimage_without_fuse(version: str) -> bytes:
    """An AppImage that fails as one does where there is no FUSE, and that
    extracts itself with --appimage-extract."""
    return (
        "#!/bin/sh\n"
        'if [ "$1" = "--appimage-extract" ]; then\n'
        "  mkdir -p squashfs-root/usr/bin\n"
        f"  printf '#!/bin/sh\\necho \"OpenSCAD version {version}\" >&2\\n' > squashfs-root/AppRun\n"
        "  chmod +x squashfs-root/AppRun\n"
        "  chmod 700 squashfs-root\n"  # as the real runtime leaves it
        "  echo squashfs-root/AppRun\n"
        "  exit 0\n"
        "fi\n"
        "echo \"fuse: device not found, try 'modprobe fuse' first\" >&2\n"
        'echo "Cannot mount AppImage, please check your FUSE setup." >&2\n'
        'echo "if you run it with the --appimage-extract option." >&2\n'
        "exit 1\n"
    ).encode()


def test_an_appimage_that_cannot_mount_without_fuse_is_extracted_and_run_as_apprun(tools):
    host = Host()
    host.add("OpenSCAD-2026.09.27-x86_64.AppImage", _appimage_without_fuse("2026.09.27"))
    log = []
    path = oi.SnapshotInstaller(fetch=host, log=log.append).install()
    home = tools / "2026.09.27"
    assert path == home / "squashfs-root" / "AppRun"
    assert oi.current_executable() == path and oi.installed_versions() == ["2026.09.27"]
    assert not (home / "openscad").exists()  # the image itself is not kept beside it
    assert (home / "squashfs-root").stat().st_mode & 0o777 == 0o755
    assert oi.read_manifest("2026.09.27")["method"] == "appimage-extracted"
    assert any("FUSE" in line for line in log)
    assert _left_in(tools) == ["2026.09.27", "current"]


def test_an_appimage_that_fails_for_another_reason_is_not_extracted(tools):
    host = Host()
    host.add(
        "OpenSCAD-2026.09.27-x86_64.AppImage",
        b"#!/bin/sh\necho 'Segmentation fault' >&2\nexit 139\n",
    )
    with pytest.raises(oi.InstallError, match="does not run here"):
        _install(host)
    assert _left_in(tools) == []


# Linux arm64: OpenSCAD's source at the snapshot's date, built here.

SHA = "31f27b7522af858ebabed764e67ecc10d9e27add"
PINS = {
    "libraries/MCAD": ("openscad", "MCAD", "1ea402208c3127ffb443931e9bb1681c191dacca"),
    "submodules/manifold": ("elalish", "manifold", "0edd9d54876f3135e431575214dd6d8a72866fee"),
}
API = "https://api.github.com/repos/openscad/openscad"
CODELOAD = "https://codeload.github.com/"


class GitHub:
    """api.github.com and codeload.github.com, for OpenSCAD at one commit."""

    def __init__(self, sha: str = SHA, pins=None):
        self.sha = sha
        self.pins = dict(PINS if pins is None else pins)
        self.urls: list[str] = []
        self.query: dict = {}
        self.gitmodules = "".join(
            f'[submodule "{path}"]\n\tpath = {path}\n\turl = https://github.com/{owner}/{repo}.git\n'
            for path, (owner, repo, _) in self.pins.items()
        )

    def tarballs(self) -> dict:
        top = f"openscad-{self.sha}"
        found = {
            f"{CODELOAD}openscad/openscad/tar.gz/{self.sha}": _tar_gz(
                [
                    (top, None),
                    (f"{top}/CMakeLists.txt", b"project(OpenSCAD)\n"),
                    (f"{top}/src/openscad.cc", b"int main() {}\n"),
                    *[(f"{top}/{path}", None) for path in self.pins],
                ]
            )
        }
        for path, (owner, repo, pin) in self.pins.items():
            found[f"{CODELOAD}{owner}/{repo}/tar.gz/{pin}"] = _tar_gz(
                [(f"{repo}-{pin}", None), (f"{repo}-{pin}/CMakeLists.txt", f"# {path}\n".encode())]
            )
        return found

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        parts = urlsplit(url)
        if url == API:
            return json.dumps({"default_branch": "master"}).encode()
        if parts.path == "/repos/openscad/openscad/commits":
            self.query = {key: value[0] for key, value in parse_qs(parts.query).items()}
            return json.dumps([{"sha": self.sha}]).encode()
        if url == f"{API}/contents/.gitmodules?ref={self.sha}":
            content = base64.b64encode(self.gitmodules.encode()).decode()
            return json.dumps({"type": "file", "encoding": "base64", "content": content}).encode()
        if url.startswith(f"{API}/contents/") and url.endswith(f"?ref={self.sha}"):
            path = url[len(f"{API}/contents/") :].split("?")[0]
            owner, repo, pin = self.pins[path]
            answer = {
                "type": "submodule",
                "path": path,
                "sha": pin,
                "submodule_git_url": f"https://github.com/{owner}/{repo}.git",
            }
            return json.dumps(answer).encode()
        return self.tarballs()[url]


# The fake cmake: it configures (refusing a source tree whose submodules are not
# in place), builds (printing progress as make does) and installs a stand-in
# OpenSCAD that reports the version it was configured with.
FAKE_OPENSCAD = """#!/bin/sh
case "$1" in
  --version) echo "OpenSCAD version VERSION" >&2 ;;
  --info) echo "OpenSCAD Version: VERSION"; echo "Manifold version: MANIFOLD" ;;
  *) while [ $# -gt 0 ]; do
       if [ "$1" = "-o" ]; then shift; echo "solid cube" > "$1"; fi
       shift
     done ;;
esac
"""

CMAKE = """#!{python}
import os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_CMAKE_LOG"], "a") as log:
    log.write(" ".join(args) + "\\n")
if args == ["--version"]:
    print("cmake version " + os.environ.get("FAKE_CMAKE_VERSION", "3.25.1"))
elif args[0] == "--build":
    print("[  4%] Building CXX object CMakeFiles/OpenSCADLibInternal.dir/src/core/node.cc.o")
    print("[  4%] Building CXX object CMakeFiles/OpenSCADLibInternal.dir/src/core/value.cc.o")
    print("[ 51%] Building CXX object submodules/manifold/src/CMakeFiles/manifold.dir/b.cpp.o")
    sys.stdout.flush()
    if os.environ.get("FAKE_CMAKE_FAIL"):
        print("src/core/value.cc:12:1: error: boom", file=sys.stderr)
        sys.exit(2)
    print("[100%] Linking CXX executable openscad")
elif args[0] == "--install":
    prefix, version = open(os.path.join(args[1], "fake-cache")).read().split()
    os.makedirs(os.path.join(prefix, "bin"))
    os.makedirs(os.path.join(prefix, "share", "openscad", "libraries", "MCAD"))
    manifold = "<not enabled>" if os.environ.get("FAKE_NO_MANIFOLD") else "3.2.0"
    exe = os.path.join(prefix, "bin", "openscad")
    with open(exe, "w") as f:
        f.write({openscad}.replace("VERSION", version).replace("MANIFOLD", manifold))
    os.chmod(exe, 0o755)
else:
    options = dict(a.split("=", 1) for a in args if a.startswith("-D"))
    source, build = args[args.index("-S") + 1], args[args.index("-B") + 1]
    for need in ("CMakeLists.txt", "submodules/manifold/CMakeLists.txt", "libraries/MCAD/CMakeLists.txt"):
        if not os.path.isfile(os.path.join(source, need)):
            print("CMake Error: " + need + " is missing", file=sys.stderr)
            sys.exit(1)
    os.makedirs(build, exist_ok=True)
    with open(os.path.join(build, "fake-cache"), "w") as f:
        f.write(options["-DCMAKE_INSTALL_PREFIX"] + "\\n" + options["-DOPENSCAD_VERSION"] + "\\n")
    print("-- Configuring done")
"""


class Machine:
    def __init__(self, bin_dir: Path, include: Path, lib: Path, cmake_log: Path):
        self.bin, self.include, self.lib, self.cmake_log = bin_dir, include, lib, cmake_log

    def cmake_calls(self) -> list:
        return _calls(self.cmake_log)


@pytest.fixture
def arm64(tools, tmp_path, monkeypatch):
    """Linux arm64 with everything a source build needs: the programs (faked;
    nothing else is on PATH), every header and library, and the fake cmake."""
    monkeypatch.setattr(oi.platform, "machine", lambda: "aarch64")
    bin_dir, include, lib = tmp_path / "bin", tmp_path / "include", tmp_path / "lib"
    for need in oi.BUILD_NEEDS:
        for program in need.programs[:1]:
            _script(bin_dir / program, "#!/bin/sh\nexit 0\n")
        for header in need.headers[:1]:
            (include / header).parent.mkdir(parents=True, exist_ok=True)
            (include / header).write_text("")
        for library in need.libraries:
            lib.mkdir(exist_ok=True)
            (lib / f"lib{library}.so").write_text("")
    cmake = CMAKE.replace("{python}", sys.executable).replace("{openscad}", repr(FAKE_OPENSCAD))
    _script(bin_dir / "cmake", cmake)
    monkeypatch.setattr(oi, "_include_dirs", lambda: [include])
    monkeypatch.setattr(oi, "_lib_dirs", lambda: [lib])
    _on_path(monkeypatch, bin_dir, keep=False)
    monkeypatch.setenv("FAKE_CMAKE_LOG", str(tmp_path / "cmake.log"))
    return Machine(bin_dir, include, lib, tmp_path / "cmake.log")


def _build(github, **kwargs) -> Path:
    return oi.SnapshotInstaller(snapshot="2026.09.27", fetch=github, **kwargs).install()


def test_linux_arm64_builds_the_snapshot_date_from_source_at_the_pinned_commits(
    tools, arm64, monkeypatch
):
    github = GitHub()
    log = []
    path = _build(github, log=log.append, jobs=3)
    home = tools / "2026.09.27"
    assert path == home / "bin" / "openscad"
    assert oi.current_executable() == path
    assert (home / "share" / "openscad" / "libraries" / "MCAD").is_dir()
    # The last commit on the default branch at or before the date, then the pins it names.
    assert github.query == {"sha": "master", "until": "2026-09-27T23:59:59Z", "per_page": "1"}
    assert github.urls == [
        API,
        f"{API}/commits?sha=master&until=2026-09-27T23:59:59Z&per_page=1",
        f"{API}/contents/.gitmodules?ref={SHA}",
        f"{API}/contents/libraries/MCAD?ref={SHA}",
        f"{API}/contents/submodules/manifold?ref={SHA}",
        f"{CODELOAD}openscad/openscad/tar.gz/{SHA}",
        f"{CODELOAD}openscad/MCAD/tar.gz/{PINS['libraries/MCAD'][2]}",
        f"{CODELOAD}elalish/manifold/tar.gz/{PINS['submodules/manifold'][2]}",
    ]
    calls = arm64.cmake_calls()
    configure = next(call for call in calls if call.startswith("-S ")).split()
    for flag in (
        "-DCMAKE_BUILD_TYPE=Release",
        "-DHEADLESS=ON",
        "-DENABLE_TESTS=OFF",
        "-DENABLE_MANIFOLD=ON",
        "-DMANIFOLD_DOWNLOADS=OFF",
        "-DFETCHCONTENT_FULLY_DISCONNECTED=ON",
        "-DOPENSCAD_VERSION=2026.09.27",
        f"-DOPENSCAD_COMMIT={SHA[:12]}",
    ):
        assert flag in configure
    assert any(call.startswith("--build ") and call.endswith(" -j 3") for call in calls)
    assert any(call.startswith("--install ") for call in calls)
    record = oi.read_manifest("2026.09.27")
    assert record["method"] == "source" and record["commit"] == SHA
    assert record["submodules"] == {path: pin for path, (_, _, pin) in PINS.items()}
    assert oi.describe("2026.09.27").how == f"built from source at {SHA}"
    # The build's progress, as it goes: one line for each step it makes.
    assert any("[ 51%]" in line for line in log)
    assert sum("[  4%]" in line for line in log) == 1
    assert (home / "build.log").is_file()
    # The source and the build tree are gone.
    assert _left_in(tools) == ["2026.09.27", "current"]
    # Pinned and installed: nothing is checked or fetched again.
    monkeypatch.setenv("PATH", "")
    again = GitHub()
    assert _build(again) == path and again.urls == []


def test_linux_arm64_builds_the_newest_night_when_no_date_is_given(tools, arm64):
    host, github = Host(), GitHub()

    def fetch(url: str) -> bytes:
        return host(url) if url.startswith(BASE) else github(url)

    path = oi.SnapshotInstaller(fetch=fetch).install()
    assert path == tools / "2026.09.27" / "bin" / "openscad"
    assert host.urls == [BASE]
    assert github.query["until"] == "2026-09-27T23:59:59Z"


def test_a_source_build_missing_what_it_needs_is_refused_with_the_apt_line_before_any_fetch(
    tools, arm64
):
    (arm64.bin / "bison").unlink()
    (arm64.include / "CGAL" / "version.h").unlink()
    (arm64.lib / "libboost_regex.so").unlink()
    github = GitHub()
    with pytest.raises(oi.InstallError) as refused:
        _build(github)
    said = str(refused.value)
    assert "\n  sudo apt install bison libboost-regex-dev libcgal-dev\n" in said
    assert github.urls == []
    assert _left_in(tools) == []


def test_a_cmake_older_than_the_build_needs_is_refused(tools, arm64, monkeypatch):
    monkeypatch.setenv("FAKE_CMAKE_VERSION", "3.13.4")
    github = GitHub()
    with pytest.raises(oi.InstallError, match="3.13.4") as refused:
        _build(github)
    assert "\n  sudo apt install cmake\n" in str(refused.value)
    assert github.urls == []


@pytest.mark.parametrize("bad", ["../../../x", "31f27b75", "g" * 40, SHA + "/../x", SHA.upper()])
def test_a_commit_that_is_not_forty_hex_characters_is_refused_before_it_is_used(tools, arm64, bad):
    github = GitHub(sha=bad)
    with pytest.raises(oi.InstallError, match="not a commit SHA"):
        _build(github)
    assert len(github.urls) == 2  # the repository and its commit; nothing built from the answer


def test_a_submodule_pin_that_is_not_a_commit_is_refused_before_any_tarball(tools, arm64):
    pins = dict(PINS)
    pins["submodules/manifold"] = ("elalish", "manifold", "main")
    github = GitHub(pins=pins)
    with pytest.raises(oi.InstallError, match="not a commit SHA"):
        _build(github)
    assert not any(url.startswith(CODELOAD) for url in github.urls)


@pytest.mark.parametrize(
    "old,new,says",
    [
        ("https://github.com/elalish/manifold.git", "https://evil.example/manifold.git", "github"),
        ("path = submodules/manifold", "path = ../../outside", "not a plain path"),
        ("https://github.com/elalish/manifold.git", "https://github.com/../x.git", "github"),
    ],
)
def test_a_submodule_from_elsewhere_or_outside_the_tree_is_refused(tools, arm64, old, new, says):
    github = GitHub()
    github.gitmodules = github.gitmodules.replace(old, new)
    with pytest.raises(oi.InstallError, match=says):
        _build(github)
    assert not any(url.startswith(CODELOAD) for url in github.urls)


def test_a_failed_build_keeps_its_log_and_installs_nothing(tools, arm64, monkeypatch):
    monkeypatch.setenv("FAKE_CMAKE_FAIL", "1")
    with pytest.raises(oi.InstallError) as failed:
        _build(GitHub())
    said = str(failed.value)
    kept = tools / "build-2026.09.27.log"
    assert "error: boom" in said and str(kept) in said
    assert "error: boom" in kept.read_text()
    assert _left_in(tools) == ["build-2026.09.27.log"]
    assert oi.current_version() is None


def test_a_build_without_manifold_installs_nothing(tools, arm64, monkeypatch):
    monkeypatch.setenv("FAKE_NO_MANIFOLD", "1")
    with pytest.raises(oi.InstallError, match="without Manifold"):
        _build(GitHub())
    assert "2026.09.27" not in _left_in(tools)
    assert oi.current_version() is None


@pytest.mark.parametrize(
    "entries",
    [
        [("top", None), ("top/../../escaped.txt", b"x")],
        [("top", None), ("top/link", "->../../escaped.txt")],
        [("top", None), ("/abs/escaped.txt", b"x")],
    ],
)
def test_a_tarball_member_that_leaves_its_folder_is_refused(tmp_path, entries):
    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(oi.InstallError, match="outside"):
        oi.unpack_tarball(_tar_gz(entries), dest)
    assert not list(tmp_path.rglob("escaped.txt"))


# --- what status says ----------------------------------------------------------------


def test_status_says_for_each_install_its_platform_how_whether_native_and_manifold(
    tools, monkeypatch
):
    from apothecary.cli import cli

    monkeypatch.delenv("APOTHECARY_OPENSCAD", raising=False)
    monkeypatch.setattr(oi, "binary_archs", lambda path: ["x86_64"])
    _install(Host(), snapshot="2026.09.22")
    host = Host()
    host.add("OpenSCAD-2026.09.27-x86_64.AppImage", _appimage_without_fuse("2026.09.27"))
    _install(host)
    result = CliRunner().invoke(cli, ["openscad", "status"])
    assert result.exit_code == 0, result.output
    assert "Linux x86_64 · AppImage, run through FUSE · native · Manifold" in result.output
    assert (
        "Linux x86_64 · AppImage extracted (no FUSE here), run as squashfs-root/AppRun"
        " · native · Manifold"
    ) in result.output


def test_status_says_a_mac_app_is_universal_or_runs_under_rosetta(tools, mac, monkeypatch):
    host = Host()
    host.add("OpenSCAD-2026.09.27.dmg", _disk_image("2026.09.27"))
    monkeypatch.setattr(oi, "binary_archs", lambda path: ["x86_64", "arm64"])
    _install(host)
    found = oi.describe("2026.09.27")
    assert found.line() == (
        "macOS arm64 · OpenSCAD.app from the disk image · native (universal: x86_64, arm64)"
        " · Manifold"
    )
    monkeypatch.setattr(oi, "_rosetta_translated", lambda: True)
    assert "under Rosetta 2" in oi.describe("2026.09.27").runs


def test_an_install_from_before_the_record_is_described_as_the_appimage_it_is(tools, monkeypatch):
    monkeypatch.setattr(oi, "binary_archs", lambda path: ["x86_64"])
    home = tools / "2026.09.27"
    _script(home / "openscad", _appimage("2026.09.27").decode())
    (tools / "current").write_text("2026.09.27\n")
    assert oi.current_executable() == home / "openscad"
    assert oi.describe("2026.09.27").line() == (
        "Linux x86_64 · AppImage, run through FUSE · native · Manifold"
    )


def test_openscad_install_passes_jobs_through(tools, monkeypatch):
    from apothecary.cli import cli

    seen = {}

    class Installer:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        def install(self):
            return tools / "2026.09.27" / "bin" / "openscad"

    monkeypatch.setattr(oi, "SnapshotInstaller", Installer)
    result = CliRunner().invoke(cli, ["openscad", "install", "--jobs", "3", "--min", "2021.01"])
    assert result.exit_code == 0, result.output
    assert seen["jobs"] == 3
    result = CliRunner().invoke(cli, ["openscad", "install", "--jobs", "0"])
    assert result.exit_code != 0
