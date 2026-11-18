"""What the world draws of the universe's orbitals (apothecary/static/orbits.js): each
shell's rings on its sphere, an outline round each category's cluster that holds its
pieces, a line from a part to each part it is built from, and which drawn loop a click
lands nearest. The module has no DOM, so node runs it here on the universe as the
server sends it."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apothecary import api

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "apothecary" / "static" / "orbits.js"
NODE = shutil.which("node") or str(Path.home() / ".local" / "bin" / "node")

pytestmark = pytest.mark.skipif(not Path(NODE).exists(), reason="node is not installed")

SCRIPT = """
import { shellsOf, ringsOf, clustersOf, capOutline, linksOf, nearestLoop, middleOf, shellLabel, clusterLabel, limbOf, facesEye, pieceNear } from "%(module)s";
import { readFileSync } from "node:fs";
const tree = JSON.parse(readFileSync(process.argv[2], "utf8"));
const nodes = tree.children.map((n) => ({ key: n.name, ...n }));
const out = {};
out.shells = shellsOf(nodes);
out.rings = out.shells.map((s) => ringsOf(s.radius).map((r) => r.map((p) => Math.hypot(...p))));
out.ringNormals = out.shells.map((s) => ringsOf(s.radius).map((r) => {
    const [a, b] = [r[0], r[Math.floor(r.length / 4)]];
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}));
out.clusters = clustersOf(nodes);
out.outlines = out.clusters.map((c) => capOutline(c).map((p) => [Math.hypot(...p),
    Math.acos(Math.max(-1, Math.min(1, (p[0] * c.centre[0] + p[1] * c.centre[1] + p[2] * c.centre[2]) / Math.hypot(...p))))]));
out.middles = Object.fromEntries(nodes.map((n) => [n.key, middleOf(n)]));
out.links = linksOf(nodes);
const square = [{ sx: 0, sy: 0 }, { sx: 100, sy: 0 }, { sx: 100, sy: 100 }, { sx: 0, sy: 100 }];
const far = square.map((p) => ({ sx: p.sx + 300, sy: p.sy }));
const behind = far.map((p) => ({ ...p, off: true }));
out.near = [nearestLoop([square, far], 50, 3, 6), nearestLoop([square, far], 302, 50, 6),
    nearestLoop([square, far], 200, 50, 6), nearestLoop([square, behind], 302, 50, 6),
    nearestLoop([square, far], 50, 50, 6)];
out.labels = out.shells.map((s) => shellLabel(s.shell, nodes));
out.clusterLabels = out.clusters.map((c) => ({ shell: c.shell, category: c.category, label: clusterLabel(c, out.clusters) }));
// A sphere of radius 3 seen from 5 away along x, and from inside it.
out.limbs = [limbOf(3, [5, 0, 0]), limbOf(3, [0, 0, 2]), limbOf(3, [0, 3, 0])];
out.faces = [facesEye([10, 0, 0], [1, 0, 0]), facesEye([10, 0, 0], [-1, 0, 0]), facesEye([10, 0, 0], [0.05, 1, 0]),
    facesEye([0.5, 0, 0], [-1, 0, 0]), facesEye([10, 0, 0], [0.1, 0.99, 0]), facesEye([10, 0, 0], [0.09, 0.99, 0])];
const seen = [{ key: "a", sx: 100, sy: 100, depth: 5 }, { key: "b", sx: 102, sy: 100, depth: 9 },
    { key: "c", sx: 300, sy: 300, depth: 1, off: true }, { key: "d", sx: 98, sy: 101, depth: 2 }];
