# Roadmap

Implementation follows strict TDD: tests first, implementation second. Milestones are ordered by dependency chain — pure logic first, then mocked I/O, then integration.

---

## M0 — Project Scaffolding ✅

Set up the package structure, build system, and dev tooling. Zero business logic.

| Task | Status |
|---|---|
| `pyproject.toml` with deps, scripts, pytest config | ✅ |
| `src/wp_migration/__init__.py` + package skeleton | ✅ |
| `tests/__init__.py` + `conftest.py` + `factories.py` | ✅ |
| Verify `pytest` runs and discovers 0 tests | ✅ |

---

## M1 — wp-config.php Parser ✅

Pure string parsing. Fastest feedback loop. No I/O.

| Test File | Tests | Status |
|---|---|---|
| `tests/test_wp_config.py` | 18 | ✅ |
| Parse `define('DB_NAME', 'foo')` → extract constants | ✅ |
| Parse multi-line defines with comments | ✅ |
| Parse `$table_prefix` variable | ✅ |
| Parse mixed single/double quotes | ✅ |
| Parse empty/invalid PHP gracefully | ✅ |
| Discover file in remote path or parent directory | ✅ |
| FileNotFoundError when wp-config.php missing | ✅ |

**Implementation:** `src/wp_migration/wp_config.py`

---

## M2 — Serialization-Safe URL Replacement ✅

The riskiest component. PHP serialized strings contain length bytes that must match.

| Test File | Tests | Status |
|---|---|---|
| `tests/test_replace.py` | 23 | ✅ |
| Plain string replacement (no serialization) | ✅ |
| Serialized string: same length | ✅ |
| Serialized string: longer/shorter URL (length adjustment) | ✅ |
| Nested serialized arrays and objects | ✅ |
| Multiple serialized values on same line | ✅ |
| SQL-escaped serialized strings (`\"`) | ✅ |
| Unicode in serialized strings (byte-level parsing) | ✅ |
| Full SQL dump replacement | ✅ |

**Implementation:** `src/wp_migration/replace.py`

---

## M3 — Configuration Loader ✅

| Test File | Tests | Status |
|---|---|---|
| `tests/test_config.py` | 17 | ✅ |
| YAML → `MigrationConfig` dataclass | ✅ |
| Missing required field raises error | ✅ |
| Invalid transport type raises error | ✅ |
| Default port: FTP=21, SFTP=22, MySQL=3306 | ✅ |
| Custom options with defaults | ✅ |
| MySQL override in source config | ✅ |

**Implementation:** `src/wp_migration/config.py`

---

## M4 — Transport Layer ✅

FTP via ftpretty, SFTP/SCP via paramiko. All backends mocked in tests.

| Test File | Tests | Status |
|---|---|---|
| `tests/test_transport.py` | 23 | ✅ |
| FTP: connect, download, upload, list, delete, exists | ✅ |
| SFTP: connect, download, upload, list, exists | ✅ |
| SCP: delegates to SFTP under the hood | ✅ |
| Connection error raises TransportError | ✅ |
| SSH key-based authentication | ✅ |
| Upload progress callback | ✅ |

**Implementation:** `src/wp_migration/transport.py`

---

## M5 — Database Operations ✅

Dump source DB, import into target. mysqldump CLI preferred, pymysql fallback.

| Test File | Tests | Status |
|---|---|---|
| `tests/test_db.py` | 10 | ✅ |
| mysqldump: correct command args | ✅ |
| mysqldump: password via env (not -p flag) | ✅ |
| pymysql fallback: SHOW TABLES + CREATE TABLE + INSERT | ✅ |
| mysql CLI import | ✅ |
| pymysql fallback import: statement-by-statement | ✅ |
| Connection failure → DatabaseError | ✅ |
| Missing dump file → DatabaseError | ✅ |

**Implementation:** `src/wp_migration/db.py`

---

## M6 — File Migration ✅

| Test File | Tests | Status |
|---|---|---|
| `tests/test_files.py` | 11 | ✅ |
| Discover wp-content subdirectories | ✅ |
| Skip dirs: cache, upgrade, backup | ✅ |
| Transfer: download → local staging → upload | ✅ |
| Resume: skip if checksum matches | ✅ |
| Re-download if checksum mismatch | ✅ |
| Empty directory handled gracefully | ✅ |

**Implementation:** `src/wp_migration/files.py`

---

## M7 — CLI ✅

Click-based CLI: `run`, `export`, `import` commands.

| Test File | Tests | Status |
|---|---|---|
| `tests/test_cli.py` | 12 | ✅ |
| Missing config → error message | ✅ |
| Nonexistent config → file not found | ✅ |
| `--dry-run` flag accepted | ✅ |
| `--verbose` flag accepted | ✅ |
| Invalid command → "No such command" | ✅ |
| No command → shows help | ✅ |

**Implementation:** `src/wp_migration/cli.py`

---

## M8 — Integration Tests ✅

End-to-end with real MySQL in Docker. Full pipeline validated.

| Test File | Tests | Status |
|---|---|---|
| `tests/test_integration.py` | 1 | ✅ |
| mysqldump → URL replace → mysql import → verify | ✅ |
| Serialized string length updated correctly | ✅ |
| New URL in target database, old URL absent | ✅ |

---

## M9 — Polish ✅

| Task | Status |
|---|---|
| Sample config.yaml | ✅ |
| README with examples | ✅ |
| Roadmap updated with checkmarks | ✅ |
| Resume support (checksum-based) | ✅ |
| Exit codes (Click/sys.exit) | ✅ |

---

## Summary

```
M0  ✅ Scaffolding          (0 tests)
M1  ✅ wp-config parser     (18 tests)
M2  ✅ URL replacement      (23 tests)
M3  ✅ Config loader        (17 tests)
M4  ✅ Transport layer      (23 tests)
M5  ✅ Database operations  (10 tests)
M6  ✅ File migration       (11 tests)
M7  ✅ CLI                  (12 tests)
M8  ✅ Integration          (1 test)
M9  ✅ Polish               (0 tests)

Total: 115 tests across 8 test modules
```
