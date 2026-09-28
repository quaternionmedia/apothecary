"""The OpenSCAD snapshot installer (apothecary/openscad_installer.py), against a
fake files.openscad.org: a listing, an AppImage that is a shell script, and its
published SHA-256. Nothing here reaches the network."""

from __future__ import annotations

import hashlib
from pathlib import Path

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
        ("Darwin", "arm64", "OpenSCAD-<date>.dmg"),
        ("Windows", "AMD64", "OpenSCAD-<date>-x86-64.zip"),
        ("Linux", "aarch64", "x86_64"),
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
    assert "files.openscad.org and nowhere else" in " ".join(result.output.split())


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
