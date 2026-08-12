import json

from click.testing import CliRunner

from apothecary.cli import cli


def test_inventory_projects_text():
    runner = CliRunner()
    result = runner.invoke(cli, ["inventory", "projects"])
    assert result.exit_code == 0
    # Should at least mention 'parts' or 'fifel' depending on repo contents
    assert ("project:" in result.output) or ("part:" in result.output)


def test_inventory_structure_json():
    runner = CliRunner()
    result = runner.invoke(cli, ["inventory", "structure", "--json-out"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    # Basic contract: keys we expect to be present
    for key in ["root", "projects", "parts", "templates", "missing_readmes"]:
        assert key in data


def test_inventory_structure_text():
    runner = CliRunner()
    result = runner.invoke(cli, ["inventory", "structure"])  # text path
    assert result.exit_code == 0
    out = result.output
    assert "root:" in out
    assert "projects:" in out
    assert "parts:" in out
    assert "templates:" in out
    assert "missing READMEs:" in out
