"""Explicit, private Linux service configuration; never defaults to host trust."""
from dataclasses import dataclass
from pathlib import Path
import ipaddress
import json
import os


@dataclass(frozen=True)
class Settings:
    data_root: Path
    credentials_file: Path | None = None
    auth_mode: str = 'disabled'
    bind_host: str = '127.0.0.1'
    host_registry: Path | None = None
    upload_limit: int = 64 * 1024 * 1024
    timeout_s: float = 120
    memory_limit_mb: int = 4096
    concurrency: int = 1
    converter_config: str | None = None

    def validate(self):
        if self.auth_mode not in ('dev-only','dsh-account'):
            raise ValueError('Explicit authentication mode required')
        if not ipaddress.ip_address(self.bind_host).is_loopback:
            raise ValueError('Authentication requires a loopback listener')
        if self.concurrency != 1 or self.timeout_s <= 0 or self.memory_limit_mb < 256 or self.upload_limit <= 0:
            raise ValueError('invalid worker/upload limits')
        if not self.data_root.is_absolute() or self.data_root.is_symlink():
            raise ValueError('data_root must be an absolute private directory')
        self.data_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.data_root.stat().st_mode & 0o077:
            raise ValueError('data_root must have mode 0700')
        file = self.credentials_file if self.auth_mode == 'dev-only' else self.host_registry
        if file is None or not file.is_absolute() or file.is_symlink() or file.stat().st_mode & 0o077:
            raise ValueError('authentication registry must be a private absolute file')
        if self.auth_mode == 'dsh-account' and self.credentials_file is not None:
            raise ValueError('Host mode cannot accept development credentials')

    @classmethod
    def from_file(cls, path):
        value = json.loads(Path(path).read_text())
        value['data_root'] = Path(value['data_root'])
        for key in ('credentials_file','host_registry'):
            if value.get(key) is not None:value[key] = Path(value[key])
        return cls(**value)
