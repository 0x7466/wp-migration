# AGENTS.md

## Project

WordPress migration tool (Python). Transfers a site between hosts via SFTP/FTP/SCP for files and direct MySQL connection for the database.

## Setup

```bash
pip install -e ".[dev]"
```

## Test commands

```bash
python -m pytest              # 114+ unit tests
python -m pytest -v           # verbose
python -m pytest -k "test_name"  # single test
```

Integration tests (require Docker):

```bash
cd test/
docker compose up -d --build
python -m pytest tests/test_integration.py -v
docker compose down -v
```

## Code style

- Python 3.11+, no type annotations required but preferred
- f-strings over `.format()` or `%`
- Exceptions: custom exception classes per module (e.g. `DatabaseError`, `TransportError`)
- Tests: strict TDD — write test first, implement after. Use `pytest-mock` for I/O mocking
- Config: typed dataclasses with `__post_init__` validation
- No comments unless explaining a non-obvious edge case

## Key architecture

| Module | Purpose |
|---|---|
| `wp_config.py` | Parse `wp-config.php`, discover in parent dir |
| `replace.py` | Serialization-safe URL replace (byte-level) |
| `config.py` | YAML → dataclasses with validation |
| `transport.py` | FTP/SFTP/SCP unified interface |
| `db.py` | mysqldump CLI or pymysql fallback |
| `files.py` | Recursive wp-content transfer with MD5 resume |
| `cli.py` | Click-based CLI (`run`, `export`, `import`) |

## Gotchas

- `replace.py` works in UTF-8 bytes to match PHP serialization's byte-length semantics. Use `rb''` for regex patterns on serialized headers.
- `mysqldump` SQL-escapes double quotes (`\"`) inside VALUES. The replace module handles both `s:N:"` and `s:N:\"` patterns.
- pymysql dump fallback generates `CREATE TABLE` via `SHOW CREATE TABLE` then `INSERT`s. Statement-by-statement import splits on `;` at line boundaries.
- MySQL SQL mode may need relaxation for strict default-value checks. See `SET GLOBAL sql_mode = '...'`.
- WordPress allows `wp-config.php` one directory above the web root.
