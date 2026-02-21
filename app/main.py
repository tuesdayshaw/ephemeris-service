"""FastAPI entrypoint for ephemeris-service."""

from __future__ import annotations

import logging
import math
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.auth import ApiKeyAuth
from app.cache import SnapshotCache
from app.config import Settings, load_settings
from app.ephemeris import DEFAULT_BODIES, EphemerisEngine
from app.errors import ApiError, register_exception_handlers
from app.logging_config import log_event, setup_logging
from app.models import (
    AspectsQuery,
    AspectsResponse,
    DailyWindowsQuery,
    DailyWindowsResponse,
    MoonAspectsQuery,
    MoonAspectsResponse,
    MoonPhaseQuery,
    MoonPhaseResponse,
    PositionsQuery,
    PositionsResponse,
    RetrogradesQuery,
    RetrogradesResponse,
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
DEFAULT_ASPECTS: list[str] = list(ASPECT_ANGLES.keys())
DEFAULT_RETROGRADE_BODIES: list[str] = [
    "mercury",
    "venus",
    "mars",
    "jupiter",
    "saturn",
    "uranus",
    "neptune",
    "pluto",
]
DEFAULT_DAILY_WINDOW_BODIES: list[str] = [
    "sun",
    "mercury",
    "venus",
    "mars",
    "jupiter",
    "saturn",
    "uranus",
    "neptune",
    "pluto",
]



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



def parse_aspects_param(value: str | None) -> list[str]:
    if value is None or value.strip() == "":
        return DEFAULT_ASPECTS.copy()

    aspects = [segment.strip().lower() for segment in value.split(",") if segment.strip()]
    if not aspects:
        return DEFAULT_ASPECTS.copy()

    unknown = [name for name in aspects if name not in ASPECT_ANGLES]
    if unknown:
        raise ApiError(422, "INVALID_DATE", f"Unknown aspect name: {unknown[0]}")

    # Preserve order while removing duplicates.
    deduped = list(dict.fromkeys(aspects))
    return deduped


def parse_retrograde_bodies_param(value: str | None) -> list[str]:
    if value is None or value.strip() == "":
        return DEFAULT_RETROGRADE_BODIES.copy()

    bodies = [segment.strip().lower() for segment in value.split(",") if segment.strip()]
    if not bodies:
        return DEFAULT_RETROGRADE_BODIES.copy()

    unknown = [name for name in bodies if name not in DEFAULT_RETROGRADE_BODIES]
    if unknown:
        raise ApiError(422, "UNKNOWN_BODY", f"Unknown body name: {unknown[0]}")

    # Preserve order while removing duplicates.
    deduped = list(dict.fromkeys(bodies))
    return deduped


def parse_daily_window_bodies_param(value: str | None) -> list[str]:
    if value is None or value.strip() == "":
        return DEFAULT_DAILY_WINDOW_BODIES.copy()

    bodies = [segment.strip().lower() for segment in value.split(",") if segment.strip()]
    if not bodies:
        return DEFAULT_DAILY_WINDOW_BODIES.copy()

    unknown = [name for name in bodies if name not in DEFAULT_DAILY_WINDOW_BODIES]
    if unknown:
        raise ApiError(422, "UNKNOWN_BODY", f"Unknown body name: {unknown[0]}")

    # Preserve order while removing duplicates.
    deduped = list(dict.fromkeys(bodies))
    return deduped


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

    app_kwargs: dict[str, Any] = {"title": "ephemeris-service", "version": "1.0.0"}
    if active_settings.disable_docs:
        app_kwargs.update({"docs_url": None, "redoc_url": None, "openapi_url": None})
    app = FastAPI(**app_kwargs)

    if active_settings.allowed_origins_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=active_settings.allowed_origins_list,
            allow_credentials=False,
            allow_methods=["GET"],
            allow_headers=["*"],
        )

    if active_settings.allowed_hosts_list:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=active_settings.allowed_hosts_list,
        )

    register_exception_handlers(app)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}
    
    @app.get("/")
    async def root() -> dict[str, str]:
        return {"service": "ephemeris-service", "status": "ok"}

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

    @app.get("/v1/retrogrades", response_model=RetrogradesResponse, dependencies=[Depends(auth)])
    async def retrogrades(
        dt: str | None = Query(default=None),
        bodies: str | None = Query(default=None),
        retrograde_only: bool = Query(default=False),
    ) -> RetrogradesResponse:
        _ = RetrogradesQuery(dt=dt, bodies=bodies, retrograde_only=retrograde_only)
        dt_value = require_param("dt", dt)
        dt_utc = parse_iso_utc_datetime(dt_value)
        body_names = parse_retrograde_bodies_param(bodies)

        started = time.perf_counter()
        positions = engine.calculate_positions(dt_utc, body_names)
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
        log_event(LOGGER, "Retrogrades computed", endpoint="/v1/retrogrades", duration_ms=elapsed_ms)

        payload_bodies = [
            {
                "name": body.name,
                "longitude": round(body.longitude, 4),
                "speed_deg_per_day": round(body.speed_deg_per_day, 8),
                "is_retrograde": body.is_retrograde,
                "sign_index": body.sign_index,
                "sign": body.sign,
                "degree_in_sign": round(body.degree_in_sign, 4),
            }
            for body in positions
            if not retrograde_only or body.is_retrograde
        ]

        return RetrogradesResponse(dt_utc=format_utc(dt_utc), bodies=payload_bodies)

    @app.get("/v1/daily/windows", response_model=DailyWindowsResponse, dependencies=[Depends(auth)])
    async def daily_windows(
        date_param: str | None = Query(default=None, alias="date"),
        tz: str | None = Query(default=None),
        orb: str | None = Query(default=None),
        bodies: str | None = Query(default=None),
        aspects: str | None = Query(default=None),
    ) -> DailyWindowsResponse:
        _ = DailyWindowsQuery(date=date_param, tz=tz, orb=orb, bodies=bodies, aspects=aspects)
        raw_date = require_param("date", date_param)
        local_date = parse_date(raw_date)
        tz_name = tz or active_settings.default_tz
        orb_value = parse_orb(orb)
        body_names = parse_daily_window_bodies_param(bodies)
        aspect_names = parse_aspects_param(aspects)

        dt_start_utc = engine.local_midnight_to_utc(local_date, tz_name)
        dt_end_utc = engine.local_midnight_to_utc(local_date + timedelta(days=1), tz_name)

        started = time.perf_counter()
        position_cache: dict[tuple[datetime, tuple[str, ...]], dict[str, Any]] = {}

        def get_positions_map(dt_utc: datetime, names: list[str]) -> dict[str, Any]:
            key = (dt_utc, tuple(names))
            cached = position_cache.get(key)
            if cached is not None:
                return cached
            calculated = engine.calculate_positions(dt_utc, names)
            by_name = {item.name: item for item in calculated}
            position_cache[key] = by_name
            return by_name

        def delta_to_exact(dt_utc: datetime, body_name: str, exact_angle: float) -> float:
            """
            Signed angular difference (deg) between the current Moon-body longitude delta and an exact aspect angle.
            Returns a value in [-180, 180).
            This avoids missing conjunction/opposition events that may not be detected with absolute separations.
            """
            by_name = get_positions_map(dt_utc, ["moon", body_name])
            moon_lon = by_name["moon"].longitude
            body_lon = by_name[body_name].longitude
            delta = (moon_lon - body_lon) % 360.0
            wrapped = ((delta - exact_angle + 180.0) % 360.0) - 180.0
            return wrapped

        def refine_sign_change(left_dt: datetime, right_dt: datetime) -> datetime:
            left = left_dt
            right = right_dt
            left_sign = get_positions_map(left, ["moon"])["moon"].sign_index
            while (right - left).total_seconds() > 60:
                mid = left + (right - left) / 2
                mid_sign = get_positions_map(mid, ["moon"])["moon"].sign_index
                if mid_sign == left_sign:
                    left = mid
                else:
                    right = mid
            return right

        def refine_aspect_root(left_dt: datetime, right_dt: datetime, body_name: str, exact_angle: float) -> datetime:
            f_left = delta_to_exact(left_dt, body_name, exact_angle)
            if f_left == 0:
                return left_dt
            f_right = delta_to_exact(right_dt, body_name, exact_angle)
            if f_right == 0:
                return right_dt

            left = left_dt
            right = right_dt
            while (right - left).total_seconds() > 60:
                mid = left + (right - left) / 2
                f_mid = delta_to_exact(mid, body_name, exact_angle)
                if f_mid == 0:
                    return mid
                if f_left * f_mid <= 0:
                    right = mid
                    f_right = f_mid
                else:
                    left = mid
                    f_left = f_mid
            return left + (right - left) / 2

        sample_step = timedelta(minutes=15)
        sample_times: list[datetime] = []
        cursor = dt_start_utc
        while cursor <= dt_end_utc:
            sample_times.append(cursor)
            cursor += sample_step
        if sample_times[-1] != dt_end_utc:
            sample_times.append(dt_end_utc)

        sample_moon_signs: dict[datetime, tuple[int, str]] = {}
        for sample_dt in sample_times:
            positions = get_positions_map(sample_dt, ["moon", *body_names])
            moon_pos = positions["moon"]
            sample_moon_signs[sample_dt] = (moon_pos.sign_index, moon_pos.sign)

        ingress_events: list[tuple[datetime, dict[str, Any]]] = []
        for idx in range(len(sample_times) - 1):
            left_dt = sample_times[idx]
            right_dt = sample_times[idx + 1]
            left_sign_index, left_sign = sample_moon_signs[left_dt]
            _, right_sign = sample_moon_signs[right_dt]
            if sample_moon_signs[left_dt][0] != sample_moon_signs[right_dt][0]:
                ingress_dt = refine_sign_change(left_dt, right_dt)
                ingress_events.append(
                    (
                        ingress_dt,
                        {
                            "from_sign": left_sign,
                            "to_sign": right_sign,
                            "dt_utc": format_utc(ingress_dt),
                        },
                    )
                )

        aspect_events_by_key: dict[tuple[str, str, int], tuple[datetime, dict[str, Any]]] = {}
        for body_name in body_names:
            for aspect_name in aspect_names:
                exact_angle = ASPECT_ANGLES[aspect_name]
                for idx in range(len(sample_times) - 1):
                    left_dt = sample_times[idx]
                    right_dt = sample_times[idx + 1]
                    f_left = delta_to_exact(left_dt, body_name, exact_angle)
                    f_right = delta_to_exact(right_dt, body_name, exact_angle)
                    if f_left == 0 or f_right == 0 or (f_left * f_right < 0):
                        event_dt = refine_aspect_root(left_dt, right_dt, body_name, exact_angle)
                        if abs(delta_to_exact(event_dt, body_name, exact_angle)) > orb_value:
                            continue
                        rounded_minute = int(event_dt.timestamp() // 60)
                        event_key = (body_name, aspect_name, rounded_minute)
                        positions = get_positions_map(event_dt, ["moon", body_name])
                        moon_pos = positions["moon"]
                        body_pos = positions[body_name]
                        event = (
                            event_dt,
                            {
                                "body": body_name,
                                "aspect": aspect_name,
                                "exact_angle": exact_angle,
                                "dt_utc": format_utc(event_dt),
                                "moon_longitude": round(moon_pos.longitude, 4),
                                "body_longitude": round(body_pos.longitude, 4),
                                "moon_sign_index": moon_pos.sign_index,
                                "moon_sign": moon_pos.sign,
                                "moon_degree_in_sign": round(moon_pos.degree_in_sign, 4),
                                "body_sign_index": body_pos.sign_index,
                                "body_sign": body_pos.sign,
                                "body_degree_in_sign": round(body_pos.degree_in_sign, 4),
                            },
                        )
                        if event_key not in aspect_events_by_key or event[0] < aspect_events_by_key[event_key][0]:
                            aspect_events_by_key[event_key] = event

        ingress_events.sort(key=lambda item: item[0])
        aspect_events = sorted(aspect_events_by_key.values(), key=lambda item: item[0])
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
        log_event(LOGGER, "Daily windows computed", endpoint="/v1/daily/windows", duration_ms=elapsed_ms)

        return DailyWindowsResponse(
            date=local_date.isoformat(),
            timezone=tz_name,
            dt_start_utc=format_utc(dt_start_utc),
            dt_end_utc=format_utc(dt_end_utc),
            moon_sign_ingresses=[payload for _, payload in ingress_events],
            moon_exact_aspects=[payload for _, payload in aspect_events],
        )

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

    @app.get("/v1/aspects", response_model=AspectsResponse, dependencies=[Depends(auth)])
    async def aspects(
        dt: str | None = Query(default=None),
        bodies: str | None = Query(default=None),
        aspects: str | None = Query(default=None),
        orb: str | None = Query(default=None),
    ) -> AspectsResponse:
        _ = AspectsQuery(dt=dt, bodies=bodies, aspects=aspects, orb=orb)
        dt_value = require_param("dt", dt)
        dt_utc = parse_iso_utc_datetime(dt_value)
        body_names = parse_bodies_param(bodies)
        aspect_names = parse_aspects_param(aspects)
        orb_value = parse_orb(orb)

        started = time.perf_counter()
        current_positions = engine.calculate_positions(dt_utc, body_names)
        next_positions = engine.calculate_positions(dt_utc + timedelta(hours=1), body_names)
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
        log_event(LOGGER, "Aspects computed", endpoint="/v1/aspects", duration_ms=elapsed_ms)

        current_by_name = {body.name: body for body in current_positions}
        next_by_name = {body.name: body for body in next_positions}
        matches: list[dict[str, Any]] = []

        for index_a, body_a_name in enumerate(body_names):
            for body_b_name in body_names[index_a + 1 :]:
                body_a_current = current_by_name[body_a_name]
                body_b_current = current_by_name[body_b_name]
                body_a_next = next_by_name[body_a_name]
                body_b_next = next_by_name[body_b_name]

                separation_now = shortest_angle_diff(body_a_current.longitude, body_b_current.longitude)
                separation_next = shortest_angle_diff(body_a_next.longitude, body_b_next.longitude)

                body_a_sign_index, body_a_sign, body_a_degree_in_sign = derive_sign_fields(body_a_current.longitude)
                body_b_sign_index, body_b_sign, body_b_degree_in_sign = derive_sign_fields(body_b_current.longitude)

                for aspect_name in aspect_names:
                    exact_angle = ASPECT_ANGLES[aspect_name]
                    orb_now = abs(separation_now - exact_angle)
                    if orb_now <= orb_value:
                        orb_next = abs(separation_next - exact_angle)
                        matches.append(
                            {
                                "body_a": body_a_name,
                                "body_b": body_b_name,
                                "aspect": aspect_name,
                                "exact_angle": exact_angle,
                                "separation_deg": round(separation_now, 4),
                                "orb_used": round(orb_now, 4),
                                "applying": orb_next < orb_now,
                                "body_a_longitude": round(body_a_current.longitude, 4),
                                "body_b_longitude": round(body_b_current.longitude, 4),
                                "body_a_sign_index": body_a_sign_index,
                                "body_a_sign": body_a_sign,
                                "body_a_degree_in_sign": round(float(body_a_degree_in_sign), 4),
                                "body_b_sign_index": body_b_sign_index,
                                "body_b_sign": body_b_sign,
                                "body_b_degree_in_sign": round(float(body_b_degree_in_sign), 4),
                            }
                        )

        matches.sort(key=lambda item: item["orb_used"])
        return AspectsResponse(dt_utc=format_utc(dt_utc), orb=orb_value, aspects=matches)

    @app.get("/v1/moon/phase", response_model=MoonPhaseResponse, dependencies=[Depends(auth)])
    async def moon_phase(
        dt: str | None = Query(default=None),
    ) -> MoonPhaseResponse:
        _ = MoonPhaseQuery(dt=dt)
        dt_value = require_param("dt", dt)
        dt_utc = parse_iso_utc_datetime(dt_value)

        started = time.perf_counter()
        now_positions = engine.calculate_positions(dt_utc, ["sun", "moon"])
        next_positions = engine.calculate_positions(dt_utc + timedelta(hours=1), ["sun", "moon"])
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
        log_event(LOGGER, "Moon phase computed", endpoint="/v1/moon/phase", duration_ms=elapsed_ms)

        now_by_name = {body.name: body for body in now_positions}
        next_by_name = {body.name: body for body in next_positions}

        current_angle = shortest_angle_diff(now_by_name["moon"].longitude, now_by_name["sun"].longitude)
        next_angle = shortest_angle_diff(next_by_name["moon"].longitude, next_by_name["sun"].longitude)
        is_waxing = next_angle > current_angle

        angle_rad = math.radians(current_angle)
        illuminated_fraction = (1.0 - math.cos(angle_rad)) / 2.0

        if current_angle <= 10.0:
            phase_name = "new"
        elif abs(current_angle - 90.0) <= 10.0 and is_waxing:
            phase_name = "first_quarter"
        elif abs(current_angle - 180.0) <= 10.0:
            phase_name = "full"
        elif abs(current_angle - 90.0) <= 10.0 and not is_waxing:
            phase_name = "last_quarter"
        elif current_angle < 90.0:
            phase_name = "waxing_crescent" if is_waxing else "waning_crescent"
        else:
            phase_name = "waxing_gibbous" if is_waxing else "waning_gibbous"

        return MoonPhaseResponse(
            dt_utc=format_utc(dt_utc),
            phase_angle_deg=current_angle,
            illuminated_fraction=illuminated_fraction,
            is_waxing=is_waxing,
            phase_name=phase_name,
        )

    return app


app = create_app()
