from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _resolve_ephe_path() -> str:
    candidate = os.getenv("EPHE_PATH", "").strip()
    if not candidate:
        pytest.skip("EPHE_PATH is not set; integration tests require Swiss Ephemeris data files")
    if not Path(candidate).exists():
        pytest.skip(f"EPHE_PATH does not exist: {candidate}")
    return candidate


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    ephe_path = _resolve_ephe_path()
    settings = Settings(
        ephe_path=ephe_path,
        api_key="test-key",
        cache_dir=str(tmp_path / "cache"),
        default_tz="America/Chicago",
    )
    app = create_app(settings)
    return TestClient(app)


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_positions_known_date_ranges(client: TestClient) -> None:
    response = client.get(
        "/v1/positions",
        params={"dt": "2025-06-15T12:00:00Z"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["dt_utc"] == "2025-06-15T12:00:00Z"
    assert len(payload["bodies"]) == 10
    for body in payload["bodies"]:
        assert 0.0 <= body["longitude"] < 360.0


def test_snapshot_daily_cache_hit(client: TestClient) -> None:
    params = {"date": "2025-06-15", "tz": "America/Chicago"}
    headers = {"X-API-Key": "test-key"}

    first = client.get("/v1/snapshot/daily", params=params, headers=headers)
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["cached"] is False

    second = client.get("/v1/snapshot/daily", params=params, headers=headers)
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["cached"] is True
    assert second_payload["bodies"] == first_payload["bodies"]
