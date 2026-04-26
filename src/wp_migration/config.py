from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Optional

import yaml

VALID_TRANSPORTS = frozenset({"sftp", "ftp", "scp"})

_TRANSPORT_DEFAULT_PORTS = {"sftp": 22, "ftp": 21, "scp": 22}


@dataclasses.dataclass
class MySQLConfig:
    host: str
    user: str
    password: str
    name: str
    port: int = 3306

    @property
    def dsn(self):
        return _DSN(self.host, self.port, self.user, self.password, self.name)


@dataclasses.dataclass
class _DSN:
    host: str
    port: int
    user: str
    password: str
    dbname: str


@dataclasses.dataclass
class HostConfig:
    transport: str
    host: str
    user: str
    password: str
    remote_path: str
    port: int | None = None
    key_path: str | None = None
    mysql: MySQLConfig | None = None
    url: str | None = None

    def __post_init__(self):
        if self.transport not in VALID_TRANSPORTS:
            raise ValueError(
                f"Invalid transport '{self.transport}'. Must be one of: {', '.join(sorted(VALID_TRANSPORTS))}"
            )
        if self.port is None:
            object.__setattr__(self, "port", _TRANSPORT_DEFAULT_PORTS[self.transport])


@dataclasses.dataclass
class OptionsConfig:
    wp_content_only: bool = True
    skip_uploads: bool = False
    skip_themes: bool = False
    skip_plugins: bool = False
    dry_run: bool = False
    resume: bool = True


@dataclasses.dataclass
class MigrationConfig:
    source: HostConfig
    target: HostConfig
    options: OptionsConfig = dataclasses.field(default_factory=OptionsConfig)

    def __post_init__(self):
        if isinstance(self.options, dict):
            object.__setattr__(self, "options", _build_options(self.options))


def _build_host_config(data: dict) -> HostConfig:
    transport = data.get("transport")
    if not transport:
        raise ValueError("Host config missing required field: transport")
    return HostConfig(
        transport=transport,
        host=data.get("host", ""),
        port=data.get("port"),
        user=data.get("user", ""),
        password=data.get("password", ""),
        key_path=data.get("key_path"),
        remote_path=data.get("remote_path", ""),
        mysql=_build_mysql_config(data.get("mysql")) if "mysql" in data and data["mysql"] else None,
        url=data.get("url"),
    )


def _build_mysql_config(data: dict) -> MySQLConfig:
    return MySQLConfig(
        host=data.get("host", ""),
        port=data.get("port", 3306),
        user=data.get("user", ""),
        password=data.get("password", ""),
        name=data.get("name", ""),
    )


def _build_options(data: dict | None) -> OptionsConfig:
    if not data:
        return OptionsConfig()
    return OptionsConfig(
        wp_content_only=data.get("wp_content_only", True),
        skip_uploads=data.get("skip_uploads", False),
        skip_themes=data.get("skip_themes", False),
        skip_plugins=data.get("skip_plugins", False),
        dry_run=data.get("dry_run", False),
        resume=data.get("resume", True),
    )


def load_config(path: str | Path) -> MigrationConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    if not data:
        raise ValueError("Config file is empty")

    if "source" not in data:
        raise ValueError("Config missing required section: source")
    if "target" not in data:
        raise ValueError("Config missing required section: target")

    source = _build_host_config(data["source"])
    target = _build_host_config(data["target"])
    options = _build_options(data.get("options"))

    # Validate required fields in source and target
    errors = []
    for name, cfg in [("source", source), ("target", target)]:
        if not cfg.transport:
            errors.append(f"{name}.transport is required")
        if not cfg.host:
            errors.append(f"{name}.host is required")
        if not cfg.user:
            errors.append(f"{name}.user is required")
        if not cfg.remote_path:
            errors.append(f"{name}.remote_path is required")

    if errors:
        raise ValueError("Config validation failed:\n" + "\n".join(errors))

    return MigrationConfig(source=source, target=target, options=options)
