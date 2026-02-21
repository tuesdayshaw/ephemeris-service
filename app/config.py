"""Environment configuration loading."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    ephe_path: str
    api_key: str
    cache_dir: str
    default_tz: str
    allowed_origins: str = ""
    allowed_hosts: str = ""
    disable_docs: bool = False

    @property
    def auth_enabled(self) -> bool:
        return bool(self.api_key)

    @property
    def allowed_origins_list(self) -> List[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]

    @property
    def allowed_hosts_list(self) -> List[str]:
        return [item.strip() for item in self.allowed_hosts.split(",") if item.strip()]


def _parse_bool_env(value: str, default: bool) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default



def load_settings() -> Settings:
    load_dotenv(override=False)
    return Settings(
        ephe_path=os.getenv("EPHE_PATH", "./ephe"),
        api_key=os.getenv("API_KEY", ""),
        cache_dir=os.getenv("CACHE_DIR", "./cache"),
        default_tz=os.getenv("TZ", "America/Chicago"),
        allowed_origins=os.getenv("ALLOWED_ORIGINS", ""),
        allowed_hosts=os.getenv("ALLOWED_HOSTS", ""),
        disable_docs=_parse_bool_env(os.getenv("DISABLE_DOCS", "false"), default=False),
    )
