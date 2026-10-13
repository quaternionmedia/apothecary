"""Screenshots, manifests and pages written by the browser tests that document.

Two recorders. ``DocRecorder`` captures a doc workflow's screenshots and manifest
under ``docs/generated/`` only when pytest runs with ``--generate-docs`` (see
conftest.py's ``doc_recorder`` fixture); without it, it writes nothing, so those
docs are made on demand. ``apothecary docs generate`` (apothecary/cli/docs.py) runs
the tests marked ``docs`` and turns the manifests into Markdown and GIFs.

``Walkthrough``, below, writes its walkthrough page and that page's screenshots on
every run of the test that holds it, ``--generate-docs`` or not (conftest.py's
``walkthrough`` fixture).
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Sequence, Tuple, Union

from playwright.sync_api import Page
from viewer_ready import settled

GENERATED_DOCS_ROOT = Path(__file__).resolve().parents[2] / "docs" / "generated"


def _slugify(text: str, max_length: int = 50) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_length]


# --------------------------------------------------------------------------
# A picture of the page, with what changes on every run blanked.
# --------------------------------------------------------------------------

# What a picture paints over what changes on every run: a grey the dark page reads as
# a blank, not as anything it draws.
BLANK_COLOR = "#3c3c3c"

# What differs on every run whatever the page does, found in the words: the moment a
# kept picture is named by (20261011T231147.943), a date or a time of day as the
# browser writes one, and a duration as the Machine writes one (1m 2s, 1h 3m).
MOMENT = (
    r"\d{8}T\d{6}(?:\.\d+)?"
    r"|\d{1,2}/\d{1,2}/\d{4},? \d{1,2}:\d{2}(?::\d{2})?(?:\s?[AP]M)?"
    r"|\d{1,2}:\d{2}:\d{2}(?:\.\d+)?(?:\s?[AP]M)?"
    r"|\b\d+h \d+m(?: \d+s)?\b|\b\d+m \d+s\b"
)

# A temperature to its tenth beside its target (``210.2/210``), which wobbles round the
# target from poll to poll.
TEMPERATURE = r"\d{1,3}\.\d+(?=\s*/\s*\d)"

# A folder of a temporary home -- the stand-in tools' and a server's state, made anew
# each run -- where a card names one (``/tmp/apothecary-docs-ych6eu0lk/tools``).
FOLDER = r"(?:/[\w.@+-]+){2,}/?"

# A blank is a CSS selector, whose element is blanked whole (a chart, a log: what a
# layout sizes, not its words), or a selector and a pattern, where only the words
# matching it are blanked, each the same width whatever they say, so the line around
# them is pictured and does not move. ``moments(selector)`` is the second with MOMENT.
Blank = Union[str, Tuple[str, str]]


def moments(*selectors: str) -> Tuple[Tuple[str, str], ...]:
    """Blanks of the moments in what ``selectors`` name, and nothing else of them."""
    return tuple((selector, MOMENT) for selector in selectors)


# All of an element's words, from the first to the last.
ALL_WORDS = r"\S(?:.*\S)?"


def all_words(*selectors: str) -> Tuple[Tuple[str, str], ...]:
    """Blanks of all the words of what ``selectors`` name, one grey of one width: for an
    element that holds a moment and nothing else, in a form MOMENT does not read (``Oct
    12, 2026, 12:18 PM``), which blanked whole would be as wide as its words."""
    return tuple((selector, ALL_WORDS) for selector in selectors)


# The words a pattern matches, each wrapped in a span of a fixed width, and kept wrapped
# while the page rewrites them (a poll redraws a list): an observer wraps again before
# the next frame is drawn. ``window.__unblank()`` takes it all back.
WRAP_WORDS = """(blanks) => {
    const wrap = () => {
        for (const [selector, pattern] of blanks) {
            const re = new RegExp(pattern, 'g');
            for (const root of document.querySelectorAll(selector)) {
                const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
                const texts = [];
                while (walker.nextNode()) texts.push(walker.currentNode);
                for (const text of texts) {
                    if (text.parentElement && text.parentElement.hasAttribute('data-blanked')) continue;
                    const found = [...text.data.matchAll(re)].filter((m) => m[0]);
                    if (!found.length) continue;
                    const words = document.createDocumentFragment();
                    let at = 0;
                    for (const m of found) {
                        words.append(text.data.slice(at, m.index));
                        const span = document.createElement('span');
                        span.setAttribute('data-blanked', '');
                        span.textContent = m[0];
                        words.append(span);
                        at = m.index + m[0].length;
                    }
                    words.append(text.data.slice(at));
                    text.replaceWith(words);
                }
            }
        }
    };
    wrap();
    const watching = new MutationObserver(wrap);
    watching.observe(document.body, { subtree: true, childList: true, characterData: true });
    window.__unblank = () => {
        watching.disconnect();
        for (const span of document.querySelectorAll('[data-blanked]')) {
            const parent = span.parentNode;
            span.replaceWith(span.textContent);
            parent && parent.normalize();
        }
    };
}"""


def _blanked(blanks: Sequence[Blank]) -> str:
    """The stylesheet a picture is taken under: each whole blank's words and what it
    holds hidden on a grey of its own size, in the page rather than painted over the
    picture, so what a panel has scrolled out of sight stays out of sight; and every
    blanked word a grey of one width."""
    whole = [b for b in blanks if isinstance(b, str)]
    style = (
        "[data-blanked] { display: inline-block; width: 5.5em; height: 1.05em;"
        " vertical-align: text-bottom; overflow: hidden; white-space: nowrap;"
        f" background: {BLANK_COLOR} !important; color: transparent !important;"
        " text-shadow: none !important; border-radius: 3px; }\n"
    )
    if whole:
        each = ", ".join(whole)
        inside = ", ".join(f"{selector} *" for selector in whole)
        style += (
            f"{each} {{ background: {BLANK_COLOR} !important; color: transparent !important;"
            " text-shadow: none !important; border-radius: 3px; }\n"
            f"{inside} {{ visibility: hidden !important; }}\n"
        )
    return style


def picture(page: Page, blanks: Sequence[Blank] = ()) -> bytes:
    """The page as a person sees it once it has settled (viewer_ready.settled), with
    ``blanks`` blanked."""
    settled(page)
    words = [list(b) for b in blanks if not isinstance(b, str)]
    if words:
        page.evaluate(WRAP_WORDS, words)
        settled(page)
    try:
        return page.screenshot(style=_blanked(blanks))
    finally:
        if words:
            page.evaluate("() => window.__unblank && window.__unblank()")


@dataclass
class DocStep:
    index: int
    description: str
    screenshot: str  # filename, relative to the workflow's screenshots/ dir


@dataclass
class DocRecorder:
    """Records step screenshots + a manifest for one doc workflow.

    A no-op (no filesystem writes) when ``enabled`` is False, so tests can
    call ``.step(...)`` unconditionally without branching on whether doc
    generation is turned on.
    """

    page: Page
    workflow: str
    title: str
    intro: str
    enabled: bool
    steps: List[DocStep] = field(default_factory=list)
    stls: str | None = None  # which OpenSCAD built the STLs its pictures draw (parts_built.py)

    def step(self, description: str, blank: Sequence[Blank] = ()) -> None:
        """``blank``: as ``Walkthrough.shows``'s, what differs on every run whatever the
        page does -- a time, a temperature's path -- blanked for the picture."""
        if not self.enabled:
            return
        index = len(self.steps) + 1
        filename = f"{index:02d}-{_slugify(description)}.png"
        screenshots_dir = GENERATED_DOCS_ROOT / self.workflow / "screenshots"
        if index == 1 and screenshots_dir.exists():
            # A run that lost or gained steps must not leave the previous
            # run's numbered files beside this one's.
            shutil.rmtree(screenshots_dir)
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        (screenshots_dir / filename).write_bytes(picture(self.page, blank))
        self.steps.append(DocStep(index=index, description=description, screenshot=filename))

    def finalize(self) -> None:
        if not self.enabled:
            return
        workflow_dir = GENERATED_DOCS_ROOT / self.workflow
        workflow_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "workflow": self.workflow,
            "title": self.title,
            "intro": self.intro,
            "stls": self.stls,
            "steps": [vars(s) for s in self.steps],
        }
        manifest_path = workflow_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------
