import pytest
from wp_migration.wp_config import parse_wp_config, discover_wp_config


class TestParseWpConfig:
    def test_parse_basic_defines(self):
        php = """<?php
define('DB_NAME', 'wordpress_db');
define('DB_USER', 'admin_user');
define('DB_PASSWORD', 'secret123');
define('DB_HOST', 'localhost');
$table_prefix = 'wp_';
"""
        result = parse_wp_config(php)
        assert result["DB_NAME"] == "wordpress_db"
        assert result["DB_USER"] == "admin_user"
        assert result["DB_PASSWORD"] == "secret123"
        assert result["DB_HOST"] == "localhost"
        assert result["table_prefix"] == "wp_"

    def test_parse_double_quotes(self):
        php = '''<?php
define("DB_NAME", "my_db");
define("DB_USER", "my_user");
'''
        result = parse_wp_config(php)
        assert result["DB_NAME"] == "my_db"
        assert result["DB_USER"] == "my_user"

    def test_parse_with_comments_and_whitespace(self):
        php = """<?php
// Database settings
define('DB_NAME', 'test_db'); // the db name
/* Multi
   line */
define('DB_USER', 'test_user');
"""
        result = parse_wp_config(php)
        assert result["DB_NAME"] == "test_db"
        assert result["DB_USER"] == "test_user"

    def test_parse_mixed_quotes(self):
        php = """<?php
define('DB_NAME', "mixed_quotes");
define("DB_USER", 'another_user');
"""
        result = parse_wp_config(php)
        assert result["DB_NAME"] == "mixed_quotes"
        assert result["DB_USER"] == "another_user"

    def test_parse_db_host_with_port(self):
        php = """<?php
define('DB_HOST', 'db.example.com:3307');
"""
        result = parse_wp_config(php)
        assert result["DB_HOST"] == "db.example.com:3307"

    def test_parse_table_prefix_variable(self):
        php = """<?php
$table_prefix = 'wp_42_';
"""
        result = parse_wp_config(php)
        assert result["table_prefix"] == "wp_42_"

    def test_parse_table_prefix_double_quotes(self):
        php = '''<?php
$table_prefix = "custom_";
'''
        result = parse_wp_config(php)
        assert result["table_prefix"] == "custom_"

    def test_parse_empty_php(self):
        assert parse_wp_config("") == {}
        assert parse_wp_config("<?php\n// nothing here") == {}

    def test_parse_no_constants_defined(self):
        php = """<?php
// Just a comment
$some_var = 'hello';
"""
        result = parse_wp_config(php)
        assert result == {}

    def test_parse_defines_with_variable_expressions(self):
        php = """<?php
define('DB_NAME', 'db_' . 'name');
"""
        result = parse_wp_config(php)
        assert result.get("DB_NAME") is None  # we don't eval expressions

    def test_parse_values_with_special_characters(self):
        php = """<?php
define('DB_PASSWORD', 'p@$$w0rd!');
define('DB_NAME', "db-with-dashes");
"""
        result = parse_wp_config(php)
        assert result["DB_PASSWORD"] == "p@$$w0rd!"
        assert result["DB_NAME"] == "db-with-dashes"

    def test_parse_with_full_wp_config(self):
        php = """<?php
/**
 * The base configuration for WordPress
 */
define('DB_NAME', 'wordpress');
define('DB_USER', 'root');
define('DB_PASSWORD', 'password');
define('DB_HOST', 'localhost');
define('DB_CHARSET', 'utf8');
define('DB_COLLATE', '');

$table_prefix = 'wp_';

define('WP_DEBUG', false);

if ( !defined('ABSPATH') )
    define('ABSPATH', dirname(__FILE__) . '/');
"""
        result = parse_wp_config(php)
        assert result["DB_NAME"] == "wordpress"
        assert result["DB_USER"] == "root"
        assert result["DB_PASSWORD"] == "password"
        assert result["DB_HOST"] == "localhost"
        assert result["table_prefix"] == "wp_"
        # Non-DB constants should be ignored in output
        assert "WP_DEBUG" not in result
        assert "ABSPATH" not in result


