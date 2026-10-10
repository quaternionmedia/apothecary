"""The OrcaSlicer installer (apothecary/slicer/orcaslicer_installer.py), against a
fake GitHub: its release record, with the digest it publishes for each asset,
and the assets -- an AppImage that is a shell script (one that mounts, one that
fails as it does without FUSE), a disk image a fake ``hdiutil`` mounts, a real
zip with a stand-in ``orca-slicer.exe``. The pinned digests are the fakes'. The
platform is patched in. Nothing here reaches the network."""

from __future__ import annotations

import hashlib
import io
import json
import os
import plistlib
import stat
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from apothecary import openscad_installer
from apothecary.slicer import orcaslicer_installer as oi

API = "https://api.github.com/repos/OrcaSlicer/OrcaSlicer/releases/tags/v2.4.2"
DOWNLOAD = "https://github.com/OrcaSlicer/OrcaSlicer/releases/download/v2.4.2/"


def _appimage(version: str = "2.4.2", fuse: bool = True) -> bytes:
    """A stand-in AppImage: extracts its profiles (or the whole image) as the
    runtime does, and says its version first, as OrcaSlicer's --help does -- or
    fails as an AppImage does where there is no FUSE."""
    run = (
        f'echo "OrcaSlicer-{version}:"\necho "Usage: orca-slicer [ OPTIONS ]"\n'
        if fuse
        else "echo \"fuse: device not found, try 'modprobe fuse' first\" >&2\n"
        'echo "Cannot mount AppImage, please check your FUSE setup." >&2\nexit 1\n'
    )
    return (
        "#!/bin/sh\n"
        'if [ "$1" = "--appimage-extract" ]; then\n'
        '  echo "$2" >> extract.log\n'
        "  mkdir -p squashfs-root/resources/profiles/Creality/machine\n"
        "  echo '{}' > squashfs-root/resources/profiles/Creality.json\n"
        '  if [ -z "$2" ]; then\n'
        f"    printf '#!/bin/sh\\necho \"OrcaSlicer-{version}:\"\\n' > squashfs-root/AppRun\n"
        "    chmod +x squashfs-root/AppRun\n"
        "  fi\n"
        "  chmod 700 squashfs-root\n"  # as the real runtime leaves it
        "  exit 0\n"
        "fi\n" + run
    ).encode()


class GitHub:
    """The pinned release as GitHub serves it: its record with each asset's digest,
    and the assets. Records every URL asked for."""

    def __init__(self, assets: dict, published: dict | None = None):
        self.assets = assets
        self.published = published or {}
        self.urls: list[str] = []

    def fetch(self, url: str) -> bytes:
        self.urls.append(url)
        assert url == API, url
        listed = [
            {
                "name": name,
                "digest": "sha256:" + self.published.get(name, hashlib.sha256(body).hexdigest()),
            }
            for name, body in self.assets.items()
        ]
        return json.dumps({"tag_name": "v2.4.2", "assets": listed}).encode()

    def fetch_to(self, url: str, path: Path) -> str:
        self.urls.append(url)
        assert url.startswith(DOWNLOAD), url
        body = self.assets[url[len(DOWNLOAD) :]]
        path.write_bytes(body)
        return hashlib.sha256(body).hexdigest()


@pytest.fixture
def tools(tmp_path, monkeypatch):
    """A Linux x86_64 machine, its tools dir the test's own."""
    monkeypatch.setenv("APOTHECARY_TOOLS_DIR", str(tmp_path / "tools"))
    _platform(monkeypatch, "Linux", "x86_64")
    monkeypatch.setattr(openscad_installer, "_rosetta_translated", lambda: False)
    monkeypatch.setattr(openscad_installer, "_windows_native_machine", lambda: None)
    return tmp_path / "tools" / "orcaslicer"


def _platform(monkeypatch, system: str, machine: str) -> None:
    monkeypatch.setattr(openscad_installer.platform, "system", lambda: system)
    monkeypatch.setattr(openscad_installer.platform, "machine", lambda: machine)


