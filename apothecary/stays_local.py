"""Personal data stays on this machine -- by the shape of the program, not by
a setting.

Four things, none of them a flag, an environment variable, a config file or
a button, so neither a person nor an agent can switch them off without
editing this code and having that edit reviewed:

1. **The process cannot reach past this machine.** ``install_guard()`` swaps
   the socket class for one that refuses to connect anywhere but loopback
   (127/8, ::1) or a Unix socket, and the name resolver for one that refuses
   to look up any name but a loopback one -- a hostname is the one place a
   process could smuggle data out without a connection. It is installed when
   the ``apothecary`` package is imported, so every apothecary process -- the
   server, the CLI, the docs generator's server, the tests -- is under it
   before any of its code runs. The one allowance is a *tool fetch*: the
   firmware installer downloads arduino-cli, and it does so through
   ``tool_fetch()``, which admits, for the duration of that one call on that
   one thread, connections to the fixed hosts in ``TOOL_SOURCES`` -- by name,
   or by an address the guarded resolver returned for one of them -- and
   nowhere else, with no proxy in the way. A tool fetch is a GET of a release archive
   at a URL built from a version string; no personal data is in it, and a
   test holds the callers of ``tool_fetch`` to the installer alone.

2. **The server refuses to listen anywhere but this machine, and refuses
   anyone who is not on it.** ``require_loopback()`` is what every ``--host``
   goes through: a non-loopback address is an error naming this record, not a
   choice. ``LocalOnly`` is an ASGI middleware on the app itself, so a server
   started some other way (``uvicorn apothecary.api:app --host 0.0.0.0``)
   still answers a request with 403 unless the client, the address it
   arrived on and the ``Host`` it asked for are all this machine -- the last
   is what stops a page from elsewhere that has pointed its own name at
   127.0.0.1 from reading this server as itself.

3. **The pages the server sends cannot load from or send to another
   origin.** The same middleware puts a Content-Security-Policy on every
   response: scripts, styles, images, media, fonts, fetches, workers and
   forms may use this origin only (images and media also ``blob:`` and
   ``data:`` for a camera frame drawn on a canvas); no frames, no referrer.
   A page that tried to post a picture elsewhere would be stopped by the
   browser before the request left.

4. **A subprocess that fetches is told where, and nothing else tells it.**
   arduino-cli, esptool and OpenSCAD are outside the socket guard (it is a
   Python object). Of the three only arduino-cli reaches out, and it is a
   program that will, left to itself, ask Arduino's cloud about every USB
   device it does not recognise and check for its own updates. Every
   arduino-cli the seam starts is given ``--config-file`` naming a file this
   package writes (``ARDUINO_CLI_CONFIG``): the board lookup off, the update
   check off, the package indexes it may fetch named. Its environment is
   ``subprocess_env()``: this process's, minus every proxy variable and every
   ``ARDUINO_*`` override, since arduino-cli lets either outrank the file.
   What it may still fetch -- indexes, cores, libraries from the hosts in
   that file -- is a tool fetch in all but mechanism, and nothing personal is
   in it.

**The named exception, not yet built:** *secured user accounts*. A future
record may let data leave this machine for an account the person holds and
has authenticated, with consent given per account and revocable. Until such
a record is Accepted there is no code path for it, and this module is what
would have to change. See the draft *Personal data stays on the device* in
``governance/qm/adr/``.
"""

from __future__ import annotations

import http.client
import ipaddress
import operator
import os
import socket
import ssl
import sys
import threading
from typing import Callable, Iterable, Mapping, Optional
from urllib.parse import urlsplit

LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "::1", "0:0:0:0:0:0:0:1", "ip6-localhost"})

# The fixed hosts a tool fetch may reach: arduino-cli's releases (the API
# that names the latest, the archive, and where GitHub redirects the archive).
TOOL_SOURCES = frozenset(
    {
        "api.github.com",
        "github.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
        "downloads.arduino.cc",
    }
)


class LeftTheMachine(OSError):
    """A connection to somewhere other than this machine was refused."""


