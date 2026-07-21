"""Docs generation CLI: regenerate docs/generated/ from the E2E doc-workflow tests.

The doc-workflow tests (tests/e2e/test_docs_*.py, marked both `e2e` and
`docs`) are the single source of truth: each `docs.step("...")` call inside
one of them is both an assertion point and a documentation paragraph. This
module runs those tests with screenshot/video capture turned on
(`--generate-docs`, see tests/e2e/conftest.py) and turns the resulting
manifests into Markdown + an animated GIF per workflow -- so editing a test
is how you edit the docs.

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
    doc = WORKFLOW_DOC_TEMPLATE.format(
        title=manifest["title"], intro=manifest["intro"], steps=steps_md, workflow=workflow
    )
    doc_path = workflow_dir / f"{workflow}.md"
    doc_path.write_text(doc, encoding="utf-8")
    click.echo(f"  {workflow}: {doc_path}")


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