# The walkthrough's pages.
#
# Everything above serves `apothecary docs generate`, a command run on
# request. A walkthrough page is written by the run that asserts it instead:
# pages 11 and 12 by the ordinary test command, a loop's page by the browser
# suite. CI fails when a page a run rewrote differs from the committed one, so
# a page carries nothing that changes from run to run.
#
# Recorded rather than compared. Nothing asserts what the page says -- a
# behaviour that changes shows up as a diff in the page, which is a thing a
# reader sees, rather than as prose that quietly stopped being true.
# --------------------------------------------------------------------------

WALKTHROUGH_ROOT = Path(__file__).resolve().parents[2] / "walkthrough"


def _keep_unless_changed(path: Path, png: bytes) -> None:
    """Write the screenshot only when its pixels differ from the committed one: a
    re-encode of the same picture is not a change, so a run leaves an unchanged
    screenshot as committed."""
    import io

    from PIL import Image, ImageChops

    if path.exists():
        old = Image.open(path).convert("RGB")
        new = Image.open(io.BytesIO(png)).convert("RGB")
        if old.size == new.size:
            changed = sum(ImageChops.difference(old, new).convert("L").histogram()[1:])
            # Software WebGL rasterises an edge a pixel differently now and then;
            # a change is more than a hundredth of a percent of the picture.
            if changed <= old.size[0] * old.size[1] // 10000:
                return
    path.write_bytes(png)


