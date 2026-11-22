"""One colour for each layer the world draws (apothecary/layer_colours.py): a table the
server and the page share, the shells' and the world's own held apart from the others and
the facets' read from apothecary/facets.py, a word nobody wrote down given the colour the
page always gave it, and a site sent with its own."""

from __future__ import annotations

import colorsys
import itertools
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apothecary import api, layer_colours, sites
from apothecary.facets import KIND, KINDS, SYSTEM, SYSTEMS, category_shade
from apothecary.facets import colour as facet_colour
from apothecary.layer_colours import (
    SHELLS,
    WORLD,
    category_colour,
    colour_of,
    shells_in,
)
from apothecary.layer_colours import (
    layer_colours as colours_for,
)
from apothecary.projects.parts.skeleton import ROOT

TEMPLATE = (ROOT / "templates" / "fractal_viewer.html.j2").read_text(encoding="utf-8")
TOKENS = (ROOT / "apothecary" / "static" / "tokens.css").read_text(encoding="utf-8")

client = TestClient(api.app)


def _lab(colour: str):
    """CIE L*a*b* (D65) of a #rrggbb colour."""
    rgb = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    return (116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z)))


def _apart(a: str, b: str) -> float:
    """How far apart two colours look: the distance between them in L*a*b* (ΔE*76)."""
    return math.dist(_lab(a), _lab(b))


def _groups() -> dict:
    return dict(re.findall(r"(--group-[a-z]+): (#[0-9a-f]{6})", TOKENS))


def _states() -> list:
    found = dict(re.findall(r"(--[a-z0-9-]+): (#[0-9a-f]{6})", TOKENS))
    return [found[name] for name in ("--ok", "--warn", "--bad")]


def _facets() -> list:
    """Every colour of a facet: each kind's, each of its categories' and each System's."""
    return [
        *(facet_colour(KIND, name) for name in KINDS),
        *(category_shade(word) for words in KINDS.values() for word in words),
        *(facet_colour(SYSTEM, name) for name in SYSTEMS),
    ]


# --- the table --------------------------------------------------------------------------


def test_every_colour_written_down_is_one_the_page_can_draw():
    for colour in [*WORLD.values(), *SHELLS, *_facets()]:
        assert re.fullmatch(r"#[0-9a-f]{6}", colour), colour


def test_a_layer_is_named_as_the_pick_scope_names_it():
    assert colour_of("grid") == WORLD["grid"]
    assert colour_of("measure") == WORLD["measure"]
    assert colour_of("bed-mesh") == WORLD["bed-mesh"]
    assert colour_of("shell:0") == SHELLS[0]
    assert colour_of(f"shell:{len(SHELLS) + 1}") == SHELLS[1]
    # A System's, a Kind's and a category's are the facets' (apothecary/facets.py).
    assert colour_of("system:building") == facet_colour(SYSTEM, "Building") == "#9c8f7a"
    assert colour_of("kind:test-pieces") == facet_colour(KIND, "Test pieces")
    assert colour_of("category:coupon") == category_shade("coupon")
    # The System's furniture and the part's are two layers in two colours.
    assert colour_of("system:furniture") != colour_of("category:furniture")
    for nowhere in ("floor", "system:nowhere", "kind:wall"):
        with pytest.raises(KeyError):
            colour_of(nowhere)


def test_the_machines_buttons_wear_the_machine_groups_colour_as_tokens_say_it():
    """The badges the layer draws wear their group's colour: the one place a layer and a
    group share one, read from tokens.css rather than written twice."""
    assert WORLD["machine-buttons"] == _groups()["--group-machine"]


def test_the_shells_and_the_worlds_own_stand_apart_from_each_other_and_from_what_they_meet():
    """A shell's rings, the build volumes, the measurement and a bed reading's posts are
    drawn beside the facets' clusters and pieces, the badges of each group and the colours
    that mean a state: each is at least 20 apart (ΔE*76) from all of those and from each
    other. The facets' are held apart from each other in tests/test_facets.py."""
    own = [*SHELLS, WORLD["grid"], WORLD["measure"], WORLD["bed-mesh"]]
    for a, b in itertools.combinations(own, 2):
        assert _apart(a, b) >= 20, (a, b)
    met = [*_facets(), *_groups().values(), *_states()]
    for colour in own:
        for other in met:
            assert _apart(colour, other) >= 20, (colour, other)


def _hue(colour: str) -> float:
    """A colour's hue, degrees round the wheel."""
    rgb = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    return colorsys.rgb_to_hsv(*rgb)[0] * 360


def test_the_measurement_is_drawn_in_no_shells_hue():
    """The measurement is drawn over the universe's rings: its magenta is no shell's, each
    shell's hue at least 30 degrees round the wheel from it, where shell 2's pink stood 24
    off and read as the same colour beside it."""
    for shell in SHELLS:
        apart = abs(_hue(shell) - _hue(WORLD["measure"])) % 360
        if shell != "#f2f2f2":  # the white shell has no hue to share
            assert min(apart, 360 - apart) >= 30, shell


