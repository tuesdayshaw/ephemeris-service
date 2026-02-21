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


def test_moon_phase_ranges(client: TestClient) -> None:
    response = client.get(
        "/v1/moon/phase",
        params={"dt": "2025-06-15T12:00:00Z"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert "dt_utc" in payload
    assert "phase_angle_deg" in payload
    assert "illuminated_fraction" in payload
    assert "is_waxing" in payload
    assert "phase_name" in payload

    assert payload["dt_utc"] == "2025-06-15T12:00:00Z"
    assert 0.0 <= payload["phase_angle_deg"] <= 180.0
    assert 0.0 <= payload["illuminated_fraction"] <= 1.0
    assert isinstance(payload["is_waxing"], bool)
    assert payload["phase_name"] in {
        "new",
        "waxing_crescent",
        "first_quarter",
        "waxing_gibbous",
        "full",
        "waning_gibbous",
        "last_quarter",
        "waning_crescent",
    }


def test_aspects_ranges_and_fields(client: TestClient) -> None:
    response = client.get(
        "/v1/aspects",
        params={"dt": "2025-06-15T12:00:00Z", "orb": "180"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert "dt_utc" in payload
    assert "orb" in payload
    assert "aspects" in payload
    assert payload["aspects"]

    item = payload["aspects"][0]
    assert "body_a" in item
    assert "body_b" in item
    assert "aspect" in item
    assert "exact_angle" in item
    assert "separation_deg" in item
    assert "orb_used" in item
    assert "applying" in item
    assert "body_a_longitude" in item
    assert "body_b_longitude" in item
    assert "body_a_sign_index" in item
    assert "body_a_sign" in item
    assert "body_a_degree_in_sign" in item
    assert "body_b_sign_index" in item
    assert "body_b_sign" in item
    assert "body_b_degree_in_sign" in item
    assert 0.0 <= item["separation_deg"] <= 180.0


def test_retrogrades_structure(client: TestClient) -> None:
    response = client.get(
        "/v1/retrogrades",
        params={"dt": "2025-06-15T12:00:00Z"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert "dt_utc" in payload
    assert "bodies" in payload
    assert payload["dt_utc"] == "2025-06-15T12:00:00Z"
    assert payload["bodies"]

    item = payload["bodies"][0]
    assert "name" in item
    assert "longitude" in item
    assert "speed_deg_per_day" in item
    assert "is_retrograde" in item
    assert "sign_index" in item
    assert "sign" in item
    assert "degree_in_sign" in item
    assert isinstance(item["is_retrograde"], bool)


def test_daily_windows_structure(client: TestClient) -> None:
    response = client.get(
        "/v1/daily/windows",
        params={"date": "2025-06-15", "tz": "America/Chicago", "orb": "180"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert "dt_start_utc" in payload
    assert "dt_end_utc" in payload
    assert "moon_sign_ingresses" in payload
    assert "moon_exact_aspects" in payload
    assert isinstance(payload["moon_sign_ingresses"], list)
    assert isinstance(payload["moon_exact_aspects"], list)

    if payload["moon_sign_ingresses"]:
        ingress = payload["moon_sign_ingresses"][0]
        assert "from_sign" in ingress
        assert "to_sign" in ingress
        assert "dt_utc" in ingress

    if payload["moon_exact_aspects"]:
        aspect = payload["moon_exact_aspects"][0]
        assert "body" in aspect
        assert "aspect" in aspect
        assert "exact_angle" in aspect
        assert "dt_utc" in aspect
        assert "moon_longitude" in aspect
        assert "body_longitude" in aspect
        assert "moon_sign_index" in aspect
        assert "moon_sign" in aspect
        assert "moon_degree_in_sign" in aspect
        assert "body_sign_index" in aspect
        assert "body_sign" in aspect
        assert "body_degree_in_sign" in aspect