def _pin(monkeypatch, system: str, machine: str, name: str, body: bytes, method: str) -> None:
    """Pin ``body`` as this platform's asset, as a commit moving the pin would."""
    pinned = dict(oi.ASSETS)
    pinned[(system, machine)] = oi.Asset(name, method, hashlib.sha256(body).hexdigest())
    monkeypatch.setattr(oi, "ASSETS", pinned)


def _left_in(folder: Path) -> list:
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


LINUX = "OrcaSlicer_Linux_AppImage_Ubuntu2404_V2.4.2.AppImage"


def _linux(monkeypatch, body: bytes) -> GitHub:
    _pin(monkeypatch, "Linux", "x86_64", LINUX, body, oi.APPIMAGE)
    return GitHub({LINUX: body})


def test_the_pinned_appimage_is_checked_installed_and_made_current(tools, monkeypatch):
    github = _linux(monkeypatch, _appimage())
    log = []
    path = oi.OrcaSlicerInstaller(
        fetch=github.fetch, fetch_to=github.fetch_to, log=log.append
    ).install()
    release = tools / "2.4.2"
    assert path == release / "OrcaSlicer.AppImage" and oi.current_executable() == path
    # GitHub's digest first, then the asset, from the pinned release and nowhere else.
    assert github.urls == [API, DOWNLOAD + LINUX]
    # Its profiles' JSON extracted beside it: an AppImage is not readable unmounted.
    assert (release / "extract.log").read_text().split() == ["resources/profiles/*"]
    assert oi.resources_for("2.4.2") == release / "squashfs-root" / "resources"
    assert (release / "squashfs-root").stat().st_mode & 0o777 == 0o755
    record = oi.read_manifest("2.4.2")
    assert record["method"] == "appimage" and record["version"] == "2.4.2"
    assert record["sha256"] == hashlib.sha256(_appimage()).hexdigest()
    assert any("SHA-256 verified" in line for line in log)
    assert any("OrcaSlicer 2.4.2 runs" in line for line in log)
    assert _left_in(tools) == ["2.4.2", "current"]
    assert oi.installed_versions() == ["2.4.2"]
    found = oi.describe("2.4.2")
    assert found.how.startswith("AppImage, run through FUSE")


def test_an_appimage_that_cannot_mount_without_fuse_is_extracted_whole(tools, monkeypatch):
    github = _linux(monkeypatch, _appimage(fuse=False))
    log = []
    path = oi.OrcaSlicerInstaller(
        fetch=github.fetch, fetch_to=github.fetch_to, log=log.append
    ).install()
    release = tools / "2.4.2"
    assert path == release / "squashfs-root" / "AppRun"
    assert not (release / "OrcaSlicer.AppImage").exists()
    assert (release / "extract.log").read_text().split() == ["resources/profiles/*"]
    assert oi.read_manifest("2.4.2")["method"] == "appimage-extracted"
    assert oi.resources_for("2.4.2") == release / "squashfs-root" / "resources"
    assert any("no FUSE" in line for line in log)


def test_a_release_whose_digest_moved_since_it_was_pinned_is_not_downloaded(tools, monkeypatch):
    github = _linux(monkeypatch, _appimage())
    github.published[LINUX] = "f" * 64
    with pytest.raises(oi.InstallError, match="has changed since it was pinned"):
        oi.OrcaSlicerInstaller(fetch=github.fetch, fetch_to=github.fetch_to).install()
    assert github.urls == [API]
    assert _left_in(tools) == []


def test_a_download_that_is_not_what_github_publishes_is_never_opened(tools, monkeypatch):
    github = _linux(monkeypatch, _appimage())
    github.published[LINUX] = hashlib.sha256(_appimage()).hexdigest()  # what was published
    github.assets[LINUX] = _appimage() + b"# tampered\n"  # and what is served
    with pytest.raises(oi.InstallError, match="checksum mismatch"):
        oi.OrcaSlicerInstaller(fetch=github.fetch, fetch_to=github.fetch_to).install()
    assert _left_in(tools) == []


def test_a_release_that_reports_another_version_installs_nothing(tools, monkeypatch):
    github = _linux(monkeypatch, _appimage(version="2.3.1"))
    with pytest.raises(oi.InstallError, match="reports 2.3.1"):
        oi.OrcaSlicerInstaller(fetch=github.fetch, fetch_to=github.fetch_to).install()
    assert _left_in(tools) == []
    assert oi.current_version() is None