def is_loopback(host: object) -> bool:
    """Whether an address (a string, or a socket address tuple) is this machine."""
    if isinstance(host, (tuple, list)):
        host = host[0] if host else ""
    if host is None:
        return False
    if isinstance(host, bytes):
        host = host.decode("utf-8", "replace")
    if not isinstance(host, str):
        return False
    text = host.strip().lower()
    if text in LOOPBACK_NAMES or text == "":
        return text != ""
    if "%" in text:  # a scoped IPv6 address, fe80::1%eth0
        text = text.split("%", 1)[0]
    try:
        return ipaddress.ip_address(text).is_loopback
    except ValueError:
        return False


# --- 1. the process cannot reach past this machine ------------------------------------------

_fetching = threading.local()
_installed = False
_original_socket: Optional[type] = None
_original_create_connection: Optional[Callable] = None
_original_http_connect: Optional[Callable] = None
_original_getaddrinfo: Optional[Callable] = None
_original_gethostbyaddr: Optional[Callable] = None
_original_getnameinfo: Optional[Callable] = None
_original_ssl_connect: Optional[Callable] = None


def _allowed_now() -> bool:
    return bool(getattr(_fetching, "hosts", None))


def _is_numeric(host: str) -> bool:
    try:
        ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False
    return True


def _name_allowed(host: object) -> bool:
    """Whether a name may be resolved: nothing (a bind), a literal address, a
    loopback name, or -- inside a tool fetch -- one of its sources."""
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("utf-8", "replace")
    if not isinstance(host, str):
        return False
    text = host.strip().lower().rstrip(".")
    if text == "" or is_loopback(text) or _is_numeric(text):
        return True
    allowed = getattr(_fetching, "hosts", None)
    return bool(allowed) and text in allowed


def _refuse(where: str, address: object) -> None:
    raise LeftTheMachine(
        f"{where}: refused to reach {address!r}. Apothecary keeps personal data on this "
        "machine by construction; nothing in it connects anywhere else. (The named "
        "exception, secured user accounts, is not built.)"
    )


DNS_PORT = 53


def _port_of(address) -> Optional[int]:
    """The port of a socket address, read as the C layer reads it; -1 if it is not one."""
    if isinstance(address, (tuple, list)) and len(address) > 1:
        try:
            return operator.index(address[1])
        except TypeError:
            return -1
    return None


def _host_of(address) -> str:
    host = address[0] if isinstance(address, (tuple, list)) and address else address
    if isinstance(host, bytes):
        host = host.decode("utf-8", "replace")
    return host.strip().lower() if isinstance(host, str) else ""


def _in_fetch(address) -> bool:
    """Inside a tool fetch: one of its sources by name, or an address the guarded
    resolver returned for one of them -- those hosts alone, as the record says."""
    hosts = getattr(_fetching, "hosts", None)
    if not hosts:
        return False
    host = _host_of(address).rstrip(".")
    if host in hosts:
        return True
    return host.split("%", 1)[0] in getattr(_fetching, "addresses", set())


def _address_allowed(address) -> bool:
    # Port 53 on loopback is the resolver's stub, which forwards whatever it is
    # sent; a name is asked through the guarded resolver, never by hand.
    if _port_of(address) in (DNS_PORT, -1):
        return False
    return is_loopback(address) or _in_fetch(address)


def _check(sock, where: str, address) -> None:
    if getattr(sock, "family", None) == socket.AF_UNIX:
        return
    if _address_allowed(address):
        return
    _refuse(where, address)


def _guarded(base: type, name: str) -> type:
    """A subclass of ``base`` whose connects are checked; ``base`` itself is left as it is."""

    class Guarded(base):  # type: ignore[misc,valid-type]
        def connect(self, address):
            _check(self, f"{name}.connect", address)
            return super().connect(address)

        def connect_ex(self, address):
            _check(self, f"{name}.connect_ex", address)
            return super().connect_ex(address)

        def sendto(self, *args):
            _check(self, f"{name}.sendto", args[-1])
            return super().sendto(*args)

        def sendmsg(self, *args, **kwargs):
            address = kwargs.get("address", args[3] if len(args) > 3 else None)
            if address is not None:
                _check(self, f"{name}.sendmsg", address)
            return super().sendmsg(*args, **kwargs)

        def bind(self, address):
            # A listener is this machine's or it is not one: 0.0.0.0, a LAN
            # address or a name that is not ours are refused here, before
            # the middleware ever sees a request.
            if getattr(self, "family", None) != socket.AF_UNIX and not is_loopback(address):
                _refuse(f"{name}.bind", address)
            return super().bind(address)

    Guarded.__name__ = Guarded.__qualname__ = base.__name__
    Guarded.__module__ = base.__module__
    return Guarded


