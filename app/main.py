"""FastAPI entrypoint for ephemeris-service."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, FastAPI, Query

from app.auth import ApiKeyAuth
from app.cache import SnapshotCache
from app.config import Settings, load_settings
from app.ephemeris import DEFAULT_BODIES, EphemerisEngine
from app.errors import ApiError, register_exception_handlers
from app.logging_config import log_event, setup_logging
from app.models import (
    MoonAspectsQuery,
    MoonAspectsResponse,
    PositionsQuery,
    PositionsResponse,
    SnapshotQuery,
    SnapshotResponse,
)
from app.zodiac import derive_sign_fields

LOGGER = logging.getLogger("ephemeris_service")

ASPECT_ANGLES: dict[str, float] = {
    "conjunction": 0.0,
    "sextile": 60.0,
    "square": 90.0,
    "trine": 120.0,
    "opposition": 180.0,
}



def parse_iso_utc_datetime(value: str) -> datetime:
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ApiError(422, "INVALID_DATE", "Invalid or unparseable datetime") from exc

    if parsed.tzinfo is None:
        raise ApiError(422, "INVALID_DATE", "Datetime must include UTC timezone (Z)")

    offset = parsed.utcoffset()
    if offset is None or offset != timedelta(0):
        raise ApiError(422, "INVALID_DATE", "Datetime must be in UTC")

    return parsed.astimezone(timezone.utc)



def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ApiError(422, "INVALID_DATE", "Invalid or unparseable date") from exc



def parse_bodies_param(value: str | None) -> list[str]:
    if value is None or value.strip() == "":
        return DEFAULT_BODIES.copy()

    bodies = [segment.strip().lower() for segment in value.split(",") if segment.strip()]
    if not bodies:
        return DEFAULT_BODIES.copy()

    unknown = [name for name in bodies if name not in DEFAULT_BODIES]
    if unknown:
        raise ApiError(422, "UNKNOWN_BODY", f"Unknown body name: {unknown[0]}")

    # Preserve order while removing duplicates.
    deduped = list(dict.fromkeys(bodies))
    return deduped



def parse_orb(value: str | None) -> float:
    if value is None or value.strip() == "":
        return 6.0
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ApiError(422, "INVALID_DATE", "Invalid orb value") from exc
    if parsed < 0:
        raise ApiError(422, "INVALID_DATE", "Orb must be non-negative")
    return parsed



def require_param(name: str, value: str | None) -> str:
    if value is None or value.strip() == "":
        raise ApiError(422, "MISSING_PARAM", f"Missing required parameter: {name}")
    return value



def format_utc(dt_utc: datetime) -> str:
    return dt_utc.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")



def shortest_angle_diff(a: float, b: float) -> float:
    diff = abs((a - b) % 360.0)
    return min(diff, 360.0 - diff)



def create_app(settings: Settings | None = None) -> FastAPI:
    setup_logging()
    active_settings = settings or load_settings()
    engine = EphemerisEngine(ephe_path=active_settings.ephe_path)
    cache = SnapshotCache(cache_dir=active_settings.cache_dir)
    auth = ApiKeyAuth(active_settings.api_key)

    app = FastAPI(title="ephemeris-service", version="1.0.0")
    register_exception_handlers(app)

    @app.on_event("startup")
    async def log_startup() -> None:
        log_event(
            LOGGER,
            "Service startup",
            ephe_path=active_settings.ephe_path,
            cache_dir=active_settings.cache_dir,
            auth_enabled=active_settings.auth_enabled,
        )
        if not active_settings.auth_enabled:
            LOGGER.warning("API key auth disabled (API_KEY not set)")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/positions", response_model=PositionsResponse, dependencies=[Depends(auth)])
    async def positions(
        dt: str | None = Query(default=None),
        bodies: str | None = Query(default=None),
    ) -> PositionsResponse:
        _ = PositionsQuery(dt=dt, bodies=bodies)
        dt_value = require_param("dt", dt)
        dt_utc = parse_iso_utc_datetime(dt_value)
        body_names = parse_bodies_param(bodies)

        started = time.perf_counter()
        body_positions = engine.calculate_positions(dt_utc, body_names)
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
        log_event(LOGGER, "Positions computed", endpoint="/v1/positions", duration_ms=elapsed_ms)

        return PositionsResponse(dt_utc=format_utc(dt_utc), bodies=body_positions)

    @app.get("/v1/snapshot/daily", response_model=SnapshotResponse, dependencies=[Depends(auth)])
    async def snapshot_daily(
        date_param: str | None = Query(default=None, alias="date"),
        tz: str | None = Query(default=None),
    ) -> SnapshotResponse:
        _ = SnapshotQuery(date=date_param, tz=tz)
        raw_date = require_param("date", date_param)
        snapshot_date = parse_date(raw_date)
        tz_name = tz or active_settings.default_tz
        cache_key = f"{snapshot_date.isoformat()}_{tz_name}"

        cached_payload = cache.get(cache_key)
        if cached_payload is not None:
            log_event(LOGGER, "Snapshot cache hit", endpoint="/v1/snapshot/daily", cache_key=cache_key)
            return SnapshotResponse(**cached_payload, cached=True)

        log_event(LOGGER, "Snapshot cache miss", endpoint="/v1/snapshot/daily", cache_key=cache_key)
        dt_utc = engine.local_midnight_to_utc(snapshot_date, tz_name)

        started = time.perf_counter()
        body_positions = engine.calculate_positions(dt_utc, DEFAULT_BODIES)
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
        log_event(
            LOGGER,
            "Snapshot computed",
            endpoint="/v1/snapshot/daily",
            duration_ms=elapsed_ms,
            cache_key=cache_key,
        )

        payload: dict[str, Any] = {
            "date": snapshot_date.isoformat(),
            "timezone": tz_name,
            "dt_utc": format_utc(dt_utc),
            "bodies": [item.model_dump() for item in body_positions],
        }
        cache.set(cache_key, payload)

        return SnapshotResponse(**payload, cached=False)

    @app.get("/v1/moon/aspects", response_model=MoonAspectsResponse, dependencies=[Depends(auth)])
    async def moon_aspects(
        date_param: str | None = Query(default=None, alias="date"),
        tz: str | None = Query(default=None),
        orb: str | None = Query(default=None),
    ) -> MoonAspectsResponse:
        _ = MoonAspectsQuery(date=date_param, tz=tz, orb=orb)
        raw_date = require_param("date", date_param)
        local_date = parse_date(raw_date)
        tz_name = tz or active_settings.default_tz
        orb_value = parse_orb(orb)

        dt_utc = engine.local_midnight_to_utc(local_date, tz_name)

        started = time.perf_counter()
        bodies = engine.calculate_positions(dt_utc, DEFAULT_BODIES)
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
        log_event(LOGGER, "Moon aspects computed", endpoint="/v1/moon/aspects", duration_ms=elapsed_ms)

        by_name = {body.name: body for body in bodies}
        moon = by_name["moon"]
        aspects: list[dict[str, Any]] = []

        for body_name in DEFAULT_BODIES:
            if body_name == "moon":
                continue
            body_position = by_name[body_name]
            actual = shortest_angle_diff(moon.longitude, body_position.longitude)
            for aspect_name, exact in ASPECT_ANGLES.items():
                orb_used = abs(actual - exact)
                if orb_used <= orb_value:
                    moon_sign_index, moon_sign, moon_degree_in_sign = derive_sign_fields(moon.longitude)
                    body_sign_index, body_sign, body_degree_in_sign = derive_sign_fields(body_position.longitude)
                    aspects.append(
                        {
                            "body": body_name,
                            "aspect": aspect_name,
                            "exact_angle": exact,
                            "actual_angle": round(actual, 4),
                            "orb_used": round(orb_used, 4),
                            "moon_longitude": round(moon.longitude, 4),
                            "body_longitude": round(body_position.longitude, 4),
                            "moon_sign_index": moon_sign_index,
                            "moon_sign": moon_sign,
                            "moon_degree_in_sign": round(float(moon_degree_in_sign), 4),
                            "body_sign_index": body_sign_index,
                            "body_sign": body_sign,
                            "body_degree_in_sign": round(float(body_degree_in_sign), 4),
                        }
                    )
                    break

        return MoonAspectsResponse(
            date=local_date.isoformat(),
            timezone=tz_name,
            orb=orb_value,
            aspects=aspects,
        )

    return app


app = create_app()
