"""What the walkthrough's pictures blank, and what a page records of the STLs they draw:
the helpers of tests/e2e/doc_capture.py and tests/e2e/parts_built.py, without a browser."""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "e2e"))

from doc_capture import MOMENT, TEMPERATURE, _blanked, moments  # noqa: E402
from parts_built import described  # noqa: E402


@pytest.mark.parametrize(
    ("words", "blanked"),
    [
        ("20261011T231147.943-garage--camera_1.png · 3 shapes", ["20261011T231147.943"]),
        ("10/11/2026, 7:42:13 PM – 7:42:20 PM · print", ["10/11/2026, 7:42:13 PM", "7:42:20 PM"]),
        ("disc_1.gcode · done · 163/163 lines (100.0%) · 0m 12s", ["0m 12s"]),
        ("19:42:13.123 ok", ["19:42:13.123"]),
        ("printer_1 · print · disc_1.gcode → disc_1 · done", []),
    ],
)
def test_a_moment_is_blanked_and_the_words_around_it_are_not(words, blanked):
    assert re.findall(MOMENT, words) == blanked


def test_a_temperature_to_its_tenth_is_blanked_and_its_target_is_not():
    assert re.findall(TEMPERATURE, "T 210.2/210° · B 60.3 / 60°") == ["210.2", "60.3"]
    assert re.findall(TEMPERATURE, "210°/60° · 41%") == []


def test_a_blanked_word_is_one_width_and_a_whole_blank_its_own_size():
    style = _blanked(("#chart", *moments("#site-jobs-list")))
    assert "[data-blanked] { display: inline-block; width: 5.5em;" in style
    assert "#chart { background:" in style and "#chart * { visibility: hidden" in style
    assert "#site-jobs-list" not in style  # its words are wrapped, not the list blanked


def test_a_page_records_the_openscad_and_nothing_that_differs_between_clones():
    found = {
        "openscad": "OpenSCAD version 2021.01",
        "path": "/usr/bin/openscad",
        "elsewhere": ["gridfinity (an STL built before this run)"],
        "boxes": [],
    }
    said = described(found)
    assert "OpenSCAD version 2021.01, the OpenSCAD its server runs" in said
    assert described({**found, "elsewhere": [], "boxes": ["gridfinity"]}) == said
    assert "no OpenSCAD" in described({"openscad": None})