def install_guard() -> bool:
    """Put the guard on this process. Idempotent; returns whether it was newly installed.

    ``socket.socket`` (the Python class, with makefile and friends) and
    ``_socket.socket`` (the C class underneath, which some callers use
    directly) are each replaced by a checked subclass of themselves; the
    Python class keeps the original C class as its base, so nothing recurses.
    ``socket.create_connection`` and ``http.client.HTTPConnection.connect``
    are wrapped as well: the latter is where a hostname is still a name, and
    where a tool fetch is held to its sources whatever a redirect says.
    ``ssl.SSLSocket`` was built on the original class before this ran, so its
    connect is checked by name; ``getaddrinfo`` and the ``gethostbyname``
    pair refuse to look up any name that is not this machine or a tool
    source, so no name carries data out; and the reverse lookups
    (``gethostbyaddr``, ``getnameinfo``) ask about this machine's addresses
    alone, so no address goes out as a question either.
    """
    global _installed, _original_socket, _original_create_connection, _original_http_connect
    global _original_getaddrinfo, _original_ssl_connect, _original_gethostbyaddr
    global _original_getnameinfo
    if _installed:
        return False
    import _socket

    _original_socket = socket.socket
    _original_create_connection = socket.create_connection
    _original_http_connect = http.client.HTTPConnection.connect
    _original_getaddrinfo = _socket.getaddrinfo
    _original_gethostbyaddr = _socket.gethostbyaddr
    _original_getnameinfo = _socket.getnameinfo
    _original_ssl_connect = ssl.SSLSocket._real_connect
    original_c_socket = _socket.socket

    def create_connection(address, *args, **kwargs):
        if not _address_allowed(address):
            _refuse("socket.create_connection", address)
        return _original_create_connection(address, *args, **kwargs)

    def http_connect(self):
        host = (self.host or "").lower()
        if not is_loopback(host):
            allowed = getattr(_fetching, "hosts", None)
            if not allowed or host not in allowed:
                _refuse("http.client.connect", host)
        return _original_http_connect(self)

    def getaddrinfo(host, port, *args, **kwargs):
        if not _name_allowed(host):
            _refuse("socket.getaddrinfo", host)
        found = _original_getaddrinfo(host, port, *args, **kwargs)
        hosts = getattr(_fetching, "hosts", None)
        if hosts and _host_of(host).rstrip(".") in hosts:
            # What a source resolves to is what the fetch may connect to.
            known = getattr(_fetching, "addresses", None)
            if known is None:
                known = _fetching.addresses = set()
            known.update(str(entry[4][0]).lower() for entry in found)
        return found

    def gethostbyaddr(address, *args, **kwargs):
        # A reverse lookup sends the address out; only this machine's are asked.
        if not (is_loopback(address) or _host_of(address) == socket.gethostname().lower()):
            _refuse("socket.gethostbyaddr", address)
        return _original_gethostbyaddr(address, *args, **kwargs)

    def getnameinfo(sockaddr, *args, **kwargs):
        # The other reverse lookup, asyncio's included.
        if not is_loopback(sockaddr):
            _refuse("socket.getnameinfo", sockaddr)
        return _original_getnameinfo(sockaddr, *args, **kwargs)

    def by_name(original, name):
        def lookup(host, *args, **kwargs):
            if not _name_allowed(host):
                _refuse(f"socket.{name}", host)
            return original(host, *args, **kwargs)

        return lookup

    def ssl_connect(self, addr, connect_ex):
        _check(self, "ssl.SSLSocket.connect", addr)
        return _original_ssl_connect(self, addr, connect_ex)

    guarded_py = _guarded(socket.socket, "socket")
    guarded_c = _guarded(_socket.socket, "_socket")
    socket.socket = guarded_py
    _socket.socket = guarded_c
    socket.create_connection = create_connection
    http.client.HTTPConnection.connect = http_connect
    _socket.getaddrinfo = getaddrinfo  # socket.getaddrinfo calls it by name
    for name in ("gethostbyname", "gethostbyname_ex"):  # bound into socket at import
        guarded = by_name(getattr(_socket, name), name)
        setattr(_socket, name, guarded)
        setattr(socket, name, guarded)
    _socket.gethostbyaddr = socket.gethostbyaddr = gethostbyaddr
    _socket.getnameinfo = socket.getnameinfo = getnameinfo
    ssl.SSLSocket._real_connect = ssl_connect
    # Every other name the original classes were bound to before this ran --
    # socket.SocketType, _socket.SocketType, ssl.socket, whatever a module
    # imported by name -- now names the guarded class.
    this = sys.modules[__name__]
    for module in list(sys.modules.values()):
        if module is this:
            continue
        for attr, value in list(getattr(module, "__dict__", {}).items()):
            if value is _original_socket:
                setattr(module, attr, guarded_py)
            elif value is original_c_socket:
                setattr(module, attr, guarded_c)
    _installed = True
    return True


