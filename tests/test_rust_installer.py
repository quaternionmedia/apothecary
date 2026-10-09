"""`apothecary firmware install --rust-esp32`: rustup, espup's Xtensa toolchain,
espflash and the vendored crates, into the tools dir, on each platform served.

Against a scripted fetch and a recording runner: nothing is downloaded or run.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from apothecary import stays_local
from apothecary.firmware import rust_installer as ri
from apothecary.firmware.modules.rust_esp32 import VENDOR_RECORD, vendored

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "system, machine, triple",
    [
        ("Linux", "x86_64", "x86_64-unknown-linux-gnu"),
        ("Linux", "aarch64", "aarch64-unknown-linux-gnu"),
        ("Darwin", "arm64", "aarch64-apple-darwin"),
        ("Windows", "AMD64", "x86_64-pc-windows-msvc"),
    ],
)
def test_each_platform_served_has_its_triple(system, machine, triple):
    assert ri.host_triple(system, machine) == triple
    assert ri.refusal(system, machine) is None


@pytest.mark.parametrize(
    "system, machine, why",
    [
        ("Darwin", "x86_64", "Apple Silicon only"),
        ("Windows", "arm64", "no ARM64 Windows build"),
        ("Linux", "armv7l", "Linux x86_64 and arm64"),
        ("FreeBSD", "amd64", "Linux x86_64 and arm64"),
    ],
)
def test_a_platform_it_cannot_serve_is_refused_saying_why(system, machine, why):
    with pytest.raises(ri.InstallError, match=why):
        ri.host_triple(system, machine)
    assert why in ri.refusal(system, machine)


def test_published_checksums_are_read_and_a_bad_one_refused():
    sha = "ab" * 32
    assert ri.published_sha256(f"{sha} *./rustup-init\n") == sha
    with pytest.raises(ri.InstallError, match="no SHA-256"):
        ri.published_sha256("<html>not found</html>")
    release = json.dumps(
        {"assets": [{"name": "espup-x86_64-unknown-linux-gnu", "digest": f"sha256:{sha}"}]}
    ).encode()
    fetched = []

    def fetch(url):
        fetched.append(url)
        return release

    assert (
        ri.github_digest("esp-rs/espup", "0.17.1", "espup-x86_64-unknown-linux-gnu", fetch) == sha
    )
    assert fetched == ["https://api.github.com/repos/esp-rs/espup/releases/tags/v0.17.1"]
    with pytest.raises(ri.InstallError, match="publishes no"):
        ri.github_digest("esp-rs/espup", "0.17.1", "espup-other", fetch)
    with pytest.raises(ri.InstallError, match="not a version"):
        ri.github_digest("esp-rs/espup", "0.17/../../x", "espup", fetch)
    with pytest.raises(ri.InstallError, match="not an asset name"):
        ri.github_digest("esp-rs/espup", "0.17.1", "../x", fetch)


class Bench:
    """The internet as the installer sees it, and what it runs, recorded."""

    def __init__(self, triple: str, home: Path):
        self.triple = triple
        self.home = home
        self.fetched: list[str] = []
        self.ran: list[tuple[list[str], dict, str]] = []
        windows = "windows" in triple
        self.ext = ".exe" if windows else ""
        self.files = {}
        init = b"rustup-init for " + triple.encode()
        base = f"{ri.RUSTUP_ARCHIVE}/{ri.RUSTUP_VERSION}/{triple}/rustup-init{self.ext}"
        self.files[base] = init
        self.files[base + ".sha256"] = (
            hashlib.sha256(init).hexdigest() + f" *./rustup-init{self.ext}\n"
        ).encode()
        espup_asset = f"espup-{triple}{self.ext}"
        espup = b"espup for " + triple.encode()
        self.files[
            f"{ri.GITHUB}/{ri.ESPUP_REPO}/releases/download/v{ri.ESPUP_VERSION}/{espup_asset}"
        ] = espup
        self.files[f"{ri.GITHUB_API}/{ri.ESPUP_REPO}/releases/tags/v{ri.ESPUP_VERSION}"] = (
            json.dumps(
                {
                    "assets": [
                        {
                            "name": espup_asset,
                            "digest": "sha256:" + hashlib.sha256(espup).hexdigest(),
                        }
                    ]
                }
            ).encode()
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(f"espflash{self.ext}", b"espflash for " + triple.encode())
        archive = buf.getvalue()
        espflash_asset = f"espflash-{triple}.zip"
        self.files[
            f"{ri.GITHUB}/{ri.ESPFLASH_REPO}/releases/download/v{ri.ESPFLASH_VERSION}/{espflash_asset}"
        ] = archive
        self.files[f"{ri.GITHUB_API}/{ri.ESPFLASH_REPO}/releases/tags/v{ri.ESPFLASH_VERSION}"] = (
            json.dumps(
                {
                    "assets": [
                        {
                            "name": espflash_asset,
                            "digest": "sha256:" + hashlib.sha256(archive).hexdigest(),
                        }
                    ]
                }
            ).encode()
        )

    def fetch(self, url: str) -> bytes:
        self.fetched.append(url)
        return self.files[url]

    def run(self, argv, env=None, cwd=None) -> int:
        self.ran.append((list(argv), dict(env or {}), str(cwd) if cwd else None))
        name = Path(argv[0]).name
        if name.startswith("rustup-init"):
            for tool in ("rustup", "cargo", "rustc"):
                path = Path(env["CARGO_HOME"]) / "bin" / f"{tool}{self.ext}"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("proxy")
        elif name.startswith("espup"):
            bin_ = Path(env["RUSTUP_HOME"]) / "toolchains" / "esp" / "bin"
            bin_.mkdir(parents=True, exist_ok=True)
            (bin_ / f"rustc{self.ext}").write_text("rustc")
            Path(argv[argv.index("--export-file") + 1]).write_text(
                'export PATH="/esp/xtensa-esp-elf/bin:$PATH"\n'
            )
        elif "vendor" in argv:
            Path(argv[-1]).mkdir(parents=True)
        return 0


@pytest.fixture
def tools(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.setattr(ri, "linker_problem", lambda triple: None)
    library = tmp_path / "sysroot" / "lib" / "rustlib" / "src" / "rust" / "library"
    library.mkdir(parents=True)
    (library / "Cargo.toml").write_text("[workspace]\n")
    monkeypatch.setattr(ri.RustEsp32Installer, "sysroot", lambda self: tmp_path / "sysroot")
    return tmp_path / "tools" / "rust-esp32"


@pytest.mark.parametrize(
    "triple", ["x86_64-unknown-linux-gnu", "aarch64-apple-darwin", "x86_64-pc-windows-msvc"]
)
def test_an_install_fetches_each_tool_once_verified_into_the_tools_dir(tools, triple):
    bench = Bench(triple, tools)
    log = []
    installer = ri.RustEsp32Installer(
        log=log.append, fetch=bench.fetch, run=bench.run, triple=triple
    )
    record = installer.install()
    ext = bench.ext

    # Every fetch is to a tool source, and apothecary verifies each download.
    assert {urlsplit(u).hostname for u in bench.fetched} <= stays_local.TOOL_SOURCES
    assert sum("SHA-256 verified" in line for line in log) == 3

    # 1. rustup, its homes in the tools dir and no toolchain of its own.
    init, env, _ = bench.ran[0]
    assert init == [
        str(tools / "downloads" / f"rustup-init{ext}"),
        "-y",
        "--no-modify-path",
        "--default-toolchain",
        "none",
        "--profile",
        "minimal",
    ]
    assert env["CARGO_HOME"] == str(tools / "cargo")
    assert env["RUSTUP_HOME"] == str(tools / "rustup")
    assert ".cargo" not in env["CARGO_HOME"] and ".rustup" not in env["RUSTUP_HOME"]

    # 2. espup's Xtensa toolchain, pinned; its ~/.espup in the tools dir too.
    espup, env, _ = bench.ran[1]
    assert espup[0] == str(tools / "bin" / f"espup{ext}")
    assert espup[1:] == [
        "install",
        "--targets",
        "esp32",
        "--name",
        "esp",
        "--toolchain-version",
        ri.XTENSA_RUST_VERSION,
        "--export-file",
        str(tools / ("export-esp.ps1" if "windows" in triple else "export-esp.sh")),
    ]
    assert env["HOME"] == str(tools / "home")
    assert bench.ran[2][0] == [str(tools / "cargo" / "bin" / f"rustup{ext}"), "default", "esp"]

    # 3. espflash, out of its zip.
    assert (tools / "bin" / f"espflash{ext}").read_bytes() == b"espflash for " + triple.encode()

    # 4. The crates: every Rust sketch's lockfile and build-std's library, vendored.
    vendor_argv, _, cwd = bench.ran[3]
    assert vendor_argv[:5] == [
        str(tools / "cargo" / "bin" / f"cargo{ext}"),
        "+esp",
        "vendor",
        "--versioned-dirs",
        "--locked",
    ]
    rust_manifest = ROOT / "parts" / "esp32_blink" / "rust" / "Cargo.toml"
    assert vendor_argv[vendor_argv.index("--manifest-path") + 1] == str(rust_manifest)
    library = vendor_argv[vendor_argv.index("--sync") + 1]
    assert library.endswith(str(Path("rust", "library", "Cargo.toml")))
    assert (tools / "vendor" / VENDOR_RECORD).is_file()
    assert "esp32_blink@rust-esp32" in vendored()
    assert record["vendored"] == ["esp32_blink@rust-esp32"]
    manifest = json.loads((tools / "install.json").read_text())
    assert manifest["triple"] == triple
    assert manifest["xtensa_rust"]["version"] == ri.XTENSA_RUST_VERSION
    assert manifest["espflash"]["version"] == ri.ESPFLASH_VERSION


def test_a_second_install_fetches_nothing_and_vendors_again(tools):
    triple = "x86_64-unknown-linux-gnu"
    bench = Bench(triple, tools)
    ri.RustEsp32Installer(fetch=bench.fetch, run=bench.run, triple=triple).install()
    bench.fetched.clear()
    bench.ran.clear()
    log = []
    ri.RustEsp32Installer(log=log.append, fetch=bench.fetch, run=bench.run, triple=triple).install()
    assert bench.fetched == []
    assert [argv[2] for argv, _, _ in bench.ran] == ["vendor"]
    assert any("rustup already installed" in line for line in log)
    assert any("already installed" in line and "Xtensa" in line for line in log)
    # Forced, the tools come again.
    bench.ran.clear()
    ri.RustEsp32Installer(fetch=bench.fetch, run=bench.run, triple=triple, force=True).install()
    assert len(bench.ran) == 4 and bench.fetched


def test_a_download_that_does_not_match_its_checksum_is_refused_before_it_runs(tools):
    triple = "x86_64-unknown-linux-gnu"
    bench = Bench(triple, tools)
    url = f"{ri.RUSTUP_ARCHIVE}/{ri.RUSTUP_VERSION}/{triple}/rustup-init"
    bench.files[url] = b"something else"
    with pytest.raises(ri.InstallError, match="checksum mismatch for rustup-init"):
        ri.RustEsp32Installer(fetch=bench.fetch, run=bench.run, triple=triple).install()
    assert bench.ran == []
    assert not (tools / "downloads" / "rustup-init").exists()


def test_a_machine_without_a_linker_is_refused_with_what_installs_one(tmp_path, monkeypatch):
    monkeypatch.setattr(ri.shutil, "which", lambda name: None)
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path))
    assert "build-essential" in ri.linker_problem("x86_64-unknown-linux-gnu")
    assert "xcode-select --install" in ri.linker_problem("aarch64-apple-darwin")
    assert "Visual Studio Build Tools" in ri.linker_problem("x86_64-pc-windows-msvc")
    monkeypatch.setenv("APOTHECARY_TOOLS_DIR", str(tmp_path / "tools"))
    fetched = []
    installer = ri.RustEsp32Installer(fetch=fetched.append, triple="x86_64-unknown-linux-gnu")
    with pytest.raises(ri.InstallError, match="build-essential"):
        installer.install()
    assert fetched == []


def test_a_sketch_without_a_lockfile_is_not_vendored(tools, tmp_path, monkeypatch):
    """A sketch's crates are vendored from its lockfile, so what is built is written down."""
    from apothecary.firmware import sketches

    parts = tmp_path / "repo" / "parts" / "pump" / "rust"
    (parts / "src").mkdir(parents=True)
    (parts / "Cargo.toml").write_text('[package]\nname = "pump"\nversion = "0.1.0"\n')
    (parts / "firmware.json").write_text('{"toolchain": "rust-esp32"}')
    real = sketches.discover_sketches
    monkeypatch.setattr(sketches, "discover_sketches", lambda root=None: real(tmp_path / "repo"))
    triple = "x86_64-unknown-linux-gnu"
    bench = Bench(triple, tools)
    with pytest.raises(ri.InstallError, match="no Cargo.lock for pump@rust-esp32"):
        ri.RustEsp32Installer(fetch=bench.fetch, run=bench.run, triple=triple).install()
