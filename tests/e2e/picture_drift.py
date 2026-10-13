"""After the browser tests: each walkthrough picture the run rewrote, against the committed one.

    uv run python tests/e2e/picture_drift.py

A picture that differs from the committed one in more than ``TOLERANCE`` of its
pixels is named in a GitHub warning annotation (``::warning file=...::``), which
CI shows on the run and a terminal shows as a line. It never fails: a picture is
looked at against its caption by a person, and a page changed on purpose is
committed with its pictures. A run rewrites a picture only past a hundredth of a
percent (doc_capture.py's ``_keep_unless_changed``), so what this reads is only
what the run wrote.
"""

from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[2]
PICTURES = "walkthrough/screenshots"

# Of a picture's pixels: a tenth of a percent, a thousand pixels of a page. Two runs
# of the walkthrough on one machine differ by a few dozen pixels in a picture at
# most; a word of the hint bar or the status line is thousands. Past this, the picture shows something the
# committed one does not, or another machine drew it.
TOLERANCE = 0.001


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


def warnings(root: Path = ROOT, tolerance: float = TOLERANCE) -> list[str]:
    """One annotation per picture past ``tolerance``, naming it."""
    said = []
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
        share = differing(committed.stdout, path.read_bytes())
        if share > tolerance:
            said.append(
                f"::warning file={name},title=A walkthrough picture changed::{name} "
                f"differs from the committed picture in {share:.2%} of its pixels, past "
                f"{tolerance:.1%}: look at it against its caption, and commit it if the "
                "page changed"
            )
    return said


def main(root: Path = ROOT) -> int:
    said = warnings(root)
    for line in said:
        print(line)
    print(
        f"{len(said)} walkthrough picture(s) differ from the committed ones past "
        f"{TOLERANCE:.1%} of their pixels"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
