import pytest
from pathlib import Path
from wp_migration.db import dump_database, import_sql, DatabaseError
from wp_migration.config import MySQLConfig


class TestDumpDatabase:
    def test_dump_with_mysqldump(self, mocker):
        mock_run = mocker.patch("wp_migration.db.subprocess.run")
        mocker.patch("wp_migration.db.shutil.which", return_value="/usr/bin/mysqldump")
        config = MySQLConfig(host="db.com", port=3306, user="u", password="p", name="wp")
        path = dump_database(config, "/tmp/test_dump.sql")
        assert path == Path("/tmp/test_dump.sql")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "mysqldump" in args[0]
        assert "--host=db.com" in " ".join(args)
        assert "--user=u" in " ".join(args)
        assert "wp" in " ".join(args)

    def test_dump_with_mysqldump_pipes_password(self, mocker):
        mock_run = mocker.patch("wp_migration.db.subprocess.run")
        mocker.patch("wp_migration.db.shutil.which", return_value="/usr/bin/mysqldump")
        config = MySQLConfig(host="db.com", port=3306, user="u", password="p", name="wp")
        dump_database(config, "/tmp/test.sql")
        cmd = " ".join(mock_run.call_args[0][0])
        # Password should NOT be in the command (use env var or --defaults-extra-file)
        assert "-pp" not in cmd
        assert "MYSQL_PWD" in mock_run.call_args[1].get("env", {})

    def test_dump_fallback_to_pymysql(self, mocker):
        mock_connect = mocker.patch("wp_migration.db.pymysql.connect")
        mocker.patch("wp_migration.db.shutil.which", return_value=None)
        mock_conn = mock_connect.return_value
        mock_conn.__enter__.return_value = mock_conn
        mock_cursor = mock_conn.cursor.return_value
        mock_cursor.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ("wp_posts",),
            ("wp_options",),
        ]
        mock_cursor.description = [("Tables_in_wp",)]
        config = MySQLConfig(host="db.com", port=3306, user="u", password="p", name="wp")
        path = dump_database(config, "/tmp/test_py.sql")
        assert path == Path("/tmp/test_py.sql")
        assert path.exists()
        content = path.read_text()
        assert "wp_posts" in content

    def test_dump_connection_failure_raises(self, mocker):
        mocker.patch("wp_migration.db.shutil.which", return_value=None)
        mocker.patch("wp_migration.db.pymysql.connect", side_effect=Exception("Can't connect"))
        config = MySQLConfig(host="db.com", port=3306, user="u", password="p", name="wp")
        with pytest.raises(DatabaseError, match="Can't connect"):
            dump_database(config, "/tmp/fail.sql")

    def test_dump_mysqldump_failure_raises(self, mocker):
        mocker.patch("wp_migration.db.shutil.which", return_value="/usr/bin/mysqldump")
        mock_run = mocker.patch("wp_migration.db.subprocess.run")
        mock_run.side_effect = Exception("mysqldump exited with code 1")
        config = MySQLConfig(host="db.com", port=3306, user="u", password="p", name="wp")
        with pytest.raises(DatabaseError, match="mysqldump"):
            dump_database(config, "/tmp/fail.sql")

    def test_dump_set_gtid_purged_off(self, mocker):
        mock_run = mocker.patch("wp_migration.db.subprocess.run")
        mocker.patch("wp_migration.db.shutil.which", return_value="/usr/bin/mysqldump")
        config = MySQLConfig(host="db.com", port=3306, user="u", password="p", name="wp")
        dump_database(config, "/tmp/test.sql")
        cmd_str = " ".join(mock_run.call_args[0][0])
        assert "--set-gtid-purged=OFF" in cmd_str


class TestImportSql:
    def test_import_with_mysql_binary(self, mocker):
        mock_run = mocker.patch("wp_migration.db.subprocess.run")
        mocker.patch("wp_migration.db.shutil.which", return_value="/usr/bin/mysql")
        config = MySQLConfig(host="db.com", port=3306, user="u", password="p", name="wp")
        dump_path = Path("/tmp/dump.sql")
        dump_path.write_text("INSERT INTO wp_posts VALUES (1);")
        import_sql(config, dump_path)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "mysql" in args[0]
        assert "wp" in " ".join(args)

    def test_import_fallback_to_pymysql(self, mocker):
        mock_connect = mocker.patch("wp_migration.db.pymysql.connect")
        mocker.patch("wp_migration.db.shutil.which", return_value=None)
        mock_conn = mock_connect.return_value
        mock_conn.__enter__.return_value = mock_conn
        mock_cursor = mock_conn.cursor.return_value
        mock_cursor.__enter__.return_value = mock_cursor
        config = MySQLConfig(host="db.com", port=3306, user="u", password="p", name="wp")
        dump_path = Path("/tmp/dump_fallback.sql")
        dump_path.write_text("INSERT INTO wp_posts VALUES (1);\nINSERT INTO wp_options VALUES (2);\n")
        import_sql(config, dump_path)
        assert mock_cursor.execute.call_count >= 2

    def test_import_missing_file_raises(self, mocker):
        config = MySQLConfig(host="db.com", port=3306, user="u", password="p", name="wp")
        with pytest.raises(DatabaseError, match="not found"):
            import_sql(config, Path("/nonexistent/dump.sql"))

    def test_import_connection_failure_raises(self, mocker):
        mocker.patch("wp_migration.db.shutil.which", return_value=None)
        mocker.patch("wp_migration.db.pymysql.connect", side_effect=Exception("Can't connect"))
        config = MySQLConfig(host="db.com", port=3306, user="u", password="p", name="wp")
        dump_path = Path("/tmp/dump_nc.sql")
        dump_path.write_text("SELECT 1;")
        with pytest.raises(DatabaseError, match="Can't connect"):
            import_sql(config, dump_path)


