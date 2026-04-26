import subprocess
from pathlib import Path
import pytest

from wp_migration.db import dump_database, import_sql
from wp_migration.replace import replace_in_sql
from wp_migration.config import MySQLConfig


def _docker_container_running(name):
    try:
        r = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0 and r.stdout.strip() == "true"
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _docker_container_running("wp_migrate_test"),
    reason="Requires running Docker container 'wp_migrate_test' with MySQL",
)

SOURCE_DB = "wp_test"
TARGET_DB = "wp_target"
MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "port": 33060,
    "user": "wp_user",
    "password": "wp_pass",
}


@pytest.fixture(scope="module")
def setup_databases():
    subprocess.run(
        ["docker", "exec", "wp_migrate_test", "mysql", "-u", "root", "-proot",
         "-e", f"DROP DATABASE IF EXISTS {TARGET_DB}; CREATE DATABASE {TARGET_DB}; GRANT ALL ON {TARGET_DB}.* TO 'wp_user'@'%'; FLUSH PRIVILEGES;"],
        check=True,
    )
    yield
    subprocess.run(
        ["docker", "exec", "wp_migrate_test", "mysql", "-u", "root", "-proot",
         "-e", f"DROP DATABASE IF EXISTS {TARGET_DB};"],
        check=False,
    )


@pytest.fixture(scope="module")
def seed_source_db(setup_databases):
    subprocess.run(
        ["docker", "exec", "-i", "wp_migrate_test", "mysql", "-u", "wp_user", "-pwp_pass", SOURCE_DB],
        input="""DROP TABLE IF EXISTS wp_options, wp_posts, wp_postmeta;
        CREATE TABLE wp_options (
            option_id INT AUTO_INCREMENT PRIMARY KEY,
            option_name VARCHAR(255),
            option_value LONGTEXT
        );
        INSERT INTO wp_options (option_name, option_value) VALUES
        ('siteurl', 'http://oldsite.com'),
        ('home', 'http://oldsite.com'),
        ('blogname', 'My Old Site');
        CREATE TABLE wp_posts (
            ID INT AUTO_INCREMENT PRIMARY KEY,
            post_title TEXT,
            guid VARCHAR(255)
        );
        INSERT INTO wp_posts (post_title, guid) VALUES
        ('Hello World', 'http://oldsite.com/hello-world'),
        ('About', 'http://oldsite.com/about');
        CREATE TABLE wp_postmeta (
            meta_id INT AUTO_INCREMENT PRIMARY KEY,
            post_id INT,
            meta_key VARCHAR(255),
            meta_value LONGTEXT
        );
        INSERT INTO wp_postmeta (post_id, meta_key, meta_value) VALUES
        (1, '_wp_attached_file', 's:18:\"http://oldsite.com\";');""".encode(),
        check=True,
    )
    yield


class TestFullMigration:
    def test_dump_and_replace_and_import(self, setup_databases, seed_source_db, tmp_path):
        source_config = MySQLConfig(
            host=MYSQL_CONFIG["host"],
            port=MYSQL_CONFIG["port"],
            user=MYSQL_CONFIG["user"],
            password=MYSQL_CONFIG["password"],
            name=SOURCE_DB,
        )
        target_config = MySQLConfig(
            host=MYSQL_CONFIG["host"],
            port=MYSQL_CONFIG["port"],
            user=MYSQL_CONFIG["user"],
            password=MYSQL_CONFIG["password"],
            name=TARGET_DB,
        )

        dump_path = tmp_path / "dump.sql"

        # Step 1: Dump source database
        result = dump_database(source_config, str(dump_path))
        assert result.exists()
        sql = dump_path.read_text()
        assert "wp_options" in sql
        assert "http://oldsite.com" in sql

        # Step 2: Replace old URL with new URL
        replaced = replace_in_sql(sql, "http://oldsite.com", "https://newsite.com")
        replaced_path = tmp_path / "dump_replaced.sql"
        replaced_path.write_text(replaced)
        assert "https://newsite.com" in replaced, f"New URL not found in replaced SQL:\n{replaced[:2000]}"
        assert "http://oldsite.com" not in replaced, f"Old URL still present in replaced SQL:\n{replaced[:2000]}"

        # Verify serialized string length was updated
        assert 's:19:"https://newsite.com"' in replaced

        assert "CREATE TABLE" in replaced, f"No CREATE TABLE in replaced SQL:\n{replaced[:500]}"

        # Step 3: Import into target database via mysql CLI
        import subprocess as sp
        with replaced_path.open("rb") as f:
            sp.run(
                ["docker", "exec", "-i", "wp_migrate_test", "mysql", "-u", "wp_user", "-pwp_pass", TARGET_DB],
                stdin=f, check=True, capture_output=True,
            )

        # Step 4: Verify import
        result = sp.run(
            ["docker", "exec", "wp_migrate_test", "mysql", "-u", "wp_user", "-pwp_pass", "-N", "-B",
             "-e", "SELECT option_value FROM wp_options WHERE option_name='siteurl'", TARGET_DB],
            capture_output=True, text=True,
        )
        assert "https://newsite.com" in result.stdout.strip()
        assert "http://oldsite.com" not in result.stdout.strip()