def test_an_installed_release_is_not_fetched_again_unless_forced(tools, monkeypatch):
    github = _linux(monkeypatch, _appimage())
    oi.OrcaSlicerInstaller(fetch=github.fetch, fetch_to=github.fetch_to).install()
    github.urls.clear()
    log = []
    oi.OrcaSlicerInstaller(fetch=github.fetch, fetch_to=github.fetch_to, log=log.append).install()
    assert github.urls == [] and "already installed" in log[0]
    oi.OrcaSlicerInstaller(fetch=github.fetch, fetch_to=github.fetch_to, force=True).install()
    assert github.urls == [API, DOWNLOAD + LINUX]
    assert _left_in(tools) == ["2.4.2", "current"]


@pytest.mark.parametrize(
    "system, machine",
    [("Linux", "armv7l"), ("FreeBSD", "amd64"), ("Windows", "x86"), ("Linux", "riscv64")],
)
def test_a_platform_no_release_is_published_for_is_refused_before_any_fetch(
    tools, monkeypatch, system, machine
):
    _platform(monkeypatch, system, machine)
    github = GitHub({})
    with pytest.raises(oi.InstallError, match="OrcaSlicer publishes Linux x86_64 and arm64"):
        oi.OrcaSlicerInstaller(fetch=github.fetch, fetch_to=github.fetch_to).install()
    assert github.urls == []
    assert "APOTHECARY_ORCASLICER" in oi.what_install_does()


def test_each_served_platform_has_its_own_asset_of_the_pinned_release():
    """Linux x86_64 and arm64, both Macs (one universal app), Windows x64 and arm64."""
    for (system, machine), asset in oi.ASSETS.items():
        assert oi.asset_for(system, machine) == asset
        assert "2.4.2" in asset.name.replace("V2.4.2", "2.4.2")
        assert len(asset.sha256) == 64
    assert oi.asset_for("Linux", "aarch64").name.endswith("_aarch64_V2.4.2.AppImage")
    assert oi.asset_for("Darwin", "x86_64") == oi.asset_for("Darwin", "arm64")
    assert oi.asset_for("Windows", "AMD64").name.endswith("_x64_portable.zip")
    assert oi.asset_for("Windows", "ARM64").name.endswith("_arm64_portable.zip")
    assert oi.ORCASLICER_VERSION == "2.4.2" and oi.TAG == "v2.4.2"
    for bad in ("../x", "2.4", "2.4.2/../x", "latest"):
        with pytest.raises(oi.InstallError, match="not an OrcaSlicer version"):
            oi.check_version(bad)