class TestDiscoverWpConfig:
    def test_discover_returns_path_when_found_in_root(self):
        class FakeConn:
            def exists(self, path):
                return path == "/var/www/wp-config.php"

        result = discover_wp_config("/var/www", FakeConn())
        assert result == "/var/www/wp-config.php"

    def test_discover_returns_path_when_found_in_parent(self):
        class FakeConn:
            def exists(self, path):
                return path == "/var/www/wp-config.php"

        result = discover_wp_config("/var/www/html", FakeConn())
        assert result == "/var/www/wp-config.php"

    def test_discover_raises_when_not_found(self):
        class FakeConn:
            def exists(self, path):
                return False
            def list(self, path):
                return ["index.php", "wp-content/"]

        with pytest.raises(FileNotFoundError, match="wp-config.php"):
            discover_wp_config("/var/www", FakeConn())

    def test_discover_error_includes_file_listing(self):
        class FakeConn:
            def exists(self, path):
                return False
            def list(self, path):
                return ["index.php", "wp-content/"]

        with pytest.raises(FileNotFoundError) as exc:
            discover_wp_config("/var/www", FakeConn())
        msg = str(exc.value)
        assert "index.php" in msg
        assert "wp-content" in msg
        assert "remote_path" in msg

    def test_discover_tries_root_first_then_parent(self):
        paths_tried = []

        class FakeConn:
            def exists(self, path):
                paths_tried.append(path)
                return False
            def list(self, path):
                return []

        with pytest.raises(FileNotFoundError):
            discover_wp_config("/var/www/html", FakeConn())

        assert paths_tried[0] == "/var/www/html/wp-config.php"
        assert paths_tried[1] == "/var/www/wp-config.php"

    def test_discover_root_has_priority_over_parent(self):
        class FakeConn:
            def exists(self, path):
                if path == "/var/www/wp-config.php":
                    return True
                return False

        result = discover_wp_config("/var/www", FakeConn())
        assert result == "/var/www/wp-config.php"

    def test_discover_strips_trailing_slash(self):
        class FakeConn:
            def exists(self, path):
                return path == "/var/www/wp-config.php"

        result = discover_wp_config("/var/www/", FakeConn())
        assert result == "/var/www/wp-config.php"

    def test_discover_returns_path_when_found_in_parent(self):
        class FakeConn:
            def exists(self, path):
                return path == "/var/www/wp-config.php"

        result = discover_wp_config("/var/www/html", FakeConn())
        assert result == "/var/www/wp-config.php"

    def test_discover_raises_when_not_found(self):
        class FakeConn:
            def exists(self, path):
                return False
            def list(self, path):
                return ["index.php", "wp-content/"]

        with pytest.raises(FileNotFoundError, match="wp-config.php"):
            discover_wp_config("/var/www", FakeConn())

    def test_discover_error_includes_file_listing(self):
        class FakeConn:
            def exists(self, path):
                return False
            def list(self, path):
                return ["index.php", "wp-content/"]

        with pytest.raises(FileNotFoundError) as exc:
            discover_wp_config("/var/www", FakeConn())
        msg = str(exc.value)
        assert "index.php" in msg
        assert "wp-content" in msg
        assert "remote_path" in msg

    def test_discover_tries_root_first_then_parent(self):
        paths_tried = []

        class FakeConn:
            def exists(self, path):
                paths_tried.append(path)
                return False
            def list(self, path):
                return []

        with pytest.raises(FileNotFoundError):
            discover_wp_config("/var/www/html", FakeConn())

        assert paths_tried[0] == "/var/www/html/wp-config.php"
        assert paths_tried[1] == "/var/www/wp-config.php"

    def test_discover_root_has_priority_over_parent(self):
        class FakeConn:
            def exists(self, path):
                if path == "/var/www/wp-config.php":
                    return True
                if path == "/var/wp-config.php":
                    return False
                return False

        result = discover_wp_config("/var/www", FakeConn())
        assert result == "/var/www/wp-config.php"

    def test_discover_strips_trailing_slash(self):
        class FakeConn:
            def exists(self, path):
                return path == "/var/www/wp-config.php"

        result = discover_wp_config("/var/www/", FakeConn())
        assert result == "/var/www/wp-config.php"
