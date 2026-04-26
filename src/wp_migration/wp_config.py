import re
from pathlib import Path


DB_CONSTANTS = frozenset({"DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST"})


def parse_wp_config(php_content: str) -> dict[str, str]:
    result = {}
    for line in php_content.splitlines():
        line = line.strip()
        m = re.match(
            r"""define\s*\(\s*['"](DB_NAME|DB_USER|DB_PASSWORD|DB_HOST)['"]\s*,\s*['"]([^'"]*)['"]\s*\)\s*;""",
            line,
        )
        if m:
            result[m.group(1)] = m.group(2)
            continue
        m = re.match(r"""\$table_prefix\s*=\s*['"]([^'"]*)['"]\s*;""", line)
        if m:
            result["table_prefix"] = m.group(1)
    return result


def discover_wp_config(remote_path: str, conn) -> str:
    candidates = [
        f"{remote_path.rstrip('/')}/wp-config.php",
        f"{str(Path(remote_path).parent)}/wp-config.php",
    ]
    for candidate in candidates:
        if conn.exists(candidate):
            return candidate
    raise FileNotFoundError("wp-config.php not found in remote path or parent directory")
