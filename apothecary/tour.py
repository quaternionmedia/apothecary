"""The tour: what the roadmap claims, a stop at a time, and what a person said of each.

``docs/ROADMAP.md`` orders it. Each of its lines names what shows it: a journey
(journeys.py), whose stages are the tour's stops, or walkthrough pages, each one stop
taken whole. A page a journey's stage names is that stage's, and is no stop of its own. A page a test writes (tests/e2e/doc_capture.py) is read back into its
steps -- heading, words, the picture the run recorded after its assertions, what it
showed -- which the tour gives as what to try at a stage, or as a page's own account.
The tour has no words of its own.

An answer is a person's word on one stop: ``as shown``, or ``off`` with what is off.
Each is kept as a line of ``tour/answers.jsonl`` under the state folder, with the moment
and the commit the server ran, and never rewritten: the latest for a stop is its answer.
``apothecary tour`` reads them back. The box over the page is widgets/tour_popover.js.
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
from .docs_site import DOCS_ROOT, WALKTHROUGH_ROOT
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


# --- the roadmap ------------------------------------------------------------------------

ROADMAP = DOCS_ROOT / "ROADMAP.md"
LINE = re.compile(r"^- \[([ xX])\] (.+)$")
JOURNEY = re.compile(r"`journey:([a-z0-9-]+)`")
PAGE = re.compile(r"\]\(\.\./walkthrough/([0-9][0-9]-[^)\s#]+\.md)\)")
NAMES = re.compile(r"\s*(?:`journey:[a-z0-9-]+`|\[[^\]]*\]\([^)]*\))[,\s]*")


@dataclass(frozen=True)
class Line:
    group: str  # the heading it is under
    text: str  # the claim, without what it names
    ticked: bool
    journey: Optional[str]
    pages: Tuple[str, ...]


def roadmap(path: Path = ROADMAP) -> List[Line]:
    """The roadmap's lines, in its order."""
    out: List[Line] = []
    group = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("## "):
            group = raw[3:].strip()
            continue
        found = LINE.match(raw)
        if not found:
            continue
        rest = found.group(2)
        journey = JOURNEY.search(rest)
        out.append(
            Line(
                group,
                NAMES.sub(" ", rest).strip(),
                found.group(1) != " ",
                journey.group(1) if journey else None,
                tuple(PAGE.findall(rest)),
            )
        )
    return out


def stage_id(journey: str, stage: str) -> str:
    return f"journey:{journey}/{stage}"


def page_id(page: str) -> str:
    return f"page:{page}"


def _tries(shown_by: Tuple[str, ...], root: Path) -> List[dict]:
    """What a stage names, as what to try on it: a recorded step, or a page whole
    (``index`` None), which says how the same thing goes at the command line."""
    out = []
    for ref in shown_by:
        page, _, number = ref.partition("#")
        here = stop(page, root)
        if here is None:
            continue
        if not number:
            out.append(
                {
                    "page": page,
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
            out.append({"page": page, **asdict(step)})
    return out


def stage_pages(journey: journeys.Journey) -> List[str]:
    """The walkthrough pages a journey's stages name, each once, in their order."""
    out: List[str] = []
    for step in journey.steps:
        for ref in step.shown_by:
            page = ref.partition("#")[0]
            if page not in out:
                out.append(page)
    return out


def _line_stops(line: Line, root: Path) -> List[dict]:
    """A line's stops: its journey's stages, then its pages, each one stop."""
    out: List[dict] = []
    journey = next((j for j in journeys.JOURNEYS if j.id == line.journey), None)
    if journey:
        for s in journey.steps:
            out.append(
                {
                    "id": stage_id(journey.id, s.id),
                    "kind": "stage",
                    "journey": journey.id,
                    "journey_name": journey.name,
                    "stage": s.id,
                    "title": s.label,
                    "words": s.hint,
                    "tries": _tries(s.shown_by, root),
                    "put_on": True,
                }
            )
    for page in line.pages:
        here = stop(page, root)
        if here is None:
            continue
        out.append(
            {
                "id": page_id(page),
                "kind": "page",
                "page": page,
                "number": here.number,
                "title": here.title,
                "words": here.intro,
                "written_by": here.written_by,
                "tries": [{"page": page, **asdict(s)} for s in here.steps],
                "put_on": False,
            }
        )
    return out


def stop_ids(path: Path = ROADMAP, root: Path = WALKTHROUGH_ROOT) -> List[str]:
    return [s["id"] for line in roadmap(path) for s in _line_stops(line, root)]


# --- answers ----------------------------------------------------------------------------


def answers_path() -> Path:
    return state_dir() / "tour" / "answers.jsonl"


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
    """An answer the tour does not keep, saying why."""


def say(stop_id: str, verdict: str, note: str = "") -> dict:
    """Keep a person's word on the stop ``stop_id``."""
    if stop_id not in stop_ids():
        raise LookupError(f"the roadmap has no stop {stop_id}")
    if verdict not in VERDICTS:
        raise Refused(f"an answer is one of {', '.join(VERDICTS)}, not {verdict!r}")
    note = note.strip()
    if verdict == "off" and not note:
        raise Refused("say what is off")
    record = {
        "stop": stop_id,
        "verdict": verdict,
        "note": note,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **running(),
    }
    path = answers_path()
    private_folder(path.parent)
    with path.open("a", encoding="utf-8") as out:
        out.write(json.dumps(record) + "\n")
    return record


def said(path: Optional[Path] = None) -> List[dict]:
    """Every answer kept, oldest first; a line that does not read is left out."""
    path = path or answers_path()
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and {"stop", "verdict"} <= set(record):
            out.append(record)
    return out


def answers(path: Optional[Path] = None) -> Dict[str, dict]:
    """Each stop's answer: the latest word on it."""
    return {record["stop"]: record for record in said(path)}


def document(path: Path = ROADMAP, root: Path = WALKTHROUGH_ROOT) -> dict:
    """The tour as the box reads it: the roadmap's lines in order, each with its stops
    and each stop's answer, the pages no line names, and the commit the server runs."""
    given = answers()
    lines = []
    named = set()
    for line in roadmap(path):
        stops_ = _line_stops(line, root)
        for s in stops_:
            s["answer"] = given.get(s["id"])
        named.update(line.pages)
        if line.journey in {j.id for j in journeys.JOURNEYS}:
            named.update(stage_pages(journeys.by_id(line.journey)))
        lines.append(
            {
                "group": line.group,
                "text": line.text,
                "ticked": line.ticked,
                "shown_by_nothing": not stops_,
                "stops": stops_,
            }
        )
    unnamed = [s.page for s in stops(root) if s.page not in named]
    return {**running(), "lines": lines, "not_on_the_roadmap": unnamed}
