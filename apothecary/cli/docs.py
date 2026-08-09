"""Docs generation CLI: regenerate docs/generated/ from the E2E doc-workflow tests.

The doc-workflow tests (tests/e2e/test_docs_*.py, marked both `e2e` and
`docs`) are the single source of truth: each `docs.step("...")` call inside
one of them is both an assertion point and a documentation paragraph. This
module runs those tests with screenshot/video capture turned on
(`--generate-docs`, see tests/e2e/conftest.py) and turns the results into,
per workflow: Markdown, a step-by-step animated GIF (the deliverable meant
for embedding somewhere a real video won't play, e.g. a PR description),
and the actual Playwright screen recording of that same run, embedded in
the Markdown as real video -- so editing a test is how you edit the docs.

Everything under docs/generated/ is a build artifact (see .gitignore) --
regenerate it with `apothecary docs generate` whenever the doc-workflow
tests change.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import click

from ..projects.parts.skeleton import ROOT

GENERATED_DOCS_ROOT = ROOT / "docs" / "generated"

WORKFLOW_DOC_TEMPLATE = """# {title}

{intro}

{steps}
## Walkthrough GIF

![{title} walkthrough]({workflow}.gif)
{video_section}"""

VIDEO_SECTION_TEMPLATE = """
## Walkthrough video

The real Playwright recording of this run, not a re-enactment -- if this
test changes, so does this video, next time `apothecary docs generate` runs.

<video controls src="{workflow}.webm" width="800"></video>
"""

STEP_TEMPLATE = """### {index}. {description}

![{description}](screenshots/{screenshot})

