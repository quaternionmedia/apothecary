"""The tour: the page's journeys a stage at a time, and what a person said of each.

The journeys (journeys.py) order it, in the order of the chain the page manages. A
stage's words are its step's own in journeys.py, and what there is to try on it is what the
stage names: steps of the walkthrough's pages, each read back here with its heading, its
words and the picture kept with it, and pages that show the same thing whole. The tour
has no words of its own.

Feedback is a person's word on one stage: ``works``, or ``off`` with what is off, under
the name they give. Each is kept as a line of ``tour/feedback.jsonl`` under the state
folder, with the moment and the commit the server ran, and never rewritten: the latest
for a stage is its feedback. A word is of the build it was said of: once the server runs
another commit it is still shown, as said of an earlier build, and the stage waits for a
word again. The box over the page is widgets/tour_popover.js.

What the project's roadmap claims of these journeys, and what was said of each claim, is
not read here: the roadmap is project/ROADMAP.md on apothecary's branch of the governance
corpus, and ``qmcp tour`` reads it beside ``GET /tour`` and ``GET /tour/feedback``.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import journeys
from .docs_site import WALKTHROUGH_ROOT
from .projects.parts.skeleton import ROOT
from .state_folder import private_folder, state_dir

VERDICTS = ("works", "off")
NAME_MOST = 80  # a name is kept this long at most

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
class Page:
    page: str  # its file name under walkthrough/
    number: str
    title: str
    written_by: Optional[str]  # the module that writes it, where one does
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


def read_page(path: Path) -> Page:
    """A walkthrough page as the tour reads it: its title, its first words, its steps."""
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
    return Page(path.name, number, title, written, intro, tuple(steps))


def pages(root: Path = WALKTHROUGH_ROOT) -> List[Page]:
    """Every walkthrough page, in order."""
    return [read_page(p) for p in sorted(root.glob("[0-9][0-9]-*.md"))]


def page(name: str, root: Path = WALKTHROUGH_ROOT) -> Optional[Page]:
    path = root / name
    return read_page(path) if path.is_file() else None


# --- the stages -------------------------------------------------------------------------


def stage_id(journey: str, stage: str) -> str:
    return f"{journey}/{stage}"


def _tries(shown_by: Tuple[str, ...], root: Path) -> List[dict]:
    """What a stage names, as what to try on it: a step of a page, or a page whole
    (``index`` None), which says how the same thing goes at the command line."""
    out = []
    for ref in shown_by:
        name, _, number = ref.partition("#")
        here = page(name, root)
        if here is None:
            continue
        if not number:
            out.append(
                {
                    "page": name,
                    "index": None,
                    "heading": f"{here.number} — {here.title}",
                    "words": here.intro,
                    "picture": None,
                    "shown": None,
                }
            )
            continue
        step = next((s for s in here.steps if str(s.index) == number), None)
        if step:
            out.append({"page": name, **asdict(step)})
    return out


def stage_ids() -> List[str]:
    return [stage_id(j.id, s.id) for j in journeys.JOURNEYS for s in j.steps]


# --- feedback ---------------------------------------------------------------------------


def feedback_path() -> Path:
    return state_dir() / "tour" / "feedback.jsonl"


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
    """Feedback the tour does not keep, saying why."""


def say(stage: str, verdict: str, note: str = "", by: str = "") -> dict:
    """Keep the word of the person ``by`` on the stage ``stage``, ``journey/stage``."""
    if stage not in stage_ids():
        raise LookupError(f"no journey has a stage {stage}")
    if verdict not in VERDICTS:
        raise Refused(f"feedback is one of {', '.join(VERDICTS)}, not {verdict!r}")
    note, by = note.strip(), by.strip()
    if verdict == "off" and not note:
        raise Refused("say what is off")
    if not by:
        raise Refused("say who is saying it")
    record = {
        "stage": stage,
        "verdict": verdict,
        "note": note,
        "by": by[:NAME_MOST],
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **running(),
    }
    path = feedback_path()
    private_folder(path.parent)
    with path.open("a", encoding="utf-8") as out:
        out.write(json.dumps(record) + "\n")
    return record


def said(path: Optional[Path] = None) -> List[dict]:
    """Every word kept, oldest first; a line that does not read is left out."""
    path = path or feedback_path()
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and {"stage", "verdict"} <= set(record):
            out.append(record)
    return out


def feedback(path: Optional[Path] = None) -> Dict[str, dict]:
    """Each stage's feedback: the latest word on it."""
    return {record["stage"]: record for record in said(path)}


def document(root: Path = WALKTHROUGH_ROOT) -> dict:
    """The tour as the box reads it: the journeys in their order, each stage with its
    words, what to try on it and its feedback, and the commit the server runs. A
    stage's feedback says whether it is ``current``: said of the commit now running.
    A server that cannot say its commit ties no word to a build, and each counts."""
    now, given = running(), feedback()

    def latest(stage: str) -> Optional[dict]:
        record = given.get(stage)
        if record is None:
            return None
        current = now["commit"] is None or record.get("commit") == now["commit"]
        return {**record, "current": current}

    return {
        **now,
        "journeys": [
            {
                "id": journey.id,
                "name": journey.name,
                "stages": [
                    {
                        "id": stage_id(journey.id, s.id),
                        "journey": journey.id,
                        "stage": s.id,
                        "title": s.label,
                        "words": s.hint,
                        "tries": _tries(s.shown_by, root),
                        "feedback": latest(stage_id(journey.id, s.id)),
                    }
                    for s in journey.steps
                ],
            }
            for journey in journeys.JOURNEYS
        ],
    }
