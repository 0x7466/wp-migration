from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional

from wp_migration.transport import TransportConnection

SKIP_DIRS = frozenset({"cache", "upgrade", "backup", "backups"})


def discover_wp_content(remote_wp_content: str, conn: TransportConnection) -> set[str]:
    entries = conn.list(remote_wp_content)
    dirs = set()
    for entry in entries:
        name = entry.rstrip("/").rstrip("\\")
        if name.startswith("."):
            continue
        if name in SKIP_DIRS:
            continue
        try:
            conn.list(f"{remote_wp_content}/{name}")
            dirs.add(name)
        except Exception:
            continue
    return dirs


def _checksum(path: str | Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _ensure_local_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def transfer_files(
    source: TransportConnection,
    target: TransportConnection,
    subdir: str,
    staging_dir: str,
    existing_checksums: dict[str, str],
    remote_wp_content: str = "",
    progress: Optional[callable] = None,
) -> dict[str, str]:
    remote_base = f"{remote_wp_content}/{subdir}" if remote_wp_content else subdir
    local_base = _ensure_local_dir(Path(staging_dir) / subdir)
    checksums: dict[str, str] = {}

    try:
        filenames = source.list(remote_base)
    except Exception:
        filenames = []

    for filename in filenames:
        if filename.startswith("."):
            continue
        remote_file = f"{remote_base}/{filename}"
        local_file = local_base / filename
        remote_target = f"{remote_wp_content}/{subdir}/{filename}" if remote_wp_content else f"/{subdir}/{filename}"

        existing = existing_checksums.get(filename)
        if existing and local_file.exists() and _checksum(local_file) == existing:
            checksums[filename] = existing
            continue

        source.download(remote_file, str(local_file))
        cksum = _checksum(local_file)
        checksums[filename] = cksum

    # Now upload from staging to target
    for filename in checksums:
        local_file = Path(staging_dir) / subdir / filename
        remote_dest = f"{remote_wp_content}/{subdir}/{filename}" if remote_wp_content else f"/{subdir}/{filename}"
        target.upload(str(local_file), remote_dest)

    if progress:
        progress(len(checksums), len(checksums))

    return checksums
