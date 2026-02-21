"""SQLite-backed cache for daily snapshots."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any


class SnapshotCache:
    def __init__(self, cache_dir: str) -> None:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        self._db_path = str(Path(cache_dir) / "snapshots.sqlite3")
        self._lock = Lock()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    cache_key TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.commit()

    def get(self, cache_key: str) -> dict[str, Any] | None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT payload_json FROM snapshots WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def set(self, cache_key: str, payload: dict[str, Any]) -> None:
        payload_json = json.dumps(payload, separators=(",", ":"))
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO snapshots (cache_key, payload_json)
                    VALUES (?, ?)
                    """,
                    (cache_key, payload_json),
                )
                conn.commit()
