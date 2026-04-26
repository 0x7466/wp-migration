# Concept: WordPress Migration Tool

## Overview

A Python CLI tool run from the admin's local machine that moves a WordPress site between hosts. It connects to source and target hosts over FTP/SFTP/SCP for files, and directly to MySQL on both ends for the database. No server-side software required on either host — just network reachability and valid credentials.

```
 ┌─────────────────────────────────────────────────────────────┐
 │                     YOUR LOCAL MACHINE                      │
 │                                                             │
 │  ┌─────────┐    ┌──────────┐    ┌──────────┐    ┌────────┐ │
 │  │ MySQL   │    │ Transport│    │  Local   │    │ MySQL  │ │
 │  │ client  │◄───│ FTP/SFTP │◄───│ staging  │───►│ client │ │
 │  │ source  │    │ source   │    │  (temp)  │    │ target │ │
 │  └────┬────┘    └────┬─────┘    └────┬─────┘    └───┬────┘ │
 │       │              │               │              │      │
 │   dump.sql    wp-content.tar.gz      │         import.sql  │
 └───────┼──────────────┼───────────────┼──────────────┼──────┘
         │              │               │              │
    ┌────▼────┐    ┌────▼────┐     ┌───▼────┐    ┌────▼─────┐
    │ SOURCE  │    │ SOURCE  │     │ TARGET │    │  TARGET  │
    │  MySQL  │    │  host   │     │  host  │    │  MySQL   │
    └─────────┘    └─────────┘     └────────┘    └──────────┘
```

## Core Principles

- **Run from anywhere** — the tool is a local PC application, not server software. It pulls data from the source and pushes it to the target.
- **No server-side dependencies** — no PHP helpers, no WP-CLI, no shell access needed. Just FTP/SFTP/SCP and MySQL port access.
- **Serialization-safe** — WordPress stores PHP-serialized data in the database. A naive domain replace corrupts it. The tool handles length byte adjustment.
- **Credentials auto-detection** — source DB credentials are parsed from `wp-config.php`. Target credentials are user-supplied.
- **Dry-run safe** — every operation supports `--dry-run`.

## Architecture

### Components

| Module | Responsibility |
|---|---|
| `cli.py` | Click-based command-line interface. Entry point: `wp-migrate`. |
| `config.py` | Dataclass model for YAML config. Load, validate, merge env vars. |
| `wp_config.py` | Parse PHP `wp-config.php` files. Extract DB constants. |
| `db.py` | Dump source DB to `.sql`. Import `.sql` to target DB. mysqldump CLI preferred, pymysql fallback. |
| `transport.py` | Unified abstraction over SFTP, FTP, SCP. Single interface, three backends. |
| `files.py` | Discover wp-content to transfer. Orchestrate file copy between hosts with resume. |
| `replace.py` | Serialization-safe search-replace on SQL dumps and strings. |
| `logging.py` | Rich-based structured output, progress bars, error formatting. |

### Credential Model

| What | Source | Target |
|---|---|---|
| Transport (host, port, user, password/key) | User-supplied (config.yaml) | User-supplied (config.yaml) |
| MySQL (host, port, user, pass, dbname) | Parsed from `wp-config.php` | User-supplied (config.yaml) |
| WordPress URL | Auto-detected from DB options table | User-supplied or auto-detected |

### wp-config.php Discovery

WordPress allows `wp-config.php` to sit **one directory above** the web root for security. The tool checks both locations:

1. `{remote_path}/wp-config.php`
2. `{remote_path}/../wp-config.php`

If neither is found, raise an error.

### MySQL Access

Both hosts must have their MySQL port (default 3306) reachable from the local machine, or an SSH tunnel must be available. The tool does not manage tunnels — that is a prerequisite handled by the user.

### Transport Layer

```
TransportProtocol (enum)
   ├── SFTP   → paramiko.SFTPClient
   ├── FTP    → ftpretty (wraps ftplib)
   └── SCP    → paramiko (scp protocol)

TransportConnection (protocol class)
   ├── connect() → establish
   ├── download(remote_path, local_path) → bytes
   ├── upload(local_path, remote_path) → bytes
   ├── list(remote_dir) → list[str]
   ├── delete(remote_path) → None
   └── exists(remote_path) → bool
```

### DB Dump Strategy

```
dump(creds) → dump.sql

if subprocess mysqldump available:
    shell: mysqldump -h host -P port -u user -p pass dbname > dump.sql
else:
    python: pymysql.connect() → for each table: SELECT * → INSERTs → dump.sql
```

Import follows the mirror pattern with `mysql` CLI preferred, `pymysql` fallback.

### URL Replacement

WordPress stores URLs in serialized PHP strings like:

```
s:22:"http://oldsite.com/menu"
```

When `oldsite.com` → `newsite.com`, the length must update:

```
s:22:"http://newsite.com/menu"
```

The algorithm walks through the dump file, identifies serialized string tokens, replaces the content *and* the length byte. Non-serialized strings are simple find-and-replace.

## Tech Stack

| Dependency | Purpose |
|---|---|
| `click` | CLI framework (commands, flags, prompts) |
| `pymysql` | Pure-Python MySQL client (fallback dump/import) |
| `paramiko` | SSH/SFTP/SCP transport |
| `ftpretty` | FTP transport (stdlib wrapper) |
| `pyyaml` | Configuration file parsing |
| `rich` | Progress bars, colored output, tables |
| `python-dotenv` | Environment variable overrides |
| `pytest` | Test framework |
| `pytest-mock` | Mocking for transport/DB tests |

## Usage

```bash
# One-shot: export from source, import to target
wp-migrate run config.yaml

# Or step by step:
wp-migrate export config.yaml          # dump DB + download wp-content → local staging
wp-migrate import config.yaml          # upload wp-content + import DB → target
```

### config.yaml Shape

```yaml
source:
  transport: sftp          # sftp | ftp | scp
  host: old-server.com
  port: 22
  user: admin
  password: secret
  key_path: ~/.ssh/id_rsa  # optional
  remote_path: /var/www/wordpress
  mysql_override:          # optional, auto-detected from wp-config.php
    host: db.example.com
    port: 3306
    user: wp_user
    password: db_secret
    name: wp_database

target:
  transport: ftp
  host: new-server.com
  port: 21
  user: deploy
  password: secret2
  remote_path: /public_html
  mysql:
    host: mysql.newserver.com
    port: 3306
    user: new_wp_user
    password: new_db_pass
    name: new_wp_db
  url: https://newsite.com

options:
  wp_content_only: true
  skip_uploads: false
  skip_themes: false
  skip_plugins: false
  dry_run: false
  resume: true
```

## Error Handling

All network operations wrapped in retry logic. Failures produce structured errors with suggestions. Database dump failures are partial-recovery-safe — incomplete dumps are flagged.
