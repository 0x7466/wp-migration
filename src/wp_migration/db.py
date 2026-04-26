from __future__ import annotations

import shutil
import subprocess
import tempfile
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