# --- macOS: a fake hdiutil "mounts" a disk image that is a tar ----------------------

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
"""


def _script(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _tar(entries) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, body in entries:
            info = tarfile.TarInfo(name)
            if body is None:
                info.type, info.mode = tarfile.DIRTYPE, 0o755
                tf.addfile(info)
            else:
                info.size, info.mode = len(body), 0o755
                tf.addfile(info, io.BytesIO(body))
    return buf.getvalue()


MAC = "OrcaSlicer_Mac_universal_V2.4.2.dmg"


def test_macos_copies_orcaslicer_app_out_of_the_disk_image_and_detaches_it(
    tools, monkeypatch, tmp_path
):
    _platform(monkeypatch, "Darwin", "arm64")
    _script(tmp_path / "bin" / "hdiutil", HDIUTIL.replace("{python}", sys.executable))
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("FAKE_HDIUTIL_LOG", str(tmp_path / "hdiutil.log"))
    app = "OrcaSlicer.app/Contents"
    image = _tar(
        [
            ("OrcaSlicer.app", None),
            (f"{app}/Info.plist", plistlib.dumps({"CFBundleExecutable": "OrcaSlicer"})),
            (f"{app}/MacOS/OrcaSlicer", b'#!/bin/sh\necho "OrcaSlicer-2.4.2:"\n'),
            (f"{app}/Resources/profiles/Creality.json", b"{}"),
            (f"{app}/Resources/profiles/Creality/machine/fdm_machine_common.json", b"{}"),
        ]
    )
    _pin(monkeypatch, "Darwin", "arm64", MAC, image, oi.DMG)
    github = GitHub({MAC: image})
    path = oi.OrcaSlicerInstaller(fetch=github.fetch, fetch_to=github.fetch_to).install()
    release = tools / "2.4.2"
    assert path == release / "OrcaSlicer.app" / "Contents" / "MacOS" / "OrcaSlicer"
    assert oi.resources_for("2.4.2") == release / "OrcaSlicer.app" / "Contents" / "Resources"
    calls = (tmp_path / "hdiutil.log").read_text().splitlines()
    assert calls[0].startswith("attach -nobrowse -readonly -noautoopen -mountpoint ")
    assert calls[1] == f"detach {calls[0].split()[5]}"
    assert oi.read_manifest("2.4.2")["method"] == "dmg"
    assert _left_in(tools) == ["2.4.2", "current"]


# --- Windows: the portable zip, unpacked --------------------------------------------

WINDOWS = "OrcaSlicer_Windows_V2.4.2_x64_portable.zip"


def _zip(entries) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, body in entries:
            zf.writestr(name, body)
    return buf.getvalue()


def test_windows_unpacks_the_portable_zip_with_its_resources_beside_the_exe(tools, monkeypatch):
    _platform(monkeypatch, "Windows", "AMD64")
    body = _zip(
        [
            ("orca-slicer.exe", '#!/bin/sh\necho "OrcaSlicer-2.4.2:"\n'),
            ("OrcaSlicer.dll", "lib"),
            ("resources/profiles/Creality.json", "{}"),
            ("resources/profiles/Creality/machine/fdm_machine_common.json", "{}"),
        ]
    )
    _pin(monkeypatch, "Windows", "x86_64", WINDOWS, body, oi.ZIP)
    github = GitHub({WINDOWS: body})
    path = oi.OrcaSlicerInstaller(fetch=github.fetch, fetch_to=github.fetch_to).install()
    release = tools / "2.4.2"
    assert path == release / "orca-slicer.exe" and (release / "OrcaSlicer.dll").is_file()
    assert oi.resources_for("2.4.2") == release / "resources"
    assert github.urls == [API, DOWNLOAD + WINDOWS]


@pytest.mark.parametrize("bad", ["../evil.exe", "/abs/evil.exe", "C:/evil.exe", "a/../../evil"])
def test_a_zip_with_a_path_that_leaves_its_folder_installs_nothing(tools, monkeypatch, bad):
    _platform(monkeypatch, "Windows", "AMD64")
    body = _zip([("orca-slicer.exe", "x"), (bad, "x")])
    _pin(monkeypatch, "Windows", "x86_64", WINDOWS, body, oi.ZIP)
    github = GitHub({WINDOWS: body})
    with pytest.raises(oi.InstallError, match="outside its folder"):
        oi.OrcaSlicerInstaller(fetch=github.fetch, fetch_to=github.fetch_to).install()
    assert _left_in(tools) == []


def test_windows_on_arm_takes_its_own_zip_even_from_an_emulated_python(tools, monkeypatch):
    _platform(monkeypatch, "Windows", "AMD64")
    monkeypatch.setattr(openscad_installer, "_windows_native_machine", lambda: "arm64")
    assert oi.asset_for().name == "OrcaSlicer_Windows_V2.4.2_arm64_portable.zip"


# --- the command line ----------------------------------------------------------------


def test_slicer_install_installs_and_then_says_where_it_stands(tools, monkeypatch):
    from click.testing import CliRunner

    from apothecary.cli.main import cli

    body = _appimage()
    github = _linux(monkeypatch, body)
    monkeypatch.setattr(oi, "_fetch", lambda url, **kw: github.fetch(url))
    monkeypatch.setattr(oi, "_fetch_to", lambda url, path, **kw: github.fetch_to(url, path))
    monkeypatch.delenv("APOTHECARY_ORCASLICER", raising=False)
    result = CliRunner().invoke(cli, ["slicer", "install"])
    assert result.exit_code == 0, result.output
    assert "SHA-256 verified" in result.output
    assert "OrcaSlicer 2.4.2 (current)" in result.output
    assert "(tools dir): 2.4.2" in result.output