# The colours the page gave words nobody wrote down, before the rule moved here: its
# own function, run under node on these words.
PAGE_GAVE = {
    "disc": "#8b5cbc",
    "bracket": "#bc5c83",
    "plate": "#bcb35c",
    "box": "#5cbcbb",
    "café": "#bc5c9b",
    "日本": "#5c91bc",
    "a": "#81bc5c",
    "": "#bc5c5c",
    "x" * 40: "#bc5c9c",
    "🙂lamp": "#94bc5c",
}


@pytest.mark.parametrize("word", sorted(PAGE_GAVE))
def test_a_word_nobody_wrote_down_has_the_colour_the_page_always_gave_it(word):
    assert category_colour(word) == PAGE_GAVE[word]


# --- a site's own ------------------------------------------------------------------------


def test_the_garage_has_its_systems_its_loose_parts_kinds_and_the_worlds_layers_and_no_shell():
    garage = sites.store.get("garage")
    assert shells_in(garage) == []
    colours = colours_for(garage, api.part_category)
    # Its Systems, then each kind of its loose parts, a heading, and its categories, as
    # the facets list them; the world's own last.
    assert list(colours) == [
        "system:building",
        "system:furniture",
        "system:machines",
        "system:mechanical",
        "system:electrical",
        "system:plumbing",
        "kind:electronics",
        "category:electrical",
        "category:electronics",
        "kind:test-pieces",
        "category:calibration",
        "category:coupon",
        "kind:things",
        "category:furniture",
        "grid",
        "machine-buttons",
        "measure",
        "bed-mesh",
    ]
    assert colours["system:building"] == "#9c8f7a"
    # A machine's System wears the Machines token's colour (apothecary/facets.py).
    machines = re.search(r"--kind-machines: (#[0-9a-f]{6})", TOKENS).group(1)
    assert colours["system:machines"] == machines


def test_the_universe_has_its_shells_its_parts_kinds_and_categories_and_its_miniatures():
    universe = sites.store.get("apothecary")
    shells = shells_in(universe)
    assert shells == sorted({c.shell for c in universe.children})
    colours = colours_for(universe, api.part_category)
    assert colours["shell:0"] == SHELLS[0]
    assert {"kind:machines", "category:machine", "category:electrical", "category:camera"} <= set(
        colours
    )
    # A site's piece is one node: the theatre's walls are drawn in it, not layers of it,
    # yet its boxes wear their Systems' colours.
    assert colours["system:building"] == facet_colour(SYSTEM, "Building")
    assert colours["system:lighting"] == facet_colour(SYSTEM, "Lighting")
    assert not any(layer.startswith("category:wall") for layer in colours)


def test_a_site_is_sent_with_its_colours():
    for name in ("garage", "apothecary"):
        body = client.get(f"/sites/{name}").json()
        assert body["layer_colours"] == colours_for(sites.store.get(name), api.part_category), name


def test_the_page_holds_no_palette_of_its_own():
    """The facets' colours, the build volumes', the measurement's and the bed mesh's are
    the table's, read from the site the page is sent: none is written in the page, nor in
    the marks a machine wears in it."""
    assert "CATEGORY_COLORS" not in TEMPLATE
    marks = (ROOT / "apothecary" / "static" / "machine_marks.js").read_text(encoding="utf-8")
    for colour in [*_facets(), WORLD["grid"], WORLD["measure"], WORLD["bed-mesh"], "#ffb347"]:
        for text in (TEMPLATE, marks):
            assert f"0x{colour[1:]}" not in text, colour
            assert colour not in text, colour
    assert layer_colours.TOKENS.name == "tokens.css"


# --- the page's reading of them ------------------------------------------------------------

MODULE = ROOT / "apothecary" / "static" / "layer_colours.js"
NODE = shutil.which("node") or str(Path.home() / ".local" / "bin" / "node")

READ = """
import { takeLayerColours, layerHex, layerColour } from "%(module)s";
const payload = JSON.parse(process.argv[2]);
const out = { before: layerColour("grid", -1), took: takeLayerColours(payload) };
out.grid = layerHex("grid");
out.wall = layerColour("system:building", -1);
out.missing = layerColour("category:nobody", -1);
out.ignored = takeLayerColours({ tree: {} });
out.kept = layerHex("grid");
takeLayerColours({ layer_colours: { grid: "red; x", "shell:0": "#3d7eff" } });
out.refused = [layerHex("grid"), layerHex("shell:0")];
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(not Path(NODE).exists(), reason="node is not installed")
def test_the_page_reads_the_colours_its_site_is_sent_with(tmp_path):
    """static/layer_colours.js takes a payload's colours in place of the last and reads
    them by layer; a payload with none leaves them, and a value that is no colour is not
    taken."""
    body = client.get("/sites/garage").json()
    script = tmp_path / "read.mjs"
    script.write_text(READ % {"module": MODULE.as_posix()}, encoding="utf-8")
    run = subprocess.run(
        [NODE, str(script), json.dumps(body)], capture_output=True, text=True, timeout=60
    )
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    assert out["before"] == -1 and out["took"] is True
    assert out["grid"] == WORLD["grid"]
    assert out["wall"] == int(facet_colour(SYSTEM, "Building")[1:], 16)
    assert out["missing"] == -1
    assert out["ignored"] is False and out["kept"] == WORLD["grid"]
    assert out["refused"] == [None, "#3d7eff"]