out.pieces = [pieceNear(seen, 101, 100, 10), pieceNear(seen, 300, 300, 10), pieceNear(seen, 200, 200, 10),
    pieceNear([{ key: "p", sx: 0, sy: 0, depth: 9 }, { key: "q", sx: 3, sy: 0, depth: 1 }], 1, 0, 10)];
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def drawn(tmp_path_factory):
    folder = tmp_path_factory.mktemp("orbits")
    tree = TestClient(api.app).get("/sites/apothecary").json()["tree"]
    (folder / "tree.json").write_text(json.dumps(tree), encoding="utf-8")
    script = folder / "run.mjs"
    script.write_text(SCRIPT % {"module": MODULE.as_uri()}, encoding="utf-8")
    done = subprocess.run(
        [NODE, str(script), str(folder / "tree.json")],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return {"tree": tree, **json.loads(done.stdout)}


def _angle(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True)) / (math.hypot(*a) * math.hypot(*b))
    return math.acos(max(-1.0, min(1.0, dot)))


def test_each_shell_is_drawn_at_its_radius_innermost_first(drawn):
    shells = drawn["shells"]
    leaves = {c["shell"] for c in drawn["tree"]["children"]}
    assert [s["shell"] for s in shells] == sorted(leaves)
    radii = [s["radius"] for s in shells]
    assert radii == sorted(radii) and len(set(radii)) == len(radii)
    for child in drawn["tree"]["children"]:
        at = math.hypot(*drawn["middles"][child["name"]])
        assert at == pytest.approx(radii[child["shell"]], rel=1e-9), child["name"]


def test_a_shells_rings_are_three_great_circles_on_its_sphere_nested_in_the_next(drawn):
    """Each shell's three rings lie on its sphere, in the same three planes as every other
    shell's, so the rings of the shells nest; no two of a shell's rings share a plane."""
    for shell, rings in zip(drawn["shells"], drawn["rings"], strict=True):
        assert len(rings) == 3
        for ring in rings:
            assert len(ring) >= 64
            assert all(r == pytest.approx(shell["radius"], rel=1e-9) for r in ring)
    for normals in drawn["ringNormals"]:
        for a, b in zip(normals, drawn["ringNormals"][0], strict=True):
            assert _angle(a, b) == pytest.approx(0, abs=1e-6)
        for a, b in [(normals[i], normals[j]) for i in range(3) for j in range(i + 1, 3)]:
            assert min(_angle(a, b), _angle(a, [-c for c in b])) > 0.5


def test_a_clusters_outline_is_on_its_shell_and_holds_every_one_of_its_pieces(drawn):
    clusters = drawn["clusters"]
    tree = drawn["tree"]["children"]
    pairs = {(c["shell"], c["category"]) for c in tree if c["category"]}
    assert {(c["shell"], c["category"]) for c in clusters} == pairs
    by_key = {c["name"]: c for c in tree}
    for cluster, outline in zip(clusters, drawn["outlines"], strict=True):
        assert all(r == pytest.approx(cluster["radius"], rel=1e-9) for r, _ in outline)
        assert all(a == pytest.approx(cluster["angle"], abs=1e-9) for _, a in outline)
        for key in cluster["members"]:
            node = by_key[key]
            assert node["shell"] == cluster["shell"] and node["category"] == cluster["category"]
            low, high = node["footprint"]["min"], node["footprint"]["max"]
            reach = math.hypot(*(h - lo for h, lo in zip(high, low, strict=True))) / 2
            inside = _angle(drawn["middles"][key], cluster["centre"]) + math.asin(
                min(1, reach / cluster["radius"])
            )
            assert inside < cluster["angle"], (key, inside, cluster["angle"])
    # The two machines, the electrical boards under them: clusters of more than one.
    sizes = {(c["shell"], c["category"]): len(c["members"]) for c in clusters}
    assert sizes[(1, "machine")] == 2 and sizes[(0, "electrical")] >= 4


def test_a_part_is_joined_to_each_part_it_is_built_from(drawn):
    links = {(link["from"], link["to"]) for link in drawn["links"]}
    built = {
        (c["name"], child) for c in drawn["tree"]["children"] for child in c["built_from"] or ()
    }
    assert links == built
    assert ("ender3", "creality_v422") in links
    assert {("webcam_ceiling_mount", "webcam"), ("webcam_desk_stand", "webcam")} <= links


