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
        assert 0 <= body["sign_index"] <= 11
        assert isinstance(body["sign"], str)
        assert 0.0 <= body["degree_in_sign"] < 30.0


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
    for body in second_payload["bodies"]:
        assert "sign_index" in body
        assert "sign" in body
        assert "degree_in_sign" in body
    assert second_payload["bodies"] == first_payload["bodies"]


def test_moon_aspects_include_sign_fields(client: TestClient) -> None:
    response = client.get(
        "/v1/moon/aspects",
        params={"date": "2025-06-15", "tz": "America/Chicago", "orb": "180"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["aspects"]
    item = payload["aspects"][0]
    assert "moon_longitude" in item
    assert "body_longitude" in item
    assert "moon_sign_index" in item
    assert "moon_sign" in item
    assert "moon_degree_in_sign" in item
    assert "body_sign_index" in item
    assert "body_sign" in item
    assert "body_degree_in_sign" in item
