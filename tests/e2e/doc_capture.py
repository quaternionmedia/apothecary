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
