"""The page's words for a machine's kind (apothecary/static/machine_words.js), held to
what the server says of the same things, so the two copies cannot drift apart: the
job and dialect of each kind, its stop, its feed's bound, the files its job takes,
and the status words a person may set.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from apothecary import jobs
from apothecary.example_hierarchy import PRINTER_STATUSES, ROUTER_STATUSES
from apothecary.firmware import dialects, gcode, grbl
from apothecary.systems import MACHINE

ROOT = Path(__file__).resolve().parents[1]
WORDS = ROOT / "apothecary" / "static" / "machine_words.js"


def _kind(name: str) -> str:
    """One kind's entry in the module, as text."""
    found = re.search(
        rf"^    {name}: \{{\n(.*?)^    \}},$", WORDS.read_text(encoding="utf-8"), re.S | re.M
    )
    assert found, f"{name} is not in {WORDS.name}"
    return found.group(1)


def _word(entry: str, key: str) -> str:
    found = re.search(rf'\b{key}: "([^"]*)"', entry)
    assert found, key
    return found.group(1)


def _number(entry: str, key: str) -> int:
    found = re.search(rf"\b{key}: (\d+)", entry)
    assert found, key
    return int(found.group(1))


def _list(entry: str, key: str) -> list:
    found = re.search(rf"\b{key}: \[([^\]]*)\]", entry)
    assert found, key
    return re.findall(r'"([^"]+)"', found.group(1))


@pytest.mark.parametrize(
    ("kind", "dialect", "operation", "feed_max"),
    [
        ("printer", dialects.MARLIN, jobs.PRINT, gcode.FEED_MAX),
        ("router", dialects.GRBL, jobs.CUT, grbl.FEED_MAX),
    ],
)
def test_a_kind_says_what_the_server_says_of_its_machine(kind, dialect, operation, feed_max):
    entry = _kind(kind)
    assert _word(entry, "dialect") == dialect.word
    assert _word(entry, "stop") == dialect.stop
    assert kind == dialect.machine == operation.machine
    assert _word(entry, "job") == operation.kind
    assert _word(entry, "verb") == operation.label
    assert _word(entry, "running") == operation.busy
    assert _number(entry, "feedMax") == feed_max
    assert _number(entry, "feedDefault") <= feed_max
    assert set(operation.inputs) <= set(_word(entry, "files").split(","))


def test_the_status_words_a_person_sets_are_the_machines_own():
    assert _list(_kind("printer"), "byHand") == list(PRINTER_STATUSES)
    by_hand = _list(_kind("router"), "byHand")
    assert set(by_hand) <= set(ROUTER_STATUSES)
    # What the router's polls set is shown, and never offered by hand.
    assert not {"running", "hold", "alarm"} & set(by_hand)


def test_a_window_titled_by_kind_is_called_what_the_kind_calls_it():
    section = next(s for s in MACHINE.sections if s.id == "print")
    assert section.title == _word(_kind("printer"), "verb")
    assert section.titles["router"] == _word(_kind("router"), "verb")
