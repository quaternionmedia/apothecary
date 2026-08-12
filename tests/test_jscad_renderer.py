import shutil
import subprocess
from pathlib import Path

import pytest

from apothecary.example import create_example_scene


def test_scene_render_jscad_produces_module():
    scene = create_example_scene()
    js_code = scene.render_jscad()
    assert "export const main" in js_code
    assert "cube(" in js_code or "cylinder(" in js_code or "sphere(" in js_code


@pytest.mark.skipif(shutil.which("node") is None, reason="node runtime required")
def test_scene_render_jscad_passes_node_check(tmp_path: Path):
    scene = create_example_scene()
    js_code = scene.render_jscad()
    target = tmp_path / "scene.jscad.mjs"
    target.write_text(js_code, encoding="utf-8")
    proc = subprocess.run(
        ["node", "--check", str(target)], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
