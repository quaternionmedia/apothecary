"""CI's picture check (tests/e2e/picture_drift.py) names a walkthrough picture that
changed past its tolerance, and never fails."""

import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent / "e2e"))

import picture_drift  # noqa: E402


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _picture(path: Path, dots: int = 0) -> None:
    """A grey picture of 100 by 100 pixels, ``dots`` of them black."""
    image = Image.new("RGB", (100, 100), (60, 60, 60))
    pen = ImageDraw.Draw(image)
    for i in range(dots):
        pen.point((i % 100, i // 100), fill=(0, 0, 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


@pytest.fixture
def checkout(tmp_path):
    """A repository whose walkthrough has two committed pictures."""
    _git(tmp_path, "init", "-q")
    for key, value in (
        ("user.name", "t"),
        ("user.email", "t@t.invalid"),
        ("commit.gpgsign", "false"),
    ):
        _git(tmp_path, "config", key, value)
    shots = tmp_path / picture_drift.PICTURES
    _picture(shots / "03-01-a.png")
    _picture(shots / "03-02-b.png")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "pictures")
    return tmp_path


def test_a_picture_within_the_tolerance_is_not_named(checkout):
    shots = checkout / picture_drift.PICTURES
    _picture(shots / "03-01-a.png", dots=8)  # eight hundredths of a percent
    assert picture_drift.warnings(checkout) == []


def test_a_picture_past_the_tolerance_and_a_new_one_are_named(checkout):
    shots = checkout / picture_drift.PICTURES
    _picture(shots / "03-02-b.png", dots=300)  # three percent
    _picture(shots / "03-03-c.png")
    said = picture_drift.warnings(checkout)
    assert said == [
        "::warning file=walkthrough/screenshots/03-02-b.png,title=A walkthrough picture "
        "changed::walkthrough/screenshots/03-02-b.png differs from the committed picture in "
        "3.00% of its pixels, past 0.1%: look at it against its caption, and commit it if "
        "the page changed",
        "::warning file=walkthrough/screenshots/03-03-c.png,title=A new walkthrough "
        "picture::walkthrough/screenshots/03-03-c.png is not committed: look at it against "
        "its caption, and commit it with its page",
    ]


def test_a_picture_of_another_size_differs_whole(checkout):
    shots = checkout / picture_drift.PICTURES
    Image.new("RGB", (100, 90), (60, 60, 60)).save(shots / "03-01-a.png")
    (said,) = picture_drift.warnings(checkout)
    assert "in 100.00% of its pixels" in said


def test_it_never_fails(checkout, capsys):
    _picture(checkout / picture_drift.PICTURES / "03-01-a.png", dots=5000)
    assert picture_drift.main(checkout) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("::warning file=walkthrough/screenshots/03-01-a.png")
    assert out[-1] == (
        "1 walkthrough picture(s) differ from the committed ones past 0.1% of their pixels"
    )