@dataclass
class ShownStep:
    """One step: a sentence of the page, and what the run had at that moment."""

    index: int
    heading: str
    sentence: str
    screenshot: str | None = None
    shown: str | None = None


@dataclass
class Walkthrough:
    """The demonstration's own account of itself.

    `says` is a step with nothing to look at -- the model half, which needs no
    browser. `shows` is a step with a picture of the screen. Both are called
    from a test that has just asserted the thing the sentence claims, which is
    the only reason the sentence is worth anything.

    `browser_suite_only` is a page the browser suite writes and the quick
    `apothecary test run` does not -- a loop's page, whose run is unmarked
    `walkthrough`: its header says the browser suite rewrites it, and its footer
    names `module`, the test module that writes it, to run alone.
    The fixture sets `module` and holds the flag to the run's marker, so the words
    stay true. It is the one place a page says who writes it.
    """

    page: Page
    ordinal: str
    slug: str
    title: str
    intro: str
    runtime: str
    does_not_show: List[str]
    steps: List[ShownStep] = field(default_factory=list)
    browser_suite_only: bool = False
    module: str | None = None  # the test module that writes the page, from the repository root
    stls: str | None = None  # which OpenSCAD built the STLs its pictures draw (parts_built.py)

    def says(self, heading: str, sentence: str, shown: str | None = None) -> None:
        self.steps.append(
            ShownStep(index=len(self.steps) + 1, heading=heading, sentence=sentence, shown=shown)
        )

    def shows(
        self, heading: str, sentence: str, shown: str | None = None, blank: Sequence[Blank] = ()
    ) -> None:
        """``blank``: what differs on every run whatever the page does -- a clock's time,
        a name made of one -- blanked for the picture, so it changes when the page does
        and not when the clock does: a selector blanked whole, or a selector and a
        pattern (``moments(...)``) blanking only the words that match. The picture is
        taken once the page has settled."""
        index = len(self.steps) + 1
        # The pages share one folder of screenshots, so each picture carries
        # its page's ordinal ahead of its step's.
        filename = f"{self.ordinal}-{index:02d}-{_slugify(heading)}.png"
        shots = WALKTHROUGH_ROOT / "screenshots"
        shots.mkdir(parents=True, exist_ok=True)
        png = picture(self.page, blank)
        _keep_unless_changed(shots / filename, png)
        self.steps.append(
            ShownStep(
                index=index,
                heading=heading,
                sentence=sentence,
                screenshot=filename,
                shown=shown,
            )
        )

    @property
    def path(self) -> Path:
        return WALKTHROUGH_ROOT / f"{self.ordinal}-{self.slug}.md"

    def write(self) -> Path:
        """Write the page. Called however the run ends, so a red run is visible.

        A run that fails half way writes the steps it reached, so the page's diff
        shows where it stopped. Writing nothing on failure would leave the last
        green run's page in place, describing a run that did not happen.
        """
        lines: List[str] = [
            f"# {self.ordinal} — {self.title}",
            "",
            f"Written by `{self.module}`, and" if self.module else "Written by its test, and",
            *(
                [
                    "rewritten by every run of the browser suite (`uv run apothecary test",
                    "all`), though not by the quicker `apothecary test run`.",
                ]
                if self.browser_suite_only
                else ["rewritten by the ordinary test command (`uv run apothecary test run`)."]
            ),
            "Each numbered step is written as the run reaches it, after the assertions",
            "before it pass, and what a step shows is what the run had then. The",
            "opening, the notes under it and the list of what the page does not show",
            "are the test's fixed words. Editing the page by hand is editing the output",
            "of a program: the next run puts it back.",
            "",
            self.intro,
            "",
            f"**Runtime-bound.** {self.runtime}",
            "",
            *([self.stls, ""] if self.stls and any(s.screenshot for s in self.steps) else []),
            "---",
            "",
        ]
        for step in self.steps:
            lines.append(f"## {step.index}. {step.heading}")
            lines.append("")
            lines.append(step.sentence)
            lines.append("")
            if step.screenshot:
                lines.append(f"![{step.heading}](screenshots/{step.screenshot})")
                lines.append("")
            if step.shown:
                lines.append("```")
                lines.extend(step.shown.rstrip("\n").splitlines())
                lines.append("```")
                lines.append("")

        lines.append("## What this page does not show")
        lines.append("")
        for boundary in self.does_not_show:
            lines.append(f"- {boundary}")
        lines.append("")
        lines.append("Run it yourself:")
        lines.append("")
        lines.append("```sh")
        if self.browser_suite_only and self.module:
            alone = f"uv run pytest {self.module} --start-server"
            suite = "uv run apothecary test all"
            width = max(len(alone), len(suite)) + 3
            lines.append(f"{alone:<{width}}# this page alone")
            lines.append(f"{suite:<{width}}# with every browser test")
        else:
            lines.append("uv run apothecary test run")
        lines.append("```")
        lines.append("")

        WALKTHROUGH_ROOT.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
        return self.path
