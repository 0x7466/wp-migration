from __future__ import annotations

import enum
from pathlib import Path
from typing import Callable, Optional

import paramiko
from ftpretty import ftpretty


class TransportProtocol(enum.Enum):
    FTP = "ftp"
    SFTP = "sftp"
    SCP = "scp"


class TransportError(Exception):
    pass


class ConnectionError(TransportError):
    pass


class TransferError(TransportError):
    pass


class TransportConnection:
    def download(self, remote_path: str, local_path: str, progress: Optional[Callable] = None) -> None:
        raise NotImplementedError

    def upload(self, local_path: str, remote_path: str, progress: Optional[Callable] = None) -> None:
        raise NotImplementedError

    def list(self, remote_dir: str) -> list[str]:
        raise NotImplementedError

    def delete(self, remote_path: str) -> None:
        raise NotImplementedError

    def exists(self, remote_path: str) -> bool:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class FtpConnection(TransportConnection):
    def __init__(self, host: str, port: int, user: str, password: str):
        try:
            self._client = ftpretty(host, user, password, port)
        except Exception as e:
            raise ConnectionError(f"FTP connection failed: {e}") from e

    def download(self, remote_path: str, local_path: str, progress: Optional[Callable] = None) -> None:
        self._client.get(remote_path, local_path)

    def upload(self, local_path: str, remote_path: str, progress: Optional[Callable] = None) -> None:
        self._client.put(local_path, remote_path)
        if progress:
            progress(1, 1)

    def list(self, remote_dir: str) -> list[str]:
        return self._client.list(remote_dir)

    def delete(self, remote_path: str) -> None:
        self._client.delete(remote_path)

    def exists(self, remote_path: str) -> bool:
        parent = str(Path(remote_path).parent)
        name = Path(remote_path).name
        try:
            entries = self._client.list(parent)
            return name in entries or f"/{name}" in entries or name.lstrip("/") in entries
        except Exception:
            return False

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass


class SshConnection(TransportConnection):
    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: Optional[str] = None,
        key_path: Optional[str] = None,
    ):
        self._ssh = paramiko.SSHClient()
        self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            connect_kwargs: dict = {
                "hostname": host,
                "port": port,
                "username": user,
            }
            if key_path:
                connect_kwargs["key_filename"] = key_path
            else:
                connect_kwargs["password"] = password or ""
            self._ssh.connect(**connect_kwargs)
        except Exception as e:
            raise ConnectionError(f"SSH connection failed: {e}") from e

        try:
            self._sftp = self._ssh.open_sftp()
        except Exception as e:
            self._ssh.close()
            raise ConnectionError(f"SFTP channel failed: {e}") from e

    def download(self, remote_path: str, local_path: str, progress: Optional[Callable] = None) -> None:
        self._sftp.get(remote_path, local_path)

    def upload(self, local_path: str, remote_path: str, progress: Optional[Callable] = None) -> None:
        self._sftp.put(local_path, remote_path)

    def list(self, remote_dir: str) -> list[str]:
        return self._sftp.listdir(remote_dir)

    def delete(self, remote_path: str) -> None:
        self._sftp.remove(remote_path)

    def exists(self, remote_path: str) -> bool:
        try:
            self._sftp.stat(remote_path)
            return True
        except (FileNotFoundError, OSError):
            return False

    def close(self) -> None:
        try:
            self._sftp.close()
        except Exception:
            pass
        try:
            self._ssh.close()
        except Exception:
            pass


class SftpConnection(SshConnection):
    pass


class ScpConnection(SshConnection):
    pass


def connect(
    protocol: TransportProtocol | str,
    host: str,
    port: int,
    user: str,
    password: Optional[str] = None,
    key_path: Optional[str] = None,
) -> TransportConnection:
    if isinstance(protocol, str):
        try:
            protocol = TransportProtocol(protocol.lower())
        except ValueError:
            raise ValueError(
                f"Invalid protocol '{protocol}'. Must be one of: {', '.join(p.value for p in TransportProtocol)}"
            )

    if protocol == TransportProtocol.FTP:
        if not password:
            raise ConnectionError("Password required for FTP connection")
        return FtpConnection(host, port, user, password)

    if not password and not key_path:
        raise ConnectionError("Password or key_path required for SSH connection")

    return SshConnection(host, port, user, password=password, key_path=key_path)