def guard_installed() -> bool:
    return _installed


class tool_fetch:
    """Admit, on this thread and for this block, connections to the tool sources.

    ``with tool_fetch(url):`` checks the URL's host is one of ``TOOL_SOURCES``
    before anything is opened, then lets the sockets underneath the fetch
    reach those hosts (and only those; a redirect elsewhere is refused). The
    firmware installer is the only caller; a test holds it to that.
    """

    def __init__(self, url: str, sources: Iterable[str] = TOOL_SOURCES):
        host = (urlsplit(url).hostname or "").lower()
        self.sources = frozenset(s.lower() for s in sources)
        if host not in self.sources:
            raise LeftTheMachine(
                f"tool fetch: {host!r} is not a tool source ({', '.join(sorted(self.sources))})"
            )
        self.host = host
        self._before = None

    def __enter__(self):
        self._before = (getattr(_fetching, "hosts", None), getattr(_fetching, "addresses", None))
        _fetching.hosts = self.sources
        _fetching.addresses = set()
        return self

    def __exit__(self, *exc):
        _fetching.hosts, _fetching.addresses = self._before
        return False


# --- 2. the server listens here, and answers only from here ------------------------------


def require_loopback(host: str) -> str:
    """The host a server may bind: loopback, or an error that names the rule."""
    if is_loopback(host):
        return host
    raise ValueError(
        f"--host {host!r}: Apothecary listens on this machine only (127.0.0.1, localhost, "
        "::1). Personal data stays on the device by construction, not by choice; see "
        "the record 'Personal data stays on the device'. The named exception, secured "
        "user accounts, is not built."
    )


# What a page may load or reach: this origin. Images and media also blob: and
# data:, for a camera frame drawn on a canvas and a data URL in the docs.
# Inline scripts and styles are the templates' own. (A peer connection, which
# would reach a STUN server, is outside what browsers let a policy forbid; no
# page here creates one, and the test on the pages refuses the word.)
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "media-src 'self' blob:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "worker-src 'self' blob:; "
    "frame-src 'none'; "
    "frame-ancestors 'none'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)
RESPONSE_HEADERS = (
    (b"content-security-policy", CONTENT_SECURITY_POLICY.encode()),
    (b"referrer-policy", b"no-referrer"),
    (b"x-content-type-options", b"nosniff"),
)


def host_is_this_machine(host_header: object) -> bool:
    """Whether a request's ``Host`` names this machine: a loopback address or name,
    with or without a numeric port; anything else is a name pointed here from
    elsewhere."""
    if isinstance(host_header, bytes):
        host_header = host_header.decode("latin-1", "replace")
    if not isinstance(host_header, str):
        return False
    text = host_header.strip().lower()
    if text.startswith("["):  # [::1]:8000
        end = text.find("]")
        if end < 0:
            return False
        text, rest = text[1:end], text[end + 1 :]
    elif text.count(":") == 1:
        text, rest = text.rsplit(":", 1)
        rest = ":" + rest
    else:
        rest = ""
    if rest and not (rest.startswith(":") and rest[1:].isdigit()):
        return False
    return is_loopback(text.rstrip("."))


def _header(scope, name: bytes) -> Optional[str]:
    for key, value in scope.get("headers", ()):
        if key.lower() == name:
            return value.decode("latin-1", "replace")
    return None


