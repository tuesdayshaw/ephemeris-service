"""Environment configuration loading."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    ephe_path: str
    api_key: str
    cache_dir: str
    default_tz: str

    @property
    def auth_enabled(self) -> bool:
        return bool(self.api_key)



def load_settings() -> Settings:
    load_dotenv(override=False)
    return Settings(
        ephe_path=os.getenv("EPHE_PATH", "./ephe"),
        api_key=os.getenv("API_KEY", ""),
        cache_dir=os.getenv("CACHE_DIR", "./cache"),
        default_tz=os.getenv("TZ", "America/Chicago"),
    )
