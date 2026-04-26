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


def _walk_remote(conn: TransportConnection, remote_dir: str) -> list[tuple[str, str, bool]]:
    """Recursively walk a remote directory.

    Returns list of (remote_path, relative_path, is_dir).
    """
    results: list[tuple[str, str, bool]] = []
    entries = conn.list(remote_dir)
    for entry in entries:
        if entry.startswith("."):
            continue
        remote_path = f"{remote_dir}/{entry}"
        try:
            sub = conn.list(remote_path)
            results.append((remote_path, entry, True))
            for sub_path, rel, is_d in _walk_remote(conn, remote_path):
                results.append((sub_path, f"{entry}/{rel}", is_d))
        except Exception:
            results.append((remote_path, entry, False))
    return results


def transfer_files(
    source: TransportConnection,
    target: Optional[TransportConnection],
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
        files = _walk_remote(source, remote_base)
    except Exception:
        files = []

    for remote_path, rel_path, is_dir in files:
        if is_dir:
            _ensure_local_dir(local_base / rel_path)
            continue

        local_file = local_base / rel_path
        existing = existing_checksums.get(rel_path)
        if existing and local_file.exists() and _checksum(local_file) == existing:
            checksums[rel_path] = existing
            continue

        _ensure_local_dir(local_file.parent)
        source.download(remote_path, str(local_file))
        cksum = _checksum(local_file)
        checksums[rel_path] = cksum

    # Upload from staging to target
    if target is not None:
        for rel_path in checksums:
            local_file = local_base / rel_path
            remote_dest = f"{remote_base}/{rel_path}"
            target.upload(str(local_file), remote_dest)

    if progress:
        progress(len(checksums), len(checksums))

    return checksums
