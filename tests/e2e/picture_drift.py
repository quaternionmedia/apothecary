"""After the browser tests: each walkthrough picture the run rewrote, against the committed one.

    uv run python tests/e2e/picture_drift.py                 # name them
    uv run python tests/e2e/picture_drift.py --sheets DIR    # and draw each beside its commit

A picture that differs from the committed one in more than ``TOLERANCE`` of its
pixels is named in a GitHub warning annotation (``::warning file=...::``) with the
box its changed pixels lie in, which CI shows on the run and a terminal shows as a
line. It never fails: a picture is looked at against its caption by a person, and a
page changed on purpose is committed with its pictures. With ``--sheets DIR``, each
named picture is drawn into DIR beside the committed one, its changed pixels marked,
so the look is at what changed. A run rewrites a picture only past a hundredth of a
percent (doc_capture.py's ``_keep_unless_changed``), so what this reads is only
what the run wrote.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[2]
PICTURES = "walkthrough/screenshots"

# Of a picture's pixels: a tenth of a percent, a thousand pixels of a page. Two runs
# of the walkthrough on one machine differ by a few dozen pixels in a picture at
# most; a word of the hint bar or the status line is thousands. Past this, the
# picture shows something the committed one does not, or another machine drew it.
TOLERANCE = 0.001


# The pictures a test writes that move by themselves, each with the test that writes it
# and why: a list of {"picture", "test", "reason"}, empty while every picture is still.
# A picture on it that changes is reported apart (a notice), so a page's change is not
# looked for among them; tests/test_picture_drift.py fails on an entry naming a picture
# or a test that is not there.
MOVES_BY_ITSELF = "tests/e2e/moves_by_itself.json"


def moves_by_itself(root: Path = ROOT) -> dict[str, dict]:
    """The listed pictures, by their path under root."""
    path = root / MOVES_BY_ITSELF
    listed = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    return {f"{PICTURES}/{entry['picture']}": entry for entry in listed}


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True)


def rewritten(root: Path = ROOT) -> list[str]:
    """The pictures the run wrote that differ from the commit, and the new ones."""
    changed = _git(root, "diff", "--name-only", "HEAD", "--", PICTURES).stdout.decode()
    new = _git(root, "ls-files", "--others", "--exclude-standard", "--", PICTURES).stdout.decode()
    return sorted({line for line in (changed + new).splitlines() if line.endswith(".png")})


def differing(old: bytes, new: bytes) -> float:
    """The share of the pictures' pixels that differ; all of them when the sizes do."""
    before = Image.open(io.BytesIO(old)).convert("RGB")
    after = Image.open(io.BytesIO(new)).convert("RGB")
    if before.size != after.size:
        return 1.0
    changed = sum(ImageChops.difference(before, after).convert("L").histogram()[1:])
    return changed / (before.size[0] * before.size[1])


def _pair(old: bytes, new: bytes) -> tuple[Image.Image, Image.Image]:
    return Image.open(io.BytesIO(old)).convert("RGB"), Image.open(io.BytesIO(new)).convert("RGB")


def changed_box(old: bytes, new: bytes) -> tuple[int, int, int, int] | None:
    """The box the changed pixels lie in, (left, top, right, bottom); None for none."""
    before, after = _pair(old, new)
    if before.size != after.size:
        return (0, 0, *after.size)
    return ImageChops.difference(before, after).convert("L").getbbox()


# The changed pixels, marked over the new picture.
MARK = (255, 0, 0)


def sheet(old: bytes, new: bytes) -> Image.Image:
    """The committed picture beside the new one, the new one's changed pixels marked."""
    before, after = _pair(old, new)
    if before.size == after.size:
        changed = ImageChops.difference(before, after).convert("L").point(lambda v: 255 * (v > 0))
        after = Image.composite(Image.new("RGB", after.size, MARK), after, changed)
    drawn = Image.new(
        "RGB", (before.width + after.width, max(before.height, after.height)), "white"
    )
    drawn.paste(before, (0, 0))
    drawn.paste(after, (before.width, 0))
    return drawn


def warnings(
    root: Path = ROOT, tolerance: float = TOLERANCE, sheets: Path | None = None
) -> list[str]:
    """One annotation per picture past ``tolerance``, naming it and the box that
    changed; with ``sheets``, each drawn there beside the committed one."""
    said = []
    moving = moves_by_itself(root)
    for name in rewritten(root):
        path = root / name
        if not path.exists():
            continue  # a picture the run did not write again is not this check's
        committed = _git(root, "show", f"HEAD:{name}")
        if committed.returncode != 0:
            said.append(
                f"::warning file={name},title=A new walkthrough picture::{name} is not "
                "committed: look at it against its caption, and commit it with its page"
            )
            continue
        now = path.read_bytes()
        share = differing(committed.stdout, now)
        if share > tolerance:
            left, top, right, bottom = changed_box(committed.stdout, now)
            if name in moving:
                said.append(
                    f"::notice file={name},title=A walkthrough picture that moves by "
                    f"itself changed::{name} is listed in {MOVES_BY_ITSELF} ({moving[name]['reason']}), "
                    f"written by {moving[name]['test']}"
                )
                continue
            said.append(
                f"::warning file={name},title=A walkthrough picture changed::{name} "
                f"differs from the committed picture in {share:.2%} of its pixels, past "
                f"{tolerance:.1%}, between ({left}, {top}) and ({right}, {bottom}): look "
                "at it against its caption, and commit it if the page changed"
            )
            if sheets is not None:
                sheets.mkdir(parents=True, exist_ok=True)
                sheet(committed.stdout, now).save(sheets / Path(name).name)
    return said


def main(root: Path = ROOT, argv: list[str] | None = None) -> int:
    argv = [] if argv is None else argv
    sheets = Path(argv[argv.index("--sheets") + 1]) if "--sheets" in argv else None
    said = warnings(root, sheets=sheets)
    for line in said:
        print(line)
    apart = sum(line.startswith("::notice") for line in said)
    print(
        f"{len(said) - apart} walkthrough picture(s) differ from the committed ones past "
        f"{TOLERANCE:.1%} of their pixels"
        + (f", and {apart} that move by themselves" if apart else "")
    )
    if sheets is not None and said:
        print(f"each drawn beside its commit, its changed pixels marked, in {sheets}")
    return 0


if __name__ == "__main__":
    sys.exit(main(argv=sys.argv[1:]))
