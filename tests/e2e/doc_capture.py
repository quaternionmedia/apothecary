"""Step-by-step screenshot + manifest capture for E2E doc-workflow tests.

Only active when pytest runs with ``--generate-docs`` (see conftest.py's
``doc_recorder`` fixture) -- a normal test run (including CI's
``apothecary test all``) never touches the filesystem here, so the docs
pipeline stays "on demand" rather than a side effect of every test run.

``apothecary docs generate`` (apothecary/cli/docs.py) is what actually runs
the flagged tests and turns the manifests this module writes into Markdown
+ GIFs.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from playwright.sync_api import Page

GENERATED_DOCS_ROOT = Path(__file__).resolve().parents[2] / "docs" / "generated"


def _slugify(text: str, max_length: int = 50) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_length]


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

    def step(self, description: str) -> None:
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
        self.page.screenshot(path=str(screenshots_dir / filename))
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
            "steps": [vars(s) for s in self.steps],
        }
        manifest_path = workflow_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------
# The one demonstration.
#
# Everything above serves `apothecary docs generate`, which is a command
# somebody has to remember. The walkthrough is not allowed to be that: it is
# the page a newcomer meets, and a page produced by a remembered command is
# stale by default. So the walkthrough is written by the run that asserts it,
# on every ordinary run, and this is the recorder for it.
#
# Recorded rather than compared. Nothing asserts what the page says -- a
# behaviour that changes shows up as a diff in the page, which is a thing a
# reader sees, rather than as prose that quietly stopped being true.
# --------------------------------------------------------------------------

WALKTHROUGH_ROOT = Path(__file__).resolve().parents[2] / "walkthrough"


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
    """

    page: Page
    ordinal: str
    slug: str
    title: str
    intro: str
    runtime: str
    does_not_show: List[str]
    steps: List[ShownStep] = field(default_factory=list)

    def says(self, heading: str, sentence: str, shown: str | None = None) -> None:
        self.steps.append(
            ShownStep(index=len(self.steps) + 1, heading=heading, sentence=sentence, shown=shown)
        )

    def shows(self, heading: str, sentence: str, shown: str | None = None) -> None:
        index = len(self.steps) + 1
        filename = f"{index:02d}-{_slugify(heading)}.png"
        shots = WALKTHROUGH_ROOT / "screenshots"
        shots.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(shots / filename))
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

        A run that failed half way writes the steps it reached and says so. The
        alternative -- write nothing on failure -- leaves the last green run's
        page in place, which is the stale page this whole arrangement exists to
        prevent.
        """
        lines: List[str] = [
            f"# {self.ordinal} — {self.title}",
            "",
            "**This page is written by the run it describes.** Every sentence below",
            "was emitted by a test that had just asserted it, and the whole page is",
            "rewritten by the ordinary test command. Editing it by hand is editing",
            "the output of a program: the next run puts it back.",
            "",
            self.intro,
            "",
            f"**Runtime-bound.** {self.runtime}",
            "",
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
        lines.append("uv run apothecary test run --e2e")
        lines.append("```")
        lines.append("")

        WALKTHROUGH_ROOT.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
        return self.path
