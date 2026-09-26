"""The browser suite must not be switched off by one fixture.

This exists because it already went wrong once. The fixture naming the picture
folder skips when nobody has said which folder to use. Starting the server was
made to depend on it, and starting the server is what every browser test depends
on — so a single skip quietly took the whole browser suite with it, and the run
still reported success. Nothing failed. Twenty-six tests simply stopped
happening.

A count of passing tests cannot catch that: the number it would have to notice
is a number of tests that were never there. So this checks the shape instead —
nothing the server is built on may be a thing that skips.

It reads the setup file rather than running it, so it needs no browser, no
server, and none of the things that file imports.
"""

import ast
from pathlib import Path

E2E_SETUP = Path(__file__).resolve().parent / "e2e" / "conftest.py"

# What every browser test reaches the server through. If one of these can be
# skipped, all of them are.
LOAD_BEARING = ("test_server", "base_url")

# Fixtures that decide, on their own, that the test asking for them cannot run.
CAN_SKIP = ("picture_folder",)


def _fixtures() -> dict[str, ast.FunctionDef]:
    tree = ast.parse(E2E_SETUP.read_text(encoding="utf-8"), filename=str(E2E_SETUP))
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _asked_for(fixture: ast.FunctionDef) -> tuple[str, ...]:
    args = fixture.args
    named = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    return tuple(a.arg for a in named)


def test_nothing_load_bearing_asks_for_a_fixture_that_can_skip():
    fixtures = _fixtures()
    for name in LOAD_BEARING:
        assert name in fixtures, f"{name!r} has gone from {E2E_SETUP.name}; this check is stale."
        asked = _asked_for(fixtures[name])
        for skipper in CAN_SKIP:
            assert skipper not in asked, (
                f"{name!r} asks for {skipper!r}, which skips when nobody has said "
                f"which picture folder to use. Every browser test reaches the "
                f"server through {name!r}, so that skip takes the whole browser "
                f"suite with it and the run still looks green. Ask for the "
                f"version that returns nothing instead, and let only the tests "
                f"that really do show the server a picture skip."
            )


def test_the_fixture_that_can_skip_still_can():
    """The check above is only worth anything while the skip is real."""
    fixtures = _fixtures()
    assert "picture_folder" in fixtures
    body = ast.dump(fixtures["picture_folder"])
    assert "skip" in body, (
        "The picture folder fixture no longer skips. Either that is deliberate "
        "and this whole file can go, or the refusal it was guarding has been lost."
    )
