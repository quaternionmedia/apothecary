"""The page's ES modules run under node as the page imports them: ``/static/...`` from
apothecary/static, and ``three`` from its vendored copy, as the viewer's import map has
it. A test writes a module body that imports what it holds and prints one line of JSON
last; ``run_module`` runs it and answers that line."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "apothecary" / "static"
THREE = STATIC / "vendor" / "three" / "three.module.js"
NODE = shutil.which("node") or str(Path.home() / ".local" / "bin" / "node")
HAVE_NODE = Path(NODE).exists()


def run_module(folder: Path, body: str) -> dict:
    """``body``, an ES module, run under node from ``folder``; its last line as JSON."""
    hooks = folder / "hooks.mjs"
    hooks.write_text(
        "export async function resolve(specifier, context, next) {\n"
        "  if (specifier === 'three')\n"
        f"    return next({json.dumps(THREE.as_uri())}, context);\n"
        "  if (specifier.startsWith('/static/'))\n"
        f"    return next(new URL('.' + specifier.slice(7), {json.dumps(STATIC.as_uri() + '/')}).href, context);\n"
        "  return next(specifier, context);\n"
        "}\n",
        encoding="utf-8",
    )
    register = folder / "register.mjs"
    register.write_text(
        "import { register } from 'node:module';\n"
        f"register({json.dumps(hooks.as_uri())});\n",
        encoding="utf-8",
    )
    script = folder / "run.mjs"
    script.write_text(body, encoding="utf-8")
    ran = subprocess.run(
        [NODE, "--import", register.as_uri(), str(script)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=folder,
        check=False,
    )
    assert ran.returncode == 0, ran.stderr
    return json.loads(ran.stdout.strip().splitlines()[-1])
