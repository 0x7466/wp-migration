import pytest
from pathlib import Path
from unittest.mock import MagicMock, call
from wp_migration.files import discover_wp_content, transfer_files


class TestDiscoverWpContent:
    def test_discover_uploads_themes_plugins(self):
        conn = MagicMock()
        conn.list.side_effect = lambda p: {
            "/var/www/wp-content": ["plugins/", "themes/", "uploads/"],
            "/var/www/wp-content/plugins": [],
            "/var/www/wp-content/themes": [],
            "/var/www/wp-content/uploads": [],
        }.get(p, [])
        result = discover_wp_content("/var/www/wp-content", conn)
        assert "uploads" in result
        assert "themes" in result
        assert "plugins" in result

    def test_discover_skips_cache_and_upgrade(self):
        conn = MagicMock()
        conn.list.side_effect = lambda p: {
            "/var/www/wp-content": ["uploads/", "cache/", "upgrade/", "backup/", "plugins/"],
            "/var/www/wp-content/uploads": [],
            "/var/www/wp-content/plugins": [],
        }.get(p, [])
        result = discover_wp_content("/var/www/wp-content", conn)
        assert "cache" not in result
        assert "upgrade" not in result
        assert "backup" not in result
        assert "uploads" in result
        assert "plugins" in result

    def test_discover_only_uploads(self):
        conn = MagicMock()
        conn.list.side_effect = lambda p: {
            "/var/www/wp-content": ["uploads/"],
            "/var/www/wp-content/uploads": [],
        }.get(p, [])
        result = discover_wp_content("/var/www/wp-content", conn)
        assert result == {"uploads"}

    def test_discover_returns_set(self):
        conn = MagicMock()
        conn.list.side_effect = lambda p: {
            "/var/www/wp-content": ["uploads/", "themes/"],
            "/var/www/wp-content/uploads": [],
            "/var/www/wp-content/themes": [],
        }.get(p, [])
        result = discover_wp_content("/var/www/wp-content", conn)
        assert isinstance(result, set)

    def test_discover_empty_dir(self):
        conn = MagicMock()
        conn.list.return_value = []
        result = discover_wp_content("/var/www/wp-content", conn)
        assert result == set()

    def test_discover_lists_correct_path(self):
        conn = MagicMock()
        conn.list.side_effect = lambda p: {
            "/custom/path/wp-content": ["uploads/"],
            "/custom/path/wp-content/uploads": [],
        }.get(p, [])
        discover_wp_content("/custom/path/wp-content", conn)
        conn.list.assert_any_call("/custom/path/wp-content")

    def test_discover_skips_files(self):
        conn = MagicMock()

        def side_effect(path):
            mapping = {
                "/var/www/wp-content": ["index.php", "uploads/", "themes/"],
                "/var/www/wp-content/uploads": [],
                "/var/www/wp-content/themes": [],
                "/var/www/wp-content/index.php": FileNotFoundError,
            }
            if path in mapping and isinstance(mapping[path], list):
                return mapping[path]
            if path in mapping and mapping[path] is FileNotFoundError:
                raise FileNotFoundError(f"Not a directory: {path}")
            return []

        conn.list.side_effect = side_effect
        result = discover_wp_content("/var/www/wp-content", conn)
        assert "index.php" not in result
        assert "themes" in result


class TestTransferFiles:
    def test_transfer_downloads_and_upload(self, tmp_path):
        source = MagicMock()
        target = MagicMock()
        source.list.return_value = ["img.jpg"]

        def fake_download(remote, local):
            Path(local).parent.mkdir(parents=True, exist_ok=True)
            Path(local).write_bytes(b"fake image data")

        source.download.side_effect = fake_download
        result = transfer_files(source, target, "uploads", str(tmp_path), {})
        source.download.assert_called_once()
        target.upload.assert_called_once()
        assert "img.jpg" in result

    def test_transfer_skips_when_checksum_matches(self, tmp_path):
        source = MagicMock()
        target = MagicMock()
        source.list.return_value = ["img.jpg"]
        local_file = tmp_path / "uploads" / "img.jpg"
        local_file.parent.mkdir(parents=True, exist_ok=True)
        local_file.write_bytes(b"data")
        import hashlib
        cksum = hashlib.md5(b"data").hexdigest()
        result = transfer_files(source, target, "uploads", str(tmp_path), {"img.jpg": cksum})
        source.download.assert_not_called()
        assert result == {"img.jpg": cksum}

    def test_transfer_re_downloads_when_checksum_mismatch(self, tmp_path):
        source = MagicMock()
        target = MagicMock()
        source.list.return_value = ["img.jpg"]

        def fake_download(remote, local):
            Path(local).parent.mkdir(parents=True, exist_ok=True)
            Path(local).write_bytes(b"new data")

        source.download.side_effect = fake_download
        result = transfer_files(source, target, "uploads", str(tmp_path), {"img.jpg": "wrong_checksum"})
        source.download.assert_called()

    def test_transfer_empty_directory(self, tmp_path):
        source = MagicMock()
        target = MagicMock()
        source.list.return_value = []
        result = transfer_files(source, target, "empty_dir", str(tmp_path), {})
        assert result == {}
