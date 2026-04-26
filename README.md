# wp-migration

WordPress site migration tool. Runs from your local machine — connects to source and target hosts via FTP/SFTP/SCP for files, and directly to MySQL for the database.

## Install

```bash
pip install .
```

Requires Python 3.11+.

## Usage

Create a `config.yaml`:

```yaml
source:
  transport: sftp
  host: old-server.com
  user: admin
  password: secret
  remote_path: /var/www/html
  mysql:
    host: db.old-server.com
    user: db_user
    password: db_pass
    name: wp_db

target:
  transport: sftp
  host: new-server.com
  user: deploy
  password: secret2
  remote_path: /var/www/html
  mysql:
    host: db.new-server.com
    user: new_db_user
    password: new_db_pass
    name: new_wp_db
  url: https://newsite.com
```

Then run:

```bash
wp-migrate run config.yaml
```

Or step by step:

```bash
wp-migrate export config.yaml   # dump DB + download wp-content
wp-migrate import config.yaml   # upload wp-content + import DB
```

## Config Reference

| Section | Field | Description |
|---|---|---|
| `source` | `transport` | `sftp`, `ftp`, or `scp` |
| | `host` | Source server hostname |
| | `port` | Default: 22 (sftp/scp), 21 (ftp) |
| | `user` | Login username |
| | `password` | Login password |
| | `key_path` | SSH key path (sftp/scp, optional) |
| | `remote_path` | Absolute path to WordPress root |
| | `mysql` | Optional — override auto-detected DB credentials |
| `target` | `transport` | Same as source |
| | `host` | Target server hostname |
| | `port` | Same defaults as source |
| | `user` | Login username |
| | `password` | Login password |
| | `remote_path` | Absolute path to WordPress root |
| | `mysql` | **Required** — target DB credentials |
| | `url` | New site URL (triggers serialization-safe replace) |
| `options` | `wp_content_only` | Skip WP core files (default: true) |
| | `skip_uploads` | Skip media files (default: false) |
| | `dry_run` | Preview only (default: false) |
| | `resume` | Skip already-transferred files by checksum (default: true) |

## How It Works

```
Your local machine
    │
    ├── SFTP → Source host     → download wp-content/
    ├── MySQL → Source DB      → dump.sql
    │
    ├── [URL replacement in dump]
    │
    ├── SFTP → Target host     → upload wp-content/
    └── MySQL → Target DB      → import dump
```

- Source DB credentials are auto-detected from `wp-config.php` (checks remote path, then parent directory)
- URL replacement handles PHP serialized data — length bytes are adjusted (not just string find/replace)
- File transfer is recursive with MD5 checksum resume support

## Development

```bash
pip install -e ".[dev]"
python -m pytest
```

### Full e2e test with real WordPress containers

```bash
cd test/
docker compose up -d --build
# Install WP + create content on source
docker compose exec source-wp wp --allow-root core install ...
# Run migration
wp-migrate run config.test.yaml
docker compose down -v
```
