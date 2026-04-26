from __future__ import annotations

import os
import secrets
import shlex
import shutil
import subprocess
import tempfile
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

import pymysql

from wp_migration.config import MySQLConfig


class DatabaseError(Exception):
    pass


def dump_database(config: MySQLConfig, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    mysqldump = shutil.which("mysqldump")

    if mysqldump:
        return _dump_via_mysqldump(config, mysqldump, output_path)

    return _dump_via_pymysql(config, output_path)


def _dump_via_mysqldump(config: MySQLConfig, mysqldump: str, output_path: Path) -> Path:
    cmd = [
        mysqldump,
        f"--host={config.host}",
        f"--port={config.port}",
        f"--user={config.user}",
        "--set-gtid-purged=OFF",
        "--single-transaction",
        "--routines",
        "--triggers",
        "--add-drop-table",
        config.name,
    ]

    env = {"MYSQL_PWD": config.password}

    try:
        with open(output_path, "w") as f:
            subprocess.run(cmd, env=env, check=True, stdout=f, stderr=subprocess.PIPE, text=True)
    except subprocess.CalledProcessError as e:
        raise DatabaseError(f"mysqldump failed: {e.stderr or e}") from e
    except Exception as e:
        raise DatabaseError(f"mysqldump failed: {e}") from e

    return output_path


def _dump_via_pymysql(config: MySQLConfig, output_path: Path) -> Path:
    try:
        conn = pymysql.connect(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password,
            database=config.name,
        )
    except Exception as e:
        raise DatabaseError(f"Database connection failed: {e}") from e

    try:
        with conn, output_path.open("w") as f:
            with conn.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                tables = [row[0] for row in cursor.fetchall()]

            for table in tables:
                # Dump CREATE TABLE
                with conn.cursor() as cursor:
                    cursor.execute(f"SHOW CREATE TABLE `{table}`")
                    row = cursor.fetchone()
                    if row:
                        f.write(f"DROP TABLE IF EXISTS `{table}`;\n")
                        f.write(f"{row[1]};\n\n")

                # Dump data
                with conn.cursor() as cursor:
                    cursor.execute(f"SELECT * FROM `{table}`")
                    rows = cursor.fetchall()
                    if not rows:
                        continue
                    col_count = len(cursor.description)
                    cols = ", ".join(f"`{d[0]}`" for d in cursor.description)

                    f.write(f"INSERT INTO `{table}` ({cols}) VALUES\n")

                    for i, row in enumerate(rows):
                        escaped = []
                        for val in row:
                            if val is None:
                                escaped.append("NULL")
                            elif isinstance(val, (int, float)):
                                escaped.append(str(val))
                            else:
                                escaped.append(f"'{str(val).replace(chr(39), chr(92) + chr(39))}'")
                        line = f"({', '.join(escaped)})"
                        if i < len(rows) - 1:
                            line += ","
                        else:
                            line += ";"
                        f.write(line + "\n")
                    f.write("\n")
    except Exception as e:
        raise DatabaseError(f"Database dump failed: {e}") from e

    return output_path


def remote_dump_via_ssh(ssh_conn, config: MySQLConfig, output_path: Path) -> Path:
    remote_temp = f"/tmp/wp_migrate_dump_{secrets.token_hex(8)}.sql"
    cmd = (
        f"mysqldump --host={shlex.quote(config.host)} "
        f"--port={config.port} "
        f"--user={shlex.quote(config.user)} "
        f"--password={shlex.quote(config.password)} "
        "--set-gtid-purged=OFF --single-transaction "
        "--routines --triggers --add-drop-table "
        f"{shlex.quote(config.name)} > {shlex.quote(remote_temp)}"
    )
    try:
        ssh_conn.exec_command(cmd)
        ssh_conn.download(remote_temp, str(output_path))
    except Exception:
        raise
    finally:
        try:
            ssh_conn.exec_command(f"rm -f {shlex.quote(remote_temp)}")
        except Exception:
            pass
    return output_path


def remote_dump_via_php(
    site_url: str,
    conn,
    remote_wp_root: str,
    output_path: Path,
    timeout: int = 300,
) -> Path:
    random_tag = secrets.token_hex(16)
    script_name = f"wp-migrate-dump-{random_tag}.php"
    remote_script = f"{remote_wp_root.rstrip('/')}/{script_name}"

    php_code = """<?php
define('WP_USE_THEMES', false);
require_once __DIR__ . '/wp-load.php';

while (ob_get_level()) ob_end_clean();
header('Content-Type: application/sql; charset=utf-8');

$tables = $wpdb->get_results("SHOW TABLES", ARRAY_N);
foreach ($tables as $row) {
    $table = current($row);
    $create = $wpdb->get_row("SHOW CREATE TABLE `$table`", ARRAY_N);
    echo "DROP TABLE IF EXISTS `$table`;\\n";
    echo $create[1] . ";\\n\\n";

    $offset = 0;
    $chunk = 500;
    do {
        $rows = $wpdb->get_results(
            $wpdb->prepare("SELECT * FROM `$table` LIMIT %d, %d", $offset, $chunk),
            ARRAY_N
        );
        if ($rows) {
            echo "INSERT INTO `$table` VALUES\\n";
            $parts = array();
            foreach ($rows as $r) {
                $vals = array();
                foreach ($r as $v) {
                    $vals[] = is_null($v) ? 'NULL' : "'" . $wpdb->_real_escape($v) . "'";
                }
                $parts[] = '(' . implode(', ', $vals) . ')';
            }
            echo implode(",\\n", $parts) . ";\\n\\n";
        }
        $offset += $chunk;
    } while (count($rows ?? []) === $chunk);
}
unlink(__FILE__);
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".php", delete=False) as f:
        f.write(php_code)
        local_script = f.name

    try:
        conn.upload(local_script, remote_script)
        url = site_url.rstrip("/") + "/" + script_name
        try:
            resp = urllib.request.urlopen(url, timeout=timeout)
            if resp.status != 200:
                raise DatabaseError(f"PHP dump script returned HTTP {resp.status}")
            with open(output_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
        except urllib.error.HTTPError as e:
            raise DatabaseError(f"PHP dump script returned HTTP {e.code}") from e
        except OSError as e:
            raise DatabaseError(f"PHP dump script request failed: {e}") from e
    except Exception:
        raise
    finally:
        try:
            conn.delete(remote_script)
        except Exception:
            pass
        try:
            os.unlink(local_script)
        except Exception:
            pass

    return output_path


def import_sql(config: MySQLConfig, dump_path: Path) -> None:
    if not dump_path.exists():
        raise DatabaseError(f"Dump file not found: {dump_path}")

    mysql = shutil.which("mysql")

    if mysql:
        _import_via_mysql(config, mysql, dump_path)
    else:
        _import_via_pymysql(config, dump_path)


def _import_via_mysql(config: MySQLConfig, mysql: str, dump_path: Path) -> None:
    cmd = [
        mysql,
        f"--host={config.host}",
        f"--port={config.port}",
        f"--user={config.user}",
        config.name,
    ]

    env = {"MYSQL_PWD": config.password}

    try:
        with open(dump_path) as f:
            subprocess.run(cmd, env=env, check=True, stdin=f, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        raise DatabaseError(f"mysql import failed: {e.stderr.decode() or e}") from e
    except Exception as e:
        raise DatabaseError(f"mysql import failed: {e}") from e


def _import_via_pymysql(config: MySQLConfig, dump_path: Path) -> None:
    try:
        conn = pymysql.connect(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password,
            database=config.name,
        )
    except Exception as e:
        raise DatabaseError(f"Database connection failed: {e}") from e

    try:
        with conn, dump_path.open() as f:
            with conn.cursor() as cursor:
                statement = ""
                for line in f:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("--"):
                        continue
                    statement += line
                    if line.rstrip().endswith(";"):
                        if statement.strip():
                            cursor.execute(statement.strip())
                        statement = ""
                if statement.strip():
                    cursor.execute(statement.strip())
            conn.commit()
    except Exception as e:
        raise DatabaseError(f"Database import failed: {e}") from e
