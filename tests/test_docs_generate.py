"""`apothecary docs generate` assembles a page per doc workflow from what its browser
test recorded (tests/e2e/doc_capture.py): its steps, a GIF of them, and when and from
which commit it was made."""

import json
import subprocess

from PIL import Image

from apothecary.cli import docs


def _recorded(folder):
    shots = folder / "screenshots"
    shots.mkdir(parents=True)
    for n in (1, 2):
        Image.new("RGB", (8, 8), (n * 60, 0, 0)).save(shots / f"0{n}-step.png")
    manifest = {
        "workflow": "sample",
        "title": "A sample",
        "intro": "What it shows.",
        "steps": [
            {"index": n, "description": f"Step {n}", "screenshot": f"0{n}-step.png"} for n in (1, 2)
        ],
    }
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_a_page_says_when_and_from_which_commit_it_was_made(tmp_path):
    _recorded(tmp_path / "sample")
    docs._render_workflow(tmp_path / "sample")
    page = (tmp_path / "sample" / "sample.md").read_text(encoding="utf-8")
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert page.startswith("# A sample\n\n*Made by `apothecary docs generate` on ")
    assert f"from commit `{sha}`" in page
    assert "Step 2" in page and (tmp_path / "sample" / "sample.gif").is_file()


def test_outside_a_checkout_a_page_says_when_alone(tmp_path):
    said = docs.made_from(tmp_path)
    assert said.startswith("*Made by `apothecary docs generate` on ") and "commit" not in said
