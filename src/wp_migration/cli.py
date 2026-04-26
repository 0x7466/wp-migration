from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import click

from wp_migration.config import load_config
from wp_migration.db import dump_database, import_sql
from wp_migration.files import discover_wp_content, transfer_files
from wp_migration.replace import replace_in_sql
from wp_migration.transport import connect, TransportProtocol
from wp_migration.wp_config import parse_wp_config, discover_wp_config


@click.group()
@click.option("--verbose", is_flag=True, help="Enable detailed output")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


def _e(msg: str) -> None:
    click.echo(msg, err=True)


def _log(msg: str) -> None:
    click.echo(f"  {msg}")


def _step(msg: str) -> None:
    click.echo(f"\n[{msg}]")


def _load_config_or_exit(path: str) -> "MigrationConfig":
    cfg_path = Path(path)
    if not cfg_path.exists():
        _e(f"Config file not found: {path}")
        sys.exit(1)
    try:
        return load_config(cfg_path)
    except (ValueError, FileNotFoundError) as e:
        _e(f"Config error: {e}")
        sys.exit(1)


@main.command()
@click.argument("config", type=click.Path(exists=False))
@click.option("--dry-run", is_flag=True, help="Show what would be done without executing")
@click.pass_context
def run(ctx: click.Context, config: str, dry_run: bool) -> None:
    """Run full migration: export from source, import to target."""
    cfg = _load_config_or_exit(config)

    _log(f"Source: {cfg.source.user}@{cfg.source.host}:{cfg.source.port} ({cfg.source.transport})")
    _log(f"Target: {cfg.target.user}@{cfg.target.host}:{cfg.target.port} ({cfg.target.transport})")

    if dry_run:
        _log("[DRY-RUN] Full migration would execute")
        return

    with tempfile.TemporaryDirectory(prefix="wp-migrate-") as tmpdir:
        dump_path, staging_dir = _do_export(cfg, tmpdir, dry_run)
        _do_import(cfg, dump_path, staging_dir, dry_run)

    click.echo("\nMigration completed successfully.")


@main.command()
@click.argument("config", type=click.Path(exists=False))
@click.option("--dry-run", is_flag=True, help="Show what would be done without executing")
@click.pass_context
def export(ctx: click.Context, config: str, dry_run: bool) -> None:
    """Export database and wp-content from source host."""
    cfg = _load_config_or_exit(config)
    _log(f"Source: {cfg.source.user}@{cfg.source.host}:{cfg.source.port} ({cfg.source.transport})")

    if dry_run:
        _log("[DRY-RUN] Export would execute")
        return

    with tempfile.TemporaryDirectory(prefix="wp-migrate-") as tmpdir:
        _do_export(cfg, tmpdir, dry_run)

    click.echo("Export completed.")


@main.command(name="import")
@click.argument("config", type=click.Path(exists=False))
@click.option("--dry-run", is_flag=True, help="Show what would be done without executing")
@click.pass_context
def import_cmd(ctx: click.Context, config: str, dry_run: bool) -> None:
    """Import database and wp-content to target host."""
    cfg = _load_config_or_exit(config)
    _log(f"Target: {cfg.target.user}@{cfg.target.host}:{cfg.target.port} ({cfg.target.transport})")

    if dry_run:
        _log("[DRY-RUN] Import would execute")
        return

    with tempfile.TemporaryDirectory(prefix="wp-migrate-") as tmpdir:
        _do_import(cfg, None, tmpdir, dry_run)

    click.echo("Import completed.")


def _resolve_source_db_config(cfg):
    if cfg.source.mysql:
        _log("Using mysql_override for source database")
        return cfg.source.mysql

    _step("Connecting to source for wp-config discovery")
    conn = connect(
        TransportProtocol(cfg.source.transport),
        cfg.source.host,
        cfg.source.port,
        cfg.source.user,
        password=cfg.source.password,
        key_path=cfg.source.key_path,
    )
    try:
        config_path = discover_wp_config(cfg.source.remote_path, conn)
        _log(f"Found wp-config.php at: {config_path}")

        raw = _read_remote_file(conn, config_path)
        parsed = parse_wp_config(raw)

        from wp_migration.config import MySQLConfig
        return MySQLConfig(
            host=parsed.get("DB_HOST", "localhost").split(":")[0],
            port=int(parsed.get("DB_HOST", "localhost").split(":")[1]) if ":" in parsed.get("DB_HOST", "") else 3306,
            user=parsed.get("DB_USER", ""),
            password=parsed.get("DB_PASSWORD", ""),
            name=parsed.get("DB_NAME", ""),
        )
    except FileNotFoundError:
        _e("Could not auto-detect database credentials from source.")
        _e("Either fix the remote_path or add a mysql_override section to your config.")
        raise
    finally:
        conn.close()


def _read_remote_file(conn, remote_path):
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False) as f:
        tmp = f.name
    conn.download(remote_path, tmp)
    content = Path(tmp).read_text()
    Path(tmp).unlink(missing_ok=True)
    return content


