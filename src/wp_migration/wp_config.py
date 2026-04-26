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
        remote_path.rstrip("/"),
        str(Path(remote_path).parent),
    ]
    for candidate in candidates:
        if conn.exists(f"{candidate}/wp-config.php"):
            return f"{candidate}/wp-config.php"

    detail_parts = [f"  Searched: {p}/wp-config.php" for p in candidates]
    for p in candidates:
        try:
            entries = conn.list(p)
            detail_parts.append(f"  Files in {p}: {', '.join(entries[:15])}")
            if len(entries) > 15:
                detail_parts[-1] += f" … and {len(entries) - 15} more"
        except Exception:
            detail_parts.append(f"  Could not list: {p}")

    raise FileNotFoundError(
        "wp-config.php not found.\n"
        + "\n".join(detail_parts)
        + "\n\n  Possible causes:"
        + "\n    - remote_path in config points to wrong directory"
        + "\n    - WordPress files are not uploaded yet"
        + "\n    - insufficient permissions to list files"
        + "\n    - wp-config.php was renamed or removed"
    )