"""


@click.group()
def docs():
    """Generate documentation (screenshots, GIFs, Markdown) from the E2E doc-workflow tests."""


@docs.command("generate")
@click.option("--host", default="127.0.0.1", help="Host for the temporary doc-generation server")
@click.option("--port", default=8766, type=int, help="Port for the temporary doc-generation server")
@click.option(
    "--keep-raw-video",
    is_flag=True,
    help="Keep the raw Playwright .webm recordings (normally deleted after GIF assembly)",
)
def generate(host: str, port: int, keep_raw_video: bool):
    """Run the doc-workflow E2E tests and render Markdown + GIFs from the results.

    Starts its own temporary server (STL generation skipped, for speed),
    runs only the tests marked 'docs', then assembles a GIF and a Markdown
    page per workflow into docs/generated/.
    """
    # A previous invocation's raw recordings (especially from a run that
    # failed before reaching cleanup, below) must not still be here --
    # _extract_workflow_videos picks "the" video for a given test out of
    # whatever's in its directory, so a stale leftover from an earlier run
    # would silently outrank (or get mistaken for) this run's actual video.
    raw_video_dir = GENERATED_DOCS_ROOT / "_videos_raw"
    if raw_video_dir.exists():
        shutil.rmtree(raw_video_dir)

    click.echo(f"Starting temporary server at http://{host}:{port} for doc generation...")
    server_proc, base_url = _start_server(host, port)

    try:
        click.echo("Running doc-workflow E2E tests...")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/e2e/",
                "-m",
                "docs",
                "--generate-docs",
                "-v",
                f"--base-url={base_url}",
            ],
            cwd=ROOT,
        )
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()

    if result.returncode != 0:
        raise SystemExit(
            f"Doc-workflow tests failed (exit {result.returncode}); docs were not regenerated."
        )

    click.echo("Extracting per-workflow videos...")
    _extract_workflow_videos()

    click.echo("Assembling GIFs and rendering Markdown...")
    if GENERATED_DOCS_ROOT.exists():
        workflow_dirs = sorted(
            p for p in GENERATED_DOCS_ROOT.iterdir() if p.is_dir() and p.name != "_videos_raw"
        )
    else:
        workflow_dirs = []

    for workflow_dir in workflow_dirs:
        _render_workflow(workflow_dir)

    raw_video_dir = GENERATED_DOCS_ROOT / "_videos_raw"
    if raw_video_dir.exists() and not keep_raw_video:
        shutil.rmtree(raw_video_dir)

    click.secho(f"Docs generated at {GENERATED_DOCS_ROOT}", fg="green")


@docs.command("clean")
def clean():
    """Remove all generated documentation artifacts (docs/generated/)."""
    if GENERATED_DOCS_ROOT.exists():
        shutil.rmtree(GENERATED_DOCS_ROOT)
        click.echo(f"Removed {GENERATED_DOCS_ROOT}")
    else:
        click.echo("Nothing to clean (docs/generated/ does not exist)")


def _start_server(host: str, port: int):
    env = os.environ.copy()
    env["APOTHECARY_SKIP_STL_GENERATION"] = "1"
    env["APOTHECARY_VIEWER_PATH"] = ""

    server_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "apothecary.api:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    server_proc = subprocess.Popen(
        server_cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    base_url = f"http://{host}:{port}"
    for _attempt in range(30):
        try:
            urllib.request.urlopen(f"{base_url}/health", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        server_proc.terminate()
        raise SystemExit("Server failed to start within 15 seconds")

    return server_proc, base_url


def _render_workflow(workflow_dir: Path) -> None:
    manifest_path = workflow_dir / "manifest.json"
    if not manifest_path.exists():
        return

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    workflow = manifest["workflow"]
    screenshots_dir = workflow_dir / "screenshots"
    screenshot_paths = [screenshots_dir / step["screenshot"] for step in manifest["steps"]]

    _assemble_gif(screenshot_paths, workflow_dir / f"{workflow}.gif")

    steps_md = "".join(
        STEP_TEMPLATE.format(
            index=step["index"], description=step["description"], screenshot=step["screenshot"]
        )
        for step in manifest["steps"]
    )
    has_video = (workflow_dir / f"{workflow}.webm").exists()
    video_section = VIDEO_SECTION_TEMPLATE.format(workflow=workflow) if has_video else ""
    doc = WORKFLOW_DOC_TEMPLATE.format(
        title=manifest["title"],
        intro=manifest["intro"],
        steps=steps_md,
        workflow=workflow,
        video_section=video_section,
    )
    doc_path = workflow_dir / f"{workflow}.md"
    doc_path.write_text(doc, encoding="utf-8")
    click.echo(f"  {workflow}: {doc_path}" + (" (+ video)" if has_video else ""))


def _extract_workflow_videos() -> None:
    """Match each doc-workflow test's recorded .webm to the workflow(s) it
    produced, and copy it into that workflow's own docs/generated/ dir as
    ``<workflow>.webm`` -- see conftest.py's browser_context_args/
    doc_recorder for how the marker file and one-video-per-test-directory
    layout this depends on gets created.

    A no-op if doc generation didn't request video (record_video_dir unset)
    or a given test's video hasn't been written yet for some other reason --
    the GIF/Markdown a workflow gets from _render_workflow either way is
    never conditional on this having succeeded.
    """
    raw_video_dir = GENERATED_DOCS_ROOT / "_videos_raw"
    if not raw_video_dir.exists():
        return

    for test_dir in sorted(p for p in raw_video_dir.iterdir() if p.is_dir()):
        marker = test_dir / "workflows.txt"
        if not marker.exists():
            continue
        videos = list(test_dir.glob("*.webm"))
        if not videos:
            click.echo(f"  Warning: no video found for {test_dir.name}, skipping")
            continue
        if len(videos) > 1:
            click.echo(
                f"  Warning: {len(videos)} videos found for {test_dir.name}, using the first"
            )
        video_path = videos[0]

        workflows = [line.strip() for line in marker.read_text(encoding="utf-8").splitlines() if line.strip()]
        for workflow in workflows:
            workflow_dir = GENERATED_DOCS_ROOT / workflow
            workflow_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(video_path, workflow_dir / f"{workflow}.webm")


def _assemble_gif(screenshot_paths: list[Path], output_path: Path, duration_ms: int = 1200) -> None:
    from PIL import Image

    images = [p for p in screenshot_paths if p.exists()]
    if not images:
        return

    frames = [Image.open(p).convert("P", palette=Image.ADAPTIVE) for p in images]
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=0,
    )
