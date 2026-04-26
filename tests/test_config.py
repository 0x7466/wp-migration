import pytest
import yaml
from pathlib import Path
from wp_migration.config import MigrationConfig, load_config, HostConfig, MySQLConfig


class TestMySQLConfig:
    def test_default_port_is_3306(self):
        c = MySQLConfig(host="db.com", user="u", password="p", name="n")
        assert c.port == 3306

    def test_custom_port(self):
        c = MySQLConfig(host="db.com", port=3307, user="u", password="p", name="n")
        assert c.port == 3307

    def test_dsn_populated(self):
        c = MySQLConfig(host="db.com", user="u", password="p", name="n")
        assert c.dsn.host == "db.com"
        assert c.dsn.port == 3306
        assert c.dsn.user == "u"
        assert c.dsn.password == "p"
        assert c.dsn.dbname == "n"


class TestHostConfig:
    def test_default_port_ftp(self):
        c = HostConfig(transport="ftp", host="h.com", user="u", password="p", remote_path="/var/www")
        assert c.port == 21

    def test_default_port_sftp(self):
        c = HostConfig(transport="sftp", host="h.com", user="u", password="p", remote_path="/var/www")
        assert c.port == 22

    def test_default_port_scp(self):
        c = HostConfig(transport="scp", host="h.com", user="u", password="p", remote_path="/var/www")
        assert c.port == 22

    def test_custom_port(self):
        c = HostConfig(transport="sftp", host="h.com", port=2222, user="u", password="p", remote_path="/var/www")
        assert c.port == 2222

    def test_invalid_transport_raises(self):
        with pytest.raises(ValueError, match="transport"):
            HostConfig(transport="http", host="h.com", user="u", password="p", remote_path="/")


class TestMigrationConfig:
    def test_minimal_valid_config(self):
        config = MigrationConfig(
            source=HostConfig(transport="sftp", host="old.com", user="u", password="p", remote_path="/var/www"),
            target=HostConfig(transport="ftp", host="new.com", user="u", password="p", remote_path="/www"),
        )
        assert config.options.wp_content_only is True
        assert config.options.skip_uploads is False
        assert config.options.dry_run is False
        assert config.options.resume is True

    def test_custom_options(self):
        config = MigrationConfig(
            source=HostConfig(transport="sftp", host="old.com", user="u", password="p", remote_path="/var/www"),
            target=HostConfig(transport="ftp", host="new.com", user="u", password="p", remote_path="/www"),
            options={"wp_content_only": False, "dry_run": True},
        )
        assert config.options.wp_content_only is False
        assert config.options.dry_run is True
        assert config.options.skip_uploads is False
        assert config.options.resume is True

    def test_skip_db_option(self):
        config = MigrationConfig(
            source=HostConfig(transport="sftp", host="old.com", user="u", password="p", remote_path="/var/www"),
            target=HostConfig(transport="ftp", host="new.com", user="u", password="p", remote_path="/www"),
            options={"skip_db": True},
        )
        assert config.options.skip_db is True

    def test_skip_db_defaults_false(self):
        config = MigrationConfig(
            source=HostConfig(transport="sftp", host="old.com", user="u", password="p", remote_path="/var/www"),
            target=HostConfig(transport="ftp", host="new.com", user="u", password="p", remote_path="/www"),
        )
        assert config.options.skip_db is False

    def test_skip_db_loaded_from_yaml(self, tmp_path):
        yml = {
            "source": {"transport": "sftp", "host": "old.com", "user": "u", "password": "p", "remote_path": "/var/www"},
            "target": {"transport": "ftp", "host": "new.com", "user": "u", "password": "p", "remote_path": "/www"},
            "options": {"skip_db": True},
        }
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            import yaml
            yaml.dump(yml, f)
        from wp_migration.config import load_config
        cfg = load_config(str(path))
        assert cfg.options.skip_db is True

    def test_source_with_mysql_override(self):
        config = MigrationConfig(
            source=HostConfig(
                transport="sftp", host="old.com", user="u", password="p",
                remote_path="/var/www",
                mysql=MySQLConfig(host="db.com", user="u", password="p", name="wp"),
            ),
            target=HostConfig(transport="ftp", host="new.com", user="u", password="p", remote_path="/www"),
        )
        assert config.source.mysql.host == "db.com"


class TestLoadConfig:
    def test_load_valid_yaml(self, tmp_path):
        yml = {
            "source": {"transport": "sftp", "host": "old.com", "user": "u", "password": "p", "remote_path": "/var/www"},
            "target": {
                "transport": "ftp", "host": "new.com", "user": "u", "password": "p", "remote_path": "/www",
                "mysql": {"host": "db.com", "user": "u", "password": "p", "name": "wp"},
                "url": "https://newsite.com",
            },
        }
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(yml, f)

        config = load_config(path)
        assert config.source.transport == "sftp"
        assert config.target.mysql.host == "db.com"
        assert config.target.url == "https://newsite.com"

    def test_load_minimal_yaml(self, tmp_path):
        yml = {
            "source": {"transport": "sftp", "host": "old.com", "user": "u", "password": "p", "remote_path": "/var/www"},
            "target": {"transport": "ftp", "host": "new.com", "user": "u", "password": "p", "remote_path": "/www"},
        }
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(yml, f)

        config = load_config(path)
        assert config.target.url is None
        assert config.options.wp_content_only is True

    def test_load_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config(Path("/nonexistent/config.yaml"))

    def test_load_missing_source_raises(self, tmp_path):
        yml = {"target": {"transport": "sftp", "host": "new.com", "user": "u", "password": "p", "remote_path": "/www"}}
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(yml, f)
        with pytest.raises(ValueError, match="source"):
            load_config(path)

    def test_load_missing_target_raises(self, tmp_path):
        yml = {"source": {"transport": "sftp", "host": "old.com", "user": "u", "password": "p", "remote_path": "/var/www"}}
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(yml, f)
        with pytest.raises(ValueError, match="target"):
            load_config(path)

    def test_load_source_missing_transport_raises(self, tmp_path):
        yml = {"source": {"host": "old.com", "user": "u", "password": "p", "remote_path": "/var/www"},
               "target": {"transport": "ftp", "host": "new.com", "user": "u", "password": "p", "remote_path": "/www"}}
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(yml, f)
        with pytest.raises(ValueError, match="transport"):
            load_config(path)
