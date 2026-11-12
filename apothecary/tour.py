"""The tour: the walkthrough's pages, a step at a time, as the help a person takes
through the app beside the live page, and what the person said of each step.

Each page under ``walkthrough/`` is a stop. A page a test writes (tests/e2e/doc_capture.py)
is read back into its steps -- heading, words, the picture the run recorded after its
assertions, what it showed -- so the tour shows what a test asserted and nothing written
beside it. A page not written that way is read whole, at its link.

A verdict is a person's word on one step: ``as shown``, or ``off`` with what is off. Each
is kept as a line of ``tour/verdicts.jsonl`` under the state folder, with the moment and
the commit the server ran, and never rewritten: the latest for a step is its answer.
``apothecary tour`` reads them back.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .docs_site import WALKTHROUGH_ROOT
from .projects.parts.skeleton import ROOT
from .state_folder import private_folder, state_dir

VERDICTS = ("as shown", "off")

TITLE = re.compile(r"^# (?:(\d+) — )?(.+)$")
WRITTEN_BY = re.compile(r"^Written by `([^`]+)`")
STEP = re.compile(r"^## (\d+)\. (.+)$")
PICTURE = re.compile(r"^!\[[^\]]*\]\((screenshots/[^)\s]+)\)$")
# The recorder's opening ends here; the page's own words follow it.
OPENING_ENDS = "of a program: the next run puts it back."


@dataclass(frozen=True)
class Step:
    index: int
    heading: str
    words: str
    picture: Optional[str]  # its path under walkthrough/, as the page links it
    shown: Optional[str]


@dataclass(frozen=True)
class Stop:
    page: str  # its file name under walkthrough/
    number: str
    title: str
    written_by: Optional[str]  # the test module that writes it, where one does
    intro: str
    steps: Tuple[Step, ...]


def _paragraph(lines: List[str], start: int) -> Tuple[str, int]:
    """The paragraph at or after ``start``, joined, and the line after it."""
    i = start
    while i < len(lines) and not lines[i].strip():
        i += 1
    out = []
    while i < len(lines) and lines[i].strip():
        out.append(lines[i].strip())
        i += 1
    return " ".join(out), i


def read_stop(path: Path) -> Stop:
    """A walkthrough page as the tour's stop."""
    lines = path.read_text(encoding="utf-8").splitlines()
    number = path.name.split("-", 1)[0]
    title = path.stem
    for line in lines:
        found = TITLE.match(line)
        if found:
            title = found.group(2).strip()
            break
    written = next((m.group(1) for m in map(WRITTEN_BY.match, lines) if m), None)
    if written is not None:
        ends = next((i for i, line in enumerate(lines) if line.endswith(OPENING_ENDS)), -1)
        intro, _ = _paragraph(lines, ends + 1)
    else:
        # A page written by hand: its first paragraph past the one saying how it runs.
        i = next((i for i, line in enumerate(lines) if line.startswith("# ")), -1) + 1
        intro, i = _paragraph(lines, i)
        while intro.startswith(("**Hermetic.**", "**Runtime-bound.**")):
            intro, i = _paragraph(lines, i)
    steps: List[Step] = []
    i = 0
    while i < len(lines):
        found = STEP.match(lines[i]) if written is not None else None
        if not found:
            i += 1
            continue
        index, heading = int(found.group(1)), found.group(2).strip()
        words, i = _paragraph(lines, i + 1)
        picture = shown = None
        while i < len(lines) and not lines[i].startswith("## "):
            line = lines[i]
            if PICTURE.match(line):
                picture = PICTURE.match(line).group(1)
            elif line.startswith("```"):
                block = []
                i += 1
                while i < len(lines) and not lines[i].startswith("```"):
                    block.append(lines[i])
                    i += 1
                shown = "\n".join(block)
            i += 1
        steps.append(Step(index, heading, words, picture, shown))
    return Stop(path.name, number, title, written, intro, tuple(steps))


def stops(root: Path = WALKTHROUGH_ROOT) -> List[Stop]:
    """Every walkthrough page, in order, as a stop."""
    return [read_stop(p) for p in sorted(root.glob("[0-9][0-9]-*.md"))]


def stop(page: str, root: Path = WALKTHROUGH_ROOT) -> Optional[Stop]:
    return next((s for s in stops(root) if s.page == page), None)


# --- verdicts ---------------------------------------------------------------------------


def verdicts_path() -> Path:
    return state_dir() / "tour" / "verdicts.jsonl"


def _git(*args: str) -> Optional[str]:
    try:
        done = subprocess.run(
            ["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def running() -> dict:
    """The commit the server's code is, and whether its tree has changes beside it."""
    commit = _git("rev-parse", "--short=8", "HEAD")
    changes = _git("status", "--porcelain", "--untracked-files=no")
    return {"commit": commit, "changed": bool(changes) if changes is not None else None}


class Refused(ValueError):
    """A verdict the tour does not keep, saying why."""


def say(page: str, step: int, verdict: str, note: str = "", root: Path = WALKTHROUGH_ROOT) -> dict:
    """Keep a person's word on ``page``'s ``step`` (0 for a page read whole)."""
    here = stop(page, root)
    if here is None:
        raise LookupError(f"no walkthrough page {page}")
    if verdict not in VERDICTS:
        raise Refused(f"a verdict is one of {', '.join(VERDICTS)}, not {verdict!r}")
    allowed = {s.index for s in here.steps} or {0}
    if step not in allowed:
        raise Refused(f"{page} has no step {step}")
    note = note.strip()
    if verdict == "off" and not note:
        raise Refused("say what is off")
    record = {
        "page": page,
        "step": step,
        "verdict": verdict,
        "note": note,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **running(),
    }
    path = verdicts_path()
    private_folder(path.parent)
    with path.open("a", encoding="utf-8") as out:
        out.write(json.dumps(record) + "\n")
    return record


def said(path: Optional[Path] = None) -> List[dict]:
    """Every verdict kept, oldest first; a line that does not read is left out."""
    path = path or verdicts_path()
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and {"page", "step", "verdict"} <= set(record):
            out.append(record)
    return out


def answers(path: Optional[Path] = None) -> Dict[Tuple[str, int], dict]:
    """Each step's answer: the latest verdict on it."""
    latest: Dict[Tuple[str, int], dict] = {}
    for record in said(path):
        latest[(record["page"], int(record["step"]))] = record
    return latest


def document(root: Path = WALKTHROUGH_ROOT) -> dict:
    """The tour as the page reads it: every stop with its steps, each step's answer
    beside it, and the commit the server runs."""
    given = answers()
    out = []
    for s in stops(root):
        body = asdict(s)
        body["answers"] = {
            str(step): record for (page, step), record in given.items() if page == s.page
        }
        out.append(body)
    return {**running(), "stops": out}
