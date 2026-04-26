import pytest
from wp_migration.replace import replace_in_string, replace_in_sql


class TestReplaceInString:
    def test_plain_string_no_serialization(self):
        result = replace_in_string(
            "http://oldsite.com/page",
            "http://oldsite.com",
            "https://newsite.com",
        )
        assert result == "https://newsite.com/page"

    def test_plain_string_no_match(self):
        result = replace_in_string("hello world", "xyz", "abc")
        assert result == "hello world"

    def test_serialized_string_same_length(self):
        s = 's:23:"http://oldsite.com/menu";'
        result = replace_in_string(s, "http://oldsite.com", "https://newsite.com")
        assert result == 's:24:"https://newsite.com/menu";'

    def test_serialized_string_longer_url(self):
        s = 's:18:"http://oldsite.com";'
        result = replace_in_string(s, "http://oldsite.com", "https://longer-site.com")
        assert result == 's:23:"https://longer-site.com";'

    def test_serialized_string_shorter_url(self):
        old = "https://longsite.com"
        new = "http://short.com"
        input_str = 's:22:"https://longsite.com/p";'
        result = replace_in_string(input_str, old, new)
        assert result == 's:18:"http://short.com/p";'

    def test_nested_serialized_array(self):
        s = 'a:2:{s:4:"link";s:18:"http://oldsite.com";s:3:"key";s:18:"http://oldsite.com";}'
        result = replace_in_string(s, "http://oldsite.com", "https://newsite.com")
        expected = 'a:2:{s:4:"link";s:19:"https://newsite.com";s:3:"key";s:19:"https://newsite.com";}'
        assert result == expected

    def test_serialized_object(self):
        s = 'O:8:"stdClass":1:{s:4:"site";s:18:"http://oldsite.com";}'
        result = replace_in_string(s, "http://oldsite.com", "https://newsite.com")
        expected = 'O:8:"stdClass":1:{s:4:"site";s:19:"https://newsite.com";}'
        assert result == expected

    def test_no_change_serialized_data_no_match(self):
        s = 's:11:"hello world";'
        result = replace_in_string(s, "xyz", "abc")
        assert result == s

    def test_url_in_serialized_length_value_itself(self):
        s = 's:14:"something else";'
        result = replace_in_string(s, "14", "99")
        assert result == s

    def test_multiple_serialized_values_same_line(self):
        s = 's:10:"oldsite.com";s:18:"http://oldsite.com";'
        result = replace_in_string(s, "http://oldsite.com", "https://newsite.com")
        assert result == 's:10:"oldsite.com";s:19:"https://newsite.com";'

    def test_serialized_string_with_special_chars(self):
        s = 's:31:"http://oldsite.com/path?q=1&r=2";'
        result = replace_in_string(s, "http://oldsite.com", "https://newsite.com")
        assert result == 's:32:"https://newsite.com/path?q=1&r=2";'

    def test_serialized_string_unicode(self):
        s = 's:24:"http://oldsite.com/café";'
        result = replace_in_string(s, "http://oldsite.com", "https://newsite.com")
        assert result == 's:25:"https://newsite.com/café";'

    def test_empty_string(self):
        assert replace_in_string("", "old", "new") == ""

    def test_replace_https_to_http(self):
        s = 's:19:"https://big.com/img";'
        result = replace_in_string(s, "https://big.com", "http://tiny.co")
        assert result == 's:18:"http://tiny.co/img";'


class TestReplaceInSql:
    def test_replace_in_sql_dump(self):
        sql = (
            "INSERT INTO wp_options (option_value) VALUES ('s:18:\"http://oldsite.com\";');\n"
            "INSERT INTO wp_posts (guid) VALUES ('http://oldsite.com/hello-world');\n"
        )
        result = replace_in_sql(sql, "http://oldsite.com", "https://newsite.com")
        assert "https://newsite.com" in result
        assert "http://oldsite.com" not in result

    def test_replace_in_sql_preserves_non_url_content(self):
        sql = (
            "INSERT INTO wp_options (option_value) VALUES ('s:18:\"http://oldsite.com\";');\n"
            "INSERT INTO wp_posts (post_content) VALUES ('<a href=\"/relative\">link</a>');\n"
        )
        result = replace_in_sql(sql, "http://oldsite.com", "https://newsite.com")
        assert "/relative" in result
        assert 's:19:"https://newsite.com"' in result

    def test_replace_in_sql_empty(self):
        assert replace_in_sql("", "old", "new") == ""

    def test_replace_in_sql_no_match(self):
        sql = "INSERT INTO wp_posts (title) VALUES ('hello');"
        assert replace_in_sql(sql, "xyz", "abc") == sql

    def test_replace_in_sql_large_serialized_array(self):
        old_url = "http://oldsite.com"
        new_url = "https://newsite.com"
        serialized = 'a:3:{s:4:"url1";s:20:"http://oldsite.com/a";s:4:"url2";s:20:"http://oldsite.com/b";s:4:"url3";s:20:"http://oldsite.com/c";}'
        sql = f"INSERT INTO wp_options (option_value) VALUES ('{serialized}');\n"
        result = replace_in_sql(sql, old_url, new_url)
        assert 's:21:"https://newsite.com/a"' in result
        assert 's:21:"https://newsite.com/b"' in result
        assert 's:21:"https://newsite.com/c"' in result

    def test_replace_in_sql_url_in_plain_text_lines(self):
        sql = (
            "INSERT INTO wp_posts (guid) VALUES ('http://oldsite.com/page1');\n"
            "INSERT INTO wp_posts (guid) VALUES ('http://oldsite.com/page2');\n"
        )
        result = replace_in_sql(sql, "http://oldsite.com", "https://newsite.com")
        assert result.count("https://newsite.com") == 2
        assert "http://oldsite.com" not in result

    def test_replace_in_sql_serialized_array_with_old_url(self):
        serialized = 'a:1:{s:3:"url";s:29:"http://oldsite.com/some-page/";}'
        sql = f"INSERT INTO wp_options (option_name, option_value) VALUES ('my_option', '{serialized}');"
        result = replace_in_sql(sql, "http://oldsite.com", "https://newsite.com")
        assert 's:30:"https://newsite.com/some-page/"' in result
