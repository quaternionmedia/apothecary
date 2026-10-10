"""`apothecary firmware install --rust-esp32`: rustup, Espressif's Xtensa toolchain
(Rust, rust-src, LLVM, GCC -- fetched and checked by apothecary itself, laid out
as espup lays them out), espflash and the vendored crates, into the tools dir, on
each platform served.

Against a scripted fetch, scripted archives and a recording runner: nothing is
downloaded or run.
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
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
        ("Windows", "arm64", "no ARM64 Windows Xtensa Rust"),
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
    listing = f"# gcc.tar.xz: 12 bytes\n{sha} *gcc.tar.xz\n{'cd' * 32} *llvm.tar.xz\n"
    assert ri.listed_sha256(listing, "gcc.tar.xz") == sha
    with pytest.raises(ri.InstallError, match="no SHA-256 listed for other.tar.xz"):
        ri.listed_sha256(listing, "other.tar.xz")
    release = json.dumps(
        {"assets": [{"name": "espflash-x86_64-unknown-linux-gnu.zip", "digest": f"sha256:{sha}"}]}
    ).encode()
    fetched = []

    def fetch(url):
        fetched.append(url)
        return release

    asset = "espflash-x86_64-unknown-linux-gnu.zip"
    assert ri.github_digest("esp-rs/espflash", "4.6.0", asset, fetch) == sha
    assert fetched == ["https://api.github.com/repos/esp-rs/espflash/releases/tags/v4.6.0"]
    with pytest.raises(ri.InstallError, match="publishes no"):
        ri.github_digest("esp-rs/espflash", "4.6.0", "espflash-other.zip", fetch)
    with pytest.raises(ri.InstallError, match="not a version"):
        ri.github_digest("esp-rs/espflash", "4.6/../../x", "espflash", fetch)
    with pytest.raises(ri.InstallError, match="not an asset name"):
        ri.github_digest("esp-rs/espflash", "4.6.0", "../x", fetch)
    with pytest.raises(ri.InstallError, match="not an Espressif release"):
        ri.check_esp_version("esp-20.1.1_20250829/../../x")


def _tar_xz(files: dict) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


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
        espflash = _zip({f"espflash{self.ext}": b"espflash for " + triple.encode()})
        espflash_asset = f"espflash-{triple}.zip"
        self.files[
            f"{ri.GITHUB}/{ri.ESPFLASH_REPO}/releases/download/v{ri.ESPFLASH_VERSION}/{espflash_asset}"
        ] = espflash
        self.digests(ri.ESPFLASH_REPO, f"v{ri.ESPFLASH_VERSION}", {espflash_asset: espflash})
        # The Xtensa toolchain, archive by archive, as Espressif publishes it.
        installer = ri.RustEsp32Installer(triple=triple)
        rust_build = {}
        listed = {}
        for archive in installer.archives():
            data = self.archive(archive.part, windows)
            self.files[archive.url] = data
            if archive.github:
                rust_build[archive.name] = data
            else:
                listed.setdefault(f"{archive.base}/{archive.checksums}", {})[archive.name] = data
        self.digests(ri.RUST_BUILD_REPO, f"v{ri.XTENSA_RUST_VERSION}", rust_build)
        for url, entries in listed.items():
            self.files[url] = "".join(
                f"# {name}: {len(data)} bytes\n{hashlib.sha256(data).hexdigest()} *{name}\n"
                for name, data in entries.items()
            ).encode()

    def digests(self, repo: str, tag: str, assets: dict) -> None:
        self.files[f"{ri.GITHUB_API}/{repo}/releases/tags/{tag}"] = json.dumps(
            {
                "assets": [
                    {"name": n, "digest": "sha256:" + hashlib.sha256(d).hexdigest()}
                    for n, d in assets.items()
                ]
            }
        ).encode()

    def archive(self, part: str, windows: bool) -> bytes:
        ext = self.ext
        if part == "rust" and windows:
            return _zip(
                {
                    f"esp/bin/rustc{ext}": b"rustc",
                    f"esp/bin/cargo{ext}": b"cargo",
                    "esp/lib/rustlib/src/rust/library/Cargo.toml": b"[workspace]\n",
                }
            )
        if part == "rust":
            root = f"rust-nightly-{self.triple}"
            return _tar_xz(
                {
                    f"{root}/components": b"rustc\ncargo\nrust-docs\n",
                    f"{root}/install.sh": b"#!/bin/sh\nexit 1  # never run\n",
                    f"{root}/rustc/manifest.in": b"file:bin/rustc\ndir:lib/rustlib/x86\n",
                    f"{root}/rustc/bin/rustc": b"rustc",
                    f"{root}/rustc/lib/rustlib/x86/libstd.rlib": b"std",
                    f"{root}/cargo/manifest.in": b"file:bin/cargo\n",
                    f"{root}/cargo/bin/cargo": b"cargo",
                    f"{root}/rust-docs/manifest.in": b"file:share/doc/index.html\n",
                    f"{root}/rust-docs/share/doc/index.html": b"docs",
                }
            )
        if part == "rust-src":
            return _tar_xz(
                {
                    "rust-src-nightly/components": b"rust-src\n",
                    "rust-src-nightly/rust-src/manifest.in": (
                        b"file:lib/rustlib/src/rust/library/Cargo.toml\n"
                    ),
                    "rust-src-nightly/rust-src/lib/rustlib/src/rust/library/Cargo.toml": (
                        b"[workspace]\n"
                    ),
                }
            )
        if part == "llvm":
            lib = "esp-clang/bin/libclang.dll" if windows else "esp-clang/lib/libclang.so"
            return _tar_xz({lib: b"libclang"})
        gcc = {f"xtensa-esp-elf/bin/xtensa-esp32-elf-gcc{ext}": b"gcc"}
        return _zip(gcc) if windows else _tar_xz(gcc)

    def fetch(self, url: str) -> bytes:
        self.fetched.append(url)
        return self.files[url]

    def fetch_to(self, url: str, path: Path) -> str:
        data = self.fetch(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    def run(self, argv, env=None, cwd=None) -> int:
        self.ran.append((list(argv), dict(env or {}), str(cwd) if cwd else None))
        name = Path(argv[0]).name
        if name.startswith("rustup-init"):
            for tool in ("rustup", "cargo", "rustc"):
                path = Path(env["CARGO_HOME"]) / "bin" / f"{tool}{self.ext}"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("proxy")
        elif argv[1:3] == ["toolchain", "link"]:
            link = Path(env["RUSTUP_HOME"]) / "toolchains" / argv[3]
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(argv[4])
        elif argv[1:3] == ["toolchain", "uninstall"]:
            import shutil

            shutil.rmtree(Path(env["RUSTUP_HOME"]) / "toolchains" / argv[3])
        elif "vendor" in argv:
            Path(argv[-1]).mkdir(parents=True)
        return 0

    def installer(self, **kw) -> ri.RustEsp32Installer:
        return ri.RustEsp32Installer(
            fetch=self.fetch, fetch_to=self.fetch_to, run=self.run, triple=self.triple, **kw
        )


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
def test_an_install_fetches_each_thing_once_checked_into_the_tools_dir(tools, triple):
    bench = Bench(triple, tools)
    log = []
    record = bench.installer(log=log.append).install()
    ext = bench.ext
    windows = "windows" in triple
    toolchain = tools / "xtensa" / ri.XTENSA_RUST_VERSION

    # Every fetch is to a tool source, and every download is checked.
    assert {urlsplit(u).hostname for u in bench.fetched} <= stays_local.TOOL_SOURCES
    downloads = 2 + len(bench.installer().archives())  # rustup-init, espflash, the archives
    assert sum("SHA-256 verified" in line for line in log) == downloads
    # Each archive checked against what its source publishes: Espressif's own
    # checksum files for LLVM and GCC, GitHub's digest for rust-build's.
    assert any(u.endswith(f"libs-clang-{ri.LLVM_VERSION}-checksum.sha256") for u in bench.fetched)
    assert any(
        u.endswith(f"crosstool-NG-esp-{ri.GCC_VERSION}-checksum.sha256") for u in bench.fetched
    )
    assert f"{ri.GITHUB_API}/{ri.RUST_BUILD_REPO}/releases/tags/v{ri.XTENSA_RUST_VERSION}" in (
        bench.fetched
    )
    assert not [u for u in bench.fetched if "espup" in u]  # espup is not fetched, nor run

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

    # 2. The Xtensa toolchain, laid out as espup lays it out, linked as rustup's esp.
    assert (toolchain / "bin" / f"rustc{ext}").read_bytes() == b"rustc"
    assert (toolchain / "lib" / "rustlib" / "src" / "rust" / "library" / "Cargo.toml").is_file()
    assert not (toolchain / "share" / "doc").exists()  # the docs are not installed
    if windows:
        assert (
            toolchain / "xtensa-esp32-elf-clang" / "esp-clang" / "bin" / "libclang.dll"
        ).is_file()
        assert (toolchain / "xtensa-esp-elf" / "bin" / f"xtensa-esp32-elf-gcc{ext}").is_file()
    else:
        assert (toolchain / "lib" / "rustlib" / "x86" / "libstd.rlib").is_file()
        assert (
            toolchain
            / "xtensa-esp32-elf-clang"
            / ri.LLVM_VERSION
            / "esp-clang"
            / "lib"
            / "libclang.so"
        ).is_file()
        gcc_bin = toolchain / "xtensa-esp-elf" / f"esp-{ri.GCC_VERSION}" / "xtensa-esp-elf" / "bin"
        assert (gcc_bin / "xtensa-esp32-elf-gcc").is_file()
        export = (tools / "export-esp.sh").read_text()
        assert f'export PATH="{gcc_bin}:$PATH"' in export
    rustup = str(tools / "cargo" / "bin" / f"rustup{ext}")
    assert [argv for argv, _, _ in bench.ran[1:3]] == [
        [rustup, "toolchain", "link", "esp", str(toolchain)],
        [rustup, "default", "esp"],
    ]
    assert not list((tools / "downloads").glob("*.tar.xz"))  # unpacked, then let go

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
    pins = manifest["xtensa_rust"]
    assert (pins["version"], pins["llvm"], pins["gcc"]) == (
        ri.XTENSA_RUST_VERSION,
        ri.LLVM_VERSION,
        ri.GCC_VERSION,
    )
    assert set(pins["archives"]) == {a.name for a in bench.installer().archives()}
    assert manifest["espflash"]["version"] == ri.ESPFLASH_VERSION


def test_a_second_install_fetches_nothing_and_vendors_again(tools):
    bench = Bench("x86_64-unknown-linux-gnu", tools)
    bench.installer().install()
    bench.fetched.clear()
    bench.ran.clear()
    log = []
    bench.installer(log=log.append).install()
    assert bench.fetched == []
    # The link stands; the crates are vendored afresh.
    assert [argv[1:3] for argv, _, _ in bench.ran] == [["default", "esp"], ["+esp", "vendor"]]
    assert any("rustup already installed" in line for line in log)
    assert any("already installed" in line and "Xtensa" in line for line in log)
    # Forced, everything comes again.
    bench.ran.clear()
    bench.installer(force=True).install()
    assert [argv[1:3] for argv, _, _ in bench.ran][1:] == [["default", "esp"], ["+esp", "vendor"]]
    assert len(bench.fetched) > 5  # rustup-init, espflash and every archive again


def test_an_install_over_espup_s_toolchain_uninstalls_it_and_links_its_own(tools):
    """An esp toolchain espup installed is a folder of rustup's own: rustup uninstalls
    it, then links the one apothecary laid out."""
    bench = Bench("x86_64-unknown-linux-gnu", tools)
    espup_s = tools / "rustup" / "toolchains" / "esp" / "bin"
    espup_s.mkdir(parents=True)
    (espup_s / "rustc").write_text("espup's")
    bench.installer().install()
    calls = [argv[1:3] for argv, _, _ in bench.ran]
    assert calls.index(["toolchain", "uninstall"]) + 1 == calls.index(["toolchain", "link"])


def test_an_archive_that_does_not_match_its_checksum_is_refused_before_it_is_opened(tools):
    triple = "x86_64-unknown-linux-gnu"
    bench = Bench(triple, tools)
    gcc = next(a for a in bench.installer().archives() if a.part == "gcc")
    bench.files[gcc.url] = b"something else"
    with pytest.raises(ri.InstallError, match=f"checksum mismatch for {gcc.name}"):
        bench.installer().install()
    assert not (tools / "downloads" / gcc.name).exists()
    assert not (tools / "xtensa" / ri.XTENSA_RUST_VERSION).exists()
    assert not [argv for argv, _, _ in bench.ran if argv[1:3] == ["toolchain", "link"]]


def test_a_download_that_does_not_match_its_checksum_is_refused_before_it_runs(tools):
    triple = "x86_64-unknown-linux-gnu"
    bench = Bench(triple, tools)
    url = f"{ri.RUSTUP_ARCHIVE}/{ri.RUSTUP_VERSION}/{triple}/rustup-init"
    bench.files[url] = b"something else"
    with pytest.raises(ri.InstallError, match="checksum mismatch for rustup-init"):
        bench.installer().install()
    assert bench.ran == []
    assert not (tools / "downloads" / "rustup-init").exists()


def test_an_archive_member_that_leaves_its_folder_is_refused(tmp_path):
    bad = tmp_path / "bad.tar.xz"
    bad.write_bytes(_tar_xz({"../escaped": b"x"}))
    with pytest.raises(ri.InstallError, match="leaves its folder"):
        ri.unpack(bad, tmp_path / "into")
    assert not (tmp_path / "escaped").exists()
    badzip = tmp_path / "bad.zip"
    badzip.write_bytes(_zip({"../escaped": b"x"}))
    with pytest.raises(ri.InstallError, match="leaves its folder"):
        ri.unpack(badzip, tmp_path / "into")


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
    bench = Bench("x86_64-unknown-linux-gnu", tools)
    with pytest.raises(ri.InstallError, match="no Cargo.lock for pump@rust-esp32"):
        bench.installer().install()


def test_the_pins_and_their_rule_are_written_where_they_live():
    """A pin moves by hand, in a commit that re-runs the real install and build."""
    assert "moves only in a" in ri.__doc__ and "re-runs a\nreal install" in ri.__doc__
    for pin in (ri.RUSTUP_VERSION, ri.ESPFLASH_VERSION, ri.XTENSA_RUST_VERSION):
        assert ri.check_version(pin) == pin
    for pin in (ri.LLVM_VERSION, ri.GCC_VERSION):
        assert ri.check_esp_version(pin) == pin
