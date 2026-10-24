"""`apothecary lighting simulate` says what is wrong instead of a traceback."""

from click.testing import CliRunner

from apothecary.cli.main import cli


def test_simulate_without_a_server_says_how_to_start_one():
    result = CliRunner().invoke(cli, ["lighting", "simulate", "--url", "http://127.0.0.1:9"])
    assert result.exit_code == 1
    assert "apothecary serve" in result.output