def test_a_click_picks_the_drawn_loop_it_lands_nearest_within_its_reach(drawn):
    """On the first loop's edge, on the second's, between them, on a loop behind the
    eye, and inside a loop away from its edge."""
    assert drawn["near"] == [0, 1, -1, -1, -1]


def test_outlines_on_one_shell_overlap_only_where_large_parts_make_them(drawn):
    """An outline is as wide as its largest part's sphere needs, so caps of large
    clusters cross: measured on the registry as it is (about one pair in twelve on the
    first shell), and the guard is that the layout keeps most pairs apart."""
    caps = drawn["clusters"]
    pairs = overlapping = 0
    for i, a in enumerate(caps):
        for b in caps[i + 1 :]:
            if a["shell"] != b["shell"]:
                continue
            pairs += 1
            between = math.acos(max(-1, min(1, sum(x * y for x, y in zip(a["centre"], b["centre"], strict=True)))))
            overlapping += between < a["angle"] + b["angle"]
    assert pairs > 20
    assert overlapping <= pairs // 4


def test_a_shell_says_what_it_is_in_the_docs_words(drawn):
    words = [label.split(" \u00b7 ")[1] for label in drawn["labels"]]
    assert words[0] == "built from nothing"
    assert words[-1] == "sites"
    assert all(w == "built from those inside" for w in words[1:-1])
    assert [label.split(" ")[1] for label in drawn["labels"]] == [
        str(s["shell"]) for s in drawn["shells"]
    ]


def test_a_label_is_hung_only_from_the_side_of_the_sphere_the_eye_sees(drawn):
    near, far, edge, inside, limb, beyond = drawn["faces"]
    # In front: seen. Behind: not. Past the horizon (the unit sphere seen from 10 away
    # shows points whose x exceeds 0.1): a point at x = 0.05 or 0.09 is hidden, 0.1 just seen.
    assert near is True and far is False and edge is False
    assert inside is True
    assert limb is True and beyond is False


def test_the_piece_under_the_pointer_is_named_at_any_distance(drawn):
    # Of a, b and d near (101, 100): d is nearest-ish? a and b are 1 and 1 away; d is
    # about 3 away. The nearest is a (first of the tie), and the one nearer the eye among
    # those about as near, d, takes it; one behind the eye is never named; none within reach.
    named, behind, nothing, eye = drawn["pieces"]
    assert named == "d"
    assert behind is None and nothing is None
    assert eye == "q"


def test_a_category_on_more_than_one_shell_names_its_shell_in_each_clusters_label(drawn):
    """The camera's parts stand on two shells, so its two outlines are labelled by shell;
    a category on one shell is labelled by its name alone."""
    shells_of: dict = {}
    for c in drawn["clusterLabels"]:
        shells_of.setdefault(c["category"], set()).add(c["shell"])
    assert len(shells_of["camera"]) > 1
    for c in drawn["clusterLabels"]:
        if len(shells_of[c["category"]]) > 1:
            assert c["label"] == f"{c['category']} \u00b7 shell {c['shell']}"
        else:
            assert c["label"] == c["category"]
    labels = [c["label"] for c in drawn["clusterLabels"]]
    assert len(labels) == len(set(labels)), "two outlines wear one label"


def test_a_shells_edge_is_the_circle_the_eye_sees_its_sphere_end_at(drawn):
    """From 5 away, a sphere of 3 ends where the lines from the eye touch it: a circle of
    radius 3 * 4 / 5 about a point 9/5 from its middle toward the eye. From inside, or on
    it, no edge is seen."""
    seen, inside, on = drawn["limbs"]
    assert seen["centre"] == pytest.approx([1.8, 0, 0])
    assert seen["radius"] == pytest.approx(2.4)
    assert seen["normal"] == pytest.approx([1, 0, 0])
    assert inside is None and on is None
