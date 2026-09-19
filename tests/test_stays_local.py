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