def _do_export(cfg, tmpdir, dry_run):
    dump_path = Path(tmpdir) / "dump.sql"
    staging_dir = Path(tmpdir) / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)

    # 1. Resolve DB config
    db_config = _resolve_source_db_config(cfg)
    _log(f"Database: {db_config.user}@{db_config.host}:{db_config.port}/{db_config.name}")

    # 2. Dump database
    _step("Dumping source database")
    dump_database(db_config, str(dump_path))
    size = len(dump_path.read_text())
    _log(f"Dumped {size:,} bytes to {dump_path.name}")

    # 3. Connect to source for file transfer
    _step("Connecting to source for file transfer")
    src_conn = connect(
        TransportProtocol(cfg.source.transport),
        cfg.source.host,
        cfg.source.port,
        cfg.source.user,
        password=cfg.source.password,
        key_path=cfg.source.key_path,
    )

    try:
        # 4. Discover and download wp-content
        _step("Downloading wp-content")
        wp_content = f"{cfg.source.remote_path.rstrip('/')}/wp-content"
        dirs = discover_wp_content(wp_content, src_conn)
        if not dirs:
            _log("No wp-content directories found to transfer")
        else:
            _log(f"Found directories: {', '.join(sorted(dirs))}")

            total_checksums: dict[str, str] = {}
            for subdir in sorted(dirs):
                if subdir in ("uploads", "themes", "plugins") or not cfg.options.wp_content_only:
                    _log(f"  Downloading {subdir}...")
                    cksums = transfer_files(
                        src_conn, None, subdir, str(staging_dir), {},
                        remote_wp_content=wp_content,
                    )
                    total_checksums.update(cksums)

            _log(f"Downloaded {len(total_checksums)} files to staging")
    finally:
        src_conn.close()

    return dump_path, staging_dir


def _do_import(cfg, dump_path, staging_dir, dry_run, old_url=None):
    target_url = cfg.target.url

    # 1. URL replacement in SQL dump
    if dump_path and dump_path.exists() and target_url:
        if not old_url:
            old_url = _detect_old_url(cfg, dump_path)
        if old_url:
            _step("Replacing URLs in database dump")
            _log(f"Replacing {old_url} → {target_url}")
            old_sql = dump_path.read_text()
            new_sql = replace_in_sql(old_sql, old_url, target_url)
            replaced_path = dump_path.with_suffix(".replaced.sql")
            replaced_path.write_text(new_sql)
            dump_path = replaced_path

    # 2. Upload wp-content to target
    _step("Connecting to target for file upload")
    tgt_conn = connect(
        TransportProtocol(cfg.target.transport),
        cfg.target.host,
        cfg.target.port,
        cfg.target.user,
        password=cfg.target.password,
        key_path=cfg.target.key_path,
    )

    try:
        _step("Uploading wp-content to target")
        staging_dir_path = Path(staging_dir)
        if staging_dir_path.exists():
            for subdir in staging_dir_path.iterdir():
                if subdir.is_dir():
                    _upload_dir(tgt_conn, subdir,
                                f"{cfg.target.remote_path.rstrip('/')}/wp-content/{subdir.name}",
                                dry_run=dry_run)
    finally:
        tgt_conn.close()

    # 3. Import database to target
    if dump_path and dump_path.exists():
        _step("Importing database to target")
        if not cfg.target.mysql:
            _e("Target MySQL configuration is required for import")
            sys.exit(1)

        _log(f"Target DB: {cfg.target.mysql.user}@{cfg.target.mysql.host}:{cfg.target.mysql.port}/{cfg.target.mysql.name}")
        if not dry_run:
            import_sql(cfg.target.mysql, dump_path)
            _log("Database imported successfully")


def _detect_old_url(cfg, dump_path):
    """Try to find old site URL from the SQL dump (fallback to source DB)."""
    if dump_path and dump_path.exists():
        sql = dump_path.read_text()
        import re
        m = re.search(r"'siteurl',\s*'([^']+)'", sql)
        if m:
            _log(f"Detected old URL from dump: {m.group(1)}")
            return m.group(1)

    try:
        db = _resolve_source_db_config(cfg)
        import pymysql
        conn = pymysql.connect(
            host=db.host, port=db.port,
            user=db.user, password=db.password,
            database=db.name,
        )
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT option_value FROM wp_options WHERE option_name='siteurl'")
                row = cur.fetchone()
                if row:
                    _log(f"Detected old URL from source DB: {row[0]}")
                    return row[0]
    except Exception:
        pass
    return None


def _upload_dir(conn, local_dir, remote_dir, dry_run=False):
    import os
    for root, dirs, files in os.walk(str(local_dir)):
        rel = os.path.relpath(root, str(local_dir))
        target_parent = remote_dir if rel == "." else f"{remote_dir}/{rel}"
        _log(f"    Uploading {rel if rel != '.' else local_dir.name}/")
        for fname in files:
            local_path = os.path.join(root, fname)
            remote_path = f"{target_parent}/{fname}"
            if not dry_run:
                try:
                    conn.upload(local_path, remote_path)
                except Exception as e:
                    _log(f"    Upload error for {fname}: {e}")
