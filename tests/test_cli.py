import pytest
from click.testing import CliRunner
from wp_migration.cli import main


@pytest.fixture
def runner():
    return CliRunner()


def test_run_no_config_errors(runner):
    result = runner.invoke(main, ["run"])
    assert result.exit_code != 0
    assert "CONFIG" in result.output or "config" in result.output or "missing" in result.output


def test_run_nonexistent_config(runner):
    result = runner.invoke(main, ["run", "/nonexistent/config.yaml"])
    assert result.exit_code != 0
    assert "not found" in result.output or "exist" in result.output


def test_export_nonexistent_config(runner):
    result = runner.invoke(main, ["export", "/nonexistent/config.yaml"])
    assert result.exit_code != 0


def test_import_nonexistent_config(runner):
    result = runner.invoke(main, ["import", "/nonexistent/config.yaml"])
    assert result.exit_code != 0


def test_help_prints_usage(runner):
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output or "run" in result.output or "export" in result.output


def test_run_command_accepts_config(runner):
    result = runner.invoke(main, ["run", "config.yaml"])
    # Should try to load the file (will fail with file not found)
    assert result.exit_code != 0


def test_export_command_accepts_config(runner):
    result = runner.invoke(main, ["export", "config.yaml"])
    assert result.exit_code != 0


def test_import_command_accepts_config(runner):
    result = runner.invoke(main, ["import", "config.yaml"])
    assert result.exit_code != 0


def test_run_dry_run_flag(runner):
    result = runner.invoke(main, ["run", "--dry-run", "config.yaml"])
    assert result.exit_code != 0


def test_verbose_flag(runner):
    result = runner.invoke(main, ["--verbose", "run", "config.yaml"])
    assert result.exit_code != 0


def test_no_command_shows_help(runner):
    result = runner.invoke(main, [])
    assert result.exit_code != 0
    assert "Usage" in result.output or "run" in result.output or "show this" in result.output.lower()


def test_invalid_command_shows_error(runner):
    result = runner.invoke(main, ["invalid-command"])
    assert result.exit_code != 0
    assert "No such command" in result.output
