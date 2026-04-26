# Roadmap

Implementation follows strict TDD: tests first, implementation second. Milestones are ordered by dependency chain — pure logic first, then mocked I/O, then integration.

---

## M0 — Project Scaffolding

Set up the package structure, build system, and dev tooling. Zero business logic.

| Task | Status |
|---|---|
| `pyproject.toml` with deps, scripts, pytest config | ⬜ |
| `src/wp_migration/__init__.py` + package skeleton | ⬜ |
| `tests/__init__.py` + `conftest.py` + `factories.py` | ⬜ |
| Verify `pytest` runs and discovers 0 tests | ⬜ |

---

## M1 — wp-config.php Parser

Pure string parsing. Fastest feedback loop. No I/O.

| Test File | Tests | Status |
|---|---|---|
| `tests/test_wp_config.py` | ~10 | ⬜ |
| — Parse `define('DB_NAME', 'foo')` → `{"DB_NAME": "foo"}` | | |
| — Parse `define('DB_HOST', 'localhost')` → fallback to 'localhost' | | |
| — Parse multi-line defines with comments | | |
| — Parse `$table_prefix` variable | | |
| — Parse with newlines and surrounding PHP code | | |
| — Parse when file is in parent directory (discovery logic) | | |
| — Parse when config file not found at all | | |
| — Parse into `WpConfig` dataclass | | |
| — Parse empty/invalid PHP gracefully | | |
| — Parse mixed single/double quotes | | |

**Implementation:** `src/wp_migration/wp_config.py`

---

## M2 — Serialization-Safe URL Replacement

The riskiest component. PHP serialized strings contain length bytes that must match. A naive replace corrupts them.

| Test File | Tests | Status |
|---|---|---|
| `tests/test_replace.py` | ~12 | ⬜ |
| — Replace plain string, no serialization | | |
| — Replace in PHP serialized string: `s:N:"...old...";` → `s:N':"...new...";` | | |
| — Replace where new URL is longer than old (length adjustment) | | |
| — Replace where new URL is shorter than old (length adjustment) | | |
| — Replace in nested serialized arrays | | |
| — Replace in serialized objects | | |
| — Multiple occurrences in one serialized structure | | |
| — No match → no change (idempotent) | | |
| — URLs that appear as values in serialized data | | |
| — Edge case: URL contains characters that need encoding in serialized strings | | |
| — Handle both `s:N:` and `s:N"` formats | | |
| — Replace in full SQL dump (mixed plain + serialized lines) | | |

**Implementation:** `src/wp_migration/replace.py`

---

## M3 — Configuration Loader

YAML parsing, validation, defaults, env var overrides.

| Test File | Tests | Status |
|---|---|---|
| `tests/test_config.py` | ~8 | ⬜ |
| — Load valid YAML → `MigrationConfig` dataclass | | |
| — Missing required field raises clear error | | |
| — Invalid transport type raises error | | |
| — Environment variable overrides config value | | |
| — `.env` file loaded and merged | | |
| — Default values applied for optional fields | | |
| — Port defaults: FTP=21, SFTP=22, MySQL=3306 | | |
| — Dry-run flag propagation through config | | |

**Implementation:** `src/wp_migration/config.py`

---

## M4 — Transport Layer

Unified interface over three file transfer protocols. All backends mocked in tests.

| Test File | Tests | Status |
|---|---|---|
| `tests/test_transport.py` | ~10 | ⬜ |
| — FTP: connect with host/port/user/pass → connection object | | |
| — FTP: download file → local path | | |
| — FTP: upload file → remote path | | |
| — FTP: list directory contents | | |
| — FTP: delete file | | |
| — FTP: exists() returns bool | | |
| — SFTP: same operations (mocked paramiko) | | |
| — SCP: same operations (mocked paramiko) | | |
| — Connection error raises TransportError with context | | |
| — Upload progress callback fires with byte counts | | |

**Implementation:** `src/wp_migration/transport.py`

---

## M5 — Database Operations

Dump source DB, import into target. Shell fallback with pymysql.

| Test File | Tests | Status |
|---|---|---|
| `tests/test_db.py` | ~10 | ⬜ |
| — Dump: mysqldump binary found → subprocess called with correct args | | |
| — Dump: mysqldump not found → falls back to pymysql | | |
| — Dump: writes `.sql` file to expected path | | |
| — Dump: pymysql path iterates all tables, writes INSERTs | | |
| — Dump: handles connection failure gracefully | | |
| — Import: mysql binary found → subprocess called with correct args | | |
| — Import: mysql not found → falls back to pymysql | | |
| — Import: pymysql path executes SQL statements | | |
| — Import: handles import failure (partial restore detection) | | |
| — Dump includes correct charset/collation headers | | |

**Implementation:** `src/wp_migration/db.py`

---

## M6 — File Migration

Discover wp-content tree, orchestrate source → local → target transfer.

| Test File | Tests | Status |
|---|---|---|
| `tests/test_files.py` | ~8 | ⬜ |
| — Discover wp-content/ from remote_path root | | |
| — Skip dirs: cache, upgrade, backup, backups | | |
| — Transfer: download file from source → local staging | | |
| — Transfer: upload file from local staging → target | | |
| — Transfer: resume skips already-transferred files (checksum match) | | |
| — Transfer: progress callback reports overall progress | | |
| — Cleanup: staging files removed after successful transfer | | |
| — Empty wp-content directory handled gracefully | | |

**Implementation:** `src/wp_migration/files.py`

---

## M7 — CLI

Wire everything together with Click. Commands, flags, dry-run, error messages.

| Test File | Tests | Status |
|---|---|---|
| `tests/test_cli.py` | ~8 | ⬜ |
| — `wp-migrate run config.yaml` runs full migration | | |
| — `wp-migrate export config.yaml` only exports | | |
| — `wp-migrate import config.yaml` only imports | | |
| — `--dry-run` logs what would happen, no actual transfer | | |
| — `--verbose` shows detailed progress output | | |
| — Missing config file shows helpful error | | |
| — Invalid config shows validation error messages | | |
| — Keyboard interrupt cleans up temp files | | |

**Implementation:** `src/wp_migration/cli.py`

---

## M8 — Integration Tests

Real end-to-end with local MySQL and a temporary file server.

| Test File | Tests | Status |
|---|---|---|
| `tests/test_integration.py` | ~4 | ⬜ |
| — Full cycle: export MySQL → import MySQL (local DB, files via local FS) | | |
| — URL replacement: export → replace old URL → import → verify new URL in DB | | |
| — wp-content transfer: real files copied between temp directories | | |
| — wp-config.php discovery finds file in parent directory | | |

---

## M9 — Polish

| Task | Status |
|---|---|
| Rich progress bars for all long-running operations | ⬜ |
| Structured logging (JSON mode for CI) | ⬜ |
| README with examples | ⬜ |
| Resume support for interrupted transfers | ⬜ |
| Exit codes for scripting | ⬜ |

---

## Summary

```
M0  ⬜ Scaffolding          (no tests)
M1  ⬜ wp-config parser     (~10 tests)
M2  ⬜ URL replacement      (~12 tests)
M3  ⬜ Config loader        (~8 tests)
M4  ⬜ Transport layer      (~10 tests)
M5  ⬜ Database operations  (~10 tests)
M6  ⬜ File migration       (~8 tests)
M7  ⬜ CLI                  (~8 tests)
M8  ⬜ Integration          (~4 tests)
M9  ⬜ Polish               (no tests)

Total: ~70 tests across 8 test modules
```
