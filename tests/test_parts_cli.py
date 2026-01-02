from click.testing import CliRunner

from apothecary.cli import cli


def test_parts_list():
    r = CliRunner().invoke(cli, ["parts", "list"])
    assert r.exit_code == 0
    # Should list at least one known part name
    assert "parametric_star" in r.output or "solderfan" in r.output


def test_parts_info_json():
    r = CliRunner().invoke(cli, ["parts", "info", "parametric_star", "--json-out"])
    assert r.exit_code == 0
    assert "\"name\"" in r.output
    assert "parametric_star" in r.output


def test_parts_render(tmp_path):
    out = tmp_path / "p.scad"
    r = CliRunner().invoke(
        cli,
        [
            "parts",
            "render",
            "parametric_star",
            "--params-json",
            "{\"points\":7,\"outer_radius\":30}",
            "-o",
            str(out),
        ],
    )
    assert r.exit_code == 0
    assert out.exists()
    text = out.read_text()
    assert "include <" in text