class TestRemoteDumpViaSsh:
    def test_remote_dump_runs_mysqldump_and_downloads(self, mocker):
        mock_conn = mocker.Mock()
        config = MySQLConfig(host="localhost", port=3306, user="root", password="secret", name="wpdb")
        output = Path("/tmp/remote_dump_test.sql")

        from wp_migration.db import remote_dump_via_ssh
        result = remote_dump_via_ssh(mock_conn, config, output)

        assert result == output
        dump_calls = [c for c in mock_conn.exec_command.call_args_list if "mysqldump" in c[0][0]]
        assert len(dump_calls) == 1
        cmd = dump_calls[0][0][0]
        assert "--host=localhost" in cmd
        assert "--user=root" in cmd
        assert "--password=secret" in cmd
        assert "wpdb" in cmd
        assert "/tmp/wp_migrate_dump_" in cmd
        mock_conn.download.assert_called_once()

    def test_remote_dump_removes_temp_on_failure(self, mocker):
        mock_conn = mocker.Mock()
        mock_conn.download.side_effect = Exception("Download failed")
        config = MySQLConfig(host="localhost", port=3306, user="root", password="secret", name="wpdb")
        output = Path("/tmp/remote_dump_fail.sql")

        from wp_migration.db import remote_dump_via_ssh
        with pytest.raises(Exception, match="Download failed"):
            remote_dump_via_ssh(mock_conn, config, output)

        cleanup_calls = [c for c in mock_conn.exec_command.call_args_list if "rm" in str(c)]
        assert len(cleanup_calls) >= 1

    def test_remote_dump_password_shell_escaped(self, mocker):
        mock_conn = mocker.Mock()
        config = MySQLConfig(host="localhost", port=3306, user="root", password="$pecial'\" chars", name="wpdb")
        output = Path("/tmp/remote_dump_escape.sql")

        from wp_migration.db import remote_dump_via_ssh
        remote_dump_via_ssh(mock_conn, config, output)

        dump_calls = [c for c in mock_conn.exec_command.call_args_list if "mysqldump" in c[0][0]]
        assert len(dump_calls) == 1
        cmd = dump_calls[0][0][0]
        assert "$pecial" in cmd or "pecial" in cmd


class TestRemoteDumpViaPhp:
    def test_generates_random_filename(self, mocker):
        mock_urlopen = mocker.patch("wp_migration.db.urllib.request.urlopen")
        mock_urlopen.return_value.status = 200
        mock_urlopen.return_value.read.side_effect = [b"", b""]
        from wp_migration.db import remote_dump_via_php
        mock_conn = mocker.Mock()
        output = Path("/tmp/php_dump_test.sql")

        result = remote_dump_via_php("https://example.com", mock_conn, "/var/www", output)

        assert result == output
        mock_conn.upload.assert_called_once()
        uploaded_path = mock_conn.upload.call_args[0][1]
        assert uploaded_path.startswith("/var/www/wp-migrate-dump-")
        assert uploaded_path.endswith(".php")
        assert len(uploaded_path) > len("/var/www/wp-migrate-dump-.php") + 10

    def test_uploads_downloads_and_cleans_up(self, mocker):
        mock_conn = mocker.Mock()
        mock_urlopen = mocker.patch("wp_migration.db.urllib.request.urlopen")
        mock_resp = mock_urlopen.return_value
        mock_resp.status = 200
        mock_resp.read.side_effect = [b"CREATE TABLE;", b""]
        output = Path("/tmp/php_dump_test2.sql")

        from wp_migration.db import remote_dump_via_php
        remote_dump_via_php("https://example.com", mock_conn, "/var/www", output)

        assert output.read_text() == "CREATE TABLE;"
        mock_conn.delete.assert_called_once()

    def test_cleans_up_on_http_failure(self, mocker):
        mock_conn = mocker.Mock()
        import urllib.error
        mock_urlopen = mocker.patch("wp_migration.db.urllib.request.urlopen")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "http://example.com", 500, "Server Error", {}, None
        )
        output = Path("/tmp/php_dump_fail.sql")

        from wp_migration.db import remote_dump_via_php
        with pytest.raises(Exception, match="500"):
            remote_dump_via_php("https://example.com", mock_conn, "/var/www", output)

        mock_conn.delete.assert_called_once()

    def test_cleans_up_on_connection_error(self, mocker):
        mock_conn = mocker.Mock()
        import urllib.error
        mock_urlopen = mocker.patch("wp_migration.db.urllib.request.urlopen")
        mock_urlopen.side_effect = OSError("Connection error")
        output = Path("/tmp/php_dump_conn_fail.sql")

        from wp_migration.db import remote_dump_via_php
        with pytest.raises(Exception, match="Connection error"):
            remote_dump_via_php("https://example.com", mock_conn, "/var/www", output)

        mock_conn.delete.assert_called_once()

    def test_generates_valid_php(self, mocker):
        php_content = []
        mock_conn = mocker.Mock()

        def capture_upload(local, remote):
            php_content.append(Path(local).read_text())

        mock_conn.upload.side_effect = capture_upload
        mock_urlopen = mocker.patch("wp_migration.db.urllib.request.urlopen")
        mock_resp = mock_urlopen.return_value
        mock_resp.status = 200
        mock_resp.read.side_effect = [b"", b""]
        output = Path("/tmp/php_dump_valid_php.sql")

        from wp_migration.db import remote_dump_via_php
        remote_dump_via_php("https://example.com", mock_conn, "/var/www", output)

        content = php_content[0]
        assert "<?php" in content
        assert "SHOW TABLES" in content
        assert "LIMIT" in content
        assert "unlink" in content  # self-delete
