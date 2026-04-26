import pytest
from click.testing import CliRunner
from wp_migration.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def sample_config(tmp_path):
    import yaml
    cfg = {
        "source": {
            "transport": "sftp",
            "host": "old.com",
            "user": "u",
            "password": "p",
            "remote_path": "/var/www",
        },
        "target": {
            "transport": "ftp",
            "host": "new.com",
            "user": "u",
            "password": "p",
            "remote_path": "/www",
        },
    }
    path = tmp_path / "config.yaml"
    with open(path, "w") as f:
        yaml.dump(cfg, f)
    return str(path)


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


class TestExportWithSkipDb:
    def test_skip_db_export_succeeds(self, runner, sample_config, mocker):
        mocker.patch("wp_migration.cli.dump_database", side_effect=Exception("Should not be called"))
        mocker.patch("wp_migration.cli._resolve_source_db_config")
        mock_conn = mocker.MagicMock()
        mocker.patch("wp_migration.cli.connect", return_value=mock_conn)
        mocker.patch("wp_migration.cli.discover_wp_content", return_value=set())
        import yaml
        with open(sample_config) as f:
            cfg = yaml.safe_load(f)
        cfg["options"] = {"skip_db": True}
        with open(sample_config, "w") as f:
            yaml.dump(cfg, f)
        result = runner.invoke(main, ["export", sample_config])
        assert result.exit_code == 0
        assert "skip_db" in result.output or "skipped" in result.output.lower()

    def test_skip_db_does_not_call_dump_database(self, runner, sample_config, mocker):
        mocker.patch("wp_migration.cli._resolve_source_db_config")
        mock_conn = mocker.MagicMock()
        mocker.patch("wp_migration.cli.connect", return_value=mock_conn)
        mocker.patch("wp_migration.cli.discover_wp_content", return_value=set())
        dump = mocker.patch("wp_migration.cli.dump_database")
        import yaml
        with open(sample_config) as f:
            cfg = yaml.safe_load(f)
        cfg["options"] = {"skip_db": True}
        with open(sample_config, "w") as f:
            yaml.dump(cfg, f)
        runner.invoke(main, ["export", sample_config])
        dump.assert_not_called()


