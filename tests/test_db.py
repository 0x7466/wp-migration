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