def from_this_machine(scope) -> bool:
    """Whether an ASGI request is this machine's own: the client is on loopback, so
    is the address it arrived on (a server that names neither is not answered),
    the ``Host`` it asked for is one of ours, and it was not sent by a page from
    another origin (a browser says so in ``Origin`` and
    ``Sec-Fetch-Site``; a link from elsewhere that opens a page here is still let in,
    a fetch, a form or an image from elsewhere is not)."""
    client = scope.get("client")
    server = scope.get("server")
    if client is None or server is None:  # a peer the server cannot name is not ours
        return False
    if not is_loopback(client[0]) or not is_loopback(server[0]):
        return False
    host = _header(scope, b"host")
    if host is None or not host_is_this_machine(host):
        return False
    origin = _header(scope, b"origin")
    if origin is not None and not host_is_this_machine(urlsplit(origin).netloc):
        return False
    site = (_header(scope, b"sec-fetch-site") or "").lower()
    if site in ("cross-site", "same-site"):
        mode = (_header(scope, b"sec-fetch-mode") or "").lower()
        method = scope.get("method", "GET").upper()
        return mode == "navigate" and method in ("GET", "HEAD")
    return True


class LocalOnly:
    """ASGI middleware: refuse a request that is not this machine's own; fence every page.

    Pure ASGI so it wraps the whole app, static files included, and needs
    nothing beyond the standard. Four things must hold for a request to be
    answered, and each closes a different door: the client address (a peer on
    the network), the server address (a listener bound elsewhere, whatever
    a forwarded-for header claims), the ``Host`` (a page from elsewhere
    that resolved its own name to 127.0.0.1 and reads this server as itself),
    and the sender (a page from another origin posting to a route here, which
    the browser would let through without a preflight).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        if not from_this_machine(scope):
            body = (
                "Apothecary answers this machine only. Personal data stays on the device "
                "by construction; the named exception, secured user accounts, is not built."
            ).encode()
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            await send(
                {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [
                        (b"content-type", b"text/plain; charset=utf-8"),
                        (b"content-length", str(len(body)).encode()),
                        *RESPONSE_HEADERS,
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {k.lower() for k, _ in headers}
                for key, value in RESPONSE_HEADERS:
                    if key not in present:
                        headers.append((key, value))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


# --- 4. a subprocess that fetches is told where, and nothing else tells it ------------

# What a child process does not inherit. A proxy variable would send every
# fetch a tool makes through somewhere else; an ARDUINO_* variable is any
# arduino-cli setting, and arduino-cli lets it outrank the config file.
PROXY_VARIABLES = frozenset({"http_proxy", "https_proxy", "ftp_proxy", "all_proxy", "no_proxy"})
SCRUBBED_PREFIXES = ("ARDUINO_",)


def subprocess_env(base: Optional[Mapping[str, str]] = None) -> dict:
    """The environment a subprocess gets: this process's, minus what would redirect a fetch."""
    env = dict(os.environ if base is None else base)
    for key in list(env):
        if key.lower() in PROXY_VARIABLES or key.upper().startswith(SCRUBBED_PREFIXES):
            del env[key]
    return env


# The package indexes arduino-cli may fetch cores from, by vendor. Official
# arduino:* cores come from downloads.arduino.cc, which needs no entry.
PACKAGE_INDEXES = {
    "esp32": "https://espressif.github.io/arduino-esp32/package_esp32_index.json",
    "esp8266": "https://arduino.esp8266.com/stable/package_esp8266com_index.json",
    "rp2040": "https://github.com/earlephilhower/arduino-pico/releases/download/global/package_rp2040_index.json",
}

# The config every arduino-cli the seam starts is given (JSON is YAML; the
# file is named .yaml because that is what arduino-cli documents). The
# cloud board lookup and the update check are the two fetches arduino-cli
# makes on its own; both are off. Everything else it fetches is an index,
# a core or a library from the hosts named here and in the official index.
ARDUINO_CLI_CONFIG = {
    "board_manager": {"additional_urls": sorted(PACKAGE_INDEXES.values())},
    "network": {"cloud_api": {"skip_board_detection_calls": True}},
    "updater": {"enable_notification": False},
}
