from click.testing import CliRunner

from apothecary.cli import cli


def test_cli_render_jscad_with_example_scene(tmp_path):
    runner = CliRunner()
    out = tmp_path / "scene.jscad.js"
    result = runner.invoke(cli, ["render-jscad", "-o", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "export const main" in text