class TestExportDbFallback:
    def test_local_db_failure_triggers_remote_ssh_dump(self, runner, sample_config, mocker):
        from wp_migration.db import DatabaseError
        mocker.patch("wp_migration.cli._resolve_source_db_config")
        mocker.patch("wp_migration.cli.dump_database", side_effect=DatabaseError("Can't connect"))
        mock_conn = mocker.MagicMock()
        mock_conn.exec_command = mocker.MagicMock()
        mocker.patch("wp_migration.cli.connect", return_value=mock_conn)
        mocker.patch("wp_migration.cli.discover_wp_content", return_value=set())
        remote_dump = mocker.patch("wp_migration.cli.remote_dump_via_ssh")

        result = runner.invoke(main, ["export", sample_config])

        assert result.exit_code == 0
        remote_dump.assert_called_once()

    def test_auto_detect_url_from_wp_config(self, mocker):
        from wp_migration.cli import _resolve_source_url
        from wp_migration.config import MigrationConfig, HostConfig, OptionsConfig

        cfg = MigrationConfig(
            source=HostConfig(
                transport="sftp", host="host.com", port=22, user="u",
                password="p", remote_path="/var/www",
            ),
            target=HostConfig(
                transport="ftp", host="new.com", user="u",
                password="p", remote_path="/www",
            ),
        )
        mock_conn = mocker.MagicMock()
        mocker.patch("wp_migration.cli.connect", return_value=mock_conn)
        mocker.patch("wp_migration.cli.discover_wp_config", return_value="/var/www/wp-config.php")
        mocker.patch("wp_migration.cli._read_remote_file", return_value="""<?php
define('WP_HOME', 'http://example.com');
define('WP_SITEURL', 'http://example.com/wp');
""")
        url = _resolve_source_url(cfg)
        assert url == "http://example.com"

    def test_auto_detect_url_falls_back_to_siteurl(self, mocker):
        from wp_migration.cli import _resolve_source_url
        from wp_migration.config import MigrationConfig, HostConfig, OptionsConfig

        cfg = MigrationConfig(
            source=HostConfig(
                transport="sftp", host="host.com", port=22, user="u",
                password="p", remote_path="/var/www",
            ),
            target=HostConfig(
                transport="ftp", host="new.com", user="u",
                password="p", remote_path="/www",
            ),
        )
        mock_conn = mocker.MagicMock()
        mocker.patch("wp_migration.cli.connect", return_value=mock_conn)
        mocker.patch("wp_migration.cli.discover_wp_config", return_value="/var/www/wp-config.php")
        mocker.patch("wp_migration.cli._read_remote_file", return_value="""<?php
define('WP_SITEURL', 'http://example.com/wp');
""")
        url = _resolve_source_url(cfg)
        assert url == "http://example.com/wp"

    def test_auto_detect_url_returns_none_when_not_found(self, mocker):
        from wp_migration.cli import _resolve_source_url
        from wp_migration.config import MigrationConfig, HostConfig, OptionsConfig

        cfg = MigrationConfig(
            source=HostConfig(
                transport="sftp", host="host.com", port=22, user="u",
                password="p", remote_path="/var/www",
            ),
            target=HostConfig(
                transport="ftp", host="new.com", user="u",
                password="p", remote_path="/www",
            ),
        )
        mock_conn = mocker.MagicMock()
        mocker.patch("wp_migration.cli.connect", return_value=mock_conn)
        mocker.patch("wp_migration.cli.discover_wp_config", return_value="/var/www/wp-config.php")
        mocker.patch("wp_migration.cli._read_remote_file", return_value="""<?php
define('DB_NAME', 'test');
""")
        url = _resolve_source_url(cfg)
        assert url is None

    def test_ftp_fallback_to_php_dump(self, runner, tmp_path, mocker):
        import yaml
        from wp_migration.db import DatabaseError
        cfg = {
            "source": {
                "transport": "ftp",
                "host": "old.com",
                "user": "u",
                "password": "p",
                "remote_path": "/var/www",
                "url": "https://oldsite.com",
            },
            "target": {
                "transport": "ftp",
                "host": "new.com",
                "user": "u",
                "password": "p",
                "remote_path": "/www",
            },
        }
        config_path = tmp_path / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(cfg, f)

        mocker.patch("wp_migration.cli._resolve_source_db_config")
        mocker.patch("wp_migration.cli.dump_database", side_effect=DatabaseError("Can't connect"))
        mock_conn = mocker.MagicMock()
        mocker.patch("wp_migration.cli.connect", return_value=mock_conn)
        mocker.patch("wp_migration.cli.discover_wp_content", return_value=set())
        php_dump = mocker.patch("wp_migration.cli.remote_dump_via_php")

        result = runner.invoke(main, ["export", str(config_path)])
        assert result.exit_code == 0
        php_dump.assert_called_once()

    def test_ssh_fallback_fails_when_no_exec_command(self, runner, sample_config, mocker):
        from wp_migration.db import DatabaseError
        mocker.patch("wp_migration.cli._resolve_source_db_config")
        mocker.patch("wp_migration.cli.dump_database", side_effect=DatabaseError("Can't connect"))
        mock_conn = mocker.MagicMock()
        del mock_conn.exec_command  # no exec_command (simulates FTP connection class)
        mocker.patch("wp_migration.cli.connect", return_value=mock_conn)
        mocker.patch("wp_migration.cli.discover_wp_content", return_value=set())

        result = runner.invoke(main, ["export", sample_config])
        assert result.exit_code != 0
        assert "skip_db" in result.output.lower() or "unreachable" in result.output.lower()

    def test_all_fallbacks_fail_exits_with_error(self, runner, sample_config, mocker):
        from wp_migration.db import DatabaseError
        mocker.patch("wp_migration.cli._resolve_source_db_config")
        mocker.patch("wp_migration.cli.dump_database", side_effect=DatabaseError("Can't connect"))
        mock_conn = mocker.MagicMock()
        mock_conn.exec_command = mocker.MagicMock()
        mocker.patch("wp_migration.cli.connect", return_value=mock_conn)
        mocker.patch("wp_migration.cli.discover_wp_content", return_value=set())
        mocker.patch("wp_migration.cli.remote_dump_via_ssh", side_effect=Exception("SSH failed"))

        result = runner.invoke(main, ["export", sample_config])
        assert result.exit_code != 0

    def test_skip_db_flag_in_config_skips_db_entirely(self, runner, sample_config, mocker):
        dump = mocker.patch("wp_migration.cli.dump_database")
        import yaml
        with open(sample_config) as f:
            cfg = yaml.safe_load(f)
        cfg["options"] = {"skip_db": True}
        with open(sample_config, "w") as f:
            yaml.dump(cfg, f)
        mock_conn = mocker.MagicMock()
        mocker.patch("wp_migration.cli.connect", return_value=mock_conn)
        mocker.patch("wp_migration.cli.discover_wp_content", return_value=set())

        result = runner.invoke(main, ["export", sample_config])
        assert result.exit_code == 0
        dump.assert_not_called()
